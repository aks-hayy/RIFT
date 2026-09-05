import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


def test_profiled_tuning_api_exposes_durable_runs_and_starts_profiled_operation():
    from rift.server import RiftServerRuntime
    from rift.operations import OperationStore
    from rift.tuning_engine import TuningStore

    with tempfile.TemporaryDirectory() as root:
        runtime_root = Path(root) / ".rift"
        runtime_root.mkdir()

        class FakeOrchestrator:
            rift_dir = runtime_root
            backend_host = type("Host", (), {"diagnostics": lambda self: {}})()
            providers = {}

            def profiled_tune_service(self, **kwargs):
                self.last_kwargs = kwargs
                return {
                    "run_id": "tune-api",
                    "service": kwargs["service_name"],
                    "profile": kwargs["profile"],
                    "outcome": "no_improvement",
                    "applied": False,
                }

        orchestrator = FakeOrchestrator()
        store = TuningStore(runtime_root / "tuning.db")
        store.create_run({"run_id": "tune-history", "service": "chat", "profile": "speed", "status": "SUCCEEDED"})
        runtime = RiftServerRuntime(
            orchestrator_factory=lambda: orchestrator,
            operation_store=OperationStore(runtime_root / "operations"),
        )
        assert runtime.is_background_operation("/api/rift/v2/tuning/runs")
        assert runtime.is_background_operation("/api/rift/v2/tuning-runs")
        listed = runtime.control_get("/api/rift/v2/tuning/runs", {"service": ["chat"]})
        assert listed["runs"][0]["run_id"] == "tune-history"
        loaded = runtime.control_get("/api/rift/v2/tuning/runs/tune-history")
        assert loaded["run_id"] == "tune-history"
        result = runtime.control_post(
            "/api/rift/v2/tuning/runs",
            {
                "service": "chat",
                "profile": "cost",
                "allow_restart": True,
                "no_apply": True,
                "dry_run": True,
                "candidate_limit": 12,
                "operation_id": "op-api",
                "target_tokens_per_second": 100,
                "accuracy_tolerance": 0.05,
                "accuracy_case_tolerance": 0.15,
                "retain_accuracy_responses": True,
                "kv_precision_search": False,
            },
        )
        assert result["profile"] == "cost"
        assert orchestrator.last_kwargs["no_apply"] is True
        assert orchestrator.last_kwargs["dry_run"] is True
        assert orchestrator.last_kwargs["candidate_limit"] == 12
        assert orchestrator.last_kwargs["operation_id"] == "op-api"
        assert orchestrator.last_kwargs["target_tokens_per_second"] == 100
        assert orchestrator.last_kwargs["accuracy_tolerance"] == 0.05
        assert orchestrator.last_kwargs["accuracy_case_tolerance"] == 0.15
        assert orchestrator.last_kwargs["retain_accuracy_responses"] is True
        assert orchestrator.last_kwargs["kv_precision_search"] is False
        runtime.shutdown()


def test_tuning_api_rejects_invalid_target_and_tolerances():
    from rift.server import RiftServerRuntime
    from rift.operations import OperationStore
    with tempfile.TemporaryDirectory() as root:
        runtime_root = Path(root) / ".rift"; runtime_root.mkdir()
        class FakeOrchestrator:
            rift_dir = runtime_root
            backend_host = type("Host", (), {"diagnostics": lambda self: {}})()
            providers = {}
            def profiled_tune_service(self, **kwargs): return {"target": {}, "accuracy": {}}
        runtime = RiftServerRuntime(orchestrator_factory=FakeOrchestrator, operation_store=OperationStore(runtime_root / "operations"))
        for key, value in (("target_tokens_per_second", 0), ("target_tokens_per_second", float("inf")), ("accuracy_tolerance", -0.1), ("accuracy_tolerance", float("nan")), ("accuracy_case_tolerance", -0.1)):
            try:
                runtime.control_post("/api/rift/v2/tuning/runs", {"service": "chat", "profile": "speed", key: value})
            except ValueError:
                pass
            else:
                raise AssertionError(f"{key} should be rejected")
        runtime.shutdown()


if __name__ == "__main__":
    test_profiled_tuning_api_exposes_durable_runs_and_starts_profiled_operation()
    print("tuning_api_tests: PASS")
