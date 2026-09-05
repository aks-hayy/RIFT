import hashlib
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


class FakeProvider:
    name = "llama.cpp"

    def plan_launch(self, *, model_path, host, port, context_length, concurrency, hardware, tuning=None):
        tuning = dict(tuning or {})
        return {
            "backend": self.name,
            "model_path": model_path,
            "host": host,
            "port": port,
            "context_length": context_length,
            "concurrency": concurrency,
            "api_base": f"http://{host}:{port}",
            "tuning": tuning,
        }

    def tuning_space(self, *, launch_plan, hardware, contract=None):
        baseline = dict(launch_plan.get("tuning") or {})
        return [
            {**baseline, "batch": 256},
            {**baseline, "batch": 512},
        ]

    def benchmark(self, *, base_url, prompt, max_tokens, seed=None, temperature=None, ignore_eos=False):
        if not hasattr(self, "calls"):
            self.calls = []
        self.calls.append({"seed": seed, "temperature": temperature, "ignore_eos": ignore_eos})
        text = "Paris" if "capital" in prompt else "blue and green" if "colors" in prompt else "{\"answer\": true}" if "JSON" in prompt else "HELLO WORLD" if "Uppercase" in prompt else "print('hello')" if "Python greeting" in prompt else "I can't help with that."
        return {"text": text, "status_code": 200, "finish_reason": "stop", "elapsed_seconds": 0.1, "generated_tokens_estimate": 8, "tokens_per_second_estimate": 80.0}


def test_speed_profile_measurements_use_deterministic_sampling_controls():
    from rift.orchestrator import RiftOrchestrator

    provider = FakeProvider()
    orchestrator = object.__new__(RiftOrchestrator)
    orchestrator._profile_measurement(
        provider=provider,
        launch_plan={"api_base": "http://127.0.0.1:1"},
        profile="speed",
        observation={"api_base": "http://127.0.0.1:1"},
        prompt="speed test",
        max_tokens=32,
        warmup_runs=1,
        repeats=1,
        measurement_runner=None,
    )
    assert provider.calls == [
        {"seed": 17, "temperature": 0.0, "ignore_eos": True},
        {"seed": 17, "temperature": 0.0, "ignore_eos": True},
    ]


class StrictOptionalProvider(FakeProvider):
    """Model the llama.cpp adapter's integer serialization for optional flags."""

    def plan_launch(self, *, model_path, host, port, context_length, concurrency, hardware, tuning=None):
        values = dict(tuning or {})
        if "poll" in values:
            int(values["poll"])
        if "poll_batch" in values:
            int(values["poll_batch"])
        return super().plan_launch(
            model_path=model_path,
            host=host,
            port=port,
            context_length=context_length,
            concurrency=concurrency,
            hardware=hardware,
            tuning=values,
        )

    def tuning_space(self, *, launch_plan, hardware, contract=None):
        baseline = {
            key: value
            for key, value in dict(launch_plan.get("tuning") or {}).items()
            if value is not None
        }
        return [{**baseline, "batch": 256}, {**baseline, "batch": 512}]


