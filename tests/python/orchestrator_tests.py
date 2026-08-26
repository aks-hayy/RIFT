import importlib
import json
import os
import shutil
import sys
import subprocess
import tempfile
import threading
import time
import types
import urllib.request
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = ROOT / "python"
sys.path.insert(0, str(PYTHON_ROOT))


class FakeNativeEngine:
    def __init__(self, cuda_device_id=0):
        self.cuda_device_id = cuda_device_id

    def build_info(self):
        return {"version": "test", "phase": "RIFT orchestrator tests"}

    def hardware_profile(self):
        return {
            "cuda_available": True,
            "device_name": "Synthetic RTX 4060 Laptop",
            "total_vram_bytes": 8 * 1024**3,
            "free_vram_bytes": 7 * 1024**3,
            "total_host_ram_bytes": 16 * 1024**3,
            "free_host_ram_bytes": 8 * 1024**3,
            "compute_capability_major": 8,
            "compute_capability_minor": 9,
        }


fake_core = types.ModuleType("rift._core")
fake_core.InferenceEngine = FakeNativeEngine
fake_core.__version__ = "test"
fake_core.build_info = lambda: {"version": "test"}
fake_core.cuda_device_count = lambda: 1
fake_core.inspect_model = lambda *args, **kwargs: {}
fake_core.parse_model_topology = lambda *args, **kwargs: {}
sys.modules["rift._core"] = fake_core

orchestrator_mod = importlib.import_module("rift.orchestrator")
server_mod = importlib.import_module("rift.server")
cli_mod = importlib.import_module("rift.cli")
providers_mod = importlib.import_module("rift.providers")
llama_cpp_mod = importlib.import_module("rift.providers.llama_cpp")
vllm_mod = importlib.import_module("rift.providers.vllm")
sglang_mod = importlib.import_module("rift.providers.sglang")
lmcache_mod = importlib.import_module("rift.providers.lmcache_aware")


