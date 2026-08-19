from __future__ import annotations

from typing import Any

from qbrix._util import NOT_GIVEN
from qbrix._util import NotGiven
from qbrix.resource._base import AsyncAPIResource
from qbrix.resource._base import SyncAPIResource
from qbrix.model.gate import GateConfig
from qbrix.model.gate import GateEvaluation
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


def _build_gate_patch(
    *,
    enabled: bool | NotGiven = NOT_GIVEN,
    rollout_percentage: float | NotGiven = NOT_GIVEN,
    default_arm_id: str | None | NotGiven = NOT_GIVEN,
    schedule_start: str | None | NotGiven = NOT_GIVEN,
    schedule_end: str | None | NotGiven = NOT_GIVEN,
    active_hours_start: str | None | NotGiven = NOT_GIVEN,
    active_hours_end: str | None | NotGiven = NOT_GIVEN,
    timezone: str | NotGiven = NOT_GIVEN,
    rules: list[GateRule | dict[str, Any]] | NotGiven = NOT_GIVEN,
) -> dict[str, Any]:
    """The supplied arguments only.

    An omitted argument is absent from the body and left as stored; ``None`` is
    transmitted and clears the field.
    """
    supplied = {
        "enabled": enabled,
        "rollout_percentage": rollout_percentage,
        "default_arm_id": default_arm_id,
        "schedule_start": schedule_start,
        "schedule_end": schedule_end,
        "active_hours_start": active_hours_start,
        "active_hours_end": active_hours_end,
        "timezone": timezone,
        "rules": rules,
    }
    body = {k: v for k, v in supplied.items() if not isinstance(v, NotGiven)}
    if not body:
        raise ValueError(
            "gate.update() needs at least one field to update; "
            "use gate.get() to read the config or gate.delete() to remove it"
        )
    if not isinstance(rules, NotGiven):
        body["rules"] = [
            r.model_dump() if isinstance(r, GateRule) else r for r in rules
        ]
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
        return self._get(f"/api/v1/gates/{experiment_id}", cast_to=GateConfig)

    def update(
        self,
        experiment_id: str,
        *,
        enabled: bool | NotGiven = NOT_GIVEN,
        rollout_percentage: float | NotGiven = NOT_GIVEN,
        default_arm_id: str | None | NotGiven = NOT_GIVEN,
        schedule_start: str | None | NotGiven = NOT_GIVEN,
        schedule_end: str | None | NotGiven = NOT_GIVEN,
        active_hours_start: str | None | NotGiven = NOT_GIVEN,
        active_hours_end: str | None | NotGiven = NOT_GIVEN,
        timezone: str | NotGiven = NOT_GIVEN,
        rules: list[GateRule | dict[str, Any]] | NotGiven = NOT_GIVEN,
    ) -> GateConfig:
        """Update the fields you pass, leaving the rest of the gate as stored.

        Raising a rollout is one argument::

            client.gate.update(experiment_id, rollout_percentage=50.0)

        Pass ``None`` to clear a field, and ``rules=[]`` to remove every rule.
        """
        body = _build_gate_patch(
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
        return self._patch(
            f"/api/v1/gates/{experiment_id}", body=body, cast_to=GateConfig
        )

    def evaluate(
        self,
        experiment_id: str,
        *,
        context_id: str = "",
        context_metadata: dict[str, Any] | None = None,
    ) -> GateEvaluation:
        """Dry-run the gate against a sample context.

        Read-only: nothing is persisted and no selection is recorded. Runs the
        same decision path ``agent.select()`` uses, so the preview cannot drift
        from live behaviour::

            client.gate.evaluate(experiment_id, context_id="user-1",
                                 context_metadata={"plan": "pro"})

        ``context_id`` is what the rollout percentage hashes on; a blank one is
        evaluated as-is. ``context_metadata`` holds the attributes the
        targeting rules read.

        Note: HTTP-only. There is no ``EvaluateGateConfig`` RPC in
        ``proxy.proto``, so this raises ``NotImplementedError`` on the gRPC
        transport.
        """
        return self._post(
            f"/api/v1/gates/{experiment_id}/evaluate",
            body={
                "context_id": context_id,
                "context_metadata": context_metadata or {},
            },
            cast_to=GateEvaluation,
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
        return await self._get(f"/api/v1/gates/{experiment_id}", cast_to=GateConfig)

    async def update(
        self,
        experiment_id: str,
        *,
        enabled: bool | NotGiven = NOT_GIVEN,
        rollout_percentage: float | NotGiven = NOT_GIVEN,
        default_arm_id: str | None | NotGiven = NOT_GIVEN,
        schedule_start: str | None | NotGiven = NOT_GIVEN,
        schedule_end: str | None | NotGiven = NOT_GIVEN,
        active_hours_start: str | None | NotGiven = NOT_GIVEN,
        active_hours_end: str | None | NotGiven = NOT_GIVEN,
        timezone: str | NotGiven = NOT_GIVEN,
        rules: list[GateRule | dict[str, Any]] | NotGiven = NOT_GIVEN,
    ) -> GateConfig:
        """Update the fields you pass, leaving the rest of the gate as stored.

        Raising a rollout is one argument::

            client.gate.update(experiment_id, rollout_percentage=50.0)

        Pass ``None`` to clear a field, and ``rules=[]`` to remove every rule.
        """
        body = _build_gate_patch(
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
        return await self._patch(
            f"/api/v1/gates/{experiment_id}", body=body, cast_to=GateConfig
        )

    async def evaluate(
        self,
        experiment_id: str,
        *,
        context_id: str = "",
        context_metadata: dict[str, Any] | None = None,
    ) -> GateEvaluation:
        """Dry-run the gate against a sample context.

        Read-only: nothing is persisted and no selection is recorded. Runs the
        same decision path ``agent.select()`` uses, so the preview cannot drift
        from live behaviour::

            await client.gate.evaluate(experiment_id, context_id="user-1",
                                       context_metadata={"plan": "pro"})

        ``context_id`` is what the rollout percentage hashes on; a blank one is
        evaluated as-is. ``context_metadata`` holds the attributes the
        targeting rules read.

        Note: HTTP-only. There is no ``EvaluateGateConfig`` RPC in
        ``proxy.proto``, so this raises ``NotImplementedError`` on the gRPC
        transport.
        """
        return await self._post(
            f"/api/v1/gates/{experiment_id}/evaluate",
            body={
                "context_id": context_id,
                "context_metadata": context_metadata or {},
            },
            cast_to=GateEvaluation,
        )

    async def delete(self, experiment_id: str) -> None:
        await self._delete(f"/api/v1/gates/{experiment_id}")
