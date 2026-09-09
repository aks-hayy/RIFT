import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


def test_shared_windows_keep_concurrency_and_do_not_count_chunks_as_tokens():
    from rift.tuning_benchmark import BenchmarkRecipe, run_windows

    calls = []

    def benchmark(**kwargs):
        calls.append(kwargs)
        return {
            "available": True,
            "status_code": 200,
            "generated_tokens": 4,
            "decode_tokens_per_second": 20.0,
            "first_token_seconds": 0.01,
        }

    result = run_windows(
        benchmark,
        base_url="http://test",
        recipe=BenchmarkRecipe(prompt="hello", usage="shared", concurrency=2, requests_per_window=2),
        warmups=1,
        repetitions=5,
    )
    assert len(calls) == 12
    assert result["requests"] == 10
    assert result["objective_definition"] == "aggregate_output_throughput"
    assert result["confidence_interval"]["available"] is True
    assert result["limitations"][-1] == "True token-level ITL unavailable"


def test_recipe_rejects_underfilled_window_and_bootstrap_is_inconclusive():
    import pytest
    from rift.tuning_benchmark import BenchmarkRecipe, bootstrap_interval

    with pytest.raises(ValueError):
        BenchmarkRecipe(prompt="x", concurrency=4, requests_per_window=1)
    assert bootstrap_interval([1.0, 2.0])["verdict"] == "inconclusive"


def test_vllm_adapter_uses_pinned_runtime_probe_and_locks_identity():
    from rift.tuning_adapters import VllmTuningAdapter

    class Provider:
        def probe_tuning_runtime(self, plan):
            return {"flags": {
                "--max-num-batched-tokens": True,
                "--max-num-seqs": True,
                "--enable-chunked-prefill": True,
                "--no-enable-chunked-prefill": True,
                "--enable-prefix-caching": True,
                "--no-enable-prefix-caching": True,
                "--enforce-eager": True,
                "--no-enforce-eager": True,
                "--gpu-memory-utilization": True,
            }, "probed": True}

    class Contract:
        concurrency = 2
        context_length = 4096
        kv_precision_search = False

    adapter = VllmTuningAdapter(Provider())
    baseline = {"accelerator_family": "cuda", "max_num_batched_tokens": 4096,
                "max_num_seqs": 2, "runtime_feature_probe": {"flags": {}},
                "model_path": "model", "dtype": "auto"}
    candidates = adapter.propose(launch_plan={"tuning": baseline}, hardware={"accelerator_family": "cuda"}, contract=Contract())
    assert candidates
    assert all(item["model_path"] == "model" for item in candidates)
    assert all(item.get("kv_cache_dtype") is None for item in candidates)
    assert any(item.get("max_num_seqs") == 4 for item in candidates)
