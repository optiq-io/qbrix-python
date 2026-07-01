"""Per-shape converters between protobuf messages and the dict shapes the
SDK's Pydantic models consume.

We do NOT use ``google.protobuf.json_format.MessageToDict`` here. Explicit
converters give us:
  - control over field renaming (e.g., schedule.start_timestamp_ms → schedule_start)
  - safe handling of ``HasField()`` for optional sub-messages
  - one place to read when a shape drifts

These mirror the canonical mappings in
``/Users/eskinmi/Dev/qbrix/svc/proxy/src/proxysvc/server.py``
(``_dict_to_pool``, ``_dict_to_experiment``, ``_proto_to_gate_config``,
``_config_to_proto_gate``), but in reverse — the server converts dict→proto,
the SDK converts proto→dict.
"""

from __future__ import annotations

import json
from datetime import datetime
from datetime import timezone
from typing import Any

from google.protobuf import json_format
from google.protobuf import struct_pb2

from qbrix._transport._grpc._proto import common_pb2
from qbrix._transport._grpc._proto import proxy_pb2

# ----- arms / pools -----------------------------------------------------------


def arm_to_dict(a: common_pb2.Arm) -> dict[str, Any]:
    return {
        "id": a.id,
        "name": a.name,
        "index": a.index,
        "is_active": a.is_active,
        "metadata": dict(a.metadata),
    }


def pool_to_dict(p: common_pb2.Pool) -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "created_at": p.created_at or None,
        "updated_at": p.updated_at or None,
        "arms": [arm_to_dict(a) for a in p.arms],
    }


def arms_from_dicts(arms: list[dict[str, Any]]) -> list[common_pb2.Arm]:
    """Build proto arms from the ArmCreate-shaped dicts the SDK sends.

    Used by CreatePool. ArmCreate only carries name + metadata; id/index are
    server-assigned. Metadata values are coerced to strings (proto map<str,str>).
    """
    out: list[common_pb2.Arm] = []
    for a in arms:
        meta = {k: str(v) for k, v in (a.get("metadata") or {}).items()}
        out.append(common_pb2.Arm(name=a["name"], metadata=meta))
    return out


# ----- experiments ------------------------------------------------------------


def _policy_params(e: common_pb2.Experiment) -> dict[str, Any]:
    """Prefer the full-fidelity Struct field; fall back to the string map."""
    if e.HasField("policy_params_json"):
        return json_format.MessageToDict(e.policy_params_json)
    return dict(e.policy_params)


def experiment_to_dict(e: common_pb2.Experiment) -> dict[str, Any]:
    return {
        "id": e.id,
        "name": e.name,
        "pool_id": e.pool_id,
        "policy": e.policy,
        "policy_params": _policy_params(e),
        "enabled": e.enabled,
        "created_at": e.created_at or None,
        "updated_at": e.updated_at or None,
    }


def experiment_detail_to_dict(d: proxy_pb2.ExperimentDetail) -> dict[str, Any]:
    """Flatten ExperimentDetail (experiment + pool + feature_gate) into the
    dict shape ``qbrix.model.Experiment`` expects."""
    out = experiment_to_dict(d.experiment)
    if d.HasField("pool"):
        out["pool"] = pool_to_dict(d.pool)
    if d.HasField("feature_gate"):
        out["feature_gate"] = gate_config_to_dict(
            d.feature_gate, experiment_id=d.experiment.id
        )
    return out


def policy_params_to_struct(params: dict[str, Any]) -> struct_pb2.Struct:
    """Build a Struct from a Pydantic policy_params dict (mixed-typed values)."""
    s = struct_pb2.Struct()
    if params:
        s.update(params)
    return s


# ----- policies ---------------------------------------------------------------


def _policy_param_to_dict(p: proxy_pb2.PolicyParam) -> dict[str, Any]:
    return {
        "name": p.name,
        "type": p.type,
        "required": p.required,
        # ``default`` is a google.protobuf.Value (the param default is Any|None).
        # MessageToDict unwraps the well-known type to a native scalar/None/list.
        "default": (
            json_format.MessageToDict(p.default) if p.HasField("default") else None
        ),
        "description": p.description,
        "constraints": dict(p.constraints),
    }


def policy_to_dict(p: proxy_pb2.Policy) -> dict[str, Any]:
    """Convert proto Policy → ``qbrix.model.Policy`` dict shape.

    Mirrors ``_policy_to_proto`` in
    ``/Users/eskinmi/Dev/qbrix/svc/proxy/src/proxysvc/server.py`` in reverse.
    """
    return {
        "name": p.name,
        "category": p.category,
        "reward_types": list(p.reward_types),
        "description": p.description,
        "user_params": [_policy_param_to_dict(pp) for pp in p.user_params],
    }


