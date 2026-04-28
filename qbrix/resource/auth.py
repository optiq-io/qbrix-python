from __future__ import annotations

from qbrix.resource._base import AsyncAPIResource
from qbrix.resource._base import SyncAPIResource
from qbrix.model.auth import APIKeyCreated
from qbrix.model.auth import APIKeyInfo
from qbrix.model.auth import APIKeyUsage


class AuthResource(SyncAPIResource):
    """synchronous API key management operations."""

    def create_api_key(self, name: str = "Default API Key") -> APIKeyCreated:
        return self._post(
            "/api/auth/api-keys",
            body={"name": name},
            cast_to=APIKeyCreated,
        )

    def list_api_keys(self) -> list[APIKeyInfo]:
        data = self._client.get("/api/auth/api-keys")
        items = data if isinstance(data, list) else []
        return [APIKeyInfo.model_validate(k) for k in items]

    def update_api_key(self, api_key_id: str, *, name: str) -> APIKeyInfo:
        return self._patch(
            f"/api/auth/api-keys/{api_key_id}",
            body={"name": name},
            cast_to=APIKeyInfo,
        )

    def rotate_api_key(self, api_key_id: str) -> APIKeyCreated:
        return self._post(
            f"/api/auth/api-keys/{api_key_id}/rotate",
            cast_to=APIKeyCreated,
        )

    def delete_api_key(self, api_key_id: str) -> None:
        self._delete(f"/api/auth/api-keys/{api_key_id}")

    def get_api_key_usage(self, api_key_id: str) -> APIKeyUsage:
        return self._get(
            f"/api/auth/api-keys/{api_key_id}/usage",
            cast_to=APIKeyUsage,
        )


class AsyncAuthResource(AsyncAPIResource):
    """asynchronous API key management operations."""

    async def create_api_key(self, name: str = "Default API Key") -> APIKeyCreated:
        return await self._post(
            "/api/auth/api-keys",
            body={"name": name},
            cast_to=APIKeyCreated,
        )

    async def list_api_keys(self) -> list[APIKeyInfo]:
        data = await self._client.get("/api/auth/api-keys")
        items = data if isinstance(data, list) else []
        return [APIKeyInfo.model_validate(k) for k in items]

    async def update_api_key(self, api_key_id: str, *, name: str) -> APIKeyInfo:
        return await self._patch(
            f"/api/auth/api-keys/{api_key_id}",
            body={"name": name},
            cast_to=APIKeyInfo,
        )

    async def rotate_api_key(self, api_key_id: str) -> APIKeyCreated:
        return await self._post(
            f"/api/auth/api-keys/{api_key_id}/rotate",
            cast_to=APIKeyCreated,
        )

    async def delete_api_key(self, api_key_id: str) -> None:
        await self._delete(f"/api/auth/api-keys/{api_key_id}")

    async def get_api_key_usage(self, api_key_id: str) -> APIKeyUsage:
        return await self._get(
            f"/api/auth/api-keys/{api_key_id}/usage",
            cast_to=APIKeyUsage,
        )
