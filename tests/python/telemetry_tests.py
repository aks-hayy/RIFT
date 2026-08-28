import os
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


def test_store_tracks_samples_and_final_report():
    from rift.telemetry.store import TelemetryStore

    store = TelemetryStore(Path(".telemetry-test") / "telemetry.db")
    try:
        session = store.start_session(
            "chat",
            node_id="local",
            pid=os.getpid(),
            metadata={
                "electricity_price_per_kwh": 0.25,
                "compute_cost_per_node_hour": 36.0,
            },
            started_at=100.0,
        )
        store.record_sample(
            session["session_id"],
            {"observed_at": 100.0, "cpu_percent": 20.0, "ram_used_bytes": 100, "gpu_power_watts": 50.0},
        )
        store.record_sample(
            session["session_id"],
            {"observed_at": 102.0, "cpu_percent": 40.0, "ram_used_bytes": 300, "gpu_power_watts": 70.0},
        )
        report = store.finish_session(session["session_id"], stopped_at=102.0)
        assert report["session_id"] == session["session_id"]
        assert report["sample_count"] == 2
        assert report["metrics"]["cpu_percent"]["average"] == 20.0
        assert report["metrics"]["ram_used_bytes"]["peak"] == 300.0
        assert report["metrics"]["gpu_energy_joules"]["estimated"] == 100.0
        assert report["costs"]["electricity_cost"] == 100.0 / 3_600_000.0 * 0.25
        assert report["costs"]["compute_cost"] == 0.02
        assert report["costs"]["total_cost"] == report["costs"]["electricity_cost"] + 0.02
    finally:
        store.close()
        db = Path(".telemetry-test") / "telemetry.db"
        if db.exists():
            db.unlink()
        if db.parent.exists():
            db.parent.rmdir()


def test_local_collector_marks_missing_accelerator_unavailable():
    from rift.telemetry.collectors import LocalCollector

    sample = LocalCollector().collect(process_id=os.getpid(), service_name="test")
    assert sample["service_name"] == "test"
    assert sample["process_id"] == os.getpid()
    assert "cpu_percent" in sample
    assert "host_ram_available_bytes" in sample
    assert sample["gpu_utilization_percent"] is None or isinstance(sample["gpu_utilization_percent"], (int, float))


def test_policy_requires_dwell_and_hysteresis():
    from rift.telemetry.policy import ResourcePolicy

    policy = ResourcePolicy(warning_cpu_temperature_c=50.0, critical_cpu_temperature_c=60.0, warning_dwell_seconds=2.0)
    assert policy.evaluate({"cpu_temperature_c": 55.0}, observed_at=100.0) == []
    warning = policy.evaluate({"cpu_temperature_c": 55.0}, observed_at=102.1)
    assert warning[0]["severity"] == "warning"
    assert policy.evaluate({"cpu_temperature_c": 45.0}, observed_at=103.0) == []


def test_energy_cost_is_unavailable_without_tariff():
    from rift.telemetry.accounting import energy_cost

    assert energy_cost(3_600_000, price_per_kwh=None) is None
    assert energy_cost(3_600_000, price_per_kwh=0.25) == 0.25


def test_service_accounting_persists_per_service_and_updates_active_session(tmp_path):
    from rift.orchestrator import RiftOrchestrator
    from rift.rift_yaml import read_yaml, write_yaml

    orchestrator = RiftOrchestrator(root=tmp_path)
    try:
        config = orchestrator.default_config()
        config["observability"]["telemetry"]["electricity_price_per_kwh"] = 0.19
        write_yaml(tmp_path / "rift.yaml", config)
        session = orchestrator.telemetry_store.start_session(
            "chat", metadata={"electricity_price_per_kwh": 0.19}
        )

        updated = orchestrator.update_service_telemetry_accounting(
            "chat",
            updates={
                "electricity_price_per_kwh": 0.31,
                "compute_cost_per_node_hour": 1.25,
            },
        )

        persisted = read_yaml(tmp_path / "rift.yaml")
        resources = persisted["services"]["chat"]["monitoring"]["resources"]
        assert resources["electricity_price_per_kwh"] == 0.31
        assert resources["compute_cost_per_node_hour"] == 1.25
        assert updated["electricity_price_source"] == "service"
        assert updated["compute_cost_source"] == "service"
        assert updated["electricity_price_per_kwh"] == 0.31
        assert updated["compute_cost_per_node_hour"] == 1.25

        active = orchestrator.telemetry_store.active_session("chat")
        assert active is not None
        metadata = json.loads(active["metadata_json"])
        assert metadata["electricity_price_per_kwh"] == 0.31
        assert metadata["compute_cost_per_node_hour"] == 1.25
        assert active["session_id"] == session["session_id"]

        cleared = orchestrator.update_service_telemetry_accounting(
            "chat", updates={"electricity_price_per_kwh": None}
        )
        assert cleared["electricity_price_per_kwh"] == 0.19
        assert cleared["electricity_price_source"] == "global"
    finally:
        orchestrator.close()


def test_service_accounting_rejects_invalid_rates(tmp_path):
    from rift.orchestrator import RiftOrchestrator
    from rift.rift_yaml import write_yaml

    orchestrator = RiftOrchestrator(root=tmp_path)
    try:
        write_yaml(tmp_path / "rift.yaml", orchestrator.default_config())
        try:
            orchestrator.update_service_telemetry_accounting(
                "chat", updates={"electricity_price_per_kwh": -0.1}
            )
        except ValueError as exc:
            assert "non-negative" in str(exc)
        else:
            raise AssertionError("negative electricity rates must be rejected")

        try:
            orchestrator.update_service_telemetry_accounting(
                "chat", updates={"unknown_rate": 1.0}
            )
        except ValueError as exc:
            assert "unsupported" in str(exc)
        else:
            raise AssertionError("unknown accounting fields must be rejected")
    finally:
        orchestrator.close()


def test_supervisor_persists_live_samples():
    from rift.telemetry.lifecycle import TelemetrySupervisor
    from rift.telemetry.store import TelemetryStore

    store = TelemetryStore(Path(".telemetry-supervisor-test") / "telemetry.db")
    supervisor = TelemetrySupervisor(store, interval_seconds=0.01)
    try:
        session = supervisor.start_service("chat", process_id=os.getpid())
        assert supervisor.sample_once("chat") is not None
        assert store.series(session["session_id"])["sample_count"] >= 1
        report = supervisor.stop_service("chat")
        assert report["session_id"] == session["session_id"]
    finally:
        supervisor.close()
        store.close()
        db = Path(".telemetry-supervisor-test") / "telemetry.db"
        if db.exists():
            db.unlink()
        if db.parent.exists():
            db.parent.rmdir()


def test_cli_exposes_telemetry_report_query():
    from rift.cli.parser import build_parser

    args = build_parser().parse_args(["service", "telemetry", "--service", "chat", "--report"])
    assert args.service_command == "telemetry"
    assert args.report is True


if __name__ == "__main__":
    test_store_tracks_samples_and_final_report()
    test_local_collector_marks_missing_accelerator_unavailable()
    test_policy_requires_dwell_and_hysteresis()
    test_supervisor_persists_live_samples()
    print("telemetry_tests: PASS")
