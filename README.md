<p align="center">
  <img src="./asset/logo/bb_logo.svg" alt="Qbrix" width="280">
</p>

<p align="center">
  <strong>Python SDK for the qbrix platform.</strong>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
  <img src="https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/eskinmi/c7d91705ef877065365d0febc49e0ea9/raw/qbrix-coverage.json" alt="Coverage">
  <img src="https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/pydantic-v2-e92063?logo=pydantic&logoColor=white" alt="Pydantic v2">
  <img src="https://img.shields.io/badge/httpx-async%20%2B%20sync-1e88e5" alt="httpx">
</p>


---

Typed sync and async clients for [Qbrix](https://github.com/optiq-io/qbrix) — pool/experiment/gate management and the agent select/feedback loop.

## Installation

```bash
pip install qbrix
```

## Quick Start

```python
from qbrix import Qbrix

client = Qbrix(api_key="optiq_xxx", base_url="https://api.qbrix.io")

# 1. Create a pool of arms (variants)
pool = client.pool.create(
    name="homepage-buttons",
    arms=[{"name": "blue"}, {"name": "green"}, {"name": "red"}],
)

# 2. Create an experiment with a bandit policy
exp = client.experiment.create(
    name="button-color-test",
    pool_id=pool.id,
    policy="BetaTSPolicy",
)

# 3. Select an arm for a user
result = client.agent.select(
    experiment_id=exp.id,
    context={"id": "user-123", "metadata": {"country": "US"}},
)
print(result.arm.name)       # "green"
print(result.is_default)     # False (bandit selected)

# 4. Send feedback (reward) after observing the outcome
client.agent.feedback(request_id=result.request_id, reward=1.0)
```

The system learns from every reward and adjusts future selections automatically.

## Async

```python
from qbrix import AsyncQbrix

async with AsyncQbrix(api_key="optiq_xxx") as client:
    result = await client.agent.select(
        experiment_id="exp-uuid",
        context={"id": "user-456"},
    )
    await client.agent.feedback(request_id=result.request_id, reward=1.0)
```

## Configuration

Constructor kwargs take priority over environment variables, which take priority over defaults.

```bash
export QBRIX_API_KEY="optiq_xxx"
export QBRIX_BASE_URL="https://api.qbrix.io"
```

```python
from qbrix import Qbrix

client = Qbrix()  # picks up env vars automatically
```

| Env Var | Default | Description |
|---------|---------|-------------|
| `QBRIX_API_KEY` | `None` | API key (`optiq_xxx`) |
| `QBRIX_BASE_URL` | `http://localhost:8080` | Proxy service URL |
| `QBRIX_TIMEOUT` | `30.0` | Request timeout (seconds) |
| `QBRIX_MAX_RETRIES` | `3` | Retry count on 429/5xx |

## Feature Gates

Attach a feature gate to control rollout before the bandit kicks in:

```python
client.gate.create(
    experiment_id=exp.id,
    enabled=True,
    rollout_percentage=80.0,
    default_arm_id=pool.arms[0].id,
    rules=[
        {"key": "plan", "operator": "==", "value": "enterprise", "arm_id": pool.arms[1].id},
    ],
)

# Gate-matched selections return is_default=True
result = client.agent.select(
    experiment_id=exp.id,
    context={"id": "user-789", "metadata": {"plan": "enterprise"}},
)
print(result.is_default)  # True
```

## Error Handling

```python
from qbrix.exception import NotFoundError, RateLimitedError

try:
    exp = client.experiment.get("nonexistent-id")
except NotFoundError as e:
    print(f"Not found: {e.detail}")
except RateLimitedError as e:
    print(f"Retry after {e.retry_after}s")
```

## Supported Policies

| Policy | Type | Best For |
|--------|------|----------|
| `BetaTSPolicy` | Stochastic | Binary rewards (clicks, conversions) |
| `GaussianTSPolicy` | Stochastic | Continuous rewards |
| `UCB1TunedPolicy` | Stochastic | Theoretical regret guarantees |
| `KLUCBPolicy` | Stochastic | Binary rewards with tight bounds |
| `MOSSPolicy` | Stochastic | Fixed horizon problems |
| `LinUCBPolicy` | Contextual | Linear reward models with features |
| `LinTSPolicy` | Contextual | Linear models with uncertainty |
| `EXP3Policy` | Adversarial | Non-stationary environments |
| `FPLPolicy` | Adversarial | Follow the perturbed leader |

## License

[MIT](LICENSE)
