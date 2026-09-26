import contextlib
import importlib
import io
import json
import os
import pytest
import sys
import tempfile
import threading
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = ROOT / "python"
sys.path.insert(0, str(PYTHON_ROOT))


class FakeNativeEngine:
    def __init__(self, cuda_device_id=0):
        self.cuda_device_id = cuda_device_id

    def build_info(self):
        return {"version": "test", "phase": "R19 recommendation tests"}

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
            "wsl_available": True,
        }

    def inspect_model(self, model_path, **kwargs):
        return {
            "model_path": model_path,
            "config": {
                "model_type": "llama",
                "family": "LLAMA",
                "quantization": "GPTQ_INT4",
                "num_hidden_layers": 1,
                "hidden_size": 8,
                "vocab_size": 16,
            },
            "topology": {"total_model_bytes": 16, "w_max_bytes": 8},
            "profile": {"supported": True},
            "execution_policy": {"supported": True},
            "generation_readiness": {
                "ready": True,
                "issues": [],
                "output_head_mode": "DENSE_FP16_LM_HEAD_STREAMING",
            },
            "generation_ready": True,
        }


fake_core = types.ModuleType("rift._core")
fake_core.InferenceEngine = FakeNativeEngine
fake_core.__version__ = "test"
fake_core.build_info = lambda: {"version": "test"}
fake_core.cuda_device_count = lambda: 1
fake_core.inspect_model = lambda model_path, **kwargs: FakeNativeEngine().inspect_model(
    model_path, **kwargs
)
fake_core.parse_model_topology = lambda *args, **kwargs: {}
sys.modules["rift._core"] = fake_core

hf_hub = importlib.import_module("rift.hf_hub")
rift = importlib.import_module("rift.rift")
system_profile = importlib.import_module("rift.system_profile")
cli = importlib.import_module("rift.cli")
rift_parser = importlib.import_module("rift.cli.parser")
benchmark_catalog = importlib.import_module("rift.benchmark_catalog")
calibration = importlib.import_module("rift.recommender_calibration")
workload_compiler = importlib.import_module("rift.workload_compiler")


GB = 1024**3

FILES = {
    "org/llama-7b-gptq": {
        "config.json": b'{"model_type":"llama","quantization_config":{"quant_method":"gptq"}}',
        "tokenizer.json": b'{"model":"tiny"}',
        "model.safetensors": b"llama-gptq-weights",
    },
    "org/coder-7b-gguf": {
        "config.json": b'{"model_type":"llama"}',
        "tokenizer.json": b'{"model":"tiny"}',
        "model-q4_k_m.gguf": b"gguf-weights",
        "model-q5_k_m.gguf": b"gguf-q5-weights",
        "model-q8_0.gguf": b"gguf-q8-weights",
    },
    "org/big-bf16-70b": {
        "config.json": b'{"model_type":"llama"}',
        "model-00001-of-00008.safetensors": b"big-weights",
    },
    "org/unsafe-bin": {
        "config.json": b'{"model_type":"llama"}',
        "pytorch_model.bin": b"pickle-weights",
    },
    "org/gated-gptq": {
        "config.json": b'{"model_type":"llama","quantization_config":{"quant_method":"gptq"}}',
        "tokenizer.json": b'{"model":"tiny"}',
        "model.safetensors": b"gated-weights",
    },
}


def sibling(path, size):
    return {"rfilename": path, "size": size}


