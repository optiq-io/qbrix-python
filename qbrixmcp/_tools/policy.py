from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.fastmcp import Context
from mcp.server.fastmcp import FastMCP

from qbrixmcp._models import ListPoliciesInput
from qbrixmcp._models import ResponseFormat
from qbrixmcp._utils import READ_ONLY
from qbrixmcp._utils import format_error
from qbrixmcp._utils import get_client

logger = logging.getLogger(__name__)


async def qbrix_list_policies(params: ListPoliciesInput, ctx: Context) -> str:
    """List all available bandit policies with parameters and reward type compatibility.

    Use this before creating an experiment to choose the right policy.
    Filter by reward_type to see only compatible policies.

    Policy categories:
    - stochastic: BetaTSPolicy (binary), GaussianTSPolicy (continuous), UCB1TunedPolicy,
      KLUCBPolicy, EpsilonPolicy, MOSSPolicy — no per-selection features
    - contextual: LinUCBPolicy, LinTSPolicy — need features per selection, sent as
      context.properties against the experiment's declared context_schema
    - adversarial: EXP3Policy, FPLPolicy — robust to non-stationary environments
    - auto: qbrix selects and tunes a policy automatically (MetaBandit)

    Args:
        params.reward_type: 'binary', 'bounded', or 'continuous'
        params.response_format: 'markdown' (default) or 'json'
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


def register(mcp: FastMCP) -> None:
    mcp.tool(name="qbrix_list_policies", annotations=READ_ONLY)(qbrix_list_policies)
