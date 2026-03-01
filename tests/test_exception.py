from __future__ import annotations

import pytest

from qbrix.exception import AuthenticationError
from qbrix.exception import BadRequestError
from qbrix.exception import ConflictError
from qbrix.exception import ForbiddenError
from qbrix.exception import InternalServerError
from qbrix.exception import NotFoundError
from qbrix.exception import QbrixAPIError
from qbrix.exception import QbrixConnectionError
from qbrix.exception import QbrixError
from qbrix.exception import QbrixTimeoutError
from qbrix.exception import RateLimitedError
from qbrix.exception import ServiceUnavailableError
from qbrix.exception import STATUS_CODE_TO_EXCEPTION


@pytest.mark.unit
class TestExceptionHierarchy:
    def test_all_api_errors_inherit_from_qbrix_error(self) -> None:
        for exc_cls in STATUS_CODE_TO_EXCEPTION.values():
            assert issubclass(exc_cls, QbrixError)
            assert issubclass(exc_cls, QbrixAPIError)

    def test_connection_and_timeout_inherit_from_qbrix_error(self) -> None:
        assert issubclass(QbrixConnectionError, QbrixError)
        assert issubclass(QbrixTimeoutError, QbrixError)

    def test_connection_and_timeout_not_api_errors(self) -> None:
        assert not issubclass(QbrixConnectionError, QbrixAPIError)
        assert not issubclass(QbrixTimeoutError, QbrixAPIError)


@pytest.mark.unit
class TestQbrixAPIError:
    def test_attributes(self) -> None:
        err = QbrixAPIError(500, "something broke", {"key": "val"})
        assert err.status_code == 500
        assert err.detail == "something broke"
        assert err.context == {"key": "val"}

    def test_str_format(self) -> None:
        err = NotFoundError(404, "experiment not found")
        assert str(err) == "[404] experiment not found"

    def test_context_defaults_to_none(self) -> None:
        err = BadRequestError(400, "bad input")
        assert err.context is None


@pytest.mark.unit
class TestRateLimitedError:
    def test_retry_after(self) -> None:
        err = RateLimitedError(429, "too many requests", retry_after=60.0)
        assert err.retry_after == 60.0
        assert err.status_code == 429

    def test_retry_after_none(self) -> None:
        err = RateLimitedError(429, "too many requests")
        assert err.retry_after is None


@pytest.mark.unit
class TestStatusCodeMapping:
    @pytest.mark.parametrize(
        "code,expected_cls",
        [
            (400, BadRequestError),
            (401, AuthenticationError),
            (403, ForbiddenError),
            (404, NotFoundError),
            (409, ConflictError),
            (429, RateLimitedError),
            (500, InternalServerError),
            (503, ServiceUnavailableError),
        ],
    )
    def test_mapping(
        self, code: int, expected_cls: type[QbrixAPIError]
    ) -> None:
        assert STATUS_CODE_TO_EXCEPTION[code] is expected_cls

    def test_unknown_status_falls_back(self) -> None:
        assert 418 not in STATUS_CODE_TO_EXCEPTION
