# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Python SDK for the Qbrix distributed computing platform — a multi-armed bandit system for site variant optimisation. The SDK wraps the Qbrix proxy service HTTP API (`proxysvc`), providing typed sync and async clients for pool/experiment/gate management and the agent select/feedback loop.

The upstream proxy service lives at `../qbrix/svc/proxy` — consult it for API endpoint behavior, request/response shapes, and feature gate evaluation logic.

## Commands

```bash
# Install dependencies (uses uv, not pip)
uv sync

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/test_resource_pool.py

# Run a single test by name
uv run pytest tests/test_resource_pool.py -k "test_create_pool"

# Run only unit tests
uv run pytest -m unit

# Run with coverage
uv run pytest --cov=qbrix

# Format
uv run black .

# Type checking (package is PEP 561 typed)
uv run mypy qbrix/
```

## Architecture

The SDK follows a layered client → transport → resource → model pattern, with sync and async variants throughout.

### Client Layer (`_client.py`)

```
Qbrix / AsyncQbrix                       ← public entry points (users import these)
    ↓ composes (transport= kwarg)
Transport / AsyncTransport               ← protocol in _transport/_base.py
    ↓ implemented by
HTTPTransport          GRPCTransport     ← _transport/_http/, _transport/_grpc/
    ↓ wraps                ↓ wraps
httpx.Client           grpc.Channel
```

`Qbrix`/`AsyncQbrix` hold a transport via **composition** (`self._transport`) and delegate the HTTP-shaped verb interface (`get`/`post`/`put`/`patch`/`delete`/`request`) to it. They expose resources as `@cached_property` — lazily instantiated on first access.

Transport is chosen by `Qbrix(transport="http"|"grpc")`, falling back to the `QBRIX_TRANSPORT` env var, then the `base_url` scheme (`grpc://`/`grpcs://` → gRPC), then HTTP. The factory in `_client.py` lazy-imports the transport module so HTTP-only users never need `grpcio` (and vice versa); a missing extra raises a clear `ImportError`.

`qbrix/_base_client.py` is a back-compat shim re-exporting `SyncAPIClient`/`AsyncAPIClient` as aliases of `HTTPTransport`/`AsyncHTTPTransport`.

### Transport Layer (`_transport/`)

Both transports satisfy the `Transport`/`AsyncTransport` protocol (`_transport/_base.py`) — an HTTP-shaped verb interface. Resources call `self._client.post("/api/v1/pools", ...)` and never know which wire format is active.

- **HTTP** (`_transport/_http/_client.py`): httpx-based; retry loop, `_make_status_error`, header construction.
- **gRPC** (`_transport/_grpc/`): `_routes.py` maps `(method, path)` → one of 17 `ProxyService` RPCs; `_handlers.py` builds proto requests + converts responses; `_convert.py` holds explicit proto↔dict converters; `_error.py` maps `grpc.StatusCode` → the same `QbrixAPIError` subclasses. Paths with no proto RPC (`/api/auth/*`, `/api/v1/policies`, `/api/v1/runtime/*`) raise `NotImplementedError` — those resources are HTTP-only.
- **Vendored protos** (`_transport/_grpc/_proto/`): generated `*_pb2.py`/`.pyi` from `../qbrix/proto/{common,proxy}.proto`. Regenerate with `make proto` (or `bash bin/regen_protos.sh`); committed to git, never hand-edited.

### Resource Layer (`resource/`)

Each resource file defines both sync and async variants (`PoolResource`/`AsyncPoolResource`, etc.). Resources hold a reference to the client and delegate calls through `_get`, `_post`, `_put`, `_patch`, `_delete` helpers from `SyncAPIResource`/`AsyncAPIResource`. The resource layer is transport-agnostic — it predates gRPC and was not modified when gRPC was added.

**`cast_to` pattern:** Resource methods pass `cast_to=ModelClass` to the client's `request()` method, which calls `ModelClass.model_validate(data)` on the JSON response. Methods that don't need a response model (like `delete`, `feedback`) omit `cast_to`.

**Dual input types:** All resource methods accept both Pydantic models and raw dicts (e.g., `arms: list[dict | ArmCreate]`, `context: Context | dict`). Serialization uses `isinstance` checks.

### Model Layer (`model/`)

All models are Pydantic v2 `BaseModel` subclasses. Request models (e.g., `PoolCreate`, `ExperimentCreate`) and response models (e.g., `Pool`, `Experiment`) are separate classes. `PaginatedResponse[T]` is a generic wrapper with `items`, `limit`, `offset`, and a `has_more` computed property.

### Config (`_config.py`)

