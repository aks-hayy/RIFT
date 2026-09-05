"""First-pass contract tests for the autonomous tuning engine."""

from __future__ import annotations

import tempfile
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


from rift.tuning_engine import (
    CostMeasurement,
    SpeedMeasurement,
    TuningContract,
    TuningStore,
    candidate_is_allowed,
    generate_llama_candidates,
    select_profile_winner,
)
import rift.tuning_engine as tuning_engine
from rift.cli.parser import build_parser


def test_contract_locks_artifact_and_cache_precision() -> None:
    contract = TuningContract.from_mapping(
        {
            "service": "chat",
            "profile": "speed",
            "model_path": "model.gguf",
            "model_sha256": "model-hash",
            "weight_quantization": "Q4_K_M",
            "cache_type_k": "f16",
            "cache_type_v": "f16",
            "context_length": 4096,
            "concurrency": 1,
        }
    )

    assert contract.model_path == "model.gguf"
    assert contract.locked["model_sha256"] == "model-hash"
    assert contract.locked["weight_quantization"] == "Q4_K_M"
    assert contract.locked["cache_type_k"] == "f16"
    assert contract.locked["cache_type_v"] == "f16"
    assert candidate_is_allowed(contract, {"batch": 512, "threads": 8})
    assert candidate_is_allowed(contract, {"cache_type_k": "q8_0"})
    assert not candidate_is_allowed(contract, {"model_path": "other.gguf"})


def test_llama_candidates_are_bounded_and_preserve_locked_values() -> None:
    contract = TuningContract.from_mapping(
        {
            "service": "chat",
            "profile": "speed",
            "model_path": "model.gguf",
            "model_sha256": "hash",
            "weight_quantization": "Q4_K_M",
            "cache_type_k": "f16",
            "cache_type_v": "f16",
            "context_length": 4096,
            "concurrency": 1,
        }
    )
    baseline = {
        "gpu_layers": 99,
        "batch": 512,
        "ubatch": 128,
        "threads": 8,
        "threads_batch": 8,
        "cache_type_k": "f16",
        "cache_type_v": "f16",
        "context_length": 4096,
    }

    candidates = generate_llama_candidates(
        baseline=baseline,
        contract=contract,
        physical_cores=8,
        logical_processors=16,
        total_vram_bytes=8 * 1024**3,
    )

    assert 1 < len(candidates) <= 24
    assert all(candidate_is_allowed(contract, item) for item in candidates)
    assert all(item["cache_type_k"] == "f16" for item in candidates)
    assert all(item["cache_type_v"] == "f16" for item in candidates)
    assert all(item["context_length"] == 4096 for item in candidates)
    assert all(item["ubatch"] <= item["batch"] for item in candidates)
    assert len({tuple(sorted(item.items())) for item in candidates}) == len(candidates)


def test_candidate_generation_varies_kv_precision_without_changing_weight_quantization() -> None:
    contract = TuningContract.from_mapping({"service":"chat", "profile":"speed", "model_path":"m.gguf", "model_sha256":"h", "weight_quantization":"Q4_K_M", "cache_type_k":"f16", "cache_type_v":"f16", "context_length":4096, "concurrency":1, "kv_precision_search":True})
    candidates = generate_llama_candidates(baseline={"batch":512,"ubatch":128,"threads":8,"threads_batch":8,"gpu_layers":999,"cache_type_k":"f16","cache_type_v":"f16"}, contract=contract, physical_cores=8, logical_processors=16, total_vram_bytes=8*1024**3, maximum=64, capabilities={"cache_type_k":["f16","q8_0","q4_0"],"cache_type_v":["f16","q8_0","q4_0"]})
    assert any(item["cache_type_k"] != "f16" or item["cache_type_v"] != "f16" for item in candidates)
    assert all(item.get("weight_quantization") == "Q4_K_M" for item in candidates)


def test_candidate_budget_prioritizes_representative_kv_pairs() -> None:
    contract = TuningContract.from_mapping({
        "service": "chat", "profile": "speed", "model_path": "m.gguf",
        "context_length": 4096, "concurrency": 1, "cache_type_k": "f16",
        "cache_type_v": "f16", "kv_precision_search": True,
    })
    candidates = generate_llama_candidates(
        baseline={"batch": 128, "ubatch": 128, "threads": 8, "threads_batch": 8,
                  "cache_type_k": "f16", "cache_type_v": "f16", "gpu_layers": 999},
        contract=contract, physical_cores=8, logical_processors=16,
        total_vram_bytes=8 * 1024**3, maximum=24,
        capabilities={"flags": ["cache-type-k", "cache-type-v"],
                      "cache_type_k": ["f16", "q8_0", "q4_0"],
                      "cache_type_v": ["f16", "q8_0", "q4_0"]},
    )
    assert {(
        item.get("cache_type_k"), item.get("cache_type_v")
    ) for item in candidates} >= {("q8_0", "q8_0"), ("q4_0", "q4_0")}


