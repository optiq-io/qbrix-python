"""HTTP transport implementation using httpx."""

from qbrix._transport._http._client import AsyncHTTPTransport
from qbrix._transport._http._client import BaseClient
from qbrix._transport._http._client import HTTPTransport

# Legacy names — kept so existing imports and tests keep working.
SyncAPIClient = HTTPTransport
AsyncAPIClient = AsyncHTTPTransport

__all__ = [
    "AsyncAPIClient",
    "AsyncHTTPTransport",
    "BaseClient",
    "HTTPTransport",
    "SyncAPIClient",
]