def make_orchestrator(tmp: Path):
    from rift.orchestrator import RiftOrchestrator

    model = tmp / "model-Q4_K_M.gguf"
    model.write_bytes(b"fixture model")
    service = {
        "backend": "llama.cpp",
        "status": "healthy",
        "desired_state": "running",
        "runtime": {"pid": 1, "api_base": "http://127.0.0.1:11735"},
        "launch_plan": {
            "model_path": str(model),
            "host": "127.0.0.1",
            "port": 11735,
            "context_length": 4096,
            "concurrency": 1,
            "api_base": "http://127.0.0.1:11735",
            "tuning": {
                "batch": 128,
                "ubatch": 64,
                "threads": 4,
                "threads_batch": 4,
                "cache_type_k": "f16",
                "cache_type_v": "f16",
            },
        },
        "serving": {"context_length": 4096, "concurrency": 1},
        "model": {"local_path": str(model), "quantization": "Q4_K_M"},
        "monitoring": {"enabled": True, "resources": {"enabled": True}},
    }
    state = {"services": {"chat": service}, "revision": 3}
    orchestrator = object.__new__(RiftOrchestrator)
    orchestrator.rift_dir = tmp / ".rift"
    orchestrator.rift_dir.mkdir()
    orchestrator.providers = {"llama.cpp": FakeProvider()}
    orchestrator.engine = type("Engine", (), {"hardware_profile": lambda self: {
        "physical_cores": 4,
        "logical_processors": 8,
        "total_vram_bytes": 8 * 1024**3,
    }})()
    orchestrator._state = state
    orchestrator.read_state = lambda: orchestrator._state
    orchestrator.writes = []
    orchestrator.write_state = lambda value: orchestrator.writes.append(value)
    orchestrator._service_observation = lambda *args, **kwargs: {
        "healthy": True,
        "api_base": "http://127.0.0.1:11735",
        "process_alive": True,
        "phase": "healthy",
    }
    orchestrator._replace_service_runtime = lambda **kwargs: {
        "ready": True,
        "runtime": {"pid": 2, "api_base": kwargs["launch_plan"].get("api_base")},
    }
    orchestrator._profile_measurement = lambda **kwargs: kwargs["measurement_runner"](
        kwargs["launch_plan"], kwargs["profile"]
    )
    return orchestrator, state, service


def test_profiled_tuning_locks_model_precision_context_and_monitoring():
    from rift.tuning_engine import TuningStore

    with tempfile.TemporaryDirectory() as root:
        orchestrator, state, service = make_orchestrator(Path(root))
        baseline_launch = dict(service["launch_plan"])
        result = orchestrator.profiled_tune_service(
            service_name="chat",
            profile="speed",
            allow_restart=True,
            candidate_limit=3,
            target_tokens_per_second=1.0,
            write=False,
            measurement_runner=lambda plan, profile: {
                "latency_seconds": 1.0 if plan["tuning"].get("batch") == 512 else 1.2,
                "ttft_seconds": 0.1,
                "tokens": 32,
                "failures": 0,
                "replicates": [1.0, 1.0, 1.0],
            },
        )
        assert result["profile"] == "speed"
        assert result["outcome"] == "improved"
        assert result["applied"] is True
        assert result["precision_locks"]["model_sha256"] == hashlib.sha256(b"fixture model").hexdigest()
        assert result["precision_locks"]["weight_quantization"] == "Q4_K_M"
        assert result["precision_locks"]["cache_type_k"] == "f16"
        assert result["precision_locks"]["cache_type_v"] == "f16"
        assert result["precision_locks"]["context_length"] == 4096
        assert result["precision_locks"]["concurrency"] == 1
        assert service["monitoring"] == {"enabled": True, "resources": {"enabled": True}}
        assert "tuning_active" not in service
        winner_tuning = result["winner"]["config"]
        assert winner_tuning["model_path"] == str(Path(root) / "model-Q4_K_M.gguf")
        assert winner_tuning["cache_type_k"] == "f16"
        assert winner_tuning["context_length"] == 4096
        assert TuningStore(orchestrator.rift_dir / "tuning.db").get_run(result["run_id"])["status"] == "SUCCEEDED"
        assert baseline_launch["tuning"]["batch"] == 128


def test_profiled_tuning_omits_unset_optional_controls_before_launch():
    """A serialized launch summary may contain None for unset poll controls."""

    with tempfile.TemporaryDirectory() as root:
        orchestrator, _state, service = make_orchestrator(Path(root))
        service["launch_plan"]["tuning"]["poll"] = None
        service["launch_plan"]["tuning"]["poll_batch"] = None
        orchestrator.providers = {"llama.cpp": StrictOptionalProvider()}
        result = orchestrator.profiled_tune_service(
            service_name="chat",
            profile="speed",
            allow_restart=True,
            candidate_limit=2,
            target_tokens_per_second=1.0,
            write=False,
            measurement_runner=lambda _plan, _profile: {
                "latency_seconds": 1.0,
                "ttft_seconds": 0.1,
                "tokens": 32,
                "failures": 0,
                "replicates": [1.0, 1.0, 1.0],
            },
        )
        assert result["outcome"] == "no_improvement"
        assert result["applied"] is False
        assert service["launch_plan"]["tuning"]["batch"] == 128


