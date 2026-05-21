from __future__ import annotations

import pytest

pytest.importorskip("grpc", reason="install qbrix[grpc] to run gRPC tests")

import grpc

from qbrix._transport._grpc._error import is_retryable
from qbrix._transport._grpc._error import make_grpc_error
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

pytestmark = pytest.mark.grpc


class _FakeRpcError(grpc.RpcError):
    """Stand-in for grpc.RpcError that the make_grpc_error helper can introspect."""

    def __init__(
        self,
        code: grpc.StatusCode,
        details: str = "",
        trailing_metadata: tuple = (),
    ) -> None:
        self._code = code
        self._details = details
        self._metadata = trailing_metadata

    def code(self) -> grpc.StatusCode:
        return self._code

    def details(self) -> str:
        return self._details

    def trailing_metadata(self) -> tuple:
        return self._metadata


class TestErrorMapping:
    @pytest.mark.parametrize(
        "code,expected_cls,expected_status",
        [
            (grpc.StatusCode.INVALID_ARGUMENT, BadRequestError, 400),
            (grpc.StatusCode.UNAUTHENTICATED, AuthenticationError, 401),
            (grpc.StatusCode.PERMISSION_DENIED, ForbiddenError, 403),
            (grpc.StatusCode.NOT_FOUND, NotFoundError, 404),
            (grpc.StatusCode.ALREADY_EXISTS, ConflictError, 409),
            (grpc.StatusCode.FAILED_PRECONDITION, ConflictError, 409),
            (grpc.StatusCode.RESOURCE_EXHAUSTED, RateLimitedError, 429),
            (grpc.StatusCode.INTERNAL, InternalServerError, 500),
            (grpc.StatusCode.UNAVAILABLE, ServiceUnavailableError, 503),
        ],
    )
    def test_status_mapping(
        self,
        code: grpc.StatusCode,
        expected_cls: type[QbrixAPIError],
        expected_status: int,
    ) -> None:
        exc = make_grpc_error(_FakeRpcError(code, "boom"))
        assert isinstance(exc, expected_cls)
        assert exc.status_code == expected_status
        assert "boom" in exc.detail

    def test_deadline_exceeded_returns_timeout_error(self) -> None:
        exc = make_grpc_error(_FakeRpcError(grpc.StatusCode.DEADLINE_EXCEEDED, "slow"))
        assert isinstance(exc, QbrixTimeoutError)
        assert "slow" in str(exc)

    def test_rate_limited_retry_after_from_metadata(self) -> None:
        exc = make_grpc_error(
            _FakeRpcError(
                grpc.StatusCode.RESOURCE_EXHAUSTED,
                "throttled",
                trailing_metadata=(("retry-after", "7.5"),),
            )
        )
        assert isinstance(exc, RateLimitedError)
        assert exc.retry_after == 7.5

    def test_rate_limited_without_retry_after(self) -> None:
        exc = make_grpc_error(
            _FakeRpcError(grpc.StatusCode.RESOURCE_EXHAUSTED, "throttled")
        )
        assert isinstance(exc, RateLimitedError)
        assert exc.retry_after is None

    def test_unknown_status_falls_back_to_generic(self) -> None:
        # CANCELLED isn't in our table; expect the generic 500 fallback.
        exc = make_grpc_error(_FakeRpcError(grpc.StatusCode.CANCELLED, "cancelled"))
        assert type(exc) is QbrixAPIError
        assert exc.status_code == 500

    def test_unimplemented_http_endpoint_gives_connection_hint(self) -> None:
        # grpc-core's tell that base_url points at an HTTP endpoint, not gRPC.
        exc = make_grpc_error(
            _FakeRpcError(
                grpc.StatusCode.UNIMPLEMENTED,
                "Received http2 header with status: 404",
            )
        )
        assert isinstance(exc, QbrixConnectionError)
        assert "not gRPC" in str(exc)
        assert "transport='http'" in str(exc)

    def test_unimplemented_missing_method_maps_to_501(self) -> None:
        # A real gRPC server that simply lacks the RPC.
        exc = make_grpc_error(
            _FakeRpcError(grpc.StatusCode.UNIMPLEMENTED, "Method not found")
        )
        assert type(exc) is QbrixAPIError
        assert exc.status_code == 501


class TestRetryability:
    @pytest.mark.parametrize(
        "code,retryable",
        [
            (grpc.StatusCode.UNAVAILABLE, True),
            (grpc.StatusCode.DEADLINE_EXCEEDED, True),
            (grpc.StatusCode.RESOURCE_EXHAUSTED, True),
            (grpc.StatusCode.NOT_FOUND, False),
            (grpc.StatusCode.INVALID_ARGUMENT, False),
            (grpc.StatusCode.UNAUTHENTICATED, False),
        ],
    )
    def test_is_retryable(self, code: grpc.StatusCode, retryable: bool) -> None:
        assert is_retryable(_FakeRpcError(code)) is retryable
