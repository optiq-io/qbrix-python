from __future__ import annotations

import httpx
import pytest
from pydantic import ValidationError

from qbrix.exception import NotFoundError
from qbrix.exception import QbrixTimeoutError
from qbrix.model.agent import SelectedArm
from qbrix.model.agent import SelectResponse
from qbrix.model.common import Context
from qbrix.resource.agent import AgentResource
from qbrix.resource.agent import AsyncAgentResource
from tests.conftest import MockAsyncClient
from tests.conftest import MockSyncClient

FALLBACK_ARM = {"id": "a0", "name": "control", "index": 0}

SELECT_RESPONSE = {
    "arm": {"id": "a1", "name": "blue", "index": 1},
    "request_id": "tok_abc123",
    "is_default": False,
}


@pytest.mark.unit
class TestAgentResource:
    def test_select_with_dict(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(SELECT_RESPONSE)
        resource = AgentResource(mock_client)
        result = resource.select("e1", {"id": "user-1"})

        assert isinstance(result, SelectResponse)
        assert result.arm.name == "blue"
        assert result.request_id == "tok_abc123"
        assert result.is_default is False

        call = mock_client.calls[0]
        assert call["method"] == "POST"
        assert call["path"] == "/api/v1/agent/select"
        assert call["json"]["experiment_id"] == "e1"
        assert call["json"]["context"]["id"] == "user-1"

    def test_select_with_context_model(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(SELECT_RESPONSE)
        resource = AgentResource(mock_client)
        ctx = Context(id="user-2", metadata={"plan": "pro"})
        result = resource.select("e1", ctx)

        call = mock_client.calls[0]
        assert call["json"]["context"]["id"] == "user-2"
        assert call["json"]["context"]["metadata"] == {"plan": "pro"}
        assert "vector" not in call["json"]["context"]

    def test_select_with_vector(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(SELECT_RESPONSE)
        resource = AgentResource(mock_client)
        ctx = Context(id="user-3", vector=[0.1, 0.5, 0.8])
        resource.select("e1", ctx)

        call = mock_client.calls[0]
        assert call["json"]["context"]["vector"] == [0.1, 0.5, 0.8]

    def test_select_with_properties(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(SELECT_RESPONSE)
        resource = AgentResource(mock_client)
        ctx = Context(id="user-4", properties={"device": "mobile", "price": 20})
        resource.select("e1", ctx)

        call = mock_client.calls[0]
        assert call["json"]["context"]["properties"] == {
            "device": "mobile",
            "price": 20,
        }
        assert "vector" not in call["json"]["context"]

    def test_select_with_properties_dict(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(SELECT_RESPONSE)
        resource = AgentResource(mock_client)
        resource.select("e1", {"id": "user-5", "properties": {"device": "desktop"}})

        call = mock_client.calls[0]
        assert call["json"]["context"]["properties"] == {"device": "desktop"}

    def test_select_dict_hits_the_same_guard(self, mock_client: MockSyncClient) -> None:
        # a raw dict is validated through Context, so dict callers — the mcp
        # server, the examples — get the local error too rather than a 400.
        resource = AgentResource(mock_client)
        with pytest.raises(ValidationError, match="not both"):
            resource.select(
                "e1",
                {"id": "user-6", "vector": [0.1], "properties": {"device": "mobile"}},
            )
        assert mock_client.calls == []

    def test_select_default_arm(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue({**SELECT_RESPONSE, "is_default": True})
        resource = AgentResource(mock_client)
        result = resource.select("e1", {"id": "user-1"})
        assert result.is_default is True

    def test_select_paused_experiment_null_request_id(
        self, mock_client: MockSyncClient
    ) -> None:
        # A paused experiment mints no feedback token; the proxy returns
        # request_id: null. The response must still parse.
        mock_client.enqueue({**SELECT_RESPONSE, "request_id": None})
        resource = AgentResource(mock_client)
        result = resource.select("e1", {"id": "user-1"})
        assert result.request_id is None

    def test_select_missing_request_id(self, mock_client: MockSyncClient) -> None:
        payload = {k: v for k, v in SELECT_RESPONSE.items() if k != "request_id"}
        mock_client.enqueue(payload)
        resource = AgentResource(mock_client)
        result = resource.select("e1", {"id": "user-1"})
        assert result.request_id is None

    def test_select_server_response_is_never_fallback(
        self, mock_client: MockSyncClient
    ) -> None:
        mock_client.enqueue(SELECT_RESPONSE)
        resource = AgentResource(mock_client)
        result = resource.select("e1", {"id": "user-1"})
        assert result.is_fallback is False

    def test_feedback(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue({})
        resource = AgentResource(mock_client)
        resource.feedback("tok_abc123", 1.0)

        call = mock_client.calls[0]
        assert call["method"] == "POST"
        assert call["path"] == "/api/v1/agent/feedback"
        assert call["json"]["request_id"] == "tok_abc123"
        assert call["json"]["reward"] == 1.0

    def test_feedback_int_reward(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue({})
        resource = AgentResource(mock_client)
        resource.feedback("tok_abc", 1)
        assert mock_client.calls[0]["json"]["reward"] == 1

    def test_feedback_zero_reward(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue({})
        resource = AgentResource(mock_client)
        resource.feedback("tok_abc", 0.0)
        assert mock_client.calls[0]["json"]["reward"] == 0.0

    def test_feedback_null_request_id_is_noop(
        self, mock_client: MockSyncClient
    ) -> None:
        resource = AgentResource(mock_client)
        resource.feedback(None, 1.0)
        assert mock_client.calls == []

    def test_feedback_empty_request_id_is_noop(
        self, mock_client: MockSyncClient
    ) -> None:
        resource = AgentResource(mock_client)
        resource.feedback("", 1.0)
        assert mock_client.calls == []

    def test_select_passes_timeout_and_max_retries(
        self, mock_client: MockSyncClient
    ) -> None:
        mock_client.enqueue(SELECT_RESPONSE)
        resource = AgentResource(mock_client)
        resource.select("e1", {"id": "user-1"}, timeout=0.3, max_retries=0)
        assert mock_client.calls[0]["timeout"] == 0.3

    def test_select_timeout_without_fallback_raises(
        self, mock_client: MockSyncClient
    ) -> None:
        mock_client._client.request.side_effect = httpx.ReadTimeout("timed out")
        resource = AgentResource(mock_client)
        with pytest.raises(QbrixTimeoutError):
            resource.select("e1", {"id": "user-1"}, timeout=0.3)

    def test_select_timeout_with_fallback_resolves_locally(
        self, mock_client: MockSyncClient
    ) -> None:
        mock_client._client.request.side_effect = httpx.ReadTimeout("timed out")
        resource = AgentResource(mock_client)
        result = resource.select(
            "e1", {"id": "user-1"}, timeout=0.3, fallback=FALLBACK_ARM
        )
        assert result.arm == SelectedArm.model_validate(FALLBACK_ARM)
        assert result.request_id is None
        assert result.is_default is True
        assert result.is_fallback is True

    def test_select_connection_error_with_fallback_resolves_locally(
        self, mock_client: MockSyncClient
    ) -> None:
        mock_client._client.request.side_effect = httpx.ConnectError("refused")
        resource = AgentResource(mock_client)
        result = resource.select(
            "e1", {"id": "user-1"}, fallback=SelectedArm.model_validate(FALLBACK_ARM)
        )
        assert result.is_fallback is True

    def test_select_service_unavailable_with_fallback_resolves_locally(
        self, mock_client: MockSyncClient
    ) -> None:
        mock_client.enqueue({"detail": "down"}, status=503)
        resource = AgentResource(mock_client)
        result = resource.select("e1", {"id": "user-1"}, fallback=FALLBACK_ARM)
        assert result.is_fallback is True

    def test_select_not_found_with_fallback_still_raises(
        self, mock_client: MockSyncClient
    ) -> None:
        # a 404 means the caller's request was wrong (bad experiment_id) — the
        # fallback must never mask that behind a fabricated selection.
        mock_client.enqueue({"detail": "no such experiment"}, status=404)
        resource = AgentResource(mock_client)
        with pytest.raises(NotFoundError):
            resource.select("e1", {"id": "user-1"}, fallback=FALLBACK_ARM)


@pytest.mark.unit
@pytest.mark.asyncio
class TestAsyncAgentResource:
    async def test_select(self, async_mock_client: MockAsyncClient) -> None:
        async_mock_client.enqueue(SELECT_RESPONSE)
        resource = AsyncAgentResource(async_mock_client)
        result = await resource.select("e1", {"id": "user-1"})
        assert result.arm.name == "blue"

    async def test_feedback(self, async_mock_client: MockAsyncClient) -> None:
        async_mock_client.enqueue({})
        resource = AsyncAgentResource(async_mock_client)
        await resource.feedback("tok_abc", 1.0)
        assert async_mock_client.calls[0]["json"]["reward"] == 1.0

    async def test_feedback_null_request_id_is_noop(
        self, async_mock_client: MockAsyncClient
    ) -> None:
        resource = AsyncAgentResource(async_mock_client)
        await resource.feedback(None, 1.0)
        assert async_mock_client.calls == []

    async def test_select_timeout_with_fallback_resolves_locally(
        self, async_mock_client: MockAsyncClient
    ) -> None:
        async_mock_client._client.request.side_effect = httpx.ReadTimeout("timed out")
        resource = AsyncAgentResource(async_mock_client)
        result = await resource.select(
            "e1", {"id": "user-1"}, timeout=0.3, fallback=FALLBACK_ARM
        )
        assert result.is_fallback is True
        assert result.request_id is None

    async def test_select_timeout_without_fallback_raises(
        self, async_mock_client: MockAsyncClient
    ) -> None:
        async_mock_client._client.request.side_effect = httpx.ReadTimeout("timed out")
        resource = AsyncAgentResource(async_mock_client)
        with pytest.raises(QbrixTimeoutError):
            await resource.select("e1", {"id": "user-1"}, timeout=0.3)
