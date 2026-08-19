"""gRPC transport for the qbrix SDK.

Implements the same ``Transport`` interface (``get`` / ``post`` / ``put`` /
``patch`` / ``delete`` + low-level ``request``) as
``qbrix._transport._http.HTTPTransport``. Resources never see the wire
difference — they hand off HTTP-shaped paths and the route table here maps
them to ``ProxyService`` RPCs.

Channel options and metadata mirror the upstream gRPC client patterns in
``/Users/eskinmi/Dev/qbrix/svc/proxy/src/proxysvc/client.py``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any
from typing import TypeVar

import grpc
from pydantic import BaseModel

from qbrix._transport._base import AsyncTransport
from qbrix._transport._base import Transport
from qbrix._transport._grpc._error import is_retryable
from qbrix._transport._grpc._error import make_grpc_error
from qbrix._transport._grpc._handlers import HANDLERS
from qbrix._transport._grpc._proto import proxy_pb2_grpc
from qbrix._transport._grpc._routes import match
from qbrix._transport._http._client import BaseClient
from qbrix._version import __version__
from qbrix.exception import QbrixAPIError

_T = TypeVar("_T", bound=BaseModel)
_log = logging.getLogger("qbrix")


_SCHEME_PREFIXES = ("grpcs://", "grpc://", "https://", "http://")


def _parse_target(base_url: str) -> str:
    """Return ``host[:port]`` stripped of any URL scheme."""
    target = base_url
    for prefix in _SCHEME_PREFIXES:
        if target.startswith(prefix):
            target = target[len(prefix) :]
            break
    return target.rstrip("/")


def _is_tls(base_url: str, use_tls: bool) -> bool:
    return use_tls or base_url.startswith(("grpcs://", "https://"))


class _BaseGRPCTransport(BaseClient):
    """Shared init / config / metadata. Subclasses pick sync vs async channel."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._target = _parse_target(self._config.base_url)
        self._use_tls = _is_tls(self._config.base_url, self._config.grpc_use_tls)

    def _channel_options(self) -> list[tuple[str, Any]]:
        return [
            ("grpc.keepalive_time_ms", self._config.grpc_keepalive_time_ms),
            ("grpc.keepalive_timeout_ms", self._config.grpc_keepalive_timeout_ms),
            (
                "grpc.http2.max_pings_without_data",
                self._config.grpc_http2_max_pings_without_data,
            ),
            (
                "grpc.keepalive_permit_without_calls",
                int(self._config.grpc_keepalive_permit_without_calls),
            ),
        ]

    def _metadata(self) -> list[tuple[str, str]]:
        meta: list[tuple[str, str]] = [
            ("user-agent", f"qbrix-python/{__version__}"),
        ]
        # gRPC metadata keys are conventionally lowercase. Matches the
        # interceptor at qbrix/svc/proxy/src/proxysvc/grpc/auth/interceptor.py.
        if self._config.api_key:
            meta.append(("x-api-key", self._config.api_key))
        return meta


def _dispatch_prepare(
    method: str, path: str, body: dict[str, Any] | None, params: dict[str, Any] | None
) -> tuple[Any, str, Any, dict[str, str]]:
    """Resolve route, build proto request, return (request, stub_attr, converter, path_params)."""
    handler_name, path_params = match(method, path)
    handler = HANDLERS[handler_name]
    req = handler.build_request(body or {}, params or {}, path_params)
    return req, handler.stub_attr, handler.convert_response, path_params


def _finalize(
    result: dict[str, Any] | None,
    cast_to: type[_T] | None,
) -> _T | dict[str, Any]:
    if cast_to is not None:
        return cast_to.model_validate(result or {})
    return result if result is not None else {}