SEARCH_MODELS = [
    {
        "id": "org/llama-7b-gptq",
        "pipeline_tag": "text-generation",
        "tags": ["llama", "gptq", "instruct", "chat", "license:apache-2.0"],
        "downloads": 25_000,
        "likes": 300,
        "trendingScore": 3.0,
        "num_parameters": 7_000_000_000,
        "siblings": [
            sibling("config.json", len(FILES["org/llama-7b-gptq"]["config.json"])),
            sibling("tokenizer.json", len(FILES["org/llama-7b-gptq"]["tokenizer.json"])),
            sibling("model.safetensors", 4 * GB),
        ],
    },
    {
        "id": "org/coder-7b-gguf",
        "pipeline_tag": "text-generation",
        "tags": ["llama", "gguf", "code", "license:apache-2.0"],
        "downloads": 15_000,
        "likes": 260,
        "trendingScore": 4.0,
        "num_parameters": 7_000_000_000,
        "siblings": [
            sibling("config.json", len(FILES["org/coder-7b-gguf"]["config.json"])),
            sibling("tokenizer.json", len(FILES["org/coder-7b-gguf"]["tokenizer.json"])),
            sibling("model-q4_k_m.gguf", None),
            sibling("model-q5_k_m.gguf", None),
            sibling("model-q8_0.gguf", None),
        ],
    },
    {
        "id": "org/big-bf16-70b",
        "pipeline_tag": "text-generation",
        "tags": ["llama", "safetensors", "instruct", "license:apache-2.0"],
        "downloads": 900_000,
        "likes": 8_000,
        "trendingScore": 90.0,
        "num_parameters": 70_000_000_000,
        "siblings": [
            sibling("config.json", len(FILES["org/big-bf16-70b"]["config.json"])),
            sibling("model-00001-of-00008.safetensors", 80 * GB),
        ],
    },
    {
        "id": "org/unsafe-bin",
        "pipeline_tag": "text-generation",
        "tags": ["llama", "instruct", "license:apache-2.0"],
        "downloads": 50_000,
        "likes": 400,
        "trendingScore": 1.0,
        "num_parameters": 7_000_000_000,
        "siblings": [
            sibling("config.json", len(FILES["org/unsafe-bin"]["config.json"])),
            sibling("pytorch_model.bin", 4 * GB),
        ],
    },
    {
        "id": "org/gated-gptq",
        "pipeline_tag": "text-generation",
        "tags": ["llama", "gptq", "instruct", "license:apache-2.0"],
        "downloads": 40_000,
        "likes": 350,
        "trendingScore": 8.0,
        "num_parameters": 7_000_000_000,
        "gated": True,
        "siblings": [
            sibling("config.json", len(FILES["org/gated-gptq"]["config.json"])),
            sibling("tokenizer.json", len(FILES["org/gated-gptq"]["tokenizer.json"])),
            sibling("model.safetensors", 4 * GB),
        ],
    },
]


MODEL_DETAILS = {
    item["id"]: {
        **item,
        "sha": f"sha-{item['id']}",
        "config": {
            "model_type": "llama",
            "quantization_config": {"quant_method": "gptq"} if "gptq" in item["id"] else {},
        },
        "cardData": {"license": "apache-2.0"},
    }
    for item in SEARCH_MODELS
}
MODEL_DETAILS["org/coder-7b-gguf"]["config"] = {"model_type": "llama"}
MODEL_DETAILS["org/big-bf16-70b"]["config"] = {"model_type": "llama"}
MODEL_DETAILS["org/unsafe-bin"]["config"] = {"model_type": "llama"}


