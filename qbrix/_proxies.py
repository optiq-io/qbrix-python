from __future__ import annotations

from qbrix._util import LazyProxy
from qbrix.resource.agent import AgentResource
from qbrix.resource.experiment import ExperimentResource
from qbrix.resource.gate import GateResource
from qbrix.resource.policy import PolicyResource
from qbrix.resource.pool import PoolResource


def _load_client() -> "Qbrix":  # type: ignore[name-defined]  # noqa: F821
    from qbrix._mod_client import _load_client as _lc

    return _lc()


class PoolProxy(LazyProxy[PoolResource]):
    def __load__(self) -> PoolResource:
        return _load_client().pool


class ExperimentProxy(LazyProxy[ExperimentResource]):
    def __load__(self) -> ExperimentResource:
        return _load_client().experiment


class GateProxy(LazyProxy[GateResource]):
    def __load__(self) -> GateResource:
        return _load_client().gate


class AgentProxy(LazyProxy[AgentResource]):
    def __load__(self) -> AgentResource:
        return _load_client().agent


class PolicyProxy(LazyProxy[PolicyResource]):
    def __load__(self) -> PolicyResource:
        return _load_client().policy
