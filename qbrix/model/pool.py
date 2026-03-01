from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class Arm(BaseModel):
    id: str
    name: str
    index: int
    is_active: bool = True
    metadata: dict[str, Any] = {}


class Pool(BaseModel):
    id: str
    name: str
    created_at: str | None = None
    updated_at: str | None = None
    arms: list[Arm] = []


class ArmCreate(BaseModel):
    name: str
    metadata: dict[str, Any] = {}


class PoolCreate(BaseModel):
    name: str
    arms: list[ArmCreate]


class PoolUpdate(BaseModel):
    name: str | None = None
