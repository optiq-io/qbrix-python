from __future__ import annotations

from typing import Any


class QbrixError(Exception):
    """base exception for all qbrix SDK errors."""


class QbrixAPIError(QbrixError):
    """error returned by the qbrix API."""

    status_code: int
    detail: str
    context: dict[str, Any] | None

    def __init__(
        self,
        status_code: int,
        detail: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.detail = detail
        self.context = context
        super().__init__(f"[{status_code}] {detail}")


class BadRequestError(QbrixAPIError):
    """400 — malformed request."""


class AuthenticationError(QbrixAPIError):
    """401 — invalid or missing credentials."""


class ForbiddenError(QbrixAPIError):
    """403 — insufficient permissions."""


class NotFoundError(QbrixAPIError):
    """404 — resource not found."""


class ConflictError(QbrixAPIError):
    """409 — resource conflict."""


class RateLimitedError(QbrixAPIError):
    """429 — rate limit exceeded."""

    retry_after: float | None

    def __init__(
        self,
        status_code: int,
        detail: str,
        context: dict[str, Any] | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(status_code, detail, context)
        self.retry_after = retry_after


class InternalServerError(QbrixAPIError):
    """500 — server error."""


class ServiceUnavailableError(QbrixAPIError):
    """503 — downstream service failure."""


class QbrixConnectionError(QbrixError):
    """failed to connect to the qbrix API."""


class QbrixTimeoutError(QbrixError):
    """request to the qbrix API timed out."""


STATUS_CODE_TO_EXCEPTION: dict[int, type[QbrixAPIError]] = {
    400: BadRequestError,
    401: AuthenticationError,
    403: ForbiddenError,
    404: NotFoundError,
    409: ConflictError,
    429: RateLimitedError,
    500: InternalServerError,
    503: ServiceUnavailableError,
}
