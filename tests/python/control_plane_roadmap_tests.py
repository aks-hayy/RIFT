import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import types


ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = ROOT / "python"
sys.path.insert(0, str(PYTHON_ROOT))


class FakeNativeEngine:
    def __init__(self, cuda_device_id=0):
        self.cuda_device_id = cuda_device_id

    def hardware_profile(self):
        return {
            "cuda_device_id": 0,
            "cuda_available": True,
            "device_name": "Fixture GPU",
            "compute_capability_major": 8,
            "compute_capability_minor": 9,
            "total_vram_bytes": 8 * 1024**3,
            "free_vram_bytes": 6 * 1024**3,
            "total_host_ram_bytes": 16 * 1024**3,
            "free_host_ram_bytes": 10 * 1024**3,
            "estimated_h2d_bandwidth_gbps": 12.0,
        }

    def build_info(self):
        return {"version": "test"}


fake_core = types.ModuleType("rift._core")
fake_core.InferenceEngine = FakeNativeEngine
fake_core.__version__ = "test"
fake_core.build_info = lambda: {"version": "test"}
fake_core.cuda_device_count = lambda: 1
fake_core.inspect_model = lambda *args, **kwargs: {}
fake_core.parse_model_topology = lambda *args, **kwargs: {}
sys.modules["rift._core"] = fake_core

artifacts_mod = importlib.import_module("rift.artifacts")
benchmark_mod = importlib.import_module("rift.benchmarking")
evidence_mod = importlib.import_module("rift.evidence")
gateway_mod = importlib.import_module("rift.gateway")
governance_mod = importlib.import_module("rift.governance")
observability_mod = importlib.import_module("rift.observability")
orchestrator_mod = importlib.import_module("rift.orchestrator")
providers_mod = importlib.import_module("rift.providers")
release_mod = importlib.import_module("rift.release")
rollout_mod = importlib.import_module("rift.rollout")
system_profile_mod = importlib.import_module("rift.system_profile")
transport_mod = importlib.import_module("rift.transport")


def test_hardware_profile_and_calibration_labels():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        analyzer = system_profile_mod.HardwareAnalyzer(root=root)
        profile = analyzer.analyze(FakeNativeEngine().hardware_profile(), state={"services": {}})
        assert profile["capacity"]["vram_bytes"] == 8 * 1024**3
        assert profile["pressure"]["vram_used_percent"] == 25.0
        assert profile["measurement_labels"]["h2d_bandwidth"] == "native_estimate"
        assert profile["fingerprint"]
        calibration = analyzer.calibrate(sample_bytes=1024**2, force=True)
        assert calibration["disk"]["read_mib_s"] > 0
        refreshed = analyzer.analyze(FakeNativeEngine().hardware_profile())
        assert refreshed["calibration"]["available"] is True
        assert refreshed["calibration"]["stale"] is False


def test_discovery_separates_managed_services_from_capacity():
    with tempfile.TemporaryDirectory() as tmp:
        orchestrator = orchestrator_mod.RiftOrchestrator(root=tmp)
        orchestrator.write_state(
            {
                "schema_version": 2,
                "services": {
                    "chat": {
                        "backend": "llama.cpp",
                        "runtime": {"pid": 4242},
                    }
                },
                "history": [],
            }
        )
        discovery = orchestrator.discover(write=False)
        profile = discovery["nodes"][0]["hardware"]
        assert profile["capacity"]["vram_bytes"] == 8 * 1024**3
        assert profile["rift_managed_occupancy"]["running_service_count"] == 1
        assert profile["rift_managed_occupancy"]["services"][0]["service"] == "chat"


def test_evidence_levels_do_not_claim_metadata_is_benchmark():
    with tempfile.TemporaryDirectory() as tmp:
        engine = evidence_mod.EvidenceEngine(root=tmp)
        metadata = engine.assess_candidate(
            {"repo_id": "org/model", "likes": 10, "downloads": 100}, task="chat"
        )
        assert metadata["highest_level"] == "HUB_METADATA"
        engine.record_local_result(
            repo_id="org/model",
            task="chat",
            metrics={"median_tokens_per_second": 10.0},
            backend="llama.cpp",
        )
        measured = engine.assess_candidate({"repo_id": "org/model"}, task="chat")
        assert measured["highest_level"] == "VERIFIED_LOCAL"
        assert measured["confidence"] >= 1.0


def test_artifact_manifest_integrity_and_provenance():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "model"
        root.mkdir()
        model = root / "tiny-Q4_K_M.gguf"
        model.write_bytes(b"RIFT-MODEL")
        (root / "config.json").write_text('{"model_type":"llama"}', encoding="utf-8")
        manager = artifacts_mod.ArtifactManifest(root=tmp)
        manifest = manager.build(root, repo_id="org/model", revision="abc", hash_mode="all")
        assert manifest["quantization"] == "Q4_K_M"
        assert manager.verify(manifest)["valid"] is True
        model.write_bytes(b"corrupt")
        verification = manager.verify(manifest)
        assert verification["valid"] is False
        assert verification["invalid_files"]


