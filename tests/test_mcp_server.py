"""Unit tests for qbrixmcp.server — each tool is called directly with a mock
AsyncQbrix client injected via a fake FastMCP Context."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest

from qbrix.exception import QbrixAPIError
from qbrix.exception import QbrixConnectionError
from qbrix.model.agent import SelectedArm
from qbrix.model.agent import SelectResponse
from qbrix.model.common import PaginatedResponse
from qbrix.model.experiment import Experiment
from qbrix.model.gate import GateConfig
from qbrix.model.gate import GateRule
from qbrix.model.pool import Arm
from qbrix.model.pool import Pool
from qbrixmcp._models import ArmInput
from qbrixmcp._models import ConfigureGateInput
from qbrixmcp._models import CreateExperimentFromPoolInput
from qbrixmcp._models import CreatePoolInput
from qbrixmcp._models import ExperimentIdInput
from qbrixmcp._models import FeedbackInput
from qbrixmcp._models import GetExperimentInput
from qbrixmcp._models import GetGateInput
from qbrixmcp._models import GetPoolInput
from qbrixmcp._models import GetStatsInput
from qbrixmcp._models import ListExperimentsInput
from qbrixmcp._models import ListPoliciesInput
from qbrixmcp._models import ListPoolsInput
from qbrixmcp._models import ResponseFormat
from qbrixmcp._models import SelectInput
from qbrixmcp._models import SetupExperimentInput
from qbrixmcp._models import TuneExperimentInput
from qbrixmcp._tools.discovery import qbrix_get_pool
from qbrixmcp._tools.discovery import qbrix_list_experiments
from qbrixmcp._tools.discovery import qbrix_list_policies
from qbrixmcp._tools.discovery import qbrix_list_pools
from qbrixmcp._tools.hotpath import qbrix_feedback
from qbrixmcp._tools.hotpath import qbrix_select
from qbrixmcp._tools.lifecycle import qbrix_delete_experiment
from qbrixmcp._tools.lifecycle import qbrix_pause_experiment
from qbrixmcp._tools.lifecycle import qbrix_remove_gate
from qbrixmcp._tools.lifecycle import qbrix_resume_experiment
from qbrixmcp._tools.lifecycle import qbrix_tune_experiment
from qbrixmcp._tools.monitoring import qbrix_get_experiment
from qbrixmcp._tools.monitoring import qbrix_get_gate
from qbrixmcp._tools.monitoring import qbrix_get_stats
from qbrixmcp._tools.setup import qbrix_configure_gate
from qbrixmcp._tools.setup import qbrix_create_experiment_from_pool
from qbrixmcp._tools.setup import qbrix_create_pool
from qbrixmcp._tools.setup import qbrix_setup_experiment


# ---------------------------------------------------------------------------
# fixtures & helpers
# ---------------------------------------------------------------------------

def _make_client() -> MagicMock:
    """Build a mock AsyncQbrix with async-ready resource methods."""
    client = MagicMock()
    client.pool.create = AsyncMock()
    client.pool.list = AsyncMock()
    client.pool.get = AsyncMock()
    client.experiment.create = AsyncMock()
    client.experiment.list = AsyncMock()
    client.experiment.get = AsyncMock()
    client.experiment.update = AsyncMock()
    client.experiment.delete = AsyncMock()
    client.gate.create = AsyncMock()
    client.gate.get = AsyncMock()
    client.gate.update = AsyncMock()
    client.gate.delete = AsyncMock()
    client.agent.select = AsyncMock()
    client.agent.feedback = AsyncMock()
    client.get = AsyncMock()
    return client


def _make_ctx(client: MagicMock) -> MagicMock:
    ctx = MagicMock()
    ctx.request_context.lifespan_state = {"client": client}
    return ctx


def _arm(name: str, index: int = 0, arm_id: str | None = None) -> Arm:
    return Arm(id=arm_id or f"arm-{index}", name=name, index=index, is_active=True, metadata={})


def _pool(name: str = "test-pool", pool_id: str = "pool-1") -> Pool:
    return Pool(
        id=pool_id,
        name=name,
        arms=[_arm("control", 0, "arm-0"), _arm("variant", 1, "arm-1")],
    )


def _experiment(
    name: str = "test-exp",
    exp_id: str = "exp-1",
    pool_id: str = "pool-1",
    enabled: bool = True,
) -> Experiment:
    return Experiment(
        id=exp_id,
        name=name,
        pool_id=pool_id,
        policy="BetaTSPolicy",
        policy_params={},
        enabled=enabled,
        pool=_pool(pool_id=pool_id),
    )


def _gate(experiment_id: str = "exp-1", rollout: float = 20.0) -> GateConfig:
    return GateConfig(experiment_id=experiment_id, rollout_percentage=rollout)


def _paginated(items: list) -> PaginatedResponse:
    return PaginatedResponse(items=items, limit=20, offset=0)


def _api_error(status: int, detail: str = "not found") -> QbrixAPIError:
    err = QbrixAPIError.__new__(QbrixAPIError)
    err.status_code = status
    err.detail = detail
    err.response = None  # type: ignore[assignment]
    err.body = None
    return err


# ---------------------------------------------------------------------------
# phase 1 — discovery & advisory
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestListPolicies:
    async def test_returns_markdown_by_default(self) -> None:
        client = _make_client()
        client.get.return_value = {
            "policies": [
                {
                    "name": "BetaTSPolicy",
                    "category": "stochastic",
                    "reward_types": ["binary"],
                    "description": "Thompson Sampling for binary rewards.",
                    "user_params": [
                        {
                            "name": "alpha_prior",
                            "type": "float",
                            "required": False,
                            "default": 1.0,
                            "description": "alpha hyperparameter",
                            "constraints": {"min": 0.0},
                        }
                    ],
                }
            ]
        }
        result = await qbrix_list_policies(ListPoliciesInput(), _make_ctx(client))

        assert "BetaTSPolicy" in result
        assert "stochastic" in result
        assert "binary" in result
        assert "alpha_prior" in result

    async def test_json_format(self) -> None:
        client = _make_client()
        client.get.return_value = {"policies": []}
        result = await qbrix_list_policies(
            ListPoliciesInput(response_format=ResponseFormat.JSON), _make_ctx(client)
        )
        parsed = json.loads(result)
        assert "policies" in parsed

    async def test_reward_type_filter_passed(self) -> None:
        client = _make_client()
        client.get.return_value = {"policies": []}
        await qbrix_list_policies(
            ListPoliciesInput(reward_type="binary"), _make_ctx(client)
        )
        client.get.assert_called_once()
        _, kwargs = client.get.call_args
        assert kwargs.get("params", {}).get("reward_type") == "binary"

    async def test_connection_error(self) -> None:
        client = _make_client()
        client.get.side_effect = QbrixConnectionError("unreachable")
        result = await qbrix_list_policies(ListPoliciesInput(), _make_ctx(client))
        assert result.startswith("error:")
        assert "QBRIX_BASE_URL" in result


@pytest.mark.unit
@pytest.mark.asyncio
class TestListExperiments:
    async def test_returns_table(self) -> None:
        client = _make_client()
        client.experiment.list.return_value = _paginated([_experiment()])
        result = await qbrix_list_experiments(ListExperimentsInput(), _make_ctx(client))

        assert "test-exp" in result
        assert "BetaTSPolicy" in result
        assert "running" in result

    async def test_empty(self) -> None:
        client = _make_client()
        client.experiment.list.return_value = _paginated([])
        result = await qbrix_list_experiments(ListExperimentsInput(), _make_ctx(client))
        assert "no experiments found" in result

    async def test_json_format(self) -> None:
        client = _make_client()
        client.experiment.list.return_value = _paginated([_experiment()])
        result = await qbrix_list_experiments(
            ListExperimentsInput(response_format=ResponseFormat.JSON),
            _make_ctx(client),
        )
        parsed = json.loads(result)
        assert len(parsed["experiments"]) == 1

    async def test_filters_passed_to_sdk(self) -> None:
        client = _make_client()
        client.experiment.list.return_value = _paginated([])
        await qbrix_list_experiments(
            ListExperimentsInput(search="my-test", enabled=True, limit=5, offset=10),
            _make_ctx(client),
        )
        client.experiment.list.assert_called_once_with(
            limit=5, offset=10, search="my-test", enabled=True
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestListPools:
    async def test_returns_pool_names(self) -> None:
        client = _make_client()
        client.pool.list.return_value = _paginated([_pool("hero-variants")])
        result = await qbrix_list_pools(ListPoolsInput(), _make_ctx(client))
        assert "hero-variants" in result
        assert "control" in result

    async def test_empty(self) -> None:
        client = _make_client()
        client.pool.list.return_value = _paginated([])
        result = await qbrix_list_pools(ListPoolsInput(), _make_ctx(client))
        assert "no pools found" in result


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetPool:
    async def test_returns_arm_table(self) -> None:
        client = _make_client()
        client.pool.get.return_value = _pool("checkout-buttons")
        result = await qbrix_get_pool(GetPoolInput(pool_id="pool-1"), _make_ctx(client))
        assert "checkout-buttons" in result
        assert "control" in result
        assert "arm-0" in result

    async def test_not_found_error(self) -> None:
        client = _make_client()
        client.pool.get.side_effect = _api_error(404)
        result = await qbrix_get_pool(GetPoolInput(pool_id="bad-id"), _make_ctx(client))
        assert "error:" in result
        assert "not found" in result


# ---------------------------------------------------------------------------
# phase 2 — setup
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestSetupExperiment:
    async def test_creates_pool_then_experiment(self) -> None:
        client = _make_client()
        client.pool.create.return_value = _pool()
        client.experiment.create.return_value = _experiment()

        params = SetupExperimentInput(
            name="btn-test",
            arms=[ArmInput(name="control"), ArmInput(name="red")],
            policy="BetaTSPolicy",
        )
        result = await qbrix_setup_experiment(params, _make_ctx(client))

        client.pool.create.assert_called_once()
        client.experiment.create.assert_called_once()
        client.gate.create.assert_not_called()

        assert "exp-1" in result
        assert "pool-1" in result
        assert "BetaTSPolicy" in result

    async def test_creates_gate_when_rollout_set(self) -> None:
        client = _make_client()
        client.pool.create.return_value = _pool()
        client.experiment.create.return_value = _experiment()
        client.gate.create.return_value = _gate(rollout=25.0)

        params = SetupExperimentInput(
            name="btn-test",
            arms=[ArmInput(name="control"), ArmInput(name="red")],
            policy="BetaTSPolicy",
            rollout_percentage=25.0,
        )
        result = await qbrix_setup_experiment(params, _make_ctx(client))

        client.gate.create.assert_called_once_with("exp-1", rollout_percentage=25.0)
        assert "25.0%" in result

    async def test_pool_name_used_for_pool(self) -> None:
        client = _make_client()
        client.pool.create.return_value = _pool()
        client.experiment.create.return_value = _experiment()

        params = SetupExperimentInput(
            name="my-experiment",
            arms=[ArmInput(name="a"), ArmInput(name="b")],
            policy="auto",
        )
        await qbrix_setup_experiment(params, _make_ctx(client))

        pool_call_kwargs = client.pool.create.call_args
        assert pool_call_kwargs[1]["name"] == "my-experiment"

    async def test_api_error_returns_error_string(self) -> None:
        client = _make_client()
        client.pool.create.side_effect = _api_error(422, "policy not found")
        params = SetupExperimentInput(
            name="x",
            arms=[ArmInput(name="a"), ArmInput(name="b")],
            policy="BadPolicy",
        )
        result = await qbrix_setup_experiment(params, _make_ctx(client))
        assert "error:" in result


@pytest.mark.unit
@pytest.mark.asyncio
class TestCreateExperimentFromPool:
    async def test_uses_existing_pool(self) -> None:
        client = _make_client()
        client.experiment.create.return_value = _experiment()

        params = CreateExperimentFromPoolInput(
            name="reuse-test",
            pool_id="pool-1",
            policy="GaussianTSPolicy",
        )
        result = await qbrix_create_experiment_from_pool(params, _make_ctx(client))

        client.pool.create.assert_not_called()
        client.experiment.create.assert_called_once_with(
            name="reuse-test",
            pool_id="pool-1",
            policy="GaussianTSPolicy",
            policy_params=None,
            enabled=True,
        )
        assert "exp-1" in result


@pytest.mark.unit
@pytest.mark.asyncio
class TestConfigureGate:
    async def test_update_existing_gate(self) -> None:
        client = _make_client()
        client.gate.update.return_value = _gate(rollout=50.0)

        params = ConfigureGateInput(experiment_id="exp-1", rollout_percentage=50.0)
        result = await qbrix_configure_gate(params, _make_ctx(client))

        client.gate.update.assert_called_once()
        client.gate.create.assert_not_called()
        assert "50.0" in result

    async def test_creates_gate_on_404(self) -> None:
        client = _make_client()
        client.gate.update.side_effect = _api_error(404)
        client.gate.create.return_value = _gate(rollout=10.0)

        params = ConfigureGateInput(experiment_id="exp-1", rollout_percentage=10.0)
        result = await qbrix_configure_gate(params, _make_ctx(client))

        client.gate.create.assert_called_once()
        assert "10.0" in result

    async def test_re_raises_non_404_error(self) -> None:
        client = _make_client()
        client.gate.update.side_effect = _api_error(403, "forbidden")

        params = ConfigureGateInput(experiment_id="exp-1")
        result = await qbrix_configure_gate(params, _make_ctx(client))
        assert "error:" in result
        assert "permissions" in result

    async def test_rules_serialised(self) -> None:
        from qbrixmcp._models import GateRuleInput

        client = _make_client()
        client.gate.update.return_value = _gate()

        params = ConfigureGateInput(
            experiment_id="exp-1",
            rules=[GateRuleInput(key="plan", operator="eq", value="premium")],
        )
        await qbrix_configure_gate(params, _make_ctx(client))

        _, kwargs = client.gate.update.call_args
        assert kwargs["rules"] == [{"key": "plan", "operator": "eq", "value": "premium"}]

    async def test_json_format(self) -> None:
        client = _make_client()
        client.gate.update.return_value = _gate(rollout=30.0)

        params = ConfigureGateInput(
            experiment_id="exp-1",
            rollout_percentage=30.0,
            response_format=ResponseFormat.JSON,
        )
        result = await qbrix_configure_gate(params, _make_ctx(client))
        parsed = json.loads(result)
        assert parsed["rollout_percentage"] == 30.0


# ---------------------------------------------------------------------------
# phase 3 — monitoring
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestGetExperiment:
    async def test_returns_markdown(self) -> None:
        client = _make_client()
        client.experiment.get.return_value = _experiment(name="hero-test")
        result = await qbrix_get_experiment(
            GetExperimentInput(experiment_id="exp-1"), _make_ctx(client)
        )
        assert "hero-test" in result
        assert "BetaTSPolicy" in result

    async def test_json_format(self) -> None:
        client = _make_client()
        client.experiment.get.return_value = _experiment()
        result = await qbrix_get_experiment(
            GetExperimentInput(experiment_id="exp-1", response_format=ResponseFormat.JSON),
            _make_ctx(client),
        )
        parsed = json.loads(result)
        assert parsed["id"] == "exp-1"

    async def test_shows_gate_when_present(self) -> None:
        client = _make_client()
        exp = _experiment()
        exp.feature_gate = _gate(rollout=30.0)
        client.experiment.get.return_value = exp
        result = await qbrix_get_experiment(
            GetExperimentInput(experiment_id="exp-1"), _make_ctx(client)
        )
        assert "30.0" in result


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetGate:
    async def test_returns_gate_details(self) -> None:
        client = _make_client()
        client.gate.get.return_value = _gate(rollout=15.0)
        result = await qbrix_get_gate(
            GetGateInput(experiment_id="exp-1"), _make_ctx(client)
        )
        assert "15.0" in result

    async def test_not_found(self) -> None:
        client = _make_client()
        client.gate.get.side_effect = _api_error(404)
        result = await qbrix_get_gate(
            GetGateInput(experiment_id="exp-1"), _make_ctx(client)
        )
        assert "error:" in result


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetStats:
    async def test_returns_overview_and_arms(self) -> None:
        client = _make_client()
        client.get.side_effect = [
            {
                "total_selections": 1000,
                "default_selections": 50,
                "total_feedback": 400,
                "avg_reward": 0.25,
                "unique_contexts": 300,
                "min_reward": 0.0,
                "max_reward": 1.0,
                "first_selection_ms": None,
                "last_selection_ms": None,
            },
            {
                "arms": [
                    {"arm_index": 0, "arm_name": "control", "selections": 500, "feedback_count": 200, "avg_reward": 0.20},
                    {"arm_index": 1, "arm_name": "variant", "selections": 500, "feedback_count": 200, "avg_reward": 0.30},
                ]
            },
        ]
        result = await qbrix_get_stats(
            GetStatsInput(experiment_id="exp-1"), _make_ctx(client)
        )
        assert "1,000" in result
        assert "control" in result
        assert "variant" in result
        assert "0.3000" in result

    async def test_arms_404_does_not_raise(self) -> None:
        client = _make_client()
        overview = {
            "total_selections": 10,
            "default_selections": 0,
            "total_feedback": 0,
            "avg_reward": None,
            "unique_contexts": 0,
            "first_selection_ms": None,
            "last_selection_ms": None,
        }
        client.get.side_effect = [overview, _api_error(404)]
        result = await qbrix_get_stats(
            GetStatsInput(experiment_id="exp-1"), _make_ctx(client)
        )
        assert "error:" not in result
        assert "10" in result

    async def test_arms_non_404_error_propagates(self) -> None:
        client = _make_client()
        overview = {
            "total_selections": 10,
            "default_selections": 0,
            "total_feedback": 0,
            "avg_reward": None,
            "unique_contexts": 0,
            "first_selection_ms": None,
            "last_selection_ms": None,
        }
        client.get.side_effect = [overview, _api_error(403, "forbidden")]
        result = await qbrix_get_stats(
            GetStatsInput(experiment_id="exp-1"), _make_ctx(client)
        )
        assert "error:" in result

    async def test_json_format(self) -> None:
        client = _make_client()
        client.get.side_effect = [
            {"total_selections": 5, "default_selections": 0, "total_feedback": 0,
             "avg_reward": None, "unique_contexts": 0, "first_selection_ms": None, "last_selection_ms": None},
            {"arms": []},
        ]
        result = await qbrix_get_stats(
            GetStatsInput(experiment_id="exp-1", response_format=ResponseFormat.JSON),
            _make_ctx(client),
        )
        parsed = json.loads(result)
        assert "overview" in parsed
        assert "arms" in parsed


# ---------------------------------------------------------------------------
# phase 4 — action
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestLifecycleTools:
    async def test_pause_calls_update_disabled(self) -> None:
        client = _make_client()
        client.experiment.update.return_value = _experiment(enabled=False)
        result = await qbrix_pause_experiment(
            ExperimentIdInput(experiment_id="exp-1"), _make_ctx(client)
        )
        client.experiment.update.assert_called_once_with("exp-1", enabled=False)
        assert "paused" in result

    async def test_resume_calls_update_enabled(self) -> None:
        client = _make_client()
        client.experiment.update.return_value = _experiment(enabled=True)
        result = await qbrix_resume_experiment(
            ExperimentIdInput(experiment_id="exp-1"), _make_ctx(client)
        )
        client.experiment.update.assert_called_once_with("exp-1", enabled=True)
        assert "resumed" in result

    async def test_tune_updates_policy_params(self) -> None:
        client = _make_client()
        exp = _experiment()
        exp.policy_params = {"alpha_prior": 2.0}
        client.experiment.update.return_value = exp

        result = await qbrix_tune_experiment(
            TuneExperimentInput(
                experiment_id="exp-1", policy_params={"alpha_prior": 2.0}
            ),
            _make_ctx(client),
        )
        client.experiment.update.assert_called_once_with(
            "exp-1", policy_params={"alpha_prior": 2.0}
        )
        assert "alpha_prior" in result

    async def test_delete_calls_sdk(self) -> None:
        client = _make_client()
        client.experiment.delete.return_value = None
        result = await qbrix_delete_experiment(
            ExperimentIdInput(experiment_id="exp-1"), _make_ctx(client)
        )
        client.experiment.delete.assert_called_once_with("exp-1")
        assert "deleted" in result

    async def test_remove_gate_calls_sdk(self) -> None:
        client = _make_client()
        client.gate.delete.return_value = None
        result = await qbrix_remove_gate(
            ExperimentIdInput(experiment_id="exp-1"), _make_ctx(client)
        )
        client.gate.delete.assert_called_once_with("exp-1")
        assert "removed" in result

    async def test_pause_error(self) -> None:
        client = _make_client()
        client.experiment.update.side_effect = _api_error(404)
        result = await qbrix_pause_experiment(
            ExperimentIdInput(experiment_id="bad"), _make_ctx(client)
        )
        assert "error:" in result


# ---------------------------------------------------------------------------
# hot path — select / feedback
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestSelectFeedback:
    async def test_select_returns_arm_json(self) -> None:
        client = _make_client()
        client.agent.select.return_value = SelectResponse(
            arm=SelectedArm(id="arm-1", name="variant", index=1),
            request_id="req-abc",
            is_default=False,
        )
        result = await qbrix_select(
            SelectInput(experiment_id="exp-1", context_id="user-99"),
            _make_ctx(client),
        )
        parsed = json.loads(result)
        assert parsed["arm_name"] == "variant"
        assert parsed["request_id"] == "req-abc"
        assert parsed["is_default"] is False

    async def test_select_passes_context(self) -> None:
        client = _make_client()
        client.agent.select.return_value = SelectResponse(
            arm=SelectedArm(id="arm-0", name="control", index=0),
            request_id="req-xyz",
            is_default=False,
        )
        await qbrix_select(
            SelectInput(
                experiment_id="exp-1",
                context_id="user-1",
                context_vector=[0.1, 0.2],
                context_metadata={"plan": "premium"},
            ),
            _make_ctx(client),
        )
        _, kwargs = client.agent.select.call_args
        assert kwargs["context"]["id"] == "user-1"
        assert kwargs["context"]["vector"] == [0.1, 0.2]
        assert kwargs["context"]["metadata"] == {"plan": "premium"}

    async def test_select_omits_vector_if_none(self) -> None:
        client = _make_client()
        client.agent.select.return_value = SelectResponse(
            arm=SelectedArm(id="arm-0", name="control", index=0),
            request_id="req-xyz",
            is_default=False,
        )
        await qbrix_select(
            SelectInput(experiment_id="exp-1", context_id="user-1"),
            _make_ctx(client),
        )
        _, kwargs = client.agent.select.call_args
        assert "vector" not in kwargs["context"]
        assert "metadata" not in kwargs["context"]

    async def test_feedback_calls_sdk(self) -> None:
        client = _make_client()
        client.agent.feedback.return_value = None

        result = await qbrix_feedback(
            FeedbackInput(request_id="req-abc", reward=1.0),
            _make_ctx(client),
        )
        client.agent.feedback.assert_called_once_with(request_id="req-abc", reward=1.0)
        parsed = json.loads(result)
        assert parsed["accepted"] is True

    async def test_select_error(self) -> None:
        client = _make_client()
        client.agent.select.side_effect = QbrixConnectionError("down")
        result = await qbrix_select(
            SelectInput(experiment_id="exp-1", context_id="u-1"),
            _make_ctx(client),
        )
        assert "error:" in result


# ---------------------------------------------------------------------------
# power user — create pool
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestCreatePool:
    async def test_creates_pool_and_shows_ids(self) -> None:
        client = _make_client()
        client.pool.create.return_value = _pool("my-pool")

        params = CreatePoolInput(
            name="my-pool",
            arms=[ArmInput(name="control"), ArmInput(name="blue")],
        )
        result = await qbrix_create_pool(params, _make_ctx(client))

        client.pool.create.assert_called_once()
        assert "my-pool" in result
        assert "pool-1" in result
        assert "qbrix_create_experiment_from_pool" in result

    async def test_passes_arm_metadata(self) -> None:
        client = _make_client()
        client.pool.create.return_value = _pool()

        params = CreatePoolInput(
            name="hero",
            arms=[
                ArmInput(name="a", metadata={"color": "blue"}),
                ArmInput(name="b", metadata={"color": "red"}),
            ],
        )
        await qbrix_create_pool(params, _make_ctx(client))

        _, kwargs = client.pool.create.call_args
        assert kwargs["arms"][0]["metadata"] == {"color": "blue"}
