from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import httpx
import pytest

from qbrix._base_client import AsyncAPIClient
from qbrix._base_client import SyncAPIClient
from qbrix._config import QbrixConfig


@pytest.fixture(autouse=True)
def _ignore_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent QbrixConfig from loading a local .env file during tests."""
    monkeypatch.setattr(
        QbrixConfig, "model_config", {**QbrixConfig.model_config, "env_file": None}
    )


class MockSyncClient(SyncAPIClient):
    """sync client with a mocked httpx.Client for testing resources."""

    def __init__(self) -> None:
        super().__init__(api_key="optiq_test_key", max_retries=0)
        self._calls: list[dict[str, Any]] = []
        self._responses: list[tuple[int, dict[str, Any]]] = []
        self._call_index = 0
        # replace real httpx client with a mock
        self._client = MagicMock(spec=httpx.Client)
        self._client.request = MagicMock(side_effect=self._fake_request)

    def enqueue(self, response: dict[str, Any], *, status: int = 200) -> None:
        self._responses.append((status, response))

    def _fake_request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout: Any = None,
    ) -> httpx.Response:
        self._calls.append(
            {
                "method": method,
                "path": path,
                "json": json,
                "params": params,
                "timeout": timeout,
            }
        )
        if self._call_index < len(self._responses):
            status, data = self._responses[self._call_index]
            self._call_index += 1
            return httpx.Response(status, json=data)
        return httpx.Response(200, json={})

    @property
    def calls(self) -> list[dict[str, Any]]:
        return self._calls


class MockAsyncClient(AsyncAPIClient):
    """async client with a mocked httpx.AsyncClient for testing resources."""

    def __init__(self) -> None:
        super().__init__(api_key="optiq_test_key", max_retries=0)
        self._calls: list[dict[str, Any]] = []
        self._responses: list[tuple[int, dict[str, Any]]] = []
        self._call_index = 0
        # replace real httpx async client with a mock
        self._client = MagicMock(spec=httpx.AsyncClient)
        self._client.request = MagicMock(side_effect=self._fake_request)

    def enqueue(self, response: dict[str, Any], *, status: int = 200) -> None:
        self._responses.append((status, response))

    async def _fake_request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout: Any = None,
    ) -> httpx.Response:
        self._calls.append(
            {
                "method": method,
                "path": path,
                "json": json,
                "params": params,
                "timeout": timeout,
            }
        )
        if self._call_index < len(self._responses):
            status, data = self._responses[self._call_index]
            self._call_index += 1
            return httpx.Response(status, json=data)
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


# ---- gRPC fixtures -----------------------------------------------------------
# The fixtures import grpc lazily; tests that use them should put
# ``pytest.importorskip("grpc")`` at the top of the module.


def _build_mock_grpc_client():  # type: ignore[no-untyped-def]
    """Return a sync GRPCTransport with channel/stub replaced by mocks."""
    from qbrix._transport._grpc import GRPCTransport

    with patch("qbrix._transport._grpc._client.grpc.insecure_channel"):
        client = GRPCTransport(
            api_key="optiq_test_key",
            base_url="localhost:50050",
            max_retries=0,
        )
    # No spec — ProxyServiceStub attaches RPC methods in __init__, so a class
    # spec wouldn't see them. The bare MagicMock auto-generates any attribute.
    client._stub = MagicMock()
    return client


def _build_mock_async_grpc_client():  # type: ignore[no-untyped-def]
    from qbrix._transport._grpc import AsyncGRPCTransport

    with patch("qbrix._transport._grpc._client.grpc.aio.insecure_channel"):
        client = AsyncGRPCTransport(
            api_key="optiq_test_key",
            base_url="localhost:50050",
            max_retries=0,
        )
    # No spec — ProxyServiceStub attaches RPC methods in __init__, so a class
    # spec wouldn't see them. The bare MagicMock auto-generates any attribute.
    client._stub = MagicMock()
    return client


@pytest.fixture
def grpc_client():  # type: ignore[no-untyped-def]
    return _build_mock_grpc_client()


@pytest.fixture
def async_grpc_client():  # type: ignore[no-untyped-def]
    return _build_mock_async_grpc_client()
