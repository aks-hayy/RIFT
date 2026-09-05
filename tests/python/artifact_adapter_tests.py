import importlib
import json
from pathlib import Path
import sys
import tempfile
import types


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

fake_core = types.ModuleType("rift._core")
fake_core.InferenceEngine = object
fake_core.__version__ = "test"
fake_core.build_info = lambda: {"version": "test"}
fake_core.cuda_device_count = lambda: 0
fake_core.inspect_model = lambda *args, **kwargs: {}
fake_core.parse_model_topology = lambda *args, **kwargs: {}
sys.modules.setdefault("rift._core", fake_core)

artifacts = importlib.import_module("rift.adapters.artifacts")
conformance = importlib.import_module("rift.adapters.conformance")
registry = importlib.import_module("rift.adapters.registry")
contracts = importlib.import_module("rift.adapters.contracts")
converters = importlib.import_module("rift.adapters.converters")


class ThirdPartyArtifact(artifacts.BaseArtifactAdapter):
    adapter_id = "artifact-third-party"
    artifact_format = "future-format"

    def detect(self, source):
        return any(item.get("path", "").endswith(".future") for item in source.get("files") or [])

    def inspect(self, source):
        model_files = [
            contracts.ArtifactFile(item["path"], item.get("size"), "weights")
            for item in source.get("files") or []
            if item.get("path", "").endswith(".future")
        ]
        return [self._variant(source, artifact_id="future:one", model_files=model_files)] if model_files else []


class FakeEntryPoint:
    name = "artifact-third-party"

    @staticmethod
    def load():
        return ThirdPartyArtifact


class FakeEntryPoints(list):
    def select(self, *, group):
        return self if group == "rift.artifact_adapters" else []


class FakeConverter:
    adapter_id = "converter-test"
    manifest = contracts.AdapterManifest(
        adapter_id=adapter_id,
        display_name="Test converter",
        upstream_project="tests/converter",
        adapter_version="1.0.0",
        adapter_api_version=contracts.ADAPTER_API_VERSION,
        kind="converter",
        capability=contracts.BackendCapability(
            tasks=("artifact-conversion",), formats=("future-format",)
        ),
    )

    def can_convert(self, *, source, target_format):
        return contracts.CompatibilityResult(
            adapter_id=self.adapter_id,
            compatible=source.format == "safetensors" and target_format == "future-format",
            platform_supported=True,
            hardware_fit=True,
            installed=True,
            support_level="AVAILABLE_NOW",
            score=1.0,
        )

    def plan_conversion(self, *, source, target_format, output_path, options=None):
        return contracts.ConversionPlan(
            converter_id=self.adapter_id,
            source_artifact=source,
            target_format=target_format,
            output_path=output_path,
            command=("fake-converter", "--output", output_path),
            estimated_output_bytes=source.total_bytes,
        )

    def convert(self, plan):
        return {"converted": True, "output_path": plan.output_path}


def _write_common(root: Path, config: dict) -> None:
    (root / "config.json").write_text(json.dumps(config), encoding="utf-8")
    (root / "tokenizer.json").write_text("{}", encoding="utf-8")


def _resolve(root: Path):
    return artifacts.artifact_adapter_host(load_entry_points=False).resolve(
        artifacts.source_from_local(root)
    )


def test_all_promised_safetensors_formats_are_distinguished():
    cases = (
        ({"model_type": "llama", "quantization_config": {"quant_method": "awq"}}, "awq"),
        ({"model_type": "llama", "quantization_config": {"quant_method": "gptq"}}, "gptq"),
        ({"model_type": "llama", "torch_dtype": "float8_e4m3fn"}, "fp8"),
        ({"model_type": "llama", "quantization_config": {"quant_method": "exl2"}}, "exl2"),
        ({"model_type": "llama", "torch_dtype": "bfloat16"}, "safetensors"),
    )
    for config, expected in cases:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_common(root, config)
            (root / "model.safetensors").write_bytes(b"weights")
            variants = _resolve(root)
            assert len(variants) == 1, (expected, [item.format for item in variants])
            assert variants[0].format == expected
            assert variants[0].validation["serving_ready"]


