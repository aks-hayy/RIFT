"""One lightweight supervisor per node, independent of the dashboard."""

from __future__ import annotations

import json
import threading
import uuid
from typing import Any

from .collectors import LocalCollector
from .policy import ResourcePolicy
from .store import TelemetryStore


class TelemetrySupervisor:
    def __init__(self, store: TelemetryStore, *, interval_seconds: float = 2.0, node_id: str = "local", collector: LocalCollector | None = None, policy: ResourcePolicy | None = None) -> None:
        if interval_seconds <= 0:
            raise ValueError("telemetry interval_seconds must be positive")
        self.store = store
        self.interval_seconds = float(interval_seconds)
        self.node_id = node_id
        self.collector = collector or LocalCollector()
        self.policy = policy or ResourcePolicy()
        self._sessions: dict[str, dict[str, Any]] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="rift-telemetry", daemon=True)
            self._thread.start()

    def close(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread:
            thread.join(timeout=max(1.0, self.interval_seconds * 2))

    def start_service(
        self,
        service_name: str,
        *,
        process_id: int | None = None,
        metadata: dict[str, Any] | None = None,
        interval_seconds: float | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            if interval_seconds is not None:
                if float(interval_seconds) <= 0:
                    raise ValueError("telemetry interval_seconds must be positive")
                self.interval_seconds = float(interval_seconds)
            previous = self._sessions.get(service_name)
            if previous:
                self.stop_service(service_name)
            session = self.store.start_session(service_name, node_id=self.node_id, pid=process_id, metadata=metadata)
            self._sessions[service_name] = session
            self.start()
            self.sample_once(service_name)
            return session

    def attach_service(self, service_name: str, *, process_id: int | None = None) -> dict[str, Any] | None:
        with self._lock:
            active = self.store.active_session(service_name)
            if active and process_id not in (None, 0) and active.get("pid") not in (None, process_id):
                # A recovery/tuning restart becomes a new runtime segment,
                # while the parent service report remains a single timeline.
                self.store.finish_session(active["session_id"])
                active = self.store.start_session(service_name, node_id=self.node_id, pid=process_id, metadata={"segment": "restart"})
            if active:
                self._sessions[service_name] = active
                self.start()
            return active

    def sample_once(self, service_name: str) -> dict[str, Any] | None:
        with self._lock:
            session = self._sessions.get(service_name) or self.store.active_session(service_name)
            if not session:
                return None
            active = self.store.active_session(service_name)
            if not active or str(active.get("session_id")) != str(session.get("session_id")):
                self._sessions.pop(service_name, None)
                return None
            self._sessions[service_name] = session
            sample = self.collector.collect(process_id=session.get("pid"), service_name=service_name)
            recorded = self.store.record_sample(session["session_id"], sample)
            for signal in self.policy.evaluate(sample, observed_at=float(sample["observed_at"])):
                self.store.connection.execute(
                    "INSERT INTO signals(signal_id,session_id,service_name,node_id,observed_at,severity,resource,payload_json) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        uuid.uuid4().hex,
                        session["session_id"],
                        service_name,
                        self.node_id,
                        sample["observed_at"],
                        signal["severity"],
                        signal["resource"],
                        json.dumps(signal),
                    ),
                )
            self.store.connection.commit()
            return recorded

    def stop_service(self, service_name: str) -> dict[str, Any] | None:
        with self._lock:
            session = self._sessions.pop(service_name, None) or self.store.active_session(service_name)
            if not session:
                return None
            self.sample_once_for_session(session)
            return self.store.finish_session(session["session_id"])

    def sample_once_for_session(self, session: dict[str, Any]) -> dict[str, Any]:
        sample = self.collector.collect(process_id=session.get("pid"), service_name=session.get("service_name"))
        recorded = self.store.record_sample(session["session_id"], sample)
        return recorded

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            with self._lock:
                names = list(self._sessions)
            for name in names:
                try:
                    if self.store.active_session(name) is None:
                        with self._lock:
                            self._sessions.pop(name, None)
                        continue
                    self.sample_once(name)
                except Exception:
                    continue


__all__ = ["TelemetrySupervisor"]