def test_candidate_accuracy_probe_failure_is_rejected_without_aborting_run():
    """A backend HTTP/quality probe error should reject only that candidate."""

    with tempfile.TemporaryDirectory() as root:
        orchestrator, _state, _service = make_orchestrator(Path(root))
        calls = {"count": 0}

        def accuracy_runner(_plan, suite):
            calls["count"] += 1
            if calls["count"] > 1:
                raise RuntimeError("HTTP Error 500: malformed chat output")
            provider = FakeProvider()
            return {
                case.id: provider.benchmark(
                    base_url="http://127.0.0.1:11735",
                    prompt=case.prompt,
                    max_tokens=128,
                    seed=17,
                    temperature=0.0,
                    ignore_eos=False,
                )
                for case in suite.cases
            }

        result = orchestrator.profiled_tune_service(
            service_name="chat",
            profile="speed",
            allow_restart=True,
            candidate_limit=2,
            target_tokens_per_second=1.0,
            write=False,
            accuracy_runner=accuracy_runner,
            measurement_runner=lambda plan, _profile: {
                "latency_seconds": 1.0 if plan["tuning"].get("batch") == 256 else 1.2,
                "ttft_seconds": 0.1,
                "tokens": 32,
                "failures": 0,
                "replicates": [1.0, 1.0, 1.0],
            },
        )

        assert result["outcome"] == "no_improvement"
        assert result["applied"] is False
        candidate = result["candidates"][1]
        assert candidate["status"] == "rejected_accuracy"
        assert "malformed chat output" in candidate["reason"]


def test_explicit_ngram_off_reaches_ordinary_candidates_and_reports_false():
    with tempfile.TemporaryDirectory() as root:
        orchestrator, _state, _service = make_orchestrator(Path(root))
        result = orchestrator.profiled_tune_service(
            service_name="chat",
            profile="speed",
            allow_restart=True,
            ngram_speculation=False,
            candidate_limit=2,
            target_tokens_per_second=1.0,
            write=False,
            measurement_runner=lambda plan, _profile: {
                "latency_seconds": 1.0 if plan["tuning"].get("batch") == 256 else 1.2,
                "ttft_seconds": 0.1,
                "tokens": 32,
                "failures": 0,
                "replicates": [1.0, 1.0, 1.0],
            },
        )

        assert len(result["candidates"]) == 2
        assert all(item.get("config", {}).get("ngram_speculation") is not True for item in result["candidates"])


def test_cost_profile_without_gpu_energy_is_explicitly_unavailable_and_restores():
    with tempfile.TemporaryDirectory() as root:
        orchestrator, _state, service = make_orchestrator(Path(root))
        result = orchestrator.profiled_tune_service(
            service_name="chat",
            profile="cost",
            allow_restart=True,
            candidate_limit=2,
            write=False,
            measurement_runner=lambda _plan, _profile: {
                "latency_seconds": 1.0,
                "tokens": 32,
                "failures": 0,
                "replicates": [1.0, 1.0],
                "energy_available": False,
            },
        )
        assert result["outcome"] == "unavailable"
        assert result["applied"] is False
        assert "GPU energy" in result["reason"]
        assert service["launch_plan"]["tuning"]["batch"] == 128
        assert "tuning_active" not in service


def test_cost_unavailable_run_is_written_to_report_history():
    with tempfile.TemporaryDirectory() as root:
        orchestrator, _state, service = make_orchestrator(Path(root))
        result = orchestrator.profiled_tune_service(
            service_name="chat",
            profile="cost",
            allow_restart=True,
            candidate_limit=2,
            write=True,
            measurement_runner=lambda _plan, _profile: {
                "latency_seconds": 1.0,
                "tokens": 32,
                "failures": 0,
                "energy_available": False,
            },
        )
        assert result["outcome"] == "unavailable"
        assert Path(result["report_path"]).is_file()


def test_monitoring_holds_recovery_and_evaluation_during_tuning_window():
    with tempfile.TemporaryDirectory() as root:
        orchestrator, _state, service = make_orchestrator(Path(root))
        service["tuning_active"] = {"run_id": "tune-test", "profile": "speed"}
        calls = []
        orchestrator._service_observation = lambda *args, **kwargs: calls.append(True) or {
            "healthy": False,
            "phase": "crashed",
        }
        result = orchestrator.reconcile(service_name="chat", allow_recovery=True)
        item = result["results"][0]
        assert item["status"] == "tuning"
        assert item["monitoring"]["suppressed"] is True
        assert calls == []


