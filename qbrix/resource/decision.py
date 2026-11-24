from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from typing import Iterable

from qbrix.exception import STATUS_CODE_TO_EXCEPTION
from qbrix.exception import BadGatewayError
from qbrix.exception import GatewayTimeoutError
from qbrix.exception import InternalServerError
from qbrix.exception import QbrixAPIError
from qbrix.exception import QbrixConnectionError
from qbrix.exception import QbrixError
from qbrix.exception import QbrixTimeoutError
from qbrix.exception import RateLimitedError
from qbrix.exception import ServiceUnavailableError
from qbrix.model.common import Context
from qbrix.model.decision import Decision
from qbrix.model.decision import Outcome
from qbrix.model.decision import Settings
from qbrix.model.decision import TrackEvent
from qbrix.model.decision import Tracked
from qbrix.model.decision import TrackResult
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


TRACK_BATCH_MAX = 500

_TRACK_ERROR_STATUS = {
    "INVALID_DECISIONS": 400,
    "INVALID_OUTCOME": 400,
    "METRIC_NOT_FOUND": 404,
}

# (index in the caller's events, the event's body as sent)
_Chunk = list[tuple[int, dict[str, Any]]]


def _track_body(event: TrackEvent | dict[str, Any]) -> dict[str, Any] | None:
    """the event as sent, its id minted once so retries reuse it; None when it
    has neither decisions nor a unit, so nothing could credit it."""
    if not isinstance(event, TrackEvent):
        event = TrackEvent.model_validate(event)
    decisions = event.decisions or None
    if decisions is None and event.unit is None:
        return None
    body: dict[str, Any] = {
        "metric": event.metric,
        "value": event.value,
        "id": event.id or uuid.uuid4().hex,
    }
    if decisions is not None:
        body["decisions"] = decisions
    if event.unit is not None:
        body["unit"] = event.unit
    if event.at is not None:
        body["at"] = event.at.isoformat()
    return body


def _track_chunks(
    events: Iterable[TrackEvent | dict[str, Any]],
) -> tuple[list[TrackResult | None], list[_Chunk]]:
    bodies = [_track_body(event) for event in events]
    sent = [(i, body) for i, body in enumerate(bodies) if body is not None]
    chunks = [
        sent[start : start + TRACK_BATCH_MAX]
        for start in range(0, len(sent), TRACK_BATCH_MAX)
    ]
    return [None] * len(bodies), chunks


def _batch_body(chunk: _Chunk) -> dict[str, Any]:
    return {"events": [body for _, body in chunk]}


def _track_error(error: dict[str, Any]) -> QbrixAPIError:
    code = error.get("code")
    status = _TRACK_ERROR_STATUS.get(code or "", 500)
    error_cls = STATUS_CODE_TO_EXCEPTION.get(status, QbrixAPIError)
    return error_cls(status, error.get("detail", ""), code=code)


def _settle(results: list[TrackResult | None], chunk: _Chunk, answer: Any) -> None:
    wire = answer.get("results") if isinstance(answer, dict) else None
    if not isinstance(wire, list) or len(wire) != len(chunk):
        raise QbrixError("qbrix: track answered a different number of events")
    for (i, body), result in zip(chunk, wire):
        if result.get("error"):
            results[i] = TrackResult(id=body["id"], error=_track_error(result["error"]))
        else:
            results[i] = TrackResult(
                id=body["id"], at=result.get("at"), credited=result.get("credited")
            )


def _fail(results: list[TrackResult | None], chunk: _Chunk, error: QbrixError) -> None:
    for i, body in chunk:
        results[i] = TrackResult(id=body["id"], error=error)


class DecisionResource(SyncAPIResource):
    """the request path: select a loop's option, report its outcome, track events."""

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

    def track(
        self,
        metric: str,
        value: int | float,
        *,
        decisions: str | None = None,
        unit: str | None = None,
        id: str | None = None,
        at: datetime | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> Tracked | None:
        body = _track_body(
            TrackEvent(
                metric=metric,
                value=value,
                decisions=decisions,
                unit=unit,
                id=id,
                at=at,
            )
        )
        if body is None:
            return None
        return self._post(
            "/api/v1/track",
            body=body,
            cast_to=Tracked,
            timeout=timeout,
            max_retries=max_retries,
        )

    def track_many(
        self,
        events: Iterable[TrackEvent | dict[str, Any]],
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> list[TrackResult | None]:
        results, chunks = _track_chunks(events)
        for chunk in chunks:
            try:
                answer = self._post(
                    "/api/v1/track",
                    body=_batch_body(chunk),
                    timeout=timeout,
                    max_retries=max_retries,
                )
                _settle(results, chunk, answer)
            except QbrixError as error:
                _fail(results, chunk, error)
        return results


class AsyncDecisionResource(AsyncAPIResource):
    """the request path: select a loop's option, report its outcome, track events."""

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

    async def track(
        self,
        metric: str,
        value: int | float,
        *,
        decisions: str | None = None,
        unit: str | None = None,
        id: str | None = None,
        at: datetime | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> Tracked | None:
        body = _track_body(
            TrackEvent(
                metric=metric,
                value=value,
                decisions=decisions,
                unit=unit,
                id=id,
                at=at,
            )
        )
        if body is None:
            return None
        return await self._post(
            "/api/v1/track",
            body=body,
            cast_to=Tracked,
            timeout=timeout,
            max_retries=max_retries,
        )

    async def track_many(
        self,
        events: Iterable[TrackEvent | dict[str, Any]],
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> list[TrackResult | None]:
        results, chunks = _track_chunks(events)
        for chunk in chunks:
            try:
                answer = await self._post(
                    "/api/v1/track",
                    body=_batch_body(chunk),
                    timeout=timeout,
                    max_retries=max_retries,
                )
                _settle(results, chunk, answer)
            except QbrixError as error:
                _fail(results, chunk, error)
        return results
