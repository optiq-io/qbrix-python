from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.fastmcp import Context
from mcp.server.fastmcp import FastMCP

from qbrix.exception import QbrixAPIError
from qbrixmcp._models import CreateExperimentFromPoolInput
from qbrixmcp._models import ExperimentIdInput
from qbrixmcp._models import GetExperimentInput
from qbrixmcp._models import GetStatsInput
from qbrixmcp._models import ListExperimentsInput
from qbrixmcp._models import ResponseFormat
from qbrixmcp._models import SetupExperimentInput
from qbrixmcp._models import TuneExperimentInput
from qbrixmcp._utils import DESTRUCTIVE
from qbrixmcp._utils import READ_ONLY
from qbrixmcp._utils import WRITE
from qbrixmcp._utils import WRITE_IDEMPOTENT
from qbrixmcp._utils import fmt_arm_table
from qbrixmcp._utils import fmt_experiment
from qbrixmcp._utils import format_error
from qbrixmcp._utils import get_client

logger = logging.getLogger(__name__)


async def qbrix_setup_experiment(params: SetupExperimentInput, ctx: Context) -> str:
    """Create a new experiment from scratch — pool, experiment, and optional gate in one call.

    This is the primary setup tool. Creates the pool of arms, the experiment with the
    chosen policy, and optionally a traffic rollout gate — all atomically.
    Use this when you don't have an existing pool to reuse.

    Workflow:
        1. Use qbrix_list_policies to choose a policy
        2. Call this tool with arm names, metadata payloads, and policy
        3. Use the returned experiment_id in qbrix_select calls

    Args:
        params.name: experiment name
        params.arms: variants with name and optional metadata payload
        params.policy: policy name from qbrix_list_policies, or 'auto'
        params.policy_params: optional policy configuration
        params.enabled: start immediately (default true)
        params.rollout_percentage: if set, creates a gate limiting traffic to this %

    Returns:
        Experiment ID, pool ID, arm name→ID mapping, and integration guidance.
    """
    try:
        client = get_client(ctx)
        logger.info("setup_experiment name=%s policy=%s rollout=%s", params.name, params.policy, params.rollout_percentage)

        arms_data = [{"name": a.name, "metadata": a.metadata} for a in params.arms]
        pool = await client.pool.create(name=params.name, arms=arms_data)
        logger.info("pool created id=%s", pool.id)

        experiment = await client.experiment.create(
            name=params.name,
            pool_id=pool.id,
            policy=params.policy,
            policy_params=params.policy_params,
            enabled=params.enabled,
        )
        logger.info("experiment created id=%s", experiment.id)

        gate = None
        if params.rollout_percentage is not None:
            gate = await client.gate.create(experiment.id, rollout_percentage=params.rollout_percentage)
            logger.info("gate created experiment_id=%s rollout=%s", experiment.id, params.rollout_percentage)

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
            fmt_arm_table(pool.arms),
        ]
        if gate:
            lines += ["", f"## Gate: {gate.rollout_percentage}% traffic rollout active"]
        lines += [
            "",
            "## Integration",
            "```python",
            f'response = client.agent.select("{experiment.id}", context={{"id": user_id}})',
            "arm = response.arm  # arm.name or arm.metadata to render the variant",
            "client.agent.feedback(response.request_id, reward=1.0)",
            "```",
            "",
            "**Arm IDs (for gate rules):**",
        ]
        for name, arm_id in arm_map.items():
            lines.append(f"- `{name}`: `{arm_id}`")
        return "\n".join(lines)
    except Exception as e:
        logger.error("setup_experiment name=%s failed: %s", params.name, e)
        return format_error(e)


