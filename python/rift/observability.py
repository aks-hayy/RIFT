"""Durable operation timeline, retention, and Prometheus export for RIFT."""

from __future__ import annotations

import json
from pathlib import Path
import re
import threading
import time
from typing import Any


JsonDict = dict[str, Any]
_SECRET_RE = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+\-/=]+|((?:api[_-]?key|token|secret)\s*[=:]\s*)\S+")


class ObservabilityStore:
    def __init__(
        self,
        root: str | Path | None = None,
        *,
        data_root: str | Path | None = None,
        retention_seconds: int = 30 * 86400,
        max_events: int = 10000,
    ) -> None:
        self.root = Path(root) if root else Path.cwd()
        self.rift_dir = Path(data_root) if data_root is not None else self.root / ".rift"
        self.timeline_path = self.rift_dir / "observability" / "timeline.jsonl"
        self.retention_seconds = max(0, int(retention_seconds))
        self.max_events = max(100, int(max_events))
        self._lock = threading.Lock()

    def append(
        self,
        event: str,
        *,
        status: str = "info",
        service: str | None = None,
        node: str | None = None,
        details: JsonDict | None = None,
    ) -> JsonDict:
        record = {
            "created_unix_seconds": time.time(),
            "event": str(event),
            "status": str(status),
            "service": service,
            "node": node,
            "details": self.redact(details or {}),
        }
        self.timeline_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.timeline_path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(record, sort_keys=True, default=str) + "\n")
        return record

    def timeline(self, *, limit: int = 200, since: float | None = None) -> JsonDict:
        events = self._read_events()
        if since is not None:
            events = [event for event in events if float(event.get("created_unix_seconds") or 0.0) >= since]
        events = events[-max(1, int(limit)) :]
        return {"events": events, "count": len(events), "path": str(self.timeline_path)}

    def prune(self, *, now: float | None = None) -> JsonDict:
        current = time.time() if now is None else float(now)
        cutoff = current - self.retention_seconds if self.retention_seconds else 0.0
        original = self._read_events()
        kept = [event for event in original if float(event.get("created_unix_seconds") or 0.0) >= cutoff]
        kept = kept[-self.max_events :]
        self.timeline_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.timeline_path.with_suffix(".jsonl.tmp")
        with self._lock, temporary.open("w", encoding="utf-8") as output:
            for event in kept:
                output.write(json.dumps(event, sort_keys=True, default=str) + "\n")
        temporary.replace(self.timeline_path)
        return {"removed": len(original) - len(kept), "retained": len(kept), "cutoff": cutoff}

    def snapshot(self, *, state: JsonDict, gateway: JsonDict, incidents: JsonDict) -> JsonDict:
        services = state.get("services", {}) if isinstance(state, dict) else {}
        statuses: dict[str, int] = {}
        restarts = 0
        for service in services.values():
            status = str(service.get("status") or "unknown")
            statuses[status] = statuses.get(status, 0) + 1
            restarts += int((service.get("supervisor") or {}).get("restart_count") or 0)
        gateway_metrics = gateway.get("metrics", {}) if isinstance(gateway, dict) else {}
        return {
            "schema_version": 1,
            "created_unix_seconds": time.time(),
            "services_total": len(services),
            "service_statuses": statuses,
            "restart_count": restarts,
            "incident_count": len(incidents.get("incidents", [])) if isinstance(incidents, dict) else 0,
            "gateway": {
                "requests_total": int(gateway_metrics.get("requests_total") or 0),
                "requests_active": int(gateway_metrics.get("requests_active") or 0),
                "requests_failed": int(gateway_metrics.get("requests_failed") or 0),
                "average_latency_seconds": gateway_metrics.get("average_latency_seconds"),
            },
        }

    def prometheus(self, snapshot: JsonDict) -> str:
        lines = [
            "# HELP rift_services_total Number of RIFT-managed services.",
            "# TYPE rift_services_total gauge",
            f"rift_services_total {int(snapshot.get('services_total') or 0)}",
            "# HELP rift_service_restarts_total Supervisor restart count.",
            "# TYPE rift_service_restarts_total counter",
            f"rift_service_restarts_total {int(snapshot.get('restart_count') or 0)}",
            "# HELP rift_incidents_total Persisted incident count.",
            "# TYPE rift_incidents_total gauge",
            f"rift_incidents_total {int(snapshot.get('incident_count') or 0)}",
        ]
        for status, count in sorted((snapshot.get("service_statuses") or {}).items()):
            safe = re.sub(r"[^A-Za-z0-9_]", "_", str(status))
            lines.append(f'rift_services_status{{status="{safe}"}} {int(count)}')
        gateway = snapshot.get("gateway") or {}
        for key in ("requests_total", "requests_active", "requests_failed"):
            lines.append(f"rift_gateway_{key} {int(gateway.get(key) or 0)}")
        latency = gateway.get("average_latency_seconds")
        if latency is not None:
            lines.append(f"rift_gateway_average_latency_seconds {float(latency):.9f}")
        return "\n".join(lines) + "\n"

    def redact(self, value: Any) -> Any:
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if any(token in str(key).lower() for token in ("secret", "token", "password", "api_key", "authorization")):
                    result[key] = "[REDACTED]"
                else:
                    result[key] = self.redact(item)
            return result
        if isinstance(value, list):
            return [self.redact(item) for item in value]
        if isinstance(value, tuple):
            return [self.redact(item) for item in value]
        if isinstance(value, str):
            return _SECRET_RE.sub(lambda match: (match.group(1) or match.group(2) or "") + "[REDACTED]", value)
        return value

    def _read_events(self) -> list[JsonDict]:
        if not self.timeline_path.is_file():
            return []
        events = []
        try:
            lines = self.timeline_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        for line in lines:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
        return events


__all__ = ["ObservabilityStore"]
