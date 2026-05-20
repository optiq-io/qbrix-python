from __future__ import annotations

import pytest

pytest.importorskip("grpc", reason="install qbrix[grpc] to run gRPC tests")

from qbrix._transport._grpc._routes import GRPCRouteNotImplementedError
from qbrix._transport._grpc._routes import ROUTES
from qbrix._transport._grpc._routes import match

pytestmark = pytest.mark.grpc


class TestRouteCoverage:
    def test_route_count_matches_proxy_proto_rpcs(self) -> None:
        # proxy.proto exposes 19 unary RPCs; the SDK routes 18 of them.
        # Health has no resource, so it is not in the table.
        assert len(ROUTES) == 18

    @pytest.mark.parametrize(
        "method,path,expected_handler,expected_params",
        [
            ("POST", "/api/v1/pools", "create_pool", {}),
            ("GET", "/api/v1/pools", "list_pools", {}),
            ("GET", "/api/v1/pools/p1", "get_pool", {"pool_id": "p1"}),
            ("PATCH", "/api/v1/pools/p1", "update_pool", {"pool_id": "p1"}),
            ("DELETE", "/api/v1/pools/p1", "delete_pool", {"pool_id": "p1"}),
            (
                "GET",
                "/api/v1/pools/p1/experiments",
                "list_pool_experiments",
                {"pool_id": "p1"},
            ),
            ("POST", "/api/v1/experiments", "create_experiment", {}),
            ("GET", "/api/v1/experiments", "list_experiments", {}),
            (
                "GET",
                "/api/v1/experiments/e1",
                "get_experiment",
                {"experiment_id": "e1"},
            ),
            (
                "PATCH",
                "/api/v1/experiments/e1",
                "update_experiment",
                {"experiment_id": "e1"},
            ),
            (
                "DELETE",
                "/api/v1/experiments/e1",
                "delete_experiment",
                {"experiment_id": "e1"},
            ),
            ("POST", "/api/v1/gates/e1", "create_gate_config", {"experiment_id": "e1"}),
            ("GET", "/api/v1/gates/e1", "get_gate_config", {"experiment_id": "e1"}),
            ("PUT", "/api/v1/gates/e1", "update_gate_config", {"experiment_id": "e1"}),
            (
                "DELETE",
                "/api/v1/gates/e1",
                "delete_gate_config",
                {"experiment_id": "e1"},
            ),
            ("POST", "/api/v1/agent/select", "select", {}),
            ("POST", "/api/v1/agent/feedback", "feedback", {}),
            ("GET", "/api/v1/policies", "list_policies", {}),
        ],
    )
    def test_matching(
        self,
        method: str,
        path: str,
        expected_handler: str,
        expected_params: dict[str, str],
    ) -> None:
        handler, params = match(method, path)
        assert handler == expected_handler
        assert params == expected_params

    def test_case_insensitive_method(self) -> None:
        handler, _ = match("get", "/api/v1/pools")
        assert handler == "list_pools"

    @pytest.mark.parametrize(
        "path,resource",
        [
            ("/api/v1/runtime/redis/health", "runtime"),
            ("/api/v1/runtime/motor/health", "runtime"),
        ],
    )
    def test_http_only_paths_raise(self, path: str, resource: str) -> None:
        with pytest.raises(GRPCRouteNotImplementedError) as exc:
            match("GET", path)
        msg = str(exc.value)
        assert resource in msg
        assert "transport='http'" in msg

    def test_unknown_path_raises(self) -> None:
        with pytest.raises(GRPCRouteNotImplementedError) as exc:
            match("GET", "/api/v1/nonsense")
        assert "no gRPC route" in str(exc.value)

    def test_wrong_method_for_known_path(self) -> None:
        # DELETE on /api/v1/pools (no pool_id) is not a route — the path is for
        # the list endpoint (GET) and the create endpoint (POST).
        with pytest.raises(GRPCRouteNotImplementedError):
            match("DELETE", "/api/v1/pools")
