from __future__ import annotations

from collections.abc import AsyncIterator
from collections.abc import Iterator
from typing import Any

from qbrix.resource._base import AsyncAPIResource
from qbrix.resource._base import SyncAPIResource
from qbrix.model.common import PaginatedResponse
from qbrix.model.experiment import Experiment
from qbrix.model.gate import GateCreate
from qbrix.model.policy import PolicyName


class ExperimentResource(SyncAPIResource):
    """synchronous experiment operations."""

    def create(
        self,
        name: str,
        pool_id: str,
        *,
        policy: PolicyName = "auto",
        policy_params: dict[str, Any] | None = None,
        enabled: bool = True,
        feature_gate: GateCreate | dict[str, Any] | None = None,
    ) -> Experiment:
        body: dict[str, Any] = {
            "name": name,
            "pool_id": pool_id,
            "policy": policy,
            "policy_params": policy_params or {},
            "enabled": enabled,
        }
        if feature_gate is not None:
            body["feature_gate"] = (
                feature_gate.model_dump()
                if isinstance(feature_gate, GateCreate)
                else feature_gate
            )
        return self._post("/api/v1/experiments", body=body, cast_to=Experiment)

    def get(self, experiment_id: str) -> Experiment:
        return self._get(f"/api/v1/experiments/{experiment_id}", cast_to=Experiment)

    def list(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        search: str | None = None,
        enabled: bool | None = None,
    ) -> PaginatedResponse[Experiment]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if search is not None:
            params["search"] = search
        if enabled is not None:
            params["enabled"] = enabled
        data = self._client.get("/api/v1/experiments", params=params)
        return PaginatedResponse[Experiment](
            items=[Experiment.model_validate(e) for e in data.get("experiments", [])],
            limit=data.get("limit", limit),
            offset=data.get("offset", offset),
        )

    def update(
        self,
        experiment_id: str,
        *,
        enabled: bool | None = None,
        policy_params: dict[str, Any] | None = None,
    ) -> Experiment:
        body: dict[str, Any] = {}
        if enabled is not None:
            body["enabled"] = enabled
        if policy_params is not None:
            body["policy_params"] = policy_params
        return self._patch(
            f"/api/v1/experiments/{experiment_id}",
            body=body,
            cast_to=Experiment,
        )

    def reset(self, experiment_id: str) -> Experiment:
        """Reset an experiment's learned params back to its configured ``policy_params``.

        The experiment must be paused first — the proxy returns ``409``
        (:class:`~qbrix.exception.ConflictError`) if it is currently running.

        Note: HTTP-only. There is no ``ResetExperiment`` RPC in ``proxy.proto``,
        so this raises ``NotImplementedError`` on the gRPC transport.
        """
        return self._post(
            f"/api/v1/experiments/{experiment_id}/reset",
            cast_to=Experiment,
        )

    def delete(self, experiment_id: str) -> None:
        self._delete(f"/api/v1/experiments/{experiment_id}")

    def iter_all(
        self,
        *,
        search: str | None = None,
        enabled: bool | None = None,
        limit: int = 100,
    ) -> Iterator[Experiment]:
        offset = 0
        while True:
            page = self.list(limit=limit, offset=offset, search=search, enabled=enabled)
            yield from page.items
            if not page.has_more:
                break
            offset += limit


class AsyncExperimentResource(AsyncAPIResource):
    """asynchronous experiment operations."""

    async def create(
        self,
        name: str,
        pool_id: str,
        *,
        policy: PolicyName = "auto",
        policy_params: dict[str, Any] | None = None,
        enabled: bool = True,
        feature_gate: GateCreate | dict[str, Any] | None = None,
    ) -> Experiment:
        body: dict[str, Any] = {
            "name": name,
            "pool_id": pool_id,
            "policy": policy,
            "policy_params": policy_params or {},
            "enabled": enabled,
        }
        if feature_gate is not None:
            body["feature_gate"] = (
                feature_gate.model_dump()
                if isinstance(feature_gate, GateCreate)
                else feature_gate
            )
        return await self._post("/api/v1/experiments", body=body, cast_to=Experiment)

    async def get(self, experiment_id: str) -> Experiment:
        return await self._get(
            f"/api/v1/experiments/{experiment_id}", cast_to=Experiment
        )

    async def list(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        search: str | None = None,
        enabled: bool | None = None,
    ) -> PaginatedResponse[Experiment]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if search is not None:
            params["search"] = search
        if enabled is not None:
            params["enabled"] = enabled
        data = await self._client.get("/api/v1/experiments", params=params)
        return PaginatedResponse[Experiment](
            items=[Experiment.model_validate(e) for e in data.get("experiments", [])],
            limit=data.get("limit", limit),
            offset=data.get("offset", offset),
        )

    async def update(
        self,
        experiment_id: str,
        *,
        enabled: bool | None = None,
        policy_params: dict[str, Any] | None = None,
    ) -> Experiment:
        body: dict[str, Any] = {}
        if enabled is not None:
            body["enabled"] = enabled
        if policy_params is not None:
            body["policy_params"] = policy_params
        return await self._patch(
            f"/api/v1/experiments/{experiment_id}",
            body=body,
            cast_to=Experiment,
        )

    async def reset(self, experiment_id: str) -> Experiment:
        """Reset an experiment's learned params back to its configured ``policy_params``.

        The experiment must be paused first — the proxy returns ``409``
        (:class:`~qbrix.exception.ConflictError`) if it is currently running.

        Note: HTTP-only. There is no ``ResetExperiment`` RPC in ``proxy.proto``,
        so this raises ``NotImplementedError`` on the gRPC transport.
        """
        return await self._post(
            f"/api/v1/experiments/{experiment_id}/reset",
            cast_to=Experiment,
        )

    async def delete(self, experiment_id: str) -> None:
        await self._delete(f"/api/v1/experiments/{experiment_id}")

    async def aiter_all(
        self,
        *,
        search: str | None = None,
        enabled: bool | None = None,
        limit: int = 100,
    ) -> AsyncIterator[Experiment]:
        offset = 0
        while True:
            page = await self.list(
                limit=limit, offset=offset, search=search, enabled=enabled
            )
            for item in page.items:
                yield item
            if not page.has_more:
                break
            offset += limit
