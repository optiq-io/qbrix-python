from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.fastmcp import Context
from mcp.server.fastmcp import FastMCP

from qbrixmcp._models import FeedbackInput
from qbrixmcp._models import SelectInput
from qbrixmcp._utils import READ_ONLY
from qbrixmcp._utils import WRITE
from qbrixmcp._utils import format_error
from qbrixmcp._utils import get_client

logger = logging.getLogger(__name__)


async def qbrix_select(params: SelectInput, ctx: Context) -> str:
    """Select an arm (variant) for a given context — the core bandit call.

    Call this before acting. The bandit evaluates the feature gate (if configured),
    then selects the best arm based on learned reward distributions. The returned
    request_id must be passed unchanged to qbrix_feedback after observing the outcome.

    Selection loop:
        1. Call qbrix_select → get arm + request_id
        2. Use arm_name or arm_metadata to render the variant or take the action
        3. Observe the outcome (click, conversion, revenue, etc.)
        4. Call qbrix_feedback(request_id, reward) to close the learning loop

    Note: is_default=true means the gate committed a specific arm. Feedback is still
    accepted and tracked but does not affect arm weights.

    Note: context_vector is required for contextual policies (LinUCBPolicy, LinTSPolicy).
    Length must match the experiment's 'dim' policy param.

    Returns:
        JSON with arm_name, arm_id, arm_index, request_id, is_default.
    """
    try:
        client = get_client(ctx)
        logger.debug("select experiment_id=%s context_id=%s", params.experiment_id, params.context_id)

        context: dict[str, Any] = {"id": params.context_id}
        if params.context_vector is not None:
            context["vector"] = params.context_vector
        if params.context_metadata is not None:
            context["metadata"] = params.context_metadata

        result = await client.agent.select(experiment_id=params.experiment_id, context=context)
        return json.dumps(
            {
                "arm_name": result.arm.name,
                "arm_id": result.arm.id,
                "arm_index": result.arm.index,
                "request_id": result.request_id,
                "is_default": result.is_default,
            },
            indent=2,
        )
    except Exception as e:
        logger.error("select experiment_id=%s failed: %s", params.experiment_id, e)
        return format_error(e)


async def qbrix_feedback(params: FeedbackInput, ctx: Context) -> str:
    """Submit a reward signal for a previous selection — closes the learning loop.

    Call this after observing the outcome of a qbrix_select call. The reward teaches
    the bandit which arms perform better so future selections improve.

    The request_id is an HMAC-signed token — pass it exactly as returned by qbrix_select.

    Reward values by policy type:
        BetaTSPolicy (binary): 1.0 (success) or 0.0 (failure)
        GaussianTSPolicy (continuous): actual metric value e.g. 42.5 for $42.50
        UCB1TunedPolicy, EpsilonPolicy etc: typically 0.0–1.0 but unbounded

    Returns:
        JSON with accepted=true on success.
    """
    try:
        client = get_client(ctx)
        logger.debug("feedback request_id=%s reward=%s", params.request_id, params.reward)
        await client.agent.feedback(request_id=params.request_id, reward=params.reward)
        return json.dumps({"accepted": True})
    except Exception as e:
        logger.error("feedback request_id=%s failed: %s", params.request_id, e)
        return format_error(e)


def register(mcp: FastMCP) -> None:
    mcp.tool(name="qbrix_select", annotations=READ_ONLY)(qbrix_select)
    mcp.tool(name="qbrix_feedback", annotations=WRITE)(qbrix_feedback)
