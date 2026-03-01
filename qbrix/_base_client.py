from __future__ import annotations

import asyncio
import random
import time
from typing import Any
from typing import TypeVar

import httpx
from pydantic import BaseModel

from qbrix._config import QbrixConfig
from qbrix.exception import QbrixAPIError
from qbrix.exception import QbrixConnectionError
from qbrix.exception import QbrixTimeoutError
from qbrix.exception import RateLimitedError
from qbrix.exception import STATUS_CODE_TO_EXCEPTION

_T = TypeVar("_T", bound=BaseModel)


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
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._config.api_key:
            headers["X-API-Key"] = self._config.api_key
        return headers

    def _make_status_error(self, response: httpx.Response) -> QbrixAPIError:
        detail = ""
        context = None
        try:
            body = response.json()
            detail = body.get("detail", response.text)
            context = body.get("context")
        except Exception:
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

    def _calculate_retry_delay(self, attempt: int) -> float:
        delay = self._config.retry_base_delay * (2**attempt)
        delay = min(delay, self._config.retry_max_delay)
        return delay + random.uniform(0, delay * 0.1)


class SyncAPIClient(BaseClient):
    _client: httpx.Client

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client = httpx.Client(
            base_url=self._config.base_url,
            headers=self._build_headers(),
            timeout=self._config.timeout,
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
        last_exc: Exception | None = None

        for attempt in range(self._config.max_retries + 1):
            try:
                response = self._client.request(
                    method, path, json=body, params=params
                )
            except httpx.ConnectError as exc:
                raise QbrixConnectionError(str(exc)) from exc
            except httpx.TimeoutException as exc:
                raise QbrixTimeoutError(str(exc)) from exc

            if response.is_success:
                if response.status_code == 204 or not response.content:
                    return cast_to.model_validate({}) if cast_to else {}
                data = response.json()
                return cast_to.model_validate(data) if cast_to else data

            if not self._should_retry(response):
                raise self._make_status_error(response)

            last_exc = self._make_status_error(response)

            if attempt < self._config.max_retries:
                time.sleep(self._calculate_retry_delay(attempt))

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

    def __enter__(self) -> SyncAPIClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class AsyncAPIClient(BaseClient):
    _client: httpx.AsyncClient

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client = httpx.AsyncClient(
            base_url=self._config.base_url,
            headers=self._build_headers(),
            timeout=self._config.timeout,
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
        last_exc: Exception | None = None

        for attempt in range(self._config.max_retries + 1):
            try:
                response = await self._client.request(
                    method, path, json=body, params=params
                )
            except httpx.ConnectError as exc:
                raise QbrixConnectionError(str(exc)) from exc
            except httpx.TimeoutException as exc:
                raise QbrixTimeoutError(str(exc)) from exc

            if response.is_success:
                if response.status_code == 204 or not response.content:
                    return cast_to.model_validate({}) if cast_to else {}
                data = response.json()
                return cast_to.model_validate(data) if cast_to else data

            if not self._should_retry(response):
                raise self._make_status_error(response)

            last_exc = self._make_status_error(response)

            if attempt < self._config.max_retries:
                await asyncio.sleep(self._calculate_retry_delay(attempt))

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

    async def __aenter__(self) -> AsyncAPIClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
