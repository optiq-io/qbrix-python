from __future__ import annotations

from datetime import datetime
from datetime import timezone
from unittest.mock import patch

import pytest

pytest.importorskip("grpc", reason="install qbrix[grpc] to run gRPC tests")

import grpc

from qbrix._transport._grpc._proto import common_pb2
from qbrix._transport._grpc._proto import loop_pb2
from qbrix._transport._grpc._proto import proxy_pb2
from qbrix.model.decision import Decision
from qbrix.model.decision import Option
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


class TestLoopViaGRPC:
    def test_select_and_outcome(self, grpc_client) -> None:
        from qbrix.resource.decision import DecisionResource

        resp = loop_pb2.SelectResponse(
            option=loop_pb2.Option(key="bold", name="Bold"),
            request_id="req_signed_xyz",
            reason="live",
        )
        resp.option.config.update({"headline": "Pay now", "size": 3})
        grpc_client._loop_stub.Select.return_value = resp
        accepted = loop_pb2.OutcomeResponse(id="evt-1")
        accepted.at.FromMilliseconds(1_793_014_200_000)
        grpc_client._loop_stub.Outcome.return_value = accepted

        resource = DecisionResource(grpc_client)
        decision = resource.select(
            "checkout-headline", {"unit": "u_1", "properties": {"plan": "pro"}}
        )
        assert decision == Decision(
            option=Option(
                key="bold", name="Bold", config={"headline": "Pay now", "size": 3}
            ),
            request_id="req_signed_xyz",
            reason="live",
        )
        outcome = resource.outcome(decision.request_id, 1)
        assert outcome is not None and outcome.id == "evt-1"
        assert outcome.at == datetime(2026, 10, 26, 11, 30, tzinfo=timezone.utc)

        select_req = grpc_client._loop_stub.Select.call_args.args[0]
        assert select_req.loop == "checkout-headline"
        assert select_req.context.unit == "u_1"
        assert select_req.context.properties["plan"] == "pro"
        outcome_req = grpc_client._loop_stub.Outcome.call_args.args[0]
        assert outcome_req.request_id == "req_signed_xyz"
        assert outcome_req.value == 1.0
        assert len(outcome_req.id) == 32
        grpc_client._stub.Select.assert_not_called()

    def test_draft_has_no_request_id(self, grpc_client) -> None:
        from qbrix.resource.decision import DecisionResource

        grpc_client._loop_stub.Select.return_value = loop_pb2.SelectResponse(
            option=loop_pb2.Option(key="control", name="Control"), reason="draft"
        )
        decision = DecisionResource(grpc_client).select("l", {"unit": "u"})
        assert decision.request_id is None
        assert decision.reason == "draft"

    @pytest.mark.parametrize(
        "code",
        [
            grpc.StatusCode.UNAVAILABLE,
            grpc.StatusCode.DEADLINE_EXCEEDED,
            grpc.StatusCode.RESOURCE_EXHAUSTED,
            grpc.StatusCode.INTERNAL,
        ],
    )
    def test_unreachable_returns_offline_option(self, grpc_client, code) -> None:
        from qbrix.resource.decision import DecisionResource

        grpc_client._loop_stub.Select.side_effect = _FakeRpcError(code, "down")
        decision = DecisionResource(grpc_client).select(
            "l", {"unit": "u"}, {"offline": {"key": "control"}}
        )
        assert decision == Decision(
            option=Option(key="control"), request_id=None, reason="offline"
        )

    def test_unknown_loop_raises(self, grpc_client) -> None:
        from qbrix.exception import NotFoundError
        from qbrix.resource.decision import DecisionResource

        grpc_client._loop_stub.Select.side_effect = _FakeRpcError(
            grpc.StatusCode.NOT_FOUND, "no loop with the key or id 'nope'"
        )
        with pytest.raises(NotFoundError, match="no loop with the key or id 'nope'"):
            DecisionResource(grpc_client).select(
                "nope", {"unit": "u"}, {"offline": {"key": "control"}}
            )

    def test_invalid_outcome_raises_with_the_rule(self, grpc_client) -> None:
        from qbrix.exception import BadRequestError
        from qbrix.resource.decision import DecisionResource

        grpc_client._loop_stub.Outcome.side_effect = _FakeRpcError(
            grpc.StatusCode.INVALID_ARGUMENT, "a conversion is 0 or 1, got 2"
        )
        with pytest.raises(BadRequestError, match="a conversion is 0 or 1, got 2"):
            DecisionResource(grpc_client).outcome("tok", 2)

    def test_retried_outcome_sends_the_same_id(self) -> None:
        from unittest.mock import MagicMock

        from qbrix._transport._grpc import GRPCTransport
        from qbrix.resource.decision import DecisionResource

        with (
            patch("qbrix._transport._grpc._client.grpc.insecure_channel"),
            patch("qbrix._transport._grpc._client.time.sleep"),
        ):
            client = GRPCTransport(
                api_key="optiq_test", base_url="localhost:50050", max_retries=1
            )
            client._loop_stub = MagicMock()
            client._loop_stub.Outcome.side_effect = [
                _FakeRpcError(grpc.StatusCode.UNAVAILABLE, "down"),
                loop_pb2.OutcomeResponse(id="evt-1"),
            ]
            DecisionResource(client).outcome("tok", 1)
        first, second = client._loop_stub.Outcome.call_args_list
        assert first.args[0].id == second.args[0].id


@pytest.mark.asyncio
class TestAsyncLoopViaGRPC:
    async def test_select(self, async_grpc_client) -> None:
        from unittest.mock import AsyncMock

        from qbrix.resource.decision import AsyncDecisionResource

        resp = loop_pb2.SelectResponse(
            option=loop_pb2.Option(key="bold", name="Bold"),
            request_id="req",
            reason="live",
        )
        resp.option.config.update({"size": 3})
        async_grpc_client._loop_stub.Select = AsyncMock(return_value=resp)
        decision = await AsyncDecisionResource(async_grpc_client).select(
            "l", {"unit": "u"}
        )
        assert decision.option is not None and decision.option.config == {"size": 3}
        assert decision.request_id == "req"

    async def test_unreachable_returns_offline_option(self, async_grpc_client) -> None:
        from unittest.mock import AsyncMock

        from qbrix.resource.decision import AsyncDecisionResource

        async_grpc_client._loop_stub.Select = AsyncMock(
            side_effect=_FakeRpcError(grpc.StatusCode.UNAVAILABLE, "down")
        )
        decision = await AsyncDecisionResource(async_grpc_client).select(
            "l", {"unit": "u"}
        )
        assert decision == Decision(option=None, request_id=None, reason="offline")


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
