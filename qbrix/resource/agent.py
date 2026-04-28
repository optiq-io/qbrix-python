from __future__ import annotations

from typing import Any

from qbrix.resource._base import AsyncAPIResource
from qbrix.resource._base import SyncAPIResource
from qbrix.model.agent import SelectResponse
from qbrix.model.common import Context


def _build_context(context: Context | dict[str, Any]) -> dict[str, Any]:
    if isinstance(context, Context):
        return context.model_dump(exclude_none=True)
    return context


class AgentResource(SyncAPIResource):
    """synchronous agent operations (select / feedback)."""

    def select(
        self,
        experiment_id: str,
        context: Context | dict[str, Any],
    ) -> SelectResponse:
        body = {
            "experiment_id": experiment_id,
            "context": _build_context(context),
        }
        return self._post("/api/v1/agent/select", body=body, cast_to=SelectResponse)

    def feedback(
        self,
        request_id: str,
        reward: int | float,
    ) -> None:
        self._post(
            "/api/v1/agent/feedback",
            body={"request_id": request_id, "reward": reward},
        )


class AsyncAgentResource(AsyncAPIResource):
    """asynchronous agent operations (select / feedback)."""

    async def select(
        self,
        experiment_id: str,
        context: Context | dict[str, Any],
    ) -> SelectResponse:
        body = {
            "experiment_id": experiment_id,
            "context": _build_context(context),
        }
        return await self._post(
            "/api/v1/agent/select", body=body, cast_to=SelectResponse
        )

    async def feedback(
        self,
        request_id: str,
        reward: int | float,
    ) -> None:
        await self._post(
            "/api/v1/agent/feedback",
            body={"request_id": request_id, "reward": reward},
        )
