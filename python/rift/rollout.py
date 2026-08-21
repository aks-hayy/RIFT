"""Capacity-aware rollout and promotion policies for RIFT clusters."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from .benchmarking import regression_decision


JsonDict = dict[str, Any]


class RolloutEngine:
    def plan(
        self,
        *,
        service: str,
        current: JsonDict | None,
        desired: JsonDict,
        strategy: str = "canary",
        replicas: int = 1,
        max_unavailable: int = 0,
    ) -> JsonDict:
        if strategy not in ("recreate", "canary", "blue_green"):
            raise ValueError("strategy must be recreate, canary, or blue_green")
        if replicas <= 0:
            raise ValueError("replicas must be positive")
        if max_unavailable < 0 or max_unavailable >= replicas and replicas > 1:
            raise ValueError("max_unavailable must preserve at least one replica")
        changed = self._fingerprint(current or {}) != self._fingerprint(desired)
        steps = []
        if not changed:
            steps.append({"kind": "noop", "message": "desired launch plan already matches current"})
        elif strategy == "recreate":
            steps.extend(
                [
                    {"kind": "stop_old", "max_unavailable": replicas},
                    {"kind": "start_new", "replicas": replicas},
                    {"kind": "readiness_gate"},
                ]
            )
        elif strategy == "canary":
            steps.extend(
                [
                    {"kind": "start_canary", "replicas": 1},
                    {"kind": "readiness_gate"},
                    {"kind": "benchmark_gate"},
                    {"kind": "promote_remaining", "replicas": max(0, replicas - 1)},
                    {"kind": "retire_old", "max_unavailable": max_unavailable},
                ]
            )
        else:
            steps.extend(
                [
                    {"kind": "start_green", "replicas": replicas},
                    {"kind": "readiness_gate"},
                    {"kind": "benchmark_gate"},
                    {"kind": "switch_traffic"},
                    {"kind": "retain_blue_for_rollback"},
                ]
            )
        return {
            "schema_version": 1,
            "created_unix_seconds": time.time(),
            "service": service,
            "strategy": strategy,
            "changed": changed,
            "replicas": replicas,
            "max_unavailable": max_unavailable,
            "steps": steps,
            "requires_permission": "allow_deploy" if changed else None,
        }

    def promotion_gate(
        self,
        *,
        readiness: JsonDict,
        baseline_benchmark: JsonDict,
        candidate_benchmark: JsonDict,
    ) -> JsonDict:
        regression = regression_decision(baseline_benchmark, candidate_benchmark)
        healthy = bool(readiness.get("healthy") or readiness.get("ready"))
        reasons = []
        if not healthy:
            reasons.append("candidate failed readiness")
        reasons.extend(regression.get("reasons", []))
        return {
            "promote": healthy and bool(regression["promote"]),
            "rollback": not healthy or bool(regression["rollback"]),
            "readiness": readiness,
            "regression": regression,
            "reasons": reasons,
        }

    @staticmethod
    def _fingerprint(payload: JsonDict) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


__all__ = ["RolloutEngine"]
