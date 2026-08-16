"""Per-RPC request builders and response converters for the gRPC transport.

Each handler is a triple ``(build_request, stub_attr, convert_response)``:
  - build_request(body, params, path_params) → proto request message
  - stub_attr: attribute name on ``proxy_pb2_grpc.ProxyServiceStub``
  - convert_response(proto_resp, path_params) → dict (Pydantic-shaped)

Splitting this from the transport class itself keeps the sync/async dispatchers
identical except for the actual ``stub.<Method>(...)`` call (sync vs await).
"""

from __future__ import annotations

from typing import Any
from typing import Callable
from typing import NamedTuple

from qbrix._transport._grpc._convert import arms_from_dicts
from qbrix._transport._grpc._convert import context_from_dict
from qbrix._transport._grpc._convert import experiment_detail_to_dict
from qbrix._transport._grpc._convert import experiment_to_dict
from qbrix._transport._grpc._convert import gate_config_from_dict
from qbrix._transport._grpc._convert import gate_config_to_dict
from qbrix._transport._grpc._convert import policy_params_to_struct
from qbrix._transport._grpc._convert import policy_to_dict
from qbrix._transport._grpc._convert import pool_to_dict
from qbrix._transport._grpc._convert import select_response_to_dict
from qbrix._transport._grpc._proto import proxy_pb2


class Handler(NamedTuple):
    build_request: Callable[[dict[str, Any], dict[str, Any], dict[str, str]], Any]
    stub_attr: str
    convert_response: Callable[[Any, dict[str, str]], dict[str, Any] | None]


def _experiment_response_to_dict(resp: Any) -> dict[str, Any]:
    """Flatten {experiment, pool?, feature_gate?} into one dict.

    Used for CreateExperimentResponse, GetExperimentResponse, and
    UpdateExperimentResponse — all share the same field layout.
    """
    out = experiment_to_dict(resp.experiment)
    if resp.HasField("pool"):
        out["pool"] = pool_to_dict(resp.pool)
    if resp.HasField("feature_gate"):
        out["feature_gate"] = gate_config_to_dict(
            resp.feature_gate, experiment_id=resp.experiment.id
        )
    return out


def _build_create_experiment_request(
    body: dict[str, Any],
) -> proxy_pb2.CreateExperimentRequest:
    req = proxy_pb2.CreateExperimentRequest(
        name=body["name"],
        pool_id=body["pool_id"],
        policy=body.get("policy", ""),
        enabled=body.get("enabled", True),
    )
    # The proto field is map<string,string>; coerce values to strings.
    for k, v in (body.get("policy_params") or {}).items():
        req.policy_params[k] = str(v)
    if body.get("feature_gate") is not None:
        req.feature_gate.CopyFrom(gate_config_from_dict(body["feature_gate"]))
    return req


def _build_update_experiment_request(
    experiment_id: str, body: dict[str, Any]
) -> proxy_pb2.UpdateExperimentRequest:
    req = proxy_pb2.UpdateExperimentRequest(experiment_id=experiment_id)
    if "enabled" in body and body["enabled"] is not None:
        req.enabled = body["enabled"]
    for k, v in (body.get("policy_params") or {}).items():
        req.policy_params[k] = str(v)
    if body.get("feature_gate") is not None:
        req.feature_gate.CopyFrom(gate_config_from_dict(body["feature_gate"]))
    return req


def _build_list_experiments_request(
    params: dict[str, Any],
) -> proxy_pb2.ListExperimentsRequest:
    req = proxy_pb2.ListExperimentsRequest(
        limit=int(params.get("limit", 100)),
        offset=int(params.get("offset", 0)),
    )
    if params.get("search") is not None:
        req.search = str(params["search"])
    if params.get("enabled") is not None:
        req.enabled = bool(params["enabled"])
    return req


def _build_update_pool_request(
    pool_id: str, body: dict[str, Any]
) -> proxy_pb2.UpdatePoolRequest:
    req = proxy_pb2.UpdatePoolRequest(pool_id=pool_id)
    if body.get("name") is not None:
        req.name = body["name"]
    return req


def _build_list_policies_request(
    params: dict[str, Any],
) -> proxy_pb2.ListPoliciesRequest:
    req = proxy_pb2.ListPoliciesRequest()
    if params.get("reward_type") is not None:
        req.reward_type = str(params["reward_type"])
    return req


