from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class PolicyParam(BaseModel):
    name: str
    type: str
    required: bool
    default: Any | None = None
    description: str
    constraints: dict[str, float] = {}


class Policy(BaseModel):
    name: str
    category: str
    reward_types: list[str]
    description: str
    user_params: list[PolicyParam] = []
