"""Map grpc.StatusCode → existing Qbrix exception classes.

Mirrors the HTTP STATUS_CODE_TO_EXCEPTION table in qbrix.exception so that
callers can catch the same exception types regardless of transport.
"""

from __future__ import annotations

import grpc

from qbrix.exception import AuthenticationError
from qbrix.exception import BadRequestError
from qbrix.exception import ConflictError
from qbrix.exception import ForbiddenError
from qbrix.exception import InternalServerError
from qbrix.exception import NotFoundError
from qbrix.exception import QbrixAPIError
from qbrix.exception import QbrixConnectionError
from qbrix.exception import QbrixTimeoutError
from qbrix.exception import RateLimitedError
from qbrix.exception import ServiceUnavailableError

# Synthesized HTTP-style codes for the QbrixAPIError(status_code=...) field.
# Callers inspecting .status_code see the same values they'd get over HTTP.
_GRPC_TO_HTTP_STATUS: dict[grpc.StatusCode, int] = {
    grpc.StatusCode.INVALID_ARGUMENT: 400,
    grpc.StatusCode.UNAUTHENTICATED: 401,
    grpc.StatusCode.PERMISSION_DENIED: 403,
    grpc.StatusCode.NOT_FOUND: 404,
    grpc.StatusCode.ALREADY_EXISTS: 409,
    grpc.StatusCode.FAILED_PRECONDITION: 409,
    grpc.StatusCode.RESOURCE_EXHAUSTED: 429,
    grpc.StatusCode.INTERNAL: 500,
    grpc.StatusCode.UNAVAILABLE: 503,
    grpc.StatusCode.DEADLINE_EXCEEDED: 504,
}

_GRPC_TO_EXCEPTION: dict[grpc.StatusCode, type[QbrixAPIError]] = {
    grpc.StatusCode.INVALID_ARGUMENT: BadRequestError,
    grpc.StatusCode.UNAUTHENTICATED: AuthenticationError,
    grpc.StatusCode.PERMISSION_DENIED: ForbiddenError,
    grpc.StatusCode.NOT_FOUND: NotFoundError,
    grpc.StatusCode.ALREADY_EXISTS: ConflictError,
    grpc.StatusCode.FAILED_PRECONDITION: ConflictError,
    grpc.StatusCode.RESOURCE_EXHAUSTED: RateLimitedError,
    grpc.StatusCode.INTERNAL: InternalServerError,
    grpc.StatusCode.UNAVAILABLE: ServiceUnavailableError,
}

# Statuses that the retry loop should treat as transient. Matches the spirit
# of QbrixConfig.retry_on for HTTP (429, 502, 503, 504).
RETRYABLE_STATUSES: frozenset[grpc.StatusCode] = frozenset(
    {
        grpc.StatusCode.UNAVAILABLE,
        grpc.StatusCode.DEADLINE_EXCEEDED,
        grpc.StatusCode.RESOURCE_EXHAUSTED,
    }
)


def _extract_retry_after(rpc_error: grpc.RpcError) -> float | None:
    """Pull retry-after from trailing metadata if the server included it."""
    try:
        metadata = rpc_error.trailing_metadata() or ()
    except Exception:
        return None
    for key, value in metadata:
        if key.lower() == "retry-after":
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def make_grpc_error(rpc_error: grpc.RpcError) -> Exception:
    """Convert a grpc.RpcError to the matching Qbrix exception.

    Returns the new exception (caller decides whether to raise/from). Maps:
        - grpc.StatusCode.DEADLINE_EXCEEDED → QbrixTimeoutError
        - grpc.StatusCode.UNAVAILABLE w/ no useful code → QbrixConnectionError
          when the channel is uninitialized; otherwise ServiceUnavailableError
        - everything else → matching QbrixAPIError subclass, or generic
          QbrixAPIError if the status code is unknown.
    """
    try:
        code = rpc_error.code()
    except Exception:
        code = None
    try:
        details = rpc_error.details() or ""
    except Exception:
        details = str(rpc_error)

    if code is grpc.StatusCode.DEADLINE_EXCEEDED:
        return QbrixTimeoutError(details or "deadline exceeded")

    http_status = _GRPC_TO_HTTP_STATUS.get(code, 500) if code is not None else 500
    exc_cls = (
        _GRPC_TO_EXCEPTION.get(code, QbrixAPIError)
        if code is not None
        else QbrixAPIError
    )

    if exc_cls is RateLimitedError:
        return RateLimitedError(
            http_status, details, None, _extract_retry_after(rpc_error)
        )

    return exc_cls(http_status, details, None)


def is_retryable(rpc_error: grpc.RpcError) -> bool:
    try:
        return rpc_error.code() in RETRYABLE_STATUSES
    except Exception:
        return False


__all__ = [
    "RETRYABLE_STATUSES",
    "is_retryable",
    "make_grpc_error",
    "QbrixConnectionError",  # re-export for convenience
]
