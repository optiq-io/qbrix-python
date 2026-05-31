from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class ResponseFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"


_BASE = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")


class ArmInput(BaseModel):
    model_config = _BASE

    name: str = Field(..., min_length=1, description="arm name e.g. 'control', 'red-button'")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="variant payload — data your app uses to render this variant e.g. {\"color\": \"#ef4444\"}",
    )


class GateRuleInput(BaseModel):
    model_config = _BASE

    key: str = Field(..., description="context attribute key e.g. 'plan', 'country'")
    operator: str = Field(..., description="'eq', 'neq', 'in', 'nin', 'gt', 'gte', 'lt', 'lte'")
    value: Any = Field(..., description="value to compare against. Use a list for 'in'/'nin'.")
    arm_id: str | None = Field(default=None, description="route matched users to this arm ID")
    arm_name: str | None = Field(default=None, description="route matched users to this arm name")


class ListPoliciesInput(BaseModel):
    model_config = _BASE

    reward_type: str | None = Field(
        default=None,
        description="filter by reward type: 'binary', 'bounded', or 'continuous'",
    )
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class ListExperimentsInput(BaseModel):
    model_config = _BASE

    search: str | None = Field(default=None, description="filter by experiment name (partial match)")
    enabled: bool | None = Field(default=None, description="true = running only, false = paused only")
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class ListPoolsInput(BaseModel):
    model_config = _BASE

    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class GetPoolInput(BaseModel):
    model_config = _BASE

    pool_id: str = Field(..., min_length=1, description="pool ID")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class SetupExperimentInput(BaseModel):
    model_config = _BASE

    name: str = Field(..., min_length=1, description="experiment name e.g. 'checkout-button-test'")
    arms: list[ArmInput] = Field(..., min_length=2, description="variants to test, minimum 2")
    policy: str = Field(
        ...,
        description=(
            "bandit policy — use qbrix_list_policies to see all options. "
            "Common: 'BetaTSPolicy' (binary), 'GaussianTSPolicy' (continuous), "
            "'LinUCBPolicy' (contextual). Use 'auto' for automatic selection."
        ),
    )
    policy_params: dict[str, Any] | None = Field(
        default=None,
        description="policy-specific parameters — see qbrix_list_policies for configurable params",
    )
    enabled: bool = Field(default=True)
    rollout_percentage: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="if set, creates a feature gate limiting traffic to this percentage",
    )


class CreateExperimentFromPoolInput(BaseModel):
    model_config = _BASE

    name: str = Field(..., min_length=1)
    pool_id: str = Field(..., min_length=1, description="existing pool ID — use qbrix_list_pools to find it")
    policy: str = Field(..., description="bandit policy name — use qbrix_list_policies")
    policy_params: dict[str, Any] | None = Field(default=None)
    enabled: bool = Field(default=True)


class ConfigureGateInput(BaseModel):
    model_config = _BASE

    experiment_id: str = Field(..., min_length=1)
    rollout_percentage: float = Field(
        default=100.0,
        ge=0.0,
        le=100.0,
        description="percentage of traffic included (0–100). Users outside rollout see the default arm.",
    )
    rules: list[GateRuleInput] = Field(
        default_factory=list,
        description=(
            "targeting rules, evaluated in order — first match wins. "
            "e.g. [{\"key\": \"plan\", \"operator\": \"eq\", \"value\": \"premium\"}]"
        ),
    )
    schedule_start: str | None = Field(default=None, description="ISO 8601 datetime — inactive before this time")
    schedule_end: str | None = Field(default=None, description="ISO 8601 datetime — inactive after this time")
    active_hours_start: str | None = Field(default=None, description="HH:MM daily start e.g. '09:00'")
    active_hours_end: str | None = Field(default=None, description="HH:MM daily end e.g. '17:00'")
    default_arm_id: str | None = Field(default=None, description="arm served to users excluded by the gate")
    timezone: str = Field(default="UTC", description="timezone e.g. 'America/New_York'")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class GetExperimentInput(BaseModel):
    model_config = _BASE

    experiment_id: str = Field(..., min_length=1)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class GetGateInput(BaseModel):
    model_config = _BASE

    experiment_id: str = Field(..., min_length=1)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class GetStatsInput(BaseModel):
    model_config = _BASE

    experiment_id: str = Field(..., min_length=1)
    start_ms: int | None = Field(default=None, ge=0, description="start of window (epoch milliseconds)")
    end_ms: int | None = Field(default=None, ge=0, description="end of window (epoch milliseconds)")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class ExperimentIdInput(BaseModel):
    model_config = _BASE

    experiment_id: str = Field(..., min_length=1)


class TuneExperimentInput(BaseModel):
    model_config = _BASE

    experiment_id: str = Field(..., min_length=1)
    policy_params: dict[str, Any] = Field(
        ...,
        description="updated policy parameters — use qbrix_get_experiment to see current params first",
    )


class SelectInput(BaseModel):
    model_config = _BASE

    experiment_id: str = Field(..., min_length=1)
    context_id: str = Field(
        ...,
        min_length=1,
        description="stable identifier for the entity being served (user ID, session ID)",
    )
    context_vector: list[float] | None = Field(
        default=None,
        description="feature vector for contextual policies (LinUCBPolicy, LinTSPolicy). Length must match 'dim' policy param.",
    )
    context_metadata: dict[str, Any] | None = Field(
        default=None,
        description="key-value context for gate rule evaluation e.g. {\"plan\": \"premium\", \"country\": \"US\"}",
    )


class FeedbackInput(BaseModel):
    model_config = _BASE

    request_id: str = Field(
        ...,
        min_length=1,
        description="request_id from qbrix_select — pass unchanged (HMAC-signed token)",
    )
    reward: float = Field(
        ...,
        description=(
            "observed outcome. Binary: 1.0 or 0.0. "
            "Continuous: actual metric value. Bounded: 0.0–1.0."
        ),
    )


class CreatePoolInput(BaseModel):
    model_config = _BASE

    name: str = Field(..., min_length=1, description="pool name e.g. 'homepage-hero-variants'")
    arms: list[ArmInput] = Field(..., min_length=2)
