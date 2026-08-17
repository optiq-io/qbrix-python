"""Personalization by segment — a declared context schema, no encoding by hand.

Backs https://qbrix.io/docs/personalization-by-segment. Every code block on
that page is lifted from this file.

Three checkout treatments where no single one wins everywhere: express suits a
small basket on a phone, installments suit a large considered basket, and a
returning customer responds to neither. A non-contextual bandit converges on
whichever is best on average and serves it to everybody. A contextual one
learns the segments — provided you can describe a visitor to it.

What this demonstrates that the other recipes do not:

  1. You declare the shape once, at experiment creation, and send named values
     per request. There is no encode() function in this file. The width, the
     one-hot slots and the normalisation are the server's problem.

  2. dim is derived from the schema, never passed. Declaring both is an error,
     because two sources for one number is how a contextual experiment silently
     starts training on garbage.

  3. An undeclared value is absorbed, not rejected: "JP" below never appears in
     the country schema and still selects fine, scored into a reserved `other`
     slot. Your traffic is allowed to surprise you.

When context.vector is still the right answer: you already hold a learned
embedding, the feature is a quantity you derive yourself (a similarity score, a
model prediction, a PCA component), or you are migrating an existing contextual
experiment and need byte-identical encoding. Everything that looks like the
schema below — device, country, plan, price band — is properties.

Note on what you will see: selection reads cached parameters, so a burst that
finishes inside one cache window returns a near-even split per segment however
much the model has worked out. That is the cache, not the model — pass
--refresh-wait to replay the traffic after a refresh and watch the segments
separate.

Run:
    export QBRIX_API_KEY=...        # not needed against a dev-mode proxy
    export QBRIX_BASE_URL=http://localhost:8080
    uv run python examples/personalization.py
    uv run python examples/personalization.py --refresh-wait 330
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

# the shape of a visitor, declared once. categorical values are one-hot with a
# trailing `other` slot; numeric is min-max normalised and clamped; boolean is a
# single 0/1. the server derives dim from this and pins it for the experiment's
# life.
CONTEXT_SCHEMA = [
    {"type": "categorical", "name": "device", "values": ["mobile", "desktop"]},
    {"type": "categorical", "name": "country", "values": ["US", "DE", "TR"]},
    {"type": "numeric", "name": "cart_value", "min": 0, "max": 500},
    {"type": "boolean", "name": "returning"},
]

# the simulated truth. in production this is exactly what you do not know — and
# note no column wins every row, which is the entire reason to go contextual.
SEGMENT_CVR = {
    "mobile-quick": {"standard": 0.028, "express": 0.061, "installments": 0.024},
    "considered": {"standard": 0.035, "express": 0.030, "installments": 0.058},
    "returning": {"standard": 0.064, "express": 0.030, "installments": 0.026},
}

COUNTRIES = ["US", "DE", "TR", "JP"]  # JP is undeclared — it lands in `other`

SESSIONS = 4000


def _visitor() -> dict:
    """one arriving shopper. plain named values — nothing to encode."""
    device = random.choice(["mobile", "desktop"])
    return {
        "device": device,
        "country": random.choice(COUNTRIES),
        # phones carry smaller baskets, which is what makes the segments real
        "cart_value": round(
            random.uniform(15, 120) if device == "mobile" else random.uniform(60, 480),
            2,
        ),
        "returning": random.random() < 0.25,
    }


def _segment(visitor: dict) -> str:
    """which row of SEGMENT_CVR this visitor is drawn from.

    the model never sees this label — it has to recover the split from the
    properties alone. it exists so the summary can score the result.
    """
    if visitor["returning"]:
        return "returning"
    if visitor["device"] == "mobile" and visitor["cart_value"] < 200:
        return "mobile-quick"
    return "considered"


def _run_phase(
    client: Qbrix, experiment_id: str, sessions: int, label: str
) -> tuple[dict[str, dict[str, int]], int, int]:
    """one burst of traffic. returns per-segment allocation, conversions, gaps."""
    served: dict[str, dict[str, int]] = {seg: {} for seg in SEGMENT_CVR}
    conversions = 0
    unattributable = 0

    for i in range(sessions):
        visitor = _visitor()

        result = client.agent.select(
            experiment_id,
            context=Context(id=f"{label}-session-{i:05d}", properties=visitor),
        )

        treatment = result.arm.name
        segment = _segment(visitor)
        served[segment][treatment] = served[segment].get(treatment, 0) + 1

        converted = random.random() < SEGMENT_CVR[segment][treatment]
        conversions += converted

        if result.request_id is None:
            unattributable += 1
            continue
        try:
            client.agent.feedback(result.request_id, reward=1.0 if converted else 0.0)
        except QbrixAPIError as exc:
            click.echo(f"feedback failed: {exc}")

    return served, conversions, unattributable


def _report(label: str, served: dict[str, dict[str, int]], conversions: int) -> None:
    sessions = sum(sum(c.values()) for c in served.values()) or 1
    click.echo(f"\n--- {label}: allocation by segment ---")
    for segment, counts in served.items():
        total = sum(counts.values()) or 1
        best = max(SEGMENT_CVR[segment], key=SEGMENT_CVR[segment].get)
        share = counts.get(best, 0) / total
        click.echo(
            f"  {segment:<13} n={total:>5}  best={best} ({share:.0%} of segment)"
        )
        for name in sorted(counts):
            click.echo(
                f"      {name:<14} {counts[name]:>5} ({counts[name] / total:>4.0%})"
            )

    click.echo(
        f"\n  conversions {conversions} of {sessions} ({conversions / sessions:.2%})"
    )
    best_possible = (
        sum(
            sum(c.values()) * max(SEGMENT_CVR[seg].values())
            for seg, c in served.items()
        )
        / sessions
    )
    click.echo(f"  perfect per-segment routing would be ~{best_possible:.2%}")


@click.command()
@click.option("--sessions", default=SESSIONS, help="simulated visitors")
@click.option(
    "--refresh-wait",
    default=0,
    help=(
        "seconds to pause, then replay the same traffic as a second phase. "
        "selection reads cached parameters, so a burst that finishes inside one "
        "cache window shows an even split per segment no matter what the model "
        "has worked out. pass ~330 to watch the segments actually separate."
    ),
)
def main(sessions: int, refresh_wait: int) -> None:
    with Qbrix() as client:
        pool = client.pool.create(
            name=f"checkout-treatments-{RUN_ID}",
            arms=[
                {"name": "standard"},
                {"name": "express"},
                {"name": "installments"},
            ],
        )
        click.echo(f"pool {pool.id} ({len(pool.arms)} treatments)")

        # a declared schema is itself the request for a contextual strategy —
        # use_context and dim are both implied by it.
        experiment = client.experiment.create(
            name=f"checkout-personalization-{RUN_ID}",
            pool_id=pool.id,
            policy="auto",
            policy_params={
                "reward_type": "binary",
                "context_schema": CONTEXT_SCHEMA,
            },
        )
        click.echo(
            f"experiment {experiment.id} (policy={experiment.policy}, "
            f"dim={experiment.policy_params.get('dim')} derived from the schema)"
        )

        label = "phase-1" if refresh_wait else "run"
        served, conversions, unattributable = _run_phase(
            client, experiment.id, sessions, label
        )
        _report(label, served, conversions)
        if unattributable:
            click.echo(f"  no request_id (experiment paused): {unattributable}")

        if not refresh_wait:
            click.echo(
                "\nevery segment above will look close to an even three-way split, "
                "and that is the cache rather than the model: this whole burst "
                "finished inside one parameter window, so every selection scored "
                "against the same snapshot. re-run with --refresh-wait 330 to watch "
                "the segments separate."
            )
            return

        click.echo(
            f"\nwaiting {refresh_wait}s for parameters to refresh, then replaying "
            f"the same traffic..."
        )
        time.sleep(refresh_wait)

        served2, conversions2, _ = _run_phase(
            client, experiment.id, sessions, "phase-2"
        )
        _report("phase-2", served2, conversions2)
        click.echo(
            "\nphase-2 is what the model actually believes. the reliable thing to "
            "look for is that the segments now pull apart instead of sitting at an "
            "even three-way split, and that they pull apart in different directions "
            "— a non-contextual experiment serves one winner to all three. which "
            "treatment each segment settles on is still moving at this sample size; "
            "raise --sessions to firm it up."
        )


if __name__ == "__main__":
    main()
