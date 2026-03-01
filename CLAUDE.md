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

The SDK follows a layered client → resource → model pattern, with sync and async variants throughout.

### Client Layer (`_base_client.py`, `_client.py`)

```
Qbrix / AsyncQbrix                    ← public entry points (users import these)
    ↓ inherits
SyncAPIClient / AsyncAPIClient         ← HTTP logic, retry, error mapping
    ↓ wraps
httpx.Client / httpx.AsyncClient       ← actual HTTP transport
```

`Qbrix` and `AsyncQbrix` expose resources as `@cached_property` — lazily instantiated on first access. The client itself IS the transport (no separate transport layer, despite what SDK-DESIGN.md describes — that abstraction was collapsed during implementation).

**Key divergences from SDK-DESIGN.md:** Client classes are `Qbrix`/`AsyncQbrix` (not `QbrixClient`/`AsyncQbrixClient`). Resource accessors are singular: `client.pool`, `client.experiment`, `client.gate`, `client.agent` (not plural). No `transport/` package exists.

### Resource Layer (`_resource.py`, `resource/`)

Each resource file defines both sync and async variants (`PoolResource`/`AsyncPoolResource`, etc.). Resources hold a reference to the client and delegate HTTP calls through `_get`, `_post`, `_put`, `_patch`, `_delete` helpers from `SyncAPIResource`/`AsyncAPIResource`.

**`cast_to` pattern:** Resource methods pass `cast_to=ModelClass` to the client's `request()` method, which calls `ModelClass.model_validate(data)` on the JSON response. Methods that don't need a response model (like `delete`, `feedback`) omit `cast_to`.

**Dual input types:** All resource methods accept both Pydantic models and raw dicts (e.g., `arms: list[dict | ArmCreate]`, `context: Context | dict`). Serialization uses `isinstance` checks.

### Model Layer (`model/`)

All models are Pydantic v2 `BaseModel` subclasses. Request models (e.g., `PoolCreate`, `ExperimentCreate`) and response models (e.g., `Pool`, `Experiment`) are separate classes. `PaginatedResponse[T]` is a generic wrapper with `items`, `limit`, `offset`, and a `has_more` computed property.

### Config (`_config.py`)

`QbrixConfig` extends `pydantic-settings.BaseSettings` with `env_prefix="QBRIX_"`. Resolution order: constructor kwargs → env vars (`QBRIX_API_KEY`, `QBRIX_BASE_URL`, etc.) → defaults. The `BaseClient.__init__` filters out `None` kwargs before passing to `QbrixConfig` so that env vars aren't shadowed by explicit `None`.

### Error Handling (`exception.py`)

`_base_client._make_status_error()` parses JSON response for `detail` and `context` fields, maps status codes via `STATUS_CODE_TO_EXCEPTION` dict. Unknown status codes fall back to `QbrixAPIError`. `RateLimitedError` parses `Retry-After` header. Network errors map to `QbrixConnectionError`/`QbrixTimeoutError`.

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

## Testing Patterns

Tests use a `MockSyncClient`/`MockAsyncClient` infrastructure (in `conftest.py`) that subclasses the real API client and replaces the httpx client with a mock. Use `mock_client.enqueue({...})` to stage responses and `mock_client.calls[n]` to assert request method/path/body.

Async tests use `@pytest.mark.asyncio` on the class. Test markers: `unit`, `integration`, `slow`.

## Conventions

- Internal modules are prefixed with `_` (e.g., `_base_client.py`, `_config.py`, `_resource.py`)
- Public API surface is defined in `__init__.py` — keep it updated when adding models/exceptions
- Python ≥ 3.10 required (uses `X | Y` union syntax)
- Dependencies: `httpx`, `pydantic`, `pydantic-settings` (runtime); `pytest`, `pytest-asyncio`, `pytest-mock`, `pytest-cov`, `black`, `pre-commit` (dev)
