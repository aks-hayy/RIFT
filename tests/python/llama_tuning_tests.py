"""llama.cpp provider contract tests for profile-aware launch plans."""

from __future__ import annotations

from pathlib import Path
import sys
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from rift.providers.llama_cpp import LlamaCppProvider


def test_profile_launch_plan_emits_explicit_runtime_controls() -> None:
    provider = LlamaCppProvider()
    plan = provider.plan_launch(
        model_path="model.gguf",
        host="127.0.0.1",
        port=18080,
        context_length=4096,
        concurrency=2,
        hardware={"total_vram_bytes": 8 * 1024**3},
        tuning={
            "gpu_layers": 40,
            "batch": 1024,
            "ubatch": 256,
            "threads": 8,
            "threads_batch": 12,
            "parallel": 2,
            "flash_attn": "on",
            "poll": 25,
            "poll_batch": 1,
            "cache_type_k": "f16",
            "cache_type_v": "f16",
        },
    )

    args = plan["command"]
    assert args[args.index("--threads-batch") + 1] == "12"
    assert args[args.index("--parallel") + 1] == "2"
    assert args[args.index("--flash-attn") + 1] == "on"
    assert args[args.index("--poll") + 1] == "25"
    assert args[args.index("--poll-batch") + 1] == "1"
    assert args[args.index("--cache-type-k") + 1] == "f16"
    assert args[args.index("--cache-type-v") + 1] == "f16"


def test_provider_profile_candidate_generation_preserves_cache_and_context() -> None:
    provider = LlamaCppProvider()
    baseline = provider.plan_launch(
        model_path="model.gguf",
        host="127.0.0.1",
        port=18080,
        context_length=4096,
        concurrency=1,
        hardware={"total_vram_bytes": 8 * 1024**3},
        tuning={"cache_type_k": "f16", "cache_type_v": "f16"},
    )

    candidates = provider.tuning_space(
        launch_plan=baseline,
        hardware={"total_vram_bytes": 8 * 1024**3},
        contract={
            "service": "chat",
            "profile": "speed",
            "model_path": "model.gguf",
            "model_sha256": "hash",
            "weight_quantization": "Q4_K_M",
            "cache_type_k": "f16",
            "cache_type_v": "f16",
            "context_length": 4096,
            "concurrency": 1,
        },
    )

    assert candidates
    assert len(candidates) <= 24
    assert all(item["cache_type_k"] == "f16" for item in candidates)
    assert all(item["cache_type_v"] == "f16" for item in candidates)
    assert all(item["context_length"] == 4096 for item in candidates)


def test_missing_precision_is_not_serialized_as_string_none() -> None:
    provider = LlamaCppProvider()
    baseline = provider.plan_launch(
        model_path="model.gguf",
        host="127.0.0.1",
        port=18080,
        context_length=4096,
        concurrency=1,
        hardware={"total_vram_bytes": 8 * 1024**3},
    )
    candidates = provider.tuning_space(
        launch_plan=baseline,
        hardware={"total_vram_bytes": 8 * 1024**3},
    )
    assert all(item.get("cache_type_k") != "None" for item in candidates)
    assert all(item.get("cache_type_v") != "None" for item in candidates)


def test_provider_searches_kv_when_precision_is_unconfigured() -> None:
    provider = LlamaCppProvider()
    baseline = provider.plan_launch(
        model_path="model.gguf", host="127.0.0.1", port=18080,
        context_length=4096, concurrency=1,
        hardware={"total_vram_bytes": 8 * 1024**3},
    )
    capabilities = {
        "flags": {"batch-size", "ubatch-size", "cache-type-k", "cache-type-v"},
        "cache_type_k": ["f16", "q8_0", "q4_0"],
        "cache_type_v": ["f16", "q8_0", "q4_0"],
        "probed": True,
    }
    with patch.object(provider, "probe_tuning_capabilities", return_value=capabilities):
        baseline["capabilities"] = capabilities
        candidates = provider.tuning_space(
            launch_plan=baseline,
            hardware={"total_vram_bytes": 8 * 1024**3},
            contract={
                "service": "chat", "profile": "speed", "model_path": "model.gguf",
                "context_length": 4096, "concurrency": 1,
                "kv_precision_search": True,
            },
        )
    assert any(item.get("cache_type_k") != "f16" or item.get("cache_type_v") != "f16" for item in candidates)
    assert all(item["context_length"] == 4096 for item in candidates)
    assert all(item["concurrency"] == 1 for item in candidates)