def test_candidate_generation_includes_runtime_memory_and_cuda_controls_when_supported() -> None:
    contract = TuningContract.from_mapping({"service":"chat", "profile":"speed", "model_path":"m.gguf", "context_length":4096, "concurrency":1, "kv_precision_search":True})
    candidates = generate_llama_candidates(baseline={"batch":512,"ubatch":128,"threads":8,"threads_batch":8,"gpu_layers":999}, contract=contract, physical_cores=8, logical_processors=16, total_vram_bytes=8*1024**3, maximum=96, capabilities={"flags":["kv-unified","kv-offload","no-host","repack","load-mode","op-offload"]})
    assert any("kv_unified" in item for item in candidates)
    assert any("kv_offload" in item for item in candidates)
    assert any("load_mode" in item for item in candidates)


def test_candidate_generation_includes_built_in_ngram_without_draft_artifact() -> None:
    contract = TuningContract.from_mapping({
        "service": "chat", "profile": "speed", "model_path": "m.gguf",
        "context_length": 8192, "concurrency": 1,
    })
    candidates = generate_llama_candidates(
        baseline={"batch": 512, "ubatch": 128, "gpu_layers": 999},
        contract=contract, physical_cores=8, logical_processors=16,
        total_vram_bytes=8 * 1024**3, maximum=24,
        capabilities={"flags": ["spec-type"]},
    )
    assert any(item.get("spec_type") == "ngram-mod" for item in candidates)
    assert all("spec_draft_model" not in item for item in candidates)


def test_candidate_generation_can_disable_all_ngram_variants() -> None:
    contract = TuningContract.from_mapping({
        "service": "chat", "profile": "speed", "model_path": "m.gguf",
        "context_length": 8192, "concurrency": 1, "ngram_speculation": False,
    })
    candidates = generate_llama_candidates(
        baseline={"batch": 512, "ubatch": 128, "gpu_layers": 999,
                  "spec_type": "ngram-mod", "spec_ngram_mod_n_min": 1},
        contract=contract, physical_cores=8, logical_processors=16,
        total_vram_bytes=8 * 1024**3, maximum=48,
        capabilities={"flags": ["spec-type", "spec-ngram-mod-n-min"]},
    )
    assert all(item.get("spec_type") != "ngram-mod" for item in candidates)
    assert all(not any(key.startswith("spec_ngram_mod_") for key in item) for item in candidates)
    assert all(item.get("ngram_speculation") is not True for item in candidates)
    assert not candidate_is_allowed(contract, {"ngram_speculation": True})


def test_candidate_generation_preserves_explicit_draft_and_bounds_schedule() -> None:
    draft = "C:/models/draft.gguf"
    contract = TuningContract.from_mapping({
        "service": "chat", "profile": "speed", "model_path": "m.gguf",
        "context_length": 8192, "concurrency": 1,
        "spec_draft_model": draft, "spec_draft_sha256": "draft-hash",
    })
    candidates = generate_llama_candidates(
        baseline={"batch": 512, "ubatch": 128, "gpu_layers": 999,
                  "spec_draft_model": draft, "spec_type": "draft-simple"},
        contract=contract, physical_cores=8, logical_processors=16,
        total_vram_bytes=8 * 1024**3, maximum=24,
        capabilities={"flags": ["spec-type", "spec-draft-model", "spec-draft-n-max"]},
    )
    draft_candidates = [item for item in candidates if "spec_draft_model" in item]
    assert draft_candidates
    assert all(item["spec_draft_model"] == draft for item in draft_candidates)
    assert {item.get("spec_draft_n_max") for item in draft_candidates if "spec_draft_n_max" in item} <= {3, 5, 8, 12}


