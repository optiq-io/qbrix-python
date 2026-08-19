"""Transport protocol — the contract resources call to reach the qbrix proxy.

Two implementations exist: ``HTTPTransport`` (httpx, default) and ``GRPCTransport``
(grpcio). Both expose an HTTP-style verb interface (``get``/``post``/``put``/
``patch``/``delete`` + low-level ``request``). The gRPC transport maps these to
``ProxyService`` RPCs internally via a routing table — resources do not need to
know which transport is in use.

Why HTTP-shaped? Resources predate gRPC; they already call ``self._client.post``
with paths like ``/api/v1/pools``. Keeping that surface on the Transport means
no resource refactor is needed when we add a second wire format.
"""

from __future__ import annotations

from typing import Any
from typing import Protocol
from typing import TypeVar
from typing import runtime_checkable

from pydantic import BaseModel

_T = TypeVar("_T", bound=BaseModel)


@runtime_checkable
class Transport(Protocol):
    """Synchronous transport for the qbrix SDK.

    ``timeout``/``max_retries`` on every verb override the client-level
    ``QbrixConfig`` defaults for that one call — hot-path callers (e.g.
    ``agent.select``) can ask for a tight budget without touching every
    other request the client makes.
    """

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> _T | dict[str, Any]: ...

    def get(
        self,
        path: str,
        *,
        cast_to: type[_T] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> _T | dict[str, Any]: ...

    def post(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> _T | dict[str, Any]: ...

    def put(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> _T | dict[str, Any]: ...

    def patch(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> _T | dict[str, Any]: ...

    def delete(
        self,
        path: str,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> None: ...

    def close(self) -> None: ...


@runtime_checkable
class AsyncTransport(Protocol):
    """Asynchronous transport for the qbrix SDK."""

    async def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> _T | dict[str, Any]: ...

    async def get(
        self,
        path: str,
        *,
        cast_to: type[_T] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> _T | dict[str, Any]: ...

    async def post(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> _T | dict[str, Any]: ...

    async def put(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> _T | dict[str, Any]: ...

    async def patch(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> _T | dict[str, Any]: ...

    async def delete(
        self,
        path: str,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> None: ...

    async def close(self) -> None: ...
