"""When qbrix can't be reached, select returns your offline option and never raises.

The client points at an address nothing listens on, so the outage is
deterministic. The decision has reason "offline" and no request_id, and
outcome() on it sends nothing, so the calling code needs no special case.

Run:
    uv run python examples/offline.py
"""

from qbrix import Qbrix

OFFLINE = {"key": "control", "config": {"headline": "Checkout"}}


def main() -> None:
    with Qbrix(api_key="optiq_unused", base_url="http://127.0.0.1:9") as client:
        decision = client.select(
            "checkout-headline",
            context={"unit": "user-1"},
            settings={"offline": OFFLINE, "timeout": 0.3},
        )
        print(decision.reason, decision.option, decision.request_id)
        assert decision.reason == "offline"
        assert client.outcome(decision.request_id, 1) is None

        bare = client.select("checkout-headline", context={"unit": "user-1"})
        print(bare.reason, bare.option)
        assert bare.option is None


if __name__ == "__main__":
    main()
