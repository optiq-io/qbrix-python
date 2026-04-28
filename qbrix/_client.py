from __future__ import annotations

from functools import cached_property

from qbrix._base_client import AsyncAPIClient
from qbrix._base_client import SyncAPIClient
from qbrix.resource.agent import AgentResource
from qbrix.resource.agent import AsyncAgentResource
from qbrix.resource.auth import AsyncAuthResource
from qbrix.resource.auth import AuthResource
from qbrix.resource.experiment import AsyncExperimentResource
from qbrix.resource.experiment import ExperimentResource
from qbrix.resource.gate import AsyncGateResource
from qbrix.resource.gate import GateResource
from qbrix.resource.policy import AsyncPolicyResource
from qbrix.resource.policy import PolicyResource
from qbrix.resource.pool import AsyncPoolResource
from qbrix.resource.pool import PoolResource
from qbrix.resource.runtime import AsyncRuntimeResource
from qbrix.resource.runtime import RuntimeResource


class Qbrix(SyncAPIClient):
    """synchronous qbrix SDK client.

    Usage::

        with Qbrix(api_key="optiq_xxx") as client:
            result = client.agent.select("exp-id", context={"id": "user-1"})
            client.agent.feedback(result.request_id, reward=1.0)
    """

    @cached_property
    def pool(self) -> PoolResource:
        return PoolResource(self)

    @cached_property
    def experiment(self) -> ExperimentResource:
        return ExperimentResource(self)

    @cached_property
    def gate(self) -> GateResource:
        return GateResource(self)

    @cached_property
    def agent(self) -> AgentResource:
        return AgentResource(self)

    @cached_property
    def policy(self) -> PolicyResource:
        return PolicyResource(self)

    @cached_property
    def auth(self) -> AuthResource:
        return AuthResource(self)

    @cached_property
    def runtime(self) -> RuntimeResource:
        return RuntimeResource(self)


class AsyncQbrix(AsyncAPIClient):
    """asynchronous qbrix SDK client.

    Usage::

        async with AsyncQbrix(api_key="optiq_xxx") as client:
            result = await client.agent.select("exp-id", context={"id": "user-1"})
            await client.agent.feedback(result.request_id, reward=1.0)
    """

    @cached_property
    def pool(self) -> AsyncPoolResource:
        return AsyncPoolResource(self)

    @cached_property
    def experiment(self) -> AsyncExperimentResource:
        return AsyncExperimentResource(self)

    @cached_property
    def gate(self) -> AsyncGateResource:
        return AsyncGateResource(self)

    @cached_property
    def agent(self) -> AsyncAgentResource:
        return AsyncAgentResource(self)

    @cached_property
    def policy(self) -> AsyncPolicyResource:
        return AsyncPolicyResource(self)

    @cached_property
    def auth(self) -> AsyncAuthResource:
        return AsyncAuthResource(self)

    @cached_property
    def runtime(self) -> AsyncRuntimeResource:
        return AsyncRuntimeResource(self)


Client = Qbrix
AsyncClient = AsyncQbrix
