import importlib
import json
import sys
import tempfile
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = ROOT / "python"
sys.path.insert(0, str(PYTHON_ROOT))


class FakeNativeEngine:
    def __init__(self, cuda_device_id=0):
        self.cuda_device_id = cuda_device_id

    def build_info(self):
        return {
            "version": "test",
            "phase": "Phase 28 + R10 primitives",
            "capability": "cached decode-attention primitives",
        }

    def hardware_profile(self):
        return {
            "cuda_available": True,
            "device_name": "Synthetic RTX",
            "total_vram_bytes": 8 * 1024**3,
            "free_vram_bytes": 7 * 1024**3,
            "total_host_ram_bytes": 16 * 1024**3,
            "free_host_ram_bytes": 8 * 1024**3,
            "compute_capability_major": 8,
            "compute_capability_minor": 9,
        }

    def inspect_model(self, model_path, **kwargs):
        return {
            "model_path": model_path,
            "config": {
                "model_type": "llama",
                "family": "LLAMA",
                "quantization": "GPTQ_INT4",
                "num_hidden_layers": 2,
                "hidden_size": 16,
                "vocab_size": 32,
            },
            "topology": {
                "total_model_bytes": 4096,
                "w_max_bytes": 1024,
            },
            "profile": {"supported": True},
            "execution_policy": {"supported": True},
            "generation_readiness": {
                "ready": True,
                "issues": [],
                "output_head_mode": "DENSE_FP16_LM_HEAD_STREAMING",
            },
            "generation_ready": True,
        }

    def load_model(self, model_path, **kwargs):
        return self.inspect_model(model_path, **kwargs)

    def generate(self, prompt, **kwargs):
        return {
            "status": "ok",
            "text": "!",
            "full_text": prompt + "!",
            "tokens": [1],
            "generated_tokens": 1,
            "layers_executed": 2,
            "total_streamed_bytes": 4096,
            "staging_capacity_bytes": 1024,
            "context_limit_tokens": 128,
        }

    def estimate_h2d_transfer_ns(self, byte_count):
        return int(byte_count)

    def benchmark_model(self, model_path):
        return {"model_path": model_path, "status": "dry-run"}


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

rift = importlib.reload(importlib.import_module("rift.rift"))


def test_rift_inspect_plan_run_report():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        model_dir = root / "model"
        model_dir.mkdir()
        (model_dir / "model.safetensors").write_bytes(bytes(range(64)))
        (model_dir / "config.json").write_text(
            '{"model_type":"llama","quantization_config":{"quant_method":"gptq"}}',
            encoding="utf-8",
        )
        (model_dir / "tokenizer.json").write_text("{}", encoding="utf-8")

        engine = rift.RiftEngine()
        inspection = engine.inspect_model(str(model_dir))
        assert inspection["rift_product"] == "RIFT"
        assert inspection["rift_compatibility_level"] == "NATIVE_RUN_READY"
        assert inspection["rift_recommended_initial_mode"] == "SURVIVAL"
        assert inspection["rift_hardware_fit_mode"] == "FAST"
        assert inspection["rift_mode_analysis"]["runtime_gap"] is True

        plan_path = root / "model.riftplan"
        plan = engine.plan_model(
            str(model_dir),
            output_path=str(plan_path),
            benchmark_read_bytes=32,
            context_length=2048,
            concurrency=2,
        )
        assert plan["schema_version"] == 2
        assert plan["recommended_mode"] == "SURVIVAL"
        assert plan["hardware_fit_mode"] == "FAST"
        assert plan["decode_readiness"]["cached_decode_attention_primitive"] is True
        assert plan["balanced_cache_plan"]["runtime_available"] is False
        assert plan["selected_backend"] == "vllm"
        assert plan["execution_backend"] == "rift_native_survival"
        assert plan["backend_decision"]["selected_backend"] == "vllm"
        assert plan["serving_plan"]["backend"] == "vllm"
        assert plan["kv_plan"]["context_length"] == 2048
        assert plan["kv_plan"]["concurrency"] == 2
        assert plan["candidate_modes"]["FAST"]["hardware_suitable"] is True
        assert plan["candidate_modes"]["FAST"]["runtime_available"] is False
        assert plan_path.exists()
        loaded_plan = engine.load_plan(str(plan_path))
        assert loaded_plan["model_fingerprint"] == plan["model_fingerprint"]

        doctor = engine.doctor(str(model_dir), benchmark_read_bytes=32)
        assert doctor["overall_status"] == "WARN"
        assert doctor["plan_summary"]["recommended_mode"] == "SURVIVAL"
        assert doctor["plan_summary"]["hardware_fit_mode"] == "FAST"
        assert doctor["plan_summary"]["selected_backend"] == "vllm"
        assert doctor["compatibility_advice"]["support_level"] == "NATIVE_RUN_CANDIDATE"
        assert doctor["compatibility_advice"]["backend_decision"]["selected_backend"] == "vllm"
        assert any(check["name"] == "mode_gap" for check in doctor["checks"])

        compatibility = engine.compatibility_advice(str(model_dir))
        assert compatibility["family"] == "LLAMA"
        assert compatibility["native_status"] == "llama_gptq_safetensors_supported"
        assert compatibility["backend_decision"]["selected_backend"] == "vllm"

        backend = engine.recommend_backend(
            model_path=str(model_dir),
            workload="agent",
            context_length=32768,
            concurrency=4,
            prefix_reuse="high",
        )
        assert backend["selected_backend"] == "lmcache_aware"
        assert backend["base_backend"] in {"vllm", "sglang"}

        gguf_dir = root / "gguf-model"
        gguf_dir.mkdir()
        (gguf_dir / "model.gguf").write_bytes(b"gguf")
        gguf_backend = engine.recommend_backend(model_path=str(gguf_dir))
        assert gguf_backend["selected_backend"] == "llama.cpp"
        assert "llama-server" in gguf_backend["launch"]["command"]

        report_path = root / "latest.riftreport.json"
        run = engine.run(
            prompt="Hello",
            plan_path=str(plan_path),
            max_tokens=1,
            report_path=str(report_path),
        )
        assert run["status"] == "ok"
        assert run["generated_tokens"] == 1
        assert run["usability_verdict"] in {
            "EXCELLENT",
            "GOOD",
            "USABLE",
            "SLOW",
            "NOT_RECOMMENDED",
        }
        assert report_path.exists()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["schema_version"] == 1
        assert report["metrics"]["generated_tokens"] == 1
        assert report["decode_path"] == "repeated_full_prefill"
        assert report["metrics"]["p50_token_seconds"] is not None
        reports = engine.list_reports()
        assert reports["reports"]


def main():
    test_rift_inspect_plan_run_report()
    print("rift rift tests passed")


if __name__ == "__main__":
    main()
