from __future__ import annotations

import json

from rift.telemetry.lifecycle import TelemetrySupervisor
from rift.telemetry.store import TelemetryStore


class FixedCollector:
    def __init__(self, values):
        self.values = iter(values)

    def collect(self, *, process_id=None, service_name=None):
        value = next(self.values)
        return {"observed_at": value["observed_at"], "service_name": service_name, "gpu_temperature_c": value["gpu_temperature_c"]}


def test_objective_events_round_trip_and_report_summary():
    store = TelemetryStore(":memory:")
    session = store.start_session("chat", started_at=1.0)
    store.record_objective_event(session["session_id"], {
        "objective_id": "temperature", "status": "breach", "observed_at": 2.0,
        "metric": "gpu_temperature_c", "value": 90, "threshold": 85,
    })
    store.record_sample(session["session_id"], {"observed_at": 1.0, "gpu_temperature_c": 80})
    report = store.finish_session(session["session_id"], stopped_at=3.0, objective_snapshot=[{
        "objective_id": "temperature", "status": "breach", "value": 90,
    }])

    events = store.list_objective_events(session_id=session["session_id"])["events"]
    assert events[0]["payload"]["status"] == "breach"
    assert report["objectives"][0]["status"] == "breach"
    assert report["objective_events"][0]["objective_id"] == "temperature"


def test_supervisor_records_objective_transition_without_breaking_sampling():
    store = TelemetryStore(":memory:")
    supervisor = TelemetrySupervisor(
        store,
        collector=FixedCollector([
            {"observed_at": 1.0, "gpu_temperature_c": 70},
            {"observed_at": 2.0, "gpu_temperature_c": 90},
            {"observed_at": 3.0, "gpu_temperature_c": 90},
        ]),
    )
    objective = [{"id": "temperature", "metric": "gpu_temperature_c", "operator": "<=", "threshold": 85}]
    session = supervisor.start_service("chat", metadata={"objectives": objective})
    supervisor.sample_once("chat")
    report = supervisor.stop_service("chat")

    assert report is not None
    assert report["objectives"][0]["status"] == "breach"
    assert report["objective_events"]


def test_supervisor_adds_gateway_derived_request_metrics_when_available(tmp_path):
    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text(json.dumps({
        "requests_total": 10,
        "requests_succeeded": 9,
        "requests_failed": 1,
        "average_latency_seconds": 0.42,
    }), encoding="utf-8")
    store = TelemetryStore(":memory:")
    supervisor = TelemetrySupervisor(
        store,
        collector=FixedCollector([{"observed_at": 1.0, "gpu_temperature_c": 70}, {"observed_at": 2.0, "gpu_temperature_c": 70}]),
    )
    session = supervisor.start_service("chat", metadata={"gateway_metrics_path": str(metrics_path)})
    recorded = store.series(session["session_id"])["samples"][0]

    assert recorded["request.error_ratio"] == 0.1
    assert recorded["service.availability_ratio"] == 0.9
    assert recorded["request.average_latency_seconds"] == 0.42


def test_supervisor_rebuilds_objective_snapshot_when_stop_happens_in_new_process():
    store = TelemetryStore(":memory:")
    first = TelemetrySupervisor(
        store,
        collector=FixedCollector([
            {"observed_at": 1.0, "gpu_temperature_c": 70},
        ]),
    )
    objective = [{"id": "temperature", "metric": "gpu_temperature_c", "operator": "<=", "threshold": 85}]
    session = first.start_service("chat", metadata={"objectives": objective})

    second = TelemetrySupervisor(
        store,
        collector=FixedCollector([
            {"observed_at": 2.0, "gpu_temperature_c": 72},
        ]),
    )
    report = second.stop_service("chat")

    assert report is not None
    assert report["objectives"][0]["objective_id"] == "temperature"
    assert report["objectives"][0]["status"] == "pass"


def test_attach_service_replays_objective_state_without_duplicate_transitions():
    store = TelemetryStore(":memory:")
    first = TelemetrySupervisor(
        store,
        collector=FixedCollector([{"observed_at": 1.0, "gpu_temperature_c": 70}]),
    )
    objective = [{"id": "temperature", "metric": "gpu_temperature_c", "operator": "<=", "threshold": 85}]
    session = first.start_service("chat", metadata={"objectives": objective})

    second = TelemetrySupervisor(
        store,
        collector=FixedCollector([{"observed_at": 2.0, "gpu_temperature_c": 72}]),
    )
    second.attach_service("chat")
    second.sample_once("chat")

    events = store.list_objective_events(session_id=session["session_id"], limit=100)["events"]
    assert len(events) == 1
