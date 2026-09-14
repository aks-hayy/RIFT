"""Durable SQLite telemetry storage, rollups and completed reports."""

from __future__ import annotations

import json
import math
from functools import wraps
from pathlib import Path
import sqlite3
import statistics
import time
import threading
from typing import Any
import uuid

from .accounting import session_costs


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str, allow_nan=False)


def _serialized(method):
    """Serialize shared-connection transactions, including nested report reads."""
    @wraps(method)
    def call(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return call


HISTORY_METRICS = frozenset({
    "cpu_percent", "host_ram_pressure_percent", "gpu_utilization_percent",
    "gpu_temperature_c", "cpu_temperature_c", "gpu_power_watts",
    "gpu_memory_used_bytes", "host_ram_used_bytes", "ram_used_bytes",
    "gpu_vram_used_bytes", "gpu_vram_pressure_percent", "process_cpu_percent",
    "process_rss_bytes",
})


class TelemetryStore:
    def __init__(self, path: str | Path, *, raw_retention_seconds: float = 48 * 3600) -> None:
        self.path = Path(path)
        self._memory = str(path) == ":memory:"
        if not self._memory:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.raw_retention_seconds = raw_retention_seconds
        self._lock = threading.RLock()
        self.connection = sqlite3.connect(":memory:" if self._memory else str(self.path), timeout=30, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self._migrate()

    def _migrate(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY, service_name TEXT NOT NULL, node_id TEXT NOT NULL,
                pid INTEGER, started_at REAL NOT NULL, stopped_at REAL, status TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}', report_json TEXT
            );
            CREATE INDEX IF NOT EXISTS sessions_service_idx ON sessions(service_name, started_at DESC);
            CREATE TABLE IF NOT EXISTS samples (
                session_id TEXT NOT NULL, sequence INTEGER NOT NULL, observed_at REAL NOT NULL,
                payload_json TEXT NOT NULL, PRIMARY KEY(session_id, sequence),
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            );
            CREATE INDEX IF NOT EXISTS samples_time_idx ON samples(observed_at);
            CREATE TABLE IF NOT EXISTS signals (
                signal_id TEXT PRIMARY KEY, session_id TEXT, service_name TEXT, node_id TEXT,
                observed_at REAL NOT NULL, severity TEXT NOT NULL, resource TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS objective_events (
                event_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, service_name TEXT NOT NULL,
                node_id TEXT NOT NULL, observed_at REAL NOT NULL, objective_id TEXT NOT NULL,
                status TEXT NOT NULL, payload_json TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            );
            CREATE INDEX IF NOT EXISTS objective_events_session_idx ON objective_events(session_id, observed_at);
            CREATE INDEX IF NOT EXISTS objective_events_service_idx ON objective_events(service_name, observed_at);
            CREATE TABLE IF NOT EXISTS outbox (
                stream TEXT NOT NULL, sequence INTEGER NOT NULL, payload_json TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at REAL NOT NULL,
                acknowledged INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(stream, sequence)
            );
            """
        )
        self.connection.commit()

    @_serialized
    def close(self) -> None:
        try:
            self.connection.close()
        except sqlite3.ProgrammingError:
            pass

    def __del__(self) -> None:
        try:
            self.close()
        except sqlite3.Error:
            pass

    @_serialized
    def start_session(self, service_name: str, *, node_id: str = "local", pid: int | None = None, metadata: dict[str, Any] | None = None, started_at: float | None = None) -> dict[str, Any]:
        session_id = uuid.uuid4().hex
        started = float(time.time() if started_at is None else started_at)
        self.connection.execute(
            "INSERT INTO sessions(session_id,service_name,node_id,pid,started_at,status,metadata_json) VALUES(?,?,?,?,?,?,?)",
            (session_id, service_name, node_id, pid, started, "running", _json(metadata or {})),
        )
        self.connection.commit()
        return {"session_id": session_id, "service_name": service_name, "node_id": node_id, "pid": pid, "started_at": started, "status": "running"}

    @_serialized
    def active_session(self, service_name: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT * FROM sessions WHERE service_name=? AND status='running' ORDER BY started_at DESC LIMIT 1", (service_name,)).fetchone()
        return self._session(row) if row else None

    @_serialized
    def update_session_metadata(self, session_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Merge metadata into a session without changing its report history."""
        row = self.connection.execute(
            "SELECT * FROM sessions WHERE session_id=?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"telemetry session not found: {session_id}")
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"telemetry session metadata is invalid: {session_id}") from exc
        if not isinstance(metadata, dict):
            raise ValueError(f"telemetry session metadata is not an object: {session_id}")
        metadata.update(updates)
        self.connection.execute(
            "UPDATE sessions SET metadata_json=? WHERE session_id=?",
            (_json(metadata), session_id),
        )
        self.connection.commit()
        refreshed = self.connection.execute(
            "SELECT * FROM sessions WHERE session_id=?",
            (session_id,),
        ).fetchone()
        return self._session(refreshed) if refreshed else {}

    @_serialized
    def record_sample(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        observed_at = float(payload["observed_at"] if payload.get("observed_at") is not None else time.time())
        if not math.isfinite(observed_at):
            raise ValueError("observed_at must be finite")
        # Do not let forwarded payloads overwrite local sequence/session identity.
        payload = {k: v for k, v in payload.items() if k not in {"sequence", "session_id", "observed_at"}}
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            row = self.connection.execute("SELECT COALESCE(MAX(sequence), 0) AS sequence FROM samples WHERE session_id=?", (session_id,)).fetchone()
            sequence = int(row["sequence"] or 0) + 1
            self.connection.execute("INSERT INTO samples(session_id,sequence,observed_at,payload_json) VALUES(?,?,?,?)", (session_id, sequence, observed_at, _json(payload)))
        return {**payload, "session_id": session_id, "sequence": sequence, "observed_at": observed_at}

    @_serialized
    def series(self, session_id: str, *, since: float | None = None, until: float | None = None, limit: int = 20000, latest: bool = False) -> dict[str, Any]:
        if type(limit) is not int or not 1 <= limit <= 20000:
            raise ValueError("limit must be an integer between 1 and 20000")
        clauses = ["session_id=?"]
        params: list[Any] = [session_id]
        if since is not None:
            clauses.append("observed_at>=?"); params.append(float(since))
        if until is not None:
            clauses.append("observed_at<=?"); params.append(float(until))
        params.append(limit + 1)
        direction = "DESC" if latest else "ASC"
        rows = self.connection.execute(f"SELECT sequence,observed_at,payload_json FROM samples WHERE {' AND '.join(clauses)} ORDER BY observed_at {direction}, sequence {direction} LIMIT ?", params).fetchall()
        truncated = len(rows) > limit
        rows = rows[:limit]
        if latest:
            rows.reverse()
        return {"session_id": session_id, "sample_count": len(rows), "truncated": truncated, "samples": [self._point(row) for row in rows]}

    @staticmethod
    def _point(row) -> dict[str, Any]:
        return {**json.loads(row["payload_json"]), "sequence": int(row["sequence"]), "observed_at": row["observed_at"]}

    @_serialized
    def history(self, session_id: str, *, metric: str, since: float, until: float, buckets: int = 180) -> dict[str, Any]:
        """Bounded gauge buckets with explicit gaps; never averages percentiles.

        Resource samples describe the recorded session/node domain, not exclusive
        service consumption. Empty buckets stay null, including retention gaps.
        """
        if metric not in HISTORY_METRICS:
            raise ValueError("unsupported resource history metric")
        if not all(math.isfinite(v) for v in (since, until)) or until <= since or until - since > 48 * 3600:
            raise ValueError("history requires a finite positive range of at most 48 hours")
        if type(buckets) is not int or not 1 <= buckets <= 1200:
            raise ValueError("buckets must be an integer between 1 and 1200")
        width = (until - since) / buckets
        # JSON paths are chosen exclusively from the allowlist above. SQL performs
        # aggregation without sending every raw sample to the controller/UI.
        rows = self.connection.execute(
            "SELECT CAST((observed_at - ?) / ? AS INTEGER) AS bucket, "
            "COUNT(*) AS count, AVG(json_extract(payload_json, ?)) AS mean, "
            "MIN(json_extract(payload_json, ?)) AS minimum, MAX(json_extract(payload_json, ?)) AS maximum "
            "FROM samples WHERE session_id=? AND observed_at>=? AND observed_at<? "
            "AND json_type(payload_json, ?) IN ('integer', 'real') GROUP BY bucket",
            (since, width, *([f"$.{metric}"] * 3), session_id, since, until, f"$.{metric}"),
        ).fetchall()
        by_bucket = {row["bucket"]: dict(row) for row in rows}
        return {
            "schema_version": 1, "session_id": session_id, "metric": metric,
            "since": since, "until": until, "bucket_seconds": width,
            "source": "recorded_resource_samples", "aggregation": "sample_mean_min_max",
            "scope": "session_observed_resource_domain", "retention_seconds": self.raw_retention_seconds,
            "points": [{"observed_at": since + i * width, "count": by_bucket.get(i, {}).get("count", 0),
                        **{k: by_bucket.get(i, {}).get(k) for k in ("mean", "minimum", "maximum")}} for i in range(buckets)],
        }

    @_serialized
    def finish_session(
        self,
        session_id: str,
        *,
        stopped_at: float | None = None,
        status: str = "completed",
        objective_snapshot: list[dict[str, Any]] | None = None,
        objective_events: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if row is None:
            raise KeyError(f"telemetry session not found: {session_id}")
        stopped = float(stopped_at if stopped_at is not None else time.time())
        rows = self.connection.execute("SELECT sequence,observed_at,payload_json FROM samples WHERE session_id=? ORDER BY observed_at,sequence", (session_id,)).fetchall()
        points = [self._point(point) for point in rows]
        if objective_events is None:
            objective_events = [
                {
                    **item["payload"],
                    "event_id": item["event_id"],
                    "session_id": item["session_id"],
                    "service_name": item["service_name"],
                    "node_id": item["node_id"],
                }
                for item in self.list_objective_events(session_id=session_id, limit=10000)["events"]
            ]
        report = self._report(
            dict(row),
            points,
            stopped,
            objective_snapshot=objective_snapshot,
            objective_events=objective_events,
        )
        report["status"] = status
        self.connection.execute("UPDATE sessions SET stopped_at=?,status=?,report_json=? WHERE session_id=?", (stopped, status, _json(report), session_id))
        self.connection.commit()
        return report

    def _report(
        self,
        session: dict[str, Any],
        points: list[dict[str, Any]],
        stopped: float,
        *,
        objective_snapshot: list[dict[str, Any]] | None = None,
        objective_events: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        numeric: dict[str, list[tuple[float, float]]] = {}
        for point in points:
            for key, value in point.items():
                if key in {"observed_at", "sequence", "process_id"} or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    continue
                numeric.setdefault(key, []).append((float(point["observed_at"]), float(value)))
        metrics: dict[str, Any] = {}
        for key, values in numeric.items():
            numbers = [value for _, value in values]
            metrics[key] = {
                "average": self._weighted_average(values, stopped),
                "minimum": min(numbers),
                "maximum": max(numbers),
                "peak": max(numbers),
                "p50": statistics.median(numbers),
                "sample_count": len(numbers),
            }
        power = numeric.get("gpu_power_watts")
        if power:
            joules = 0.0
            for index, (at, watts) in enumerate(power):
                next_at = power[index + 1][0] if index + 1 < len(power) else stopped
                delta = next_at - at
                if 0.0 < delta <= 20.0:
                    joules += watts * delta
            metrics["gpu_energy_joules"] = {"average": joules, "minimum": joules, "maximum": joules, "peak": joules, "p50": joules, "sample_count": len(power), "estimated": joules}
        report = {
            "report_id": uuid.uuid4().hex,
            "session_id": session["session_id"],
            "service_name": session["service_name"],
            "node_id": session["node_id"],
            "started_at": session["started_at"],
            "stopped_at": stopped,
            "duration_seconds": max(0.0, stopped - float(session["started_at"])),
            "sample_count": len(points),
            "status": "completed",
            "metrics": metrics,
            "coverage": {"resource_samples": len(points), "traffic": "unknown unless observed through the RIFT gateway"},
            "objectives": list(objective_snapshot or []),
            "objective_events": list(objective_events or []),
            "generated_at": time.time(),
        }
        metadata = json.loads(session.get("metadata_json") or "{}") if session.get("metadata_json") else {}
        report["costs"] = session_costs(
            report,
            electricity_price_per_kwh=metadata.get("electricity_price_per_kwh"),
            compute_cost_per_node_hour=metadata.get("compute_cost_per_node_hour"),
        )
        return report

    @staticmethod
    def _weighted_average(values: list[tuple[float, float]], stopped: float) -> float:
        if len(values) < 2:
            return values[0][1] if values else 0.0
        total = 0.0; duration = 0.0
        for index, (at, value) in enumerate(values):
            next_at = values[index + 1][0] if index + 1 < len(values) else stopped
            delta = max(0.0, next_at - at)
            if delta <= 20.0:
                total += value * delta; duration += delta
        return total / duration if duration else statistics.mean(value for _, value in values)

    @_serialized
    def get_session(self, session_id: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if not row:
            return None
        result = self._session(row)
        result["series"] = self.series(session_id)
        result["report"] = json.loads(row["report_json"]) if row["report_json"] else None
        return result

    @_serialized
    def list_sessions(self, *, service_name: str | None = None, node_id: str | None = None, limit: int = 100) -> dict[str, Any]:
        clauses = ["1=1"]; params: list[Any] = []
        if service_name: clauses.append("service_name=?"); params.append(service_name)
        if node_id: clauses.append("node_id=?"); params.append(node_id)
        params.append(int(limit))
        rows = self.connection.execute(f"SELECT * FROM sessions WHERE {' AND '.join(clauses)} ORDER BY started_at DESC LIMIT ?", params).fetchall()
        return {"sessions": [self._session(row) for row in rows]}

    @_serialized
    def list_reports(self, *, service_name: str | None = None, node_id: str | None = None, limit: int = 100) -> dict[str, Any]:
        sessions = self.list_sessions(service_name=service_name, node_id=node_id, limit=limit)["sessions"]
        reports = []
        for item in sessions:
            if item.get("report_json"):
                reports.append(json.loads(item["report_json"]))
        return {"reports": reports}

    @_serialized
    def get_report(self, report_id: str) -> dict[str, Any] | None:
        rows = self.connection.execute("SELECT report_json FROM sessions WHERE report_json IS NOT NULL").fetchall()
        for row in rows:
            report = json.loads(row["report_json"])
            if report.get("report_id") == report_id:
                return report
        return None

    @_serialized
    def record_signal(self, session: dict[str, Any], signal: dict[str, Any], *, observed_at: float) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO signals(signal_id,session_id,service_name,node_id,observed_at,severity,resource,payload_json) VALUES(?,?,?,?,?,?,?,?)",
                (uuid.uuid4().hex, session["session_id"], session["service_name"], session["node_id"],
                 observed_at, signal["severity"], signal["resource"], _json(signal)),
            )

    @_serialized
    def record_objective_event(self, session_id: str, event: dict[str, Any]) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT service_name,node_id FROM sessions WHERE session_id=?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"telemetry session not found: {session_id}")
        observed_at = float(event.get("observed_at") if event.get("observed_at") is not None else time.time())
        objective_id = str(event.get("objective_id") or "")
        status = str(event.get("status") or "unknown")
        if not objective_id:
            raise ValueError("objective event requires objective_id")
        event_id = uuid.uuid4().hex
        with self.connection:
            self.connection.execute(
                "INSERT INTO objective_events(event_id,session_id,service_name,node_id,observed_at,objective_id,status,payload_json) VALUES(?,?,?,?,?,?,?,?)",
                (event_id, session_id, row["service_name"], row["node_id"], observed_at, objective_id, status, _json(event)),
            )
        return {"event_id": event_id, "session_id": session_id, "service_name": row["service_name"], "node_id": row["node_id"], "observed_at": observed_at, "objective_id": objective_id, "status": status, "payload": dict(event)}

    @_serialized
    def list_objective_events(
        self,
        *,
        service_name: str | None = None,
        session_id: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        clauses = ["1=1"]
        params: list[Any] = []
        if service_name:
            clauses.append("service_name=?")
            params.append(service_name)
        if session_id:
            clauses.append("session_id=?")
            params.append(session_id)
        params.append(int(limit))
        rows = self.connection.execute(
            f"SELECT * FROM objective_events WHERE {' AND '.join(clauses)} ORDER BY observed_at DESC LIMIT ?",
            params,
        ).fetchall()
        return {
            "events": [
                {
                    "event_id": row["event_id"],
                    "session_id": row["session_id"],
                    "service_name": row["service_name"],
                    "node_id": row["node_id"],
                    "observed_at": row["observed_at"],
                    "objective_id": row["objective_id"],
                    "status": row["status"],
                    "payload": json.loads(row["payload_json"]),
                }
                for row in rows
            ]
        }

    @_serialized
    def list_signals(
        self,
        *,
        service_name: str | None = None,
        session_id: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        clauses = ["1=1"]
        params: list[Any] = []
        if service_name:
            clauses.append("service_name=?")
            params.append(service_name)
        if session_id:
            clauses.append("session_id=?")
            params.append(session_id)
        params.append(int(limit))
        rows = self.connection.execute(
            f"SELECT * FROM signals WHERE {' AND '.join(clauses)} ORDER BY observed_at DESC LIMIT ?",
            params,
        ).fetchall()
        signals = []
        for row in rows:
            item = self._session(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            signals.append(item)
        return {"signals": signals}

    @_serialized
    def update_report(self, report: dict[str, Any]) -> None:
        report_id = str(report.get("report_id") or "")
        if not report_id:
            return
        self.connection.execute("UPDATE sessions SET report_json=? WHERE session_id=?", (_json(report), str(report.get("session_id") or "")))
        self.connection.commit()

    @_serialized
    def enqueue(self, stream: str, sequence: int, payload: dict[str, Any], *, next_attempt_at: float | None = None) -> None:
        self.connection.execute(
            "INSERT OR IGNORE INTO outbox(stream,sequence,payload_json,next_attempt_at) VALUES(?,?,?,?)",
            (stream, int(sequence), _json(payload), float(next_attempt_at if next_attempt_at is not None else time.time())),
        )
        self.connection.commit()

    @_serialized
    def due_outbox(self, *, limit: int = 100, now: float | None = None) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT stream,sequence,payload_json,attempts FROM outbox WHERE acknowledged=0 AND next_attempt_at<=? ORDER BY stream,sequence LIMIT ?",
            (float(now if now is not None else time.time()), int(limit)),
        ).fetchall()
        return [{"stream": row["stream"], "sequence": row["sequence"], "payload": json.loads(row["payload_json"]), "attempts": row["attempts"]} for row in rows]

    @_serialized
    def acknowledge(self, stream: str, sequence: int) -> None:
        self.connection.execute("UPDATE outbox SET acknowledged=1 WHERE stream=? AND sequence=?", (stream, int(sequence)))
        self.connection.commit()

    @_serialized
    def retry_outbox(self, stream: str, sequence: int, *, retry_after_seconds: float) -> None:
        self.connection.execute("UPDATE outbox SET attempts=attempts+1,next_attempt_at=? WHERE stream=? AND sequence=?", (time.time() + max(0.1, retry_after_seconds), stream, int(sequence)))
        self.connection.commit()

    @_serialized
    def prune(self, *, now: float | None = None) -> dict[str, int]:
        cutoff = float(now if now is not None else time.time()) - self.raw_retention_seconds
        cursor = self.connection.execute("DELETE FROM samples WHERE observed_at<? AND session_id IN (SELECT session_id FROM sessions WHERE status!='running')", (cutoff,))
        self.connection.commit()
        return {"samples_deleted": cursor.rowcount}

    @staticmethod
    def _session(row: sqlite3.Row) -> dict[str, Any]:
        return {key: row[key] for key in row.keys()}


__all__ = ["TelemetryStore"]
