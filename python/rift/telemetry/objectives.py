"""Metric-agnostic service objective normalization and evaluation."""

from __future__ import annotations

from collections import deque
import math
import statistics
import time
from typing import Any, Iterable, Mapping


OPERATORS = frozenset({">=", "<=", ">", "<", "=="})
AGGREGATIONS = frozenset({"latest", "average", "min", "max", "p95", "p99", "ratio"})


def _number(value: Any, *, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"objective {field} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"objective {field} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"objective {field} must be finite")
    return result


def normalize_objectives(raw: Any) -> list[dict[str, Any]]:
    """Validate and normalize a list of objective definitions."""

    if raw in (None, ""):
        return []
    if isinstance(raw, Mapping):
        raw = raw.get("objectives", raw.get("items", []))
    if not isinstance(raw, list):
        raise ValueError("monitoring objectives must be an array")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise ValueError(f"objective {index} must be an object")
        objective_id = str(item.get("id") or item.get("name") or "").strip()
        metric = str(item.get("metric") or "").strip()
        if not objective_id:
            raise ValueError(f"objective {index} requires id")
        if objective_id in seen:
            raise ValueError(f"duplicate objective id: {objective_id}")
        seen.add(objective_id)
        if not metric:
            raise ValueError(f"objective {objective_id} requires metric")
        target = item.get("target")
        target_map = target if isinstance(target, Mapping) else {}
        operator = str(item.get("operator") or target_map.get("operator") or "<=").strip()
        if operator not in OPERATORS:
            raise ValueError(f"objective {objective_id} operator must be one of {sorted(OPERATORS)}")
        threshold_value = item.get("threshold", target_map.get("value"))
        if threshold_value is None:
            raise ValueError(f"objective {objective_id} requires threshold")
        aggregation = str(item.get("aggregation") or "latest").strip().lower()
        if aggregation not in AGGREGATIONS:
            raise ValueError(f"objective {objective_id} aggregation must be one of {sorted(AGGREGATIONS)}")
        window = _number(item.get("window_seconds", item.get("window", 0.0)), field=f"{objective_id}.window_seconds")
        if window < 0:
            raise ValueError(f"objective {objective_id} window_seconds cannot be negative")
        consecutive = item.get("consecutive_breaches", item.get("failure_threshold", 1))
        recovery_consecutive = item.get("recovery_consecutive", item.get("clear_threshold", 1))
        try:
            consecutive = int(consecutive)
            recovery_consecutive = int(recovery_consecutive)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"objective {objective_id} consecutive thresholds must be integers") from exc
        if consecutive < 1 or recovery_consecutive < 1:
            raise ValueError(f"objective {objective_id} consecutive thresholds must be positive")
        warning = item.get("warning_threshold")
        recovery = item.get("recovery_threshold")
        normalized = {
            "id": objective_id,
            "metric": metric,
            "operator": operator,
            "threshold": _number(threshold_value, field=f"{objective_id}.threshold"),
            "aggregation": aggregation,
            "window_seconds": window,
            "consecutive_breaches": consecutive,
            "recovery_consecutive": recovery_consecutive,
            "warning_threshold": None if warning is None else _number(warning, field=f"{objective_id}.warning_threshold"),
            "recovery_threshold": None if recovery is None else _number(recovery, field=f"{objective_id}.recovery_threshold"),
            "alerts": [str(value).strip() for value in (item.get("alerts") or []) if str(value).strip()],
        }
        result.append(normalized)
    return result


def required_metrics(objectives: Iterable[Mapping[str, Any]]) -> set[str]:
    """Return canonical metric ids referenced by objectives."""

    return {str(item.get("metric") or "").strip() for item in objectives if str(item.get("metric") or "").strip()}


def _lookup(sample: Mapping[str, Any], metric: str) -> Any:
    if metric in sample:
        return sample[metric]
    current: Any = sample
    for part in metric.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _compare(value: float, operator: str, threshold: float) -> bool:
    return {
        ">=": value >= threshold,
        "<=": value <= threshold,
        ">": value > threshold,
        "<": value < threshold,
        "==": math.isclose(value, threshold, rel_tol=1e-12, abs_tol=1e-12),
    }[operator]


def _aggregate(values: list[float], aggregation: str) -> float:
    if not values:
        raise ValueError("cannot aggregate an empty objective window")
    if aggregation in {"latest", "ratio"}:
        return values[-1]
    if aggregation == "average":
        return statistics.fmean(values)
    if aggregation == "min":
        return min(values)
    if aggregation == "max":
        return max(values)
    ordered = sorted(values)
    percentile = 0.95 if aggregation == "p95" else 0.99
    rank = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[rank]


