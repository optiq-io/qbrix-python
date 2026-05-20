from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("grpc", reason="install qbrix[grpc] to run gRPC tests")

import grpc

from qbrix._transport._grpc._proto import common_pb2
from qbrix._transport._grpc._proto import proxy_pb2
from qbrix.model.experiment import Experiment
from qbrix.model.gate import GateConfig
from qbrix.model.pool import Pool
from qbrix.resource.pool import PoolResource
from tests.test_grpc_errors import _FakeRpcError

pytestmark = pytest.mark.grpc


class TestTransportConstruction:
    def test_target_strips_grpc_scheme(self) -> None:
        from qbrix._transport._grpc import GRPCTransport

        with patch("qbrix._transport._grpc._client.grpc.insecure_channel"):
            t = GRPCTransport(base_url="grpc://qbrix.io:50050", api_key="optiq_test")
        assert t._target == "qbrix.io:50050"
        assert t._use_tls is False

    def test_grpcs_scheme_picks_tls(self) -> None:
        from qbrix._transport._grpc import GRPCTransport

        with (
            patch("qbrix._transport._grpc._client.grpc.secure_channel"),
            patch("qbrix._transport._grpc._client.grpc.ssl_channel_credentials"),
        ):
            t = GRPCTransport(base_url="grpcs://qbrix.io:443", api_key="optiq_test")
        assert t._target == "qbrix.io:443"
        assert t._use_tls is True

    def test_explicit_tls_flag(self) -> None:
        from qbrix._transport._grpc import GRPCTransport

        with (
            patch("qbrix._transport._grpc._client.grpc.secure_channel"),
            patch("qbrix._transport._grpc._client.grpc.ssl_channel_credentials"),
        ):
            t = GRPCTransport(
                base_url="qbrix.io:443", api_key="optiq_test", grpc_use_tls=True
            )
        assert t._use_tls is True

    def test_metadata_includes_api_key_and_user_agent(self, grpc_client) -> None:
        meta = dict(grpc_client._metadata())
        assert meta["x-api-key"] == "optiq_test_key"
        assert meta["user-agent"].startswith("qbrix-python/")

    def test_metadata_omits_api_key_when_absent(self) -> None:
        from qbrix._transport._grpc import GRPCTransport

        with patch("qbrix._transport._grpc._client.grpc.insecure_channel"):
            t = GRPCTransport(base_url="localhost:50050")
        meta = dict(t._metadata())
        assert "x-api-key" not in meta


class TestPoolViaGRPC:
    def test_create_pool_through_resource(self, grpc_client) -> None:
        # gRPC stub returns a CreatePoolResponse with the populated pool
        grpc_client._stub.CreatePool.return_value = proxy_pb2.CreatePoolResponse(
            pool=common_pb2.Pool(
                id="p_42",
                name="my-pool",
                created_at="2026-05-19T00:00:00Z",
                arms=[
                    common_pb2.Arm(id="a1", name="red", index=0, is_active=True),
                    common_pb2.Arm(id="a2", name="blue", index=1, is_active=True),
                ],
            )
        )
        # The resource speaks HTTP-style paths — transport routes to CreatePool
        resource = PoolResource(grpc_client)
        pool = resource.create("my-pool", arms=[{"name": "red"}, {"name": "blue"}])
        assert isinstance(pool, Pool)
        assert pool.id == "p_42"
        assert len(pool.arms) == 2

        # Verify the stub was called with a proper proto request
        call = grpc_client._stub.CreatePool.call_args
        req = call.args[0]
        assert req.name == "my-pool"
        assert [a.name for a in req.arms] == ["red", "blue"]
        meta = dict(call.kwargs["metadata"])
        assert meta["x-api-key"] == "optiq_test_key"

    def test_get_pool_path_params(self, grpc_client) -> None:
        grpc_client._stub.GetPool.return_value = proxy_pb2.GetPoolResponse(
            pool=common_pb2.Pool(id="p_42", name="my-pool")
        )
        resource = PoolResource(grpc_client)
        pool = resource.get("p_42")
        assert pool.id == "p_42"
        req = grpc_client._stub.GetPool.call_args.args[0]
        assert req.pool_id == "p_42"

    def test_delete_pool_returns_none(self, grpc_client) -> None:
        grpc_client._stub.DeletePool.return_value = proxy_pb2.DeletePoolResponse(
            deleted=True
        )
        resource = PoolResource(grpc_client)
        assert resource.delete("p_42") is None