def test_candidate_generation_skips_numa_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """NUMA auto/distribute can fail readiness on the Windows CUDA build."""
    monkeypatch.setattr(tuning_engine.platform, "system", lambda: "Windows")
    contract = TuningContract.from_mapping({
        "service": "chat", "profile": "speed", "model_path": "m.gguf",
        "context_length": 8192, "concurrency": 1,
    })
    candidates = generate_llama_candidates(
        baseline={"batch": 512, "ubatch": 128, "gpu_layers": 999},
        contract=contract, physical_cores=8, logical_processors=16,
        total_vram_bytes=8 * 1024**3, maximum=48,
        capabilities={"flags": ["numa"]},
    )
    assert all("numa" not in item for item in candidates)


def test_candidate_generation_locks_gpu_layers_and_preserves_default_kv_permission() -> None:
    contract = TuningContract.from_mapping({"service": "chat", "profile": "speed", "model_path": "m.gguf", "context_length": 4096, "concurrency": 1, "gpu_layers": 17})
    assert contract.kv_precision_search is True
    candidates = generate_llama_candidates(baseline={"gpu_layers": 17}, contract=contract, physical_cores=4, logical_processors=8, total_vram_bytes=8 * 1024**3, maximum=24)
    assert candidates
    assert all(item["gpu_layers"] == 17 for item in candidates)
    assert not candidate_is_allowed(contract, {"gpu_layers": 18})


def test_candidate_generation_does_not_vary_standard_controls_with_empty_capabilities() -> None:
    contract = TuningContract.from_mapping({"service": "chat", "profile": "speed", "model_path": "m.gguf", "context_length": 4096, "concurrency": 1})
    baseline = {"batch": 512, "ubatch": 128, "threads": 8, "threads_batch": 8, "flash_attn": "auto", "poll": 50, "poll_batch": 1, "parallel": 1}
    candidates = generate_llama_candidates(baseline=baseline, contract=contract, physical_cores=8, logical_processors=16, total_vram_bytes=8 * 1024**3, maximum=24, capabilities={"flags": []})
    assert all((item.get("flash_attn"), item.get("poll"), item.get("poll_batch"), item.get("parallel")) == ("auto", 50, 1, 1) for item in candidates)


def test_empty_capabilities_do_not_synthesize_standard_defaults() -> None:
    contract = TuningContract.from_mapping({"service": "chat", "profile": "speed", "model_path": "m.gguf", "context_length": 4096, "concurrency": 1})
    candidates = generate_llama_candidates(baseline={}, contract=contract, physical_cores=4, logical_processors=8, total_vram_bytes=8 * 1024**3, maximum=24, capabilities={"flags": []})
    assert candidates
    assert all(not {"batch", "ubatch", "threads", "threads_batch", "gpu_layers", "flash_attn", "poll", "poll_batch", "parallel"}.intersection(item) for item in candidates)


def test_partial_capabilities_do_not_vary_unadvertised_standard_controls() -> None:
    contract = TuningContract.from_mapping({"service": "chat", "profile": "speed", "model_path": "m.gguf", "context_length": 4096, "concurrency": 1})
    candidates = generate_llama_candidates(baseline={}, contract=contract, physical_cores=4, logical_processors=8, total_vram_bytes=8 * 1024**3, maximum=24, capabilities={"flags": ["kv-unified"]})
    assert candidates
    assert all(not {"batch", "ubatch", "threads", "threads_batch", "flash_attn", "poll", "poll_batch", "parallel"}.intersection(item) for item in candidates)


def test_combined_candidates_do_not_synthesize_unadvertised_standard_controls() -> None:
    contract = TuningContract.from_mapping({
        "service": "chat", "profile": "speed", "model_path": "m.gguf",
        "context_length": 4096, "concurrency": 1,
    })
    baseline = {"batch": 128, "ubatch": 64, "threads": 4, "threads_batch": 4, "poll": 50}
    candidates = generate_llama_candidates(
        baseline=baseline,
        contract=contract,
        physical_cores=4,
        logical_processors=8,
        total_vram_bytes=8 * 1024**3,
        maximum=24,
        capabilities={"flags": ["poll"]},
        )
    assert candidates
    assert all(
        (item.get("batch"), item.get("ubatch"), item.get("threads"), item.get("threads_batch"))
        == (128, 64, 4, 4)
        for item in candidates
    )
    assert {item.get("poll") for item in candidates} >= {0, 25, 50}


