from __future__ import annotations

import pytest

from qbrix.model.policy import Policy
from qbrix.resource.policy import AsyncPolicyResource
from qbrix.resource.policy import PolicyResource
from tests.conftest import MockAsyncClient
from tests.conftest import MockSyncClient

POLICY_RESPONSE = {
    "policies": [
        {
            "name": "BetaTSPolicy",
            "category": "bayesian",
            "reward_types": ["binary"],
            "description": "Beta-Thompson Sampling for binary rewards.",
            "user_params": [],
        }
    ]
}


@pytest.mark.unit
class TestPolicyResource:
    def test_list_all(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(POLICY_RESPONSE)
        resource = PolicyResource(mock_client)
        policies = resource.list()

        assert len(policies) == 1
        assert isinstance(policies[0], Policy)
        assert policies[0].name == "BetaTSPolicy"

        call = mock_client.calls[0]
        assert call["method"] == "GET"
        assert call["path"] == "/api/v1/policies"
        assert call["params"] is None

    def test_list_filter_by_reward_type(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(POLICY_RESPONSE)
        resource = PolicyResource(mock_client)
        resource.list(reward_type="binary")

        call = mock_client.calls[0]
        assert call["params"]["reward_type"] == "binary"

    def test_list_empty(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue({"policies": []})
        resource = PolicyResource(mock_client)
        policies = resource.list()
        assert policies == []


@pytest.mark.unit
@pytest.mark.asyncio
class TestAsyncPolicyResource:
    async def test_list_all(self, async_mock_client: MockAsyncClient) -> None:
        async_mock_client.enqueue(POLICY_RESPONSE)
        resource = AsyncPolicyResource(async_mock_client)
        policies = await resource.list()

        assert len(policies) == 1
        assert policies[0].name == "BetaTSPolicy"

    async def test_list_filter_by_reward_type(
        self, async_mock_client: MockAsyncClient
    ) -> None:
        async_mock_client.enqueue(POLICY_RESPONSE)
        resource = AsyncPolicyResource(async_mock_client)
        await resource.list(reward_type="binary")

        call = async_mock_client.calls[0]
        assert call["params"]["reward_type"] == "binary"
