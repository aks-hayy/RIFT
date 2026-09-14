"""Explicit authority for autonomous execution, independent of workload NLP.

These records authorize bounded actions; they neither execute them nor certify
hardware. A saved policy is an upper bound. Each approved run freezes a narrower
envelope, including exact enrolled-node/device identifiers.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping


ACTIONS = frozenset({"download", "install", "temporary_launch", "restart", "promote", "remote_execution", "cleanup"})
LIMITS = frozenset({"exploration_seconds", "max_artifacts", "tuning_candidates", "per_artifact_bytes", "total_download_bytes"})


def default_execution_policy(*, target: str = "local") -> dict[str, Any]:
    """Return a conservative, editable policy template for the easy path.

    No action is enabled by default; the user must explicitly select every
    permission in the approval screen.
    """
    return {
        "schema_version": 1,
        "actions": {action: False for action in sorted(ACTIONS)},
        "targets": [target],
        "sources": ["huggingface"],
        "licenses": ["Apache-2.0"],
        "network": "approved_sources",
        "limits": {
            "exploration_seconds": 3600,
            "max_artifacts": 3,
            "tuning_candidates": 24,
            "per_artifact_bytes": 12 * 1024**3,
            "total_download_bytes": 36 * 1024**3,
        },
        "allow_quantization_alternatives": False,
        "exposure": "loopback",
        "operations_mode": "recover",
    }


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _exact_fields(value: Any, fields: set[str] | frozenset[str], label: str) -> dict:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    if set(value) != fields:
        raise ValueError(f"{label}: missing {sorted(fields - set(value))}; unsupported {sorted(set(value) - fields)}")
    return dict(value)


def _names(value: Any, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise ValueError(f"{label} requires an explicit list")
    if any(not isinstance(item, str) or not item.strip() or item != item.strip() or item == "*" for item in value):
        raise ValueError(f"{label} requires exact nonempty identifiers, not wildcards")
    if len(set(value)) != len(value):
        raise ValueError(f"{label} contains duplicates")
    return sorted(value)


def validate_envelope(value: Mapping[str, Any]) -> dict[str, Any]:
    result = _exact_fields(value, {"schema_version", "actions", "targets", "sources", "licenses", "network", "limits", "allow_quantization_alternatives", "exposure", "operations_mode"}, "execution envelope")
    if type(result["schema_version"]) is not int or result["schema_version"] != 1:
        raise ValueError("unsupported execution envelope version")
    actions = _exact_fields(result["actions"], ACTIONS, "actions")
    if any(type(enabled) is not bool for enabled in actions.values()):
        raise ValueError("every permission must be an explicit boolean")
    result["actions"] = actions
    result["targets"] = _names(result["targets"], "targets")
    result["sources"] = _names(result["sources"], "sources", allow_empty=True)
    result["licenses"] = _names(result["licenses"], "licenses", allow_empty=True)
    limits = _exact_fields(result["limits"], LIMITS, "limits")
    for name, number in limits.items():
        if type(number) is not int or number < (0 if name.endswith("bytes") else 1):
            raise ValueError(f"limits.{name} must be an explicit nonnegative integer (positive for time/counts)")
    if limits["per_artifact_bytes"] > limits["total_download_bytes"]:
        raise ValueError("per-artifact bytes cannot exceed total download bytes")
    result["limits"] = limits
    if result["network"] not in {"offline", "approved_sources"}:
        raise ValueError("network must be offline or approved_sources")
    if result["network"] == "offline" and (actions["download"] or actions["install"] or limits["total_download_bytes"]):
        raise ValueError("offline envelope cannot authorize network downloads/installations")
    if actions["download"] and not result["sources"]:
        raise ValueError("download permission requires approved sources")
    if type(result["allow_quantization_alternatives"]) is not bool:
        raise ValueError("quantization alternatives require an explicit boolean")
    if result["exposure"] not in {"loopback", "authenticated_pool"}:
        raise ValueError("unsupported endpoint exposure")
    if result["operations_mode"] not in {"recover", "idle", "canary"}:
        raise ValueError("unsupported operations mode")
    return result


def require_within_policy(envelope: Mapping[str, Any], policy: Mapping[str, Any]) -> dict[str, Any]:
    requested, ceiling = validate_envelope(envelope), validate_envelope(policy)
    for action in ACTIONS:
        if requested["actions"][action] and not ceiling["actions"][action]:
            raise PermissionError(f"policy does not authorize {action}")
    for name in ("targets", "sources", "licenses"):
        if not set(requested[name]).issubset(ceiling[name]):
            raise PermissionError(f"requested {name} escape saved policy")
    for name in LIMITS:
        if requested["limits"][name] > ceiling["limits"][name]:
            raise PermissionError(f"requested {name} exceeds policy limit")
    if ceiling["network"] == "offline" and requested["network"] != "offline":
        raise PermissionError("cannot relax offline policy")
    if requested["allow_quantization_alternatives"] and not ceiling["allow_quantization_alternatives"]:
        raise PermissionError("policy does not authorize quantization alternatives")
    if ceiling["exposure"] == "loopback" and requested["exposure"] != "loopback":
        raise PermissionError("cannot broaden endpoint exposure")
    # Autonomy modes are choices, not an ordinal permission ladder.
    if requested["operations_mode"] not in {"recover", ceiling["operations_mode"]}:
        raise PermissionError("operations mode requires a new policy approval")
    return requested


def validate_workload_contract(value: Mapping[str, Any]) -> dict[str, Any]:
    """Strict executable subset for the first text workload pack.

    Draft compilers may preserve unsupported fields outside this contract and
    ask questions. They cannot drop them to obtain an approvable contract.
    Numeric requirements are never accepted without units/meaning in the schema.
    """
    result = _exact_fields(value, {"schema_version", "task", "objective", "performance", "quality", "capabilities", "policies", "service"}, "workload contract")
    if type(result["schema_version"]) is not int or result["schema_version"] != 1:
        raise ValueError("unsupported workload contract version")
    if result["task"] not in {"chat", "coding", "documents", "rag"} or result["objective"] not in {"balanced", "speed", "cost"}:
        raise ValueError("unsupported task or objective")
    perf = _exact_fields(result["performance"], {"min_decode_tps", "decode_scope", "max_ttft_ms", "ttft_percentile", "context_tokens", "concurrency", "request_rate"}, "performance")
    for key in ("context_tokens", "concurrency"):
        if type(perf[key]) is not int or perf[key] < 1:
            raise ValueError(f"{key} requires a positive integer")
    for key in ("min_decode_tps", "max_ttft_ms", "request_rate"):
        number = perf[key]
        if number is not None and (type(number) not in (int, float) or not math.isfinite(number) or number <= 0):
            raise ValueError(f"{key} must be positive and finite, or null")
    if perf["decode_scope"] not in {"per_request", "aggregate"}:
        raise ValueError("decode scope must be reviewed explicitly")
    if perf["ttft_percentile"] != 95 or type(perf["ttft_percentile"]) is not int:
        raise ValueError("v1 TTFT acceptance supports reviewed p95 only")
    quality = _exact_fields(result["quality"], {"suite_id", "suite_version", "minimum_score", "required_cases"}, "quality")
    if any(not isinstance(quality[k], str) or not quality[k].strip() for k in ("suite_id", "suite_version")):
        raise ValueError("quality floor requires a versioned evaluation suite")
    floor = quality["minimum_score"]
    if type(floor) not in (int, float) or not math.isfinite(floor) or not 0 <= floor <= 1:
        raise ValueError("quality floor must be finite in [0, 1]")
    quality["required_cases"] = _names(quality["required_cases"], "required_cases")
    caps = _exact_fields(result["capabilities"], {"tool_calling", "structured_output"}, "capabilities")
    if any(type(v) is not bool for v in caps.values()):
        raise ValueError("capabilities require explicit booleans")
    policies = _exact_fields(result["policies"], {"network", "backend", "model_family"}, "policies")
    if policies["network"] not in {"offline", "approved_sources"}:
        raise ValueError("invalid workload network policy")
    for key in ("backend", "model_family"):
        if policies[key] is not None and (not isinstance(policies[key], str) or not policies[key].strip()):
            raise ValueError(f"{key} must be null or an exact identifier")
    service = _exact_fields(result["service"], {"name"}, "service")
    if not isinstance(service["name"], str) or not service["name"].strip():
        raise ValueError("service name is required")
    # Copy through canonical JSON: caller mutation cannot change a stored value.
    return json.loads(canonical_json({**result, "quality": quality}))
