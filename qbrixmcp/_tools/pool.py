from __future__ import annotations

import logging

from mcp.server.fastmcp import Context
from mcp.server.fastmcp import FastMCP

from qbrixmcp._models import CreatePoolInput
from qbrixmcp._models import GetPoolInput
from qbrixmcp._models import ListPoolsInput
from qbrixmcp._models import ResponseFormat
from qbrixmcp._utils import READ_ONLY
from qbrixmcp._utils import WRITE
from qbrixmcp._utils import fmt_arm_table
from qbrixmcp._utils import format_error
from qbrixmcp._utils import get_client

logger = logging.getLogger(__name__)


async def qbrix_list_pools(params: ListPoolsInput, ctx: Context) -> str:
    """List all arm pools in the workspace.

    Use this to discover existing pools before running a new experiment on them.
    Pools are reusable — the same variants can be tested with different policies.

    Returns (markdown):
        Each pool's name, ID, and arm names.
        Use pool_id with qbrix_create_experiment_from_pool to reuse it.
    """
    import json

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

    Use this to inspect an existing pool before reusing it in a new experiment,
    or to look up arm IDs needed for gate rule configuration.

    Returns (markdown):
        Pool name, all arms with ID, index, active status, and metadata.
    """
    try:
        client = get_client(ctx)
        logger.debug("get_pool id=%s", params.pool_id)
        pool = await client.pool.get(params.pool_id)

        if params.response_format == ResponseFormat.JSON:
            return pool.model_dump_json(indent=2)

        return "\n".join([f"# Pool: {pool.name}", f"**ID:** `{pool.id}`", "", fmt_arm_table(pool.arms)])
    except Exception as e:
        logger.error("get_pool id=%s failed: %s", params.pool_id, e)
        return format_error(e)


async def qbrix_create_pool(params: CreatePoolInput, ctx: Context) -> str:
    """Create a standalone pool of arms for reuse across multiple experiments.

    Pools are reusable — the same variants can be tested with different policies.
    Prefer qbrix_setup_experiment for the common case of creating pool and experiment together.

    Args:
        params.name: pool name
        params.arms: arms with name and optional metadata payload

    Returns:
        Pool ID and arm IDs for use with qbrix_create_experiment_from_pool.
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
    mcp.tool(name="qbrix_list_pools", annotations=READ_ONLY)(qbrix_list_pools)
    mcp.tool(name="qbrix_get_pool", annotations=READ_ONLY)(qbrix_get_pool)
    mcp.tool(name="qbrix_create_pool", annotations=WRITE)(qbrix_create_pool)
