from __future__ import annotations

from typing import Any

from qbrix.resource._base import AsyncAPIResource
from qbrix.resource._base import SyncAPIResource
from qbrix.exception import BadGatewayError
from qbrix.exception import GatewayTimeoutError
from qbrix.exception import InternalServerError
from qbrix.exception import QbrixConnectionError
from qbrix.exception import QbrixTimeoutError
from qbrix.exception import RateLimitedError
from qbrix.exception import ServiceUnavailableError
from qbrix.model.agent import SelectedArm
from qbrix.model.agent import SelectResponse
from qbrix.model.common import Context

# Failures that mean "the proxy is unreachable or unhealthy right now", as
# opposed to a caller error (bad request, auth, not found, ...). select()
# only falls back to a caller-declared arm for these — never for errors that
# indicate the request itself was wrong, since silently swallowing those
# would hide real bugs behind a fabricated selection.
_AVAILABILITY_ERRORS: tuple[type[Exception], ...] = (
    QbrixConnectionError,
    QbrixTimeoutError,
    RateLimitedError,
    InternalServerError,
    BadGatewayError,
    ServiceUnavailableError,
    GatewayTimeoutError,
)


def _build_context(context: Context | dict[str, Any]) -> dict[str, Any]:
    # dicts go through the model too, so a raw-dict caller gets the same
    # validation as a typed one — notably the vector/properties guard.
    if not isinstance(context, Context):
        context = Context.model_validate(context)
    return context.model_dump(exclude_none=True)


def _resolve_fallback(fallback: SelectedArm | dict[str, Any]) -> SelectResponse:
    arm = (
        fallback
        if isinstance(fallback, SelectedArm)
        else SelectedArm.model_validate(fallback)
    )
    # request_id=None mirrors the proxy's own paused-experiment response: no
    # server-minted token exists for this arm, so feedback() must not send one.
    return SelectResponse(arm=arm, request_id=None, is_default=True, is_fallback=True)


class AgentResource(SyncAPIResource):
    """synchronous agent operations (select / feedback)."""

    def select(
        self,
        experiment_id: str,
        context: Context | dict[str, Any],
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        fallback: SelectedArm | dict[str, Any] | None = None,
    ) -> SelectResponse:
        body = {
            "experiment_id": experiment_id,
            "context": _build_context(context),
        }
        try:
            return self._post(
                "/api/v1/agent/select",
                body=body,
                cast_to=SelectResponse,
                timeout=timeout,
                max_retries=max_retries,
            )
        except _AVAILABILITY_ERRORS:
            if fallback is None:
                raise
            return _resolve_fallback(fallback)

    def feedback(
        self,
        request_id: str | None,
        reward: int | float,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        # A null request_id means select() minted no token — a paused
        # experiment, or a client-side fallback. Nothing valid to feed back.
        if not request_id:
            return
        self._post(
            "/api/v1/agent/feedback",
            body={"request_id": request_id, "reward": reward},
            timeout=timeout,
            max_retries=max_retries,
        )


class AsyncAgentResource(AsyncAPIResource):
    """asynchronous agent operations (select / feedback)."""

    async def select(
        self,
        experiment_id: str,
        context: Context | dict[str, Any],
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        fallback: SelectedArm | dict[str, Any] | None = None,
    ) -> SelectResponse:
        body = {
            "experiment_id": experiment_id,
            "context": _build_context(context),
        }
        try:
            return await self._post(
                "/api/v1/agent/select",
                body=body,
                cast_to=SelectResponse,
                timeout=timeout,
                max_retries=max_retries,
            )
        except _AVAILABILITY_ERRORS:
            if fallback is None:
                raise
            return _resolve_fallback(fallback)

    async def feedback(
        self,
        request_id: str | None,
        reward: int | float,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        if not request_id:
            return
        await self._post(
            "/api/v1/agent/feedback",
            body={"request_id": request_id, "reward": reward},
            timeout=timeout,
            max_retries=max_retries,
        )
