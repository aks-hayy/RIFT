"""Persistent desired-state deployment lifecycle for mesh services."""

from __future__ import annotations

import json
import secrets
import time
from pathlib import Path


class DeploymentManager:
    def __init__(self, path: Path | str, *, clock=time.time):
        self.path = Path(path)
        self.clock = clock
        self._state = self._load()

    def _load(self) -> dict[str, object]:
        if not self.path.is_file():
            return {"schema_version": 1, "deployments": {}}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"deployment state is unreadable: {self.path}") from exc
        if not isinstance(value, dict) or int(value.get("schema_version") or 0) != 1:
            raise RuntimeError("unsupported deployment state schema")
        value.setdefault("deployments", {})
        return value

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        pending = self.path.with_suffix(self.path.suffix + ".tmp")
        pending.write_text(json.dumps(self._state, indent=2, sort_keys=True), encoding="utf-8")
        pending.replace(self.path)

    def _record(self, service_id: str) -> dict[str, object] | None:
        deployments = self._state["deployments"]
        assert isinstance(deployments, dict)
        value = deployments.get(service_id)
        return value if isinstance(value, dict) else None

    def deploy(self, service_id: str, *, revision: str, replicas: int = 1, operation_id: str | None = None) -> dict[str, object]:
        service_id, revision = self._required(service_id, revision)
        if replicas < 1:
            raise ValueError("replicas must be positive")
        current = self._record(service_id)
        if current and current.get("status") == "RUNNING" and current.get("active_revision") == revision and int(current.get("desired_replicas") or 0) == replicas:
            return dict(current)
        generation = int(current.get("generation") or 0) + 1 if current else 1
        history = list(current.get("revision_history") or []) if current else []
        if revision not in history:
            history.append(revision)
        record = {
            "service_id": service_id,
            "active_revision": revision,
            "desired_revision": revision,
            "desired_replicas": int(replicas),
            "status": "RUNNING",
            "generation": generation,
            "operation_id": operation_id or f"op-{secrets.token_hex(8)}",
            "updated_at": float(self.clock()),
            "revision_history": history[-20:],
            "reconcile_required": True,
        }
        self._put(service_id, record)
        return dict(record)

    def terminate(self, service_id: str, *, operation_id: str | None = None) -> dict[str, object]:
        record = self._require(service_id)
        if record.get("status") == "STOPPED":
            return dict(record)
        record["status"] = "STOPPED"
        record["desired_replicas"] = 0
        record["generation"] = int(record.get("generation") or 0) + 1
        record["operation_id"] = operation_id or f"op-{secrets.token_hex(8)}"
        record["updated_at"] = float(self.clock())
        record["reconcile_required"] = True
        self._put(service_id, record)
        return dict(record)

    def rollback(self, service_id: str, *, revision: str | None = None, operation_id: str | None = None) -> dict[str, object]:
        record = self._require(service_id)
        history = list(record.get("revision_history") or [])
        target = revision or (history[-2] if len(history) >= 2 else None)
        if not target:
            raise ValueError("no previous revision is available for rollback")
        if target not in history:
            raise KeyError(f"revision is not in deployment history: {target}")
        replicas = max(1, int(record.get("desired_replicas") or 1))
        return self.deploy(service_id, revision=target, replicas=replicas, operation_id=operation_id)

    def scale(self, service_id: str, *, replicas: int, operation_id: str | None = None) -> dict[str, object]:
        if replicas < 1:
            raise ValueError("replicas must be positive")
        record = self._require(service_id)
        if record.get("status") == "STOPPED":
            raise RuntimeError("cannot scale a stopped service")
        if int(record.get("desired_replicas") or 0) == replicas:
            return dict(record)
        record["desired_replicas"] = int(replicas)
        record["generation"] = int(record.get("generation") or 0) + 1
        record["operation_id"] = operation_id or f"op-{secrets.token_hex(8)}"
        record["updated_at"] = float(self.clock())
        record["reconcile_required"] = True
        self._put(service_id, record)
        return dict(record)

    def reconcile(self, service_id: str, nodes: list[dict[str, object]]) -> dict[str, object]:
        record = self._require(service_id)
        desired = int(record.get("desired_replicas") or 0)
        eligible = sorted(
            {
                str(node.get("node_id"))
                for node in nodes
                if node.get("node_id")
                and bool(node.get("healthy", True))
                and bool(node.get("compute_shared", True))
            }
        )
        target = eligible[:desired] if record.get("status") != "STOPPED" else []
        previous = [str(item) for item in record.get("assigned_nodes") or []]
        actions: list[dict[str, object]] = []
        for node_id in target:
            if node_id not in previous:
                actions.append({"action": "start", "node_id": node_id, "revision": record.get("active_revision")})
        for node_id in previous:
            if node_id not in target:
                actions.append({"action": "stop", "node_id": node_id, "revision": record.get("active_revision")})
        record["assigned_nodes"] = target
        record["status"] = "STOPPED" if desired == 0 else ("RUNNING" if len(target) >= desired else "DEGRADED")
        record["reconcile_required"] = bool(actions)
        record["updated_at"] = float(self.clock())
        self._put(service_id, record)
        return {"service_id": service_id, "status": record["status"], "desired_replicas": desired, "assigned_nodes": target, "actions": actions, "generation": record.get("generation")}

    def status(self, service_id: str | None = None) -> dict[str, object] | list[dict[str, object]]:
        deployments = self._state["deployments"]
        assert isinstance(deployments, dict)
        if service_id is not None:
            return dict(self._require(service_id))
        return [dict(deployments[key]) for key in sorted(deployments) if isinstance(deployments[key], dict)]

    def _require(self, service_id: str) -> dict[str, object]:
        value = self._record(str(service_id))
        if value is None:
            raise KeyError(f"unknown deployment service: {service_id}")
        return value

    def _put(self, service_id: str, record: dict[str, object]) -> None:
        deployments = self._state["deployments"]
        assert isinstance(deployments, dict)
        deployments[service_id] = record
        self._save()

    @staticmethod
    def _required(service_id: str, revision: str) -> tuple[str, str]:
        service_id, revision = str(service_id or "").strip(), str(revision or "").strip()
        if not service_id or not revision:
            raise ValueError("service_id and revision are required")
        return service_id, revision


__all__ = ["DeploymentManager"]