`QbrixConfig` extends `pydantic-settings.BaseSettings` with `env_prefix="QBRIX_"`. Resolution order: constructor kwargs → env vars (`QBRIX_API_KEY`, `QBRIX_BASE_URL`, etc.) → defaults. The `BaseClient.__init__` filters out `None` kwargs before passing to `QbrixConfig` so that env vars aren't shadowed by explicit `None`. HTTP-specific fields: `http2`, `max_connections`, `max_keepalive_connections`. gRPC-specific fields: `grpc_keepalive_time_ms`, `grpc_keepalive_timeout_ms`, `grpc_use_tls` (default `False`).

### Error Handling (`exception.py`)

HTTP: `BaseClient._make_status_error()` parses JSON response for `detail` and `context` fields, maps status codes via `STATUS_CODE_TO_EXCEPTION` dict. `RateLimitedError` parses the `Retry-After` header. gRPC: `_transport/_grpc/_error.py` maps `grpc.StatusCode` → the same exception classes, synthesizing an HTTP-equivalent `status_code`, and pulls `retry-after` from trailing metadata. Both unknown HTTP codes and unknown gRPC statuses fall back to `QbrixAPIError`. Network/deadline errors map to `QbrixConnectionError`/`QbrixTimeoutError`.

## Proxy API Reference

The SDK targets these proxy endpoints (all under `/api/v1`):

- **Pools:** `POST/GET/PATCH/DELETE /pools[/{id}]`, `GET /pools/{id}/experiments`
- **Experiments:** `POST/GET/PATCH/DELETE /experiments[/{id}]` — supports `?search=&enabled=` filters
- **Gates:** `POST/GET/PUT/DELETE /gates/{experiment_id}` — note: update is `PUT` (full replace), not `PATCH`
- **Agent:** `POST /agent/select`, `POST /agent/feedback`

### Supported Policies

Experiment `policy` field values (must match exactly): `BetaTSPolicy`, `GaussianTSPolicy`, `UCB1TunedPolicy`, `KLUCBPolicy`, `EpsilonPolicy`, `MOSSPolicy`, `MOSSAnyTimePolicy`, `LinUCBPolicy`, `LinTSPolicy`, `EXP3Policy`, `FPLPolicy`.

Contextual policies (`LinUCBPolicy`, `LinTSPolicy`) require `context.vector` with length matching the `dim` policy param.

### Agent Select/Feedback Loop

1. `POST /agent/select` → gate evaluation (if configured) → bandit selection → returns `{arm, request_id, is_default}`
2. `request_id` is an HMAC-signed opaque token — store it, pass it unchanged to feedback
3. `POST /agent/feedback` with `{request_id, reward}` → publishes to learning stream
4. `is_default: true` means the gate committed an arm (bypassed bandit)

### Feature Gate Evaluation Order

Gate checks: enabled → schedule (date range) → active hours → rollout percentage (hash-based) → rules (first match wins). Any negative check → return `default_arm`, skip bandit.

## Commands (gRPC)

```bash
# Regenerate vendored gRPC stubs from ../qbrix/proto
make proto                # or: bash bin/regen_protos.sh

# Verify vendored stubs are current (CI check)
make proto-check

# Live HTTP+gRPC parity smoke against a running docker-compose proxy
QBRIX_API_KEY=optiq_xxx uv run python bin/smoke_dual_transport.py
```

## Testing Patterns

HTTP tests use a `MockSyncClient`/`MockAsyncClient` infrastructure (in `conftest.py`) that subclasses the real API client and replaces the httpx client with a mock. Use `mock_client.enqueue({...})` to stage responses and `mock_client.calls[n]` to assert request method/path/body.

gRPC tests use the `grpc_client`/`async_grpc_client` fixtures — a `GRPCTransport` with the channel patched out and `_stub` swapped for a `MagicMock`. Stage proto responses via `grpc_client._stub.<RpcName>.return_value = ...`. gRPC test modules start with `pytest.importorskip("grpc")` and carry the `grpc` marker.

Async tests use `@pytest.mark.asyncio` on the class. Test markers: `unit`, `integration`, `slow`, `grpc`.

## Conventions

- Internal modules are prefixed with `_` (e.g., `_base_client.py`, `_config.py`, `_client.py`)
- Public API surface is defined in `__init__.py` — keep it updated when adding models/exceptions
- Python ≥ 3.10 required (uses `X | Y` union syntax)
- Runtime deps: `click`, `pydantic`, `pydantic-settings` core; `httpx` via the `[http]` extra, `grpcio`+`protobuf` via `[grpc]`, both via `[all]`
- Dev deps: `pytest`, `pytest-asyncio`, `pytest-mock`, `pytest-cov`, `black`, `pre-commit`, plus `qbrix[all]`
- Never hand-edit `qbrix/_transport/_grpc/_proto/` — regenerate with `make proto`
