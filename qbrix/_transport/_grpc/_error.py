"""Map grpc.StatusCode → existing Qbrix exception classes.

Mirrors the HTTP STATUS_CODE_TO_EXCEPTION table in qbrix.exception so that
callers can catch the same exception types regardless of transport.
"""

from __future__ import annotations

import re

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

# The proxy's TokenExpiredException subclasses DeadlineExceededException, so an
# expired feedback token arrives as DEADLINE_EXCEEDED with a fixed "token
# expired" detail (transport/grpc/exception/base.py). Retrying it can never
# help — the token is stale, not the deadline.
_TOKEN_EXPIRED_RE = re.compile(r"token expired", re.IGNORECASE)


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
        - grpc.StatusCode.UNIMPLEMENTED → QbrixConnectionError when the peer
          replied with HTTP instead of gRPC (wrong base_url); else a 501 error
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
        # The proxy reuses DEADLINE_EXCEEDED for an expired feedback token
        # (mod/agent/token.py TokenExpiredError → TokenExpiredException), which
        # is a business-level 400 the HTTP transport surfaces as
        # BadRequestError — not an RPC that ran out of time. Disambiguate on
        # the details text so callers catch the same class either way.
        if _TOKEN_EXPIRED_RE.search(details):
            return BadRequestError(400, details, None)
        return QbrixTimeoutError(details or "deadline exceeded")

    if code is grpc.StatusCode.UNIMPLEMENTED:
        # grpc-core reports UNIMPLEMENTED with a "Received http2 header with
        # status: NNN" detail when the peer answered with a plain HTTP response
        # instead of gRPC — i.e. base_url points at an HTTP/REST server or a
        # CDN/proxy that doesn't carry gRPC, not at a gRPC server.
        if "Received http2 header with status" in details:
            return QbrixConnectionError(
                f"gRPC call failed: {details}. The endpoint replied with HTTP, "
                "not gRPC — check base_url. gRPC needs a gRPC server address "
                "(e.g. grpc://host:50050); an HTTP/REST URL or a CDN-fronted "
                "host will not work. Use transport='http' for HTTP endpoints."
            )
        return QbrixAPIError(501, details or "RPC not implemented by the server", None)

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
        if rpc_error.code() not in RETRYABLE_STATUSES:
            return False
    except Exception:
        return False
    # An expired feedback token rides in on DEADLINE_EXCEEDED but is terminal —
    # retrying burns the budget on a token that can never be accepted.
    try:
        return not _TOKEN_EXPIRED_RE.search(rpc_error.details() or "")
    except Exception:
        return True


__all__ = [
    "RETRYABLE_STATUSES",
    "is_retryable",
    "make_grpc_error",
    "QbrixConnectionError",  # re-export for convenience
]