# ----- gate config ------------------------------------------------------------


def _ts_ms_to_iso(ts_ms: int) -> str:
    """milliseconds-since-epoch → ISO 8601 UTC string."""
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()


def _iso_to_ts_ms(iso: str) -> int:
    """ISO 8601 string → milliseconds-since-epoch (UTC)."""
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _rule_to_dict(r: proxy_pb2.RuleConfig) -> dict[str, Any]:
    value: Any = r.value
    if value:
        try:
            value = json.loads(r.value)
        except (json.JSONDecodeError, TypeError):
            pass
    return {
        "key": r.key,
        "operator": r.operator,
        "value": value,
        "arm_id": r.arm_id or None,
        "arm_name": None,  # not carried on the wire; server reads via arm_id
    }


def gate_config_to_dict(
    cfg: proxy_pb2.FeatureGateConfig, *, experiment_id: str
) -> dict[str, Any]:
    """Convert proto FeatureGateConfig → ``qbrix.model.GateConfig`` dict shape.

    ``experiment_id`` is injected from the request because it isn't carried
    inside the FeatureGateConfig message itself.
    """
    out: dict[str, Any] = {
        "experiment_id": experiment_id,
        "enabled": cfg.enabled,
        "rollout_percentage": cfg.rollout_percentage,
        "default_arm_id": cfg.default_arm_id or None,
        "default_arm_name": None,
        "timezone": cfg.timezone or "UTC",
        "rules": [_rule_to_dict(r) for r in cfg.rules],
    }
    if cfg.HasField("schedule"):
        if cfg.schedule.start_timestamp_ms:
            out["schedule_start"] = _ts_ms_to_iso(cfg.schedule.start_timestamp_ms)
        if cfg.schedule.end_timestamp_ms:
            out["schedule_end"] = _ts_ms_to_iso(cfg.schedule.end_timestamp_ms)
    if cfg.HasField("active_hours"):
        if cfg.active_hours.start:
            out["active_hours_start"] = cfg.active_hours.start
        if cfg.active_hours.end:
            out["active_hours_end"] = cfg.active_hours.end
    return out


def gate_config_from_dict(body: dict[str, Any]) -> proxy_pb2.FeatureGateConfig:
    """Build proto FeatureGateConfig from the SDK gate body dict."""
    cfg = proxy_pb2.FeatureGateConfig(
        enabled=body.get("enabled", True),
        rollout_percentage=float(body.get("rollout_percentage", 100.0)),
        default_arm_id=body.get("default_arm_id") or "",
        timezone=body.get("timezone", "UTC"),
    )
    if body.get("schedule_start"):
        cfg.schedule.start_timestamp_ms = _iso_to_ts_ms(body["schedule_start"])
    if body.get("schedule_end"):
        cfg.schedule.end_timestamp_ms = _iso_to_ts_ms(body["schedule_end"])
    if body.get("active_hours_start"):
        cfg.active_hours.start = body["active_hours_start"]
    if body.get("active_hours_end"):
        cfg.active_hours.end = body["active_hours_end"]
    for r in body.get("rules") or []:
        value = r.get("value")
        if not isinstance(value, str):
            value = json.dumps(value)
        cfg.rules.append(
            proxy_pb2.RuleConfig(
                key=r["key"],
                operator=r["operator"],
                value=value,
                arm_id=r.get("arm_id") or "",
            )
        )
    return cfg


# ----- agent ------------------------------------------------------------------


def context_from_dict(ctx: dict[str, Any]) -> common_pb2.Context:
    metadata = ctx.get("metadata") or {}
    return common_pb2.Context(
        id=ctx.get("id", ""),
        vector=list(ctx.get("vector") or []),
        metadata={k: str(v) for k, v in metadata.items()},
    )


def select_response_to_dict(r: proxy_pb2.SelectResponse) -> dict[str, Any]:
    return {
        "arm": {
            "id": r.arm.id,
            "name": r.arm.name,
            "index": r.arm.index,
        },
        # proto3 has no null; a paused experiment mints no token → empty string.
        # Normalize to None for parity with the HTTP transport.
        "request_id": r.request_id or None,
        "is_default": r.is_default,
    }


__all__ = [
    "arm_to_dict",
    "arms_from_dicts",
    "context_from_dict",
    "experiment_detail_to_dict",
    "experiment_to_dict",
    "gate_config_from_dict",
    "gate_config_to_dict",
    "policy_params_to_struct",
    "policy_to_dict",
    "pool_to_dict",
    "select_response_to_dict",
]
