from __future__ import annotations

import pytest

from qbrix.model.auth import APIKeyCreated
from qbrix.model.auth import APIKeyInfo
from qbrix.model.auth import APIKeyUsage
from qbrix.resource.auth import AsyncAuthResource
from qbrix.resource.auth import AuthResource
from tests.conftest import MockAsyncClient
from tests.conftest import MockSyncClient

API_KEY_CREATED = {
    "id": "k1",
    "name": "Default API Key",
    "key": "optiq_abc123",
    "rate_limit_per_minute": 100,
    "scopes": ["agent:read", "agent:write"],
    "created_at": 1704067200.0,
    "is_active": True,
}

API_KEY_INFO = {
    "id": "k1",
    "name": "Default API Key",
    "rate_limit_per_minute": 100,
    "scopes": ["agent:read", "agent:write"],
    "created_at": 1704067200.0,
    "last_used_at": None,
    "is_active": True,
}

API_KEY_USAGE = {
    "current_minute_usage": 5,
    "rate_limit_per_minute": 100,
}


@pytest.mark.unit
class TestAuthResource:
    def test_create_api_key_default_name(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(API_KEY_CREATED)
        resource = AuthResource(mock_client)
        key = resource.create_api_key()

        assert isinstance(key, APIKeyCreated)
        assert key.key == "optiq_abc123"
        call = mock_client.calls[0]
        assert call["method"] == "POST"
        assert call["path"] == "/api/auth/api-keys"
        assert call["json"]["name"] == "Default API Key"

    def test_create_api_key_custom_name(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(API_KEY_CREATED)
        resource = AuthResource(mock_client)
        resource.create_api_key(name="My Key")
        assert mock_client.calls[0]["json"]["name"] == "My Key"

    def test_list_api_keys(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue([API_KEY_INFO])
        resource = AuthResource(mock_client)
        keys = resource.list_api_keys()

        assert len(keys) == 1
        assert isinstance(keys[0], APIKeyInfo)
        assert keys[0].id == "k1"
        assert mock_client.calls[0]["method"] == "GET"

    def test_update_api_key(self, mock_client: MockSyncClient) -> None:
        updated = {**API_KEY_INFO, "name": "Renamed Key"}
        mock_client.enqueue(updated)
        resource = AuthResource(mock_client)
        key = resource.update_api_key("k1", name="Renamed Key")

        assert isinstance(key, APIKeyInfo)
        assert key.name == "Renamed Key"
        call = mock_client.calls[0]
        assert call["method"] == "PATCH"
        assert call["path"] == "/api/auth/api-keys/k1"
        assert call["json"]["name"] == "Renamed Key"

    def test_rotate_api_key(self, mock_client: MockSyncClient) -> None:
        rotated = {**API_KEY_CREATED, "key": "optiq_newkey"}
        mock_client.enqueue(rotated)
        resource = AuthResource(mock_client)
        key = resource.rotate_api_key("k1")

        assert isinstance(key, APIKeyCreated)
        assert key.key == "optiq_newkey"
        call = mock_client.calls[0]
        assert call["method"] == "POST"
        assert call["path"] == "/api/auth/api-keys/k1/rotate"

    def test_delete_api_key(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue({})
        resource = AuthResource(mock_client)
        resource.delete_api_key("k1")

        call = mock_client.calls[0]
        assert call["method"] == "DELETE"
        assert call["path"] == "/api/auth/api-keys/k1"

    def test_get_api_key_usage(self, mock_client: MockSyncClient) -> None:
        mock_client.enqueue(API_KEY_USAGE)
        resource = AuthResource(mock_client)
        usage = resource.get_api_key_usage("k1")

        assert isinstance(usage, APIKeyUsage)
        assert usage.current_minute_usage == 5
        assert usage.rate_limit_per_minute == 100
        call = mock_client.calls[0]
        assert call["path"] == "/api/auth/api-keys/k1/usage"


@pytest.mark.unit
@pytest.mark.asyncio
class TestAsyncAuthResource:
    async def test_create_api_key(self, async_mock_client: MockAsyncClient) -> None:
        async_mock_client.enqueue(API_KEY_CREATED)
        resource = AsyncAuthResource(async_mock_client)
        key = await resource.create_api_key()
        assert isinstance(key, APIKeyCreated)
        assert key.key == "optiq_abc123"

    async def test_list_api_keys(self, async_mock_client: MockAsyncClient) -> None:
        async_mock_client.enqueue([API_KEY_INFO])
        resource = AsyncAuthResource(async_mock_client)
        keys = await resource.list_api_keys()
        assert len(keys) == 1
        assert keys[0].id == "k1"

    async def test_rotate_api_key(self, async_mock_client: MockAsyncClient) -> None:
        rotated = {**API_KEY_CREATED, "key": "optiq_newkey"}
        async_mock_client.enqueue(rotated)
        resource = AsyncAuthResource(async_mock_client)
        key = await resource.rotate_api_key("k1")
        assert key.key == "optiq_newkey"

    async def test_delete_api_key(self, async_mock_client: MockAsyncClient) -> None:
        async_mock_client.enqueue({})
        resource = AsyncAuthResource(async_mock_client)
        await resource.delete_api_key("k1")
        assert async_mock_client.calls[0]["method"] == "DELETE"
