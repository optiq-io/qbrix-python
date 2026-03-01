from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from qbrix._base_client import AsyncAPIClient
from qbrix._base_client import SyncAPIClient
from qbrix._config import QbrixConfig


class MockSyncClient(SyncAPIClient):
    """sync client with a mocked httpx.Client for testing resources."""

    def __init__(self) -> None:
        super().__init__(api_key="optiq_test_key", max_retries=0)
        self._calls: list[dict[str, Any]] = []
        self._responses: list[dict[str, Any]] = []
        self._call_index = 0
        # replace real httpx client with a mock
        self._client = MagicMock(spec=httpx.Client)
        self._client.request = MagicMock(side_effect=self._fake_request)

    def enqueue(self, response: dict[str, Any]) -> None:
        self._responses.append(response)

    def _fake_request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        self._calls.append(
            {"method": method, "path": path, "json": json, "params": params}
        )
        if self._call_index < len(self._responses):
            data = self._responses[self._call_index]
            self._call_index += 1
            return httpx.Response(200, json=data)
        return httpx.Response(200, json={})

    @property
    def calls(self) -> list[dict[str, Any]]:
        return self._calls


class MockAsyncClient(AsyncAPIClient):
    """async client with a mocked httpx.AsyncClient for testing resources."""

    def __init__(self) -> None:
        super().__init__(api_key="optiq_test_key", max_retries=0)
        self._calls: list[dict[str, Any]] = []
        self._responses: list[dict[str, Any]] = []
        self._call_index = 0
        # replace real httpx async client with a mock
        self._client = MagicMock(spec=httpx.AsyncClient)
        self._client.request = MagicMock(side_effect=self._fake_request)

    def enqueue(self, response: dict[str, Any]) -> None:
        self._responses.append(response)

    async def _fake_request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        self._calls.append(
            {"method": method, "path": path, "json": json, "params": params}
        )
        if self._call_index < len(self._responses):
            data = self._responses[self._call_index]
            self._call_index += 1
            return httpx.Response(200, json=data)
        return httpx.Response(200, json={})

    @property
    def calls(self) -> list[dict[str, Any]]:
        return self._calls


@pytest.fixture
def mock_client() -> MockSyncClient:
    return MockSyncClient()


@pytest.fixture
def async_mock_client() -> MockAsyncClient:
    return MockAsyncClient()


@pytest.fixture
def config() -> QbrixConfig:
    return QbrixConfig(
        api_key="optiq_test_key",
        base_url="http://localhost:8080",
        max_retries=0,
    )
