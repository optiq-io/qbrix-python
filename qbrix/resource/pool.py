from __future__ import annotations

from typing import Any

from qbrix.resource._base import AsyncAPIResource
from qbrix.resource._base import SyncAPIResource
from qbrix.model.common import PaginatedResponse
from qbrix.model.experiment import Experiment
from qbrix.model.pool import ArmCreate
from qbrix.model.pool import Pool


class PoolResource(SyncAPIResource):
    """synchronous pool operations."""

    def create(
        self,
        name: str,
        arms: list[dict[str, Any] | ArmCreate],
    ) -> Pool:
        serialized_arms = [
            a.model_dump() if isinstance(a, ArmCreate) else a for a in arms
        ]
        return self._post(
            "/api/v1/pools",
            body={"name": name, "arms": serialized_arms},
            cast_to=Pool,
        )

    def get(self, pool_id: str) -> Pool:
        return self._get(f"/api/v1/pools/{pool_id}", cast_to=Pool)

    def list(
        self, *, limit: int = 100, offset: int = 0
    ) -> PaginatedResponse[Pool]:
        data = self._client.get(
            "/api/v1/pools", params={"limit": limit, "offset": offset}
        )
        return PaginatedResponse[Pool](
            items=[Pool.model_validate(p) for p in data.get("pools", [])],
            limit=data.get("limit", limit),
            offset=data.get("offset", offset),
        )

    def update(self, pool_id: str, *, name: str | None = None) -> Pool:
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        return self._patch(f"/api/v1/pools/{pool_id}", body=body, cast_to=Pool)

    def delete(self, pool_id: str) -> None:
        self._delete(f"/api/v1/pools/{pool_id}")

    def list_experiments(self, pool_id: str) -> list[Experiment]:
        data = self._client.get(f"/api/v1/pools/{pool_id}/experiments")
        items = data if isinstance(data, list) else data.get("experiments", [])
        return [Experiment.model_validate(e) for e in items]


class AsyncPoolResource(AsyncAPIResource):
    """asynchronous pool operations."""

    async def create(
        self,
        name: str,
        arms: list[dict[str, Any] | ArmCreate],
    ) -> Pool:
        serialized_arms = [
            a.model_dump() if isinstance(a, ArmCreate) else a for a in arms
        ]
        return await self._post(
            "/api/v1/pools",
            body={"name": name, "arms": serialized_arms},
            cast_to=Pool,
        )

    async def get(self, pool_id: str) -> Pool:
        return await self._get(f"/api/v1/pools/{pool_id}", cast_to=Pool)

    async def list(
        self, *, limit: int = 100, offset: int = 0
    ) -> PaginatedResponse[Pool]:
        data = await self._client.get(
            "/api/v1/pools", params={"limit": limit, "offset": offset}
        )
        return PaginatedResponse[Pool](
            items=[Pool.model_validate(p) for p in data.get("pools", [])],
            limit=data.get("limit", limit),
            offset=data.get("offset", offset),
        )

    async def update(self, pool_id: str, *, name: str | None = None) -> Pool:
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        return await self._patch(
            f"/api/v1/pools/{pool_id}", body=body, cast_to=Pool
        )

    async def delete(self, pool_id: str) -> None:
        await self._delete(f"/api/v1/pools/{pool_id}")

    async def list_experiments(self, pool_id: str) -> list[Experiment]:
        data = await self._client.get(
            f"/api/v1/pools/{pool_id}/experiments"
        )
        items = data if isinstance(data, list) else data.get("experiments", [])
        return [Experiment.model_validate(e) for e in items]