def test_launch_plan_serializes_speculative_controls_when_supported() -> None:
    provider = LlamaCppProvider()
    capabilities = {
        "flags": {
            "spec-type", "spec-draft-model", "spec-draft-n-max", "spec-draft-n-min",
            "spec-draft-p-min", "spec-draft-p-split", "spec-draft-ngl", "spec-draft-device",
        },
        "probed": True,
    }
    with patch.object(provider, "probe_tuning_capabilities", return_value=capabilities):
        plan = provider.plan_launch(
            model_path="model.gguf", host="127.0.0.1", port=18080,
            context_length=8192, concurrency=1,
            hardware={"total_vram_bytes": 8 * 1024**3},
            tuning={
                "spec_type": "ngram-mod", "spec_draft_model": "C:/models/draft.gguf",
                "spec_draft_n_max": 8, "spec_draft_n_min": 2,
                "spec_draft_p_min": 0.75, "spec_draft_p_split": 0.1,
                "spec_draft_ngl": 0, "spec_draft_device": "CPU",
            },
        )
    args = plan["command"]
    for flag, value in (
        ("--spec-type", "ngram-mod"), ("--spec-draft-model", "C:/models/draft.gguf"),
        ("--spec-draft-n-max", "8"), ("--spec-draft-n-min", "2"),
        ("--spec-draft-p-min", "0.75"), ("--spec-draft-p-split", "0.1"),
        ("--spec-draft-ngl", "0"), ("--spec-draft-device", "CPU"),
    ):
        assert args[args.index(flag) + 1] == value
    assert plan["tuning"]["spec_draft_model"] == "C:/models/draft.gguf"


def test_launch_plan_honors_explicit_ngram_speculation_off() -> None:
    provider = LlamaCppProvider()
    capabilities = {"flags": {"spec-type", "spec-ngram-mod-n-min"}, "probed": True}
    with patch.object(provider, "probe_tuning_capabilities", return_value=capabilities):
        plan = provider.plan_launch(
            model_path="model.gguf", host="127.0.0.1", port=18080,
            context_length=8192, concurrency=1,
            hardware={"total_vram_bytes": 8 * 1024**3},
            tuning={"ngram_speculation": False, "spec_type": "ngram-mod",
                    "spec_ngram_mod_n_min": 1},
        )
    assert "--spec-type" not in plan["command"]
    assert "--spec-ngram-mod-n-min" not in plan["command"]
    assert plan["tuning"]["ngram_speculation"] is False


def test_default_launch_plan_omits_unset_optional_flags() -> None:
    provider = LlamaCppProvider()
    plan = provider.plan_launch(
        model_path="model.gguf",
        host="127.0.0.1",
        port=18080,
        context_length=4096,
        concurrency=1,
        hardware={"total_vram_bytes": 8 * 1024**3},
    )
    assert "--poll" not in plan["command"]
    assert "--poll-batch" not in plan["command"]
    assert "--cache-type-k" not in plan["command"]
    assert "--cache-type-v" not in plan["command"]


def test_launch_plan_serializes_kv_unified_load_mode_and_op_offload() -> None:
    provider = LlamaCppProvider()
    plan = provider.plan_launch(
        model_path="model.gguf", host="127.0.0.1", port=18080,
        context_length=4096, concurrency=1,
        hardware={"total_vram_bytes": 8 * 1024**3},
        tuning={"kv_unified": True, "kv_offload": True, "no_host": True,
                 "repack": True, "load_mode": "mmap", "op_offload": True, "prio": 1},
    )
    assert "--kv-unified" in plan["command"]
    assert "--kv-offload" in plan["command"]
    assert "--no-host" in plan["command"]
    assert "--load-mode" in plan["command"] and "mmap" in plan["command"]
    assert "--op-offload" in plan["command"]


def test_capability_probe_filters_flags_not_present_in_binary() -> None:
    provider = LlamaCppProvider()
    capabilities = provider._parse_tuning_capabilities("--batch-size N\n--cache-type-k TYPE")
    assert capabilities["flags"] == {"batch-size", "cache-type-k"}
    assert "cache_type_v" not in capabilities["cache_types"]


