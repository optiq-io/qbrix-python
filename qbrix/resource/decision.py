from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from qbrix.exception import BadGatewayError
from qbrix.exception import GatewayTimeoutError
from qbrix.exception import InternalServerError
from qbrix.exception import QbrixConnectionError
from qbrix.exception import QbrixTimeoutError
from qbrix.exception import RateLimitedError
from qbrix.exception import ServiceUnavailableError
from qbrix.model.common import Context
from qbrix.model.decision import Decision
from qbrix.model.decision import Outcome
from qbrix.model.decision import Settings
from qbrix.resource._base import AsyncAPIResource
from qbrix.resource._base import SyncAPIResource

# qbrix can't be reached, as opposed to a caller error (bad context, auth, an
# unknown loop), which raises: those are bugs to fix, never a silent offline.
_UNREACHABLE: tuple[type[Exception], ...] = (
    QbrixConnectionError,
    QbrixTimeoutError,
    RateLimitedError,
    InternalServerError,
    BadGatewayError,
    ServiceUnavailableError,
    GatewayTimeoutError,
)


def _settings(settings: Settings | dict[str, Any] | None) -> Settings:
    if settings is None:
        return Settings()
    if isinstance(settings, Settings):
        return settings
    return Settings.model_validate(settings)


def _select_body(loop: str, context: Context | dict[str, Any]) -> dict[str, Any]:
    if not isinstance(context, Context):
        context = Context.model_validate(context)
    return {"loop": loop, "context": context.model_dump(exclude_none=True)}


def _offline(settings: Settings) -> Decision:
    return Decision(option=settings.offline, request_id=None, reason="offline")


def _outcome_body(
    request_id: str, value: int | float, id: str | None, at: datetime | None
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "request_id": request_id,
        "value": value,
        "id": id or uuid.uuid4().hex,
    }
    if at is not None:
        body["at"] = at.isoformat()
    return body


class DecisionResource(SyncAPIResource):
    """the request path: select a loop's option, report its outcome."""

    def select(
        self,
        loop: str,
        context: Context | dict[str, Any],
        settings: Settings | dict[str, Any] | None = None,
    ) -> Decision:
        resolved = _settings(settings)
        body = _select_body(loop, context)
        try:
            return self._post(
                "/api/v1/select",
                body=body,
                cast_to=Decision,
                timeout=resolved.timeout,
                max_retries=resolved.max_retries,
            )
        except _UNREACHABLE:
            return _offline(resolved)

    def outcome(
        self,
        request_id: str | None,
        value: int | float,
        *,
        id: str | None = None,
        at: datetime | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> Outcome | None:
        if request_id is None:
            return None
        return self._post(
            "/api/v1/outcome",
            body=_outcome_body(request_id, value, id, at),
            cast_to=Outcome,
            timeout=timeout,
            max_retries=max_retries,
        )


class AsyncDecisionResource(AsyncAPIResource):
    """the request path: select a loop's option, report its outcome."""

    async def select(
        self,
        loop: str,
        context: Context | dict[str, Any],
        settings: Settings | dict[str, Any] | None = None,
    ) -> Decision:
        resolved = _settings(settings)
        body = _select_body(loop, context)
        try:
            return await self._post(
                "/api/v1/select",
                body=body,
                cast_to=Decision,
                timeout=resolved.timeout,
                max_retries=resolved.max_retries,
            )
        except _UNREACHABLE:
            return _offline(resolved)

    async def outcome(
        self,
        request_id: str | None,
        value: int | float,
        *,
        id: str | None = None,
        at: datetime | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> Outcome | None:
        if request_id is None:
            return None
        return await self._post(
            "/api/v1/outcome",
            body=_outcome_body(request_id, value, id, at),
            cast_to=Outcome,
            timeout=timeout,
            max_retries=max_retries,
        )
