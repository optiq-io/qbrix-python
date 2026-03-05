from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class GateRule(BaseModel):
    key: str
    operator: str
    value: Any
    arm_id: str | None = None
    arm_name: str | None = None


class GateConfig(BaseModel):
    experiment_id: str
    rules: list[dict[str, Any]] = []
    updated_at: str | None = None
    version: int = 1


class GateCreate(BaseModel):
    enabled: bool = True
    rollout_percentage: float = 100.0
    default_arm_id: str | None = None
    schedule_start: str | None = None
    schedule_end: str | None = None
    active_hours_start: str | None = None
    active_hours_end: str | None = None
    timezone: str = "UTC"
    rules: list[GateRule] = []
