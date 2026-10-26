"""Quickstart: ask a loop for a decision, render it, report what happened.

Needs a qbrix server with next switched on and a loop to ask, e.g. one an
agent created over MCP with options whose config carries a "headline".

Run:
    export QBRIX_API_KEY=optiq_...
    export QBRIX_BASE_URL=http://localhost:8000
    uv run python examples/quickstart.py checkout-headline
"""

import random
import sys

from qbrix import Qbrix

OFFLINE = {"key": "control", "config": {"headline": "Checkout"}}


def main(loop: str) -> None:
    with Qbrix() as client:
        for n in range(20):
            decision = client.select(
                loop,
                context={"unit": f"user-{n}", "properties": {"device": "mobile"}},
                settings={"offline": OFFLINE},
            )
            headline = decision.option.config.get("headline")
            print(
                f"user-{n}: {decision.reason:<8} {decision.option.key:<12} {headline}"
            )

            converted = random.random() < 0.3
            client.outcome(decision.request_id, 1 if converted else 0)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "checkout-headline")
