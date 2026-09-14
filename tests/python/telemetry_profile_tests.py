import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


def test_catalog_exposes_profiles_and_default_metrics():
    from rift.telemetry.profiles import DEFAULT_PROFILE, metric_catalog, profile_catalog, resolve_selection

    catalog = metric_catalog()
    profiles = profile_catalog()
    assert DEFAULT_PROFILE == "default"
    assert "gpu_power_watts" in catalog
    assert "default" in profiles
    selection = resolve_selection({"profile": "default"})
    assert selection["profile"] == "default"
    assert "gpu_power_watts" in selection["metrics"]
    assert "cpu_temperature_c" not in selection["metrics"]
    assert "gpu_vram_used_bytes" not in selection["metrics"]


def test_custom_metric_selection_rejects_unknown_metrics():
    from rift.telemetry.profiles import resolve_selection

    try:
        resolve_selection({"profile": "custom", "metrics": ["not_a_metric"]})
    except ValueError as exc:
        assert "unknown telemetry metric" in str(exc)
    else:
        raise AssertionError("unknown metrics must be rejected")


def test_supervisor_persists_only_selected_metrics():
    from rift.telemetry.lifecycle import TelemetrySupervisor
    from rift.telemetry.store import TelemetryStore

    class FakeCollector:
        def collect(self, *, process_id=None, service_name=None):
            return {
                "observed_at": 100.0,
                "service_name": service_name,
                "process_id": process_id,
                "cpu_percent": 12.0,
                "process_cpu_percent": 4.0,
                "gpu_power_watts": 80.0,
                "gpu_temperature_c": 61.0,
                "availability": {"cpu": "measured", "gpu": "measured"},
            }

    store = TelemetryStore(":memory:")
    supervisor = TelemetrySupervisor(store, collector=FakeCollector(), interval_seconds=0.1)
    try:
        session = supervisor.start_service(
            "chat",
            metrics=["gpu_power_watts"],
            process_id=123,
        )
        sample = store.series(session["session_id"])["samples"][0]
        assert sample["gpu_power_watts"] == 80.0
        assert "cpu_percent" not in sample
        assert "gpu_temperature_c" not in sample
        metadata = json.loads(store.get_session(session["session_id"])["metadata_json"])
        assert metadata["telemetry_metrics"] == ["gpu_power_watts"]
    finally:
        supervisor.close()
        store.close()


def test_orchestrator_exposes_catalog_and_validates_service_selection(tmp_path):
    from rift.orchestrator import RiftOrchestrator

    orchestrator = RiftOrchestrator(root=tmp_path)
    try:
        catalog = orchestrator.telemetry_catalog()
        assert catalog["default_profile"] == "default"
        assert any(item["id"] == "gpu_power_watts" for item in catalog["metrics"])
        config = orchestrator.default_config()
        config["services"]["chat"]["monitoring"]["resources"]["profile"] = "not-real"
        try:
            orchestrator.validate_config(config)
        except ValueError as exc:
            assert "unknown telemetry profile" in str(exc)
        else:
            raise AssertionError("unknown telemetry profiles must be rejected")
    finally:
        orchestrator.close()


if __name__ == "__main__":
    test_catalog_exposes_profiles_and_default_metrics()
    test_custom_metric_selection_rejects_unknown_metrics()
    test_supervisor_persists_only_selected_metrics()
    print("telemetry_profile_tests: PASS")
