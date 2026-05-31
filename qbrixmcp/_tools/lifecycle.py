from __future__ import annotations

import json
import logging

from mcp.server.fastmcp import Context
from mcp.server.fastmcp import FastMCP

from qbrixmcp._models import ExperimentIdInput
from qbrixmcp._models import TuneExperimentInput
from qbrixmcp._utils import DESTRUCTIVE
from qbrixmcp._utils import WRITE
from qbrixmcp._utils import WRITE_IDEMPOTENT
from qbrixmcp._utils import format_error
from qbrixmcp._utils import get_client

logger = logging.getLogger(__name__)


async def qbrix_pause_experiment(params: ExperimentIdInput, ctx: Context) -> str:
    """Pause an experiment — stop traffic allocation while preserving learning state.

    The bandit's learned arm weights are kept. Resume at any time with
    qbrix_resume_experiment to continue from where it left off. Prefer this
    over deleting when you may want to resume or revisit the results later.
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
    """Update the policy parameters of a running experiment.

    Use this to tune exploration-exploitation trade-offs without stopping the experiment.
    Use qbrix_get_experiment first to see the current parameters before modifying them.

    Args:
        params.experiment_id: experiment ID
        params.policy_params: new policy parameters dict — replaces current params
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

    This is irreversible. The underlying pool and arms are NOT deleted and can be
    reused via qbrix_create_experiment_from_pool.

    Consider qbrix_pause_experiment instead if you may want to resume later.
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


async def qbrix_remove_gate(params: ExperimentIdInput, ctx: Context) -> str:
    """Remove the feature gate from an experiment.

    After removal, 100% of traffic passes to the bandit unconditionally —
    no rollout cap, no targeting rules, no schedule.
    Use qbrix_configure_gate to update settings instead of removing them.
    """
    try:
        client = get_client(ctx)
        logger.info("remove_gate experiment_id=%s", params.experiment_id)
        await client.gate.delete(params.experiment_id)
        return (
            f"gate removed from experiment `{params.experiment_id}`. "
            "100% of traffic now passes to the bandit unconditionally."
        )
    except Exception as e:
        logger.error("remove_gate experiment_id=%s failed: %s", params.experiment_id, e)
        return format_error(e)


def register(mcp: FastMCP) -> None:
    mcp.tool(name="qbrix_pause_experiment", annotations=WRITE_IDEMPOTENT)(qbrix_pause_experiment)
    mcp.tool(name="qbrix_resume_experiment", annotations=WRITE_IDEMPOTENT)(qbrix_resume_experiment)
    mcp.tool(name="qbrix_tune_experiment", annotations=WRITE)(qbrix_tune_experiment)
    mcp.tool(name="qbrix_delete_experiment", annotations=DESTRUCTIVE)(qbrix_delete_experiment)
    mcp.tool(name="qbrix_remove_gate", annotations=WRITE)(qbrix_remove_gate)