def test_cli_profiled_tune_dispatches_profile_and_supports_history_actions():
    from rift.cli import commands
    from rift.cli.console import RiftConsole
    from rift.cli.parser import build_parser

    class FakeOrchestrator:
        def __init__(self):
            self.calls = []

        def profiled_tune_service(self, **kwargs):
            self.calls.append(kwargs)
            return {"available": True, "outcome": "improved", "applied": False, "profile": kwargs["profile"]}

    fake = FakeOrchestrator()
    original = commands.RiftOrchestrator
    commands.RiftOrchestrator = lambda: fake
    try:
        args = build_parser().parse_args(
            ["tune", "--service", "chat", "--profile", "speed", "--no-apply", "--budget", "5m", "--yes"]
        )
        assert commands.execute(args, RiftConsole(json_output=True)) == 0
        assert fake.calls[0]["profile"] == "speed"
        assert fake.calls[0]["no_apply"] is True
        assert fake.calls[0]["budget_seconds"] == 300.0
    finally:
        commands.RiftOrchestrator = original


def test_profiled_tuning_cancel_checkpoint_restores_baseline():
    with tempfile.TemporaryDirectory() as root:
        orchestrator, _state, service = make_orchestrator(Path(root))
        result = orchestrator.profiled_tune_service(
            service_name="chat",
            profile="speed",
            allow_restart=True,
            candidate_limit=3,
            write=False,
            cancel_check=lambda: True,
            measurement_runner=lambda plan, profile: {
                "latency_seconds": 1.0,
                "tokens": 32,
                "failures": 0,
                "replicates": [1.0, 1.0],
            },
        )
        assert result["outcome"] == "cancelled"
        assert result["applied"] is False
        assert result["baseline_restored"] is True
        assert "tuning_active" not in service


def test_profiled_tuning_cancel_during_final_promotion_restores_baseline():
    with tempfile.TemporaryDirectory() as root:
        orchestrator, _state, service = make_orchestrator(Path(root))
        calls = {"replace": 0, "cancel": False}

        def replace(**kwargs):
            calls["replace"] += 1
            if calls["replace"] >= 2:
                calls["cancel"] = True
            return {"ready": True, "runtime": {"pid": calls["replace"], "api_base": kwargs["launch_plan"].get("api_base")}}

        orchestrator._replace_service_runtime = replace
        result = orchestrator.profiled_tune_service(
            service_name="chat",
            profile="speed",
            allow_restart=True,
            candidate_limit=2,
            write=False,
            cancel_check=lambda: calls["cancel"],
            target_tokens_per_second=1.0,
            measurement_runner=lambda plan, _profile: {
                "latency_seconds": 0.5 if plan["tuning"].get("batch") == 256 else 1.0,
                "tokens": 32,
                "failures": 0,
                "replicates": [0.5, 0.5],
            },
        )
        assert result["outcome"] == "cancelled"
        assert result["applied"] is False
        assert result["baseline_restored"] is True
        assert service["launch_plan"]["tuning"]["batch"] == 128
        assert "tuning_active" not in service


def test_interrupted_tuning_is_recovered_at_controller_startup():
    from rift.orchestrator import RiftOrchestrator
    from rift.tuning_engine import TuningStore

    with tempfile.TemporaryDirectory() as root:
        orchestrator, state, service = make_orchestrator(Path(root))
        baseline = dict(service["launch_plan"])
        service["launch_plan"] = {**baseline, "tuning": {**baseline["tuning"], "batch": 512}}
        service["tuning_active"] = {"run_id": "tune-interrupted", "profile": "speed"}
        store = TuningStore(orchestrator.rift_dir / "tuning.db")
        store.create_run(
            {
                "run_id": "tune-interrupted",
                "service": "chat",
                "profile": "speed",
                "backend": "llama.cpp",
                "status": "RUNNING",
                "baseline": {"launch_plan": baseline, "tuning": baseline["tuning"]},
            }
        )
        calls = []

        def replace(**kwargs):
            calls.append(kwargs["launch_plan"])
            return {"ready": True, "runtime": {"pid": 7, "api_base": kwargs["launch_plan"].get("api_base")}}

        orchestrator._replace_service_runtime = replace
        result = orchestrator.recover_interrupted_tuning()
        recovered = store.get_run("tune-interrupted")
        assert result["recovered"] == ["tune-interrupted"]
        assert calls and calls[-1]["tuning"]["batch"] == 128
        assert service["launch_plan"]["tuning"]["batch"] == 128
        assert "tuning_active" not in service
        assert recovered["status"] == "INTERRUPTED"
        assert recovered["outcome"] == "interrupted"
        assert recovered["baseline_restored"] is True


