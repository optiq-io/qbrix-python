from __future__ import annotations

import logging
from unittest.mock import patch

import httpx
import pytest

from qbrix._base_client import AsyncAPIClient
from qbrix._base_client import SyncAPIClient
from qbrix._version import __version__
from qbrix.exception import AuthenticationError
from qbrix.exception import BadGatewayError
from qbrix.exception import NotFoundError
from qbrix.exception import QbrixConnectionError
from qbrix.exception import QbrixTimeoutError
from qbrix.exception import RateLimitedError
from qbrix.exception import ServiceUnavailableError
from qbrix.exception import UnprocessableEntityError


@pytest.mark.unit
class TestBuildHeaders:
    def test_with_api_key(self) -> None:
        client = SyncAPIClient(api_key="optiq_test_key", max_retries=0)
        headers = client._build_headers()
        assert headers["X-API-Key"] == "optiq_test_key"
        assert headers["Accept"] == "application/json"
        assert headers["Content-Type"] == "application/json"
        assert headers["User-Agent"] == f"qbrix-python/{__version__}"
        client.close()

    def test_without_api_key(self) -> None:
        client = SyncAPIClient(max_retries=0)
        headers = client._build_headers()
        assert "X-API-Key" not in headers
        assert "User-Agent" in headers
        client.close()


@pytest.mark.unit
class TestMakeStatusError:
    def test_success_no_error(self) -> None:
        response = httpx.Response(200, json={"ok": True})
        assert response.is_success

    def test_404_returns_not_found(self) -> None:
        client = SyncAPIClient(api_key="optiq_test", max_retries=0)
        response = httpx.Response(404, json={"detail": "experiment not found"})
        err = client._make_status_error(response)
        assert isinstance(err, NotFoundError)
        assert err.status_code == 404
        assert err.detail == "experiment not found"
        client.close()

    def test_401_returns_authentication_error(self) -> None:
        client = SyncAPIClient(api_key="optiq_test", max_retries=0)
        response = httpx.Response(401, json={"detail": "invalid api key"})
        err = client._make_status_error(response)
        assert isinstance(err, AuthenticationError)
        client.close()

    def test_429_with_retry_after(self) -> None:
        client = SyncAPIClient(api_key="optiq_test", max_retries=0)
        response = httpx.Response(
            429,
            json={"detail": "rate limited"},
            headers={"Retry-After": "30"},
        )
        err = client._make_status_error(response)
        assert isinstance(err, RateLimitedError)
        assert err.retry_after == 30.0
        client.close()

    def test_429_without_retry_after(self) -> None:
        client = SyncAPIClient(api_key="optiq_test", max_retries=0)
        response = httpx.Response(429, json={"detail": "rate limited"})
        err = client._make_status_error(response)
        assert isinstance(err, RateLimitedError)
        assert err.retry_after is None
        client.close()

    def test_non_json_body(self) -> None:
        client = SyncAPIClient(api_key="optiq_test", max_retries=0)
        response = httpx.Response(500, text="Internal Server Error")
        err = client._make_status_error(response)
        assert err.status_code == 500
        client.close()

    def test_context_field(self) -> None:
        client = SyncAPIClient(api_key="optiq_test", max_retries=0)
        response = httpx.Response(
            409,
            json={
                "detail": "pool has experiments",
                "context": {"experiments": ["exp-1"]},
            },
        )
        err = client._make_status_error(response)
        assert err.context == {"experiments": ["exp-1"]}
        client.close()

    def test_422_flattens_fastapis_validation_list(self) -> None:
        # 422s bypass the proxy's {code, detail, context} envelope — FastAPI's
        # own handler sends detail as a list of per-field dicts.
        client = SyncAPIClient(api_key="optiq_test", max_retries=0)
        errors = [
            {
                "loc": ["body", "rollout_percentage"],
                "msg": "input should be less than or equal to 100",
                "type": "less_than_equal",
            },
            {"loc": ["body", "policy"], "msg": "field required", "type": "missing"},
        ]
        response = httpx.Response(422, json={"detail": errors})
        err = client._make_status_error(response)

        assert isinstance(err, UnprocessableEntityError)
        assert err.status_code == 422
        assert isinstance(err.detail, str)
        assert "rollout_percentage: input should be less than or equal to 100" in (
            err.detail
        )
        assert "policy: field required" in err.detail
        # the raw list stays reachable for callers that want the structure
        assert err.context is not None
        assert err.context["errors"] == errors
        client.close()

    def test_422_with_a_plain_string_detail_is_left_alone(self) -> None:
        client = SyncAPIClient(api_key="optiq_test", max_retries=0)
        response = httpx.Response(422, json={"detail": "unprocessable"})
        err = client._make_status_error(response)
        assert isinstance(err, UnprocessableEntityError)
        assert err.detail == "unprocessable"
        client.close()


