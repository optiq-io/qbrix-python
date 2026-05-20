"""HTTP transport for the qbrix SDK (httpx-based).

Moved from ``qbrix._base_client``. The old module remains as a back-compat
shim re-exporting these symbols. New code should import from
``qbrix._transport._http`` directly.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any
from typing import TypeVar

import httpx
from pydantic import BaseModel

from qbrix._config import QbrixConfig
from qbrix._transport._base import AsyncTransport
from qbrix._transport._base import Transport
from qbrix._version import __version__
from qbrix.exception import QbrixAPIError
from qbrix.exception import QbrixConnectionError
from qbrix.exception import QbrixTimeoutError
from qbrix.exception import RateLimitedError
from qbrix.exception import STATUS_CODE_TO_EXCEPTION

_T = TypeVar("_T", bound=BaseModel)
_log = logging.getLogger("qbrix")


class BaseClient:
    _config: QbrixConfig

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        **kwargs: Any,
    ) -> None:
        overrides: dict[str, Any] = {}
        if api_key is not None:
            overrides["api_key"] = api_key
        if base_url is not None:
            overrides["base_url"] = base_url
        if timeout is not None:
            overrides["timeout"] = timeout
        if max_retries is not None:
            overrides["max_retries"] = max_retries
        overrides.update(kwargs)
        self._config = QbrixConfig(**overrides)

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": f"qbrix-python/{__version__}",
        }
        if self._config.api_key:
            headers["X-API-Key"] = self._config.api_key
        return headers

    @staticmethod
    def _make_status_error(response: httpx.Response) -> QbrixAPIError:
        detail = ""
        context = None
        try:
            body = response.json()
            detail = body.get("detail", response.text)
            context = body.get("context")
        except Exception:  # noqa
            detail = response.text

        status = response.status_code
        exc_cls = STATUS_CODE_TO_EXCEPTION.get(status, QbrixAPIError)

        if exc_cls is RateLimitedError:
            retry_after_raw = response.headers.get("Retry-After")
            retry_after = float(retry_after_raw) if retry_after_raw else None
            return RateLimitedError(status, detail, context, retry_after)

        return exc_cls(status, detail, context)

    def _should_retry(self, response: httpx.Response) -> bool:
        return response.status_code in self._config.retry_on

    def _calculate_retry_delay(
        self, attempt: int, exc: QbrixAPIError | None = None
    ) -> float:
        if isinstance(exc, RateLimitedError) and exc.retry_after:
            return min(exc.retry_after, self._config.retry_max_delay)
        delay = self._config.retry_base_delay * (2**attempt)
        delay = min(delay, self._config.retry_max_delay)
        return delay + random.uniform(0, delay * 0.1)


class HTTPTransport(BaseClient, Transport):
    """Synchronous HTTP transport. Implements the ``Transport`` protocol."""

    _client: httpx.Client

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        limits = httpx.Limits(
            max_connections=self._config.max_connections,
            max_keepalive_connections=self._config.max_keepalive_connections,
        )
        self._client = httpx.Client(
            base_url=self._config.base_url,
            headers=self._build_headers(),
            timeout=self._config.timeout,
            http2=self._config.http2,
            limits=limits,
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
    ) -> _T | dict[str, Any]:
        last_exc: QbrixAPIError | None = None
        max_attempts = self._config.max_retries + 1

        for attempt in range(max_attempts):
            _log.debug("%s %s attempt=%d/%d", method, path, attempt + 1, max_attempts)
            try:
                response = self._client.request(method, path, json=body, params=params)
            except httpx.ConnectError as exc:
                raise QbrixConnectionError(str(exc)) from exc
            except httpx.TimeoutException as exc:
                raise QbrixTimeoutError(str(exc)) from exc

            if response.is_success:
                _log.debug("%s %s → %d", method, path, response.status_code)
                if response.status_code == 204 or not response.content:
                    return cast_to.model_validate({}) if cast_to else {}
                data = response.json()
                return cast_to.model_validate(data) if cast_to else data

            if not self._should_retry(response):
                raise self._make_status_error(response)

            last_exc = self._make_status_error(response)

            if attempt < self._config.max_retries:
                delay = self._calculate_retry_delay(attempt, last_exc)
                _log.debug(
                    "%s %s retrying in %.2fs (attempt %d/%d)",
                    method,
                    path,
                    delay,
                    attempt + 1,
                    self._config.max_retries,
                )
                time.sleep(delay)

        _log.debug("%s %s failed after %d attempts", method, path, max_attempts)
        if last_exc:
            raise last_exc

        return {}

    def get(
        self,
        path: str,
        *,
        cast_to: type[_T] | None = None,
        params: dict[str, Any] | None = None,
    ) -> _T | dict[str, Any]:
        return self.request("GET", path, cast_to=cast_to, params=params)

    def post(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
    ) -> _T | dict[str, Any]:
        return self.request("POST", path, body=body, cast_to=cast_to)

    def put(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
    ) -> _T | dict[str, Any]:
        return self.request("PUT", path, body=body, cast_to=cast_to)

    def patch(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
    ) -> _T | dict[str, Any]:
        return self.request("PATCH", path, body=body, cast_to=cast_to)

    def delete(self, path: str) -> None:
        self.request("DELETE", path)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HTTPTransport:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class AsyncHTTPTransport(BaseClient, AsyncTransport):
    """Asynchronous HTTP transport. Implements the ``AsyncTransport`` protocol."""

    _client: httpx.AsyncClient

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        limits = httpx.Limits(
            max_connections=self._config.max_connections,
            max_keepalive_connections=self._config.max_keepalive_connections,
        )
        self._client = httpx.AsyncClient(
            base_url=self._config.base_url,
            headers=self._build_headers(),
            timeout=self._config.timeout,
            http2=self._config.http2,
            limits=limits,
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
    ) -> _T | dict[str, Any]:
        last_exc: QbrixAPIError | None = None
        max_attempts = self._config.max_retries + 1

        for attempt in range(max_attempts):
            _log.debug("%s %s attempt=%d/%d", method, path, attempt + 1, max_attempts)
            try:
                response = await self._client.request(
                    method, path, json=body, params=params
                )
            except httpx.ConnectError as exc:
                raise QbrixConnectionError(str(exc)) from exc
            except httpx.TimeoutException as exc:
                raise QbrixTimeoutError(str(exc)) from exc

            if response.is_success:
                _log.debug("%s %s → %d", method, path, response.status_code)
                if response.status_code == 204 or not response.content:
                    return cast_to.model_validate({}) if cast_to else {}
                data = response.json()
                return cast_to.model_validate(data) if cast_to else data

            if not self._should_retry(response):
                raise self._make_status_error(response)

            last_exc = self._make_status_error(response)

            if attempt < self._config.max_retries:
                delay = self._calculate_retry_delay(attempt, last_exc)
                _log.debug(
                    "%s %s retrying in %.2fs (attempt %d/%d)",
                    method,
                    path,
                    delay,
                    attempt + 1,
                    self._config.max_retries,
                )
                await asyncio.sleep(delay)

        _log.debug("%s %s failed after %d attempts", method, path, max_attempts)
        if last_exc:
            raise last_exc

        return {}

    async def get(
        self,
        path: str,
        *,
        cast_to: type[_T] | None = None,
        params: dict[str, Any] | None = None,
    ) -> _T | dict[str, Any]:
        return await self.request("GET", path, cast_to=cast_to, params=params)

    async def post(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
    ) -> _T | dict[str, Any]:
        return await self.request("POST", path, body=body, cast_to=cast_to)

    async def put(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
    ) -> _T | dict[str, Any]:
        return await self.request("PUT", path, body=body, cast_to=cast_to)

    async def patch(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
    ) -> _T | dict[str, Any]:
        return await self.request("PATCH", path, body=body, cast_to=cast_to)

    async def delete(self, path: str) -> None:
        await self.request("DELETE", path)

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> AsyncHTTPTransport:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