def test_mlx_identity_is_resolved_without_confusing_dense_safetensors():
    source = {
        "source": "huggingface",
        "repo_id": "mlx-community/Qwen-test-4bit",
        "revision": "abc123",
        "config": {"model_type": "qwen2", "quantization": {"bits": 4, "group_size": 64}},
        "files": [
            {"path": "model.safetensors", "size": 100, "sha256": "a" * 64},
            {"path": "config.json", "size": 10, "sha256": "b" * 64},
            {"path": "tokenizer.json", "size": 10, "sha256": "c" * 64},
        ],
    }
    variants = artifacts.artifact_adapter_host(load_entry_points=False).resolve(source)
    assert [item.format for item in variants] == ["mlx"]
    assert variants[0].validation["integrity_status"] == "HASHED_COMPLETE"
    assert variants[0].validation["exact_revision"]


def test_safetensors_filename_shards_are_checked_without_an_index():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_common(root, {"model_type": "llama"})
        (root / "model-00001-of-00003.safetensors").write_bytes(b"a")
        (root / "model-00003-of-00003.safetensors").write_bytes(b"c")
        variant = _resolve(root)[0]
        assert not variant.validation["valid"]
        assert not variant.validation["serving_ready"]
        assert "SafeTensors shard 00002-of-00003" in variant.validation["missing_dependencies"]


def test_complete_filename_shards_are_usable_with_an_explicit_warning():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_common(root, {"model_type": "llama"})
        (root / "model-00001-of-00002.safetensors").write_bytes(b"a")
        (root / "model-00002-of-00002.safetensors").write_bytes(b"b")
        variant = _resolve(root)[0]
        assert variant.validation["serving_ready"]
        assert variant.metadata["shard_naming_complete"]
        assert any("filename-complete" in item for item in variant.validation["warnings"])


def test_gguf_split_and_multimodal_dependencies_fail_closed():
    source = {
        "source": "huggingface",
        "repo_id": "org/vision-gguf",
        "tags": ["image-text-to-text"],
        "files": [
            {"path": "model-q4_k_m-00001-of-00002.gguf", "size": 20},
        ],
    }
    variant = artifacts.artifact_adapter_host(load_entry_points=False).resolve(source)[0]
    assert variant.quantization == "Q4_K_M"
    assert not variant.validation["serving_ready"]
    assert "multimodal projection GGUF" in variant.validation["missing_dependencies"]
    assert any("shard-00002-of-00002" in item for item in variant.validation["missing_dependencies"])


def test_multimodal_safetensors_requires_processor_metadata():
    source = {
        "source": "huggingface",
        "repo_id": "org/vlm",
        "revision": "sha",
        "tags": ["image-text-to-text"],
        "config": {"model_type": "mllama"},
        "files": [
            {"path": "model.safetensors", "size": 100},
            {"path": "config.json", "size": 10},
            {"path": "tokenizer.json", "size": 10},
        ],
    }
    variant = artifacts.artifact_adapter_host(load_entry_points=False).resolve(source)[0]
    assert not variant.validation["serving_ready"]
    assert "processor_config.json/preprocessor_config.json" in variant.validation["missing_dependencies"]


def test_resource_estimate_includes_config_derived_kv_and_dependencies():
    source = {
        "source": "huggingface",
        "repo_id": "org/model",
        "revision": "sha",
        "config": {
            "model_type": "llama",
            "hidden_size": 4096,
            "num_hidden_layers": 32,
            "num_attention_heads": 32,
            "num_key_value_heads": 8,
        },
        "files": [
            {"path": "model.safetensors", "size": 4 * 1024**3},
            {"path": "config.json", "size": 1024},
            {"path": "tokenizer.json", "size": 2048},
        ],
    }
    host = artifacts.artifact_adapter_host(load_entry_points=False)
    variant = host.resolve(source)[0]
    adapter = host.get("artifact-safetensors")
    estimate = adapter.estimate_resources(
        variant,
        {
            "total_vram_bytes": 8 * 1024**3,
            "total_host_ram_bytes": 16 * 1024**3,
            "context_length": 4096,
            "concurrency": 1,
        },
    )
    expected_kv = 2 * 32 * 4096 * 8 * 128 * 2
    assert estimate["estimated_kv_cache_bytes"] == expected_kv
    assert estimate["minimum_disk_bytes"] == 4 * 1024**3 + 3072
    assert estimate["recommended_vram_bytes"] > estimate["weight_bytes"]