@pytest.mark.unit
class TestRetryDelay:
    def test_exponential_growth(self) -> None:
        client = SyncAPIClient(
            api_key="optiq_test",
            retry_base_delay=0.5,
            retry_max_delay=30.0,
        )
        d0 = client._calculate_retry_delay(0)
        d1 = client._calculate_retry_delay(1)
        d2 = client._calculate_retry_delay(2)
        assert d0 < d1 < d2
        client.close()

    def test_capped_at_max(self) -> None:
        client = SyncAPIClient(
            api_key="optiq_test",
            retry_base_delay=10.0,
            retry_max_delay=15.0,
        )
        delay = client._calculate_retry_delay(10)
        assert delay <= 15.0 * 1.1  # max + jitter
        client.close()

    def test_retry_after_header_used(self) -> None:
        client = SyncAPIClient(
            api_key="optiq_test",
            retry_base_delay=0.5,
            retry_max_delay=120.0,
        )
        exc = RateLimitedError(429, "rate limited", retry_after=45.0)
        delay = client._calculate_retry_delay(0, exc=exc)
        assert delay == 45.0
        client.close()

    def test_retry_after_capped_at_max(self) -> None:
        client = SyncAPIClient(
            api_key="optiq_test",
            retry_base_delay=0.5,
            retry_max_delay=30.0,
        )
        exc = RateLimitedError(429, "rate limited", retry_after=999.0)
        delay = client._calculate_retry_delay(0, exc=exc)
        assert delay == 30.0
        client.close()

    def test_no_retry_after_uses_backoff(self) -> None:
        client = SyncAPIClient(
            api_key="optiq_test",
            retry_base_delay=1.0,
            retry_max_delay=30.0,
        )
        exc = RateLimitedError(429, "rate limited", retry_after=None)
        delay = client._calculate_retry_delay(0, exc=exc)
        assert delay >= 1.0
        client.close()


@pytest.mark.unit
class TestSyncAPIClient:
    def test_success_json(self) -> None:
        client = SyncAPIClient(api_key="optiq_test", max_retries=0)
        mock_response = httpx.Response(200, json={"id": "p1", "name": "test"})
        with patch.object(client._client, "request", return_value=mock_response):
            result = client.request("GET", "/api/v1/pools/p1")
        assert result == {"id": "p1", "name": "test"}
        client.close()

    def test_204_returns_empty(self) -> None:
        client = SyncAPIClient(api_key="optiq_test", max_retries=0)
        mock_response = httpx.Response(204)
        with patch.object(client._client, "request", return_value=mock_response):
            result = client.request("DELETE", "/api/v1/pools/p1")
        assert result == {}
        client.close()

    def test_404_raises(self) -> None:
        client = SyncAPIClient(api_key="optiq_test", max_retries=0)
        mock_response = httpx.Response(404, json={"detail": "not found"})
        with patch.object(client._client, "request", return_value=mock_response):
            with pytest.raises(NotFoundError):
                client.request("GET", "/api/v1/pools/nope")
        client.close()

    def test_connect_error_wraps(self) -> None:
        client = SyncAPIClient(api_key="optiq_test", max_retries=0)
        with patch.object(
            client._client,
            "request",
            side_effect=httpx.ConnectError("connection refused"),
        ):
            with pytest.raises(QbrixConnectionError):
                client.request("GET", "/api/v1/pools")
        client.close()

    def test_timeout_wraps(self) -> None:
        client = SyncAPIClient(api_key="optiq_test", max_retries=0)
        with patch.object(
            client._client,
            "request",
            side_effect=httpx.ReadTimeout("read timed out"),
        ):
            with pytest.raises(QbrixTimeoutError):
                client.request("GET", "/api/v1/pools")
        client.close()

    def test_retry_on_503(self) -> None:
        client = SyncAPIClient(
            api_key="optiq_test",
            max_retries=2,
            retry_base_delay=0.0,
            retry_max_delay=0.0,
        )
        fail = httpx.Response(503, json={"detail": "unavailable"})
        ok = httpx.Response(200, json={"status": "ok"})
        with patch.object(client._client, "request", side_effect=[fail, fail, ok]):
            result = client.request("GET", "/health")
        assert result == {"status": "ok"}
        client.close()

    def test_retry_exhausted_raises(self) -> None:
        client = SyncAPIClient(
            api_key="optiq_test",
            max_retries=1,
            retry_base_delay=0.0,
            retry_max_delay=0.0,
        )
        fail = httpx.Response(503, json={"detail": "unavailable"})
        with patch.object(client._client, "request", side_effect=[fail, fail]):
            with pytest.raises(ServiceUnavailableError):
                client.request("GET", "/health")
        client.close()

    def test_no_retry_on_400(self) -> None:
        client = SyncAPIClient(api_key="optiq_test", max_retries=0)
        mock_response = httpx.Response(400, json={"detail": "bad request"})
        with patch.object(
            client._client, "request", return_value=mock_response
        ) as mock_req:
            with pytest.raises(Exception):
                client.request("POST", "/api/v1/pools", body={})
            assert mock_req.call_count == 1
        client.close()

    def test_502_raises_bad_gateway(self) -> None:
        client = SyncAPIClient(api_key="optiq_test", max_retries=0)
        mock_response = httpx.Response(502, json={"detail": "bad gateway"})
        with patch.object(client._client, "request", return_value=mock_response):
            with pytest.raises(BadGatewayError):
                client.request("GET", "/api/v1/pools")
        client.close()

    def test_debug_logging_on_request(self, caplog: pytest.LogCaptureFixture) -> None:
        client = SyncAPIClient(api_key="optiq_test", max_retries=0)
        mock_response = httpx.Response(200, json={"ok": True})
        with caplog.at_level(logging.DEBUG, logger="qbrix"):
            with patch.object(client._client, "request", return_value=mock_response):
                client.request("GET", "/api/v1/pools")
        assert any(
            "GET" in r.message and "/api/v1/pools" in r.message for r in caplog.records
        )
        client.close()


