"""A nightly job: send what happened to each unit, for events that never passed
through a device holding decisions.

qbrix credits each event to the unit's most recent open decision in every loop
that improves the metric, about a minute after it arrives. track_many sends up
to 500 events per request and answers each one, in order. A stable id per event
lets the job run again without counting anything twice.

Run:
    export QBRIX_API_KEY=optiq_...
    export QBRIX_BASE_URL=http://localhost:8080
    uv run python examples/backend_job.py
"""

from datetime import datetime

from qbrix import Qbrix
from qbrix import TrackEvent

RENEWALS = [
    {"customer": "customer-1", "amount": 49, "renewed_at": "2026-11-21T09:12:00Z"},
    {"customer": "customer-2", "amount": 99, "renewed_at": "2026-11-21T14:40:00Z"},
]


def main() -> None:
    events = [
        TrackEvent(
            metric="revenue",
            value=renewal["amount"],
            unit=renewal["customer"],
            at=datetime.fromisoformat(renewal["renewed_at"]),
            id=f"renewal-{renewal['customer']}-{renewal['renewed_at']}",
        )
        for renewal in RENEWALS
    ]
    with Qbrix() as client:
        results = client.track_many(events)

    for event, result in zip(events, results):
        if result is None or result.error is None:
            print(f"{event.unit}: recorded")
        else:
            print(f"{event.unit}: {result.error}")


if __name__ == "__main__":
    main()