def test_optional_family_representatives_are_reserved_before_products() -> None:
    contract = TuningContract.from_mapping({
        "service": "chat", "profile": "speed", "model_path": "m.gguf",
        "context_length": 4096, "concurrency": 1, "kv_precision_search": True,
    })
    candidates = generate_llama_candidates(
        baseline={"batch": 512, "ubatch": 128, "threads": 8, "threads_batch": 8,
                  "cache_type_k": "f16", "cache_type_v": "f16"},
        contract=contract,
        physical_cores=8,
        logical_processors=16,
        total_vram_bytes=8 * 1024**3,
        maximum=24,
        capabilities={
            "flags": ["cache-type-k", "cache-type-v", "kv-unified", "kv-offload",
                      "no-host", "repack", "load-mode", "op-offload"],
            "cache_type_k": ["f16", "q8_0", "q4_0"],
            "cache_type_v": ["f16", "q8_0", "q4_0"],
        },
    )
    assert all(any(key in item for item in candidates) for key in (
        "kv_unified", "kv_offload", "no_host", "repack", "load_mode", "op_offload",
    ))


def test_baseline_prio_is_removed_when_priority_is_not_advertised() -> None:
    contract = TuningContract.from_mapping({"service": "chat", "profile": "speed", "model_path": "m.gguf", "context_length": 4096, "concurrency": 1})
    candidates = generate_llama_candidates(baseline={"prio": 10}, contract=contract, physical_cores=4, logical_processors=8, total_vram_bytes=8 * 1024**3, maximum=24, capabilities={"flags": ["kv-unified"]})
    assert all("prio" not in item for item in candidates)


def test_explicit_capabilities_gate_parallel_variations_even_for_concurrent_contracts() -> None:
    contract = TuningContract.from_mapping({"service": "chat", "profile": "speed", "model_path": "m.gguf", "context_length": 4096, "concurrency": 4})
    candidates = generate_llama_candidates(baseline={"parallel": 4}, contract=contract, physical_cores=4, logical_processors=8, total_vram_bytes=8 * 1024**3, maximum=24, capabilities={"flags": []})
    assert all(item.get("parallel") == 4 for item in candidates)


def test_contract_gpu_layers_override_conflicting_baseline() -> None:
    contract = TuningContract.from_mapping({"service": "chat", "profile": "speed", "model_path": "m.gguf", "context_length": 4096, "concurrency": 1, "gpu_layers": 17})
    candidates = generate_llama_candidates(baseline={"gpu_layers": 99}, contract=contract, physical_cores=4, logical_processors=8, total_vram_bytes=8 * 1024**3)
    assert candidates
    assert all(item["gpu_layers"] == 17 for item in candidates)


def test_candidate_generation_emits_numeric_prio_when_priority_is_supported() -> None:
    contract = TuningContract.from_mapping({"service": "chat", "profile": "speed", "model_path": "m.gguf", "context_length": 4096, "concurrency": 1})
    candidates = generate_llama_candidates(baseline={}, contract=contract, physical_cores=4, logical_processors=8, total_vram_bytes=8 * 1024**3, maximum=24, capabilities={"flags": ["priority"]})
    assert any(isinstance(item.get("prio"), int) for item in candidates)


def test_candidate_generation_reserves_enabled_runtime_families_with_small_budget() -> None:
    contract = TuningContract.from_mapping({"service": "chat", "profile": "speed", "model_path": "m.gguf", "context_length": 4096, "concurrency": 1})
    candidates = generate_llama_candidates(baseline={}, contract=contract, physical_cores=4, logical_processors=8, total_vram_bytes=8 * 1024**3, maximum=24, capabilities={"flags": ["kv-unified", "kv-offload", "no-host", "repack", "load-mode", "op-offload", "priority"]})
    assert any("kv_unified" in item for item in candidates)
    assert any("kv_offload" in item for item in candidates)
    assert any("no_host" in item for item in candidates)
    assert any("repack" in item for item in candidates)
    assert any("load_mode" in item for item in candidates)
    assert any("op_offload" in item for item in candidates)
    assert any("prio" in item for item in candidates)


def test_speed_winner_requires_positive_paired_interval_and_constraints() -> None:
    baseline = SpeedMeasurement.from_mapping(
        {"latency_seconds": 10.0, "ttft_seconds": 1.0, "tokens": 256, "failures": 0}
    )
    better = SpeedMeasurement.from_mapping(
        {"latency_seconds": 8.0, "ttft_seconds": 0.9, "tokens": 256, "failures": 0}
    )
    worse_quality = SpeedMeasurement.from_mapping(
        {"latency_seconds": 7.0, "ttft_seconds": 0.8, "tokens": 256, "failures": 1}
    )

    result = select_profile_winner(
        "speed",
        baseline=baseline,
        candidates=[
            {"config": {"batch": 512}, "measurement": better, "improvement_interval": (0.05, 0.30)},
            {"config": {"batch": 1024}, "measurement": worse_quality, "improvement_interval": (0.10, 0.40)},
        ],
    )

    assert result["selected"]["config"] == {"batch": 512}
    assert result["outcome"] == "improved"