async def qbrix_create_experiment_from_pool(params: CreateExperimentFromPoolInput, ctx: Context) -> str:
    """Create a new experiment using an existing pool of arms.

    Use this when you already have a pool and want to run a new experiment on the same
    variants — to compare policies or restart after deleting a previous experiment.
    Use qbrix_list_pools or qbrix_get_pool first to find the pool ID.

    Args:
        params.name: experiment name
        params.pool_id: ID of the existing pool
        params.policy: policy name — use qbrix_list_policies
        params.policy_params: optional policy configuration
        params.enabled: start immediately (default true)
    """
    try:
        client = get_client(ctx)
        logger.info("create_experiment_from_pool name=%s pool_id=%s policy=%s", params.name, params.pool_id, params.policy)
        experiment = await client.experiment.create(
            name=params.name,
            pool_id=params.pool_id,
            policy=params.policy,
            policy_params=params.policy_params,
            enabled=params.enabled,
        )
        logger.info("experiment created id=%s", experiment.id)

        lines = [
            f"# Experiment Created: {experiment.name}",
            "",
            f"**Experiment ID:** `{experiment.id}`",
            f"**Pool ID:** `{params.pool_id}`",
            f"**Policy:** {experiment.policy}",
            f"**Status:** {'✓ running' if experiment.enabled else '⏸ paused'}",
        ]
        if experiment.pool:
            lines += ["", "## Arms", fmt_arm_table(experiment.pool.arms)]
        lines.append("\nUse qbrix_configure_gate to set rollout percentage or targeting rules.")
        return "\n".join(lines)
    except Exception as e:
        logger.error("create_experiment_from_pool name=%s failed: %s", params.name, e)
        return format_error(e)


