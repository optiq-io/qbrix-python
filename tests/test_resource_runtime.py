from __future__ import annotations

import pytest

from qbrix.model.runtime import ServiceHealth
from qbrix.model.runtime import StreamSize
from qbrix.resource.runtime import AsyncRuntimeResource
from qbrix.resource.runtime import RuntimeResource
from tests.conftest import MockAsyncClient
from tests.conftest import MockSyncClient

REDIS_HEALTH = {"service": "redis", "status": "ok"}
MOTOR_HEALTH = {"service": "motor", "status": "ok"}
CORTEX_HEALTH = {"service": "cortex", "status": "ok"}
STREAM_SIZE = {"len": 42}


@pytest.mark.unit
class TestRuntimeResource:
    def test_redis_health(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(REDIS_HEALTH)
        resource = RuntimeResource(mock_client)
        health = resource.redis_health()

        assert isinstance(health, ServiceHealth)
        assert health.service == "redis"
        assert health.status == "ok"
        call = mock_client.calls[0]
        assert call["path"] == "/api/v1/runtime/redis/health"

    def test_motor_health(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(MOTOR_HEALTH)
        resource = RuntimeResource(mock_client)
        health = resource.motor_health()
        assert health.service == "motor"
        assert mock_client.calls[0]["path"] == "/api/v1/runtime/motor/health"

    def test_cortex_health(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(CORTEX_HEALTH)
        resource = RuntimeResource(mock_client)
        health = resource.cortex_health()
        assert health.service == "cortex"

    def test_stream_size(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(STREAM_SIZE)
        resource = RuntimeResource(mock_client)
        size = resource.stream_size()

        assert isinstance(size, StreamSize)
        assert size.len == 42
        assert mock_client.calls[0]["path"] == "/api/v1/runtime/redis/stream/size"


@pytest.mark.unit
@pytest.mark.asyncio
class TestAsyncRuntimeResource:
    async def test_redis_health(self, async_mock_client: MockAsyncClient) -> None:
        async_mock_client.enqueue(REDIS_HEALTH)
        resource = AsyncRuntimeResource(async_mock_client)
        health = await resource.redis_health()
        assert isinstance(health, ServiceHealth)
        assert health.service == "redis"

    async def test_stream_size(self, async_mock_client: MockAsyncClient) -> None:
        async_mock_client.enqueue(STREAM_SIZE)
        resource = AsyncRuntimeResource(async_mock_client)
        size = await resource.stream_size()
        assert size.len == 42
