from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

from qbrix import AsyncQbrix
from qbrix.exception import QbrixAPIError
from qbrix.exception import QbrixConnectionError
from qbrix.exception import QbrixTimeoutError


READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)
WRITE_IDEMPOTENT = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True)


def get_client(ctx: Context) -> AsyncQbrix:
    return ctx.request_context.lifespan_context["client"]


def format_error(e: Exception) -> str:
    if isinstance(e, QbrixAPIError):
        status = e.status_code
        detail = e.detail
        if status == 401:
            return f"error: authentication failed — check QBRIX_API_KEY. detail: {detail}"
        if status == 403:
            return f"error: insufficient permissions. detail: {detail}"
        if status == 404:
            return f"error: resource not found. detail: {detail}"
        if status == 409:
            return f"error: conflict — resource may already exist. detail: {detail}"
        if status == 422:
            return f"error: invalid parameters — {detail}"
        if status == 429:
            return "error: rate limit exceeded. wait before retrying."
        return f"error: API returned {status}. detail: {detail}"
    if isinstance(e, QbrixConnectionError):
        return "error: cannot connect to qbrix API. check QBRIX_BASE_URL and that proxysvc is running."
    if isinstance(e, QbrixTimeoutError):
        return "error: request timed out. check that qbrix proxysvc is running."
    return f"error: {type(e).__name__}: {e}"


def fmt_gate(gate: Any) -> str:
    lines = [
        f"- **Rollout:** {gate.rollout_percentage}% of traffic",
        f"- **Gate enabled:** {'yes' if gate.enabled else 'no'}",
    ]
    if gate.default_arm_name:
        lines.append(f"- **Default arm** (users outside rollout): {gate.default_arm_name}")
    if gate.schedule_start or gate.schedule_end:
        lines.append(f"- **Schedule:** {gate.schedule_start or 'any'} → {gate.schedule_end or 'any'} ({gate.timezone})")
    if gate.active_hours_start:
        lines.append(f"- **Active hours:** {gate.active_hours_start}–{gate.active_hours_end} ({gate.timezone})")
    if gate.rules:
        lines.append(f"- **Targeting rules** ({len(gate.rules)}):")
        for r in gate.rules:
            target = f" → arm '{r.arm_name or r.arm_id}'" if (r.arm_name or r.arm_id) else ""
            lines.append(f"  - `{r.key}` {r.operator} `{r.value}`{target}")
    return "\n".join(lines)


def fmt_experiment(exp: Any) -> str:
    status = "✓ running" if exp.enabled else "⏸ paused"
    lines = [
        f"# Experiment: {exp.name}",
        f"**ID:** `{exp.id}`  |  **Status:** {status}  |  **Policy:** {exp.policy}",
    ]
    if exp.policy_params:
        lines.append(f"**Policy params:** `{json.dumps(exp.policy_params)}`")
    if exp.meta_experiment_id:
        lines.append(f"**Meta-experiment** (auto policy, learner of `{exp.meta_experiment_id}`)")
    if exp.pool:
        lines.append(f"\n**Pool:** {exp.pool.name} (`{exp.pool_id}`)")
        lines.append("\n" + fmt_arm_table(exp.pool.arms))
    if exp.feature_gate:
        lines.append("\n**Feature gate:**")
        lines.append(fmt_gate(exp.feature_gate))
    return "\n".join(lines)


def fmt_arm_table(arms: list[Any]) -> str:
    rows = ["| # | Arm | ID | Active | Metadata |", "|---|-----|----|--------|----------|"]
    for arm in arms:
        meta = json.dumps(arm.metadata) if arm.metadata else ""
        active = "✓" if arm.is_active else "✗"
        rows.append(f"| {arm.index} | {arm.name} | `{arm.id}` | {active} | {meta} |")
    return "\n".join(rows)
