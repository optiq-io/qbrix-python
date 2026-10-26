from __future__ import annotations

import pytest
from pydantic import ValidationError

from qbrix.model.common import Context
from qbrix.model.common import PaginatedResponse
from qbrix.model.decision import Decision
from qbrix.model.decision import Settings
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
        ctx = Context(unit="user-1")
        assert ctx.unit == "user-1"
        assert ctx.model_dump(exclude_none=True) == {"unit": "user-1"}

    def test_properties_preserve_value_types(self) -> None:
        ctx = Context(unit="u-5", properties={"price": 20, "returning": True})
        assert ctx.properties == {"price": 20, "returning": True}
        assert isinstance(ctx.properties["price"], int)

    @pytest.mark.parametrize("unit", ["", "  ", "u" * 257])
    def test_invalid_unit_rejected(self, unit: str) -> None:
        with pytest.raises(ValidationError):
            Context(unit=unit)

    def test_unit_required(self) -> None:
        with pytest.raises(ValidationError):
            Context.model_validate({"properties": {"device": "mobile"}})


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
class TestDecisionModels:
    def test_decision_from_dict(self) -> None:
        decision = Decision.model_validate(
            {
                "option": {"key": "bold", "name": "Bold", "config": {"n": 3}},
                "request_id": None,
                "reason": "draft",
            }
        )
        assert decision.option is not None
        assert decision.option.config == {"n": 3}
        assert decision.request_id is None

    def test_settings_offline_needs_only_a_key(self) -> None:
        settings = Settings.model_validate({"offline": {"key": "control"}})
        assert settings.offline is not None
        assert settings.offline.config == {}
        assert settings.offline.name is None
