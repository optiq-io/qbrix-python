from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from qbrix.model.gate import GateCreate
from qbrix.model.pool import Pool


class Experiment(BaseModel):
    id: str
    name: str
    pool_id: str
    policy: str
    policy_params: dict[str, Any]
    enabled: bool
    created_at: str | None = None
    updated_at: str | None = None
    pool: Pool | None = None
    feature_gate: dict[str, Any] | None = None


class ExperimentCreate(BaseModel):
    name: str
    pool_id: str
    policy: str
    policy_params: dict[str, Any] = {}
    enabled: bool = True
    feature_gate: GateCreate | None = None


class ExperimentUpdate(BaseModel):
    enabled: bool | None = None
    policy_params: dict[str, Any] | None = None
