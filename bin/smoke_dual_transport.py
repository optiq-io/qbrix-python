"""Live end-to-end smoke against docker-compose: HTTP and gRPC parity.

Runs the same pool → experiment → gate → select → feedback flow against both
transports and asserts the Pydantic objects coming out match. Hits the proxy
on http://localhost:8080 and localhost:50050.

The second leg is contextual: one experiment with a declared context_schema,
created over HTTP and selected against by both transports. On gRPC the
properties travel as a protobuf Struct, and a successful select is itself the
proof that the types survived — cart_value is declared numeric, so had the
Struct flattened it to a string the server's encoder would have rejected the
call.

Usage:
    QBRIX_API_KEY=optiq_xxx python bin/smoke_dual_transport.py
"""

from __future__ import annotations

import os
import sys
import uuid
from typing import Any

from qbrix import Context
from qbrix import Qbrix
from qbrix.model.experiment import Experiment
from qbrix.model.gate import GateConfig
from qbrix.model.pool import Pool

HTTP_URL = "http://localhost:8080"
GRPC_URL = "localhost:50050"

RUN_ID = uuid.uuid4().hex[:8]

CONTEXT_SCHEMA = [
    {"type": "categorical", "name": "device", "values": ["mobile", "desktop"]},
    {"type": "numeric", "name": "cart_value", "min": 0, "max": 500},
    {"type": "boolean", "name": "returning"},
]

# one visitor per shape, so both branches of every property get exercised.
VISITORS = [
    {"device": "mobile", "cart_value": 42.5, "returning": True},
    {"device": "desktop", "cart_value": 310, "returning": False},
    # a value the schema never declared: encoded into the reserved `other`
    # slot rather than rejected.
    {"device": "tablet", "cart_value": 0, "returning": True},
]


def _api_key() -> str:
    key = os.environ.get("QBRIX_API_KEY")
    if not key:
        sys.exit("set QBRIX_API_KEY (try `set -a; source .env`)")
    return key


def _create_pool(client: Qbrix, suffix: str) -> Pool:
    return client.pool.create(
        name=f"smoke-{suffix}-{RUN_ID}",
        arms=[
            {"name": "control"},
            {"name": "variant-a"},
            {"name": "variant-b"},
        ],
    )


def _create_experiment(client: Qbrix, pool_id: str, suffix: str) -> Experiment:
    return client.experiment.create(
        name=f"smoke-exp-{suffix}-{RUN_ID}",
        pool_id=pool_id,
        policy="BetaTSPolicy",
        enabled=True,
    )


def _create_contextual(client: Qbrix) -> tuple[Pool, Experiment]:
    """a pool + experiment with a declared context schema.

    Created over HTTP only, and selected against by both transports: the gRPC
    CreateExperimentRequest carries policy_params as map<string,string>, so a
    schema (a list of dicts) arrives str()-ed and fails to parse. See OPT-399.
    """
    pool = client.pool.create(
        name=f"smoke-ctx-{RUN_ID}",
        arms=[{"name": "express"}, {"name": "standard"}],
    )
    exp = client.experiment.create(
        name=f"smoke-ctx-exp-{RUN_ID}",
        pool_id=pool.id,
        policy="auto",
        policy_params={"reward_type": "binary", "context_schema": CONTEXT_SCHEMA},
        enabled=True,
    )
    # dim is derived from the schema, never sent — assert the server did that.
    dim = exp.policy_params.get("dim")
    expected_dim = 1 + (len(CONTEXT_SCHEMA[0]["values"]) + 1) + 1 + 1
    assert dim == expected_dim, f"dim={dim}, expected {expected_dim}"
    print(f"\ncontextual experiment {exp.id} (dim={dim} derived from the schema)")
    return pool, exp


def _contextual_leg(client: Qbrix, experiment_id: str) -> dict[str, Any]:
    """select with context.properties on whichever transport this client uses.

    On gRPC the properties travel as a protobuf Struct. cart_value is declared
    numeric, so a Struct that flattened it to a string would be rejected by the
    server's encoder — a clean pass here is the type-preservation proof.
    """
    arm_counts: dict[str, int] = {}
    request_id_present = True
    for i, properties in enumerate(VISITORS):
        result = client.agent.select(
            experiment_id,
            Context(id=f"visitor-{i}", properties=properties),
        )
        arm_counts[result.arm.name] = arm_counts.get(result.arm.name, 0) + 1
        request_id_present &= isinstance(result.request_id, str)
        client.agent.feedback(result.request_id, reward=1.0 if i == 0 else 0.0)
    print(f"  ctx select: {arm_counts}")

    # which arms come back is a bandit outcome, not a transport property — the
    # counts are printed but deliberately not compared across transports.
    return {
        "ctx_selections": sum(arm_counts.values()),
        "ctx_request_ids": request_id_present,
    }


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

            # one contextual experiment, selected against by both transports —
            # same schema, same arms, so the results are genuinely comparable.
            # created last so it never overlaps the round trips: the free tier
            # caps active experiments at 3.
            ctx_pool, ctx_exp = _create_contextual(http_client)
            try:
                print("\n=== HTTP · context.properties ===")
                http_result.update(_contextual_leg(http_client, ctx_exp.id))
                print("\n=== gRPC · context.properties ===")
                grpc_result.update(_contextual_leg(grpc_client, ctx_exp.id))
            finally:
                http_client.experiment.delete(ctx_exp.id)
                http_client.pool.delete(ctx_pool.id)

    print("\n=== Parity check ===")
    for key in (
        "pool_type",
        "experiment_type",
        "gate_type",
        "pool_arms",
        "ctx_selections",
        "ctx_request_ids",
    ):
        same = http_result[key] == grpc_result[key]
        print(
            f"  {key}: HTTP={http_result[key]} gRPC={grpc_result[key]} {'OK' if same else 'MISMATCH'}"
        )
        if not same:
            return 1

    print(
        "\nALL GOOD. Both transports produced identical Pydantic shapes, "
        "and both encoded context.properties server-side."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
