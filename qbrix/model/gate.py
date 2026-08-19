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
    """A stored gate config.

    Note: ``default_arm_name``, ``rules[].arm_name``, ``updated_at`` and
    ``version`` are only populated on the HTTP transport. ``proxy.proto``'s
    ``FeatureGateConfig``/``RuleConfig`` carry no such fields, so over gRPC the
    names and ``updated_at`` read ``None`` and ``version`` reads the default
    ``1`` regardless of the stored value. Use ``transport="http"`` when those
    matter.
    """

    experiment_id: str
    enabled: bool = True
    rollout_percentage: float = 100.0
    default_arm_id: str | None = None
    default_arm_name: str | None = None
    schedule_start: str | None = None
    schedule_end: str | None = None
    active_hours_start: str | None = None
    active_hours_end: str | None = None
    timezone: str = "UTC"
    rules: list[GateRule] = []
    updated_at: str | None = None
    version: int = 1


class GateRuleEvaluation(BaseModel):
    """One rule's outcome in a dry-run evaluation."""

    key: str
    operator: str
    value: Any
    matched: bool
    # the rule that decided the outcome, when one did
    decisive: bool = False


class GateEvaluation(BaseModel):
    """The gate's decision for a sample context, and why.

    ``eligible`` is true when the bandit would select — i.e. the gate declined
    to force an arm. It is deliberately not a synonym for "passed the rules": a
    context outside the rollout is ineligible even with every rule matching.
    """

    eligible: bool
    # disabled | blackout | rollout | rule | bandit
    reason: str
    arm_id: str | None = None
    arm_name: str | None = None
    enabled: bool
    in_schedule: bool
    in_rollout: bool
    rollout_percentage: float
    rules: list[GateRuleEvaluation] = []


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