@pytest.mark.unit
@pytest.mark.asyncio
class TestAsyncAPIClient:
    async def test_success_json(self) -> None:
        client = AsyncAPIClient(api_key="optiq_test", max_retries=0)
        mock_response = httpx.Response(200, json={"id": "p1"})
        with patch.object(client._client, "request", return_value=mock_response):
            result = await client.request("GET", "/api/v1/pools/p1")
        assert result == {"id": "p1"}
        await client.close()

    async def test_204_returns_empty(self) -> None:
        client = AsyncAPIClient(api_key="optiq_test", max_retries=0)
        mock_response = httpx.Response(204)
        with patch.object(client._client, "request", return_value=mock_response):
            result = await client.request("DELETE", "/api/v1/pools/p1")
        assert result == {}
        await client.close()

    async def test_404_raises(self) -> None:
        client = AsyncAPIClient(api_key="optiq_test", max_retries=0)
        mock_response = httpx.Response(404, json={"detail": "not found"})
        with patch.object(client._client, "request", return_value=mock_response):
            with pytest.raises(NotFoundError):
                await client.request("GET", "/api/v1/pools/nope")
        await client.close()

    async def test_connect_error_wraps(self) -> None:
        client = AsyncAPIClient(api_key="optiq_test", max_retries=0)
        with patch.object(
            client._client,
            "request",
            side_effect=httpx.ConnectError("refused"),
        ):
            with pytest.raises(QbrixConnectionError):
                await client.request("GET", "/api/v1/pools")
        await client.close()

    async def test_timeout_wraps(self) -> None:
        client = AsyncAPIClient(api_key="optiq_test", max_retries=0)
        with patch.object(
            client._client,
            "request",
            side_effect=httpx.ReadTimeout("timed out"),
        ):
            with pytest.raises(QbrixTimeoutError):
                await client.request("GET", "/api/v1/pools")
        await client.close()

    async def test_retry_on_503(self) -> None:
        client = AsyncAPIClient(
            api_key="optiq_test",
            max_retries=2,
            retry_base_delay=0.0,
            retry_max_delay=0.0,
        )
        fail = httpx.Response(503, json={"detail": "unavailable"})
        ok = httpx.Response(200, json={"status": "ok"})
        with patch.object(client._client, "request", side_effect=[fail, fail, ok]):
            result = await client.request("GET", "/health")
        assert result == {"status": "ok"}
        await client.close()
