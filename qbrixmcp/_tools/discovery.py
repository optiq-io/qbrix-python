from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.fastmcp import Context
from mcp.server.fastmcp import FastMCP

from qbrixmcp._models import GetPoolInput
from qbrixmcp._models import ListExperimentsInput
from qbrixmcp._models import ListPoliciesInput
from qbrixmcp._models import ListPoolsInput
from qbrixmcp._models import ResponseFormat
from qbrixmcp._utils import READ_ONLY
from qbrixmcp._utils import fmt_arm_table
from qbrixmcp._utils import format_error
from qbrixmcp._utils import get_client

logger = logging.getLogger(__name__)


async def qbrix_list_policies(params: ListPoliciesInput, ctx: Context) -> str:
    """List all available bandit policies with their parameters and reward type compatibility.

    Use this before creating an experiment to choose the right policy for your use case.
    Optionally filter by reward type to see only compatible policies.

    Policy categories:
    - stochastic: BetaTSPolicy (binary), GaussianTSPolicy (continuous), UCB1TunedPolicy,
      KLUCBPolicy, EpsilonPolicy, MOSSPolicy — no context vector required
    - contextual: LinUCBPolicy, LinTSPolicy — require context.vector per selection
    - adversarial: EXP3Policy, FPLPolicy — robust to non-stationary reward distributions
    - auto: qbrix selects and tunes a policy automatically (MetaBandit)

    Args:
        params.reward_type: filter to 'binary', 'bounded', or 'continuous'
        params.response_format: 'markdown' (default) or 'json'

    Returns (markdown):
        Policy name, category, supported reward types, description, and tunable parameters.
    """
    try:
        client = get_client(ctx)
        query: dict[str, Any] = {}
        if params.reward_type:
            query["reward_type"] = params.reward_type
        logger.debug("list_policies reward_type=%s", params.reward_type)
        data = await client.get("/api/v1/policies", params=query)

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
            lines.append(
                f"**Category:** {p.get('category', '—')}  |  "
                f"**Reward types:** {', '.join(p.get('reward_types', []))}"
            )
            if p.get("description"):
                lines.append(p["description"])
            user_params = p.get("user_params", [])
            if user_params:
                lines.append("\n**Configurable parameters:**")
                for up in user_params:
                    req = " *(required)*" if up.get("required") else f" (default: `{up.get('default')}`)"
                    constraints = up.get("constraints", {})
                    cstr = ""
                    if constraints:
                        parts = [f"{k}: {v}" for k, v in constraints.items() if v is not None]
                        if parts:
                            cstr = f" — constraints: {', '.join(parts)}"
                    lines.append(f"- `{up['name']}` ({up['type']}){req}{cstr}: {up.get('description', '')}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        logger.error("list_policies failed: %s", e)
        return format_error(e)


async def qbrix_list_experiments(params: ListExperimentsInput, ctx: Context) -> str:
    """List experiments in the workspace with optional search and state filtering.

    Use this to survey what's running, find an experiment by name, or check which
    experiments are paused. Returns experiment IDs needed for monitoring and action tools.

    Args:
        params.search: partial name match
        params.enabled: true = running only, false = paused only, omit = all
        params.limit / params.offset: pagination

    Returns (markdown):
        Table with name, ID, policy, status, arm count, and gate info.
    """
    try:
        client = get_client(ctx)
        logger.debug("list_experiments search=%s enabled=%s", params.search, params.enabled)
        result = await client.experiment.list(
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
            lines.append(f"*More available — use offset={result.offset + result.limit} to paginate*")
        lines += ["", "| Name | ID | Policy | Status | Arms | Gate |", "|------|----|--------|--------|------|------|"]
        for e in result.items:
            status = "✓ running" if e.enabled else "⏸ paused"
            arm_count = len(e.pool.arms) if e.pool else "—"
            gate = f"{e.feature_gate.rollout_percentage}% rollout" if e.feature_gate else "—"
            lines.append(f"| {e.name} | `{e.id}` | {e.policy} | {status} | {arm_count} | {gate} |")
        return "\n".join(lines)
    except Exception as e:
        logger.error("list_experiments failed: %s", e)
        return format_error(e)


async def qbrix_list_pools(params: ListPoolsInput, ctx: Context) -> str:
    """List all arm pools in the workspace.

    Use this to discover existing pools before running a new experiment on them.
    Pools are reusable — the same variants can be tested with different policies.

    Returns (markdown):
        Each pool's name, ID, and arm names.
        Use a pool ID with qbrix_create_experiment_from_pool to reuse it.
    """
    try:
        client = get_client(ctx)
        logger.debug("list_pools limit=%s offset=%s", params.limit, params.offset)
        result = await client.pool.list(limit=params.limit, offset=params.offset)

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
            lines += [f"## {p.name}", f"**ID:** `{p.id}`", f"**Arms ({len(p.arms)}):** {arm_names}", ""]
        if result.has_more:
            lines.append(f"*More available — use offset={result.offset + result.limit} to paginate*")
        return "\n".join(lines)
    except Exception as e:
        logger.error("list_pools failed: %s", e)
        return format_error(e)


async def qbrix_get_pool(params: GetPoolInput, ctx: Context) -> str:
    """Get full details of a pool including all arms and their metadata payloads.

    Use this to inspect an existing pool before reusing it, or to look up arm IDs
    needed for gate rule configuration.

    Returns (markdown):
        Pool name, all arms with ID, index, active status, and metadata payload.
    """
    try:
        client = get_client(ctx)
        logger.debug("get_pool pool_id=%s", params.pool_id)
        pool = await client.pool.get(params.pool_id)

        if params.response_format == ResponseFormat.JSON:
            return pool.model_dump_json(indent=2)

        return "\n".join([f"# Pool: {pool.name}", f"**ID:** `{pool.id}`", "", fmt_arm_table(pool.arms)])
    except Exception as e:
        logger.error("get_pool pool_id=%s failed: %s", params.pool_id, e)
        return format_error(e)


def register(mcp: FastMCP) -> None:
    mcp.tool(name="qbrix_list_policies", annotations=READ_ONLY)(qbrix_list_policies)
    mcp.tool(name="qbrix_list_experiments", annotations=READ_ONLY)(qbrix_list_experiments)
    mcp.tool(name="qbrix_list_pools", annotations=READ_ONLY)(qbrix_list_pools)
    mcp.tool(name="qbrix_get_pool", annotations=READ_ONLY)(qbrix_get_pool)
