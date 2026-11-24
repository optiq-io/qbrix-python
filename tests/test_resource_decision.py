from __future__ import annotations

from datetime import datetime
from datetime import timezone
from unittest.mock import AsyncMock
from unittest.mock import patch

import httpx
import pytest
from pydantic import ValidationError

from qbrix.exception import AuthenticationError
from qbrix.exception import BadRequestError
from qbrix.exception import NotFoundError
from qbrix.exception import QbrixConnectionError
from qbrix.exception import QbrixError
from qbrix.exception import ServiceUnavailableError
from qbrix.model.decision import Decision
from qbrix.model.decision import Option
from qbrix.model.decision import Outcome
from qbrix.model.decision import Settings
from qbrix.model.decision import Tracked
from qbrix.model.decision import TrackEvent
from qbrix.resource.decision import AsyncDecisionResource
from qbrix.resource.decision import DecisionResource
from tests.conftest import MockAsyncClient
from tests.conftest import MockSyncClient

LIVE = {
    "option": {"key": "bold", "name": "Bold", "config": {"headline": "Pay now"}},
    "request_id": "tok_abc",
    "reason": "live",
}
DRAFT = {
    "option": {"key": "control", "name": "Control", "config": {}},
    "request_id": None,
    "reason": "draft",
}
OFFLINE = {"offline": {"key": "control", "config": {"headline": "Checkout"}}}
ACCEPTED = {"id": "evt-1", "at": "2026-10-26T12:00:00+00:00"}