def test_server_runtime_invokes_interrupted_tuning_recovery_once_at_startup():
    from rift.server import RiftServerRuntime

    with tempfile.TemporaryDirectory() as root:
        calls = []

        class FakeOrchestrator:
            rift_dir = Path(root) / ".rift"

            def recover_interrupted_tuning(self):
                calls.append(True)
                return {"recovered": [], "failed": []}

        runtime = RiftServerRuntime(orchestrator_factory=FakeOrchestrator)
        assert calls == [True]
        runtime.shutdown()


def test_profiled_tuning_preview_is_read_only_and_shows_locked_contract():
    with tempfile.TemporaryDirectory() as root:
        orchestrator, _state, service = make_orchestrator(Path(root))
        result = orchestrator.profiled_tune_service(
            service_name="chat",
            profile="cost",
            allow_restart=False,
            dry_run=True,
            write=False,
            candidate_limit=3,
        )
        assert result["mode"] == "profiled_preview"
        assert result["outcome"] == "preview"
        assert result["applied"] is False
        assert result["precision_locks"]["weight_quantization"] == "Q4_K_M"
        assert result["candidates"]
        assert "tuning_active" not in service


def test_profiled_tuning_resolves_implicit_llama_kv_cache_defaults():
    with tempfile.TemporaryDirectory() as root:
        orchestrator, _state, service = make_orchestrator(Path(root))
        service["launch_plan"]["tuning"].pop("cache_type_k")
        service["launch_plan"]["tuning"].pop("cache_type_v")
        result = orchestrator.profiled_tune_service(
            service_name="chat",
            profile="speed",
            dry_run=True,
            write=False,
            candidate_limit=2,
        )
        assert result["precision_locks"]["cache_type_k"] == "f16"
        assert result["precision_locks"]["cache_type_v"] == "f16"


def test_profiled_tuning_reports_progress_for_live_operation_surfaces():
    with tempfile.TemporaryDirectory() as root:
        orchestrator, _state, _service = make_orchestrator(Path(root))
        progress = []
        result = orchestrator.profiled_tune_service(
            service_name="chat",
            profile="speed",
            allow_restart=True,
            candidate_limit=2,
            write=False,
            progress=lambda stage, message, percent, details=None: progress.append((stage, percent)),
            measurement_runner=lambda _plan, _profile: {
                "latency_seconds": 1.0,
                "tokens": 32,
                "failures": 0,
                "replicates": [1.0, 1.0],
            },
        )
        assert result["outcome"] in {"improved", "no_improvement"}
        assert any(stage == "candidate" for stage, _percent in progress)


def test_cli_tuning_view_includes_winner_and_tradeoff_explanation():
    import contextlib
    import io
    from rift.cli.console import RiftConsole

    output_buffer = io.StringIO()
    with contextlib.redirect_stdout(output_buffer):
        RiftConsole().render(
            {
                "profile": "speed",
                "outcome": "improved",
                "applied": True,
                "winner": {"config": {"batch": 512, "threads": 8}},
                "decision": "Selected the feasible candidate with 12% higher throughput.",
                "opportunities": [
                    {"title": "Try lower-precision K/V cache", "warning": "May affect quality."}
                ],
            },
            view="tuning",
        )
    output = output_buffer.getvalue()
    assert "Winning configuration" in output
    assert "12% higher throughput" in output
    assert "recommendation only" in output.lower()


