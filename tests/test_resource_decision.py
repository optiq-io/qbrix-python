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
from qbrix.model.decision import Decision
from qbrix.model.decision import Option
from qbrix.model.decision import Outcome
from qbrix.model.decision import Settings
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
