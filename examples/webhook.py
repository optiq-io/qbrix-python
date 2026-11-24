"""An order webhook: credit the decisions the browser carried to the order.

At checkout the browser calls qbrix.decisions("purchase") (qbrix-js) and puts
the token where the order already carries things: a cart attribute, order
metadata, a payment's metadata. At most four decisions fit in a 500-character
metadata value. The webhook sends track with that token, and the order id makes
a redelivered webhook count once.

Run:
    export QBRIX_API_KEY=optiq_...
    export QBRIX_BASE_URL=http://localhost:8080
    QBRIX_DECISIONS=... uv run python examples/webhook.py
"""

import os
import time

from qbrix import Qbrix


def on_order_paid(client: Qbrix, order: dict) -> None:
    tracked = client.track(
        "purchase",
        1,
        decisions=order["metadata"].get("qbrix_decisions"),
        id=order["id"],
    )
    if tracked is None:
        print(f"{order['id']}: no decisions to credit")
    else:
        print(f"{order['id']}: credited {tracked.credited} decision(s)")


def main() -> None:
    order = {
        "id": f"order-{int(time.time())}",
        "metadata": {"qbrix_decisions": os.environ.get("QBRIX_DECISIONS")},
    }
    with Qbrix() as client:
        on_order_paid(client, order)


if __name__ == "__main__":
    main()