def test_cost_improvement_interval_uses_repeated_energy_per_request_samples():
    from rift.orchestrator import RiftOrchestrator
    from rift.tuning_engine import CostMeasurement

    interval = RiftOrchestrator._profile_improvement_interval(
        "cost",
        CostMeasurement(gpu_joules=30.0, requests=3, latency_seconds=1.0, cpu_seconds=1.0, failures=0),
        CostMeasurement(gpu_joules=24.0, requests=3, latency_seconds=1.0, cpu_seconds=1.0, failures=0),
        baseline_raw={"replicates": [10.0, 11.0, 9.0]},
        candidate_raw={"replicates": [8.0, 8.0, 8.0]},
    )
    assert interval[0] > 0.0
    assert interval[1] > interval[0]


def test_accuracy_regression_rejects_fast_candidate():
    with tempfile.TemporaryDirectory() as root:
        orchestrator, _state, service = make_orchestrator(Path(root))
        suite_response = lambda _plan, suite: {
            case.id: {"text": case.reference, "status_code": 200, "finish_reason": "stop"}
            for case in suite.cases
        }
        def accuracy(plan, suite):
            if plan["tuning"].get("batch") != 128:
                return {case.id: {"text": "wrong", "status_code": 200, "finish_reason": "stop"} for case in suite.cases}
            return suite_response(plan, suite)
        result = orchestrator.profiled_tune_service(
            service_name="chat", profile="speed", allow_restart=True, candidate_limit=2,
            write=False, accuracy_runner=accuracy,
            measurement_runner=lambda plan, _profile: {
                "latency_seconds": 0.1, "tokens": 32, "tokens_per_second": 320,
                "failures": 0, "replicates": [0.1, 0.1],
            },
        )
        rejected = [item for item in result["candidates"] if item.get("status") == "rejected_accuracy"]
        assert rejected and result["applied"] is False


def test_validated_target_candidate_is_applied():
    with tempfile.TemporaryDirectory() as root:
        orchestrator, _state, service = make_orchestrator(Path(root))
        def accuracy(_plan, suite):
            return {case.id: {"text": case.reference, "status_code": 200, "finish_reason": "stop"} for case in suite.cases}

        def measured(plan, _profile):
            elapsed = 0.2 if plan["tuning"].get("batch") != 128 else 1.0
            throughput = 160 if plan["tuning"].get("batch") != 128 else 32
            return {
                "latency_seconds": elapsed,
                "tokens": 32,
                "tokens_per_second": throughput,
                "failures": 0,
                "replicates": [elapsed, elapsed],
                "samples": [
                    {
                        "elapsed_seconds": elapsed,
                        "generated_tokens_estimate": int(throughput * elapsed),
                        "tokens_per_second_estimate": throughput,
                    },
                    {
                        "elapsed_seconds": elapsed,
                        "generated_tokens_estimate": int(throughput * elapsed),
                        "tokens_per_second_estimate": throughput,
                    },
                ],
            }

        result = orchestrator.profiled_tune_service(
            service_name="chat", profile="speed", allow_restart=True, candidate_limit=2,
            write=False, target_tokens_per_second=100.0, accuracy_runner=accuracy,
            measurement_runner=measured,
        )
        assert result["applied"] is True
        assert result["target"]["reached"] is True
        assert result["target"]["validated"] is True
        assert result["final_measurement"]["confidence_interval"]["available"] is True
        assert result["target"]["confidence_lower_bound"] >= 100.0
        assert service["launch_plan"]["tuning"]["batch"] == 256


def test_final_validation_does_not_promote_candidate_that_regresses_after_retest():
    """A noisy candidate peak must not be reported as an applied speed win."""

    with tempfile.TemporaryDirectory() as root:
        orchestrator, _state, service = make_orchestrator(Path(root))
        calls = []

        def accuracy(_plan, suite):
            return {case.id: {"text": case.reference, "status_code": 200, "finish_reason": "stop"} for case in suite.cases}

        def measured(_plan, _profile):
            calls.append(True)
            # baseline -> candidate shortlist -> final promotion retest
            tps = (100.0, 150.0, 90.0)[min(len(calls) - 1, 2)]
            elapsed = 32.0 / tps
            return {
                "latency_seconds": elapsed,
                "tokens": 32,
                "tokens_per_second": tps,
                "failures": 0,
                "replicates": [elapsed, elapsed],
            }

        result = orchestrator.profiled_tune_service(
            service_name="chat", profile="speed", allow_restart=True, candidate_limit=2,
            write=False, target_tokens_per_second=1.0, accuracy_runner=accuracy,
            measurement_runner=measured,
        )
        assert len(calls) == 3
        assert result["applied"] is False
        assert result["outcome"] == "no_improvement"
        assert service["launch_plan"]["tuning"]["batch"] == 128


