from __future__ import annotations

import pytest

from qbrix.model.pool import ArmCreate
from qbrix.model.pool import Pool
from qbrix.resource.pool import AsyncPoolResource
from qbrix.resource.pool import PoolResource
from tests.conftest import MockAsyncClient
from tests.conftest import MockSyncClient


POOL_RESPONSE = {
    "id": "p1",
    "name": "colors",
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T00:00:00",
    "arms": [
        {"id": "a1", "name": "red", "index": 0, "is_active": True, "metadata": {}},
        {"id": "a2", "name": "blue", "index": 1, "is_active": True, "metadata": {}},
    ],
}

POOL_LIST_RESPONSE = {
    "pools": [POOL_RESPONSE],
    "limit": 10,
    "offset": 0,
}


@pytest.mark.unit
class TestPoolResource:
    def test_create_with_dicts(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(POOL_RESPONSE)
        resource = PoolResource(mock_client)
        pool = resource.create("colors", arms=[{"name": "red"}, {"name": "blue"}])

        assert isinstance(pool, Pool)
        assert pool.id == "p1"
        assert len(pool.arms) == 2

        call = mock_client.calls[0]
        assert call["method"] == "POST"
        assert call["path"] == "/api/v1/pools"
        assert call["json"]["name"] == "colors"

    def test_create_with_arm_create(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(POOL_RESPONSE)
        resource = PoolResource(mock_client)
        pool = resource.create(
            "colors",
            arms=[ArmCreate(name="red"), ArmCreate(name="blue")],
        )
        assert pool.name == "colors"
        call = mock_client.calls[0]
        assert call["json"]["arms"][0] == {"name": "red", "metadata": {}}

    def test_get(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(POOL_RESPONSE)
        resource = PoolResource(mock_client)
        pool = resource.get("p1")
        assert pool.id == "p1"
        assert mock_client.calls[0]["path"] == "/api/v1/pools/p1"

    def test_list(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(POOL_LIST_RESPONSE)
        resource = PoolResource(mock_client)
        page = resource.list(limit=10, offset=0)

        assert len(page.items) == 1
        assert page.limit == 10
        assert page.has_more is False

    def test_update(self, mock_client: MockSyncClient) -> None:
        updated = {**POOL_RESPONSE, "name": "renamed"}
        mock_client.enqueue(updated)
        resource = PoolResource(mock_client)
        pool = resource.update("p1", name="renamed")

        assert pool.name == "renamed"
        call = mock_client.calls[0]
        assert call["method"] == "PATCH"
        assert call["json"] == {"name": "renamed"}

    def test_delete(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue({})
        resource = PoolResource(mock_client)
        resource.delete("p1")
        call = mock_client.calls[0]
        assert call["method"] == "DELETE"
        assert call["path"] == "/api/v1/pools/p1"

    def test_list_experiments(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue({
            "experiments": [
                {
                    "id": "e1",
                    "name": "test",
                    "pool_id": "p1",
                    "policy": "beta_ts",
                    "policy_params": {},
                    "enabled": True,
                }
            ]
        })
        resource = PoolResource(mock_client)
        exps = resource.list_experiments("p1")
        assert len(exps) == 1
        assert exps[0].id == "e1"


@pytest.mark.unit
@pytest.mark.asyncio
class TestAsyncPoolResource:
    async def test_create(self, async_mock_client: MockAsyncClient) -> None:
        async_mock_client.enqueue(POOL_RESPONSE)
        resource = AsyncPoolResource(async_mock_client)
        pool = await resource.create("colors", arms=[{"name": "red"}])
        assert pool.id == "p1"

    async def test_get(self, async_mock_client: MockAsyncClient) -> None:
        async_mock_client.enqueue(POOL_RESPONSE)
        resource = AsyncPoolResource(async_mock_client)
        pool = await resource.get("p1")
        assert pool.name == "colors"

    async def test_list(self, async_mock_client: MockAsyncClient) -> None:
        async_mock_client.enqueue(POOL_LIST_RESPONSE)
        resource = AsyncPoolResource(async_mock_client)
        page = await resource.list(limit=10)
        assert len(page.items) == 1

    async def test_delete(self, async_mock_client: MockAsyncClient) -> None:
        async_mock_client.enqueue({})
        resource = AsyncPoolResource(async_mock_client)
        await resource.delete("p1")
        assert async_mock_client.calls[0]["method"] == "DELETE"
