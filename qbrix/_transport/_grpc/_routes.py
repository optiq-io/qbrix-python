"""Route table mapping (HTTP method, path) → gRPC handler name.

The SDK's resources call ``self._client.post("/api/v1/pools", ...)`` and the
GRPC transport translates that to the matching ``ProxyService`` RPC. Routes
mirror the 1:1 mapping between HTTP routes in
``../qbrix/svc/proxy/src/proxysvc/transport/http/router/`` and RPCs in
``../qbrix/proto/proxy.proto``.

Paths outside this table raise ``NotImplementedError`` — they are HTTP-only
because ``proxy.proto`` doesn't expose them. See ``_HTTP_ONLY`` for the ones
that get a named, actionable message.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Route:
    method: str
    pattern: re.Pattern[str]
    handler: str


def _r(method: str, regex: str, handler: str) -> Route:
    return Route(method=method, pattern=re.compile(regex), handler=handler)


# Order is irrelevant — patterns are mutually exclusive by anchoring (^…$).
ROUTES: tuple[Route, ...] = (
    # pools
    _r("POST", r"^/api/v1/pools$", "create_pool"),
    _r("GET", r"^/api/v1/pools$", "list_pools"),
    _r("GET", r"^/api/v1/pools/(?P<pool_id>[^/]+)$", "get_pool"),
    _r("PATCH", r"^/api/v1/pools/(?P<pool_id>[^/]+)$", "update_pool"),
    _r("DELETE", r"^/api/v1/pools/(?P<pool_id>[^/]+)$", "delete_pool"),
    _r(
        "GET",
        r"^/api/v1/pools/(?P<pool_id>[^/]+)/experiments$",
        "list_pool_experiments",
    ),
    # experiments
    _r("POST", r"^/api/v1/experiments$", "create_experiment"),
    _r("GET", r"^/api/v1/experiments$", "list_experiments"),
    _r("GET", r"^/api/v1/experiments/(?P<experiment_id>[^/]+)$", "get_experiment"),
    _r("PATCH", r"^/api/v1/experiments/(?P<experiment_id>[^/]+)$", "update_experiment"),
    _r(
        "DELETE", r"^/api/v1/experiments/(?P<experiment_id>[^/]+)$", "delete_experiment"
    ),
    # gates
    _r("POST", r"^/api/v1/gates/(?P<experiment_id>[^/]+)$", "create_gate_config"),
    _r("GET", r"^/api/v1/gates/(?P<experiment_id>[^/]+)$", "get_gate_config"),
    _r("PUT", r"^/api/v1/gates/(?P<experiment_id>[^/]+)$", "update_gate_config"),
    _r("PATCH", r"^/api/v1/gates/(?P<experiment_id>[^/]+)$", "patch_gate_config"),
    _r("DELETE", r"^/api/v1/gates/(?P<experiment_id>[^/]+)$", "delete_gate_config"),
    # agent
    _r("POST", r"^/api/v1/agent/select$", "select"),
    _r("POST", r"^/api/v1/agent/feedback$", "feedback"),
    # policies
    _r("GET", r"^/api/v1/policies$", "list_policies"),
)


# Friendly names for the HTTP-only routes. Used when raising
# NotImplementedError to point users at the right install/transport. These are
# paths the proxy serves over HTTP that proxy.proto has no matching RPC for.
_HTTP_ONLY: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^/api/v1/runtime/"), "the runtime resource"),
    (re.compile(r"^/api/v1/gates/[^/]+/evaluate$"), "gate.evaluate()"),
    (re.compile(r"^/api/v1/experiments/[^/]+/reset$"), "experiment.reset()"),
)


class GRPCRouteNotImplementedError(NotImplementedError):
    """Raised when a resource calls a path that has no proxy.proto RPC."""


def match(method: str, path: str) -> tuple[str, dict[str, str]]:
    """Return (handler_name, path_params) for the given (method, path).

    Raises ``GRPCRouteNotImplementedError`` if the route is HTTP-only or
    unknown. The error message names the resource family so callers can fix
    their code (use HTTP transport, or open the relevant proto ticket).
    """
    method_upper = method.upper()
    for route in ROUTES:
        if route.method != method_upper:
            continue
        m = route.pattern.match(path)
        if m is not None:
            return route.handler, m.groupdict()

    for pattern, name in _HTTP_ONLY:
        if pattern.match(path):
            raise GRPCRouteNotImplementedError(
                f"{name} is HTTP-only; proxy.proto does not expose it. "
                f"Construct Qbrix with transport='http' or install qbrix[http]."
            )

    raise GRPCRouteNotImplementedError(f"no gRPC route for {method_upper} {path}")


__all__ = ["GRPCRouteNotImplementedError", "ROUTES", "Route", "match"]