def test_every_builtin_artifact_adapter_passes_shared_conformance():
    sources = {
        "artifact-gguf": {
            "source": "huggingface",
            "repo_id": "org/model-gguf",
            "files": [{"path": "model-q4_k_m.gguf", "size": 100}],
        },
        "artifact-awq": {
            "source": "huggingface",
            "repo_id": "org/model-awq",
            "config": {"model_type": "llama", "quantization_config": {"quant_method": "awq"}},
            "files": [{"path": "model.safetensors", "size": 100}, {"path": "config.json", "size": 10}, {"path": "tokenizer.json", "size": 10}],
        },
        "artifact-gptq": {
            "source": "huggingface",
            "repo_id": "org/model-gptq",
            "config": {"model_type": "llama", "quantization_config": {"quant_method": "gptq"}},
            "files": [{"path": "model.safetensors", "size": 100}, {"path": "config.json", "size": 10}, {"path": "tokenizer.json", "size": 10}],
        },
        "artifact-fp8": {
            "source": "huggingface",
            "repo_id": "org/model-fp8",
            "config": {"model_type": "llama", "torch_dtype": "float8_e4m3fn"},
            "files": [{"path": "model.safetensors", "size": 100}, {"path": "config.json", "size": 10}, {"path": "tokenizer.json", "size": 10}],
        },
        "artifact-exl2": {
            "source": "huggingface",
            "repo_id": "org/model-exl2",
            "config": {"model_type": "llama", "quantization_config": {"quant_method": "exl2"}},
            "files": [{"path": "model.safetensors", "size": 100}, {"path": "config.json", "size": 10}, {"path": "tokenizer.json", "size": 10}],
        },
        "artifact-mlx": {
            "source": "huggingface",
            "repo_id": "mlx-community/model-4bit",
            "config": {"model_type": "llama", "quantization": {"bits": 4}},
            "files": [{"path": "model.safetensors", "size": 100}, {"path": "config.json", "size": 10}, {"path": "tokenizer.json", "size": 10}],
        },
        "artifact-safetensors": {
            "source": "huggingface",
            "repo_id": "org/model",
            "config": {"model_type": "llama", "torch_dtype": "bfloat16"},
            "files": [{"path": "model.safetensors", "size": 100}, {"path": "config.json", "size": 10}, {"path": "tokenizer.json", "size": 10}],
        },
    }
    suite = conformance.ArtifactConformanceSuite()
    for adapter in artifacts.builtin_artifact_adapters():
        report = suite.run(adapter, source=sources[adapter.adapter_id])
        assert report["passed"], report


def test_third_party_artifact_entry_point_requires_no_core_registry_edit():
    original = registry.importlib.metadata.entry_points
    registry.importlib.metadata.entry_points = lambda: FakeEntryPoints([FakeEntryPoint()])
    try:
        host = artifacts.artifact_adapter_host(load_entry_points=True)
    finally:
        registry.importlib.metadata.entry_points = original
    assert "artifact-third-party" in host.enabled()
    variants = host.resolve(
        {"source": "catalog", "files": [{"path": "weights.future", "size": 12}]}
    )
    assert any(item.format == "future-format" for item in variants)


def test_conversion_is_separate_and_permission_gated():
    source = contracts.ArtifactVariant(
        artifact_id="source",
        format="safetensors",
        quantization="BF16",
        files=(contracts.ArtifactFile("model.safetensors", 100, "weights"),),
        total_bytes=100,
        size_known=True,
    )
    host = converters.converter_adapter_host(
        builtins=(FakeConverter(),), load_entry_points=False
    )
    plans = host.plans(
        source=source,
        target_format="future-format",
        output_path="converted.future",
    )
    assert len(plans) == 1 and plans[0].requires_permission
    try:
        host.execute(plans[0])
    except converters.ConversionPermissionError:
        pass
    else:
        raise AssertionError("conversion ran without explicit permission")
    executed = host.execute(plans[0], allow_conversion=True)
    assert executed["result"]["converted"]


def main():
    test_all_promised_safetensors_formats_are_distinguished()
    test_mlx_identity_is_resolved_without_confusing_dense_safetensors()
    test_safetensors_filename_shards_are_checked_without_an_index()
    test_complete_filename_shards_are_usable_with_an_explicit_warning()
    test_gguf_split_and_multimodal_dependencies_fail_closed()
    test_multimodal_safetensors_requires_processor_metadata()
    test_resource_estimate_includes_config_derived_kv_and_dependencies()
    test_every_builtin_artifact_adapter_passes_shared_conformance()
    test_third_party_artifact_entry_point_requires_no_core_registry_edit()
    test_conversion_is_separate_and_permission_gated()
    print("RIFT artifact adapter tests passed")


if __name__ == "__main__":
    main()
