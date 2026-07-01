from __future__ import annotations

import pytest

from qbrix.model.agent import SelectResponse
from qbrix.model.common import Context
from qbrix.resource.agent import AgentResource
from qbrix.resource.agent import AsyncAgentResource
from tests.conftest import MockAsyncClient
from tests.conftest import MockSyncClient

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
