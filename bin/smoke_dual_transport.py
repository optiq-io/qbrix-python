"""Live smoke for the request path against a server with next switched on.

Creates a metric and a draft loop over raw HTTP, then runs select and outcome
through every client the SDK has: HTTP and gRPC, sync and async. Each must
answer the draft's fallback without a request_id, then, once the loop is
launched, a live decision whose outcome is accepted. Finishes with the
offline path against an address nothing listens on.

Usage:
    QBRIX_API_KEY=optiq_xxx uv run python bin/smoke_dual_transport.py
    # QBRIX_SMOKE_HTTP_URL (default http://localhost:8080)
    # QBRIX_SMOKE_GRPC_URL (default grpc://localhost:50050)
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from typing import Any

import httpx
from pydantic import ValidationError

from qbrix import AsyncQbrix
from qbrix import BadRequestError
from qbrix import Decision
from qbrix import NotFoundError
from qbrix import Qbrix

HTTP_URL = os.environ.get("QBRIX_SMOKE_HTTP_URL", "http://localhost:8080")
GRPC_URL = os.environ.get("QBRIX_SMOKE_GRPC_URL", "grpc://localhost:50050")
RUN_ID = uuid.uuid4().hex[:8]
CONFIG = {"headline": "Pay now", "size": 3, "ratio": 0.5}
OFFLINE = {"key": "offline", "config": {"headline": "Checkout"}}
TARGETS = [("http", HTTP_URL), ("grpc", GRPC_URL)]


def _api_key() -> str:
    key = os.environ.get("QBRIX_API_KEY")
    if not key:
        sys.exit("set QBRIX_API_KEY")
    return key


def _setup(api: httpx.Client) -> str:
    metric = f"smoke-purchase-{RUN_ID}"
    api.post(
        "/api/v1/metrics",
        json={"name": metric, "semantic": "a purchase", "type": "conversion"},
    ).raise_for_status()
    loop = api.post(
        "/api/v1/loops",
        json={
            "name": f"smoke headline {RUN_ID}",
            "metric": metric,
            "options": [
                {"key": "control", "name": "Control", "config": {"headline": "Buy"}},
                {"key": "bold", "name": "Bold", "config": CONFIG},
            ],
            "fallback": "control",
        },
    )
    loop.raise_for_status()
    return loop.json()["key"]


def _launch(api: httpx.Client, key: str) -> None:
    api.post(f"/api/v1/loops/{key}/launch", json={}).raise_for_status()


def _check_draft(label: str, d: Decision) -> None:
    assert d.reason == "draft", (label, d)
    assert d.request_id is None, (label, d)
    assert d.option is not None and d.option.key == "control", (label, d)
    print(f"  ok  {label}: draft → {d.option.key}, no request_id")


def _check_live(label: str, d: Decision) -> None:
    assert d.reason == "live", (label, d)
    assert d.request_id, (label, d)
    assert d.option is not None, (label, d)
    if d.option.key == "bold":
        assert d.option.config == CONFIG, (label, d.option.config)
        assert isinstance(d.option.config["size"], int), (label, d.option.config)
    print(f"  ok  {label}: live → {d.option.key} {d.option.config}")


def _sync(key: str, api_key: str, stage: str) -> None:
    for transport, url in TARGETS:
        label = f"sync {transport}"
        with Qbrix(api_key=api_key, base_url=url, transport=transport) as client:
            d = client.select(key, context={"unit": f"u-{label}"})
            if stage == "draft":
                _check_draft(label, d)
                assert client.outcome(d.request_id, 1) is None
                continue
            _check_live(label, d)
            accepted = client.outcome(d.request_id, 1)
            assert accepted is not None and accepted.id, (label, accepted)
            print(f"  ok  {label}: outcome accepted as {accepted.id}")
            try:
                client.outcome(d.request_id, 2)
                raise AssertionError(f"{label}: a conversion of 2 was accepted")
            except BadRequestError as e:
                print(f"  ok  {label}: outcome 2 refused: {e.detail}")
            try:
                client.select(f"no-such-loop-{RUN_ID}", context={"unit": "u"})
                raise AssertionError(f"{label}: unknown loop answered")
            except NotFoundError as e:
                print(f"  ok  {label}: unknown loop: {e.detail}")


async def _async(key: str, api_key: str, stage: str) -> None:
    for transport, url in TARGETS:
        label = f"async {transport}"
        async with AsyncQbrix(
            api_key=api_key, base_url=url, transport=transport
        ) as client:
            d = await client.select(
                key, context={"unit": f"u-{label}", "properties": {"device": "web"}}
            )
            if stage == "draft":
                _check_draft(label, d)
                continue
            _check_live(label, d)
            accepted = await client.outcome(d.request_id, 0)
            assert accepted is not None and accepted.id, (label, accepted)
            print(f"  ok  {label}: outcome accepted as {accepted.id}")


def _offline() -> None:
    for transport, url in [
        ("http", "http://127.0.0.1:9"),
        ("grpc", "grpc://127.0.0.1:9"),
    ]:
        with Qbrix(api_key="optiq_unused", base_url=url, transport=transport) as client:
            settings: dict[str, Any] = {"offline": OFFLINE, "timeout": 0.5}
            d = client.select("anything", context={"unit": "u"}, settings=settings)
            assert d.reason == "offline" and d.request_id is None, d
            assert d.option is not None and d.option.key == "offline", d
            bare = client.select(
                "anything", context={"unit": "u"}, settings={"timeout": 0.5}
            )
            assert bare.option is None and bare.reason == "offline", bare
            try:
                client.select("anything", context={})
                raise AssertionError("a missing unit reached the network")
            except ValidationError:
                pass
        print(f"  ok  {transport}: unreachable → offline option, or none")


def main() -> None:
    api_key = _api_key()
    with httpx.Client(base_url=HTTP_URL, headers={"X-API-Key": api_key}) as api:
        key = _setup(api)
        print(f"loop {key} (draft)")
        _sync(key, api_key, "draft")
        asyncio.run(_async(key, api_key, "draft"))
        _launch(api, key)
        print(f"loop {key} (live)")
        _sync(key, api_key, "live")
        asyncio.run(_async(key, api_key, "live"))
    print("offline")
    _offline()
    print("all good")


if __name__ == "__main__":
    main()