def test_benchmark_statistics_and_regression_gate():
    samples = [
        {"elapsed_seconds": 1.0, "generated_tokens_estimate": 10, "tokens_per_second_estimate": 10},
        {"elapsed_seconds": 2.0, "generated_tokens_estimate": 18, "tokens_per_second_estimate": 9},
        {"elapsed_seconds": 1.2, "generated_tokens_estimate": 12, "tokens_per_second_estimate": 10},
    ]
    summary = benchmark_mod.summarize_samples(samples)
    assert summary["valid"] is True
    assert summary["median_tokens_per_second"] == 10.0
    assert summary["p95_elapsed_seconds"] > summary["median_elapsed_seconds"]
    rejected = benchmark_mod.regression_decision(
        {"median_tokens_per_second": 10, "p95_elapsed_seconds": 1},
        {"median_tokens_per_second": 8, "p95_elapsed_seconds": 1.2},
    )
    assert rejected["promote"] is False
    assert rejected["rollback"] is True


def test_observability_retention_redaction_and_prometheus():
    with tempfile.TemporaryDirectory() as tmp:
        store = observability_mod.ObservabilityStore(root=tmp, retention_seconds=1, max_events=100)
        store.append("request", details={"Authorization": "Bearer secret-value"})
        event = store.timeline()["events"][0]
        assert "secret-value" not in json.dumps(event)
        snapshot = store.snapshot(
            state={"services": {"chat": {"status": "healthy", "supervisor": {"restart_count": 2}}}},
            gateway={"metrics": {"requests_total": 5, "requests_active": 0, "requests_failed": 1}},
            incidents={"incidents": [{"id": 1}]},
        )
        output = store.prometheus(snapshot)
        assert "rift_services_total 1" in output
        assert "rift_incidents_total 1" in output
        assert store.prune(now=time.time() + 2)["retained"] == 0


def test_provider_contract_and_api_key_lifecycle():
    for provider in providers_mod.provider_registry().values():
        gate = providers_mod.provider_lifecycle_gate(provider)
        assert gate["contract_complete"] is True
        assert gate["gate_passed"] is True
        assert gate["capabilities"]["formats"]
    with tempfile.TemporaryDirectory() as tmp:
        store = gateway_mod.ApiKeyStore(Path(tmp) / "keys.json")
        created = store.create(label="test")
        assert store.verify(created["secret"]) is True
        rotated = store.rotate(created["id"])
        assert store.verify(created["secret"]) is False
        assert store.verify(rotated["new"]["secret"]) is True
        assert "sha256" not in json.dumps(store.list())


def test_remote_transport_permission_and_parsing():
    def fake_runner(args, **kwargs):
        del args, kwargs
        return subprocess.CompletedProcess([], 0, '{"hostname":"node-a","disk_free_bytes":100}', "")

    transport = transport_mod.SshTransport(runner=fake_runner)
    transport.detect = lambda: {"available": True, "executable": "ssh"}
    blocked = transport.discover({"name": "node-a", "host": "node-a"})
    assert blocked["executed"] is False
    result = transport.discover({"name": "node-a", "host": "node-a"}, allow_remote=True)
    assert result["ok"] is True
    assert result["hardware"]["hostname"] == "node-a"


def test_rollout_governance_migration_and_diagnostics():
    engine = rollout_mod.RolloutEngine()
    plan = engine.plan(
        service="chat",
        current={"batch": 256},
        desired={"batch": 512},
        strategy="canary",
        replicas=2,
    )
    assert plan["changed"] is True
    assert plan["steps"][0]["kind"] == "start_canary"
    gate = engine.promotion_gate(
        readiness={"healthy": True},
        baseline_benchmark={"median_tokens_per_second": 10, "p95_elapsed_seconds": 1},
        candidate_benchmark={"median_tokens_per_second": 11, "p95_elapsed_seconds": 0.9},
    )
    assert gate["promote"] is True

    policy = governance_mod.GovernancePolicy(
        {"allowed_sources": ["huggingface"], "denied_licenses": ["unknown"]}
    )
    denied = policy.evaluate(model={"source": "huggingface", "license": "unknown"}, backend="llama.cpp")
    assert denied["allowed"] is False

    state, changes = release_mod.migrate_state({"schema_version": 1, "services": {}})
    assert state["schema_version"] == 2 and changes
    config, changes = release_mod.migrate_config({"version": 1})
    assert config["version"] == 2 and changes

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".rift" / "logs").mkdir(parents=True)
        (root / ".rift" / "state.json").write_text(
            json.dumps({"token": "secret", "services": {}}), encoding="utf-8"
        )
        bundle = release_mod.DiagnosticBundle(root=root).create()
        assert Path(bundle["path"]).is_file()
        assert ".rift/state.json" in bundle["included_files"]


def main():
    test_hardware_profile_and_calibration_labels()
    test_evidence_levels_do_not_claim_metadata_is_benchmark()
    test_artifact_manifest_integrity_and_provenance()
    test_benchmark_statistics_and_regression_gate()
    test_observability_retention_redaction_and_prometheus()
    test_provider_contract_and_api_key_lifecycle()
    test_remote_transport_permission_and_parsing()
    test_rollout_governance_migration_and_diagnostics()
    print("RIFT control-plane roadmap tests passed")


if __name__ == "__main__":
    main()
