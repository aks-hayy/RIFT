"""One lightweight supervisor per node, independent of the dashboard."""

from __future__ import annotations

import json
import threading
from typing import Any

from .collectors import LocalCollector
from .alerts import AlertDispatcher
from .objectives import ObjectiveEvaluator, normalize_objectives
from .policy import ResourcePolicy
from .profiles import filter_sample
from .store import TelemetryStore


class TelemetrySupervisor:
    def __init__(self, store: TelemetryStore, *, interval_seconds: float = 2.0, node_id: str = "local", collector: LocalCollector | None = None, policy: ResourcePolicy | None = None, alert_dispatcher: AlertDispatcher | None = None) -> None:
        if interval_seconds <= 0:
            raise ValueError("telemetry interval_seconds must be positive")
        self.store = store
        self.interval_seconds = float(interval_seconds)
        self.node_id = node_id
        self.collector = collector or LocalCollector()
        self.policy = policy or ResourcePolicy()
        self.alert_dispatcher = alert_dispatcher or AlertDispatcher()
        self._sessions: dict[str, dict[str, Any]] = {}
        self._evaluators: dict[str, ObjectiveEvaluator] = {}
        self._objective_event_counts: dict[str, int] = {}
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
        metrics: list[str] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            if interval_seconds is not None:
                if float(interval_seconds) <= 0:
                    raise ValueError("telemetry interval_seconds must be positive")
                self.interval_seconds = float(interval_seconds)
            previous = self._sessions.get(service_name)
            if previous:
                self.stop_service(service_name)
            session_metadata = dict(metadata or {})
            normalized_objectives = normalize_objectives(session_metadata.get("objectives"))
            session_metadata["objectives"] = normalized_objectives
            if metrics is not None:
                session_metadata["telemetry_metrics"] = list(metrics)
            session = self.store.start_session(
                service_name,
                node_id=self.node_id,
                pid=process_id,
                metadata=session_metadata,
            )
            # Keep the serialized metadata on the in-memory session as well;
            # the first sample is recorded immediately before a DB round-trip
            # could otherwise provide it through ``active_session``.
            session["metadata_json"] = json.dumps(session_metadata, separators=(",", ":"), sort_keys=True)
            self._sessions[service_name] = session
            self._evaluators[service_name] = ObjectiveEvaluator(normalized_objectives)
            self._objective_event_counts[service_name] = 0
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
                try:
                    metadata = json.loads(active.get("metadata_json") or "{}")
                except (TypeError, json.JSONDecodeError):
                    metadata = {}
                if not isinstance(metadata, dict):
                    metadata = {}
                metadata["segment"] = "restart"
                active = self.store.start_session(service_name, node_id=self.node_id, pid=process_id, metadata=metadata)
            if active:
                self._sessions[service_name] = active
                metadata = active.get("metadata_json")
                try:
                    parsed = json.loads(metadata) if isinstance(metadata, str) else metadata or {}
                except (TypeError, json.JSONDecodeError):
                    parsed = {}
                self._evaluators[service_name] = self._restore_evaluator(active) or ObjectiveEvaluator((parsed or {}).get("objectives") or [])
                self._objective_event_counts[service_name] = len(
                    self.store.list_objective_events(session_id=str(active["session_id"]), limit=10000)["events"]
                )
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
            sample = self._augment_gateway_metrics(session, sample)
            sample = filter_sample(sample, self._session_metrics(session))
            recorded = self.store.record_sample(session["session_id"], sample)
            for signal in self.policy.evaluate(sample, observed_at=float(sample["observed_at"])):
                self.store.record_signal(session, signal, observed_at=float(sample["observed_at"]))
            self._evaluate_objectives(service_name, session, sample)
            return recorded

    def stop_service(self, service_name: str) -> dict[str, Any] | None:
        with self._lock:
            session = self._sessions.pop(service_name, None) or self.store.active_session(service_name)
            if not session:
                return None
            self.sample_once_for_session(session)
            evaluator = self._evaluators.pop(service_name, None)
            self._objective_event_counts.pop(service_name, None)
            if evaluator is None:
                # A stop command commonly runs in a fresh CLI process.  The
                # durable session still has the objective definitions, so
                # replay its samples to produce a complete final snapshot.
                evaluator = self._restore_evaluator(session)
            stored_events = self.store.list_objective_events(
                session_id=str(session["session_id"]), limit=10000
            )["events"]
            objective_events = [
                {
                    **item.get("payload", {}),
                    "event_id": item.get("event_id"),
                    "session_id": item.get("session_id"),
                    "service_name": item.get("service_name"),
                    "node_id": item.get("node_id"),
                }
                for item in stored_events
            ]
            return self.store.finish_session(
                session["session_id"],
                objective_snapshot=evaluator.snapshot() if evaluator else None,
                objective_events=objective_events or (evaluator.events() if evaluator else None),
            )

    def sample_once_for_session(self, session: dict[str, Any]) -> dict[str, Any]:
        sample = self.collector.collect(process_id=session.get("pid"), service_name=session.get("service_name"))
        sample = self._augment_gateway_metrics(session, sample)
        sample = filter_sample(sample, self._session_metrics(session))
        recorded = self.store.record_sample(session["session_id"], sample)
        self._evaluate_objectives(str(session.get("service_name") or ""), session, sample)
        return recorded

    def _evaluate_objectives(self, service_name: str, session: dict[str, Any], sample: dict[str, Any]) -> None:
        evaluator = self._evaluators.get(service_name)
        if evaluator is None:
            return
        try:
            evaluator.evaluate(sample, observed_at=float(sample["observed_at"]))
            events = evaluator.events()
            start = self._objective_event_counts.get(service_name, 0)
            for event in events[start:]:
                self.store.record_objective_event(str(session["session_id"]), event)
                objective = next((item for item in evaluator.objectives if item.get("id") == event.get("objective_id")), None)
                if objective and objective.get("alerts"):
                    self.alert_dispatcher.dispatch(event, adapters=list(objective.get("alerts") or []))
            self._objective_event_counts[service_name] = len(events)
        except Exception:
            # An invalid/unsupported objective must never interrupt resource
            # collection or a managed service's lifecycle.
            return

    def _restore_evaluator(self, session: dict[str, Any]) -> ObjectiveEvaluator | None:
        metadata = session.get("metadata_json")
        try:
            parsed = json.loads(metadata) if isinstance(metadata, str) else metadata or {}
        except (TypeError, json.JSONDecodeError):
            parsed = {}
        objectives = normalize_objectives(parsed.get("objectives") if isinstance(parsed, dict) else None)
        if not objectives:
            return None
        evaluator = ObjectiveEvaluator(objectives)
        samples = self.store.series(str(session["session_id"])).get("samples", [])
        for sample in samples:
            try:
                evaluator.evaluate(sample, observed_at=float(sample.get("observed_at")))
            except (TypeError, ValueError):
                continue
        return evaluator

    @staticmethod
    def _augment_gateway_metrics(session: dict[str, Any], sample: dict[str, Any]) -> dict[str, Any]:
        """Add request-level signals from the managed RIFT gateway, when configured.

        Gateway metrics are intentionally read as a best-effort side channel so
        telemetry remains backend-agnostic and a missing/partially written file
        never interrupts service sampling.
        """
        metadata = session.get("metadata_json")
        try:
            metadata = json.loads(metadata) if isinstance(metadata, str) else metadata or {}
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        path = metadata.get("gateway_metrics_path") if isinstance(metadata, dict) else None
        if not path:
            return dict(sample)
        try:
            with open(path, "r", encoding="utf-8") as source:
                gateway = json.load(source)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return dict(sample)
        if not isinstance(gateway, dict):
            return dict(sample)
        result = dict(sample)
        try:
            route_scope = metadata.get("gateway_route_scope") if isinstance(metadata, dict) else None
            scoped = (gateway.get("route_metrics") or {}).get(route_scope) if route_scope and isinstance(gateway.get("route_metrics"), dict) else None
            source = scoped if isinstance(scoped, dict) else gateway
            total = int(source.get("requests_total") or 0)
            succeeded = int(source.get("requests_succeeded") or 0)
            failed = int(source.get("requests_failed") or 0)
            completed = succeeded + failed
            if completed > 0:
                result["request.error_ratio"] = failed / completed
            if total > 0:
                result["service.availability_ratio"] = succeeded / total
            average_latency = source.get("average_latency_seconds")
            if average_latency is not None:
                result["request.average_latency_seconds"] = float(average_latency)
            last_request = source.get("last_request")
            if isinstance(last_request, dict) and last_request.get("latency_seconds") is not None:
                result["request.last_latency_seconds"] = float(last_request["latency_seconds"])
        except (TypeError, ValueError, OverflowError):
            return result
        return result

    @staticmethod
    def _session_metrics(session: dict[str, Any]) -> list[str] | None:
        metadata = session.get("metadata_json")
        if not metadata:
            return None
        try:
            value = json.loads(metadata) if isinstance(metadata, str) else metadata
        except (TypeError, json.JSONDecodeError):
            return None
        metrics = value.get("telemetry_metrics") if isinstance(value, dict) else None
        return list(metrics) if isinstance(metrics, list) else None

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
