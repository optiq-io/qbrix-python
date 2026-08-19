"""Handling outages — sub-second timeouts and fail-open fallback for select().

Backs https://qbrix.io/docs/handling-outages. select() sits on your request
path; this script shows the two knobs that keep it from becoming your
incident: a tight per-call timeout, and a `fallback` arm resolved locally
when qbrix can't be reached.

What this demonstrates:

  1. A per-call timeout tighter than the client-wide default (5.0s) — pass
     `timeout=` on the call that's actually on your hot path, not on the
     client constructor.

  2. `fallback=` makes select() fail open: an unreachable proxy resolves the
     declared arm locally (is_fallback=True) instead of raising. The second
     client below points at a black-hole address to simulate that outage
     deterministically, without needing to actually take qbrix down.

  3. feedback(request_id, ...) is a safe no-op whenever request_id is None —
     which is exactly what a fallback selection returns, since there is no
     server-minted token to report against. Call it unconditionally; don't
     guard on is_fallback yourself.

Run:
    export QBRIX_API_KEY=...        # not needed against a dev-mode proxy
    export QBRIX_BASE_URL=http://localhost:8080
    uv run python examples/handling_outages.py
"""

import uuid

import click

from qbrix import Context
from qbrix import Qbrix

RUN_ID = uuid.uuid4().hex[:8]

# a port nothing listens on: connection is refused immediately, so the
# "outage" below is deterministic and doesn't depend on an external host.
UNREACHABLE_BASE_URL = "http://127.0.0.1:1"

SESSIONS = 20


@click.command()
@click.option("--sessions", default=SESSIONS, help="simulated sessions")
def main(sessions: int) -> None:
    with Qbrix() as client:
        pool = client.pool.create(
            name=f"handling-outages-{RUN_ID}",
            arms=[{"name": "control"}, {"name": "upsell"}],
        )
        experiment = client.experiment.create(
            name=f"handling-outages-{RUN_ID}",
            pool_id=pool.id,
            policy="auto",
            policy_params={"reward_type": "binary"},
        )
        click.echo(f"experiment {experiment.id} ({len(pool.arms)} arms)")

        # the arm to serve when qbrix can't be reached — pick something safe
        # to show everyone with no context, not last week's leader. shaped
        # exactly like the arm select() itself returns.
        fallback_arm = {
            "id": pool.arms[0].id,
            "name": pool.arms[0].name,
            "index": pool.arms[0].index,
        }

        # simulates "qbrix is unreachable" deterministically. in production
        # there's no second client — the same client just fails to connect.
        with Qbrix(base_url=UNREACHABLE_BASE_URL, timeout=0.3) as unreachable:
            resolved, fell_back = 0, 0

            for i in range(sessions):
                # every third session simulates an outage.
                use_client = unreachable if i % 3 == 0 else client

                result = use_client.agent.select(
                    experiment.id,
                    context=Context(id=f"session-{i:04d}"),
                    timeout=0.3,
                    fallback=fallback_arm,
                )

                if result.is_fallback:
                    fell_back += 1
                    click.echo(f"  session-{i:04d} -> fallback ({result.arm.name})")
                else:
                    resolved += 1
                    click.echo(f"  session-{i:04d} -> {result.arm.name} (live)")

                # safe unconditionally: a no-op when request_id is None,
                # which is exactly what the fallback branch above returns.
                use_client.agent.feedback(result.request_id, reward=1.0)

        click.echo(
            f"\n{resolved} resolved live, {fell_back} failed open to "
            f"{fallback_arm['name']!r} — feedback() no-op'd for every one of "
            f"the {fell_back} fallback selections, since none had a request_id."
        )


if __name__ == "__main__":
    main()
