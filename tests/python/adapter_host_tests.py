import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import types


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


class FakeNativeEngine:
    def __init__(self, cuda_device_id=0):
        self.cuda_device_id = cuda_device_id

    def hardware_profile(self):
        return {
            "cuda_available": True,
            "total_vram_bytes": 8 * 1024**3,
            "free_vram_bytes": 7 * 1024**3,
            "total_host_ram_bytes": 16 * 1024**3,
            "free_host_ram_bytes": 10 * 1024**3,
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


contracts = importlib.import_module("rift.adapters.contracts")
registry_mod = importlib.import_module("rift.adapters.registry")
artifacts_mod = importlib.import_module("rift.adapters.artifacts")
conformance_mod = importlib.import_module("rift.adapters.conformance")
providers_mod = importlib.import_module("rift.providers")
recommendations_mod = importlib.import_module("rift.recommendations")
orchestrator_mod = importlib.import_module("rift.orchestrator")
server_mod = importlib.import_module("rift.server")


class FakeBackend:
    name = "third-party-test"
    manifest = contracts.AdapterManifest(
        adapter_id=name,
        display_name="Third-party test",
        upstream_project="tests/fake",
        adapter_version="1.0.0",
        adapter_api_version=contracts.ADAPTER_API_VERSION,
        kind="backend",
        capability=contracts.BackendCapability(
            tasks=("chat",),
            formats=("testfmt",),
            quantizations=("int4",),
            operating_systems=("windows", "linux", "macos"),
            accelerators=("cpu",),
            installation_methods=("fake",),
        ),
        evidence_status="test",
    )

    def __init__(self):
        self.running = False

    def probe(self, *, search_root=None):
        return {"backend": self.name, "available": True, "search_root": search_root}

    def capabilities(self):
        return self.manifest.capability.to_dict()

    def install_plan(self):
        return {"backend": self.name, "requires_permission": True}

    def install(self, *, target_dir, variant="auto", force=False):
        return {"installed": True, "target_dir": target_dir, "variant": variant, "force": force}

    def evaluate_fit(self, *, artifact, hardware, workload="chat"):
        return {"fits": artifact.get("format") == "testfmt", "reason": workload}

    def build_launch_spec(self, **kwargs):
        return {
            "backend": self.name,
            "command": ["fake-server", "--model", kwargs["model_path"]],
            "api_base": f"http://{kwargs['host']}:{kwargs['port']}",
            "openai_base": f"http://{kwargs['host']}:{kwargs['port']}/v1",
            "tuning": kwargs.get("tuning") or {},
        }

    def launch(self, launch_plan, *, log_path=None):
        self.running = True
        return {"pid": 9001, "api_base": launch_plan["api_base"]}

    def health(self, *, base_url, timeout_seconds=2.0):
        return {"healthy": self.running, "base_url": base_url}

    def benchmark(self, *, base_url, prompt, max_tokens, timeout_seconds=60.0):
        return {"tokens_per_second": 10.0, "generated_tokens": max_tokens}

    def tuning_space(self, *, launch_plan, hardware):
        return [{"batch": 1}, {"batch": 2}]

    def stop(self, *, pid):
        self.running = False
        return {"stopped": True, "pid": pid}

    def recover(self, launch_plan, *, log_path=None):
        return self.launch(launch_plan, log_path=log_path)


class FakeEntryPoint:
    def __init__(self, name, loaded):
        self.name = name
        self.loaded = loaded

    def load(self):
        return self.loaded


class FakeEntryPoints(list):
    def select(self, *, group):
        return self if group == "rift.backend_adapters" else []


def test_entry_point_adapter_requires_no_core_registration_edit():
    original = registry_mod.importlib.metadata.entry_points
    registry_mod.importlib.metadata.entry_points = lambda: FakeEntryPoints(
        [FakeEntryPoint("third-party-test", FakeBackend)]
    )
    try:
        host = registry_mod.BackendAdapterHost(
            builtins=(), entry_point_group="rift.backend_adapters"
        )
    finally:
        registry_mod.importlib.metadata.entry_points = original
    assert "third-party-test" in host.enabled()
    assert host.all()["third-party-test"].source.startswith("entry-point:")


def test_conflicts_fail_closed_without_disabling_first_registration():
    first = FakeBackend()
    second = FakeBackend()
    host = registry_mod.BackendAdapterHost(
        builtins=(first, second),
        entry_point_group="rift.backend_adapters",
        load_entry_points=False,
    )
    assert host.get("third-party-test") is first
    assert any(
        item["code"] == "ADAPTER_ID_CONFLICT"
        for item in host.diagnostics()["host_diagnostics"]
    )


def test_conformance_exercises_complete_fake_lifecycle():
    report = conformance_mod.BackendConformanceSuite().run(
        FakeBackend(), exercise_fake_lifecycle=True
    )
    assert report["passed"], report
    names = {item["name"] for item in report["checks"]}
    assert {"launch", "health", "benchmark", "stop", "recover"}.issubset(names)


def test_builtin_backend_and_overlay_separation():
    backends = providers_mod.backend_adapter_registry(load_entry_points=False)
    overlays = providers_mod.overlay_registry()
    assert {"llama.cpp", "vllm", "sglang", "mlx-lm"}.issubset(backends)
    assert "lmcache_aware" not in backends
    assert "lmcache_aware" in overlays
    assert overlays["lmcache_aware"].manifest.kind == "overlay"


def test_manifest_driven_matching_has_no_static_format_table():
    host = registry_mod.BackendAdapterHost(
        builtins=(FakeBackend(),),
        entry_point_group="rift.backend_adapters",
        load_entry_points=False,
    )
    results = host.rank(
        artifact={
            "artifact_id": "test",
            "format": "testfmt",
            "quantization": "int4_grouped",
            "architecture": "new-architecture",
            "total_bytes": 1,
        },
        hardware={"identity": {"os": "windows"}},
        workload="chat",
    )
    assert results[0].adapter_id == "third-party-test"
    assert results[0].compatible
    embedding_results = host.rank(
        artifact={
            "artifact_id": "test",
            "format": "testfmt",
            "quantization": "int4",
            "architecture": "new-architecture",
            "total_bytes": 1,
        },
        hardware={"identity": {"os": "windows"}},
        workload="embeddings",
    )
    assert not embedding_results[0].compatible
    assert any("workload task embeddings" in reason for reason in embedding_results[0].reasons)


def test_detected_backend_version_can_narrow_static_manifest_capabilities():
    adapter = FakeBackend()
    adapter.probe = lambda search_root=None: {
        "available": True,
        "version": "legacy-test",
        "runtime_feature_probe": {
            "probed": True,
            "flags": {"--quantization": False},
        },
    }
    host = registry_mod.BackendAdapterHost(
        builtins=(adapter,),
        entry_point_group="rift.backend_adapters",
        load_entry_points=False,
    )
    result = host.rank(
        artifact={
            "artifact_id": "test",
            "format": "testfmt",
            "quantization": "int4",
            "architecture": "unknown",
            "total_bytes": 1,
        },
        hardware={"identity": {"os": "windows"}},
        workload="chat",
    )[0]
    assert not result.compatible
    assert any("quantization launch option" in reason for reason in result.reasons)


def test_format_neutral_query_arms_follow_workload_pipeline_tags():
    engine = importlib.import_module("rift.rift").RiftEngine()
    embedding = engine._recommendation_query_arms(
        "embeddings", {"safetensors"}, include_format_arms=False
    )
    assert {item["pipeline_tag"] for item in embedding} == {
        "feature-extraction",
        "sentence-similarity",
    }
    vision = engine._recommendation_query_arms(
        "vision-language", {"gguf", "safetensors"}, include_format_arms=False
    )
    assert {item["pipeline_tag"] for item in vision} == {"image-text-to-text"}


def test_artifact_adapters_resolve_shards_dependencies_and_quantization():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "config.json").write_text(
            json.dumps(
                {
                    "model_type": "llama",
                    "quantization_config": {"quant_method": "awq", "bits": 4},
                }
            ),
            encoding="utf-8",
        )
        (root / "tokenizer.json").write_text("{}", encoding="utf-8")
        (root / "model-00001-of-00002.safetensors").write_bytes(b"a")
        (root / "model-00002-of-00002.safetensors").write_bytes(b"b")
        (root / "model.safetensors.index.json").write_text(
            json.dumps(
                {
                    "weight_map": {
                        "a": "model-00001-of-00002.safetensors",
                        "b": "model-00002-of-00002.safetensors",
                    }
                }
            ),
            encoding="utf-8",
        )
        host = artifacts_mod.artifact_adapter_host(load_entry_points=False)
        variants = host.resolve(artifacts_mod.source_from_local(root))
        assert len(variants) == 1
        variant = variants[0]
        assert variant.format == "awq"
        assert variant.metadata["sharded"]
        assert variant.metadata["expected_shard_count"] == 2
        assert variant.validation["serving_ready"]
        assert variant.total_bytes == 2


