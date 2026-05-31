from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.fastmcp import Context
from mcp.server.fastmcp import FastMCP

from qbrix.exception import QbrixAPIError
from qbrixmcp._models import ConfigureGateInput
from qbrixmcp._models import CreateExperimentFromPoolInput
from qbrixmcp._models import CreatePoolInput
from qbrixmcp._models import ResponseFormat
from qbrixmcp._models import SetupExperimentInput
from qbrixmcp._utils import WRITE
from qbrixmcp._utils import WRITE_IDEMPOTENT
from qbrixmcp._utils import fmt_arm_table
from qbrixmcp._utils import fmt_gate
from qbrixmcp._utils import format_error
from qbrixmcp._utils import get_client

logger = logging.getLogger(__name__)


async def qbrix_setup_experiment(params: SetupExperimentInput, ctx: Context) -> str:
    """Create a new experiment from scratch — pool, experiment, and optional gate in one call.

    This is the primary setup tool. It creates the pool of arms, creates the experiment
    with the chosen policy, and optionally sets a traffic rollout gate — all atomically.
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

    Returns:
        Experiment ID and arm list for integration.
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


async def qbrix_configure_gate(params: ConfigureGateInput, ctx: Context) -> str:
    """Create or update (upsert) the feature gate for an experiment.

    Controls who enters the experiment: rollout percentage caps total traffic,
    targeting rules route specific user segments, and schedules restrict when
    the experiment runs. This tool is idempotent — call it to configure the gate
    whether or not one already exists, and again to update the configuration.

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
        params.rules: targeting rules, first match wins
        params.schedule_start/end: ISO 8601 datetimes for active window
        params.active_hours_start/end: HH:MM daily window
        params.default_arm_id: arm for users excluded by the gate
        params.timezone: for schedule and active hours (default UTC)

    Returns:
        Configured gate with full settings in plain-English summary.
    """
    try:
        client = get_client(ctx)
        logger.info("configure_gate experiment_id=%s rollout=%s rules=%d", params.experiment_id, params.rollout_percentage, len(params.rules))

        rules_data = [r.model_dump(exclude_none=True) for r in params.rules]
        gate_kwargs: dict[str, Any] = dict(rollout_percentage=params.rollout_percentage, rules=rules_data, timezone=params.timezone)
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
            gate = await client.gate.update(params.experiment_id, **gate_kwargs)
        except QbrixAPIError as api_err:
            if api_err.status_code == 404:
                gate = await client.gate.create(params.experiment_id, **gate_kwargs)
                logger.info("gate created (upsert) experiment_id=%s", params.experiment_id)
            else:
                raise

        if params.response_format == ResponseFormat.JSON:
            return gate.model_dump_json(indent=2)

        return "\n".join([f"# Gate Configured: experiment `{params.experiment_id}`", "", fmt_gate(gate)])
    except Exception as e:
        logger.error("configure_gate experiment_id=%s failed: %s", params.experiment_id, e)
        return format_error(e)


async def qbrix_create_pool(params: CreatePoolInput, ctx: Context) -> str:
    """Create a standalone pool of arms for reuse across multiple experiments.

    Pools are reusable — the same variants can be tested with different policies in
    separate experiments. Prefer qbrix_setup_experiment for the common case of
    creating a pool and experiment together.

    Args:
        params.name: pool name
        params.arms: arms with name and optional metadata payload

    Returns:
        Pool ID and arm IDs. Use the pool ID with qbrix_create_experiment_from_pool.
    """
    try:
        client = get_client(ctx)
        logger.info("create_pool name=%s arms=%d", params.name, len(params.arms))
        arms_data = [{"name": a.name, "metadata": a.metadata} for a in params.arms]
        pool = await client.pool.create(name=params.name, arms=arms_data)
        logger.info("pool created id=%s", pool.id)

        return "\n".join([
            f"# Pool Created: {pool.name}",
            f"**ID:** `{pool.id}`",
            "",
            fmt_arm_table(pool.arms),
            "",
            f'Use `pool_id: "{pool.id}"` with qbrix_create_experiment_from_pool to run an experiment on these arms.',
        ])
    except Exception as e:
        logger.error("create_pool name=%s failed: %s", params.name, e)
        return format_error(e)


def register(mcp: FastMCP) -> None:
    mcp.tool(name="qbrix_setup_experiment", annotations=WRITE)(qbrix_setup_experiment)
    mcp.tool(name="qbrix_create_experiment_from_pool", annotations=WRITE)(qbrix_create_experiment_from_pool)
    mcp.tool(name="qbrix_configure_gate", annotations=WRITE_IDEMPOTENT)(qbrix_configure_gate)
    mcp.tool(name="qbrix_create_pool", annotations=WRITE)(qbrix_create_pool)
