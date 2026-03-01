from __future__ import annotations

import pytest

from qbrix._client import AsyncQbrix
from qbrix._client import Qbrix
from qbrix.resource.agent import AgentResource
from qbrix.resource.agent import AsyncAgentResource
from qbrix.resource.experiment import AsyncExperimentResource
from qbrix.resource.experiment import ExperimentResource
from qbrix.resource.gate import AsyncGateResource
from qbrix.resource.gate import GateResource
from qbrix.resource.pool import AsyncPoolResource
from qbrix.resource.pool import PoolResource


@pytest.mark.unit
class TestQbrix:
    def test_resource_types(self) -> None:
        client = Qbrix(api_key="optiq_test")
        assert isinstance(client.pool, PoolResource)
        assert isinstance(client.experiment, ExperimentResource)
        assert isinstance(client.gate, GateResource)
        assert isinstance(client.agent, AgentResource)
        client.close()

    def test_cached_property_returns_same_instance(self) -> None:
        client = Qbrix(api_key="optiq_test")
        assert client.pool is client.pool
        assert client.agent is client.agent
        client.close()

    def test_config_passthrough(self) -> None:
        client = Qbrix(
            api_key="optiq_xxx",
            base_url="https://api.qbrix.io",
            timeout=5.0,
            max_retries=1,
        )
        assert client._config.api_key == "optiq_xxx"
        assert client._config.base_url == "https://api.qbrix.io"
        assert client._config.timeout == 5.0
        assert client._config.max_retries == 1
        client.close()

    def test_env_var_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("QBRIX_API_KEY", "optiq_env")
        client = Qbrix()
        assert client._config.api_key == "optiq_env"
        client.close()

    def test_context_manager(self) -> None:
        with Qbrix(api_key="optiq_test") as client:
            assert isinstance(client, Qbrix)

    def test_close_idempotent(self) -> None:
        client = Qbrix(api_key="optiq_test")
        client.close()
        client.close()


@pytest.mark.unit
class TestAsyncQbrix:
    def test_resource_types(self) -> None:
        client = AsyncQbrix(api_key="optiq_test")
        assert isinstance(client.pool, AsyncPoolResource)
        assert isinstance(client.experiment, AsyncExperimentResource)
        assert isinstance(client.gate, AsyncGateResource)
        assert isinstance(client.agent, AsyncAgentResource)

    def test_config_passthrough(self) -> None:
        client = AsyncQbrix(
            api_key="optiq_xxx",
            base_url="https://api.qbrix.io",
        )
        assert client._config.api_key == "optiq_xxx"
        assert client._config.base_url == "https://api.qbrix.io"

    @pytest.mark.asyncio
    async def test_async_context_manager(self) -> None:
        async with AsyncQbrix(api_key="optiq_test") as client:
            assert isinstance(client, AsyncQbrix)
