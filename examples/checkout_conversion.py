"""Checkout & CTA conversion — the canonical qbrix loop.

Backs https://qbrix.io/docs/checkout-conversion. Every code block on that page
is lifted from this file, so a signature change breaks a script someone runs
rather than silently rotting a docs page.

Three checkout CTA variants, a binary purchase reward, no context vector. The
two things this demonstrates that are easy to get wrong:

  1. The selection response carries no arm metadata — only {id, name, index}.
     You map arm.name to behaviour on your side (CTA_COPY below). Pool metadata
     is available via pool.get() if you would rather it lived in qbrix, but it
     is read once at boot, never per request.

  2. request_id is None when the experiment is paused. Selection still
     succeeds, so code that assumes a string fails later, at feedback time.

Run:
    export QBRIX_API_KEY=...        # not needed against a dev-mode proxy
    export QBRIX_BASE_URL=http://localhost:8080
    uv run python examples/checkout_conversion.py
"""

import random
import time
import uuid

import click

from qbrix import Context
from qbrix import Qbrix
from qbrix import QbrixAPIError

# pool and experiment names are unique per workspace, so a script you run twice
# needs a fresh name each time. (a duplicate name currently surfaces as a 500
# rather than a conflict — see OPT-353.)
RUN_ID = uuid.uuid4().hex[:8]

# the simulated truth this script is trying to discover. in production these
# are exactly what you do not know.
TRUE_CVR = {
    "control": 0.031,
    "urgency": 0.038,
    "social-proof": 0.052,
}

# arm.name -> what your renderer should do. this is the map the docs are about:
# the hot path returns a name, and the behaviour behind it stays in your code.
CTA_COPY = {
    "control": "Complete purchase",
    "urgency": "Complete purchase — 2 left",
    "social-proof": "Join 12,000 buyers",
}

SESSIONS = 4000
ROLLOUT_PERCENTAGE = 100.0


def _run_phase(
    client: Qbrix,
    experiment_id: str,
    sessions: int,
    label: str,
) -> tuple[dict[str, int], dict[str, int], int, int]:
    """one burst of select -> render -> feedback. returns per-arm counters."""
    served: dict[str, int] = {}
    purchases: dict[str, int] = {}
    gated = 0
    unattributable = 0

    for i in range(sessions):
        result = client.agent.select(
            experiment_id,
            context=Context(id=f"{label}-session-{i:05d}"),
        )

        # unknown names fall back to control — this is what protects you the
        # day someone renames an arm in the console. in a real app this string
        # is what you render.
        copy = CTA_COPY.get(result.arm.name, CTA_COPY["control"])
        if i < 3:
            click.echo(f"  {label}-session-{i:05d} → {result.arm.name}: {copy!r}")

        served[result.arm.name] = served.get(result.arm.name, 0) + 1
        if result.is_default:
            gated += 1

        # a paused experiment mints no feedback token. nothing to credit.
        if result.request_id is None:
            unattributable += 1
            continue

        # in production this happens on a later request — the order webhook —
        # with the request id read back off the session.
        purchased = random.random() < TRUE_CVR.get(result.arm.name, 0.03)
        if purchased:
            purchases[result.arm.name] = purchases.get(result.arm.name, 0) + 1

        try:
            # send 0.0 as well as 1.0: a variant with no purchases has to be
            # learned as bad. feeding back only successes teaches the learner
            # that every arm converts at 100%.
            client.agent.feedback(result.request_id, reward=1.0 if purchased else 0.0)
        except QbrixAPIError as exc:
            click.echo(f"feedback failed: {exc}")

    return served, purchases, gated, unattributable


def _report(label: str, served: dict[str, int], purchases: dict[str, int]) -> None:
    total = sum(served.values()) or 1
    click.echo(f"\n--- allocation ({label}) ---")
    for name in sorted(served):
        n = served[name]
        conv = purchases.get(name, 0)
        click.echo(
            f"  {name:<14} served {n:>5} ({n / total:>4.0%})  "
            f"purchases {conv:>4}  observed cvr {conv / n:.2%}  "
            f"(true {TRUE_CVR.get(name, 0):.1%})"
        )


@click.command()
@click.option("--sessions", default=SESSIONS, help="simulated checkout sessions")
@click.option(
    "--rollout",
    default=ROLLOUT_PERCENTAGE,
    help="gate rollout percentage; below 100 some traffic gets the default arm",
)
@click.option(
    "--refresh-wait",
    default=0,
    help=(
        "seconds to pause, then replay the same traffic as a second phase. "
        "selection reads cached parameters, so a burst that finishes inside one "
        "cache window shows an even split no matter what the learner knows. "
        "pass ~330 to watch allocation actually move."
    ),
)
def main(sessions: int, rollout: float, refresh_wait: int) -> None:
    with Qbrix() as client:
        pool = client.pool.create(
            name=f"checkout-cta-{RUN_ID}",
            arms=[
                {"name": "control", "metadata": {"copy": CTA_COPY["control"]}},
                {"name": "urgency", "metadata": {"copy": CTA_COPY["urgency"]}},
                {
                    "name": "social-proof",
                    "metadata": {"copy": CTA_COPY["social-proof"]},
                },
            ],
        )
        click.echo(f"pool {pool.id} ({len(pool.arms)} arms)")

        experiment = client.experiment.create(
            name=f"checkout-cta-conversion-{RUN_ID}",
            pool_id=pool.id,
            policy="auto",
            policy_params={"reward_type": "binary"},
        )
        click.echo(f"experiment {experiment.id} (policy={experiment.policy})")

        # optional. a gate lets you watch the loop on a slice of real traffic
        # before committing the whole funnel to it. anyone outside the rollout
        # is served default_arm_id and comes back with is_default=True — they
        # still get a request_id, so their feedback is accepted normally.
        if rollout < 100.0:
            client.gate.create(
                experiment.id,
                enabled=True,
                rollout_percentage=rollout,
                default_arm_id=pool.arms[0].id,
            )
            click.echo(f"gate at {rollout}% (default={pool.arms[0].name})")

        label = "phase-1" if refresh_wait else "run"
        served, purchases, gated, unattributable = _run_phase(
            client, experiment.id, sessions, label
        )
        _report(label, served, purchases)
        if gated:
            click.echo(f"  served by the gate (is_default): {gated}")
        if unattributable:
            click.echo(f"  no request_id (experiment paused): {unattributable}")

        if not refresh_wait:
            click.echo(
                "\nthe split above will look close to even, and that is the cache "
                "rather than the learner: this whole burst finished inside one "
                "parameter window, so every selection saw the same snapshot. "
                "re-run with --refresh-wait 330 to watch it move."
            )
            return

        click.echo(
            f"\nwaiting {refresh_wait}s for parameters to refresh, then replaying "
            f"the same traffic..."
        )
        time.sleep(refresh_wait)

        served2, purchases2, _, _ = _run_phase(
            client, experiment.id, sessions, "phase-2"
        )
        _report("phase-2", served2, purchases2)
        click.echo(
            "\nphase-2 is what the learner actually believes. the gap between the "
            "two phases is the refresh interval, not learning speed."
        )


if __name__ == "__main__":
    main()