class FakeRecommendHubHandler(BaseHTTPRequestHandler):
    search_calls = 0
    info_calls = 0
    tree_calls = 0
    download_calls = 0

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/api/models":
            FakeRecommendHubHandler.search_calls += 1
            self._send_json(SEARCH_MODELS)
            return
        if path.startswith("/api/models/") and "/revision/" in path:
            FakeRecommendHubHandler.info_calls += 1
            repo_id = path[len("/api/models/") :].split("/revision/", 1)[0]
            if repo_id in MODEL_DETAILS:
                self._send_json(MODEL_DETAILS[repo_id])
                return
        if path.startswith("/api/models/") and "/tree/" in path:
            FakeRecommendHubHandler.tree_calls += 1
            repo_id = path[len("/api/models/") :].split("/tree/", 1)[0]
            details = MODEL_DETAILS.get(repo_id)
            if details:
                exact_sizes = {
                    "model-q4_k_m.gguf": 4 * GB,
                    "model-q5_k_m.gguf": int(5.2 * GB),
                    "model-q8_0.gguf": 8 * GB,
                }
                self._send_json(
                    [
                        {
                            "type": "file",
                            "path": item["rfilename"],
                            "size": exact_sizes.get(item["rfilename"], item.get("size")),
                        }
                        for item in details.get("siblings", [])
                    ]
                )
                return
        if "/resolve/" in path:
            prefix = path.strip("/").split("/resolve/", 1)
            repo_id = prefix[0]
            filename = prefix[1].split("/", 1)[1]
            if repo_id in FILES and filename in FILES[repo_id]:
                FakeRecommendHubHandler.download_calls += 1
                self._send_bytes(FILES[repo_id][filename])
                return
        self.send_error(404)

    def log_message(self, fmt, *args):
        return

    def _send_json(self, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class FakeRecommendHubServer:
    def __enter__(self):
        FakeRecommendHubHandler.search_calls = 0
        FakeRecommendHubHandler.info_calls = 0
        FakeRecommendHubHandler.tree_calls = 0
        FakeRecommendHubHandler.download_calls = 0
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeRecommendHubHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return f"http://127.0.0.1:{self.httpd.server_port}"

    def __exit__(self, exc_type, exc, tb):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


def test_hub_search_cache_and_refresh():
    with FakeRecommendHubServer() as endpoint, tempfile.TemporaryDirectory() as tmp:
        client = hf_hub.HfHubClient(endpoint=endpoint, cache_dir=str(Path(tmp) / "cache"))
        first = client.search_models(search="instruct", limit=5, sort="downloads")
        second = client.search_models(search="instruct", limit=5, sort="downloads")
        assert len(first) == len(SEARCH_MODELS)
        assert second[0]["id"] == first[0]["id"]
        assert FakeRecommendHubHandler.search_calls == 1
        refreshed = client.search_models(search="instruct", limit=5, sort="downloads", refresh=True)
        assert refreshed[0]["id"] == first[0]["id"]
        assert FakeRecommendHubHandler.search_calls == 2


def test_verify_cli_defaults_to_one_and_exposes_budget_controls():
    parser = rift_parser.build_parser()
    default = parser.parse_args(["model", "recommend", "--verify"])
    assert default.verify is True
    assert default.verify_top is None
    assert default.verify_finalists is None
    explicit = parser.parse_args(["model", "recommend", "--verify", "--verify-top", "3", "--verify-budget", "5"])
    assert explicit.verify_top == 3
    assert explicit.verify_budget == 5.0
    discovery = parser.parse_args([
        "model", "recommend", "--workload-id", "draft-1", "--workload-revision", "2",
        "--search-candidate-limit", "400", "--model-ref", "org/model",
    ])
    assert discovery.workload_id == "draft-1"
    assert discovery.workload_revision == 2
    assert discovery.search_candidate_limit == 400
    assert discovery.model_ref == "org/model"


def test_simulated_hardware_profile_accepts_compact_input():
    profile = system_profile.simulate_hardware_profile(
        "gpu=RTX 5090,vram_gb=32,ram_gb=64,disk_free_gb=500,os=linux"
    )
    assert profile["profile_kind"] == "simulated"
    assert profile["device_name"] == "RTX 5090"
    assert profile["total_vram_bytes"] == 32 * GB
    assert profile["total_host_ram_bytes"] == 64 * GB
    assert profile["pressure"]["disk_free_bytes"] == 500 * GB
    assert profile["identity"]["os"] == "Linux"
    assert profile["simulation"]["enabled"] is True


def test_simulated_recommendation_uses_profile_and_marks_result():
    parser = rift_parser.build_parser()
    parsed = parser.parse_args(
        [
            "model",
            "recommend",
            "--simulate-hardware",
            "gpu=RTX 5090,vram_gb=32,ram_gb=64,disk_free_gb=500,os=linux",
        ]
    )
    assert parsed.simulate_hardware.startswith("gpu=RTX 5090")

    with FakeRecommendHubServer() as endpoint, tempfile.TemporaryDirectory() as tmp:
        engine = rift.RiftEngine()
        result = engine.recommend_models(
            task="chat",
            top=2,
            candidate_limit=20,
            max_download_gb=12,
            endpoint=endpoint,
            cache_dir=str(Path(tmp) / "cache"),
            enrichment_cap=3,
            simulated_hardware=parsed.simulate_hardware,
        )
    assert result["hardware_profile"]["profile_kind"] == "simulated"
    assert result["hardware_profile"]["device_name"] == "RTX 5090"
    assert result["hardware_profile"]["total_vram_bytes"] == 32 * GB
    assert result["hardware_simulation"]["enabled"] is True
    assert result["disk_profile"]["free_bytes"] == 500 * GB
    assert result["recommendations"]


def test_recommendation_exposes_benchmark_sites_and_diversified_search():
    with FakeRecommendHubServer() as endpoint, tempfile.TemporaryDirectory() as tmp:
        result = rift.RiftEngine().recommend_models(
            task="chat",
            top=2,
            candidate_limit=20,
            max_download_gb=12,
            endpoint=endpoint,
            cache_dir=str(Path(tmp) / "cache"),
            enrichment_cap=3,
            persist_run=False,
        )
    assert {
        "arena",
        "evalplus",
        "livebench",
        "bigcodebench",
    }.issubset({item["source_id"] for item in result["benchmark_sources"]})
    arm_names = {item["name"] for item in result["query_arms"]}
    assert {"format_gguf", "format_awq", "format_gptq", "format_safetensors"}.issubset(arm_names)
    assert {"small_parameter_band", "medium_parameter_band", "large_parameter_band"}.issubset(arm_names)
    assert result["discovery"]["query_strategy_version"] == "R20_DIVERSIFIED_EVIDENCE_FUNNEL"


def test_hugging_face_eval_results_preserve_benchmark_task_and_provenance():
    evidence = rift.RiftEngine()._candidate_eval_evidence(
        {
            "id": "org/coder-7b-gguf",
            "evalResults": [
                {
                    "dataset_id": "open-code-eval/benchmark",
                    "dataset_name": "Open Code Eval",
                    "task_id": "code_generation",
                    "task_type": "text-generation",
                    "metric_type": "pass@1",
                    "value": 0.64,
                    "source": {"name": "Verified leaderboard", "url": "https://example.test/results"},
                    "verifyToken": "verified-token",
                }
            ],
        }
    )

    assert evidence["present"] is True
    assert evidence["metrics"] == [
        {
            "benchmark_id": "open-code-eval/benchmark",
            "benchmark_name": "Open Code Eval",
            "task_id": "code_generation",
            "task_type": "text-generation",
            "name": "pass@1",
            "value": 0.64,
            "source": "Verified leaderboard",
            "source_url": "https://example.test/results",
            "verification": "verified",
        }
    ]


def test_public_eval_scores_only_change_ranking_for_shared_task_relevant_metrics():
    engine = rift.RiftEngine()
    unrelated = {
        "benchmark_id": "general/chat",
        "task_id": "chat",
        "task_type": "text-generation",
        "name": "accuracy",
        "value": 0.99,
        "source": "publisher",
        "verification": "community",
    }
    shared = {
        "benchmark_id": "public/code-eval",
        "task_id": "code_generation",
        "task_type": "text-generation",
        "name": "pass@1",
        "source": "public leaderboard",
        "verification": "verified",
    }
    candidates = [
        {
            "repo_id": "org/model-a",
            "final_score": 0.80,
            "scores": {"quality_proxy": 0.70},
            "evaluation_evidence": {"metrics": [{**shared, "value": 0.42}, unrelated]},
        },
        {
            "repo_id": "org/model-b",
            "final_score": 0.79,
            "scores": {"quality_proxy": 0.69},
            "evaluation_evidence": {"metrics": [{**shared, "value": 0.81}]},
        },
    ]

    ranked = engine._rank_with_public_evaluations(candidates, task="coding")

    assert ranked[0]["repo_id"] == "org/model-b"
    assert ranked[0]["public_evaluation_comparison"]["benchmark_count"] == 1
    assert ranked[0]["public_evaluation_comparison"]["score"] == 1.0
    assert ranked[1]["public_evaluation_comparison"]["score"] == 0.0
    assert ranked[1]["public_evaluation_comparison"]["ignored_metric_count"] == 1


def test_live_hub_evaluations_flow_into_best_fit_recommendation():
    repo_values = {
        "org/llama-7b-gptq": 0.20,
        "org/coder-7b-gguf": 0.95,
    }
    previous = {
        repo_id: MODEL_DETAILS[repo_id].get("evalResults")
        for repo_id in repo_values
    }
    for repo_id, value in repo_values.items():
        MODEL_DETAILS[repo_id]["evalResults"] = [
            {
                "dataset": {"id": "public/code-eval", "name": "Public Code Eval"},
                "task_id": "code_generation",
                "task_type": "code-generation",
                "metric_type": "pass@1",
                "value": value,
                "source": {"name": "Verified public leaderboard", "url": "https://example.test/code"},
                "verifyToken": "verified-token",
            }
        ]
    try:
        with FakeRecommendHubServer() as endpoint, tempfile.TemporaryDirectory() as tmp:
            result = rift.RiftEngine().recommend_models(
                task="coding",
                top=10,
                candidate_limit=20,
                max_download_gb=12,
                endpoint=endpoint,
                cache_dir=str(Path(tmp) / "cache"),
                enrichment_cap=5,
                artifact_enrichment_cap=5,
                persist_run=False,
            )
    finally:
        for repo_id, old in previous.items():
            if old is None:
                MODEL_DETAILS[repo_id].pop("evalResults", None)
            else:
                MODEL_DETAILS[repo_id]["evalResults"] = old

    published = [
        item for item in result["recommendations"]
        if item.get("public_evaluation_comparison", {}).get("score") is not None
    ]
    assert len(published) == 2
    assert result["best_for_hardware"]["best_accuracy_proxy"]["repo_id"] == "org/coder-7b-gguf"
    assert result["best_for_hardware"]["best_accuracy_proxy"]["public_evaluation_comparison"]["score"] == 1.0
    assert result["categories"]["best_published_quality"]["repo_id"] == "org/coder-7b-gguf"


def test_public_metric_percent_and_fraction_scales_are_compared_consistently():
    engine = rift.RiftEngine()
    candidates = [
        {
            "repo_id": "org/fraction-score",
            "final_score": 0.8,
            "scores": {"quality_proxy": 0.7},
            "evaluation_evidence": {"metrics": [{
                "benchmark_id": "public/chat-eval", "task_id": "chat", "task_type": "chat",
                "name": "accuracy", "value": 0.72, "verification": "verified",
            }]},
        },
        {
            "repo_id": "org/percent-score",
            "final_score": 0.79,
            "scores": {"quality_proxy": 0.69},
            "evaluation_evidence": {"metrics": [{
                "benchmark_id": "public/chat-eval", "task_id": "chat", "task_type": "chat",
                "name": "accuracy", "value": 72.0, "verification": "verified",
            }]},
        },
    ]

    ranked = engine._rank_with_public_evaluations(candidates, task="chat")

    assert ranked[0]["repo_id"] == "org/fraction-score"
    assert ranked[0]["public_evaluation_comparison"]["score"] == 0.5
    assert ranked[1]["public_evaluation_comparison"]["score"] == 0.5


def test_compiled_workload_controls_hub_discovery_and_search_breadth():
    contract = workload_compiler.compile_workload(
        {
            "task": "rag",
            "objective": "speed",
            "performance": {"context_tokens": 16384, "concurrency": 2, "min_decode_tps": 20},
            "quality": {"suite_id": "rift-text-core", "suite_version": "v1", "minimum_score": 0.8, "required_cases": ["response_nonempty"]},
            "capabilities": {"tool_calling": False, "structured_output": False},
            "policies": {"network": "approved_sources", "backend": "llama.cpp", "model_family": "Mamba-2"},
            "service": {"name": "rag"},
        },
        confirm_default_quality=True,
    )["contract"]
    with FakeRecommendHubServer() as endpoint, tempfile.TemporaryDirectory() as tmp:
        result = rift.RiftEngine().recommend_models(
            task="chat",
            workload_contract=contract,
            top=1,
            candidate_limit=1,
            search_candidate_limit=8,
            endpoint=endpoint,
            cache_dir=str(Path(tmp) / "cache"),
            enrichment_cap=3,
            persist_run=False,
        )
    assert result["task"] == "rag"
    assert result["workload_profile"]["context_length"] == 16384
    assert result["workload_profile"]["concurrency"] == 2
    assert result["search_candidate_limit"] == 8
    assert result["candidate_counts"]["raw"] <= 8
    assert result["workload_contract_hash"]
    assert result["recommendations"][0]["workload_match"]["objective"] == "speed"


def test_offline_workload_contract_never_queries_hugging_face():
    contract = workload_compiler.compile_workload(
        "Offline RAG assistant, 8K context", confirm_default_quality=True
    )["contract"]
    with FakeRecommendHubServer() as endpoint, tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(ValueError, match="offline workload requires local"):
            rift.RiftEngine().recommend_models(
                workload_contract=contract,
                endpoint=endpoint,
                cache_dir=str(Path(tmp) / "cache"),
                persist_run=False,
            )
        assert FakeRecommendHubHandler.search_calls == 0


def test_calibration_matrix_contains_real_and_fifty_simulated_profiles():
    scenarios = calibration.build_calibration_scenarios(
        real_profile={"device_name": "RTX 4060 Laptop", "profile_kind": "real"}
    )
    assert len(scenarios) == 51
    assert sum(item["profile_kind"] == "real" for item in scenarios) == 1
    assert sum(item["profile_kind"] == "simulated" for item in scenarios) == 50
    assert any("mobile" in item["scenario_id"] for item in scenarios)
    assert any(item["relative_tier"] == "weaker" for item in scenarios)
    assert any(item["relative_tier"] == "stronger" for item in scenarios)
    assert all(item["reference_label"] == "external_evidence_baseline" for item in scenarios)


def test_simulation_rejects_side_effectful_cli_modes():
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        code = cli.main(
            [
                "model",
                "recommend",
                "--simulate-hardware",
                "gpu=RTX 5090,vram_gb=32,ram_gb=64,disk_free_gb=500,os=linux",
                "--verify",
            ]
        )
    assert code == 2


def test_unsupported_simulated_platform_has_no_best_deployment():
    with FakeRecommendHubServer() as endpoint, tempfile.TemporaryDirectory() as tmp:
        result = rift.RiftEngine().recommend_models(
            task="chat",
            top=3,
            candidate_limit=20,
            max_download_gb=12,
            endpoint=endpoint,
            cache_dir=str(Path(tmp) / "mobile-cache"),
            enrichment_cap=3,
            persist_run=False,
            simulated_hardware=(
                "gpu=Adreno 750 shared GPU,vram_gb=1,ram_gb=8,disk_free_gb=32,"
                "os=android,cuda=false"
            ),
        )
    assert result["recommendations"]
    assert all(item["support_level"] == "UNSUPPORTED" for item in result["recommendations"])
    assert result["answer"]["absolute_best_repo_id"] is None


def test_enriched_gated_candidate_is_removed_after_metadata_refresh():
    original = MODEL_DETAILS["org/llama-7b-gptq"].get("gated")
    MODEL_DETAILS["org/llama-7b-gptq"]["gated"] = True
    try:
        with FakeRecommendHubServer() as endpoint, tempfile.TemporaryDirectory() as tmp:
            result = rift.RiftEngine().recommend_models(
                task="chat",
                top=3,
                candidate_limit=20,
                max_download_gb=12,
                endpoint=endpoint,
                cache_dir=str(Path(tmp) / "gated-cache"),
                enrichment_cap=3,
                persist_run=False,
            )
    finally:
        if original is None:
            MODEL_DETAILS["org/llama-7b-gptq"].pop("gated", None)
        else:
            MODEL_DETAILS["org/llama-7b-gptq"]["gated"] = original
    assert "org/llama-7b-gptq" not in [item["repo_id"] for item in result["recommendations"]]


def test_low_host_memory_rejects_artifact_without_runtime_headroom():
    engine = rift.RiftEngine()
    hardware = system_profile.simulate_hardware_profile(
        "gpu=GTX 1650,vram_gb=4,ram_gb=8,disk_free_gb=50,os=windows"
    )
    disk = system_profile.simulated_disk_capacity(hardware, reserve_bytes=2 * GB)
    scored = engine._score_hub_candidate(
        {
            "id": "org/large-awq",
            "tags": ["awq", "instruct", "chat", "license:apache-2.0"],
            "num_parameters": 12_000_000_000,
            "config": {"model_type": "llama", "quantization_config": {"quant_method": "awq"}},
            "cardData": {"license": "apache-2.0"},
            "siblings": [
                {"rfilename": "config.json", "size": 512},
                {"rfilename": "tokenizer.json", "size": 512},
                {"rfilename": "model.safetensors", "size": int(7.75 * GB)},
            ],
        },
        hardware=hardware,
        task="chat",
        mode="balanced",
        allowed_formats={"awq", "safetensors"},
        max_download_bytes=12 * GB,
        include_gated=False,
        disk_profile=disk,
    )
    assert scored["excluded"] is True
    assert "host RAM headroom" in scored["exclusion_reason"]


def test_unrelated_public_eval_metadata_does_not_inflate_quality_or_confidence():
    engine = rift.RiftEngine()
    hardware = system_profile.simulate_hardware_profile(
        "gpu=RTX 4060,vram_gb=8,ram_gb=16,disk_free_gb=100,os=windows"
    )
    disk = system_profile.simulated_disk_capacity(hardware, reserve_bytes=2 * GB)
    candidate = {
        "id": "org/general-chat-7b",
        "pipeline_tag": "text-generation",
        "tags": ["llama", "gguf", "instruct", "chat", "license:apache-2.0"],
        "num_parameters": 7_000_000_000,
        "config": {"model_type": "llama"},
        "cardData": {"license": "apache-2.0"},
        "siblings": [
            {"rfilename": "config.json", "size": 512},
            {"rfilename": "model-q4_k_m.gguf", "size": 4 * GB},
        ],
    }
    baseline = engine._score_hub_candidate(
        candidate,
        hardware=hardware,
        task="chat",
        mode="balanced",
        allowed_formats={"gguf"},
        max_download_bytes=12 * GB,
        include_gated=False,
        disk_profile=disk,
    )
    with_unrelated_eval = engine._score_hub_candidate(
        {
            **candidate,
            "model-index": [{
                "results": [{
                    "task": {"type": "text-generation", "name": "code generation"},
                    "dataset": {"type": "public/code-benchmark", "name": "code benchmark"},
                    "metrics": [{"type": "pass@1", "value": 0.99}],
                }]
            }],
        },
        hardware=hardware,
        task="chat",
        mode="balanced",
        allowed_formats={"gguf"},
        max_download_bytes=12 * GB,
        include_gated=False,
        disk_profile=disk,
    )

    assert with_unrelated_eval["scores"]["quality_proxy"] == baseline["scores"]["quality_proxy"]
    assert with_unrelated_eval["confidence"] == baseline["confidence"]


def test_recommendation_scoring_filters_and_enrichment_cap():
    with FakeRecommendHubServer() as endpoint, tempfile.TemporaryDirectory() as tmp:
        engine = rift.RiftEngine()
        result = engine.recommend_models(
            task="chat",
            mode="balanced",
            top=3,
            candidate_limit=20,
            max_download_gb=12,
            endpoint=endpoint,
            cache_dir=str(Path(tmp) / "cache"),
            enrichment_cap=3,
        )
        repos = [item["repo_id"] for item in result["recommendations"]]
        assert result["rift_phase"] == "M3_EXACT_ARTIFACT"
        assert repos[0] == "org/llama-7b-gptq"
        assert "org/big-bf16-70b" not in repos
        assert "org/gated-gptq" not in repos
        assert result["best_for_hardware"]["best_overall"]["repo_id"] == "org/llama-7b-gptq"
        assert result["best_for_hardware"]["absolute_best"]["repo_id"] == "org/llama-7b-gptq"
        assert result["answer"]["absolute_best_repo_id"] == "org/llama-7b-gptq"
        assert "Best model for this laptop" in result["answer"]["headline"]
        assert result["answer"]["why"]
        assert result["best_for_hardware"]["best_performance"]["repo_id"] in repos
        assert result["best_for_hardware"]["best_accuracy_proxy"]["repo_id"] in repos
        assert "accuracy" in result["best_for_hardware"]["accuracy_note"].lower()
        assert result["candidate_counts"]["enriched"] <= 3
        assert result["discovery"]["selection_automatic"] is True
        assert result["discovery"]["repository_input_required"] is False
        assert result["discovery"]["literal_full_hub_crawl"] is False
        assert result["discovery"]["query_arm_count"] > 1
        assert FakeRecommendHubHandler.info_calls <= 3
        top = result["recommendations"][0]
        assert top["format"] == "gptq"
        assert top["support_level"] == "INSTALLABLE_BACKEND"
        assert top["backend"] == "vllm"
        assert top["backend_candidates"]
        assert top["scores"]["hardware_fit"] > 0.0
        assert top["confidence"] > 0.0
        assert "quality_evidence" in top
        assert "claim_boundary" in top["evidence_provenance"]
        assert set(
            ("best_published_quality", "best_estimated_fit", "best_verified_local", "fastest_verified_local", "best_deployment")
        ).issubset(result["categories"])
        assert top["pull_command"].startswith("rift model pull org/llama-7b-gptq")


def test_recommendation_task_and_format_preferences():
    with FakeRecommendHubServer() as endpoint, tempfile.TemporaryDirectory() as tmp:
        engine = rift.RiftEngine()
        coding = engine.recommend_models(
            task="coding",
            mode="balanced",
            top=2,
            candidate_limit=20,
            max_download_gb=12,
            endpoint=endpoint,
            cache_dir=str(Path(tmp) / "coding-cache"),
            enrichment_cap=3,
        )
        assert coding["recommendations"][0]["repo_id"] == "org/coder-7b-gguf"
        coding_best = coding["recommendations"][0]
        assert coding_best["selected_file"] == "model-q4_k_m.gguf"
        assert coding_best["selected_files"] == ["model-q4_k_m.gguf"]
        assert coding_best["quantization"] == "Q4_K_M"
        assert coding_best["download_size_source"] == "exact_artifact_files"
        assert coding_best["estimated_download_bytes"] == 4 * GB
        assert coding_best["disk_feasibility"]["status"] == "fits"
        assert '--include "model-q4_k_m.gguf"' in coding_best["pull_command"]
        assert FakeRecommendHubHandler.tree_calls >= 1

        gguf_only = engine.recommend_models(
            task="chat",
            mode="balanced",
            formats="gguf",
            top=3,
            candidate_limit=20,
            max_download_gb=12,
            endpoint=endpoint,
            cache_dir=str(Path(tmp) / "gguf-cache"),
            enrichment_cap=3,
        )
        assert gguf_only["recommendations"]
        assert all(item["format"] == "gguf" for item in gguf_only["recommendations"])
        assert gguf_only["recommendations"][0]["support_level"] in (
            "AVAILABLE_NOW",
            "INSTALLABLE_BACKEND",
        )
        assert gguf_only["recommendations"][0]["backend"] == "llama.cpp"


def test_pull_best_and_cli_write_report():
    with FakeRecommendHubServer() as endpoint, tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        engine = rift.RiftEngine()
        weight = next(
            item
            for item in MODEL_DETAILS["org/llama-7b-gptq"]["siblings"]
            if item["rfilename"] == "model.safetensors"
        )
        advertised_size = weight["size"]
        weight["size"] = len(FILES["org/llama-7b-gptq"]["model.safetensors"])
        try:
            result = engine.recommend_models(
                task="chat",
                mode="balanced",
                top=1,
                candidate_limit=20,
                max_download_gb=12,
                pull_best=True,
                output_dir=str(root / "pulled"),
                endpoint=endpoint,
                cache_dir=str(root / "cache"),
                enrichment_cap=3,
            )
        finally:
            weight["size"] = advertised_size
        assert result["pull_best"]["repo_id"] == "org/llama-7b-gptq"
        assert (root / "pulled" / "config.json").is_file()
        assert (root / "pulled" / "model.safetensors").read_bytes() == FILES["org/llama-7b-gptq"]["model.safetensors"]
        assert FakeRecommendHubHandler.download_calls >= 1

        report_path = root / "recommendations.json"
        old_cwd = Path.cwd()
        os.chdir(root)
        try:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main(
                    [
                        "--json",
                        "model",
                        "recommend",
                        "--task",
                        "chat",
                        "--top",
                        "1",
                        "--candidate-limit",
                        "20",
                        "--max-download-gb",
                        "12",
                        "--endpoint",
                        endpoint,
                        "--write-report",
                        str(report_path),
                    ]
                )
        finally:
            os.chdir(old_cwd)
        assert code == 0
        payload = json.loads(stdout.getvalue())
        assert payload["recommendations"][0]["repo_id"] == "org/llama-7b-gptq"
        assert payload["answer"]["absolute_best_repo_id"] == "org/llama-7b-gptq"
        assert payload["report_path"] == str(report_path)
        assert json.loads(report_path.read_text(encoding="utf-8"))["rift_phase"] == "M3_EXACT_ARTIFACT"


def test_top_level_pull_discovers_repo_without_repo_argument():
    with FakeRecommendHubServer() as endpoint, tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = cli.main(
                [
                    "--json",
                        "model",
                        "pull",
                    "--task",
                    "chat",
                    "--dry-run",
                    "--top",
                    "1",
                    "--candidate-limit",
                    "20",
                    "--max-download-gb",
                    "12",
                    "--download-root",
                    str(root),
                    "--endpoint",
                    endpoint,
                ]
            )
        assert code == 0
        payload = json.loads(stdout.getvalue())
        assert payload["automatic_pull"]["repository_input_required"] is False
        assert payload["automatic_pull"]["dry_run"] is True
        assert payload["automatic_pull"]["selected_repo_id"] == "org/llama-7b-gptq"
        assert payload["automatic_pull"]["downloaded"] is False
        assert "pull_best" not in payload
        assert FakeRecommendHubHandler.download_calls == 0


def test_sharded_gguf_selection_and_disk_exclusion():
    provider = rift.LlamaCppProvider()
    selected = provider.select_gguf(
        [
            {"path": "model-Q4_K_M-00002-of-00002.gguf", "size": 2 * GB},
            {"path": "model-Q5_K_M.gguf", "size": 5 * GB},
            {"path": "model-Q4_K_M-00001-of-00002.gguf", "size": 2 * GB},
        ],
        hardware=FakeNativeEngine().hardware_profile(),
        disk_budget_bytes=6 * GB,
    )
    assert selected["path"].endswith("00001-of-00002.gguf")
    assert selected["selected_files"] == [
        "model-Q4_K_M-00001-of-00002.gguf",
        "model-Q4_K_M-00002-of-00002.gguf",
    ]
    assert selected["size"] == 4 * GB
    assert selected["complete"] is True

    original_disk_usage = hf_hub.shutil.disk_usage
    try:
        hf_hub.shutil.disk_usage = lambda _path: type(
            "Usage", (), {"total": 100 * GB, "used": 97 * GB, "free": 3 * GB}
        )()
        with FakeRecommendHubServer() as endpoint, tempfile.TemporaryDirectory() as tmp:
            engine = rift.RiftEngine()
            result = engine.recommend_models(
                task="chat",
                formats="gguf",
                top=3,
                candidate_limit=20,
                max_download_gb=12,
                endpoint=endpoint,
                cache_dir=str(Path(tmp) / "disk-cache"),
                enrichment_cap=3,
                disk_reserve_gb=2,
            )
            assert result["disk_profile"]["usable_bytes"] == 1 * GB
            assert result["recommendations"] == []
            assert result["answer"]["absolute_best_repo_id"] is None
    finally:
        hf_hub.shutil.disk_usage = original_disk_usage


def main():
    test_hub_search_cache_and_refresh()
    test_verify_cli_defaults_to_one_and_exposes_budget_controls()
    test_simulated_hardware_profile_accepts_compact_input()
    test_simulated_recommendation_uses_profile_and_marks_result()
    test_recommendation_exposes_benchmark_sites_and_diversified_search()
    test_calibration_matrix_contains_real_and_fifty_simulated_profiles()
    test_simulation_rejects_side_effectful_cli_modes()
    test_unsupported_simulated_platform_has_no_best_deployment()
    test_enriched_gated_candidate_is_removed_after_metadata_refresh()
    test_low_host_memory_rejects_artifact_without_runtime_headroom()
    test_recommendation_scoring_filters_and_enrichment_cap()
    test_recommendation_task_and_format_preferences()
    test_pull_best_and_cli_write_report()
    test_top_level_pull_discovers_repo_without_repo_argument()
    test_sharded_gguf_selection_and_disk_exclusion()
    print("rift recommend tests passed")


if __name__ == "__main__":
    main()
