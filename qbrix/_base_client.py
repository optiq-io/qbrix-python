"""Back-compat shim — kept so existing imports of ``SyncAPIClient`` /
``AsyncAPIClient`` continue to resolve. New code should import from
``qbrix._transport._http`` directly.

The HTTP-transport implementation moved to ``qbrix._transport._http._client``
when gRPC support was added; see ``qbrix._transport._base.Transport`` for the
interface both transports satisfy.
"""

from qbrix._transport._http._client import AsyncHTTPTransport  # noqa: F401
from qbrix._transport._http._client import BaseClient  # noqa: F401
from qbrix._transport._http._client import HTTPTransport  # noqa: F401

# Legacy names — these are aliases of the new transport classes above.
SyncAPIClient = HTTPTransport
AsyncAPIClient = AsyncHTTPTransport