class TestExperimentViaGRPC:
    def test_create_experiment_with_feature_gate(self, grpc_client) -> None:
        grpc_client._stub.CreateExperiment.return_value = (
            proxy_pb2.CreateExperimentResponse(
                experiment=common_pb2.Experiment(
                    id="e_1",
                    name="exp-1",
                    pool_id="p_1",
                    policy="BetaTSPolicy",
                    enabled=True,
                ),
                feature_gate=proxy_pb2.FeatureGateConfig(
                    enabled=True, rollout_percentage=10.0, timezone="UTC"
                ),
                pool=common_pb2.Pool(id="p_1", name="my-pool"),
            )
        )
        from qbrix.resource.experiment import ExperimentResource

        resource = ExperimentResource(grpc_client)
        exp = resource.create(
            "exp-1",
            "p_1",
            policy="BetaTSPolicy",
            feature_gate={"enabled": True, "rollout_percentage": 10.0},
        )
        assert isinstance(exp, Experiment)
        assert exp.feature_gate is not None
        assert exp.feature_gate.experiment_id == "e_1"
        assert exp.pool is not None
        assert exp.pool.id == "p_1"

        req = grpc_client._stub.CreateExperiment.call_args.args[0]
        assert req.HasField("feature_gate")
        assert req.feature_gate.rollout_percentage == 10.0


class TestGateViaGRPC:
    def test_get_gate_injects_experiment_id_from_path(self, grpc_client) -> None:
        grpc_client._stub.GetGateConfig.return_value = proxy_pb2.GetGateConfigResponse(
            config=proxy_pb2.FeatureGateConfig(
                enabled=True, rollout_percentage=100.0, timezone="UTC"
            )
        )
        from qbrix.resource.gate import GateResource

        resource = GateResource(grpc_client)
        gc = resource.get("e_999")
        assert isinstance(gc, GateConfig)
        # FeatureGateConfig has no experiment_id field — the transport injects it
        assert gc.experiment_id == "e_999"


class TestAgentViaGRPC:
    def test_select_and_feedback(self, grpc_client) -> None:
        grpc_client._stub.Select.return_value = proxy_pb2.SelectResponse(
            arm=common_pb2.Arm(id="a1", name="winner", index=2),
            request_id="req_signed_xyz",
            is_default=False,
        )
        grpc_client._stub.Feedback.return_value = proxy_pb2.FeedbackResponse(
            accepted=True
        )
        from qbrix.resource.agent import AgentResource

        resource = AgentResource(grpc_client)
        result = resource.select("e_abc", {"id": "u_1", "metadata": {"plan": "pro"}})
        assert result.arm.id == "a1"
        assert result.arm.name == "winner"
        assert result.request_id == "req_signed_xyz"

        # Feedback returns None (the resource discards the response)
        assert resource.feedback(result.request_id, 1.0) is None

        select_req = grpc_client._stub.Select.call_args.args[0]
        assert select_req.experiment_id == "e_abc"
        assert select_req.context.id == "u_1"
        assert dict(select_req.context.metadata) == {"plan": "pro"}