@pytest.mark.unit
class TestSelect:
    def test_posts_loop_and_context(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(LIVE)
        decision = DecisionResource(mock_client).select(
            "checkout-headline",
            {"unit": "user-1", "properties": {"device": "mobile"}},
        )

        assert decision == Decision(
            option=Option(key="bold", name="Bold", config={"headline": "Pay now"}),
            request_id="tok_abc",
            reason="live",
        )
        call = mock_client.calls[0]
        assert call["method"] == "POST"
        assert call["path"] == "/api/v1/select"
        assert call["json"] == {
            "loop": "checkout-headline",
            "context": {"unit": "user-1", "properties": {"device": "mobile"}},
        }

    def test_omits_absent_properties(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(LIVE)
        DecisionResource(mock_client).select("l", {"unit": "user-1"})
        assert mock_client.calls[0]["json"]["context"] == {"unit": "user-1"}

    def test_draft_has_no_request_id(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(DRAFT)
        decision = DecisionResource(mock_client).select("l", {"unit": "user-1"})
        assert decision.reason == "draft"
        assert decision.request_id is None
        assert decision.option is not None and decision.option.key == "control"

    @pytest.mark.parametrize(
        "context", [{}, {"unit": ""}, {"unit": "   "}, {"unit": "u" * 257}]
    )
    def test_invalid_unit_raises_before_the_call(
        self, mock_client: MockSyncClient, context: dict
    ) -> None:
        with pytest.raises(ValidationError):
            DecisionResource(mock_client).select("l", context)
        assert mock_client.calls == []

    def test_settings_pass_timeout_and_retries(
        self, mock_client: MockSyncClient
    ) -> None:
        mock_client.enqueue(LIVE)
        DecisionResource(mock_client).select(
            "l", {"unit": "u"}, settings={"timeout": 0.3, "max_retries": 0}
        )
        assert mock_client.calls[0]["timeout"] == 0.3

    @pytest.mark.parametrize(
        "failure",
        [httpx.ConnectError("refused"), httpx.ReadTimeout("timed out")],
    )
    def test_unreachable_returns_offline_option(
        self, mock_client: MockSyncClient, failure: Exception
    ) -> None:
        mock_client._client.request.side_effect = failure
        decision = DecisionResource(mock_client).select("l", {"unit": "u"}, OFFLINE)
        assert decision == Decision(
            option=Option(key="control", config={"headline": "Checkout"}),
            request_id=None,
            reason="offline",
        )

    @pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
    def test_unhealthy_returns_offline_option(
        self, mock_client: MockSyncClient, status: int
    ) -> None:
        mock_client.enqueue({"detail": "down"}, status=status)
        decision = DecisionResource(mock_client).select(
            "l", {"unit": "u"}, Settings.model_validate(OFFLINE)
        )
        assert decision.reason == "offline"
        assert decision.option is not None and decision.option.key == "control"

    def test_unreachable_without_offline_returns_no_option(
        self, mock_client: MockSyncClient
    ) -> None:
        mock_client._client.request.side_effect = httpx.ConnectError("refused")
        decision = DecisionResource(mock_client).select("l", {"unit": "u"})
        assert decision == Decision(option=None, request_id=None, reason="offline")

    def test_unknown_loop_raises_with_the_server_message(
        self, mock_client: MockSyncClient
    ) -> None:
        detail = "no loop with the key or id 'nope'"
        mock_client.enqueue({"code": "LOOP_NOT_FOUND", "detail": detail}, status=404)
        with pytest.raises(NotFoundError) as exc:
            DecisionResource(mock_client).select("nope", {"unit": "u"}, OFFLINE)
        assert exc.value.detail == detail

    @pytest.mark.parametrize(
        "status,error", [(400, BadRequestError), (401, AuthenticationError)]
    )
    def test_caller_errors_raise_even_with_offline(
        self, mock_client: MockSyncClient, status: int, error: type[Exception]
    ) -> None:
        mock_client.enqueue({"detail": "wrong"}, status=status)
        with pytest.raises(error):
            DecisionResource(mock_client).select("l", {"unit": "u"}, OFFLINE)


@pytest.mark.unit
class TestOutcome:
    def test_posts_value_with_a_minted_id(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(ACCEPTED, status=202)
        outcome = DecisionResource(mock_client).outcome("tok_abc", 1)

        assert outcome == Outcome(
            id="evt-1", at=datetime(2026, 10, 26, 12, tzinfo=timezone.utc)
        )
        call = mock_client.calls[0]
        assert call["path"] == "/api/v1/outcome"
        assert call["json"]["request_id"] == "tok_abc"
        assert call["json"]["value"] == 1
        assert len(call["json"]["id"]) == 32
        assert "at" not in call["json"]

    def test_sends_given_id_and_at_as_iso(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(ACCEPTED, status=202)
        at = datetime(2026, 10, 26, 11, 30, tzinfo=timezone.utc)
        DecisionResource(mock_client).outcome("tok", 0.5, id="order-7", at=at)
        body = mock_client.calls[0]["json"]
        assert body["id"] == "order-7"
        assert body["at"] == "2026-10-26T11:30:00+00:00"

    def test_none_request_id_makes_no_request(
        self, mock_client: MockSyncClient
    ) -> None:
        assert DecisionResource(mock_client).outcome(None, 1) is None
        assert mock_client.calls == []

    def test_retries_send_the_same_id(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue({"detail": "down"}, status=503)
        mock_client.enqueue(ACCEPTED, status=202)
        with patch("qbrix._transport._http._client.time.sleep"):
            DecisionResource(mock_client).outcome("tok", 1, max_retries=1)
        first, second = mock_client.calls
        assert first["json"]["id"] == second["json"]["id"]

    def test_each_call_mints_its_own_id(self, mock_client: MockSyncClient) -> None:
        resource = DecisionResource(mock_client)
        mock_client.enqueue(ACCEPTED, status=202)
        mock_client.enqueue(ACCEPTED, status=202)
        resource.outcome("tok", 1)
        resource.outcome("tok", 1)
        first, second = mock_client.calls
        assert first["json"]["id"] != second["json"]["id"]

    def test_invalid_value_raises_with_the_rule(
        self, mock_client: MockSyncClient
    ) -> None:
        rule = "a conversion is 0 or 1, got 2"
        mock_client.enqueue({"code": "INVALID_OUTCOME", "detail": rule}, status=400)
        with pytest.raises(BadRequestError) as exc:
            DecisionResource(mock_client).outcome("tok", 2)
        assert exc.value.detail == rule
        assert exc.value.code == "INVALID_OUTCOME"


TRACKED = {"id": "evt-1", "at": "2026-11-24T12:00:00+00:00", "credited": 2}
TOKEN = "tok_a.tok_b"


def _batch_answer(n: int) -> dict:
    return {
        "results": [
            {"id": f"e{i}", "at": "2026-11-24T12:00:00+00:00", "credited": None}
            for i in range(n)
        ]
    }


@pytest.mark.unit
class TestTrack:
    def test_posts_one_event_with_a_minted_id(
        self, mock_client: MockSyncClient
    ) -> None:
        mock_client.enqueue(TRACKED, status=202)
        tracked = DecisionResource(mock_client).track("purchase", 1, decisions=TOKEN)

        assert tracked == Tracked(
            id="evt-1", at=datetime(2026, 11, 24, 12, tzinfo=timezone.utc), credited=2
        )
        call = mock_client.calls[0]
        assert call["path"] == "/api/v1/track"
        body = call["json"]
        assert len(body.pop("id")) == 32
        assert body == {"metric": "purchase", "value": 1, "decisions": TOKEN}

    def test_sends_unit_id_and_at(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue({**TRACKED, "credited": None}, status=202)
        at = datetime(2026, 11, 21, 9, 12, tzinfo=timezone.utc)
        tracked = DecisionResource(mock_client).track(
            "revenue", 49.5, unit="customer-1", id="renewal-1", at=at
        )
        assert tracked is not None and tracked.credited is None
        assert mock_client.calls[0]["json"] == {
            "metric": "revenue",
            "value": 49.5,
            "unit": "customer-1",
            "id": "renewal-1",
            "at": "2026-11-21T09:12:00+00:00",
        }

    @pytest.mark.parametrize("decisions", [None, ""])
    def test_nothing_to_credit_makes_no_request(
        self, mock_client: MockSyncClient, decisions: str | None
    ) -> None:
        assert (
            DecisionResource(mock_client).track("purchase", 1, decisions=decisions)
            is None
        )
        assert mock_client.calls == []

    def test_empty_token_falls_back_to_the_unit(
        self, mock_client: MockSyncClient
    ) -> None:
        mock_client.enqueue(TRACKED, status=202)
        DecisionResource(mock_client).track("purchase", 1, decisions="", unit="u")
        assert "decisions" not in mock_client.calls[0]["json"]

    def test_retries_send_the_same_id(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue({"detail": "down"}, status=503)
        mock_client.enqueue(TRACKED, status=202)
        with patch("qbrix._transport._http._client.time.sleep"):
            DecisionResource(mock_client).track("purchase", 1, unit="u", max_retries=1)
        first, second = mock_client.calls
        assert first["json"]["id"] == second["json"]["id"]

    @pytest.mark.parametrize(
        "status,code,error",
        [
            (404, "METRIC_NOT_FOUND", NotFoundError),
            (400, "INVALID_DECISIONS", BadRequestError),
            (400, "INVALID_OUTCOME", BadRequestError),
        ],
    )
    def test_refused_event_raises_with_its_code(
        self, mock_client: MockSyncClient, status: int, code: str, error: type
    ) -> None:
        mock_client.enqueue({"code": code, "detail": "no"}, status=status)
        with pytest.raises(error) as exc:
            DecisionResource(mock_client).track("purchase", 1, unit="u")
        assert exc.value.code == code

    def test_unreachable_raises(self, mock_client: MockSyncClient) -> None:
        mock_client._client.request.side_effect = httpx.ConnectError("refused")
        with pytest.raises(QbrixConnectionError):
            DecisionResource(mock_client).track("purchase", 1, unit="u")


@pytest.mark.unit
class TestTrackMany:
    def test_sends_in_chunks_of_500_and_answers_in_order(
        self, mock_client: MockSyncClient
    ) -> None:
        for n in (500, 500, 201):
            mock_client.enqueue(_batch_answer(n), status=202)
        events = [
            TrackEvent(metric="revenue", value=i, unit=f"customer-{i}")
            for i in range(1201)
        ]

        results = DecisionResource(mock_client).track_many(events)

        assert [len(c["json"]["events"]) for c in mock_client.calls] == [500, 500, 201]
        sent = [e for c in mock_client.calls for e in c["json"]["events"]]
        assert [e["unit"] for e in sent] == [f"customer-{i}" for i in range(1201)]
        assert len({e["id"] for e in sent}) == 1201
        assert len(results) == 1201
        assert all(r is not None and r.error is None for r in results)
        assert [r.id for r in results if r] == [e["id"] for e in sent]

    def test_two_thousand_events_take_four_requests(
        self, mock_client: MockSyncClient
    ) -> None:
        for _ in range(4):
            mock_client.enqueue(_batch_answer(500), status=202)
        results = DecisionResource(mock_client).track_many(
            [{"metric": "revenue", "value": 1, "unit": f"u{i}"} for i in range(2000)]
        )
        assert len(mock_client.calls) == 4
        assert len(results) == 2000

    def test_refused_event_carries_its_typed_error(
        self, mock_client: MockSyncClient
    ) -> None:
        mock_client.enqueue(
            {
                "results": [
                    {"id": "e0", "at": "2026-11-24T12:00:00+00:00", "credited": 1},
                    {
                        "error": {
                            "code": "METRIC_NOT_FOUND",
                            "detail": "no metric named 'nope'",
                        }
                    },
                ]
            },
            status=202,
        )
        ok, refused = DecisionResource(mock_client).track_many(
            [
                {"metric": "purchase", "value": 1, "decisions": TOKEN},
                {"metric": "nope", "value": 1, "unit": "u", "id": "mine"},
            ]
        )
        assert ok is not None and ok.credited == 1 and ok.error is None
        assert refused is not None and refused.id == "mine"
        assert isinstance(refused.error, NotFoundError)
        assert refused.error.code == "METRIC_NOT_FOUND"
        assert refused.error.detail == "no metric named 'nope'"

    def test_events_with_nothing_to_credit_are_not_sent(
        self, mock_client: MockSyncClient
    ) -> None:
        mock_client.enqueue(_batch_answer(1), status=202)
        results = DecisionResource(mock_client).track_many(
            [
                {"metric": "purchase", "value": 1},
                {"metric": "purchase", "value": 1, "unit": "u"},
            ]
        )
        assert results[0] is None
        assert results[1] is not None
        assert len(mock_client.calls[0]["json"]["events"]) == 1

    def test_a_failed_chunk_keeps_its_ids_and_the_next_one_still_sends(
        self, mock_client: MockSyncClient
    ) -> None:
        mock_client.enqueue({"detail": "down"}, status=503)
        mock_client.enqueue(_batch_answer(1), status=202)
        events = [
            {"metric": "revenue", "value": 1, "unit": f"u{i}"} for i in range(501)
        ]

        results = DecisionResource(mock_client).track_many(events)

        first_chunk = mock_client.calls[0]["json"]["events"]
        assert len(mock_client.calls) == 2
        assert all(isinstance(r.error, ServiceUnavailableError) for r in results[:500])
        assert [r.id for r in results[:500]] == [e["id"] for e in first_chunk]
        assert results[500] is not None and results[500].error is None

    def test_a_short_answer_fails_its_chunk(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(_batch_answer(1), status=202)
        results = DecisionResource(mock_client).track_many(
            [{"metric": "m", "value": 1, "unit": f"u{i}"} for i in range(2)]
        )
        assert all(r is not None and isinstance(r.error, QbrixError) for r in results)

    def test_no_events_make_no_request(self, mock_client: MockSyncClient) -> None:
        assert DecisionResource(mock_client).track_many([]) == []
        assert mock_client.calls == []


@pytest.mark.unit
@pytest.mark.asyncio
class TestAsyncDecision:
    async def test_select(self, async_mock_client: MockAsyncClient) -> None:
        async_mock_client.enqueue(LIVE)
        decision = await AsyncDecisionResource(async_mock_client).select(
            "l", {"unit": "u"}
        )
        assert decision.request_id == "tok_abc"
        assert async_mock_client.calls[0]["path"] == "/api/v1/select"

    async def test_unreachable_returns_offline_option(
        self, async_mock_client: MockAsyncClient
    ) -> None:
        async_mock_client._client.request.side_effect = httpx.ConnectError("refused")
        decision = await AsyncDecisionResource(async_mock_client).select(
            "l", {"unit": "u"}, OFFLINE
        )
        assert decision.reason == "offline"
        assert decision.option is not None and decision.option.key == "control"

    async def test_invalid_unit_raises_before_the_call(
        self, async_mock_client: MockAsyncClient
    ) -> None:
        with pytest.raises(ValidationError):
            await AsyncDecisionResource(async_mock_client).select("l", {})
        assert async_mock_client.calls == []

    async def test_outcome(self, async_mock_client: MockAsyncClient) -> None:
        async_mock_client.enqueue(ACCEPTED, status=202)
        outcome = await AsyncDecisionResource(async_mock_client).outcome("tok", 1)
        assert outcome is not None and outcome.id == "evt-1"
        assert async_mock_client.calls[0]["json"]["request_id"] == "tok"

    async def test_none_request_id_makes_no_request(
        self, async_mock_client: MockAsyncClient
    ) -> None:
        assert await AsyncDecisionResource(async_mock_client).outcome(None, 1) is None
        assert async_mock_client.calls == []

    async def test_retries_send_the_same_id(
        self, async_mock_client: MockAsyncClient
    ) -> None:
        async_mock_client.enqueue({"detail": "down"}, status=503)
        async_mock_client.enqueue(ACCEPTED, status=202)
        with patch(
            "qbrix._transport._http._client.asyncio.sleep", new_callable=AsyncMock
        ):
            await AsyncDecisionResource(async_mock_client).outcome(
                "tok", 1, max_retries=1
            )
        first, second = async_mock_client.calls
        assert first["json"]["id"] == second["json"]["id"]

    async def test_track(self, async_mock_client: MockAsyncClient) -> None:
        async_mock_client.enqueue(TRACKED, status=202)
        tracked = await AsyncDecisionResource(async_mock_client).track(
            "purchase", 1, decisions=TOKEN
        )
        assert tracked is not None and tracked.credited == 2
        assert async_mock_client.calls[0]["json"]["decisions"] == TOKEN

    async def test_track_with_nothing_to_credit(
        self, async_mock_client: MockAsyncClient
    ) -> None:
        assert await AsyncDecisionResource(async_mock_client).track("m", 1) is None
        assert async_mock_client.calls == []

    async def test_track_many_chunks_and_keeps_failed_ids(
        self, async_mock_client: MockAsyncClient
    ) -> None:
        async_mock_client.enqueue(_batch_answer(500), status=202)
        async_mock_client.enqueue({"detail": "down"}, status=503)
        results = await AsyncDecisionResource(async_mock_client).track_many(
            [{"metric": "m", "value": 1, "unit": f"u{i}"} for i in range(501)]
        )
        assert [len(c["json"]["events"]) for c in async_mock_client.calls] == [500, 1]
        assert all(r is not None and r.error is None for r in results[:500])
        last = results[500]
        assert last is not None and isinstance(last.error, ServiceUnavailableError)
        assert last.id == async_mock_client.calls[1]["json"]["events"][0]["id"]
