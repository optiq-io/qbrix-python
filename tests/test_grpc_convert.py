from __future__ import annotations

import pytest

pytest.importorskip("grpc", reason="install qbrix[grpc] to run gRPC tests")

from qbrix._transport._grpc import _convert as convert
from qbrix._transport._grpc._proto import common_pb2
from qbrix._transport._grpc._proto import proxy_pb2
from qbrix.model.gate import GateConfig
from qbrix.model.pool import Pool

pytestmark = pytest.mark.grpc


class TestArmAndPool:
    def test_arm_to_dict(self) -> None:
        a = common_pb2.Arm(
            id="a1", name="red", index=2, is_active=True, metadata={"k": "v"}
        )
        assert convert.arm_to_dict(a) == {
            "id": "a1",
            "name": "red",
            "index": 2,
            "is_active": True,
            "metadata": {"k": "v"},
        }

    def test_arms_from_dicts_only_uses_name_and_metadata(self) -> None:
        result = convert.arms_from_dicts(
            [{"name": "red", "metadata": {"weight": 1}}, {"name": "blue"}]
        )
        assert len(result) == 2
        assert result[0].name == "red"
        # metadata values get coerced to strings (map<str,str>)
        assert dict(result[0].metadata) == {"weight": "1"}
        assert result[1].name == "blue"

    def test_pool_to_dict_validates_into_pydantic(self) -> None:
        p = common_pb2.Pool(
            id="p1",
            name="my-pool",
            created_at="2026-01-01T00:00:00Z",
            arms=[common_pb2.Arm(id="a1", name="red", index=0, is_active=True)],
        )
        d = convert.pool_to_dict(p)
        pool = Pool.model_validate(d)
        assert pool.id == "p1"
        assert pool.created_at == "2026-01-01T00:00:00Z"
        assert pool.updated_at is None  # empty string normalizes to None
        assert len(pool.arms) == 1


class TestExperiment:
    def test_experiment_prefers_policy_params_json(self) -> None:
        e = common_pb2.Experiment(
            id="e1",
            name="exp",
            pool_id="p1",
            policy="BetaTSPolicy",
            policy_params={"alpha": "1"},  # legacy map (strings only)
            enabled=True,
        )
        # Populate the Struct field with mixed-type values
        e.policy_params_json.update({"alpha": 1.5, "beta": 2})
        d = convert.experiment_to_dict(e)
        assert d["policy_params"] == {"alpha": 1.5, "beta": 2.0}

    def test_experiment_falls_back_to_string_map(self) -> None:
        e = common_pb2.Experiment(
            id="e1",
            name="exp",
            pool_id="p1",
            policy="EpsilonPolicy",
            policy_params={"eps": "0.1"},
            enabled=False,
        )
        d = convert.experiment_to_dict(e)
        assert d["policy_params"] == {"eps": "0.1"}
        assert d["enabled"] is False

    def test_experiment_detail_includes_pool_and_gate(self) -> None:
        d = proxy_pb2.ExperimentDetail(
            experiment=common_pb2.Experiment(
                id="e1", name="exp", pool_id="p1", policy="EpsilonPolicy", enabled=True
            ),
            pool=common_pb2.Pool(id="p1", name="my-pool"),
            feature_gate=proxy_pb2.FeatureGateConfig(
                enabled=True, rollout_percentage=50.0, timezone="UTC"
            ),
        )
        result = convert.experiment_detail_to_dict(d)
        assert result["pool"]["id"] == "p1"
        assert result["feature_gate"]["experiment_id"] == "e1"
        assert result["feature_gate"]["rollout_percentage"] == 50.0


class TestGateConfig:
    def test_round_trip(self) -> None:
        src = {
            "enabled": True,
            "rollout_percentage": 25.0,
            "default_arm_id": "a_default",
            "schedule_start": "2026-01-01T00:00:00+00:00",
            "schedule_end": "2026-12-31T23:59:59+00:00",
            "active_hours_start": "09:00",
            "active_hours_end": "17:00",
            "timezone": "America/New_York",
            "rules": [
                {
                    "key": "region",
                    "operator": "in",
                    "value": ["us", "eu"],
                    "arm_id": "a_x",
                },
                {"key": "plan", "operator": "==", "value": "pro", "arm_id": "a_y"},
            ],
        }
        proto = convert.gate_config_from_dict(src)
        result = convert.gate_config_to_dict(proto, experiment_id="e_test")
        assert result["experiment_id"] == "e_test"
        assert result["enabled"] is True
        assert result["rollout_percentage"] == 25.0
        assert result["timezone"] == "America/New_York"
        assert result["active_hours_start"] == "09:00"
        assert result["rules"][0]["value"] == ["us", "eu"]
        assert result["rules"][1]["value"] == "pro"
        # And the result validates into the Pydantic model
        GateConfig.model_validate(result)

    def test_empty_gate(self) -> None:
        # Optional sub-messages → keys absent (not None) from the dict
        cfg = proxy_pb2.FeatureGateConfig(enabled=False, rollout_percentage=0.0)
        d = convert.gate_config_to_dict(cfg, experiment_id="e_x")
        assert "schedule_start" not in d
        assert "active_hours_start" not in d
        gc = GateConfig.model_validate(d)
        assert gc.enabled is False
        assert gc.schedule_start is None

    def test_iso_with_no_timezone_treated_as_utc(self) -> None:
        proto = convert.gate_config_from_dict({"schedule_start": "2026-06-15T12:00:00"})
        # 2026-06-15T12:00:00 UTC == 1_781_524_800_000 ms since epoch
        assert proto.schedule.start_timestamp_ms == 1_781_524_800_000


class TestContextAndSelect:
    def test_context_from_dict(self) -> None:
        ctx = convert.context_from_dict(
            {"id": "u1", "vector": [0.1, 0.2], "metadata": {"plan": "pro"}}
        )
        assert ctx.id == "u1"
        assert list(ctx.vector) == [pytest.approx(0.1), pytest.approx(0.2)]
        assert dict(ctx.metadata) == {"plan": "pro"}

    def test_select_response_flattens_arm(self) -> None:
        resp = proxy_pb2.SelectResponse(
            arm=common_pb2.Arm(id="a1", name="winner", index=3, is_active=True),
            request_id="req_xxx",
            is_default=False,
        )
        d = convert.select_response_to_dict(resp)
        # Only id/name/index — matches SelectedArm pydantic shape
        assert d["arm"] == {"id": "a1", "name": "winner", "index": 3}
        assert d["request_id"] == "req_xxx"
        assert d["is_default"] is False
