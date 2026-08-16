from __future__ import annotations

import logging
from typing import Any

from mcp.server.fastmcp import Context
from mcp.server.fastmcp import FastMCP

from qbrix.exception import QbrixAPIError
from qbrixmcp._models import ConfigureGateInput
from qbrixmcp._models import ExperimentIdInput
from qbrixmcp._models import GetGateInput
from qbrixmcp._models import ResponseFormat
from qbrixmcp._utils import READ_ONLY
from qbrixmcp._utils import WRITE
from qbrixmcp._utils import WRITE_IDEMPOTENT
from qbrixmcp._utils import fmt_gate
from qbrixmcp._utils import format_error
from qbrixmcp._utils import get_client

logger = logging.getLogger(__name__)


async def qbrix_configure_gate(params: ConfigureGateInput, ctx: Context) -> str:
    """Create or update the feature gate for an experiment.

    Controls who enters the experiment: rollout percentage caps total traffic,
    targeting rules route specific segments, and schedules restrict when the
    experiment runs.

    Only the arguments you pass are written — everything else on the gate is
    left as it is. To raise a rollout, pass `rollout_percentage` alone; the
    default arm, targeting rules and schedule are kept. If no gate exists yet,
    one is created and the arguments you did not pass take their defaults.

    Gate rule examples:
        # Only premium users
        rules=[{"key": "plan", "operator": "eq", "value": "premium"}]
        # US and Canada only
        rules=[{"key": "country", "operator": "in", "value": ["US", "CA"]}]
        # Route new users to a specific arm
        rules=[{"key": "user_type", "operator": "eq", "value": "new", "arm_name": "onboarding"}]

    Args:
        params.experiment_id: experiment to configure
        params.enabled: whether the gate is active
        params.rollout_percentage: % of traffic to include
        params.rules: targeting rules, first match wins — replaces the whole list
        params.schedule_start/end: ISO 8601 datetimes for active window
        params.active_hours_start/end: HH:MM daily window
        params.default_arm_id: arm for users excluded by the gate
        params.timezone: for schedule and active hours
    """
    try:
        client = get_client(ctx)
        logger.info(
            "configure_gate experiment_id=%s rollout=%s rules=%s",
            params.experiment_id,
            params.rollout_percentage,
            "unchanged" if params.rules is None else len(params.rules),
        )

        gate_kwargs: dict[str, Any] = {}
        for name in (
            "enabled",
            "rollout_percentage",
            "schedule_start",
            "schedule_end",
            "active_hours_start",
            "active_hours_end",
            "default_arm_id",
            "timezone",
        ):
            value = getattr(params, name)
            if value is not None:
                gate_kwargs[name] = value
        if params.rules is not None:
            gate_kwargs["rules"] = [
                r.model_dump(exclude_none=True) for r in params.rules
            ]

        if not gate_kwargs:
            return format_error(
                ValueError(
                    "nothing to configure — pass at least one gate field, or use "
                    "qbrix_get_gate to read the current configuration"
                )
            )

        try:
            gate = await client.gate.update(params.experiment_id, **gate_kwargs)
        except QbrixAPIError as api_err:
            if api_err.status_code == 404:
                gate = await client.gate.create(params.experiment_id, **gate_kwargs)
                logger.info("gate created experiment_id=%s", params.experiment_id)
            else:
                raise

        if params.response_format == ResponseFormat.JSON:
            return gate.model_dump_json(indent=2)

        return "\n".join(
            [
                f"# Gate Configured: experiment `{params.experiment_id}`",
                "",
                fmt_gate(gate),
            ]
        )
    except Exception as e:
        logger.error(
            "configure_gate experiment_id=%s failed: %s", params.experiment_id, e
        )
        return format_error(e)


async def qbrix_get_gate(params: GetGateInput, ctx: Context) -> str:
    """Get the feature gate configuration for an experiment.

    Use this to inspect rollout %, targeting rules, and schedule before
    modifying with qbrix_configure_gate.
    """
    try:
        client = get_client(ctx)
        logger.debug("get_gate experiment_id=%s", params.experiment_id)
        gate = await client.gate.get(params.experiment_id)

        if params.response_format == ResponseFormat.JSON:
            return gate.model_dump_json(indent=2)

        return "\n".join(
            [
                f"# Gate: experiment `{params.experiment_id}`",
                f"*Last updated: {gate.updated_at or 'unknown'}  |  Version: {gate.version}*",
                "",
                fmt_gate(gate),
            ]
        )
    except Exception as e:
        logger.error("get_gate experiment_id=%s failed: %s", params.experiment_id, e)
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
    mcp.tool(name="qbrix_configure_gate", annotations=WRITE_IDEMPOTENT)(
        qbrix_configure_gate
    )
    mcp.tool(name="qbrix_get_gate", annotations=READ_ONLY)(qbrix_get_gate)
    mcp.tool(name="qbrix_remove_gate", annotations=WRITE)(qbrix_remove_gate)
