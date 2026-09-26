from __future__ import annotations

from rift.telemetry.alerts import AlertDispatcher, MemoryAlertAdapter
from rift.telemetry.lifecycle import TelemetrySupervisor
from rift.telemetry.store import TelemetryStore


def test_alert_dispatcher_routes_only_configured_objective_adapters():
    memory = MemoryAlertAdapter()
    dispatcher = AlertDispatcher({"memory": memory})

    result = dispatcher.dispatch(
        {"objective_id": "ttft", "status": "breach", "value": 700},
        adapters=["memory"],
    )

    assert result == {"sent": 1, "failed": 0}
    assert memory.events[0]["objective_id"] == "ttft"


def test_alert_dispatcher_is_fail_safe_for_unknown_adapter():
    dispatcher = AlertDispatcher({})

    assert dispatcher.dispatch({"objective_id": "temp", "status": "warning"}, adapters=["email"]) == {
        "sent": 0,
        "failed": 1,
    }


def test_supervisor_dispatches_objective_transition_without_blocking_sampling():
    class Collector:
        def __init__(self):
            self.value = 90

        def collect(self, *, process_id=None, service_name=None):
            return {"observed_at": 1.0, "service_name": service_name, "gpu_temperature_c": self.value}

    memory = MemoryAlertAdapter()
    supervisor = TelemetrySupervisor(
        TelemetryStore(":memory:"),
        collector=Collector(),
        alert_dispatcher=AlertDispatcher({"memory": memory}),
    )
    supervisor.start_service("chat", metadata={"objectives": [{"id": "temp", "metric": "gpu_temperature_c", "operator": "<=", "threshold": 85, "alerts": ["memory"]}]})

    assert memory.events
    assert memory.events[-1]["objective_id"] == "temp"
