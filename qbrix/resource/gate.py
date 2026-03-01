from __future__ import annotations

from typing import Any

from qbrix._resource import AsyncAPIResource
from qbrix._resource import SyncAPIResource
from qbrix.model.gate import GateConfig
from qbrix.model.gate import GateRule


def _build_gate_body(
    *,
    enabled: bool = True,
    rollout_percentage: float = 100.0,
    default_arm_id: str | None = None,
    schedule_start: str | None = None,
    schedule_end: str | None = None,
    active_hours_start: str | None = None,
    active_hours_end: str | None = None,
    timezone: str = "UTC",
    rules: list[GateRule | dict[str, Any]] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "enabled": enabled,
        "rollout_percentage": rollout_percentage,
        "timezone": timezone,
    }
    if default_arm_id is not None:
        body["default_arm_id"] = default_arm_id
    if schedule_start is not None:
        body["schedule_start"] = schedule_start
    if schedule_end is not None:
        body["schedule_end"] = schedule_end
    if active_hours_start is not None:
        body["active_hours_start"] = active_hours_start
    if active_hours_end is not None:
        body["active_hours_end"] = active_hours_end
    if rules is not None:
        body["rules"] = [
            r.model_dump() if isinstance(r, GateRule) else r for r in rules
        ]
    else:
        body["rules"] = []
    return body


class GateResource(SyncAPIResource):
    """synchronous gate operations."""

    def create(
        self,
        experiment_id: str,
        *,
        enabled: bool = True,
        rollout_percentage: float = 100.0,
        default_arm_id: str | None = None,
        schedule_start: str | None = None,
        schedule_end: str | None = None,
        active_hours_start: str | None = None,
        active_hours_end: str | None = None,
        timezone: str = "UTC",
        rules: list[GateRule | dict[str, Any]] | None = None,
    ) -> GateConfig:
        body = _build_gate_body(
            enabled=enabled,
            rollout_percentage=rollout_percentage,
            default_arm_id=default_arm_id,
            schedule_start=schedule_start,
            schedule_end=schedule_end,
            active_hours_start=active_hours_start,
            active_hours_end=active_hours_end,
            timezone=timezone,
            rules=rules,
        )
        return self._post(
            f"/api/v1/gates/{experiment_id}", body=body, cast_to=GateConfig
        )

    def get(self, experiment_id: str) -> GateConfig:
        return self._get(
            f"/api/v1/gates/{experiment_id}", cast_to=GateConfig
        )

    def update(
        self,
        experiment_id: str,
        *,
        enabled: bool = True,
        rollout_percentage: float = 100.0,
        default_arm_id: str | None = None,
        schedule_start: str | None = None,
        schedule_end: str | None = None,
        active_hours_start: str | None = None,
        active_hours_end: str | None = None,
        timezone: str = "UTC",
        rules: list[GateRule | dict[str, Any]] | None = None,
    ) -> GateConfig:
        body = _build_gate_body(
            enabled=enabled,
            rollout_percentage=rollout_percentage,
            default_arm_id=default_arm_id,
            schedule_start=schedule_start,
            schedule_end=schedule_end,
            active_hours_start=active_hours_start,
            active_hours_end=active_hours_end,
            timezone=timezone,
            rules=rules,
        )
        return self._put(
            f"/api/v1/gates/{experiment_id}", body=body, cast_to=GateConfig
        )

    def delete(self, experiment_id: str) -> None:
        self._delete(f"/api/v1/gates/{experiment_id}")


class AsyncGateResource(AsyncAPIResource):
    """asynchronous gate operations."""

    async def create(
        self,
        experiment_id: str,
        *,
        enabled: bool = True,
        rollout_percentage: float = 100.0,
        default_arm_id: str | None = None,
        schedule_start: str | None = None,
        schedule_end: str | None = None,
        active_hours_start: str | None = None,
        active_hours_end: str | None = None,
        timezone: str = "UTC",
        rules: list[GateRule | dict[str, Any]] | None = None,
    ) -> GateConfig:
        body = _build_gate_body(
            enabled=enabled,
            rollout_percentage=rollout_percentage,
            default_arm_id=default_arm_id,
            schedule_start=schedule_start,
            schedule_end=schedule_end,
            active_hours_start=active_hours_start,
            active_hours_end=active_hours_end,
            timezone=timezone,
            rules=rules,
        )
        return await self._post(
            f"/api/v1/gates/{experiment_id}", body=body, cast_to=GateConfig
        )

    async def get(self, experiment_id: str) -> GateConfig:
        return await self._get(
            f"/api/v1/gates/{experiment_id}", cast_to=GateConfig
        )

    async def update(
        self,
        experiment_id: str,
        *,
        enabled: bool = True,
        rollout_percentage: float = 100.0,
        default_arm_id: str | None = None,
        schedule_start: str | None = None,
        schedule_end: str | None = None,
        active_hours_start: str | None = None,
        active_hours_end: str | None = None,
        timezone: str = "UTC",
        rules: list[GateRule | dict[str, Any]] | None = None,
    ) -> GateConfig:
        body = _build_gate_body(
            enabled=enabled,
            rollout_percentage=rollout_percentage,
            default_arm_id=default_arm_id,
            schedule_start=schedule_start,
            schedule_end=schedule_end,
            active_hours_start=active_hours_start,
            active_hours_end=active_hours_end,
            timezone=timezone,
            rules=rules,
        )
        return await self._put(
            f"/api/v1/gates/{experiment_id}", body=body, cast_to=GateConfig
        )

    async def delete(self, experiment_id: str) -> None:
        await self._delete(f"/api/v1/gates/{experiment_id}")