# Lambdas keep the table dense. Pylint/IDE warnings on "lambda" are acceptable here
# because each entry is a one-shot adapter — naming them would just add noise.
HANDLERS: dict[str, Handler] = {
    # ----- pools -----
    "create_pool": Handler(
        build_request=lambda body, params, pp: proxy_pb2.CreatePoolRequest(
            name=body["name"],
            arms=arms_from_dicts(body.get("arms", [])),
        ),
        stub_attr="CreatePool",
        convert_response=lambda resp, pp: pool_to_dict(resp.pool),
    ),
    "get_pool": Handler(
        build_request=lambda body, params, pp: proxy_pb2.GetPoolRequest(
            pool_id=pp["pool_id"]
        ),
        stub_attr="GetPool",
        convert_response=lambda resp, pp: pool_to_dict(resp.pool),
    ),
    "list_pools": Handler(
        build_request=lambda body, params, pp: proxy_pb2.ListPoolsRequest(
            limit=int(params.get("limit", 100)),
            offset=int(params.get("offset", 0)),
        ),
        stub_attr="ListPools",
        convert_response=lambda resp, pp: {
            "pools": [pool_to_dict(p) for p in resp.pools],
            "limit": resp.limit,
            "offset": resp.offset,
        },
    ),
    "update_pool": Handler(
        build_request=lambda body, params, pp: _build_update_pool_request(
            pp["pool_id"], body
        ),
        stub_attr="UpdatePool",
        convert_response=lambda resp, pp: pool_to_dict(resp.pool),
    ),
    "delete_pool": Handler(
        build_request=lambda body, params, pp: proxy_pb2.DeletePoolRequest(
            pool_id=pp["pool_id"]
        ),
        stub_attr="DeletePool",
        convert_response=lambda resp, pp: None,
    ),
    "list_pool_experiments": Handler(
        build_request=lambda body, params, pp: proxy_pb2.ListPoolExperimentsRequest(
            pool_id=pp["pool_id"]
        ),
        stub_attr="ListPoolExperiments",
        convert_response=lambda resp, pp: {
            "experiments": [experiment_detail_to_dict(d) for d in resp.items],
        },
    ),
    # ----- experiments -----
    "create_experiment": Handler(
        build_request=lambda body, params, pp: _build_create_experiment_request(body),
        stub_attr="CreateExperiment",
        convert_response=lambda resp, pp: _experiment_response_to_dict(resp),
    ),
    "get_experiment": Handler(
        build_request=lambda body, params, pp: proxy_pb2.GetExperimentRequest(
            experiment_id=pp["experiment_id"]
        ),
        stub_attr="GetExperiment",
        convert_response=lambda resp, pp: _experiment_response_to_dict(resp),
    ),
    "list_experiments": Handler(
        build_request=lambda body, params, pp: _build_list_experiments_request(params),
        stub_attr="ListExperiments",
        convert_response=lambda resp, pp: {
            "experiments": [experiment_detail_to_dict(d) for d in resp.items],
            "limit": resp.limit,
            "offset": resp.offset,
        },
    ),
    "update_experiment": Handler(
        build_request=lambda body, params, pp: _build_update_experiment_request(
            pp["experiment_id"], body
        ),
        stub_attr="UpdateExperiment",
        convert_response=lambda resp, pp: _experiment_response_to_dict(resp),
    ),
    "delete_experiment": Handler(
        build_request=lambda body, params, pp: proxy_pb2.DeleteExperimentRequest(
            experiment_id=pp["experiment_id"]
        ),
        stub_attr="DeleteExperiment",
        convert_response=lambda resp, pp: None,
    ),
    # ----- gates -----
    "create_gate_config": Handler(
        build_request=lambda body, params, pp: proxy_pb2.CreateGateConfigRequest(
            experiment_id=pp["experiment_id"],
            config=gate_config_from_dict(body),
        ),
        stub_attr="CreateGateConfig",
        convert_response=lambda resp, pp: gate_config_to_dict(
            resp.config, experiment_id=pp["experiment_id"]
        ),
    ),
    "get_gate_config": Handler(
        build_request=lambda body, params, pp: proxy_pb2.GetGateConfigRequest(
            experiment_id=pp["experiment_id"]
        ),
        stub_attr="GetGateConfig",
        convert_response=lambda resp, pp: gate_config_to_dict(
            resp.config, experiment_id=pp["experiment_id"]
        ),
    ),
    "update_gate_config": Handler(
        build_request=lambda body, params, pp: proxy_pb2.UpdateGateConfigRequest(
            experiment_id=pp["experiment_id"],
            config=gate_config_from_dict(body),
        ),
        stub_attr="UpdateGateConfig",
        convert_response=lambda resp, pp: gate_config_to_dict(
            resp.config, experiment_id=pp["experiment_id"]
        ),
    ),
    "patch_gate_config": Handler(
        build_request=lambda body, params, pp: proxy_pb2.UpdateGateConfigRequest(
            experiment_id=pp["experiment_id"],
            config=gate_config_from_dict(body),
            update_mask=list(body),
        ),
        stub_attr="UpdateGateConfig",
        convert_response=lambda resp, pp: gate_config_to_dict(
            resp.config, experiment_id=pp["experiment_id"]
        ),
    ),
    "delete_gate_config": Handler(
        build_request=lambda body, params, pp: proxy_pb2.DeleteGateConfigRequest(
            experiment_id=pp["experiment_id"]
        ),
        stub_attr="DeleteGateConfig",
        convert_response=lambda resp, pp: None,
    ),
    # ----- agent -----
    "select": Handler(
        build_request=lambda body, params, pp: proxy_pb2.SelectRequest(
            experiment_id=body["experiment_id"],
            context=context_from_dict(body.get("context") or {}),
        ),
        stub_attr="Select",
        convert_response=lambda resp, pp: select_response_to_dict(resp),
    ),
    "feedback": Handler(
        build_request=lambda body, params, pp: proxy_pb2.FeedbackRequest(
            request_id=body["request_id"],
            reward=float(body["reward"]),
        ),
        stub_attr="Feedback",
        convert_response=lambda resp, pp: None,
    ),
    # ----- policies -----
    "list_policies": Handler(
        build_request=lambda body, params, pp: _build_list_policies_request(params),
        stub_attr="ListPolicies",
        convert_response=lambda resp, pp: {
            "policies": [policy_to_dict(p) for p in resp.policies],
        },
    ),
}


# Silence unused-import warning — kept so policy_params_to_struct is reachable for
# future use (currently unused because CreateExperimentRequest only has map<str,str>).
_ = policy_params_to_struct


__all__ = ["HANDLERS", "Handler"]
