"""Live end-to-end smoke against docker-compose: HTTP and gRPC parity.

Runs the same pool → experiment → gate → select → feedback flow against both
transports and asserts the Pydantic objects coming out match. Hits the proxy
on http://localhost:8080 and localhost:50050.

Usage:
    QBRIX_API_KEY=optiq_xxx python bin/smoke_dual_transport.py
"""

from __future__ import annotations

import os
import sys
from typing import Any

from qbrix import Qbrix
from qbrix.model.experiment import Experiment
from qbrix.model.gate import GateConfig
from qbrix.model.pool import Pool

HTTP_URL = "http://localhost:8080"
GRPC_URL = "localhost:50050"


def _api_key() -> str:
    key = os.environ.get("QBRIX_API_KEY")
    if not key:
        sys.exit("set QBRIX_API_KEY (try `set -a; source .env`)")
    return key


def _create_pool(client: Qbrix, suffix: str) -> Pool:
    return client.pool.create(
        name=f"smoke-{suffix}",
        arms=[
            {"name": "control"},
            {"name": "variant-a"},
            {"name": "variant-b"},
        ],
    )


def _create_experiment(client: Qbrix, pool_id: str, suffix: str) -> Experiment:
    return client.experiment.create(
        name=f"smoke-exp-{suffix}",
        pool_id=pool_id,
        policy="BetaTSPolicy",
        enabled=True,
    )


def _round_trip(client: Qbrix, label: str) -> dict[str, Any]:
    print(f"\n=== {label} ===")
    pool = _create_pool(client, label.lower())
    print(f"  pool:       id={pool.id} name={pool.name} arms={len(pool.arms)}")
    exp = _create_experiment(client, pool.id, label.lower())
    print(f"  experiment: id={exp.id} policy={exp.policy} enabled={exp.enabled}")

    # Optional gate
    gate = client.gate.create(
        exp.id,
        enabled=True,
        rollout_percentage=100.0,
    )
    assert isinstance(gate, GateConfig)
    print(f"  gate:       enabled={gate.enabled} rollout={gate.rollout_percentage}")

    # Select + feedback loop
    arm_counts: dict[str, int] = {}
    for i in range(5):
        result = client.agent.select(exp.id, {"id": f"user-{i}"})
        arm_counts[result.arm.name] = arm_counts.get(result.arm.name, 0) + 1
        client.agent.feedback(result.request_id, reward=1.0 if i % 2 == 0 else 0.0)
    print(f"  select:     {arm_counts}")

    # Cleanup
    client.experiment.delete(exp.id)
    client.pool.delete(pool.id)

    return {
        "pool_type": type(pool).__name__,
        "pool_arms": len(pool.arms),
        "experiment_type": type(exp).__name__,
        "gate_type": type(gate).__name__,
        "arm_counts": arm_counts,
    }


def main() -> int:
    api_key = _api_key()

    with Qbrix(transport="http", api_key=api_key, base_url=HTTP_URL) as http_client:
        http_result = _round_trip(http_client, "HTTP")

    with Qbrix(transport="grpc", api_key=api_key, base_url=GRPC_URL) as grpc_client:
        grpc_result = _round_trip(grpc_client, "gRPC")

    print("\n=== Parity check ===")
    for key in ("pool_type", "experiment_type", "gate_type", "pool_arms"):
        same = http_result[key] == grpc_result[key]
        print(
            f"  {key}: HTTP={http_result[key]} gRPC={grpc_result[key]} {'OK' if same else 'MISMATCH'}"
        )
        if not same:
            return 1

    print("\nALL GOOD. Both transports produced identical Pydantic shapes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
