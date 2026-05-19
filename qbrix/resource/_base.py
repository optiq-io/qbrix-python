from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any
from typing import TypeVar

from pydantic import BaseModel

if TYPE_CHECKING:
    from qbrix._transport._base import AsyncTransport
    from qbrix._transport._base import Transport

_T = TypeVar("_T", bound=BaseModel)


class SyncAPIResource:
    _client: Transport

    def __init__(self, client: Transport) -> None:
        self._client = client

    def _get(
        self,
        path: str,
        *,
        cast_to: type[_T] | None = None,
        params: dict[str, Any] | None = None,
    ) -> _T | dict[str, Any]:
        return self._client.get(path, cast_to=cast_to, params=params)

    def _post(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
    ) -> _T | dict[str, Any]:
        return self._client.post(path, body=body, cast_to=cast_to)

    def _put(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
    ) -> _T | dict[str, Any]:
        return self._client.put(path, body=body, cast_to=cast_to)

    def _patch(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
    ) -> _T | dict[str, Any]:
        return self._client.patch(path, body=body, cast_to=cast_to)

    def _delete(self, path: str) -> None:
        self._client.delete(path)


class AsyncAPIResource:
    _client: AsyncTransport

    def __init__(self, client: AsyncTransport) -> None:
        self._client = client

    async def _get(
        self,
        path: str,
        *,
        cast_to: type[_T] | None = None,
        params: dict[str, Any] | None = None,
    ) -> _T | dict[str, Any]:
        return await self._client.get(path, cast_to=cast_to, params=params)

    async def _post(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
    ) -> _T | dict[str, Any]:
        return await self._client.post(path, body=body, cast_to=cast_to)

    async def _put(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
    ) -> _T | dict[str, Any]:
        return await self._client.put(path, body=body, cast_to=cast_to)

    async def _patch(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
    ) -> _T | dict[str, Any]:
        return await self._client.patch(path, body=body, cast_to=cast_to)

    async def _delete(self, path: str) -> None:
        await self._client.delete(path)
