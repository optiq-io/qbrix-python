from __future__ import annotations

from typing import Any

from qbrix.resource._base import AsyncAPIResource
from qbrix.resource._base import SyncAPIResource
from qbrix.model.policy import Policy


class PolicyResource(SyncAPIResource):
    """synchronous policy discovery operations."""

    def list(self, *, reward_type: str | None = None) -> list[Policy]:
        params: dict[str, Any] = {}
        if reward_type is not None:
            params["reward_type"] = reward_type
        data = self._client.get("/api/v1/policies", params=params or None)
        return [Policy.model_validate(p) for p in data.get("policies", [])]


class AsyncPolicyResource(AsyncAPIResource):
    """asynchronous policy discovery operations."""

    async def list(self, *, reward_type: str | None = None) -> list[Policy]:
        params: dict[str, Any] = {}
        if reward_type is not None:
            params["reward_type"] = reward_type
        data = await self._client.get("/api/v1/policies", params=params or None)
        return [Policy.model_validate(p) for p in data.get("policies", [])]
