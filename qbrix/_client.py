from __future__ import annotations

import os
from functools import cached_property
from typing import Any
from typing import Literal
from typing import TYPE_CHECKING

from qbrix._config import QbrixConfig
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

if TYPE_CHECKING:
    from qbrix._transport._base import AsyncTransport
    from qbrix._transport._base import Transport

TransportName = Literal["http", "grpc"]

_GRPC_SCHEMES = ("grpc://", "grpcs://")


def _detect_transport_from_url(base_url: str | None) -> TransportName | None:
    if not base_url:
        return None
    lower = base_url.lower()
    if any(lower.startswith(s) for s in _GRPC_SCHEMES):
        return "grpc"
    if lower.startswith(("http://", "https://")):
        return "http"
    return None


def _resolve_transport(
    explicit: TransportName | None,
    base_url: str | None,
) -> TransportName:
    """Resolution order: kwarg > QBRIX_TRANSPORT env > URL scheme > 'http'."""
    if explicit is not None:
        return explicit
    env = os.environ.get("QBRIX_TRANSPORT")
    if env:
        env_lower = env.strip().lower()
        if env_lower in ("http", "grpc"):
            return env_lower  # type: ignore[return-value]
        raise ValueError(
            f"QBRIX_TRANSPORT={env!r} is invalid; expected 'http' or 'grpc'"
        )
    detected = _detect_transport_from_url(base_url)
    if detected:
        return detected
    return "http"


def _build_sync_transport(name: TransportName, **kwargs: Any) -> Transport:
    if name == "http":
        try:
            from qbrix._transport._http import HTTPTransport
        except ImportError as exc:
            raise ImportError(
                "HTTP transport requires httpx. Install with: pip install qbrix[http]"
            ) from exc
        return HTTPTransport(**kwargs)
    if name == "grpc":
        try:
            from qbrix._transport._grpc import GRPCTransport
        except ImportError as exc:
            raise ImportError(
                "gRPC transport requires grpcio. Install with: pip install qbrix[grpc]"
            ) from exc
        return GRPCTransport(**kwargs)
    raise ValueError(f"unknown transport: {name!r}")


def _build_async_transport(name: TransportName, **kwargs: Any) -> AsyncTransport:
    if name == "http":
        try:
            from qbrix._transport._http import AsyncHTTPTransport
        except ImportError as exc:
            raise ImportError(
                "HTTP transport requires httpx. Install with: pip install qbrix[http]"
            ) from exc
        return AsyncHTTPTransport(**kwargs)
    if name == "grpc":
        try:
            from qbrix._transport._grpc import AsyncGRPCTransport
        except ImportError as exc:
            raise ImportError(
                "gRPC transport requires grpcio. Install with: pip install qbrix[grpc]"
            ) from exc
        return AsyncGRPCTransport(**kwargs)
    raise ValueError(f"unknown transport: {name!r}")


class Qbrix:
    """Synchronous qbrix SDK client.

    Usage::

        with Qbrix(api_key="optiq_xxx") as client:
            result = client.agent.select("exp-id", context={"id": "user-1"})
            client.agent.feedback(result.request_id, reward=1.0)

    Transport selection (HTTP default; gRPC support landing in Phase 4):

    - ``Qbrix(transport="http")`` or ``Qbrix(transport="grpc")``
    - ``QBRIX_TRANSPORT`` env var
    - URL scheme: ``grpc://`` / ``grpcs://`` → gRPC, otherwise HTTP
    """

    _transport: Transport

    def __init__(
        self,
        *,
        transport: TransportName | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        **kwargs: Any,
    ) -> None:
        chosen = _resolve_transport(transport, base_url)
        self._transport = _build_sync_transport(
            chosen,
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            **kwargs,
        )

    @property
    def _config(self) -> QbrixConfig:
        return self._transport._config  # type: ignore[attr-defined]

    # Transport delegation — resources call these via ``SyncAPIResource._get`` etc.
    def request(self, *args: Any, **kwargs: Any) -> Any:
        return self._transport.request(*args, **kwargs)

    def get(self, *args: Any, **kwargs: Any) -> Any:
        return self._transport.get(*args, **kwargs)

    def post(self, *args: Any, **kwargs: Any) -> Any:
        return self._transport.post(*args, **kwargs)

    def put(self, *args: Any, **kwargs: Any) -> Any:
        return self._transport.put(*args, **kwargs)

    def patch(self, *args: Any, **kwargs: Any) -> Any:
        return self._transport.patch(*args, **kwargs)

    def delete(self, path: str) -> None:
        self._transport.delete(path)

    def close(self) -> None:
        self._transport.close()

    def __enter__(self) -> Qbrix:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

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


class AsyncQbrix:
    """Asynchronous qbrix SDK client.

    Usage::

        async with AsyncQbrix(api_key="optiq_xxx") as client:
            result = await client.agent.select("exp-id", context={"id": "user-1"})
            await client.agent.feedback(result.request_id, reward=1.0)
    """

    _transport: AsyncTransport

    def __init__(
        self,
        *,
        transport: TransportName | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        **kwargs: Any,
    ) -> None:
        chosen = _resolve_transport(transport, base_url)
        self._transport = _build_async_transport(
            chosen,
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            **kwargs,
        )

    @property
    def _config(self) -> QbrixConfig:
        return self._transport._config  # type: ignore[attr-defined]

    async def request(self, *args: Any, **kwargs: Any) -> Any:
        return await self._transport.request(*args, **kwargs)

    async def get(self, *args: Any, **kwargs: Any) -> Any:
        return await self._transport.get(*args, **kwargs)

    async def post(self, *args: Any, **kwargs: Any) -> Any:
        return await self._transport.post(*args, **kwargs)

    async def put(self, *args: Any, **kwargs: Any) -> Any:
        return await self._transport.put(*args, **kwargs)

    async def patch(self, *args: Any, **kwargs: Any) -> Any:
        return await self._transport.patch(*args, **kwargs)

    async def delete(self, path: str) -> None:
        await self._transport.delete(path)

    async def close(self) -> None:
        await self._transport.close()

    async def __aenter__(self) -> AsyncQbrix:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

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
