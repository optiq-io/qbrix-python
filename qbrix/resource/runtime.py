from __future__ import annotations

from qbrix.resource._base import AsyncAPIResource
from qbrix.resource._base import SyncAPIResource
from qbrix.model.runtime import ServiceHealth
from qbrix.model.runtime import StreamSize


class RuntimeResource(SyncAPIResource):
    """synchronous runtime health check operations."""

    def redis_health(self) -> ServiceHealth:
        return self._get("/api/v1/runtime/redis/health", cast_to=ServiceHealth)

    def motor_health(self) -> ServiceHealth:
        return self._get("/api/v1/runtime/motor/health", cast_to=ServiceHealth)

    def cortex_health(self) -> ServiceHealth:
        return self._get("/api/v1/runtime/cortex/health", cast_to=ServiceHealth)

    def stream_size(self) -> StreamSize:
        return self._get("/api/v1/runtime/redis/stream/size", cast_to=StreamSize)


class AsyncRuntimeResource(AsyncAPIResource):
    """asynchronous runtime health check operations."""

    async def redis_health(self) -> ServiceHealth:
        return await self._get("/api/v1/runtime/redis/health", cast_to=ServiceHealth)

    async def motor_health(self) -> ServiceHealth:
        return await self._get("/api/v1/runtime/motor/health", cast_to=ServiceHealth)

    async def cortex_health(self) -> ServiceHealth:
        return await self._get("/api/v1/runtime/cortex/health", cast_to=ServiceHealth)

    async def stream_size(self) -> StreamSize:
        return await self._get("/api/v1/runtime/redis/stream/size", cast_to=StreamSize)
