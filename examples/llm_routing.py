"""LLM model & prompt routing — bounded reward, delayed judged feedback.

Backs https://qbrix.io/docs/llm-routing. Every code block on that page is
lifted from this file.

Three routes (frontier / mid / small), a reward in [0, 1] blending answer
quality against cost, and a context vector describing the request so the
router can learn that short questions go somewhere different from long
tool-using ones.

What this demonstrates that the checkout recipe does not:

  1. The reward does not exist at selection time. A judge has to run. The
     request_id is persisted alongside the generation and fed back later —
     here via a pending queue, in production via your own store.

  2. reward_type="bounded" with use_context — the vector width must equal the
     experiment's dim on every call, for the life of the experiment.

The model call and the judge are simulated. Swap _call_model and _judge for
real ones and the rest of the script is unchanged.

Note on what you will see: selection reads cached parameters, so a burst that
finishes inside one cache window returns a near-even split however much the
learner has worked out. That is the cache, not the router. examples/
checkout_conversion.py has a --refresh-wait flag that demonstrates the effect
directly.

Run:
    export QBRIX_API_KEY=...        # not needed against a dev-mode proxy
    export QBRIX_BASE_URL=http://localhost:8080
    uv run python examples/llm_routing.py
"""

import random
import uuid

import click

from qbrix import Context
from qbrix import Qbrix
from qbrix import QbrixAPIError

# pool and experiment names are unique per workspace, so a script you run twice
# needs a fresh name each time. (a duplicate name currently surfaces as a 500
# rather than a conflict — see OPT-353.)
RUN_ID = uuid.uuid4().hex[:8]

# usd per call, and the quality each route tends to produce on an easy vs a
# hard request. the simulated truth: the small model is fine on easy requests
# and poor on hard ones, which is exactly the pattern a contextual router
# should discover and a global one cannot.
ROUTE_PROFILE = {
    "frontier": {"usd": 0.030, "easy": 0.93, "hard": 0.91},
    "mid": {"usd": 0.004, "easy": 0.90, "hard": 0.74},
    "small": {"usd": 0.0006, "easy": 0.86, "hard": 0.48},
}

MAX_COST_USD = 0.030

# how much quality you will give up to save a full unit of cost. this one
# constant is the entire product decision — it is the thing to argue about in
# review, and changing it invalidates an experiment already in flight.
COST_WEIGHT = 0.25

CONTEXT_DIM = 4
REQUESTS = 4000
FEEDBACK_DELAY = 20  # requests between a generation and its judged reward


def encode(
    prompt_len: int, has_tools: bool, history_turns: int, is_question: bool
) -> list[float]:
    """request -> fixed-width numeric vector. runs on every request, so keep it cheap.

    every feature is scaled into roughly [0, 1]: a raw token count sitting next
    to a 0/1 flag would dominate the linear model on units alone.
    """
    return [
        min(prompt_len / 4000, 1.0),
        1.0 if has_tools else 0.0,
        min(history_turns / 20, 1.0),
        1.0 if is_question else 0.0,
    ]


def reward(quality: float, cost_usd: float) -> float:
    """quality in [0, 1], penalised by cost, clamped back into [0, 1].

    bounded means bounded — an out-of-range reward is a modelling error, not a
    strong opinion, so the clamp is not optional.
    """
    penalty = COST_WEIGHT * min(cost_usd / MAX_COST_USD, 1.0)
    return max(0.0, min(1.0, quality - penalty))


def _call_model(route: str, is_hard: bool) -> tuple[str, float]:
    """stand-in for your provider call. returns (answer, cost_usd)."""
    return f"<answer from {route}>", ROUTE_PROFILE[route]["usd"]


def _judge(route: str, is_hard: bool) -> float:
    """stand-in for an LLM-as-judge or a human rating. returns quality in [0, 1].

    note it never sees which route produced the answer in a real setup — and
    the judge model should not be one of the routes, or it will rate its own
    outputs generously and you will learn a preference for the judge.
    """
    base = ROUTE_PROFILE[route]["hard" if is_hard else "easy"]
    return max(0.0, min(1.0, random.gauss(base, 0.06)))


@click.command()
@click.option("--requests", "n_requests", default=REQUESTS, help="simulated requests")
def main(n_requests: int) -> None:
    with Qbrix() as client:
        pool = client.pool.create(
            name=f"assistant-routes-{RUN_ID}",
            arms=[
                {"name": name, "metadata": {"usd_per_call": profile["usd"]}}
                for name, profile in ROUTE_PROFILE.items()
            ],
        )
        click.echo(f"pool {pool.id} ({len(pool.arms)} routes)")

        experiment = client.experiment.create(
            name=f"assistant-routing-{RUN_ID}",
            pool_id=pool.id,
            policy="auto",
            policy_params={
                "reward_type": "bounded",
                "use_context": True,
                "dim": CONTEXT_DIM,
            },
        )
        click.echo(f"experiment {experiment.id} (policy={experiment.policy})")

        # stands in for your generations table: the request_id has to outlive
        # the request that produced it, because the reward arrives later.
        pending: list[tuple[int, str, str, bool, float]] = []

        served: dict[str, int] = {}
        served_hard: dict[str, int] = {}
        rewarded = 0
        unattributable = 0
        total_cost = 0.0

        for i in range(n_requests):
            is_hard = random.random() < 0.4
            vector = encode(
                prompt_len=(
                    random.randint(2000, 6000) if is_hard else random.randint(40, 400)
                ),
                has_tools=is_hard and random.random() < 0.7,
                history_turns=(
                    random.randint(4, 18) if is_hard else random.randint(0, 2)
                ),
                is_question=not is_hard,
            )

            result = client.agent.select(
                experiment.id,
                context=Context(id=f"conversation-{i:05d}", vector=vector),
            )

            route = result.arm.name if result.arm.name in ROUTE_PROFILE else "mid"
            _answer, cost_usd = _call_model(route, is_hard)
            total_cost += cost_usd

            served[route] = served.get(route, 0) + 1
            if is_hard:
                served_hard[route] = served_hard.get(route, 0) + 1

            if result.request_id is None:
                unattributable += 1
            else:
                pending.append((i, result.request_id, route, is_hard, cost_usd))

            # drain whatever has aged past the judging delay
            ready = [row for row in pending if i - row[0] >= FEEDBACK_DELAY]
            pending = [row for row in pending if i - row[0] < FEEDBACK_DELAY]
            for _tick, request_id, row_route, row_hard, row_cost in ready:
                quality = _judge(row_route, row_hard)
                try:
                    client.agent.feedback(request_id, reward=reward(quality, row_cost))
                    rewarded += 1
                except QbrixAPIError as exc:
                    click.echo(f"feedback failed: {exc}")

        click.echo("\n--- allocation ---")
        for name in sorted(served):
            n = served[name]
            hard = served_hard.get(name, 0)
            click.echo(
                f"  {name:<9} served {n:>5} ({n / n_requests:>4.0%})  "
                f"of which hard {hard:>4} ({hard / n:>4.0%})"
            )
        click.echo(
            f"\n  cost      ${total_cost:.2f} over {n_requests} requests "
            f"(${total_cost / n_requests:.4f}/request)"
        )
        click.echo(
            f"  all-frontier baseline would be "
            f"${ROUTE_PROFILE['frontier']['usd'] * n_requests:.2f}"
        )
        click.echo(f"  rewarded  {rewarded}")
        if pending:
            click.echo(f"  still awaiting judgement: {len(pending)}")
        if unattributable:
            click.echo(f"  no request_id (experiment paused): {unattributable}")


if __name__ == "__main__":
    main()
