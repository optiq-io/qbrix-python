"""Quickstart example for the Qbrix Python SDK.

Creates a pool with three site variants, sets up an experiment with
Thompson Sampling, and configures a feature gate with rollout and rules.

Then runs an event-driven simulation: at each step, either a new user
arrives (selection) or a previous user converts (feedback), chosen at
random with configurable probability.  This mirrors real production
traffic where selections and rewards arrive interleaved.
"""

import random
import click

from qbrix import Qbrix
from qbrix import QbrixAPIError
from qbrix import Context

# -- arm reward distributions (simulated true conversion rates) -----------
ARM_PROBS = {
    "variant-a": 0.130,
    "variant-b": 0.12,
    "variant-c": 0.138,
}

TOTAL_EVENTS = 1000         # total simulation ticks
SELECT_PROB = 0.55           # probability each tick is a selection (vs feedback)
FEEDBACK_DELAY_MIN = 5      # min ticks before a selection becomes eligible for feedback


@click.command
def main() -> None:
    with Qbrix() as client:
        # 1. Create a pool with three arms -----------------------------------
        pool = client.pool.create(
            name="landing-page-variants",
            arms=[
                {"name": "variant-a", "metadata": {"color": "blue"}},
                {"name": "variant-b", "metadata": {"color": "green"}},
                {"name": "variant-c", "metadata": {"color": "red"}},
            ],
        )
        click.echo(f"Pool created: {pool.id}  ({len(pool.arms)} arms)")

        # 2. Create an experiment --------------------------------------------
        experiment = client.experiment.create(
            name="homepage-cta-test",
            pool_id=pool.id,
            policy="EXP3Policy",
            policy_params={"gamma": 0.2},
        )
        click.echo(f"Experiment created: {experiment.id}  (policy={experiment.policy})")

        # 3. Configure a feature gate ----------------------------------------
        default_arm = pool.arms[0]
        gate = client.gate.create(
            experiment.id,
            enabled=True,
            rollout_percentage=100.0,
            default_arm_id=default_arm.id,
            rules=[
                {
                    "key": "country",
                    "operator": "in",
                    "value": ["US", "GB", "DE"],
                    "arm_id": pool.arms[0].id,
                },
            ],
        )
        click.echo(f"Gate created for experiment {experiment.id}  "
              f"(rollout={80.0}%, default_arm={default_arm.name})")

        # 4. Event-driven simulation -----------------------------------------
        #    Each tick is randomly a "select" or "feedback" event.
        #    Feedback can only fire once per selection, after a short delay.
        pending: list[tuple[int, str, str]] = []   # (tick_created, request_id, arm_name)
        rewarded: set[str] = set()                  # request_ids already rewarded

        user_seq = 0
        select_count = 0
        feedback_count = 0
        arm_counts: dict[str, int] = {}

        click.echo(f"\n{'tick':>4}  {'event':<10}  detail")
        click.echo("-" * 60)

        for tick in range(1, TOTAL_EVENTS + 1):
            eligible = [
                (t, rid, arm) for t, rid, arm in pending
                if rid not in rewarded and tick - t >= FEEDBACK_DELAY_MIN
            ]

            # decide event type: select if nothing eligible, feedback if
            # we've done enough selects, otherwise random
            if not eligible:
                do_select = True
            elif user_seq == 0:
                do_select = True
            else:
                do_select = random.random() < SELECT_PROB

            if do_select:
                resp = client.agent.select(
                    experiment.id,
                    context=Context(
                        id=f"user-{user_seq:04d}",
                        metadata={"country": "TR", "device": "ios"}
                    ),
                )
                pending.append((tick, resp.request_id, resp.arm.name))
                arm_counts[resp.arm.name] = arm_counts.get(resp.arm.name, 0) + 1
                user_seq += 1
                select_count += 1
                tag = " [default]" if resp.is_default else ""
                click.echo(f"{tick:>4}  {'SELECT':<10}  → {resp.arm.name}{tag}")
            else:
                # pick a random eligible selection to reward
                _, request_id, arm_name = random.choice(eligible)
                prob = ARM_PROBS.get(arm_name, 0.15)
                reward = 1.0 if random.random() < prob else 0.0
                try:
                    client.agent.feedback(request_id, reward=reward)
                    rewarded.add(request_id)
                    feedback_count += 1
                    click.echo(f"{tick:>4}  {'FEEDBACK':<10}  ← {arm_name}  reward={reward}")
                except QbrixAPIError as exc:
                    click.echo(f"{tick:>4}  {'FEEDBACK':<10}  ✗ {arm_name}  error: {exc}")

        # 5. Summary ---------------------------------------------------------
        click.echo("\n--- Summary ---")
        click.echo(f"Total events:  {TOTAL_EVENTS}")
        click.echo(f"Selections:    {select_count}")
        click.echo(f"Feedbacks:     {feedback_count}")
        click.echo(f"Pending (no feedback): {select_count - feedback_count}")
        click.echo("Arm distribution:")
        for name, count in sorted(arm_counts.items()):
            click.echo(f"  {name}: {count} ({count / select_count:.0%})")


if __name__ == "__main__":
    main()