def test_successful_probe_gates_standard_controls() -> None:
    provider = LlamaCppProvider()
    capabilities = {"flags": {"batch-size"}, "cache_types": {}, "probed": True}
    with patch.object(provider, "probe_tuning_capabilities", return_value=capabilities):
        plan = provider.plan_launch(
            model_path="model.gguf", host="127.0.0.1", port=18080,
            context_length=4096, concurrency=1,
            hardware={"total_vram_bytes": 8 * 1024**3},
            tuning={"threads_batch": 12, "parallel": 2},
        )
    assert "--threads-batch" not in plan["command"]
    assert "--parallel" not in plan["command"]


def test_capability_parser_reads_cache_types_from_continuation_lines() -> None:
    provider = LlamaCppProvider()
    capabilities = provider._parse_tuning_capabilities(
        "--cache-type-k TYPE\n  allowed: f16, q8_0, q4_0\n"
        "--cache-type-v TYPE\n  allowed: f16, q4_1"
    )
    assert capabilities["cache_types"]["cache_type_k"] == ["f16", "q8_0", "q4_0"]
    assert capabilities["cache_types"]["cache_type_v"] == ["f16", "q4_1"]


def test_capability_probe_returns_nested_copies() -> None:
    provider = LlamaCppProvider()
    with patch("rift.providers.llama_cpp.subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stdout = "--cache-type-k f16 q8_0"
        run.return_value.stderr = ""
        first = provider.probe_tuning_capabilities("llama-copy-test")
        first["flags"].clear()
        first["cache_types"]["cache_type_k"].clear()
        second = provider.probe_tuning_capabilities("llama-copy-test")
    assert second["flags"]
    assert second["cache_types"]["cache_type_k"]


def test_tuning_space_resolves_probe_executable_from_search_root(monkeypatch) -> None:
    provider = LlamaCppProvider()
    observed = []
    monkeypatch.setattr(
        provider,
        "detect",
        lambda *, search_root: {"executable": str(Path(search_root) / "llama-server.exe")},
    )
    monkeypatch.setattr(
        provider,
        "probe_tuning_capabilities",
        lambda executable: observed.append(executable) or {
            "flags": {"batch-size", "cache-type-k", "cache-type-v"},
            "cache_type_k": ["f16", "q8_0"],
            "cache_type_v": ["f16", "q8_0"],
            "probed": True,
        },
    )
    provider.tuning_space(
        launch_plan={
            "model_path": "model.gguf",
            "tuning": {"batch": 128, "ubatch": 128, "search_root": "C:/rift/backends/llama.cpp"},
        },
        hardware={"physical_cores": 4, "logical_processors": 8, "total_vram_bytes": 8 * 1024**3},
    )
    assert len(observed) == 1
    assert Path(observed[0]).as_posix().lower().endswith(
        "/rift/backends/llama.cpp/llama-server.exe"
    )


def test_candidate_budget_keeps_diverse_knob_families() -> None:
    provider = LlamaCppProvider()
    plan = provider.plan_launch(
        model_path="model.gguf",
        host="127.0.0.1",
        port=18080,
        context_length=4096,
        concurrency=1,
        hardware={"total_vram_bytes": 8 * 1024**3},
    )
    candidates = provider.tuning_space(
        launch_plan=plan,
        hardware={"total_vram_bytes": 8 * 1024**3, "physical_cores": 4, "logical_processors": 8},
    )
    assert any(item.get("threads") != candidates[0].get("threads") for item in candidates)
    assert any(item.get("flash_attn") in {"on", "off"} for item in candidates)
    assert any(item.get("poll") in {0, 25, 50} for item in candidates)


def main() -> None:
    test_profile_launch_plan_emits_explicit_runtime_controls()
    test_provider_profile_candidate_generation_preserves_cache_and_context()
    test_missing_precision_is_not_serialized_as_string_none()
    test_default_launch_plan_omits_unset_optional_flags()
    test_launch_plan_serializes_kv_unified_load_mode_and_op_offload()
    test_capability_probe_filters_flags_not_present_in_binary()
    test_successful_probe_gates_standard_controls()
    test_capability_parser_reads_cache_types_from_continuation_lines()
    test_capability_probe_returns_nested_copies()
    test_candidate_budget_keeps_diverse_knob_families()
    print("llama_tuning_tests: PASS")


if __name__ == "__main__":
    main()
