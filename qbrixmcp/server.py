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
import logging
from contextlib import asynccontextmanager

from mcp.server.fastmcp import Context
from mcp.server.fastmcp import FastMCP

from qbrix import AsyncQbrix
from qbrixmcp._tools import agent
from qbrixmcp._tools import experiment
from qbrixmcp._tools import gate
from qbrixmcp._tools import policy
from qbrixmcp._tools import pool
from qbrixmcp._utils import get_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(server: FastMCP):  # noqa: ARG001
    logger.info("qbrix_mcp starting")
    client = AsyncQbrix()
    yield {"client": client}
    await client.close()
    logger.info("qbrix_mcp stopped")


mcp = FastMCP("qbrix_mcp", lifespan=lifespan)

policy.register(mcp)
pool.register(mcp)
experiment.register(mcp)
gate.register(mcp)
agent.register(mcp)


@mcp.resource("qbrix://policies")
async def policies_resource(ctx: Context) -> str:
    """All available bandit policies with configurable parameters."""
    client = get_client(ctx)
    data = await client.get("/api/v1/policies")
    return json.dumps(data, indent=2)


@mcp.resource("qbrix://experiments")
async def experiments_resource(ctx: Context) -> str:
    """Summary of all experiments in the workspace."""
    client = get_client(ctx)
    result = await client.experiment.list(limit=100)
    items = [e.model_dump(mode="json") for e in result.items]
    return json.dumps({"experiments": items, "total": len(items)}, indent=2)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