def test_cost_winner_is_gpu_energy_per_request_and_rejects_latency_regression() -> None:
    baseline = CostMeasurement.from_mapping(
        {
            "gpu_joules": 100.0,
            "requests": 10,
            "latency_seconds": 10.0,
            "cpu_seconds": 20.0,
            "failures": 0,
        }
    )
    lower_energy = CostMeasurement.from_mapping(
        {
            "gpu_joules": 80.0,
            "requests": 10,
            "latency_seconds": 10.2,
            "cpu_seconds": 20.1,
            "failures": 0,
        }
    )
    slow = CostMeasurement.from_mapping(
        {
            "gpu_joules": 60.0,
            "requests": 10,
            "latency_seconds": 20.0,
            "cpu_seconds": 20.0,
            "failures": 0,
        }
    )

    result = select_profile_winner(
        "cost",
        baseline=baseline,
        candidates=[
            {"config": {"poll": 0}, "measurement": lower_energy, "improvement_interval": (0.05, 0.30)},
            {"config": {"batch": 128}, "measurement": slow, "improvement_interval": (0.10, 0.50)},
        ],
    )

    assert result["selected"]["config"] == {"poll": 0}
    assert result["selected"]["measurement"]["gpu_joules_per_request"] == 8.0
    assert result["outcome"] == "improved"


def test_tuning_store_round_trips_run_events_without_clobbering_existing_state() -> None:
    with tempfile.TemporaryDirectory() as directory:
        store = TuningStore(Path(directory) / "tuning.db")
        run = store.create_run({"service": "chat", "profile": "speed"})
        store.append_event(run["run_id"], {"stage": "baseline", "message": "measured"})
        store.update_run(run["run_id"], {"status": "COMPLETED", "outcome": "no_improvement"})

        loaded = store.get_run(run["run_id"])
        assert loaded["status"] == "COMPLETED"
        assert loaded["outcome"] == "no_improvement"
        assert loaded["events"][0]["stage"] == "baseline"


def test_gpu_energy_sampler_integrates_power_without_touching_monitoring_store() -> None:
    from rift.tuning_engine import GpuEnergySampler

    class Collector:
        def __init__(self):
            self.samples = iter(
                [
                    {"observed_at": 0.0, "gpu_power_watts": 10.0},
                    {"observed_at": 1.0, "gpu_power_watts": 20.0},
                    {"observed_at": 2.0, "gpu_power_watts": 10.0},
                ]
            )

        def collect(self):
            return next(self.samples)

    sampler = GpuEnergySampler(collector=Collector())
    sampler.sample_once()
    sampler.sample_once()
    result = sampler.stop()
    assert result["available"] is True
    assert result["gpu_joules"] == 30.0
    assert result["covered_seconds"] == 2.0


def test_profiled_tune_cli_parses_review_and_run_controls() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "tune",
            "--service",
            "chat",
            "--profile",
            "cost",
            "--budget",
            "60m",
            "--no-apply",
            "--detach",
            "--allow-restart",
            "--yes",
        ]
    )

    assert args.command == "tune"
    assert args.profile == "cost"
    assert args.budget == "60m"
    assert args.no_apply is True
    assert args.detach is True
    assert args.allow_restart is True
    assert args.yes is True


def main() -> None:
    test_contract_locks_artifact_and_cache_precision()
    test_llama_candidates_are_bounded_and_preserve_locked_values()
    test_candidate_generation_varies_kv_precision_without_changing_weight_quantization()
    test_candidate_generation_includes_runtime_memory_and_cuda_controls_when_supported()
    test_speed_winner_requires_positive_paired_interval_and_constraints()
    test_cost_winner_is_gpu_energy_per_request_and_rejects_latency_regression()
    test_tuning_store_round_trips_run_events_without_clobbering_existing_state()
    test_gpu_energy_sampler_integrates_power_without_touching_monitoring_store()
    test_profiled_tune_cli_parses_review_and_run_controls()
    print("tuning_engine_tests: PASS")


if __name__ == "__main__":
    main()