async def qbrix_list_experiments(params: ListExperimentsInput, ctx: Context) -> str:
    """List experiments in the workspace with optional search and state filtering.

    Use this to survey what's running, find an experiment by name, or check which
    experiments are paused. Returns experiment IDs needed for other tools.

    Args:
        params.search: partial name match
        params.enabled: true = running only, false = paused only, omit = all
        params.limit / params.offset: pagination
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


async def qbrix_get_experiment(params: GetExperimentInput, ctx: Context) -> str:
    """Get full details of an experiment including its policy, arms, and gate configuration.

    Use this to inspect the current state before taking action, or to verify a setup
    completed correctly.
    """
    try:
        client = get_client(ctx)
        logger.debug("get_experiment id=%s", params.experiment_id)
        experiment = await client.experiment.get(params.experiment_id)

        if params.response_format == ResponseFormat.JSON:
            return experiment.model_dump_json(indent=2)
        return fmt_experiment(experiment)
    except Exception as e:
        logger.error("get_experiment id=%s failed: %s", params.experiment_id, e)
        return format_error(e)


async def qbrix_get_stats(params: GetStatsInput, ctx: Context) -> str:
    """Get performance statistics for an experiment including per-arm breakdown.

    Returns aggregate metrics and per-arm results showing which variants are winning.
    Use this to decide whether to continue, pause, or declare a winner.

    Requires Qbrix Enterprise Edition (EE) with analytics enabled.

    Args:
        params.experiment_id: experiment ID
        params.start_ms / params.end_ms: time window in epoch milliseconds
    """
    try:
        client = get_client(ctx)
        logger.debug("get_stats id=%s start_ms=%s end_ms=%s", params.experiment_id, params.start_ms, params.end_ms)

        query: dict[str, Any] = {}
        if params.start_ms is not None:
            query["start_ms"] = params.start_ms
        if params.end_ms is not None:
            query["end_ms"] = params.end_ms

        overview = await client.get(f"/api/v1/ee/insight/experiment/{params.experiment_id}", params=query)

        arms: list[dict[str, Any]] = []
        try:
            arm_data = await client.get(f"/api/v1/ee/insight/experiment/{params.experiment_id}/arms", params=query)
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
            lines += ["", "## Per-Arm Performance", "| Arm | Selections | Feedback | Avg Reward |", "|-----|-----------|---------|------------|"]
            for arm in sorted(arms, key=lambda a: a.get("avg_reward") or 0, reverse=True):
                avg = arm.get("avg_reward")
                avg_str = f"{avg:.4f}" if avg is not None else "—"
                lines.append(
                    f"| {arm.get('arm_name', '?')} | {arm.get('selections', 0):,} | "
                    f"{arm.get('feedback_count', 0):,} | {avg_str} |"
                )
        return "\n".join(lines)
    except Exception as e:
        logger.error("get_stats id=%s failed: %s", params.experiment_id, e)
        return format_error(e)


async def qbrix_pause_experiment(params: ExperimentIdInput, ctx: Context) -> str:
    """Pause an experiment — stop traffic allocation while preserving learning state.

    The bandit's learned arm weights are kept intact. Resume at any time with
    qbrix_resume_experiment. Prefer this over deleting when you may want to resume later.
    """
    try:
        client = get_client(ctx)
        logger.info("pause_experiment id=%s", params.experiment_id)
        await client.experiment.update(params.experiment_id, enabled=False)
        return f"experiment `{params.experiment_id}` paused. learning state preserved. use qbrix_resume_experiment to restart."
    except Exception as e:
        logger.error("pause_experiment id=%s failed: %s", params.experiment_id, e)
        return format_error(e)


async def qbrix_resume_experiment(params: ExperimentIdInput, ctx: Context) -> str:
    """Resume a paused experiment — re-enable traffic allocation.

    Picks up from the existing learned arm weights. Gate configuration is unchanged.
    """
    try:
        client = get_client(ctx)
        logger.info("resume_experiment id=%s", params.experiment_id)
        await client.experiment.update(params.experiment_id, enabled=True)
        return f"experiment `{params.experiment_id}` resumed and running."
    except Exception as e:
        logger.error("resume_experiment id=%s failed: %s", params.experiment_id, e)
        return format_error(e)


async def qbrix_tune_experiment(params: TuneExperimentInput, ctx: Context) -> str:
    """Update the policy parameters of a running or paused experiment.

    Use this to adjust exploration-exploitation trade-offs without stopping the experiment.
    Use qbrix_get_experiment first to inspect the current parameters.

    Args:
        params.experiment_id: experiment ID
        params.policy_params: new parameters dict — replaces current params entirely
    """
    try:
        client = get_client(ctx)
        logger.info("tune_experiment id=%s params=%s", params.experiment_id, params.policy_params)
        experiment = await client.experiment.update(params.experiment_id, policy_params=params.policy_params)
        return (
            f"experiment `{experiment.id}` updated.\n"
            f"**Policy:** {experiment.policy}\n"
            f"**New params:** `{json.dumps(experiment.policy_params)}`"
        )
    except Exception as e:
        logger.error("tune_experiment id=%s failed: %s", params.experiment_id, e)
        return format_error(e)


async def qbrix_delete_experiment(params: ExperimentIdInput, ctx: Context) -> str:
    """Permanently delete an experiment and its learned parameter state.

    Irreversible. The underlying pool and arms are NOT deleted.
    Consider qbrix_pause_experiment if you may want to resume later.
    """
    try:
        client = get_client(ctx)
        logger.info("delete_experiment id=%s", params.experiment_id)
        await client.experiment.delete(params.experiment_id)
        return (
            f"experiment `{params.experiment_id}` permanently deleted. "
            "the pool and arms are still available for new experiments."
        )
    except Exception as e:
        logger.error("delete_experiment id=%s failed: %s", params.experiment_id, e)
        return format_error(e)


def register(mcp: FastMCP) -> None:
    mcp.tool(name="qbrix_setup_experiment", annotations=WRITE)(qbrix_setup_experiment)
    mcp.tool(name="qbrix_create_experiment_from_pool", annotations=WRITE)(qbrix_create_experiment_from_pool)
    mcp.tool(name="qbrix_list_experiments", annotations=READ_ONLY)(qbrix_list_experiments)
    mcp.tool(name="qbrix_get_experiment", annotations=READ_ONLY)(qbrix_get_experiment)
    mcp.tool(name="qbrix_get_stats", annotations=READ_ONLY)(qbrix_get_stats)
    mcp.tool(name="qbrix_pause_experiment", annotations=WRITE_IDEMPOTENT)(qbrix_pause_experiment)
    mcp.tool(name="qbrix_resume_experiment", annotations=WRITE_IDEMPOTENT)(qbrix_resume_experiment)
    mcp.tool(name="qbrix_tune_experiment", annotations=WRITE)(qbrix_tune_experiment)
    mcp.tool(name="qbrix_delete_experiment", annotations=DESTRUCTIVE)(qbrix_delete_experiment)
