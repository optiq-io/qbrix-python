from __future__ import annotations

import pytest

from qbrix.model.experiment import Experiment
from qbrix.model.gate import GateCreate
from qbrix.resource.experiment import AsyncExperimentResource
from qbrix.resource.experiment import ExperimentResource
from tests.conftest import MockAsyncClient
from tests.conftest import MockSyncClient


EXP_RESPONSE = {
    "id": "e1",
    "name": "cta-test",
    "pool_id": "p1",
    "policy": "beta_ts",
    "policy_params": {},
    "enabled": True,
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T00:00:00",
    "pool": None,
    "feature_gate": None,
}

EXP_LIST_RESPONSE = {
    "experiments": [EXP_RESPONSE],
    "limit": 10,
    "offset": 0,
}


@pytest.mark.unit
class TestExperimentResource:
    def test_create_minimal(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(EXP_RESPONSE)
        resource = ExperimentResource(mock_client)
        exp = resource.create("cta-test", "p1", "beta_ts")

        assert isinstance(exp, Experiment)
        assert exp.policy == "beta_ts"

        call = mock_client.calls[0]
        assert call["method"] == "POST"
        assert call["json"]["name"] == "cta-test"
        assert call["json"]["enabled"] is True

    def test_create_with_gate(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(EXP_RESPONSE)
        resource = ExperimentResource(mock_client)
        gate = GateCreate(rollout_percentage=50.0)
        resource.create("test", "p1", "ucb1", feature_gate=gate)

        call = mock_client.calls[0]
        assert call["json"]["feature_gate"]["rollout_percentage"] == 50.0

    def test_create_with_gate_dict(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(EXP_RESPONSE)
        resource = ExperimentResource(mock_client)
        resource.create(
            "test", "p1", "ucb1", feature_gate={"rollout_percentage": 75.0}
        )
        call = mock_client.calls[0]
        assert call["json"]["feature_gate"]["rollout_percentage"] == 75.0

    def test_get(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(EXP_RESPONSE)
        resource = ExperimentResource(mock_client)
        exp = resource.get("e1")
        assert exp.id == "e1"

    def test_list_with_filters(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(EXP_LIST_RESPONSE)
        resource = ExperimentResource(mock_client)
        page = resource.list(search="cta", enabled=True)

        call = mock_client.calls[0]
        assert call["params"]["search"] == "cta"
        assert call["params"]["enabled"] is True

    def test_list_without_filters(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(EXP_LIST_RESPONSE)
        resource = ExperimentResource(mock_client)
        page = resource.list()

        call = mock_client.calls[0]
        assert "search" not in call["params"]
        assert "enabled" not in call["params"]

    def test_update(self, mock_client: MockSyncClient) -> None:
        updated = {**EXP_RESPONSE, "enabled": False}
        mock_client.enqueue(updated)
        resource = ExperimentResource(mock_client)
        exp = resource.update("e1", enabled=False)

        assert exp.enabled is False
        call = mock_client.calls[0]
        assert call["method"] == "PATCH"
        assert call["json"] == {"enabled": False}

    def test_update_policy_params(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(EXP_RESPONSE)
        resource = ExperimentResource(mock_client)
        resource.update("e1", policy_params={"epsilon": 0.1})

        call = mock_client.calls[0]
        assert call["json"] == {"policy_params": {"epsilon": 0.1}}

    def test_delete(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue({})
        resource = ExperimentResource(mock_client)
        resource.delete("e1")
        call = mock_client.calls[0]
        assert call["method"] == "DELETE"


@pytest.mark.unit
@pytest.mark.asyncio
class TestAsyncExperimentResource:
    async def test_create(self, async_mock_client: MockAsyncClient) -> None:
        async_mock_client.enqueue(EXP_RESPONSE)
        resource = AsyncExperimentResource(async_mock_client)
        exp = await resource.create("test", "p1", "beta_ts")
        assert exp.id == "e1"

    async def test_list(self, async_mock_client: MockAsyncClient) -> None:
        async_mock_client.enqueue(EXP_LIST_RESPONSE)
        resource = AsyncExperimentResource(async_mock_client)
        page = await resource.list()
        assert len(page.items) == 1
