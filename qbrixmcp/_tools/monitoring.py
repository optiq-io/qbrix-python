from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.fastmcp import Context
from mcp.server.fastmcp import FastMCP

from qbrix.exception import QbrixAPIError
from qbrixmcp._models import GetExperimentInput
from qbrixmcp._models import GetGateInput
from qbrixmcp._models import GetStatsInput
from qbrixmcp._models import ResponseFormat
from qbrixmcp._utils import READ_ONLY
from qbrixmcp._utils import fmt_experiment
from qbrixmcp._utils import fmt_gate
from qbrixmcp._utils import format_error
from qbrixmcp._utils import get_client

logger = logging.getLogger(__name__)


async def qbrix_get_experiment(params: GetExperimentInput, ctx: Context) -> str:
    """Get full details of an experiment including its policy, arms, and gate configuration.

    Use this to inspect the current state before taking action, or to verify a setup
    completed correctly.

    Returns (markdown):
        Experiment config, policy and params, enabled state, pool with all arms,
        and gate configuration if present.
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


async def qbrix_get_gate(params: GetGateInput, ctx: Context) -> str:
    """Get the feature gate configuration for an experiment.

    Use this to inspect rollout %, targeting rules, and schedule before
    modifying a gate with qbrix_configure_gate.

    Returns (markdown):
        Rollout percentage, targeting rules in plain language, schedule,
        and active hours window.
    """
    try:
        client = get_client(ctx)
        logger.debug("get_gate experiment_id=%s", params.experiment_id)
        gate = await client.gate.get(params.experiment_id)

        if params.response_format == ResponseFormat.JSON:
            return gate.model_dump_json(indent=2)

        return "\n".join([
            f"# Gate: experiment `{params.experiment_id}`",
            f"*Last updated: {gate.updated_at or 'unknown'}  |  Version: {gate.version}*",
            "",
            fmt_gate(gate),
        ])
    except Exception as e:
        logger.error("get_gate experiment_id=%s failed: %s", params.experiment_id, e)
        return format_error(e)


async def qbrix_get_stats(params: GetStatsInput, ctx: Context) -> str:
    """Get performance statistics for an experiment including per-arm breakdown.

    Returns aggregate metrics and per-arm results showing which variants are winning.
    Use this to decide whether to continue, pause, or declare a winner.

    Requires Qbrix Enterprise Edition (EE) with analytics enabled.
    Optional time range filters scope the stats to a specific period.

    Args:
        params.experiment_id: experiment ID
        params.start_ms / params.end_ms: time window in epoch milliseconds

    Returns (markdown):
        Overview metrics (selections, feedback, rewards, default/gated traffic)
        and per-arm table sorted by avg reward descending.
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


def register(mcp: FastMCP) -> None:
    mcp.tool(name="qbrix_get_experiment", annotations=READ_ONLY)(qbrix_get_experiment)
    mcp.tool(name="qbrix_get_gate", annotations=READ_ONLY)(qbrix_get_gate)
    mcp.tool(name="qbrix_get_stats", annotations=READ_ONLY)(qbrix_get_stats)
