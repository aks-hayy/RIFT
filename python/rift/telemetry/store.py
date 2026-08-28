"""Durable SQLite telemetry storage, rollups and completed reports."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import statistics
import time
from typing import Any
import uuid

from .accounting import session_costs


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


class TelemetryStore:
    def __init__(self, path: str | Path, *, raw_retention_seconds: float = 48 * 3600) -> None:
        self.path = Path(path)
        self._memory = str(path) == ":memory:"
        if not self._memory:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.raw_retention_seconds = raw_retention_seconds
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
            CREATE TABLE IF NOT EXISTS outbox (
                stream TEXT NOT NULL, sequence INTEGER NOT NULL, payload_json TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at REAL NOT NULL,
                acknowledged INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(stream, sequence)
            );
            """
        )
        self.connection.commit()

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

    def start_session(self, service_name: str, *, node_id: str = "local", pid: int | None = None, metadata: dict[str, Any] | None = None, started_at: float | None = None) -> dict[str, Any]:
        session_id = uuid.uuid4().hex
        started = float(time.time() if started_at is None else started_at)
        self.connection.execute(
            "INSERT INTO sessions(session_id,service_name,node_id,pid,started_at,status,metadata_json) VALUES(?,?,?,?,?,?,?)",
            (session_id, service_name, node_id, pid, started, "running", _json(metadata or {})),
        )
        self.connection.commit()
        return {"session_id": session_id, "service_name": service_name, "node_id": node_id, "pid": pid, "started_at": started, "status": "running"}

    def active_session(self, service_name: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT * FROM sessions WHERE service_name=? AND status='running' ORDER BY started_at DESC LIMIT 1", (service_name,)).fetchone()
        return self._session(row) if row else None

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

    def record_sample(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        observed_at = float(payload.get("observed_at") or time.time())
        row = self.connection.execute("SELECT COALESCE(MAX(sequence), 0) AS sequence FROM samples WHERE session_id=?", (session_id,)).fetchone()
        sequence = int(row["sequence"] or 0) + 1
        self.connection.execute("INSERT INTO samples(session_id,sequence,observed_at,payload_json) VALUES(?,?,?,?)", (session_id, sequence, observed_at, _json(payload)))
        self.connection.commit()
        return {"session_id": session_id, "sequence": sequence, "observed_at": observed_at, **payload}

    def series(self, session_id: str, *, since: float | None = None, until: float | None = None, limit: int = 20000) -> dict[str, Any]:
        clauses = ["session_id=?"]
        params: list[Any] = [session_id]
        if since is not None:
            clauses.append("observed_at>=?"); params.append(float(since))
        if until is not None:
            clauses.append("observed_at<=?"); params.append(float(until))
        params.append(int(limit))
        rows = self.connection.execute(f"SELECT sequence,observed_at,payload_json FROM samples WHERE {' AND '.join(clauses)} ORDER BY observed_at ASC LIMIT ?", params).fetchall()
        return {"session_id": session_id, "sample_count": len(rows), "samples": [{"sequence": int(row["sequence"]), "observed_at": row["observed_at"], **json.loads(row["payload_json"])} for row in rows]}

    def finish_session(self, session_id: str, *, stopped_at: float | None = None, status: str = "completed") -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if row is None:
            raise KeyError(f"telemetry session not found: {session_id}")
        stopped = float(stopped_at if stopped_at is not None else time.time())
        points = self.series(session_id)["samples"]
        report = self._report(dict(row), points, stopped)
        self.connection.execute("UPDATE sessions SET stopped_at=?,status=?,report_json=? WHERE session_id=?", (stopped, status, _json(report), session_id))
        self.connection.commit()
        return report

    def _report(self, session: dict[str, Any], points: list[dict[str, Any]], stopped: float) -> dict[str, Any]:
        numeric: dict[str, list[tuple[float, float]]] = {}
        for point in points:
            for key, value in point.items():
                if key in {"observed_at", "sequence", "process_id"} or isinstance(value, bool) or not isinstance(value, (int, float)):
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

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if not row:
            return None
        result = self._session(row)
        result["series"] = self.series(session_id)
        result["report"] = json.loads(row["report_json"]) if row["report_json"] else None
        return result

    def list_sessions(self, *, service_name: str | None = None, node_id: str | None = None, limit: int = 100) -> dict[str, Any]:
        clauses = ["1=1"]; params: list[Any] = []
        if service_name: clauses.append("service_name=?"); params.append(service_name)
        if node_id: clauses.append("node_id=?"); params.append(node_id)
        params.append(int(limit))
        rows = self.connection.execute(f"SELECT * FROM sessions WHERE {' AND '.join(clauses)} ORDER BY started_at DESC LIMIT ?", params).fetchall()
        return {"sessions": [self._session(row) for row in rows]}

    def list_reports(self, *, service_name: str | None = None, node_id: str | None = None, limit: int = 100) -> dict[str, Any]:
        sessions = self.list_sessions(service_name=service_name, node_id=node_id, limit=limit)["sessions"]
        reports = []
        for item in sessions:
            if item.get("report_json"):
                reports.append(json.loads(item["report_json"]))
        return {"reports": reports}

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        rows = self.connection.execute("SELECT report_json FROM sessions WHERE report_json IS NOT NULL").fetchall()
        for row in rows:
            report = json.loads(row["report_json"])
            if report.get("report_id") == report_id:
                return report
        return None

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

    def update_report(self, report: dict[str, Any]) -> None:
        report_id = str(report.get("report_id") or "")
        if not report_id:
            return
        self.connection.execute("UPDATE sessions SET report_json=? WHERE session_id=?", (_json(report), str(report.get("session_id") or "")))
        self.connection.commit()

    def enqueue(self, stream: str, sequence: int, payload: dict[str, Any], *, next_attempt_at: float | None = None) -> None:
        self.connection.execute(
            "INSERT OR IGNORE INTO outbox(stream,sequence,payload_json,next_attempt_at) VALUES(?,?,?,?)",
            (stream, int(sequence), _json(payload), float(next_attempt_at if next_attempt_at is not None else time.time())),
        )
        self.connection.commit()

    def due_outbox(self, *, limit: int = 100, now: float | None = None) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT stream,sequence,payload_json,attempts FROM outbox WHERE acknowledged=0 AND next_attempt_at<=? ORDER BY stream,sequence LIMIT ?",
            (float(now if now is not None else time.time()), int(limit)),
        ).fetchall()
        return [{"stream": row["stream"], "sequence": row["sequence"], "payload": json.loads(row["payload_json"]), "attempts": row["attempts"]} for row in rows]

    def acknowledge(self, stream: str, sequence: int) -> None:
        self.connection.execute("UPDATE outbox SET acknowledged=1 WHERE stream=? AND sequence=?", (stream, int(sequence)))
        self.connection.commit()

    def retry_outbox(self, stream: str, sequence: int, *, retry_after_seconds: float) -> None:
        self.connection.execute("UPDATE outbox SET attempts=attempts+1,next_attempt_at=? WHERE stream=? AND sequence=?", (time.time() + max(0.1, retry_after_seconds), stream, int(sequence)))
        self.connection.commit()

    def prune(self, *, now: float | None = None) -> dict[str, int]:
        cutoff = float(now if now is not None else time.time()) - self.raw_retention_seconds
        cursor = self.connection.execute("DELETE FROM samples WHERE observed_at<? AND session_id IN (SELECT session_id FROM sessions WHERE status!='running')", (cutoff,))
        self.connection.commit()
        return {"samples_deleted": cursor.rowcount}

    @staticmethod
    def _session(row: sqlite3.Row) -> dict[str, Any]:
        return {key: row[key] for key in row.keys()}


__all__ = ["TelemetryStore"]