class GRPCTransport(_BaseGRPCTransport, Transport):
    """Synchronous gRPC transport."""

    _channel: grpc.Channel
    _stub: proxy_pb2_grpc.ProxyServiceStub

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        options = self._channel_options()
        if self._use_tls:
            credentials = grpc.ssl_channel_credentials()
            self._channel = grpc.secure_channel(
                self._target, credentials, options=options
            )
        else:
            self._channel = grpc.insecure_channel(self._target, options=options)
        self._stub = proxy_pb2_grpc.ProxyServiceStub(self._channel)

    def _call(
        self,
        stub_attr: str,
        req: Any,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> Any:
        stub_method = getattr(self._stub, stub_attr)
        last_exc: QbrixAPIError | None = None
        effective_timeout = timeout if timeout is not None else self._config.timeout
        effective_max_retries = (
            max_retries if max_retries is not None else self._config.max_retries
        )
        max_attempts = effective_max_retries + 1
        for attempt in range(max_attempts):
            _log.debug("%s attempt=%d/%d", stub_attr, attempt + 1, max_attempts)
            try:
                return stub_method(
                    req, metadata=self._metadata(), timeout=effective_timeout
                )
            except grpc.RpcError as exc:
                if not is_retryable(exc) or attempt >= effective_max_retries:
                    raise make_grpc_error(exc) from exc
                last_exc = make_grpc_error(exc)  # type: ignore[assignment]
                time.sleep(self._calculate_retry_delay(attempt, last_exc))
        # Loop exits via raise or return; this is unreachable but appeases mypy.
        if last_exc:
            raise last_exc
        return None

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> _T | dict[str, Any]:
        req, stub_attr, converter, path_params = _dispatch_prepare(
            method, path, body, params
        )
        resp = self._call(stub_attr, req, timeout=timeout, max_retries=max_retries)
        return _finalize(converter(resp, path_params), cast_to)

    def get(
        self,
        path: str,
        *,
        cast_to: type[_T] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> _T | dict[str, Any]:
        return self.request(
            "GET",
            path,
            cast_to=cast_to,
            params=params,
            timeout=timeout,
            max_retries=max_retries,
        )

    def post(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> _T | dict[str, Any]:
        return self.request(
            "POST",
            path,
            body=body,
            cast_to=cast_to,
            timeout=timeout,
            max_retries=max_retries,
        )

    def put(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> _T | dict[str, Any]:
        return self.request(
            "PUT",
            path,
            body=body,
            cast_to=cast_to,
            timeout=timeout,
            max_retries=max_retries,
        )

    def patch(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> _T | dict[str, Any]:
        return self.request(
            "PATCH",
            path,
            body=body,
            cast_to=cast_to,
            timeout=timeout,
            max_retries=max_retries,
        )

    def delete(
        self,
        path: str,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        self.request("DELETE", path, timeout=timeout, max_retries=max_retries)

    def close(self) -> None:
        self._channel.close()

    def __enter__(self) -> GRPCTransport:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class AsyncGRPCTransport(_BaseGRPCTransport, AsyncTransport):
    """Asynchronous gRPC transport."""

    _channel: grpc.aio.Channel
    _stub: proxy_pb2_grpc.ProxyServiceStub

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        options = self._channel_options()
        if self._use_tls:
            credentials = grpc.ssl_channel_credentials()
            self._channel = grpc.aio.secure_channel(
                self._target, credentials, options=options
            )
        else:
            self._channel = grpc.aio.insecure_channel(self._target, options=options)
        self._stub = proxy_pb2_grpc.ProxyServiceStub(self._channel)

    async def _call(
        self,
        stub_attr: str,
        req: Any,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> Any:
        stub_method = getattr(self._stub, stub_attr)
        last_exc: QbrixAPIError | None = None
        effective_timeout = timeout if timeout is not None else self._config.timeout
        effective_max_retries = (
            max_retries if max_retries is not None else self._config.max_retries
        )
        max_attempts = effective_max_retries + 1
        for attempt in range(max_attempts):
            _log.debug("%s attempt=%d/%d", stub_attr, attempt + 1, max_attempts)
            try:
                return await stub_method(
                    req, metadata=self._metadata(), timeout=effective_timeout
                )
            except grpc.RpcError as exc:
                if not is_retryable(exc) or attempt >= effective_max_retries:
                    raise make_grpc_error(exc) from exc
                last_exc = make_grpc_error(exc)  # type: ignore[assignment]
                await asyncio.sleep(self._calculate_retry_delay(attempt, last_exc))
        if last_exc:
            raise last_exc
        return None

    async def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> _T | dict[str, Any]:
        req, stub_attr, converter, path_params = _dispatch_prepare(
            method, path, body, params
        )
        resp = await self._call(
            stub_attr, req, timeout=timeout, max_retries=max_retries
        )
        return _finalize(converter(resp, path_params), cast_to)

    async def get(
        self,
        path: str,
        *,
        cast_to: type[_T] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> _T | dict[str, Any]:
        return await self.request(
            "GET",
            path,
            cast_to=cast_to,
            params=params,
            timeout=timeout,
            max_retries=max_retries,
        )

    async def post(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> _T | dict[str, Any]:
        return await self.request(
            "POST",
            path,
            body=body,
            cast_to=cast_to,
            timeout=timeout,
            max_retries=max_retries,
        )

    async def put(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> _T | dict[str, Any]:
        return await self.request(
            "PUT",
            path,
            body=body,
            cast_to=cast_to,
            timeout=timeout,
            max_retries=max_retries,
        )

    async def patch(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> _T | dict[str, Any]:
        return await self.request(
            "PATCH",
            path,
            body=body,
            cast_to=cast_to,
            timeout=timeout,
            max_retries=max_retries,
        )

    async def delete(
        self,
        path: str,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        await self.request("DELETE", path, timeout=timeout, max_retries=max_retries)

    async def close(self) -> None:
        await self._channel.close()

    async def __aenter__(self) -> AsyncGRPCTransport:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
