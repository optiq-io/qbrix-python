from __future__ import annotations

import pytest
from pydantic import ValidationError

from qbrix.model.agent import FeedbackRequest
from qbrix.model.agent import SelectedArm
from qbrix.model.agent import SelectRequest
from qbrix.model.agent import SelectResponse
from qbrix.model.common import Context
from qbrix.model.common import PaginatedResponse
from qbrix.model.experiment import Experiment
from qbrix.model.experiment import ExperimentCreate
from qbrix.model.experiment import ExperimentUpdate
from qbrix.model.gate import GateConfig
from qbrix.model.gate import GateCreate
from qbrix.model.gate import GateRule
from qbrix.model.pool import Arm
from qbrix.model.pool import ArmCreate
from qbrix.model.pool import Pool
from qbrix.model.pool import PoolCreate
from qbrix.model.pool import PoolUpdate


@pytest.mark.unit
class TestContext:
    def test_minimal(self) -> None:
        ctx = Context(id="user-1")
        assert ctx.id == "user-1"
        assert ctx.properties is None
        assert ctx.vector is None
        assert ctx.metadata is None

    def test_full(self) -> None:
        ctx = Context(id="u-2", vector=[0.1, 0.5], metadata={"plan": "pro"})
        assert ctx.vector == [0.1, 0.5]
        assert ctx.metadata == {"plan": "pro"}

    def test_properties(self) -> None:
        ctx = Context(id="u-4", properties={"device": "mobile", "price": 20})
        assert ctx.properties == {"device": "mobile", "price": 20}
        assert ctx.vector is None

    def test_properties_preserve_value_types(self) -> None:
        # the server encodes a numeric property against a declared range, so
        # the SDK must not coerce 20 to "20" on the way in.
        ctx = Context(id="u-5", properties={"price": 20, "returning": True})
        assert ctx.properties["price"] == 20
        assert isinstance(ctx.properties["price"], int)
        assert ctx.properties["returning"] is True

    def test_vector_and_properties_together_rejected(self) -> None:
        with pytest.raises(ValidationError, match="not both"):
            Context(id="u-6", vector=[0.1], properties={"device": "mobile"})

    def test_properties_with_metadata_is_fine(self) -> None:
        # metadata targets the gate, properties feed the strategy — different
        # channels, no conflict.
        ctx = Context(
            id="u-7", properties={"device": "mobile"}, metadata={"plan": "pro"}
        )
        assert ctx.properties == {"device": "mobile"}
        assert ctx.metadata == {"plan": "pro"}

    def test_field_order_leads_with_properties(self) -> None:
        # the escape hatch comes last so an editor completes the encouraged
        # path first; mirrors the proxy's ContextModel.
        assert list(Context.model_fields) == ["id", "properties", "metadata", "vector"]

    def test_exclude_none_serialization(self) -> None:
        ctx = Context(id="u-3")
        dumped = ctx.model_dump(exclude_none=True)
        assert "vector" not in dumped
        assert "properties" not in dumped
        assert "metadata" not in dumped


@pytest.mark.unit
class TestPaginatedResponse:
    def test_has_more_false(self) -> None:
        page = PaginatedResponse[Pool](
            items=[Pool(id="p1", name="test")],
            limit=10,
            offset=0,
        )
        assert page.has_more is False

    def test_has_more_true(self) -> None:
        pools = [Pool(id=f"p{i}", name=f"pool-{i}") for i in range(10)]
        page = PaginatedResponse[Pool](items=pools, limit=10, offset=0)
        assert page.has_more is True

    def test_empty(self) -> None:
        page = PaginatedResponse[Experiment](items=[], limit=10, offset=0)
        assert page.has_more is False
        assert len(page.items) == 0


@pytest.mark.unit
class TestPoolModels:
    def test_arm(self) -> None:
        arm = Arm(id="a1", name="red", index=0)
        assert arm.is_active is True
        assert arm.metadata == {}

    def test_arm_create(self) -> None:
        ac = ArmCreate(name="blue", metadata={"hex": "#0000FF"})
        dumped = ac.model_dump()
        assert dumped == {"name": "blue", "metadata": {"hex": "#0000FF"}}

    def test_pool(self) -> None:
        pool = Pool(
            id="p1",
            name="colors",
            arms=[Arm(id="a1", name="red", index=0)],
        )
        assert len(pool.arms) == 1
        assert pool.created_at is None

    def test_pool_create(self) -> None:
        pc = PoolCreate(
            name="test",
            arms=[ArmCreate(name="a"), ArmCreate(name="b")],
        )
        assert len(pc.arms) == 2

    def test_pool_update(self) -> None:
        pu = PoolUpdate(name="renamed")
        assert pu.name == "renamed"

    def test_pool_update_empty(self) -> None:
        pu = PoolUpdate()
        assert pu.name is None


@pytest.mark.unit
class TestExperimentModels:
    def test_experiment(self) -> None:
        exp = Experiment(
            id="e1",
            name="cta-test",
            pool_id="p1",
            policy="beta_ts",
            policy_params={},
            enabled=True,
        )
        assert exp.pool is None
        assert exp.feature_gate is None

    def test_experiment_create_minimal(self) -> None:
        ec = ExperimentCreate(name="test", pool_id="p1", policy="beta_ts")
        assert ec.enabled is True
        assert ec.policy_params == {}
        assert ec.feature_gate is None

    def test_experiment_create_with_gate(self) -> None:
        gate = GateCreate(rollout_percentage=50.0)
        ec = ExperimentCreate(
            name="test", pool_id="p1", policy="ucb1", feature_gate=gate
        )
        assert ec.feature_gate is not None
        assert ec.feature_gate.rollout_percentage == 50.0

    def test_experiment_update(self) -> None:
        eu = ExperimentUpdate(enabled=False)
        assert eu.enabled is False
        assert eu.policy_params is None


@pytest.mark.unit
class TestGateModels:
    def test_gate_rule(self) -> None:
        rule = GateRule(key="country", operator="==", value="US")
        assert rule.arm_id is None

    def test_gate_rule_with_arm(self) -> None:
        rule = GateRule(key="plan", operator="==", value="enterprise", arm_id="a1")
        assert rule.arm_id == "a1"

    def test_gate_create_defaults(self) -> None:
        gc = GateCreate()
        assert gc.enabled is True
        assert gc.rollout_percentage == 100.0
        assert gc.timezone == "UTC"
        assert gc.rules == []

    def test_gate_config(self) -> None:
        gc = GateConfig(experiment_id="e1")
        assert gc.version == 1
        assert gc.rules == []


@pytest.mark.unit
class TestAgentModels:
    def test_select_request(self) -> None:
        sr = SelectRequest(experiment_id="e1", context=Context(id="u-1"))
        assert sr.experiment_id == "e1"

    def test_select_response(self) -> None:
        resp = SelectResponse(
            arm=SelectedArm(id="a1", name="blue", index=1),
            request_id="tok_abc",
            is_default=False,
        )
        assert resp.arm.name == "blue"
        assert resp.is_default is False

    def test_select_response_from_dict(self) -> None:
        data = {
            "arm": {"id": "a1", "name": "red", "index": 0},
            "request_id": "tok_xyz",
            "is_default": True,
        }
        resp = SelectResponse.model_validate(data)
        assert resp.arm.index == 0
        assert resp.is_default is True

    def test_feedback_request(self) -> None:
        fr = FeedbackRequest(request_id="tok_abc", reward=1.0)
        assert fr.reward == 1.0

    def test_feedback_request_int_reward(self) -> None:
        fr = FeedbackRequest(request_id="tok_abc", reward=1)
        assert fr.reward == 1
