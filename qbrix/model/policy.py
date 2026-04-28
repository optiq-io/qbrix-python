from __future__ import annotations

from typing import Any
from typing import Literal

from pydantic import BaseModel

PolicyName = Literal[
    "auto",
    "BetaTSPolicy",
    "GaussianTSPolicy",
    "UCB1TunedPolicy",
    "KLUCBPolicy",
    "EpsilonPolicy",
    "MOSSPolicy",
    "MOSSAnyTimePolicy",
    "LinUCBPolicy",
    "LinTSPolicy",
    "EXP3Policy",
    "FPLPolicy",
]


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