def test_artifact_adapter_reports_missing_index_shard():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "config.json").write_text('{"model_type":"llama"}', encoding="utf-8")
        (root / "tokenizer.json").write_text("{}", encoding="utf-8")
        (root / "model-00001-of-00002.safetensors").write_bytes(b"a")
        (root / "model.safetensors.index.json").write_text(
            json.dumps(
                {
                    "weight_map": {
                        "a": "model-00001-of-00002.safetensors",
                        "b": "model-00002-of-00002.safetensors",
                    }
                }
            ),
            encoding="utf-8",
        )
        variant = artifacts_mod.artifact_adapter_host(load_entry_points=False).resolve(
            artifacts_mod.source_from_local(root)
        )[0]
        assert not variant.validation["valid"]
        assert "model-00002-of-00002.safetensors" in variant.validation["missing_dependencies"]


def test_recommendation_runs_are_atomic_and_materialize_deployment_intent():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = recommendations_mod.RecommendationStore(root / ".rift")
        run = {
            "recommendation_run_id": "run-v2-test",
            "recommendation_contract": "RECOMMENDATION_V2_ADAPTER_GRAPH",
            "task": "chat",
            "max_download_gb": 8.0,
            "hardware_profile": {
                "total_vram_bytes": 8 * 1024**3,
                "total_host_ram_bytes": 16 * 1024**3,
            },
            "discovery": {"source": "https://huggingface.co"},
            "categories": {
                "best_estimated": {
                    "repo_id": "org/model",
                    "artifact_id": "org/model:q4",
                }
            },
            "recommendations": [
                {
                    "repo_id": "org/model",
                    "revision": "012345",
                    "backend": "llama.cpp",
                    "format": "gguf",
                    "quantization": "Q4_K_M",
                    "selected_file": "model-q4_k_m.gguf",
                    "selected_files": ["model-q4_k_m.gguf"],
                    "selected_download_bytes": 4 * 1024**3,
                    "selected_artifact": {
                        "artifact_id": "org/model:q4",
                        "format": "gguf",
                        "total_bytes": 4 * 1024**3,
                    },
                    "final_score": 0.91,
                    "confidence": 0.8,
                    "evidence": ["exact artifact inventory"],
                    "warnings": [],
                }
            ],
        }
        path = Path(store.save_recommendation(run))
        assert path.is_file()
        assert not list(path.parent.glob("*.tmp"))
        orchestrator = orchestrator_mod.RiftOrchestrator(root=root)
        materialized = orchestrator.materialize_recommendation_config(
            run_id="run-v2-test"
        )
        service = materialized["config"]["services"]["chat"]
        assert service["model"]["id"] == "org/model"
        assert service["model"]["revision"] == "012345"
        assert service["model"]["selected_file"] == "model-q4_k_m.gguf"
        assert service["policy"]["backend"] == "llama.cpp"
        assert Path(materialized["config_path"]).is_file()


