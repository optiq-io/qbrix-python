from __future__ import annotations

from typing import Any
from typing import Literal

from pydantic import BaseModel

# Mirrors the proxy's policy registry (qbrixcore.policy.POLICIES). Grouped the
# same way it is upstream so the two stay easy to diff. ``policy.list()`` is
# the runtime source of truth if this drifts.
PolicyName = Literal[
    "auto",
    # Thompson Sampling
    "BetaTSPolicy",
    "DiscountedTSPolicy",
    "GaussianTSPolicy",
    "DirichletTSPolicy",
    "LinTSPolicy",
    "LogisticTSPolicy",
    # Upper Confidence Bound
    "UCB1TunedPolicy",
    "KLUCBPolicy",
    "KLUCBPlusPolicy",
    "LinUCBPolicy",
    "GLMUCBPolicy",
    # Epsilon-Greedy
    "EpsilonPolicy",
    # MOSS
    "MOSSPolicy",
    "MOSSAnyTimePolicy",
    # Adversarial
    "EXP3Policy",
    "EXP3IXPolicy",
    "FPLPolicy",
    # Baseline
    "RandomPolicy",
    # Meta
    "MetaBanditPolicy",
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