def request_json(base_url, path, payload=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(base_url + path, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=5) as response:
        body = response.read().decode("utf-8")
        return response.status, json.loads(body)


def make_fake_ggufs(root: Path) -> Path:
    models = root / "models"
    models.mkdir()
    (models / "tiny-q8_0.gguf").write_bytes(b"q8")
    (models / "tiny-q4_k_m.gguf").write_bytes(b"q4")
    (models / "tiny-q3_k_s.gguf").write_bytes(b"q3")
    return models


class FakeInstallableProvider:
    name = "llama.cpp"

    def __init__(self):
        self.installed = False
        self.launched = False
        self.last_model_path = None

    def detect(self, *, search_root=None):
        return {
            "backend": self.name,
            "available": self.installed,
            "executable": "fake-llama-server" if self.installed else None,
            "source": "fake" if self.installed else None,
            "version": "fake",
        }

    def install_plan(self):
        return {"backend": self.name, "official_sources": ["fake"]}

    def install(self, *, target_dir, variant="auto", force=False):
        self.installed = True
        Path(target_dir).mkdir(parents=True, exist_ok=True)
        return {
            "backend": self.name,
            "installed": True,
            "changed": True,
            "target_dir": target_dir,
            "variant": variant,
            "detection": self.detect(search_root=target_dir),
        }

    def plan_launch(self, *, model_path, host, port, context_length, concurrency, hardware, tuning=None):
        self.last_model_path = model_path
        return {
            "backend": self.name,
            "command": ["fake-llama-server", "-m", model_path],
            "display": f"fake-llama-server -m {model_path}",
            "api_base": f"http://{host}:{port}",
            "openai_base": f"http://{host}:{port}/v1",
            "tuning": tuning or {},
        }

    def model_fit(self, *, model, hardware):
        return {"backend": self.name, "fits": True, "reason": "fake provider accepts fixture"}

    def launch(self, launch_plan, *, log_path=None):
        self.launched = True
        return {"backend": self.name, "pid": 1234, "api_base": launch_plan["api_base"]}

    def health(self, *, base_url, timeout_seconds=2.0):
        return {"backend": self.name, "healthy": self.launched, "url": base_url}

    def benchmark(self, *, base_url, prompt, max_tokens, timeout_seconds=60.0):
        return {"backend": self.name, "generated_tokens_estimate": max_tokens}

    def tune_candidates(self, *, launch_plan, hardware):
        return [{"batch": 128}, {"batch": 256}]


class FakeRecommendationEngine(FakeNativeEngine):
    def __init__(self):
        super().__init__()
        self.pull_calls = 0

    def hardware_profile(self):
        return FakeNativeEngine().hardware_profile()

    def recommend_models(self, **_kwargs):
        selected = {
            "repo_id": "org/multi-quant-gguf",
            "format": "gguf",
            "backend": "llama.cpp",
            "parameters_b": 7.0,
            "selected_file": "model-Q4_K_M.gguf",
            "selected_files": ["model-Q4_K_M.gguf"],
            "quantization": "Q4_K_M",
            "artifact_selection": {
                "path": "model-Q4_K_M.gguf",
                "selected_files": ["model-Q4_K_M.gguf"],
                "quantization": "Q4_K_M",
                "size": 4096,
                "complete": True,
            },
            "disk_feasibility": {
                "status": "fits",
                "required_bytes": 4096,
                "usable_bytes": 10 * 1024**3,
            },
            "evidence": ["exact GGUF artifact selected"],
        }
        return {
            "best_for_hardware": {"absolute_best": selected},
            "recommendations": [selected],
        }

    def pull_model_from_hub(self, repo_id, **kwargs):
        self.pull_calls += 1
        output = Path(kwargs["output_dir"])
        output.mkdir(parents=True, exist_ok=True)
        artifact = output / "model-Q4_K_M.gguf"
        artifact.write_bytes(b"gguf")
        return {
            "repo_id": repo_id,
            "local_dir": str(output),
            "downloaded": [
                {
                    "path": "model-Q4_K_M.gguf",
                    "local_path": str(artifact),
                    "bytes": artifact.stat().st_size,
                }
            ],
        }


class FakeSupervisorProvider(FakeInstallableProvider):
    def __init__(self):
        super().__init__()
        self.installed = True
        self.health_ok = True
        self.launch_count = 0

    def launch(self, launch_plan, *, log_path=None):
        self.launch_count += 1
        pid = 2000 + self.launch_count
        return {
            "backend": self.name,
            "pid": pid,
            "api_base": launch_plan["api_base"],
            "openai_base": launch_plan.get("openai_base"),
        }

    def health(self, *, base_url, timeout_seconds=2.0):
        return {
            "backend": self.name,
            "healthy": self.health_ok,
            "url": base_url,
            "timeout_seconds": timeout_seconds,
        }


class FakeLiveTuningProvider(FakeInstallableProvider):
    def __init__(self):
        super().__init__()
        self.installed = True
        self.alive = {3100}
        self.current_tuning = {"batch": 512}
        self.launch_count = 0

    def launch(self, launch_plan, *, log_path=None):
        self.launch_count += 1
        pid = 3100 + self.launch_count
        self.alive.add(pid)
        self.current_tuning = dict(launch_plan.get("tuning") or {})
        return {
            "backend": self.name,
            "pid": pid,
            "started_unix_seconds": int(time.time()),
            "api_base": launch_plan["api_base"],
            "openai_base": launch_plan.get("openai_base"),
        }

    def health(self, *, base_url, timeout_seconds=2.0):
        return {"backend": self.name, "healthy": bool(self.alive), "url": base_url}

    def benchmark(self, *, base_url, prompt, max_tokens, timeout_seconds=60.0):
        throughput = {256: 8.0, 512: 10.0, 1024: 13.0}.get(
            int(self.current_tuning.get("batch") or 512),
            5.0,
        )
        return {
            "backend": self.name,
            "status_code": 200,
            "elapsed_seconds": max_tokens / throughput,
            "generated_tokens_estimate": max_tokens,
            "tokens_per_second_estimate": throughput,
            "response_preview": "valid fixture response",
        }

    def tune_candidates(self, *, launch_plan, hardware):
        return [{"batch": 256}, {"batch": 1024}]

def test_local_generate_plan_apply_gate_and_tune():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        models = make_fake_ggufs(root)
        orch = orchestrator_mod.RiftOrchestrator(root=root)
        fake_provider = FakeInstallableProvider()
        orch.providers["llama.cpp"] = fake_provider

        created = orch.init_config(overwrite=True)
        assert created["created"] is True
        assert (root / "rift.yaml").exists()

        generated = orch.generate_config(
            source="local",
            models_dir=str(models),
            output="generated.yaml",
        )
        service = generated["config"]["services"]["chat"]
        assert service["policy"]["backend"] == "llama.cpp"
        assert service["model"]["selected_file"].endswith("tiny-q4_k_m.gguf")
        assert service["model"]["decision"]["reason"]

        plan = orch.plan(config_path="generated.yaml")
        assert plan["read_only"] is True
        assert plan["services"]["chat"]["backend"] == "llama.cpp"
        assert any(action["kind"] == "install" for action in plan["actions"])
        assert any(action["kind"] == "launch" for action in plan["actions"])
        assert not any(action["kind"] == "download" for action in plan["actions"])

        blocked = orch.apply(config_path="generated.yaml")
        assert blocked["applied"] is False
        assert "allow_launch" in blocked["required_permissions"]

        progress_events = []
        installed = orch.apply(
            config_path="generated.yaml",
            permissions=orchestrator_mod.ApplyPermissions(allow_install=True, allow_launch=True),
            progress_callback=lambda phase, status, details: progress_events.append(
                (phase, status, details)
            ),
        )
        assert installed["applied"] is True
        assert installed["install_results"][0]["installed"] is True
        assert installed["results"][0]["launched"]["pid"] == 1234
        assert Path(fake_provider.last_model_path).is_absolute()
        assert ("planning", "complete") in {(phase, status) for phase, status, _ in progress_events}
        assert ("installing", "complete") in {(phase, status) for phase, status, _ in progress_events}
        assert ("downloading", "skipped") in {(phase, status) for phase, status, _ in progress_events}
        assert ("launching", "complete") in {(phase, status) for phase, status, _ in progress_events}
        assert ("persisting", "complete") in {(phase, status) for phase, status, _ in progress_events}
        assert ("complete", "complete") in {(phase, status) for phase, status, _ in progress_events}

        tune = orch.tune_service(service_name="chat", plan=plan)
        assert tune["candidates"]
        assert (root / ".rift" / "generated" / "rift.optimized.yaml").exists()

        assert orch.latest_plan()["services"]["chat"]["backend"] == "llama.cpp"
        assert "llama.cpp" in orch.backend_status()["providers"]


def test_llama_cpp_provider_install_from_fake_release_archive():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        archive = root / "llama-fake-bin-win-cuda-cu12.4-x64.zip"
        payload_dir = root / "payload"
        payload_dir.mkdir()
        (payload_dir / "llama-server.exe").write_bytes(b"fake executable")
        with zipfile.ZipFile(archive, "w") as package:
            package.write(payload_dir / "llama-server.exe", "llama-fake/llama-server.exe")

        provider = llama_cpp_mod.LlamaCppProvider()
        original_system = llama_cpp_mod.platform.system
        original_machine = llama_cpp_mod.platform.machine
        original_latest = provider._latest_release_info
        original_download = provider._download_asset
        original_version = provider._version
        try:
            llama_cpp_mod.platform.system = lambda: "Windows"
            llama_cpp_mod.platform.machine = lambda: "AMD64"
            provider._latest_release_info = lambda: {
                "tag_name": "fake",
                "html_url": "https://github.com/ggml-org/llama.cpp/releases/tag/fake",
                "assets": [
                    {
                        "name": "cudart-llama-bin-win-cuda-12.4-x64.zip",
                        "browser_download_url": "https://example.test/cudart.zip",
                    },
                    {
                        "name": archive.name,
                        "browser_download_url": "https://example.test/llama.zip",
                    },
                ],
            }
            provider._download_asset = lambda url, target: shutil.copy2(archive, target)
            provider._version = lambda executable: "fake llama.cpp"
            result = provider.install(target_dir=str(root / "install"), variant="cuda12", force=True)
        finally:
            llama_cpp_mod.platform.system = original_system
            llama_cpp_mod.platform.machine = original_machine
            provider._latest_release_info = original_latest
            provider._download_asset = original_download
            provider._version = original_version

        assert result["installed"] is True
        assert result["detection"]["available"] is True
        assert result["detection"]["executable"].endswith("llama-server.exe")
        assert (root / "install" / "rift-install.json").exists()


def test_hub_exact_artifact_flows_from_generate_to_launch():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orch = orchestrator_mod.RiftOrchestrator(root=root, engine=FakeRecommendationEngine())
        provider = FakeInstallableProvider()
        provider.installed = True
        orch.providers["llama.cpp"] = provider

        generated = orch.generate_config(
            source="huggingface",
            output="generated.yaml",
            candidate_limit=10,
        )
        model = generated["config"]["services"]["chat"]["model"]
        assert model["selected_file"] == "model-Q4_K_M.gguf"
        assert model["selected_files"] == ["model-Q4_K_M.gguf"]
        assert model["quantization"] == "Q4_K_M"

        plan = orch.plan(config_path="generated.yaml")
        download = next(action for action in plan["actions"] if action["kind"] == "download")
        assert download["selected_file"] == "model-Q4_K_M.gguf"
        assert download["required_bytes"] == 4096

        result = orch.apply(
            config_path="generated.yaml",
            permissions=orchestrator_mod.ApplyPermissions(
                allow_download=True,
                allow_launch=True,
            ),
        )
        assert result["applied"] is True
        assert provider.last_model_path.endswith("model-Q4_K_M.gguf")
        assert Path(provider.last_model_path).is_file()
        state = orch.read_state()
        assert state["services"]["chat"]["launch_plan"]["command"][-1].endswith(
            "model-Q4_K_M.gguf"
        )

        reapplied = orch.apply(
            config_path="generated.yaml",
            permissions=orchestrator_mod.ApplyPermissions(
                allow_download=True,
                allow_launch=True,
            ),
        )
        assert reapplied["applied"] is True
        assert orch.engine.pull_calls == 1


def test_plan_source_helpers_accept_hub_urls_and_local_model_inputs():
    assert orchestrator_mod.RiftOrchestrator.normalize_huggingface_repo(
        "https://huggingface.co/org/model/tree/main"
    ) == "org/model"
    assert orchestrator_mod.RiftOrchestrator.normalize_huggingface_repo(
        "https://huggingface.co/api/models/org/model"
    ) == "org/model"

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        models = make_fake_ggufs(root)
        orch = orchestrator_mod.RiftOrchestrator(root=root)
        ranking = orch.rank_local_models(models, task="coding")
        assert ranking["task"] == "coding"
        assert ranking["candidates"]
        assert all(item["evidence"] == "LOCAL_INSPECTION" for item in ranking["candidates"])
        assert all(item["reasons"] for item in ranking["candidates"])


def test_plans_are_saved_in_repository_and_listed_with_concise_metadata():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orch = orchestrator_mod.RiftOrchestrator(root=root)
        orch.init_config(path="rift.yaml")
        created = orch.plan(config_path="rift.yaml")
        assert Path(created["plan_path"]).parent == root / "plans"
        assert Path(created["plan_path"]).is_file()
        assert (root / "plans" / "latest.json").is_file()

        inventory = orch.list_plans()
        assert inventory["root"] == str((root / "plans").resolve())
        assert inventory["count"] == 1
        summary = inventory["plans"][0]
        assert summary["plan_id"] == created["plan_id"]
        assert summary["service_count"] == 1
        assert summary["config_path"].endswith("rift.yaml")


def test_clear_plans_removes_repository_and_runtime_plan_artifacts_only():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orch = orchestrator_mod.RiftOrchestrator(root=root)
        repository_plans = root / "plans"
        runtime_plans = root / ".rift" / "plans"
        repository_plans.mkdir(parents=True)
        runtime_plans.mkdir(parents=True)

        for path in (
            repository_plans / "123-riftplan.json",
            repository_plans / "latest.json",
            repository_plans / "plan-local.yaml",
            repository_plans / "recommendation-run-1.yaml",
            runtime_plans / "456-riftplan.json",
            runtime_plans / "latest.json",
        ):
            path.write_text("generated", encoding="utf-8")
        preserved = repository_plans / "operator-notes.yaml"
        preserved.write_text("keep", encoding="utf-8")

        result = orch.clear_plans()

        assert result["removed_count"] == 6
        assert preserved.is_file()
        assert not (repository_plans / "123-riftplan.json").exists()
        assert not (runtime_plans / "456-riftplan.json").exists()
        assert result["skipped"] == [str(preserved.resolve())]


def test_service_supervisor_recovery_backoff_and_degraded_state():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orch = orchestrator_mod.RiftOrchestrator(root=root)
        provider = FakeSupervisorProvider()
        orch.providers["llama.cpp"] = provider
        alive = {1001}
        orch._process_alive = lambda pid: pid in alive

        def terminate(pid, timeout_seconds=5.0):
            alive.discard(pid)
            return {"pid": pid, "stopped": True, "status": "terminated"}

        orch._terminate_pid = terminate
        orch.write_state(
            {
                "schema_version": 1,
                "services": {
                    "chat": {
                        "backend": "llama.cpp",
                        "model": {"id": "fixture.gguf", "format": "gguf"},
                        "launch_plan": {
                            "backend": "llama.cpp",
                            "command": ["fake-llama-server", "-m", "fixture.gguf"],
                            "api_base": "http://127.0.0.1:19000",
                            "openai_base": "http://127.0.0.1:19000/v1",
                        },
                        "runtime": {
                            "pid": 1001,
                            "api_base": "http://127.0.0.1:19000",
                        },
                        "desired_state": "running",
                        "status": "started",
                        "monitoring": {
                            "enabled": True,
                            "health_timeout_seconds": 1.0,
                            "history_limit": 3,
                        },
                        "recovery": {
                            "enabled": True,
                            "max_restarts": 2,
                            "backoff_seconds": 2.0,
                            "max_backoff_seconds": 8.0,
                            "reset_after_healthy_seconds": 300.0,
                        },
                    }
                },
            }
        )

        status = orch.status()
        assert status["services"]["chat"]["observation"]["healthy"] is True
        assert status["summary"]["healthy"] == 1

        provider.health_ok = False
        alive.clear()
        observed = orch.reconcile(service_name="chat", allow_recovery=False, now=1000.0)
        assert observed["results"][0]["status"] == "crashed"
        assert observed["results"][0]["recovery"]["action"] == "recovery_not_authorized"
        assert orch.incidents()["incident_count"] == 1

        blocked = orch.recover(service_name="chat", allow_launch=False)
        assert blocked["recovered"] is False
        assert blocked["required_permission"] == "allow_launch"

        recovered = orch.recover(service_name="chat", allow_launch=True)
        assert recovered["recovered"] is True
        assert recovered["result"]["new_pid"] == 2001
        assert provider.launch_count == 1
        alive.add(2001)

        state = orch.read_state()
        next_retry = state["services"]["chat"]["supervisor"]["next_retry_unix_seconds"]
        backoff = orch.reconcile(
            service_name="chat",
            allow_recovery=True,
            now=next_retry - 0.25,
        )
        assert backoff["results"][0]["status"] == "backoff"
        assert backoff["results"][0]["recovery"]["action"] == "backoff"
        assert provider.launch_count == 1

        retried = orch.reconcile(
            service_name="chat",
            allow_recovery=True,
            now=next_retry + 0.25,
        )
        assert retried["results"][0]["recovery"]["action"] == "waiting_failure_threshold"
        retried = orch.reconcile(
            service_name="chat",
            allow_recovery=True,
            now=next_retry + 0.5,
        )
        assert retried["results"][0]["recovery"]["action"] == "restarted"
        assert provider.launch_count == 2
        assert retried["results"][0]["recovery"]["new_pid"] == 2002

        alive.clear()
        state = orch.read_state()
        exhausted_at = state["services"]["chat"]["supervisor"]["next_retry_unix_seconds"] + 1.0
        degraded = orch.reconcile(
            service_name="chat",
            allow_recovery=True,
            now=exhausted_at,
        )
        assert degraded["results"][0]["status"] == "degraded"
        assert degraded["results"][0]["recovery"]["action"] == "marked_degraded"
        assert provider.launch_count == 2

        incidents = orch.incidents(limit=20)
        actions = {item["action"] for item in incidents["incidents"]}
        assert {"detected", "restarted", "marked_degraded"}.issubset(actions)
        assert list((root / ".rift" / "incidents").glob("*.json"))
        assert len(orch.read_state()["health_history"]["chat"]) == 3


def test_live_tuning_measures_candidates_and_recovery_rolls_back():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orch = orchestrator_mod.RiftOrchestrator(root=root)
        provider = FakeLiveTuningProvider()
        orch.providers["llama.cpp"] = provider
        orch._process_alive = lambda pid: pid in provider.alive

        def terminate(pid, timeout_seconds=5.0):
            provider.alive.discard(pid)
            return {"pid": pid, "stopped": True, "status": "terminated"}

        orch._terminate_pid = terminate
        baseline_plan = provider.plan_launch(
            model_path="fixture.gguf",
            host="127.0.0.1",
            port=19010,
            context_length=2048,
            concurrency=1,
            hardware=FakeNativeEngine().hardware_profile(),
            tuning={"batch": 512},
        )
        orch.write_state(
            {
                "schema_version": 1,
                "services": {
                    "chat": {
                        "backend": "llama.cpp",
                        "model": {"id": "fixture.gguf", "format": "gguf"},
                        "serving": {
                            "host": "127.0.0.1",
                            "port": 19010,
                            "context_length": 2048,
                            "concurrency": 1,
                        },
                        "launch_plan": baseline_plan,
                        "last_known_good_launch_plan": baseline_plan,
                        "runtime": {
                            "pid": 3100,
                            "started_unix_seconds": int(time.time()) - 30,
                            "api_base": baseline_plan["api_base"],
                        },
                        "desired_state": "running",
                        "status": "healthy",
                    }
                },
            }
        )

        blocked = orch.tune_service(service_name="chat", live=True)
        assert blocked["applied"] is False
        assert blocked["required_permission"] == "allow_restart"

        report = orch.tune_service(
            service_name="chat",
            live=True,
            allow_restart=True,
            candidate_limit=3,
            warmup_runs=0,
            repeats=2,
            startup_timeout_seconds=2.0,
            max_tokens=16,
        )
        assert report["applied"] is True
        assert report["winning_config"]["batch"] == 1024
        assert report["improvement_percent"] == 30.0
        tuned_state = orch.read_state()["services"]["chat"]
        assert tuned_state["last_known_good_launch_plan"]["tuning"]["batch"] == 1024

        bad_plan = dict(tuned_state["launch_plan"])
        bad_plan["tuning"] = {"batch": 2048}
        tuned_state["launch_plan"] = bad_plan
        crashed_pid = int(tuned_state["runtime"]["pid"])
        provider.alive.discard(crashed_pid)
        state = orch.read_state()
        state["services"]["chat"] = tuned_state
        orch.write_state(state)

        recovered = orch.recover(service_name="chat", allow_launch=True)
        assert recovered["recovered"] is True
        assert recovered["result"]["action"] == "rolled_back"
        assert orch.read_state()["services"]["chat"]["launch_plan"]["tuning"]["batch"] == 1024


def test_tune_plan_uses_active_state_when_default_config_missing():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orch = orchestrator_mod.RiftOrchestrator(root=root)
        provider = FakeLiveTuningProvider()
        orch.providers["llama.cpp"] = provider
        baseline_plan = provider.plan_launch(
            model_path="fixture.gguf",
            host="127.0.0.1",
            port=19011,
            context_length=2048,
            concurrency=1,
            hardware=FakeNativeEngine().hardware_profile(),
            tuning={"batch": 512},
        )
        orch.write_state(
            {
                "schema_version": 1,
                "services": {
                    "chat": {
                        "backend": "llama.cpp",
                        "model": {"id": "fixture.gguf", "format": "gguf"},
                        "launch_plan": baseline_plan,
                        "last_known_good_launch_plan": baseline_plan,
                        "runtime": {
                            "pid": 3100,
                            "started_unix_seconds": int(time.time()) - 30,
                            "api_base": baseline_plan["api_base"],
                        },
                        "desired_state": "running",
                        "status": "healthy",
                    }
                },
            }
        )

        report = orch.tune_service(
            service_name="chat",
            config_path=root / "missing-rift.yaml",
        )

        assert report["mode"] == "plan_only"
        assert report["candidates"]
        assert report["baseline"] == {"batch": 512}
        assert "optimized_config_skipped_reason" in report
        assert list((root / ".rift" / "reports").glob("*-chat-tuning.json"))


def test_rebuild_launch_plan_materializes_downloaded_relative_model_path():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        model_dir = root / "models"
        model_dir.mkdir()
        model_file = model_dir / "fixture.gguf"
        model_file.write_bytes(b"fixture")
        orch = orchestrator_mod.RiftOrchestrator(root=root)
        provider = FakeLiveTuningProvider()
        baseline_plan = provider.plan_launch(
            model_path="fixture.gguf",
            host="127.0.0.1",
            port=19012,
            context_length=2048,
            concurrency=1,
            hardware=FakeNativeEngine().hardware_profile(),
            tuning={"batch": 512},
        )
        service = {
            "model": {"selected_file": "fixture.gguf", "format": "gguf"},
            "download": {"local_dir": str(model_dir)},
            "serving": {"host": "127.0.0.1", "port": 19012, "context_length": 2048, "concurrency": 1},
        }

        rebuilt = orch._rebuild_launch_plan(
            provider=provider,
            service=service,
            launch_plan=baseline_plan,
            hardware=FakeNativeEngine().hardware_profile(),
            tuning={"batch": 256},
        )

        assert rebuilt["command"][rebuilt["command"].index("-m") + 1] == str(model_file)


def test_destroy_removes_service_state_but_retains_model_file():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        model_path = root / "models" / "fixture.gguf"
        model_path.parent.mkdir()
        model_path.write_bytes(b"model")
        orch = orchestrator_mod.RiftOrchestrator(root=root)
        orch._terminate_pid = lambda pid: {
            "pid": pid,
            "stopped": True,
            "status": "terminated",
        }
        orch.write_state(
            {
                "schema_version": 1,
                "services": {
                    "chat": {
                        "status": "healthy",
                        "desired_state": "running",
                        "runtime": {"pid": 1234},
                        "model": {"path": str(model_path)},
                    }
                },
            }
        )

        result = orch.destroy(service_name="chat")

        assert result["removed"] == ["chat"]
        assert result["stopped"][0]["pid"] == 1234
        assert "chat" not in orch.read_state()["services"]
        assert model_path.read_bytes() == b"model"


def test_destroy_stops_named_container_and_removes_service_state(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orch = orchestrator_mod.RiftOrchestrator(root=root)
        orch._terminate_pid = lambda pid: {
            "pid": pid,
            "stopped": True,
            "status": "terminated",
        }
        calls = []

        def fake_run(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        monkeypatch.setattr(orchestrator_mod.subprocess, "run", fake_run)
        orch.write_state(
            {
                "schema_version": 1,
                "services": {
                    "chat": {
                        "status": "healthy",
                        "desired_state": "running",
                        "runtime": {"pid": 1234, "container_name": "rift-vllm-11735"},
                        "launch_plan": {
                            "command": [
                                "docker",
                                "run",
                                "--rm",
                                "--name",
                                "rift-vllm-11735",
                            ]
                        },
                    }
                },
            }
        )

        result = orch.destroy(service_name="chat")

        assert result["stopped"][0]["container_termination"]["stopped"] is True
        assert calls == [
            ["docker", "stop", "--time", "10", "rift-vllm-11735"],
            ["docker", "rm", "-f", "rift-vllm-11735"],
        ]


def test_external_provider_registry_and_launch_plans():
    registry = providers_mod.provider_registry()
    assert {"llama.cpp", "vllm", "sglang", "lmcache_aware"}.issubset(registry)

    hardware = FakeNativeEngine().hardware_profile()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fake_vllm = root / "vllm.bat"
        fake_sglang = root / "sglang.bat"
        fake_vllm.write_text("@echo fake vllm 0.0\r\n", encoding="utf-8")
        fake_sglang.write_text("@echo fake sglang 0.0\r\n", encoding="utf-8")
        old_vllm = os.environ.get("VLLM_BIN")
        old_sglang = os.environ.get("SGLANG_BIN")
        try:
            os.environ["VLLM_BIN"] = str(fake_vllm)
            os.environ["SGLANG_BIN"] = str(fake_sglang)

            vllm = vllm_mod.VllmProvider()
            vllm_detect = vllm.detect()
            assert vllm_detect["available"] is True
            assert vllm_detect["executable"] == str(fake_vllm)
            vllm_plan = vllm.plan_launch(
                model_path="C:/models/tiny-safetensors",
                host="127.0.0.1",
                port=18001,
                context_length=2048,
                concurrency=1,
                hardware=hardware,
            )
            assert vllm_plan["command"][:3] == [str(fake_vllm), "serve", "C:/models/tiny-safetensors"]
            assert "--max-model-len" in vllm_plan["command"]
            assert vllm_plan["openai_base"].endswith("/v1")

            sglang = sglang_mod.SglangProvider()
            sglang_detect = sglang.detect()
            assert sglang_detect["available"] is True
            assert sglang_detect["executable"] == str(fake_sglang)
            sglang_plan = sglang.plan_launch(
                model_path="C:/models/tiny-safetensors",
                host="127.0.0.1",
                port=18002,
                context_length=4096,
                concurrency=2,
                hardware=hardware,
            )
            assert sglang_plan["command"][:2] == [str(fake_sglang), "launch_server"]
            assert "--model-path" in sglang_plan["command"]

            lmcache = lmcache_mod.LMCacheAwareProvider()
            lmcache_plan = lmcache.plan_launch(
                model_path="C:/models/tiny-safetensors",
                host="127.0.0.1",
                port=18003,
                context_length=8192,
                concurrency=1,
                hardware=hardware,
            )
            assert lmcache_plan["backend"] == "lmcache_aware"
            assert "--kv-transfer-config" in lmcache_plan["command"]
            assert lmcache_plan["env"]["LMCACHE_CONFIG_FILE"].endswith("lmcache_config.yaml")
            assert "local_cpu: true" in lmcache_plan["lmcache_config"]["content"]
        finally:
            if old_vllm is None:
                os.environ.pop("VLLM_BIN", None)
            else:
                os.environ["VLLM_BIN"] = old_vllm
            if old_sglang is None:
                os.environ.pop("SGLANG_BIN", None)
            else:
                os.environ["SGLANG_BIN"] = old_sglang


def test_safetensors_config_routes_to_vllm_provider_gate():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config = {
            "version": 1,
            "project": "provider-gate-test",
            "nodes": [{"name": "local", "host": "localhost"}],
            "services": {
                "chat": {
                    "model": {
                        "source": "local",
                        "id": "C:/models/tiny-safetensors",
                        "selected_file": "C:/models/tiny-safetensors",
                        "format": "safetensors",
                    },
                    "serving": {
                        "host": "127.0.0.1",
                        "port": 18004,
                        "context_length": 2048,
                        "concurrency": 1,
                    },
                    "policy": {"backend": "auto"},
                }
            },
        }
        orchestrator_mod.write_yaml(root / "rift.yaml", config)
        orch = orchestrator_mod.RiftOrchestrator(root=root)
        plan = orch.plan(config_path="rift.yaml")
        assert plan["services"]["chat"]["backend"] == "vllm"
        assert not any(action["kind"] == "error" for action in plan["actions"])
        assert any(action["kind"] == "install" and action["install_plan"]["backend"] == "vllm" for action in plan["actions"])
        assert any(action["kind"] == "launch" and action["launch_plan"]["backend"] == "vllm" for action in plan["actions"])


def test_control_api_routes_use_orchestrator():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        models = make_fake_ggufs(root)
        orch = orchestrator_mod.RiftOrchestrator(root=root)
        runtime = server_mod.RiftServerRuntime(orchestrator_factory=lambda: orch)
        httpd = server_mod.create_rift_server(host="127.0.0.1", port=0, runtime=runtime)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{httpd.server_port}"
        try:
            status, body = request_json(base_url, "/api/rift/state")
            assert status == 200
            assert body["schema_version"] == 1

            status, body = request_json(
                base_url,
                "/api/rift/generate",
                {"source": "local", "models_dir": str(models), "output": "api-generated.yaml"},
            )
            assert status == 200
            assert body["config"]["services"]["chat"]["model"]["format"] == "gguf"

            status, body = request_json(base_url, "/api/rift/plan", {"config": "api-generated.yaml"})
            assert status == 200
            assert body["services"]["chat"]["backend"] == "llama.cpp"

            status, body = request_json(base_url, "/api/rift/backends")
            assert status == 200
            assert "llama.cpp" in body["providers"]

            status, body = request_json(base_url, "/api/rift/monitor", {"iterations": 1})
            assert status == 200
            assert body["iterations_completed"] == 1

            status, body = request_json(base_url, "/api/rift/incidents")
            assert status == 200
            assert "incidents" in body

            status, body = request_json(base_url, "/api/rift/gateway")
            assert status == 200
            assert "process_alive" in body
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)


def test_recommendation_verification_budget_blocks_before_launch():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orch = orchestrator_mod.RiftOrchestrator(root=root)
        orch.recommendation_store.save_recommendation(
            {
                "recommendation_run_id": "budget-run",
                "task": "chat",
                "recommendations": [
                    {
                        "repo_id": "org/model",
                        "backend": "llama.cpp",
                        "support_level": "INSTALLABLE_BACKEND",
                        "selected_file": "model.gguf",
                        "selected_artifact": {"artifact_id": "model.gguf"},
                        "final_score": 0.8,
                    }
                ],
            }
        )
        report = orch.verify_recommendation_run(
            run_id="budget-run",
            permissions=orchestrator_mod.ApplyPermissions(
                allow_download=True,
                allow_install=True,
                allow_launch=True,
            ),
            finalists=1,
            budget_seconds=0.0,
        )
        assert report["status"] == "blocked"
        assert report["results"][0]["status"] == "BUDGET_EXHAUSTED"
        assert not report["results"][0]["steps"]


def test_terraform_style_cli_smoke():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        models = make_fake_ggufs(root)
        previous = Path.cwd()
        os.chdir(root)
        try:
            assert cli_mod.main(["init", "--overwrite"]) == 0
            assert cli_mod.main(["discover", "--models-dir", str(models)]) == 0
            assert (
                cli_mod.main(
                    [
                        "model",
                        "recommend",
                        "--source",
                        "local",
                        "--models-dir",
                        str(models),
                        "--top",
                        "1",
                        "--output",
                        ".rift/generated/rift.generated.yaml",
                    ]
                )
                == 0
            )
            assert (
                cli_mod.main(
                    [
                        "plan",
                        "--models-dir",
                        str(models),
                        "--select",
                        "1",
                        "--no-prompt",
                        "--materialized-config",
                        ".rift/generated/plan-local.yaml",
                    ]
                )
                == 0
            )
            assert (
                cli_mod.main(
                    [
                        "plan",
                        "--local-model",
                        str(models / "tiny-q4_k_m.gguf"),
                        "--select",
                        "1",
                        "--no-prompt",
                        "--materialized-config",
                        ".rift/generated/plan-file.yaml",
                    ]
                )
                == 0
            )
            assert cli_mod.main(["plan", "--config", ".rift/generated/rift.generated.yaml"]) == 0
            assert cli_mod.main(["apply", "--config", ".rift/generated/rift.generated.yaml"]) == 2
            assert cli_mod.main(["backend", "detect"]) == 0
            assert cli_mod.main(["backend", "install", "vllm"]) == 2
            assert cli_mod.main(["service", "monitor", "--iterations", "1", "--interval-seconds", "0"]) == 0
            assert cli_mod.main(["service", "restart", "--service", "chat"]) == 2
            assert cli_mod.main(["service", "incidents", "--limit", "5"]) == 0
        finally:
            os.chdir(previous)


def main():
    test_local_generate_plan_apply_gate_and_tune()
    test_llama_cpp_provider_install_from_fake_release_archive()
    test_hub_exact_artifact_flows_from_generate_to_launch()
    test_plan_source_helpers_accept_hub_urls_and_local_model_inputs()
    test_plans_are_saved_in_repository_and_listed_with_concise_metadata()
    test_clear_plans_removes_repository_and_runtime_plan_artifacts_only()
    test_service_supervisor_recovery_backoff_and_degraded_state()
    test_live_tuning_measures_candidates_and_recovery_rolls_back()
    test_tune_plan_uses_active_state_when_default_config_missing()
    test_rebuild_launch_plan_materializes_downloaded_relative_model_path()
    test_destroy_removes_service_state_but_retains_model_file()
    test_external_provider_registry_and_launch_plans()
    test_safetensors_config_routes_to_vllm_provider_gate()
    test_control_api_routes_use_orchestrator()
    test_recommendation_verification_budget_blocks_before_launch()
    test_terraform_style_cli_smoke()
    print("rift orchestrator tests passed")


if __name__ == "__main__":
    main()