def test_recommendation_store_rejects_path_traversal_ids():
    with tempfile.TemporaryDirectory() as tmp:
        store = recommendations_mod.RecommendationStore(Path(tmp))
        try:
            store.load_recommendation("../state")
        except ValueError as exc:
            assert "unsupported characters" in str(exc)
        else:
            raise AssertionError("path traversal run id was accepted")


def test_recommendation_store_lists_existing_pulled_models_with_metrics():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        pulled = root / "models" / "org--model"
        pulled.mkdir(parents=True)
        (pulled / "model.gguf").write_bytes(b"fixture")
        store = recommendations_mod.RecommendationStore(root / ".rift")
        store.save_recommendation(
            {
                "recommendation_run_id": "pulled-run",
                "task": "coding",
                "categories": {"best_estimated_fit": {"repo_id": "org/model"}},
                "recommendations": [
                    {
                        "repo_id": "org/model",
                        "selected_file": "model.gguf",
                        "format": "gguf",
                        "quantization": "Q4_K_M",
                        "backend": "llama.cpp",
                        "final_score": 0.87,
                        "evidence": ["fits local VRAM", "published benchmark evidence"],
                    }
                ],
                "pull_best": {
                    "local_dir": str(pulled.relative_to(Path.cwd()))
                    if pulled.is_relative_to(Path.cwd())
                    else str(pulled),
                    "completed_unix_seconds": 123,
                },
            }
        )

        listed = store.list_pulled_models()
        assert listed["count"] == 1
        model = listed["models"][0]
        assert model["task"] == "coding"
        assert model["repo_id"] == "org/model"
        assert model["backend"] == "llama.cpp"
        assert model["score"] == 0.87
        assert model["evidence"] == "ESTIMATED"
        assert Path(model["local_dir"]).resolve() == pulled.resolve()