class TestPolicyViaGRPC:
    def test_list_policies_filters_and_unwraps_default(self, grpc_client) -> None:
        from google.protobuf import struct_pb2

        grpc_client._stub.ListPolicies.return_value = proxy_pb2.ListPoliciesResponse(
            policies=[
                proxy_pb2.Policy(
                    name="EpsilonPolicy",
                    category="stochastic",
                    reward_types=["binary", "bounded"],
                    description="epsilon-greedy exploration",
                    user_params=[
                        proxy_pb2.PolicyParam(
                            name="epsilon",
                            type="number",
                            required=False,
                            default=struct_pb2.Value(number_value=0.1),
                            description="exploration rate",
                            constraints={"gte": 0.0, "lte": 1.0},
                        ),
                    ],
                ),
            ]
        )
        from qbrix.resource.policy import PolicyResource

        resource = PolicyResource(grpc_client)
        policies = resource.list(reward_type="binary")

        assert len(policies) == 1
        policy = policies[0]
        assert policy.name == "EpsilonPolicy"
        assert policy.reward_types == ["binary", "bounded"]
        # google.protobuf.Value default unwraps to a native scalar
        assert policy.user_params[0].default == 0.1
        assert policy.user_params[0].constraints == {"gte": 0.0, "lte": 1.0}

        req = grpc_client._stub.ListPolicies.call_args.args[0]
        assert req.HasField("reward_type")
        assert req.reward_type == "binary"

    def test_list_policies_without_filter_omits_reward_type(self, grpc_client) -> None:
        grpc_client._stub.ListPolicies.return_value = proxy_pb2.ListPoliciesResponse()
        from qbrix.resource.policy import PolicyResource

        assert PolicyResource(grpc_client).list() == []
        req = grpc_client._stub.ListPolicies.call_args.args[0]
        assert not req.HasField("reward_type")


class TestHTTPOnlyResourceGuards:
    def test_runtime_raises_on_grpc_transport(self, grpc_client) -> None:
        from qbrix.resource.runtime import RuntimeResource

        resource = RuntimeResource(grpc_client)
        with pytest.raises(NotImplementedError) as exc:
            resource.redis_health()
        assert "runtime" in str(exc.value).lower()


class TestRetryLogic:
    def test_unavailable_retries_then_succeeds(self) -> None:
        from qbrix._transport._grpc import GRPCTransport

        with (
            patch("qbrix._transport._grpc._client.grpc.insecure_channel"),
            patch("qbrix._transport._grpc._client.time.sleep"),
        ):
            client = GRPCTransport(
                api_key="optiq_test",
                base_url="localhost:50050",
                max_retries=2,
                retry_base_delay=0.0,
            )
        from unittest.mock import MagicMock

        client._stub = MagicMock()
        # First two calls raise UNAVAILABLE, third succeeds
        client._stub.GetPool.side_effect = [
            _FakeRpcError(grpc.StatusCode.UNAVAILABLE, "down"),
            _FakeRpcError(grpc.StatusCode.UNAVAILABLE, "down"),
            proxy_pb2.GetPoolResponse(pool=common_pb2.Pool(id="p1", name="ok")),
        ]
        from qbrix.resource.pool import PoolResource

        resource = PoolResource(client)
        pool = resource.get("p1")
        assert pool.id == "p1"
        assert client._stub.GetPool.call_count == 3

    def test_not_found_does_not_retry(self) -> None:
        from qbrix._transport._grpc import GRPCTransport
        from qbrix.exception import NotFoundError

        with patch("qbrix._transport._grpc._client.grpc.insecure_channel"):
            client = GRPCTransport(
                api_key="optiq_test", base_url="localhost:50050", max_retries=3
            )
        from unittest.mock import MagicMock

        client._stub = MagicMock()
        client._stub.GetPool.side_effect = _FakeRpcError(
            grpc.StatusCode.NOT_FOUND, "missing"
        )
        from qbrix.resource.pool import PoolResource

        with pytest.raises(NotFoundError):
            PoolResource(client).get("p1")
        # No retries on non-retryable errors
        assert client._stub.GetPool.call_count == 1
