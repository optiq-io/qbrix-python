"""qbrix MCP server — AI experimentation assistant for Qbrix SaaS customers.

Provides tools for the full experimentation lifecycle: discovering and comparing
bandit policies, designing and launching experiments, configuring traffic gates,
monitoring performance, and taking lifecycle actions. Also exposes the agent
select/feedback hot path for customers embedding qbrix in their own product code.

Connect to Claude Code, Claude Desktop, Cursor, or any MCP-compatible client.
Configure via environment variables: QBRIX_API_KEY, QBRIX_BASE_URL.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from enum import Enum
from typing import Any

from mcp.server.fastmcp import Context
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from qbrix import AsyncQbrix
from qbrix.exception import QbrixAPIError
from qbrix.exception import QbrixConnectionError
from qbrix.exception import QbrixTimeoutError


# ---------------------------------------------------------------------------
# annotation presets
# ---------------------------------------------------------------------------

_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)

_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=True,
)

_WRITE_IDEMPOTENT = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)

_DESTRUCTIVE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=True,
)


# ---------------------------------------------------------------------------
# lifespan — persistent SDK client for connection pooling
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(server: FastMCP):  # noqa: ARG001
    client = AsyncQbrix()
    yield {"client": client}
    await client.close()


mcp = FastMCP("qbrix_mcp", lifespan=lifespan)


def _client(ctx: Context) -> AsyncQbrix:
    return ctx.request_context.lifespan_state["client"]


def _format_error(e: Exception) -> str:
    if isinstance(e, QbrixAPIError):
        status = e.status_code
        detail = e.detail
        if status == 401:
            return f"error: authentication failed — check QBRIX_API_KEY. detail: {detail}"
        if status == 403:
            return f"error: insufficient permissions. detail: {detail}"
        if status == 404:
            return f"error: resource not found. detail: {detail}"
        if status == 409:
            return f"error: conflict — resource may already exist. detail: {detail}"
        if status == 422:
            return f"error: invalid parameters — {detail}"
        if status == 429:
            return "error: rate limit exceeded. wait before retrying."
        return f"error: API returned {status}. detail: {detail}"
    if isinstance(e, QbrixConnectionError):
        return "error: cannot connect to qbrix API. check QBRIX_BASE_URL and that proxysvc is running."
    if isinstance(e, QbrixTimeoutError):
        return "error: request timed out. check that qbrix proxysvc is running."
    return f"error: {type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# shared config and response format
# ---------------------------------------------------------------------------

class ResponseFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"


_BASE_CONFIG = ConfigDict(
    str_strip_whitespace=True,
    validate_assignment=True,
    extra="forbid",
)


# ---------------------------------------------------------------------------
# markdown formatting helpers
# ---------------------------------------------------------------------------

def _fmt_gate(gate: Any) -> str:
    lines = [
        f"- **Rollout:** {gate.rollout_percentage}% of traffic",
        f"- **Gate enabled:** {'yes' if gate.enabled else 'no'}",
    ]
    if gate.default_arm_name:
        lines.append(f"- **Default arm** (users outside rollout): {gate.default_arm_name}")
    if gate.schedule_start or gate.schedule_end:
        lines.append(
            f"- **Schedule:** {gate.schedule_start or 'any'} → {gate.schedule_end or 'any'} ({gate.timezone})"
        )
    if gate.active_hours_start:
        lines.append(
            f"- **Active hours:** {gate.active_hours_start}–{gate.active_hours_end} ({gate.timezone})"
        )
    if gate.rules:
        lines.append(f"- **Targeting rules** ({len(gate.rules)}):")
        for r in gate.rules:
            target = f" → arm '{r.arm_name or r.arm_id}'" if (r.arm_name or r.arm_id) else ""
            lines.append(f"  - `{r.key}` {r.operator} `{r.value}`{target}")
    return "\n".join(lines)


def _fmt_experiment(exp: Any) -> str:
    status = "✓ running" if exp.enabled else "⏸ paused"
    lines = [
        f"# Experiment: {exp.name}",
        f"**ID:** `{exp.id}`  |  **Status:** {status}  |  **Policy:** {exp.policy}",
    ]
    if exp.policy_params:
        lines.append(f"**Policy params:** `{json.dumps(exp.policy_params)}`")
    if exp.meta_experiment_id:
        lines.append(f"**Meta-experiment** (auto policy, learner of `{exp.meta_experiment_id}`)")
    if exp.pool:
        lines.append(f"\n**Pool:** {exp.pool.name} (`{exp.pool_id}`)")
        lines.append("\n| # | Arm | ID | Active |")
        lines.append("|---|-----|----|--------|")
        for arm in exp.pool.arms:
            active = "✓" if arm.is_active else "✗"
            lines.append(f"| {arm.index} | {arm.name} | `{arm.id}` | {active} |")
    if exp.feature_gate:
        lines.append("\n**Feature gate:**")
        lines.append(_fmt_gate(exp.feature_gate))
    return "\n".join(lines)


def _fmt_arm_table(arms: list[Any]) -> str:
    rows = ["| # | Arm | ID | Active | Metadata |", "|---|-----|----|--------|----------|"]
    for arm in arms:
        meta = json.dumps(arm.metadata) if arm.metadata else ""
        active = "✓" if arm.is_active else "✗"
        rows.append(f"| {arm.index} | {arm.name} | `{arm.id}` | {active} | {meta} |")
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# input models
# ---------------------------------------------------------------------------

# --- shared ---

class ArmInput(BaseModel):
    model_config = _BASE_CONFIG

    name: str = Field(
        ...,
        min_length=1,
        description="arm name e.g. 'control', 'red-button', 'pricing-v2'",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "variant payload — arbitrary data your app uses to render this variant. "
            "e.g. {\"color\": \"#ef4444\", \"text\": \"Buy Now\", \"layout\": \"hero\"}"
        ),
    )


class GateRuleInput(BaseModel):
    model_config = _BASE_CONFIG

    key: str = Field(..., description="context attribute key e.g. 'plan', 'country', 'user_id'")
    operator: str = Field(
        ...,
        description="comparison operator: 'eq', 'neq', 'in', 'nin', 'gt', 'gte', 'lt', 'lte'",
    )
    value: Any = Field(
        ...,
        description="value to compare against. Use a list for 'in'/'nin' operators.",
    )
    arm_id: str | None = Field(
        default=None,
        description="route matched users to this specific arm ID (overrides bandit)",
    )
    arm_name: str | None = Field(
        default=None,
        description="route matched users to this arm name (overrides bandit)",
    )


# --- phase 1: discovery ---

class ListPoliciesInput(BaseModel):
    model_config = _BASE_CONFIG

    reward_type: str | None = Field(
        default=None,
        description="filter by reward type: 'binary' (click/no-click), 'bounded' (0–1 scores), or 'continuous' (revenue, time-on-page, etc.)",
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="'markdown' for human-readable (default), 'json' for structured data",
    )


class ListExperimentsInput(BaseModel):
    model_config = _BASE_CONFIG

    search: str | None = Field(default=None, description="filter by experiment name (partial match)")
    enabled: bool | None = Field(
        default=None,
        description="filter by state: true = running only, false = paused only, omit = all",
    )
    limit: int = Field(default=20, ge=1, le=100, description="max results to return")
    offset: int = Field(default=0, ge=0, description="pagination offset")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class ListPoolsInput(BaseModel):
    model_config = _BASE_CONFIG

    limit: int = Field(default=20, ge=1, le=100, description="max results to return")
    offset: int = Field(default=0, ge=0, description="pagination offset")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class GetPoolInput(BaseModel):
    model_config = _BASE_CONFIG

    pool_id: str = Field(..., min_length=1, description="pool ID")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


# --- phase 2: setup ---

class SetupExperimentInput(BaseModel):
    model_config = _BASE_CONFIG

    name: str = Field(..., min_length=1, description="experiment name e.g. 'checkout-button-test'")
    arms: list[ArmInput] = Field(
        ...,
        min_length=2,
        description="variants to test, minimum 2. Each arm has a name and optional metadata payload.",
    )
    policy: str = Field(
        ...,
        description=(
            "bandit policy name. Use qbrix_list_policies to see all options. "
            "Common choices: 'BetaTSPolicy' (binary rewards, e.g. clicks), "
            "'GaussianTSPolicy' (continuous rewards, e.g. revenue), "
            "'LinUCBPolicy' (contextual — adapts per user features), "
            "'UCB1TunedPolicy' (exploration-exploitation balance). "
            "Use 'auto' to let qbrix select and tune a policy automatically."
        ),
    )
    policy_params: dict[str, Any] | None = Field(
        default=None,
        description="policy-specific parameters. Use qbrix_list_policies to see configurable params per policy e.g. {\"alpha_prior\": 1.0} for BetaTSPolicy.",
    )
    enabled: bool = Field(default=True, description="start the experiment immediately")
    rollout_percentage: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="if set, creates a feature gate limiting traffic to this percentage (e.g. 20.0 to start with 20% of users)",
    )


class CreateExperimentFromPoolInput(BaseModel):
    model_config = _BASE_CONFIG

    name: str = Field(..., min_length=1, description="experiment name")
    pool_id: str = Field(
        ...,
        min_length=1,
        description="ID of an existing pool — use qbrix_list_pools or qbrix_get_pool to find it",
    )
    policy: str = Field(
        ...,
        description="bandit policy name — use qbrix_list_policies. e.g. 'BetaTSPolicy', 'GaussianTSPolicy', 'auto'",
    )
    policy_params: dict[str, Any] | None = Field(default=None)
    enabled: bool = Field(default=True)


class ConfigureGateInput(BaseModel):
    model_config = _BASE_CONFIG

    experiment_id: str = Field(..., min_length=1, description="experiment ID")
    rollout_percentage: float = Field(
        default=100.0,
        ge=0.0,
        le=100.0,
        description="percentage of traffic included in the experiment (0–100). Users outside the rollout see the default arm.",
    )
    rules: list[GateRuleInput] = Field(
        default_factory=list,
        description=(
            "targeting rules evaluated in order — first match wins. "
            "Example: [{\"key\": \"plan\", \"operator\": \"eq\", \"value\": \"premium\"}] "
            "routes premium users through the gate. "
            "Use arm_id or arm_name in a rule to commit a specific arm for matched users."
        ),
    )
    schedule_start: str | None = Field(
        default=None,
        description="ISO 8601 datetime — experiment inactive before this time e.g. '2025-09-01T00:00:00Z'",
    )
    schedule_end: str | None = Field(
        default=None,
        description="ISO 8601 datetime — experiment inactive after this time",
    )
    active_hours_start: str | None = Field(
        default=None,
        description="HH:MM — experiment active only after this time each day e.g. '09:00'",
    )
    active_hours_end: str | None = Field(
        default=None,
        description="HH:MM — experiment inactive after this time each day e.g. '17:00'",
    )
    default_arm_id: str | None = Field(
        default=None,
        description="arm ID served to users excluded by rollout, schedule, or rules",
    )
    timezone: str = Field(
        default="UTC",
        description="timezone for schedule and active hours e.g. 'America/New_York', 'Europe/London'",
    )
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


# --- phase 3: monitoring ---

class GetExperimentInput(BaseModel):
    model_config = _BASE_CONFIG

    experiment_id: str = Field(..., min_length=1, description="experiment ID")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class GetGateInput(BaseModel):
    model_config = _BASE_CONFIG

    experiment_id: str = Field(..., min_length=1, description="experiment ID")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class GetStatsInput(BaseModel):
    model_config = _BASE_CONFIG

    experiment_id: str = Field(..., min_length=1, description="experiment ID")
    start_ms: int | None = Field(
        default=None, ge=0, description="start of time window (epoch milliseconds)"
    )
    end_ms: int | None = Field(
        default=None, ge=0, description="end of time window (epoch milliseconds)"
    )
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


# --- phase 4: action ---

class ExperimentIdInput(BaseModel):
    model_config = _BASE_CONFIG

    experiment_id: str = Field(..., min_length=1, description="experiment ID")


class TuneExperimentInput(BaseModel):
    model_config = _BASE_CONFIG

    experiment_id: str = Field(..., min_length=1, description="experiment ID")
    policy_params: dict[str, Any] = Field(
        ...,
        description="updated policy parameters. Use qbrix_get_experiment to see current params before changing.",
    )


# --- hot path ---

class SelectInput(BaseModel):
    model_config = _BASE_CONFIG

    experiment_id: str = Field(..., min_length=1, description="experiment ID to select an arm from")
    context_id: str = Field(
        ...,
        min_length=1,
        description="stable identifier for the entity being served (e.g. user ID, session ID). Used for consistent assignment and deduplication.",
    )
    context_vector: list[float] | None = Field(
        default=None,
        description="feature vector for contextual policies (LinUCBPolicy, LinTSPolicy). Length must match the experiment's 'dim' policy param. Omit for non-contextual policies.",
    )
    context_metadata: dict[str, Any] | None = Field(
        default=None,
        description="key-value context for gate rule evaluation e.g. {\"plan\": \"premium\", \"country\": \"US\"}. Does not affect the bandit — only used to evaluate feature gate targeting rules.",
    )


class FeedbackInput(BaseModel):
    model_config = _BASE_CONFIG

    request_id: str = Field(
        ...,
        min_length=1,
        description="the request_id returned by qbrix_select — pass it unchanged. This is an HMAC-signed token; any modification will cause rejection.",
    )
    reward: float = Field(
        ...,
        description=(
            "observed outcome for this selection. "
            "Binary reward: 1.0 (success, e.g. clicked) or 0.0 (failure). "
            "Continuous reward: the actual metric value (e.g. 42.5 for $42.50 revenue). "
            "Bounded reward: value between 0.0 and 1.0 (e.g. 0.75 for a satisfaction score)."
        ),
    )


# --- power user ---

class CreatePoolInput(BaseModel):
    model_config = _BASE_CONFIG

    name: str = Field(..., min_length=1, description="pool name e.g. 'homepage-hero-variants'")
    arms: list[ArmInput] = Field(
        ...,
        min_length=2,
        description="arms (variants) in this pool. Pools are reusable — the same pool can be used in multiple experiments.",
    )


# ---------------------------------------------------------------------------
# resources
# ---------------------------------------------------------------------------

@mcp.resource("qbrix://policies")
async def policies_resource(ctx: Context) -> str:
    """all available bandit policies with configurable parameters.

    reference this to understand which policies are available and how to
    configure them before creating experiments.
    """
    c = _client(ctx)
    data = await c.get("/api/v1/policies")
    return json.dumps(data, indent=2)


@mcp.resource("qbrix://experiments")
async def experiments_resource(ctx: Context) -> str:
    """summary of all experiments in the workspace.

    provides a quick overview of active and inactive experiments for context.
    """
    c = _client(ctx)
    result = await c.experiment.list(limit=100)
    items = [e.model_dump(mode="json") for e in result.items]
    return json.dumps({"experiments": items, "total": len(items)}, indent=2)


# ---------------------------------------------------------------------------
# phase 1 — discovery & advisory
# ---------------------------------------------------------------------------

@mcp.tool(name="qbrix_list_policies", annotations=_READ_ONLY)
async def qbrix_list_policies(params: ListPoliciesInput, ctx: Context) -> str:
    """List all available bandit policies with their parameters and reward type compatibility.

    Use this before creating an experiment to choose the right policy for your use case.
    Optionally filter by reward type to see only compatible policies.

    Policy categories:
    - stochastic: BetaTSPolicy (binary), GaussianTSPolicy (continuous), UCB1TunedPolicy,
      KLUCBPolicy, EpsilonPolicy, MOSSPolicy — no context vector required
    - contextual: LinUCBPolicy, LinTSPolicy — require context.vector per selection,
      length must match the experiment's 'dim' policy param
    - adversarial: EXP3Policy, FPLPolicy — robust to non-stationary reward distributions
    - auto: qbrix selects and tunes a policy automatically (MetaBandit)

    Args:
        params.reward_type: filter to 'binary', 'bounded', or 'continuous'
        params.response_format: 'markdown' (default) or 'json'

    Returns (markdown):
        Policy name, category, supported reward types, description, and tunable parameters
        with defaults and constraints — enough to advise on policy selection.
    """
    try:
        c = _client(ctx)
        query: dict[str, Any] = {}
        if params.reward_type:
            query["reward_type"] = params.reward_type
        data = await c.get("/api/v1/policies", params=query)

        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2)

        policies = data.get("policies", [])
        if not policies:
            return "no policies found matching the filter."

        lines = ["# Available Bandit Policies", ""]
        if params.reward_type:
            lines.append(f"*Filtered to reward type: **{params.reward_type}***\n")
        for p in policies:
            lines.append(f"## {p['name']}")
            lines.append(f"**Category:** {p.get('category', '—')}  |  **Reward types:** {', '.join(p.get('reward_types', []))}")
            if p.get("description"):
                lines.append(p["description"])
            user_params = p.get("user_params", [])
            if user_params:
                lines.append("\n**Configurable parameters:**")
                for up in user_params:
                    req = " *(required)*" if up.get("required") else f" (default: `{up.get('default')}`)"
                    constraints = up.get("constraints", {})
                    constraint_str = ""
                    if constraints:
                        parts = [f"{k}: {v}" for k, v in constraints.items() if v is not None]
                        if parts:
                            constraint_str = f" — constraints: {', '.join(parts)}"
                    lines.append(f"- `{up['name']}` ({up['type']}){req}{constraint_str}: {up.get('description', '')}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return _format_error(e)


@mcp.tool(name="qbrix_list_experiments", annotations=_READ_ONLY)
async def qbrix_list_experiments(params: ListExperimentsInput, ctx: Context) -> str:
    """List experiments in the workspace with optional search and state filtering.

    Use this to survey what's running, find an experiment by name, or check
    which experiments are currently paused. Returns experiment IDs needed for
    monitoring and action tools.

    Args:
        params.search: partial name match
        params.enabled: true = running only, false = paused only, omit = all
        params.limit: max results (default 20)
        params.offset: pagination offset

    Returns (markdown):
        Table of experiments with name, ID, policy, status, arm count, and gate info.
    """
    try:
        c = _client(ctx)
        result = await c.experiment.list(
            limit=params.limit,
            offset=params.offset,
            search=params.search,
            enabled=params.enabled,
        )

        if params.response_format == ResponseFormat.JSON:
            return json.dumps(
                {
                    "experiments": [e.model_dump(mode="json") for e in result.items],
                    "limit": result.limit,
                    "offset": result.offset,
                    "has_more": result.has_more,
                },
                indent=2,
            )

        if not result.items:
            return "no experiments found."

        lines = [f"# Experiments ({len(result.items)} returned)"]
        if result.has_more:
            lines.append(f"*More results available — use offset={result.offset + result.limit} to paginate*")
        lines.append("")
        lines.append("| Name | ID | Policy | Status | Arms | Gate |")
        lines.append("|------|----|--------|--------|------|------|")
        for e in result.items:
            status = "✓ running" if e.enabled else "⏸ paused"
            arm_count = len(e.pool.arms) if e.pool else "—"
            gate = f"{e.feature_gate.rollout_percentage}% rollout" if e.feature_gate else "—"
            lines.append(f"| {e.name} | `{e.id}` | {e.policy} | {status} | {arm_count} | {gate} |")
        return "\n".join(lines)
    except Exception as e:
        return _format_error(e)


@mcp.tool(name="qbrix_list_pools", annotations=_READ_ONLY)
async def qbrix_list_pools(params: ListPoolsInput, ctx: Context) -> str:
    """List all arm pools in the workspace.

    Use this to discover existing pools before running a new experiment on them.
    Pools are reusable — the same set of variants can be tested with different
    policies in separate experiments.

    Args:
        params.limit: max results (default 20)
        params.offset: pagination offset

    Returns (markdown):
        Each pool's name, ID, and arm names. Use a pool ID with
        qbrix_create_experiment_from_pool to reuse it.
    """
    try:
        c = _client(ctx)
        result = await c.pool.list(limit=params.limit, offset=params.offset)

        if params.response_format == ResponseFormat.JSON:
            return json.dumps(
                {
                    "pools": [p.model_dump(mode="json") for p in result.items],
                    "limit": result.limit,
                    "offset": result.offset,
                    "has_more": result.has_more,
                },
                indent=2,
            )

        if not result.items:
            return "no pools found."

        lines = [f"# Pools ({len(result.items)} returned)", ""]
        for p in result.items:
            arm_names = ", ".join(a.name for a in p.arms)
            lines.append(f"## {p.name}")
            lines.append(f"**ID:** `{p.id}`")
            lines.append(f"**Arms ({len(p.arms)}):** {arm_names}")
            lines.append("")
        if result.has_more:
            lines.append(f"*More results available — use offset={result.offset + result.limit} to paginate*")
        return "\n".join(lines)
    except Exception as e:
        return _format_error(e)


@mcp.tool(name="qbrix_get_pool", annotations=_READ_ONLY)
async def qbrix_get_pool(params: GetPoolInput, ctx: Context) -> str:
    """Get full details of a pool including all arms and their metadata payloads.

    Use this to inspect an existing pool before reusing it in a new experiment,
    or to look up arm IDs needed for gate rule configuration.

    Args:
        params.pool_id: pool ID

    Returns (markdown):
        Pool name, all arms with ID, index, active status, and metadata payload.
    """
    try:
        c = _client(ctx)
        pool = await c.pool.get(params.pool_id)

        if params.response_format == ResponseFormat.JSON:
            return pool.model_dump_json(indent=2)

        lines = [
            f"# Pool: {pool.name}",
            f"**ID:** `{pool.id}`",
            "",
            _fmt_arm_table(pool.arms),
        ]
        return "\n".join(lines)
    except Exception as e:
        return _format_error(e)


# ---------------------------------------------------------------------------
# phase 2 — setup
# ---------------------------------------------------------------------------

@mcp.tool(name="qbrix_setup_experiment", annotations=_WRITE)
async def qbrix_setup_experiment(params: SetupExperimentInput, ctx: Context) -> str:
    """Create a new experiment from scratch — pool, experiment, and optional gate in one call.

    This is the primary setup tool. It creates the pool of arms, creates the
    experiment with the chosen policy, and optionally sets a traffic rollout gate —
    all atomically. Use this when you don't have an existing pool to reuse.

    Workflow:
        1. Use qbrix_list_policies to choose a policy
        2. Call this tool with arm names, metadata payloads, and policy
        3. Use the returned experiment_id in qbrix_select calls

    Args:
        params.name: experiment name
        params.arms: list of variants with name and optional metadata payload
        params.policy: policy name from qbrix_list_policies, or 'auto'
        params.policy_params: optional policy configuration parameters
        params.enabled: start immediately (default true)
        params.rollout_percentage: if set, creates a gate limiting traffic to this %

    Returns:
        Experiment ID, pool ID, arm name→ID mapping, and integration guidance.
        All IDs are needed for qbrix_select and qbrix_configure_gate calls.
    """
    try:
        c = _client(ctx)
        arms_data = [{"name": a.name, "metadata": a.metadata} for a in params.arms]
        pool = await c.pool.create(name=params.name, arms=arms_data)

        experiment = await c.experiment.create(
            name=params.name,
            pool_id=pool.id,
            policy=params.policy,
            policy_params=params.policy_params,
            enabled=params.enabled,
        )

        gate = None
        if params.rollout_percentage is not None:
            gate = await c.gate.create(
                experiment.id,
                rollout_percentage=params.rollout_percentage,
            )

        arm_map = {a.name: a.id for a in pool.arms}

        lines = [
            f"# Experiment Created: {experiment.name}",
            "",
            f"**Experiment ID:** `{experiment.id}`",
            f"**Pool ID:** `{pool.id}`",
            f"**Policy:** {experiment.policy}",
            f"**Status:** {'✓ running' if experiment.enabled else '⏸ paused'}",
            "",
            "## Arms",
            _fmt_arm_table(pool.arms),
        ]

        if gate:
            lines += [
                "",
                f"## Gate: {gate.rollout_percentage}% traffic rollout active",
                "Use qbrix_configure_gate to add targeting rules or adjust rollout.",
            ]

        lines += [
            "",
            "## Integration",
            "```python",
            f'response = client.agent.select("{experiment.id}", context={{"id": user_id}})',
            "arm = response.arm  # arm.name or arm.metadata to render the variant",
            "# after observing outcome:",
            "client.agent.feedback(response.request_id, reward=1.0)  # or 0.0 for no-conversion",
            "```",
            "",
            "**Arm IDs (for gate rules):**",
        ]
        for name, arm_id in arm_map.items():
            lines.append(f"- `{name}`: `{arm_id}`")

        return "\n".join(lines)
    except Exception as e:
        return _format_error(e)


@mcp.tool(name="qbrix_create_experiment_from_pool", annotations=_WRITE)
async def qbrix_create_experiment_from_pool(
    params: CreateExperimentFromPoolInput, ctx: Context
) -> str:
    """Create a new experiment using an existing pool of arms.

    Use this when you already have a pool and want to run a new experiment on the
    same set of variants — for example to compare policies or restart after deleting
    a previous experiment.

    Use qbrix_list_pools or qbrix_get_pool first to find the pool ID and arm IDs.

    Args:
        params.name: experiment name
        params.pool_id: ID of the existing pool
        params.policy: policy name — use qbrix_list_policies
        params.policy_params: optional policy configuration
        params.enabled: start immediately (default true)

    Returns:
        Experiment ID and arm list for integration.
    """
    try:
        c = _client(ctx)
        experiment = await c.experiment.create(
            name=params.name,
            pool_id=params.pool_id,
            policy=params.policy,
            policy_params=params.policy_params,
            enabled=params.enabled,
        )

        lines = [
            f"# Experiment Created: {experiment.name}",
            "",
            f"**Experiment ID:** `{experiment.id}`",
            f"**Pool ID:** `{params.pool_id}`",
            f"**Policy:** {experiment.policy}",
            f"**Status:** {'✓ running' if experiment.enabled else '⏸ paused'}",
        ]

        if experiment.pool:
            lines += ["", "## Arms", _fmt_arm_table(experiment.pool.arms)]

        lines += [
            "",
            "Use qbrix_configure_gate to set a rollout percentage or targeting rules.",
        ]
        return "\n".join(lines)
    except Exception as e:
        return _format_error(e)


@mcp.tool(name="qbrix_configure_gate", annotations=_WRITE_IDEMPOTENT)
async def qbrix_configure_gate(params: ConfigureGateInput, ctx: Context) -> str:
    """Create or update (upsert) the feature gate for an experiment.

    A feature gate controls who enters the experiment: rollout percentage caps
    total traffic, targeting rules route specific user segments, and schedules
    restrict when the experiment runs. All parameters are optional — omitted
    fields use defaults (100% rollout, no rules, no schedule, UTC).

    This tool is idempotent — call it to configure the gate whether or not one
    already exists, and call it again to update the configuration.

    Gate rule examples:
        # Only premium users
        rules=[{"key": "plan", "operator": "eq", "value": "premium"}]
        # US and Canada only
        rules=[{"key": "country", "operator": "in", "value": ["US", "CA"]}]
        # Route new users to a specific arm
        rules=[{"key": "user_type", "operator": "eq", "value": "new", "arm_name": "onboarding"}]

    Args:
        params.experiment_id: experiment to configure
        params.rollout_percentage: % of traffic to include (default 100)
        params.rules: targeting rules, evaluated in order — first match wins
        params.schedule_start/end: ISO 8601 datetimes for active window
        params.active_hours_start/end: HH:MM daily active window
        params.default_arm_id: arm for users excluded by the gate
        params.timezone: for schedule and active hours (default UTC)

    Returns:
        Configured gate with full settings and plain-English rule summary.
    """
    try:
        c = _client(ctx)
        rules_data = [r.model_dump(exclude_none=True) for r in params.rules]

        gate_kwargs: dict[str, Any] = dict(
            rollout_percentage=params.rollout_percentage,
            rules=rules_data,
            timezone=params.timezone,
        )
        if params.schedule_start is not None:
            gate_kwargs["schedule_start"] = params.schedule_start
        if params.schedule_end is not None:
            gate_kwargs["schedule_end"] = params.schedule_end
        if params.active_hours_start is not None:
            gate_kwargs["active_hours_start"] = params.active_hours_start
        if params.active_hours_end is not None:
            gate_kwargs["active_hours_end"] = params.active_hours_end
        if params.default_arm_id is not None:
            gate_kwargs["default_arm_id"] = params.default_arm_id

        try:
            gate = await c.gate.update(params.experiment_id, **gate_kwargs)
        except QbrixAPIError as api_err:
            if api_err.status_code == 404:
                gate = await c.gate.create(params.experiment_id, **gate_kwargs)
            else:
                raise

        if params.response_format == ResponseFormat.JSON:
            return gate.model_dump_json(indent=2)

        lines = [
            f"# Gate Configured: experiment `{params.experiment_id}`",
            "",
            _fmt_gate(gate),
        ]
        return "\n".join(lines)
    except Exception as e:
        return _format_error(e)


# ---------------------------------------------------------------------------
# phase 3 — monitoring
# ---------------------------------------------------------------------------

@mcp.tool(name="qbrix_get_experiment", annotations=_READ_ONLY)
async def qbrix_get_experiment(params: GetExperimentInput, ctx: Context) -> str:
    """Get full details of an experiment including its policy, arms, and gate configuration.

    Use this to inspect the current state of an experiment before taking action,
    or to verify a setup completed correctly.

    Args:
        params.experiment_id: experiment ID

    Returns (markdown):
        Experiment config, policy and params, enabled state, pool with all arms,
        and gate configuration if present.
    """
    try:
        c = _client(ctx)
        experiment = await c.experiment.get(params.experiment_id)

        if params.response_format == ResponseFormat.JSON:
            return experiment.model_dump_json(indent=2)

        return _fmt_experiment(experiment)
    except Exception as e:
        return _format_error(e)


@mcp.tool(name="qbrix_get_gate", annotations=_READ_ONLY)
async def qbrix_get_gate(params: GetGateInput, ctx: Context) -> str:
    """Get the feature gate configuration for an experiment.

    Use this to inspect rollout %, targeting rules, and schedule before
    modifying a gate with qbrix_configure_gate.

    Args:
        params.experiment_id: experiment ID

    Returns (markdown):
        Rollout percentage, targeting rules in plain language, schedule,
        and active hours window.
    """
    try:
        c = _client(ctx)
        gate = await c.gate.get(params.experiment_id)

        if params.response_format == ResponseFormat.JSON:
            return gate.model_dump_json(indent=2)

        lines = [
            f"# Gate: experiment `{params.experiment_id}`",
            f"*Last updated: {gate.updated_at or 'unknown'}  |  Version: {gate.version}*",
            "",
            _fmt_gate(gate),
        ]
        return "\n".join(lines)
    except Exception as e:
        return _format_error(e)


@mcp.tool(name="qbrix_get_stats", annotations=_READ_ONLY)
async def qbrix_get_stats(params: GetStatsInput, ctx: Context) -> str:
    """Get performance statistics for an experiment including per-arm breakdown.

    Returns aggregate metrics and per-arm results showing which variants are
    winning. Use this to decide whether to continue, pause, or declare a winner.

    Requires Qbrix Enterprise Edition (EE) with analytics enabled.
    Optional time range filters scope the stats to a specific period.

    Args:
        params.experiment_id: experiment ID
        params.start_ms: start of window (epoch milliseconds)
        params.end_ms: end of window (epoch milliseconds)

    Returns (markdown):
        Overview metrics (selections, feedback, rewards, default/gated traffic)
        and per-arm table with selections, feedback count, and average reward.
    """
    try:
        c = _client(ctx)
        query: dict[str, Any] = {}
        if params.start_ms is not None:
            query["start_ms"] = params.start_ms
        if params.end_ms is not None:
            query["end_ms"] = params.end_ms

        overview = await c.get(
            f"/api/v1/ee/insight/experiment/{params.experiment_id}",
            params=query,
        )

        arms: list[dict[str, Any]] = []
        try:
            arm_data = await c.get(
                f"/api/v1/ee/insight/experiment/{params.experiment_id}/arms",
                params=query,
            )
            arms = arm_data.get("arms", [])
        except QbrixAPIError as e:
            if e.status_code != 404:
                raise

        if params.response_format == ResponseFormat.JSON:
            return json.dumps({"overview": overview, "arms": arms}, indent=2)

        lines = [
            f"# Experiment Stats: `{params.experiment_id}`",
            "",
            f"**Total selections:** {overview.get('total_selections', 0):,}",
            f"**Default (gated out):** {overview.get('default_selections', 0):,}",
            f"**Total feedback:** {overview.get('total_feedback', 0):,}",
            f"**Avg reward:** {overview.get('avg_reward') or '—'}",
            f"**Unique contexts:** {overview.get('unique_contexts', 0):,}",
        ]
        if overview.get("first_selection_ms"):
            lines.append(f"**First selection:** {overview['first_selection_ms']} ms epoch")
        if overview.get("last_selection_ms"):
            lines.append(f"**Last selection:** {overview['last_selection_ms']} ms epoch")

        if arms:
            lines += [
                "",
                "## Per-Arm Performance",
                "| Arm | Selections | Feedback | Avg Reward |",
                "|-----|-----------|---------|------------|",
            ]
            sorted_arms = sorted(arms, key=lambda a: a.get("avg_reward") or 0, reverse=True)
            for arm in sorted_arms:
                avg = arm.get("avg_reward")
                avg_str = f"{avg:.4f}" if avg is not None else "—"
                lines.append(
                    f"| {arm.get('arm_name', '?')} | {arm.get('selections', 0):,} | "
                    f"{arm.get('feedback_count', 0):,} | {avg_str} |"
                )

        return "\n".join(lines)
    except Exception as e:
        return _format_error(e)


# ---------------------------------------------------------------------------
# phase 4 — action (semantic lifecycle)
# ---------------------------------------------------------------------------

@mcp.tool(name="qbrix_pause_experiment", annotations=_WRITE_IDEMPOTENT)
async def qbrix_pause_experiment(params: ExperimentIdInput, ctx: Context) -> str:
    """Pause an experiment — stop traffic allocation while preserving learning state.

    The bandit's learned arm weights are kept. Resume at any time with
    qbrix_resume_experiment to continue from where it left off. Prefer this
    over deleting when you may want to resume or revisit the results later.

    Args:
        params.experiment_id: experiment ID

    Returns:
        Confirmation that the experiment is paused.
    """
    try:
        c = _client(ctx)
        await c.experiment.update(params.experiment_id, enabled=False)
        return f"experiment `{params.experiment_id}` paused. learning state preserved. use qbrix_resume_experiment to restart."
    except Exception as e:
        return _format_error(e)


@mcp.tool(name="qbrix_resume_experiment", annotations=_WRITE_IDEMPOTENT)
async def qbrix_resume_experiment(params: ExperimentIdInput, ctx: Context) -> str:
    """Resume a paused experiment — re-enable traffic allocation.

    Picks up from the existing learned arm weights. Gate configuration is
    unchanged.

    Args:
        params.experiment_id: experiment ID

    Returns:
        Confirmation that the experiment is running again.
    """
    try:
        c = _client(ctx)
        await c.experiment.update(params.experiment_id, enabled=True)
        return f"experiment `{params.experiment_id}` resumed and running."
    except Exception as e:
        return _format_error(e)


@mcp.tool(name="qbrix_tune_experiment", annotations=_WRITE)
async def qbrix_tune_experiment(params: TuneExperimentInput, ctx: Context) -> str:
    """Update the policy parameters of a running experiment.

    Use this to tune exploration-exploitation trade-offs without stopping the
    experiment. Use qbrix_get_experiment first to see the current parameters
    before modifying them.

    Args:
        params.experiment_id: experiment ID
        params.policy_params: new policy parameters dict — replaces current params

    Returns:
        Updated experiment with new policy params confirmed.
    """
    try:
        c = _client(ctx)
        experiment = await c.experiment.update(
            params.experiment_id,
            policy_params=params.policy_params,
        )
        return (
            f"experiment `{experiment.id}` updated.\n"
            f"**Policy:** {experiment.policy}\n"
            f"**New params:** `{json.dumps(experiment.policy_params)}`"
        )
    except Exception as e:
        return _format_error(e)


@mcp.tool(name="qbrix_delete_experiment", annotations=_DESTRUCTIVE)
async def qbrix_delete_experiment(params: ExperimentIdInput, ctx: Context) -> str:
    """Permanently delete an experiment and its learned parameter state.

    This is irreversible. The underlying pool and arms are NOT deleted and
    can be reused in a new experiment via qbrix_create_experiment_from_pool.

    Consider qbrix_pause_experiment instead if you may want to resume later
    or review the results.

    Args:
        params.experiment_id: experiment ID to delete

    Returns:
        Confirmation of deletion.
    """
    try:
        c = _client(ctx)
        await c.experiment.delete(params.experiment_id)
        return (
            f"experiment `{params.experiment_id}` permanently deleted. "
            "the pool and arms are still available for new experiments."
        )
    except Exception as e:
        return _format_error(e)


@mcp.tool(name="qbrix_remove_gate", annotations=_WRITE)
async def qbrix_remove_gate(params: ExperimentIdInput, ctx: Context) -> str:
    """Remove the feature gate from an experiment.

    After removal, 100% of traffic passes to the bandit unconditionally —
    no rollout cap, no targeting rules, no schedule. Use this when you want
    to open the experiment to all traffic.

    To update gate settings instead of removing them, use qbrix_configure_gate.

    Args:
        params.experiment_id: experiment ID

    Returns:
        Confirmation that the gate has been removed.
    """
    try:
        c = _client(ctx)
        await c.gate.delete(params.experiment_id)
        return (
            f"gate removed from experiment `{params.experiment_id}`. "
            "100% of traffic now passes to the bandit unconditionally."
        )
    except Exception as e:
        return _format_error(e)


# ---------------------------------------------------------------------------
# hot path — select / feedback
# ---------------------------------------------------------------------------

@mcp.tool(name="qbrix_select", annotations=_READ_ONLY)
async def qbrix_select(params: SelectInput, ctx: Context) -> str:
    """Select an arm (variant) for a given context — the core bandit call.

    Call this before acting. The bandit evaluates the feature gate (if configured),
    then selects the best arm based on learned reward distributions. The returned
    request_id must be passed unchanged to qbrix_feedback after observing the outcome.

    Selection loop:
        1. Call qbrix_select → get arm + request_id
        2. Use arm.name or arm_metadata to render the variant or take the action
        3. Observe the outcome (click, conversion, revenue, etc.)
        4. Call qbrix_feedback(request_id, reward) to close the learning loop

    Note on is_default:
        is_default=true means the feature gate committed a specific arm (e.g. a
        targeting rule matched). The bandit was bypassed. Feedback is still accepted
        and tracked but does not affect arm weights.

    Note on context_vector:
        Required for contextual policies (LinUCBPolicy, LinTSPolicy). Length must
        match the experiment's 'dim' policy param. Omit for all other policies.

    Args:
        params.experiment_id: experiment to select from
        params.context_id: stable user/session ID for consistent assignment
        params.context_vector: feature vector for contextual policies
        params.context_metadata: key-value context for gate rule evaluation

    Returns:
        JSON with arm_name, arm_id, arm_index, arm_metadata, request_id, is_default.
    """
    try:
        c = _client(ctx)
        context: dict[str, Any] = {"id": params.context_id}
        if params.context_vector is not None:
            context["vector"] = params.context_vector
        if params.context_metadata is not None:
            context["metadata"] = params.context_metadata

        result = await c.agent.select(
            experiment_id=params.experiment_id,
            context=context,
        )
        return json.dumps(
            {
                "arm_name": result.arm.name,
                "arm_id": result.arm.id,
                "arm_index": result.arm.index,
                "request_id": result.request_id,
                "is_default": result.is_default,
            },
            indent=2,
        )
    except Exception as e:
        return _format_error(e)


@mcp.tool(name="qbrix_feedback", annotations=_WRITE)
async def qbrix_feedback(params: FeedbackInput, ctx: Context) -> str:
    """Submit a reward signal for a previous selection — closes the learning loop.

    Call this after observing the outcome of a qbrix_select call. The reward
    teaches the bandit which arms perform better so future selections improve.

    The request_id is an HMAC-signed token — pass it exactly as returned by
    qbrix_select. Any modification will cause rejection.

    Reward values by policy type:
        BetaTSPolicy (binary): 1.0 (success) or 0.0 (failure)
        GaussianTSPolicy (continuous): actual metric value e.g. 42.5 for $42.50
        UCB1TunedPolicy, EpsilonPolicy etc: typically 0.0–1.0 but unbounded

    Args:
        params.request_id: the request_id from qbrix_select — unchanged
        params.reward: observed outcome value

    Returns:
        JSON with accepted=true on success.
    """
    try:
        c = _client(ctx)
        await c.agent.feedback(
            request_id=params.request_id,
            reward=params.reward,
        )
        return json.dumps({"accepted": True})
    except Exception as e:
        return _format_error(e)


# ---------------------------------------------------------------------------
# power user — pool management
# ---------------------------------------------------------------------------

@mcp.tool(name="qbrix_create_pool", annotations=_WRITE)
async def qbrix_create_pool(params: CreatePoolInput, ctx: Context) -> str:
    """Create a standalone pool of arms for reuse across multiple experiments.

    Pools are reusable — the same set of variants can be tested with different
    policies in different experiments over time. Use this when you want to
    manage the pool lifecycle separately from experiments.

    For most cases, prefer qbrix_setup_experiment which creates a pool and
    experiment in one step.

    Args:
        params.name: pool name
        params.arms: list of arms with name and optional metadata payload

    Returns:
        Pool ID and arm IDs. Use the pool ID with qbrix_create_experiment_from_pool.
    """
    try:
        c = _client(ctx)
        arms_data = [{"name": a.name, "metadata": a.metadata} for a in params.arms]
        pool = await c.pool.create(name=params.name, arms=arms_data)

        lines = [
            f"# Pool Created: {pool.name}",
            f"**ID:** `{pool.id}`",
            "",
            _fmt_arm_table(pool.arms),
            "",
            f"Use `pool_id: \"{pool.id}\"` with qbrix_create_experiment_from_pool to run an experiment on these arms.",
        ]
        return "\n".join(lines)
    except Exception as e:
        return _format_error(e)


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