def test_verification_tournament_is_permission_gated_and_records_real_measurement():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        model_root = root / ".rift" / "models" / "org--model"
        model_root.mkdir(parents=True)
        (model_root / "weights.test").write_bytes(b"fixture")
        orchestrator = orchestrator_mod.RiftOrchestrator(root=root)
        provider = FakeBackend()
        orchestrator.providers = {provider.name: provider}
        orchestrator._process_alive = lambda _pid: True
        run = {
            "recommendation_run_id": "verify-source",
            "task": "chat",
            "hardware_profile": FakeNativeEngine().hardware_profile(),
            "discovery": {"source": "https://huggingface.co"},
            "recommendations": [
                {
                    "repo_id": "org/model",
                    "revision": "main",
                    "backend": provider.name,
                    "support_level": "AVAILABLE_NOW",
                    "format": "testfmt",
                    "quantization": "int4",
                    "selected_file": "weights.test",
                    "selected_files": ["weights.test"],
                    "selected_download_bytes": 7,
                    "selected_artifact": {
                        "artifact_id": "org/model:test",
                        "format": "testfmt",
                        "quantization": "int4",
                        "total_bytes": 7,
                    },
                    "final_score": 0.8,
                }
            ],
        }
        orchestrator.recommendation_store.save_recommendation(run)
        blocked = orchestrator.verify_recommendation_run(run_id="verify-source")
        assert blocked["status"] == "blocked"
        assert blocked["permission_gate"]["missing"] == ["allow_launch"]
        assert not provider.running
        verified = orchestrator.verify_recommendation_run(
            run_id="verify-source",
            permissions=orchestrator_mod.ApplyPermissions(allow_launch=True),
            startup_timeout_seconds=1.0,
        )
        assert verified["status"] == "verified", verified
        assert verified["best_verified"]["benchmark"]["tokens_per_second"] == 10.0
        assert verified["best_verified"]["teardown"]["stopped"]
        assert Path(verified["verification_run_path"]).is_file()


def test_api_v2_exposes_dynamic_adapters_runs_and_compatibility():
    with tempfile.TemporaryDirectory() as tmp:
        orchestrator = orchestrator_mod.RiftOrchestrator(root=Path(tmp))
        host = registry_mod.BackendAdapterHost(
            builtins=(FakeBackend(),),
            entry_point_group="rift.backend_adapters",
            load_entry_points=False,
        )
        orchestrator.backend_host = host
        orchestrator.providers = host.enabled()
        orchestrator.recommendation_store.save_recommendation(
            {
                "recommendation_run_id": "api-run",
                "task": "chat",
                "recommendations": [],
            }
        )
        runtime = server_mod.RiftServerRuntime(
            orchestrator_factory=lambda: orchestrator
        )
        adapters = runtime.control_get("/api/rift/v2/adapters")
        assert adapters["api_version"] == "2"
        assert adapters["adapters"][0]["adapter_id"] == "third-party-test"
        converters = runtime.control_get("/api/rift/v2/converter-adapters")
        assert converters["api_version"] == "2"
        assert isinstance(converters["adapters"], list)
        runs = runtime.control_get("/api/rift/v2/recommendation-runs")
        assert runs["count"] == 1
        loaded = runtime.control_get("/api/rift/v2/recommendation-runs/api-run")
        assert loaded["recommendation_run_id"] == "api-run"
        compatibility = runtime.control_post(
            "/api/rift/v2/compatibility",
            {
                "task": "chat",
                "artifact": {
                    "artifact_id": "test",
                    "format": "testfmt",
                    "quantization": "int4",
                    "architecture": "unknown",
                    "total_bytes": 1,
                },
                "hardware": {"identity": {"os": "windows"}},
            },
        )
        assert compatibility["results"][0]["adapter_id"] == "third-party-test"
        assert compatibility["results"][0]["compatible"]


def main():
    test_entry_point_adapter_requires_no_core_registration_edit()
    test_conflicts_fail_closed_without_disabling_first_registration()
    test_conformance_exercises_complete_fake_lifecycle()
    test_builtin_backend_and_overlay_separation()
    test_manifest_driven_matching_has_no_static_format_table()
    test_detected_backend_version_can_narrow_static_manifest_capabilities()
    test_format_neutral_query_arms_follow_workload_pipeline_tags()
    test_artifact_adapters_resolve_shards_dependencies_and_quantization()
    test_artifact_adapter_reports_missing_index_shard()
    test_recommendation_runs_are_atomic_and_materialize_deployment_intent()
    test_recommendation_store_rejects_path_traversal_ids()
    test_recommendation_store_lists_existing_pulled_models_with_metrics()
    test_verification_tournament_is_permission_gated_and_records_real_measurement()
    test_api_v2_exposes_dynamic_adapters_runs_and_compatibility()
    print("RIFT adapter host tests passed")


if __name__ == "__main__":
    main()
