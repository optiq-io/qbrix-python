from __future__ import annotations

import pytest

from qbrix.model.gate import GateConfig
from qbrix.model.gate import GateRule
from qbrix.resource.gate import AsyncGateResource
from qbrix.resource.gate import GateResource
from tests.conftest import MockAsyncClient
from tests.conftest import MockSyncClient

GATE_RESPONSE = {
    "experiment_id": "e1",
    "rules": [{"key": "plan", "operator": "==", "value": "pro", "arm_id": "a1"}],
    "updated_at": "2024-01-01T00:00:00",
    "version": 1,
}


@pytest.mark.unit
class TestGateResource:
    def test_create(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(GATE_RESPONSE)
        resource = GateResource(mock_client)
        gate = resource.create(
            "e1",
            rollout_percentage=80.0,
            default_arm_id="a1",
            rules=[{"key": "plan", "operator": "==", "value": "pro"}],
        )

        assert isinstance(gate, GateConfig)
        assert gate.version == 1

        call = mock_client.calls[0]
        assert call["method"] == "POST"
        assert call["path"] == "/api/v1/gates/e1"
        assert call["json"]["rollout_percentage"] == 80.0
        assert call["json"]["default_arm_id"] == "a1"

    def test_create_with_gate_rule_models(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(GATE_RESPONSE)
        resource = GateResource(mock_client)
        resource.create(
            "e1",
            rules=[GateRule(key="country", operator="==", value="US")],
        )

        call = mock_client.calls[0]
        assert call["json"]["rules"][0]["key"] == "country"

    def test_create_with_schedule(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(GATE_RESPONSE)
        resource = GateResource(mock_client)
        resource.create(
            "e1",
            schedule_start="2024-01-01T00:00:00",
            schedule_end="2024-06-01T00:00:00",
            active_hours_start="09:00",
            active_hours_end="17:00",
            timezone="America/New_York",
        )

        call = mock_client.calls[0]
        assert call["json"]["schedule_start"] == "2024-01-01T00:00:00"
        assert call["json"]["timezone"] == "America/New_York"

    def test_get(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(GATE_RESPONSE)
        resource = GateResource(mock_client)
        gate = resource.get("e1")
        assert gate.experiment_id == "e1"
        assert mock_client.calls[0]["method"] == "GET"

    def test_update(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue({**GATE_RESPONSE, "version": 2})
        resource = GateResource(mock_client)
        gate = resource.update("e1", rollout_percentage=50.0)

        assert gate.version == 2
        call = mock_client.calls[0]
        assert call["method"] == "PATCH"
        assert call["json"]["rollout_percentage"] == 50.0

    def test_update_sends_only_the_arguments_passed(
        self, mock_client: MockSyncClient
    ) -> None:
        """regression (OPT-355): omitted arguments used to be sent as their
        defaults, so raising a rollout re-enabled the gate, dropped the default
        arm, cleared every rule and erased the schedule."""
        mock_client.enqueue(GATE_RESPONSE)
        resource = GateResource(mock_client)
        resource.update("e1", rollout_percentage=50.0)

        assert mock_client.calls[0]["json"] == {"rollout_percentage": 50.0}

    def test_update_transmits_an_explicit_none_to_clear(
        self, mock_client: MockSyncClient
    ) -> None:
        """None is a value here, not an absence — it is how a field is cleared."""
        mock_client.enqueue(GATE_RESPONSE)
        resource = GateResource(mock_client)
        resource.update("e1", default_arm_id=None, schedule_start=None)

        assert mock_client.calls[0]["json"] == {
            "default_arm_id": None,
            "schedule_start": None,
        }

    def test_update_sends_an_empty_rule_list_when_asked(
        self, mock_client: MockSyncClient
    ) -> None:
        mock_client.enqueue(GATE_RESPONSE)
        resource = GateResource(mock_client)
        resource.update("e1", rules=[])

        assert mock_client.calls[0]["json"] == {"rules": []}

    def test_update_serialises_gate_rule_models(
        self, mock_client: MockSyncClient
    ) -> None:
        mock_client.enqueue(GATE_RESPONSE)
        resource = GateResource(mock_client)
        resource.update("e1", rules=[GateRule(key="plan", operator="eq", value="pro")])

        rules = mock_client.calls[0]["json"]["rules"]
        assert rules[0]["key"] == "plan"

    def test_update_with_no_fields_is_rejected(
        self, mock_client: MockSyncClient
    ) -> None:
        """an empty patch is meaningless, and over the grpc transport an empty
        update mask means replace — so it must never reach the wire."""
        resource = GateResource(mock_client)

        with pytest.raises(ValueError, match="at least one field"):
            resource.update("e1")

        assert mock_client.calls == []

    def test_delete(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue({})
        resource = GateResource(mock_client)
        resource.delete("e1")
        call = mock_client.calls[0]
        assert call["method"] == "DELETE"
        assert call["path"] == "/api/v1/gates/e1"

    def test_default_body_values(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(GATE_RESPONSE)
        resource = GateResource(mock_client)
        resource.create("e1")

        call = mock_client.calls[0]
        body = call["json"]
        assert body["enabled"] is True
        assert body["rollout_percentage"] == 100.0
        assert body["timezone"] == "UTC"
        assert body["rules"] == []
        assert "default_arm_id" not in body
        assert "schedule_start" not in body


@pytest.mark.unit
@pytest.mark.asyncio
class TestAsyncGateResource:
    async def test_create(self, async_mock_client: MockAsyncClient) -> None:
        async_mock_client.enqueue(GATE_RESPONSE)
        resource = AsyncGateResource(async_mock_client)
        gate = await resource.create("e1", rollout_percentage=80.0)
        assert isinstance(gate, GateConfig)
        assert async_mock_client.calls[0]["method"] == "POST"

    async def test_get(self, async_mock_client: MockAsyncClient) -> None:
        async_mock_client.enqueue(GATE_RESPONSE)
        resource = AsyncGateResource(async_mock_client)
        gate = await resource.get("e1")
        assert gate.experiment_id == "e1"
        assert async_mock_client.calls[0]["method"] == "GET"

    async def test_update(self, async_mock_client: MockAsyncClient) -> None:
        async_mock_client.enqueue({**GATE_RESPONSE, "version": 2})
        resource = AsyncGateResource(async_mock_client)
        gate = await resource.update("e1", rollout_percentage=50.0)
        assert gate.version == 2
        assert async_mock_client.calls[0]["method"] == "PATCH"

    async def test_update_sends_only_the_arguments_passed(
        self, async_mock_client: MockAsyncClient
    ) -> None:
        async_mock_client.enqueue(GATE_RESPONSE)
        resource = AsyncGateResource(async_mock_client)
        await resource.update("e1", rollout_percentage=50.0)

        assert async_mock_client.calls[0]["json"] == {"rollout_percentage": 50.0}

    async def test_update_transmits_an_explicit_none_to_clear(
        self, async_mock_client: MockAsyncClient
    ) -> None:
        async_mock_client.enqueue(GATE_RESPONSE)
        resource = AsyncGateResource(async_mock_client)
        await resource.update("e1", default_arm_id=None)

        assert async_mock_client.calls[0]["json"] == {"default_arm_id": None}

    async def test_update_with_no_fields_is_rejected(
        self, async_mock_client: MockAsyncClient
    ) -> None:
        resource = AsyncGateResource(async_mock_client)

        with pytest.raises(ValueError, match="at least one field"):
            await resource.update("e1")

        assert async_mock_client.calls == []

    async def test_delete(self, async_mock_client: MockAsyncClient) -> None:
        async_mock_client.enqueue({})
        resource = AsyncGateResource(async_mock_client)
        await resource.delete("e1")
        assert async_mock_client.calls[0]["method"] == "DELETE"