def test_final_confidence_requires_at_least_two_replicates():
    from rift.orchestrator import RiftOrchestrator
    from rift.tuning_engine import CostMeasurement, SpeedMeasurement

    metric = SpeedMeasurement.from_mapping({
        "latency_seconds": 0.1,
        "tokens": 32,
        "tokens_per_second": 320,
        "failures": 0,
    })
    confidence = RiftOrchestrator._profile_confidence_interval(
        "speed", metric, {"tokens_per_second": 320, "replicates": [0.1]},
    )
    assert confidence["available"] is False
    assert confidence["sample_count"] == 0

    missing_per_request = RiftOrchestrator._profile_confidence_interval(
        "speed", metric, {"tokens_per_second": 320, "replicates": [0.1, 0.2, 0.3]},
    )
    assert missing_per_request["available"] is False

    cost_metric = CostMeasurement.from_mapping({
        "gpu_joules": 50, "requests": 5, "latency_seconds": 1, "failures": 0,
    })
    cost_confidence = RiftOrchestrator._profile_confidence_interval(
        "cost", cost_metric, {"replicates": [10, 10, 10, 10, 10]},
    )
    assert cost_confidence["available"] is True
    assert cost_confidence["lower_bound"] == 10.0
    assert cost_confidence["upper_bound"] == 10.0


def test_missing_accuracy_provider_fails_closed_before_fast_candidate_promotion():
    with tempfile.TemporaryDirectory() as root:
        orchestrator, _state, service = make_orchestrator(Path(root))
        orchestrator.providers["llama.cpp"].benchmark = None
        result = orchestrator.profiled_tune_service(
            service_name="chat", profile="speed", allow_restart=True, candidate_limit=2,
            write=False, measurement_runner=lambda _plan, _profile: {
                "latency_seconds": 0.01, "tokens": 1000, "tokens_per_second": 100000,
                "failures": 0, "replicates": [0.01, 0.01],
            },
        )
        assert result["outcome"] == "unavailable"
        assert result["applied"] is False
        assert service["launch_plan"]["tuning"]["batch"] == 128


def test_report_writer_serializes_capability_sets_as_sorted_json_arrays():
    from rift.orchestrator import RiftOrchestrator

    with tempfile.TemporaryDirectory() as root:
        orchestrator, _state, _service = make_orchestrator(Path(root))
        target = Path(root) / "reports" / "capabilities.json"
        orchestrator._write_json(
            target,
            {"capabilities": {"flags": {"threads", "batch-size", "flash-attn"}}},
        )
        payload = json.loads(target.read_text(encoding="utf-8"))
        assert payload["capabilities"]["flags"] == ["batch-size", "flash-attn", "threads"]


if __name__ == "__main__":
    test_profiled_tuning_locks_model_precision_context_and_monitoring()
    test_profiled_tuning_omits_unset_optional_controls_before_launch()
    test_cost_profile_without_gpu_energy_is_explicitly_unavailable_and_restores()
    test_cost_unavailable_run_is_written_to_report_history()
    test_monitoring_holds_recovery_and_evaluation_during_tuning_window()
    test_cli_profiled_tune_dispatches_profile_and_supports_history_actions()
    test_profiled_tuning_cancel_checkpoint_restores_baseline()
    test_profiled_tuning_preview_is_read_only_and_shows_locked_contract()
    test_profiled_tuning_reports_progress_for_live_operation_surfaces()
    test_cli_tuning_view_includes_winner_and_tradeoff_explanation()
    test_cost_improvement_interval_uses_repeated_energy_per_request_samples()
    test_accuracy_regression_rejects_fast_candidate()
    test_validated_target_candidate_is_applied()
    test_missing_accuracy_provider_fails_closed_before_fast_candidate_promotion()
    print("profiled_tuning_tests: PASS")
