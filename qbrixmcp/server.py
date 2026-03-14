"""qbrix MCP server — experiment lifecycle tools for AI agents.

provides tools for creating, managing, and monitoring multi-armed bandit
experiments on the qbrix platform. designed for agentic experimentation
loops where agents control the experiment lifecycle while the qbrix
engine handles real-time traffic allocation and learning.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any
from typing import Optional

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


def _get_client(ctx) -> AsyncQbrix:
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
        if status == 429:
            return "error: rate limit exceeded. wait before retrying."
        return f"error: API returned {status}. detail: {detail}"
    if isinstance(e, QbrixConnectionError):
        return "error: cannot connect to qbrix API. check QBRIX_BASE_URL and that proxysvc is running."
    if isinstance(e, QbrixTimeoutError):
        return "error: request timed out. check that qbrix proxysvc is running."
    return f"error: {type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# input models
# ---------------------------------------------------------------------------

class ListPoliciesInput(BaseModel):
    """input for listing available bandit policies."""
    model_config = ConfigDict(str_strip_whitespace=True)

    reward_type: Optional[str] = Field(
        default=None,
        description="filter by reward type: 'binary', 'bounded', or 'continuous'",
    )


class ArmInput(BaseModel):
    """a single arm (variant) to include in a pool."""
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., description="arm name (e.g. 'red-cta', 'pricing-v2')", min_length=1)
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="arbitrary payload for this arm — the data your site/SDK uses to render the variant (e.g. {\"text\": \"Buy Now\", \"color\": \"#ef4444\"})",
    )


class CreatePoolInput(BaseModel):
    """input for creating a pool of arms (variants)."""
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., description="pool name (e.g. 'pricing-cta-variants')", min_length=1)
    arms: list[ArmInput] = Field(..., description="list of arms (variants) in this pool, minimum 2", min_length=2)


class ListPoolsInput(BaseModel):
    """input for listing pools."""
    model_config = ConfigDict(str_strip_whitespace=True)

    limit: int = Field(default=20, description="max results to return", ge=1, le=100)
    offset: int = Field(default=0, description="pagination offset", ge=0)


class GetPoolInput(BaseModel):
    """input for getting a single pool."""
    model_config = ConfigDict(str_strip_whitespace=True)

    pool_id: str = Field(..., description="pool ID", min_length=1)


class CreateExperimentInput(BaseModel):
    """input for creating a new bandit experiment."""
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., description="experiment name (e.g. 'homepage-hero-test')", min_length=1)
    pool_id: str = Field(..., description="ID of the pool containing the arms to test", min_length=1)
    policy: str = Field(
        ...,
        description="bandit policy name — use qbrix_list_policies to see available options (e.g. 'BetaTS', 'UCB1Tuned', 'LinUCB')",
    )
    policy_params: Optional[dict[str, Any]] = Field(
        default=None,
        description="policy-specific parameters — use qbrix_list_policies to see configurable params per policy (e.g. {\"alpha_prior\": 1.0, \"beta_prior\": 1.0} for BetaTS)",
    )
    enabled: bool = Field(default=True, description="start the experiment immediately")


class ListExperimentsInput(BaseModel):
    """input for listing experiments."""
    model_config = ConfigDict(str_strip_whitespace=True)

    limit: int = Field(default=20, description="max results to return", ge=1, le=100)
    offset: int = Field(default=0, description="pagination offset", ge=0)
    search: Optional[str] = Field(default=None, description="search by experiment name")
    enabled: Optional[bool] = Field(default=None, description="filter by enabled state")


class GetExperimentInput(BaseModel):
    """input for getting a single experiment."""
    model_config = ConfigDict(str_strip_whitespace=True)

    experiment_id: str = Field(..., description="experiment ID", min_length=1)


class UpdateExperimentInput(BaseModel):
    """input for updating an experiment."""
    model_config = ConfigDict(str_strip_whitespace=True)

    experiment_id: str = Field(..., description="experiment ID", min_length=1)
    enabled: Optional[bool] = Field(default=None, description="enable or disable the experiment")
    policy_params: Optional[dict[str, Any]] = Field(default=None, description="updated policy parameters")


class DeleteExperimentInput(BaseModel):
    """input for deleting an experiment."""
    model_config = ConfigDict(str_strip_whitespace=True)

    experiment_id: str = Field(..., description="experiment ID", min_length=1)


class GetExperimentStatsInput(BaseModel):
    """input for getting experiment performance statistics."""
    model_config = ConfigDict(str_strip_whitespace=True)

    experiment_id: str = Field(..., description="experiment ID", min_length=1)
    start_ms: Optional[int] = Field(default=None, description="start time filter (epoch ms)", ge=0)
    end_ms: Optional[int] = Field(default=None, description="end time filter (epoch ms)", ge=0)


# ---------------------------------------------------------------------------
# resources
# ---------------------------------------------------------------------------

@mcp.resource("qbrix://policies")
async def policies_resource() -> str:
    """all available bandit policies with their configurable parameters.

    use this resource to understand which policies are available and how
    to configure them before creating experiments.
    """
    async with AsyncQbrix() as client:
        data = await client.get("/api/v1/policies")
        return json.dumps(data, indent=2)


@mcp.resource("qbrix://experiments")
async def experiments_resource() -> str:
    """summary of all experiments in the workspace.

    provides a quick overview of active and inactive experiments.
    """
    async with AsyncQbrix() as client:
        result = await client.experiment.list(limit=100)
        items = [e.model_dump(mode="json") for e in result.items]
        return json.dumps({"experiments": items}, indent=2)


# ---------------------------------------------------------------------------
# tools
# ---------------------------------------------------------------------------

@mcp.tool(name="qbrix_list_policies", annotations=_READ_ONLY)
async def qbrix_list_policies(params: ListPoliciesInput, ctx=None) -> str:
    """list all available bandit policies and their configurable parameters.

    returns every policy qbrix supports — stochastic (BetaTS, UCB1Tuned, etc.),
    contextual (LinUCB, LinTS), and adversarial (EXP3, FPL). each policy
    includes its category, supported reward types, and tunable parameters.

    call this before creating an experiment to choose the right policy.
    filter by reward_type if you know your reward signal type.

    returns:
        JSON with a 'policies' array, each containing:
        - name (str): policy identifier to use in qbrix_create_experiment
        - category (str): 'stochastic', 'contextual', or 'adversarial'
        - reward_types (list[str]): supported reward types ('binary', 'bounded', 'continuous')
        - description (str): what this policy does
        - user_params (list): configurable parameters with name, type, default, constraints
    """
    try:
        client = _get_client(ctx)
        query: dict[str, Any] = {}
        if params.reward_type:
            query["reward_type"] = params.reward_type
        data = await client.get("/api/v1/policies", params=query)
        return json.dumps(data, indent=2)
    except Exception as e:
        return _format_error(e)


@mcp.tool(name="qbrix_create_pool", annotations=_WRITE)
async def qbrix_create_pool(params: CreatePoolInput, ctx=None) -> str:
    """create a pool of arms (variants) that experiments will test.

    a pool defines the set of options to choose between. each arm has a name
    and optional metadata payload containing the data your site needs to
    render that variant (text, colors, image URLs, config values, etc.).

    pools are reusable — multiple experiments can share the same pool to
    compare different optimization policies on the same set of variants.

    example arms:
        [
            {"name": "control", "metadata": {"headline": "Welcome"}},
            {"name": "urgent", "metadata": {"headline": "Limited Time Offer!"}}
        ]

    returns:
        JSON with the created pool including generated IDs for each arm.
    """
    try:
        client = _get_client(ctx)
        arms = [{"name": a.name, "metadata": a.metadata} for a in params.arms]
        pool = await client.pool.create(name=params.name, arms=arms)
        return pool.model_dump_json(indent=2)
    except Exception as e:
        return _format_error(e)


@mcp.tool(name="qbrix_list_pools", annotations=_READ_ONLY)
async def qbrix_list_pools(params: ListPoolsInput, ctx=None) -> str:
    """list all arm pools in the workspace.

    returns:
        JSON with a 'pools' array and pagination info (limit, offset).
    """
    try:
        client = _get_client(ctx)
        result = await client.pool.list(limit=params.limit, offset=params.offset)
        return json.dumps(
            {
                "pools": [p.model_dump(mode="json") for p in result.items],
                "limit": result.limit,
                "offset": result.offset,
                "has_more": result.has_more,
            },
            indent=2,
        )
    except Exception as e:
        return _format_error(e)


@mcp.tool(name="qbrix_get_pool", annotations=_READ_ONLY)
async def qbrix_get_pool(params: GetPoolInput, ctx=None) -> str:
    """get a pool by ID including all its arms and their metadata.

    returns:
        JSON with pool details: id, name, arms (each with id, name, index, metadata).
    """
    try:
        client = _get_client(ctx)
        pool = await client.pool.get(params.pool_id)
        return pool.model_dump_json(indent=2)
    except Exception as e:
        return _format_error(e)


@mcp.tool(name="qbrix_create_experiment", annotations=_WRITE)
async def qbrix_create_experiment(params: CreateExperimentInput, ctx=None) -> str:
    """create a new bandit experiment on an existing pool of arms.

    the experiment starts optimizing traffic allocation immediately if
    enabled=true. the bandit policy continuously learns from feedback
    and shifts traffic toward better-performing arms.

    workflow:
        1. use qbrix_list_policies to choose a policy
        2. use qbrix_create_pool to create arms with variant payloads
        3. use this tool to start the experiment
        4. use qbrix_get_experiment_stats to monitor performance

    the policy parameter must match a policy name from qbrix_list_policies
    (e.g. 'BetaTS', 'UCB1Tuned', 'LinUCB', 'EXP3').

    returns:
        JSON with the created experiment including id, policy config,
        and nested pool with arm details.
    """
    try:
        client = _get_client(ctx)
        experiment = await client.experiment.create(
            name=params.name,
            pool_id=params.pool_id,
            policy=params.policy,
            policy_params=params.policy_params,
            enabled=params.enabled,
        )
        return experiment.model_dump_json(indent=2)
    except Exception as e:
        return _format_error(e)


@mcp.tool(name="qbrix_list_experiments", annotations=_READ_ONLY)
async def qbrix_list_experiments(params: ListExperimentsInput, ctx=None) -> str:
    """list experiments in the workspace with optional filtering.

    use search to find experiments by name, or filter by enabled state
    to see only active or paused experiments.

    returns:
        JSON with an 'experiments' array and pagination info (limit, offset).
        each experiment includes id, name, policy, enabled state, and nested pool.
    """
    try:
        client = _get_client(ctx)
        result = await client.experiment.list(
            limit=params.limit,
            offset=params.offset,
            search=params.search,
            enabled=params.enabled,
        )
        return json.dumps(
            {
                "experiments": [e.model_dump(mode="json") for e in result.items],
                "limit": result.limit,
                "offset": result.offset,
                "has_more": result.has_more,
            },
            indent=2,
        )
    except Exception as e:
        return _format_error(e)


@mcp.tool(name="qbrix_get_experiment", annotations=_READ_ONLY)
async def qbrix_get_experiment(params: GetExperimentInput, ctx=None) -> str:
    """get full details of a single experiment.

    returns the experiment configuration including policy, parameters,
    enabled state, the nested pool with all arms and their metadata,
    and any feature gate configuration.

    returns:
        JSON with experiment details: id, name, pool_id, policy, policy_params,
        enabled, created_at, updated_at, pool (with arms), feature_gate (if set).
    """
    try:
        client = _get_client(ctx)
        experiment = await client.experiment.get(params.experiment_id)
        return experiment.model_dump_json(indent=2)
    except Exception as e:
        return _format_error(e)


@mcp.tool(name="qbrix_update_experiment", annotations=_WRITE_IDEMPOTENT)
async def qbrix_update_experiment(params: UpdateExperimentInput, ctx=None) -> str:
    """update an experiment's enabled state or policy parameters.

    use this to:
    - pause an experiment: enabled=false
    - resume an experiment: enabled=true
    - tune policy parameters: policy_params={...}

    only provided fields are updated — omitted fields remain unchanged.

    returns:
        JSON with the updated experiment.
    """
    try:
        client = _get_client(ctx)
        experiment = await client.experiment.update(
            params.experiment_id,
            enabled=params.enabled,
            policy_params=params.policy_params,
        )
        return experiment.model_dump_json(indent=2)
    except Exception as e:
        return _format_error(e)


@mcp.tool(name="qbrix_delete_experiment", annotations=_DESTRUCTIVE)
async def qbrix_delete_experiment(params: DeleteExperimentInput, ctx=None) -> str:
    """permanently delete an experiment.

    this removes the experiment and its parameter state. the underlying
    pool and arms are not deleted and can be reused.

    this action is irreversible. consider disabling the experiment
    (qbrix_update_experiment with enabled=false) instead if you may
    want to resume it later.

    returns:
        JSON confirmation message.
    """
    try:
        client = _get_client(ctx)
        await client.experiment.delete(params.experiment_id)
        return json.dumps({"message": "experiment deleted successfully"})
    except Exception as e:
        return _format_error(e)


@mcp.tool(name="qbrix_get_experiment_stats", annotations=_READ_ONLY)
async def qbrix_get_experiment_stats(params: GetExperimentStatsInput, ctx=None) -> str:
    """get performance statistics for an experiment including per-arm breakdown.

    returns aggregate metrics (total selections, feedback count, average reward)
    and per-arm statistics showing how each variant is performing.

    use this to monitor experiment progress and decide whether to continue,
    iterate, or promote a winning arm.

    requires qbrix Enterprise Edition (EE) with analytics enabled.

    optional time range filters (start_ms, end_ms) scope the stats to a
    specific period. timestamps are in epoch milliseconds.

    returns:
        JSON with two sections:
        - overview: total_selections, total_feedback, avg_reward, min_reward,
          max_reward, unique_contexts, first/last_selection_ms
        - arms: per-arm array with arm_index, arm_name, selections,
          feedback_count, avg_reward
    """
    try:
        client = _get_client(ctx)
        query: dict[str, Any] = {}
        if params.start_ms is not None:
            query["start_ms"] = params.start_ms
        if params.end_ms is not None:
            query["end_ms"] = params.end_ms

        overview = await client.get(
            f"/api/v1/ee/insight/experiment/{params.experiment_id}",
            params=query,
        )

        result: dict[str, Any] = {"overview": overview}
        try:
            arms = await client.get(
                f"/api/v1/ee/insight/experiment/{params.experiment_id}/arms",
                params=query,
            )
            result["arms"] = arms.get("arms", [])
        except QbrixAPIError:
            pass

        return json.dumps(result, indent=2)
    except Exception as e:
        return _format_error(e)


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def main():
    mcp.run()


if __name__ == "__main__":
    main()
