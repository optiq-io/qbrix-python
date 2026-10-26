# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Python SDK for the Qbrix distributed computing platform — a multi-armed bandit system for site variant optimisation. The SDK wraps the Qbrix proxy service HTTP API (`proxysvc`), providing typed sync and async clients for the request path (`select` / `outcome` on loops) and, until today's API retires, pool/experiment/gate management. This is the `next` branch: it publishes `0.4.0aN` pre-releases for a server with next switched on (`PROXY_NEXT_ENABLED=true`); `main` keeps the stable releases.

The upstream proxy service lives at `../qbrix/svc/proxy` — consult it for API endpoint behavior, request/response shapes, and feature gate evaluation logic. HTTP routes are under `src/proxysvc/transport/http/router/`, gRPC under `src/proxysvc/transport/grpc/`, and per-domain schemas under `src/proxysvc/mod/<domain>/`.

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
- **gRPC** (`_transport/_grpc/`): `_routes.py` maps `(method, path)` → a `ProxyService` or `LoopService` RPC (each `Handler` names its `service`); `_handlers.py` builds proto requests + converts responses; `_convert.py` holds explicit proto↔dict converters; `_error.py` maps `grpc.StatusCode` → the same `QbrixAPIError` subclasses. Paths with no proto RPC raise `NotImplementedError` — see `_HTTP_ONLY` in `_routes.py` for the HTTP-only set (`/api/v1/runtime/*`, `gate.evaluate()`, `experiment.reset()`).

**Known HTTP/gRPC parity gaps** (need an upstream `proxy.proto` change to close — the SDK cannot fix these on its own):

| Field | HTTP | gRPC |
|-------|------|------|
| `GateConfig.default_arm_name`, `rules[].arm_name` | resolved server-side | always `None` — no proto field |
| `GateConfig.updated_at` | real value | always `None` — no proto field |
| `GateConfig.version` | real value | always `1` (model default) — no proto field |
| `Experiment.meta_experiment_id` | real value | always `None` — not in `common.proto` |

`GateConfig.version` is the sharp edge: it is silently *wrong* over gRPC rather than merely absent, so don't build optimistic-concurrency logic on it without `transport="http"`.
- **Vendored protos** (`_transport/_grpc/_proto/`): generated `*_pb2.py`/`.pyi` from `../qbrix/proto/{common,proxy,loop}.proto`. Regenerate with `make proto` (or `bash bin/regen_protos.sh`); committed to git, never hand-edited.

### Resource Layer (`resource/`)

Each resource file defines both sync and async variants (`PoolResource`/`AsyncPoolResource`, etc.). Resources hold a reference to the client and delegate calls through `_get`, `_post`, `_put`, `_patch`, `_delete` helpers from `SyncAPIResource`/`AsyncAPIResource`. The resource layer is transport-agnostic — it predates gRPC and was not modified when gRPC was added.

**`cast_to` pattern:** Resource methods pass `cast_to=ModelClass` to the client's `request()` method, which calls `ModelClass.model_validate(data)` on the JSON response. Methods that don't need a response model (like `delete`) omit `cast_to`.

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
- **Gates:** `POST/GET/PUT/PATCH/DELETE /gates/{experiment_id}`, `POST /gates/{experiment_id}/evaluate` — `gate.update()` sends `PATCH` (partial, matching `pool.update`/`experiment.update`); the proxy's `PUT` full-replace is deliberately unreachable from the SDK since OPT-355. `evaluate` is a read-only dry run and is HTTP-only.
- **Request path:** `POST /select`, `POST /outcome` (next switch on)
- **Policies:** `GET /policies` — supports `?reward_type=` filter (read-only policy discovery)

### Supported Policies

Experiment `policy` field values (must match exactly), mirroring the proxy's `qbrixcore.policy.POLICIES` registry:

- **Thompson Sampling:** `BetaTSPolicy`, `DiscountedTSPolicy`, `GaussianTSPolicy`, `DirichletTSPolicy`, `LinTSPolicy`, `LogisticTSPolicy`
- **UCB:** `UCB1TunedPolicy`, `KLUCBPolicy`, `KLUCBPlusPolicy`, `LinUCBPolicy`, `GLMUCBPolicy`
- **Epsilon-greedy:** `EpsilonPolicy`
- **MOSS:** `MOSSPolicy`, `MOSSAnyTimePolicy`
- **Adversarial:** `EXP3Policy`, `EXP3IXPolicy`, `FPLPolicy`
- **Baseline:** `RandomPolicy`
- **Meta:** `MetaBanditPolicy`

`policy.list()` is the runtime source of truth if `PolicyName` drifts from the registry.

### Request Path (select / outcome)

1. `client.select(loop, context, settings)` → `POST /select` `{loop, context: {unit, properties}}` → `Decision{option{key, name, config}, request_id | None, reason}`. Over gRPC it is `qbrix.loop.LoopService/Select`; an empty `request_id` becomes `None` and `unstruct` restores whole floats in `config` to ints, so both transports return the same `Decision`.
2. `context.unit` is validated locally (non-blank, ≤ 256 chars) before any call.
3. Connection errors, timeouts, 429 and 5xx (gRPC `UNAVAILABLE`, `DEADLINE_EXCEEDED`, `RESOURCE_EXHAUSTED`, `INTERNAL`) return `settings.offline` with reason `offline` and no `request_id` — never raise. 4xx caller errors raise.
4. `client.outcome(request_id, value, id=, at=)` → `POST /outcome` (202 `{id, at}`) / `LoopService/Outcome`. `None` request_id sends nothing. The SDK mints `id` once per call, so transport retries reuse it; `at` goes as ISO 8601 (HTTP) or a `Timestamp` (gRPC).

### Feature Gate Evaluation Order

Gate checks: enabled → schedule (date range) → active hours → rollout percentage (hash-based) → rules (first match wins). Any negative check → return `default_arm`, skip bandit.

## Commands (gRPC)

```bash
# Regenerate vendored gRPC stubs from ../qbrix/proto
make proto                # or: bash bin/regen_protos.sh

# Verify vendored stubs are current (CI check)
make proto-check

# Live select/outcome smoke on HTTP+gRPC, sync+async, against a proxy with next on (make dev-next)
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