class ObjectiveEvaluator:
    """Evaluate normalized objectives over a bounded sample history."""

    def __init__(self, objectives: Iterable[Mapping[str, Any]]) -> None:
        self.objectives = normalize_objectives(list(objectives))
        self._windows: dict[str, deque[tuple[float, float]]] = {
            item["id"]: deque(maxlen=10_000) for item in self.objectives
        }
        self._state: dict[str, dict[str, Any]] = {
            item["id"]: {
                "status": "unknown",
                "candidate_status": None,
                "candidate_count": 0,
                "recovery_count": 0,
                "last": None,
                "sample_count": 0,
            }
            for item in self.objectives
        }
        self._events: list[dict[str, Any]] = []

    def evaluate(self, sample: Mapping[str, Any], *, observed_at: float | None = None) -> list[dict[str, Any]]:
        at = float(observed_at if observed_at is not None else sample.get("observed_at", time.time()))
        results: list[dict[str, Any]] = []
        for objective in self.objectives:
            objective_id = objective["id"]
            metric = objective["metric"]
            state = self._state[objective_id]
            raw = _lookup(sample, metric)
            numeric = None
            if isinstance(raw, (int, float)) and not isinstance(raw, bool) and math.isfinite(float(raw)):
                numeric = float(raw)
                window = self._windows[objective_id]
                window.append((at, numeric))
                max_age = float(objective["window_seconds"])
                if max_age > 0:
                    while window and at - window[0][0] > max_age:
                        window.popleft()
                state["sample_count"] = len(window)
            if numeric is None:
                result = self._result(objective, state, at, status="unknown", value=None, reason="metric_unavailable")
                state["candidate_status"] = None
                state["candidate_count"] = 0
                state["recovery_count"] = 0
                if state["status"] != "unknown":
                    self._transition(objective, state, result)
                results.append(result)
                continue
            values = [value for _, value in self._windows[objective_id]]
            value = _aggregate(values, objective["aggregation"])
            target_status = "pass"
            if objective["warning_threshold"] is not None:
                warning_met = _compare(value, objective["operator"], objective["warning_threshold"])
                if not warning_met:
                    target_status = "warning"
            if not _compare(value, objective["operator"], objective["threshold"]):
                target_status = "breach"
            current = state["status"]
            if target_status == "pass":
                recovery_threshold = objective["recovery_threshold"]
                recovery_met = True if recovery_threshold is None else _compare(value, objective["operator"], recovery_threshold)
                if current in {"warning", "breach"} and not recovery_met:
                    target_status = current
                    state["recovery_count"] = 0
                elif current in {"warning", "breach"}:
                    state["recovery_count"] += 1
                    if state["recovery_count"] < objective["recovery_consecutive"]:
                        target_status = current
                    else:
                        state["recovery_count"] = 0
            else:
                state["recovery_count"] = 0
            if target_status != current and target_status in {"warning", "breach"}:
                # A critical breach can be downgraded to warning as soon as the
                # value crosses the warning boundary; dwell applies to entering
                # an incident from a passing state, not to severity recovery.
                if current == "breach" and target_status == "warning":
                    state["candidate_status"] = None
                    state["candidate_count"] = 0
                elif state["candidate_status"] == target_status:
                    state["candidate_count"] += 1
                else:
                    state["candidate_status"] = target_status
                    state["candidate_count"] = 1
                if current != "breach" and state["candidate_count"] < objective["consecutive_breaches"]:
                    target_status = current if current != "unknown" else "pass"
                elif current != "breach":
                    state["candidate_status"] = None
                    state["candidate_count"] = 0
            else:
                state["candidate_status"] = None
                state["candidate_count"] = 0
            result = self._result(objective, state, at, status=target_status, value=value, reason="threshold_evaluated")
            if target_status != current:
                self._transition(objective, state, result)
            results.append(result)
        return results

    def _result(self, objective: Mapping[str, Any], state: Mapping[str, Any], at: float, *, status: str, value: float | None, reason: str) -> dict[str, Any]:
        return {
            "objective_id": objective["id"],
            "metric": objective["metric"],
            "status": status,
            "value": value,
            "operator": objective["operator"],
            "threshold": objective["threshold"],
            "warning_threshold": objective["warning_threshold"],
            "aggregation": objective["aggregation"],
            "window_seconds": objective["window_seconds"],
            "sample_count": int(state.get("sample_count") or 0),
            "observed_at": at,
            "reason": reason,
        }

    def _transition(self, objective: Mapping[str, Any], state: dict[str, Any], result: dict[str, Any]) -> None:
        previous = state["status"]
        state["status"] = result["status"]
        state["last"] = dict(result)
        event = {**result, "previous_status": previous, "event": "objective_status_changed"}
        self._events.append(event)

    def snapshot(self) -> list[dict[str, Any]]:
        return [dict(state["last"] or {
            "objective_id": objective["id"],
            "metric": objective["metric"],
            "status": state["status"],
            "value": None,
            "operator": objective["operator"],
            "threshold": objective["threshold"],
            "warning_threshold": objective["warning_threshold"],
            "aggregation": objective["aggregation"],
            "window_seconds": objective["window_seconds"],
            "sample_count": 0,
            "reason": "not_evaluated",
        }) for objective in self.objectives for state in [self._state[objective["id"]]]]

    def events(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._events]


__all__ = ["AGGREGATIONS", "OPERATORS", "ObjectiveEvaluator", "normalize_objectives", "required_metrics"]
