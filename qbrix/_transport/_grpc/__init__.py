"""gRPC transport implementation using grpcio.

Importing this package requires the ``grpc`` extra. ``qbrix._client`` performs
a lazy import inside the transport factory, so HTTP-only users never trigger
this path and don't need ``grpcio`` installed.
"""

from qbrix._transport._grpc._client import AsyncGRPCTransport
from qbrix._transport._grpc._client import GRPCTransport
from qbrix._transport._grpc._routes import GRPCRouteNotImplementedError

__all__ = [
    "AsyncGRPCTransport",
    "GRPCRouteNotImplementedError",
    "GRPCTransport",
]
