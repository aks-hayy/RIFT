"""Backend-neutral load windows and deterministic, window-level statistics.

Raw observations retain failures. Streaming chunks are never treated as tokens.
These primitives do not execute generated code or infer prompts from telemetry.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
import math
import random
import statistics
import time
from typing import Any, Callable


@dataclass(frozen=True)
class BenchmarkRecipe:
    prompt: str
    max_tokens: int = 32
    concurrency: int = 1
    usage: str = "interactive"
    requests_per_window: int = 1
    request_rate: float | None = None
    cache_condition: str = "warm_prefix"
    seed: int = 17
    schema_version: int = 1
    recipe_id: str = "rift-synthetic-local/v1"
    max_ttft_seconds: float | None = None
    max_latency_seconds: float | None = None

    def __post_init__(self):
        if self.schema_version != 1 or self.usage not in {"interactive", "shared"}:
            raise ValueError("unsupported recipe version or usage")
        if not isinstance(self.prompt, str) or not self.prompt.strip():
            raise ValueError("recipe needs a nonempty prompt")
        for key in ("concurrency", "max_tokens", "requests_per_window"):
            value = getattr(self, key)
            if type(value) is not int or value < 1:
                raise ValueError(f"{key} must be a positive integer")
        if self.requests_per_window < self.concurrency:
            raise ValueError("a window must offer at least the requested concurrency")
        for key in ("request_rate", "max_ttft_seconds", "max_latency_seconds"):
            value = getattr(self, key)
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value <= 0):
                raise ValueError(f"{key} must be a positive finite number")
        if self.cache_condition not in {"warm_prefix", "unique_prefix"}:
            raise ValueError("unsupported cache condition")


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lo, hi = math.floor(position), math.ceil(position)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo)


def bootstrap_interval(values: list[float], *, seed: int = 17, draws: int = 2000) -> dict[str, Any]:
    if len(values) < 5 or any(not math.isfinite(v) for v in values):
        return {"available": False, "verdict": "inconclusive", "sample_count": len(values), "reason": "at least five finite independent windows required"}
    rng = random.Random(seed)
    means = [statistics.mean(rng.choices(values, k=len(values))) for _ in range(draws)]
    return {"available": True, "method": "seeded_window_bootstrap/v1", "level": .95,
            "seed": seed, "draws": draws, "sample_count": len(values),
            "point_estimate": statistics.mean(values), "lower_bound": percentile(means, .025),
            "upper_bound": percentile(means, .975)}


def improvement_interval(baseline: list[float], candidate: list[float], *, cost: bool = False) -> list[float]:
    if min(len(baseline), len(candidate)) < 5 or any(not math.isfinite(v) or v <= 0 for v in baseline + candidate):
        return [-1.0, 1.0]
    rng = random.Random(17)
    values = []
    for _ in range(2000):
        a = statistics.mean(rng.choices(baseline, k=len(baseline)))
        b = statistics.mean(rng.choices(candidate, k=len(candidate)))
        values.append(1 - b / a if cost else b / a - 1)
    return [percentile(values, .025), percentile(values, .975)]


def run_windows(benchmark: Callable[..., dict], *, base_url: str, recipe: BenchmarkRecipe,
                warmups: int, repetitions: int) -> dict[str, Any]:
    if repetitions < 1 or warmups < 0:
        raise ValueError("invalid measurement window counts")
    windows = []
    for window_id in range(-warmups, repetitions):
        started = time.perf_counter()

        def request(index: int) -> dict:
            scheduled = started + index / recipe.request_rate if recipe.request_rate else None
            if scheduled:
                delay = scheduled - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
            entered = time.perf_counter()
            queue = max(0.0, entered - scheduled) if scheduled else 0.0
            prompt = recipe.prompt
            if recipe.cache_condition == "unique_prefix":
                prompt = f"Request {recipe.seed:08d}-{window_id:06d}-{index:06d}\n" + prompt
            try:
                raw = dict(benchmark(base_url=base_url, prompt=prompt, max_tokens=recipe.max_tokens,
                                     seed=recipe.seed, temperature=0.0, ignore_eos=True))
            except Exception as exc:
                raw = {"available": False, "error": str(exc)}
            elapsed = time.perf_counter() - entered
            # Prefer backend usage counts; never manufacture counts from chunks.
            tokens = raw.get("generated_tokens") or raw.get("generated_tokens_estimate") or 0
            if not isinstance(tokens, (int, float)) or not math.isfinite(tokens) or tokens < 0:
                tokens = 0
            success = raw.get("available", True) and raw.get("status_code", 200) == 200 and tokens > 0
            ttft = raw.get("first_token_seconds")
            ttft_source = "client_stream" if ttft is not None else "unavailable"
            if ttft is None and raw.get("time_to_first_token_seconds_estimate") is not None:
                ttft = raw["time_to_first_token_seconds_estimate"]
                ttft_source = "backend_timing_estimate"
            latency = queue + elapsed
            ttft = queue + float(ttft) if ttft is not None else None
            qualified = success
            if recipe.max_ttft_seconds is not None:
                qualified = qualified and ttft is not None and ttft <= recipe.max_ttft_seconds
            if recipe.max_latency_seconds is not None:
                qualified = qualified and latency <= recipe.max_latency_seconds
            return {**raw, "request_index": index, "success": bool(success), "slo_passed": bool(qualified),
                    "generated_tokens": tokens, "client_queue_seconds": queue,
                    "client_elapsed_seconds": latency, "first_token_seconds": ttft,
                    "ttft_source": ttft_source}

        with ThreadPoolExecutor(max_workers=recipe.concurrency) as executor:
            samples = list(executor.map(request, range(recipe.requests_per_window)))
        elapsed = max(time.perf_counter() - started, 1e-9)
        successful = [s for s in samples if s["success"]]
        decode = [s.get("decode_tokens_per_second") for s in successful]
        decode = [float(v) for v in decode if isinstance(v, (int, float)) and math.isfinite(v) and v > 0]
        tokens = sum(s["generated_tokens"] for s in successful)
        good_tokens = sum(s["generated_tokens"] for s in samples if s["slo_passed"])
        constrained = recipe.max_ttft_seconds is not None or recipe.max_latency_seconds is not None
        aggregate = tokens / elapsed
        objective = statistics.mean(decode) if recipe.usage == "interactive" and len(decode) == len(samples) else None
        if recipe.usage == "shared":
            objective = good_tokens / elapsed if constrained else aggregate
        if window_id >= 0:
            windows.append({"window_id": window_id, "elapsed_seconds": elapsed, "samples": samples,
                            "objective": objective, "aggregate_tokens_per_second": aggregate,
                            "goodput_tokens_per_second": good_tokens / elapsed if constrained else None,
                            "failures": len(samples) - len(successful)})
    samples = [s for w in windows for s in w["samples"]]
    objectives = [w["objective"] for w in windows if w["objective"] is not None]
    latencies = [s["client_elapsed_seconds"] for s in samples]
    ttfts = [s["first_token_seconds"] for s in samples if s["first_token_seconds"] is not None]
    return {"schema_version": 2, "recipe": asdict(recipe), "windows": windows, "samples": samples,
            "objective_samples": objectives, "tokens_per_second": statistics.mean(objectives) if len(objectives) == len(windows) else None,
            "objective_definition": "per_request_decode" if recipe.usage == "interactive" else "slo_goodput" if constrained else "aggregate_output_throughput",
            "latency_seconds": statistics.mean(latencies), "ttft_seconds": statistics.mean(ttfts) if ttfts else None,
            "requests": len(samples), "tokens": sum(s["generated_tokens"] for s in samples),
            "failures": sum(w["failures"] for w in windows), "replicates": [w["elapsed_seconds"] for w in windows],
            "confidence_interval": bootstrap_interval(objectives),
            "p95": {"available": False, "verdict": "inconclusive", "completed_requests": sum(s["success"] for s in samples),
                    "reason": "tail-latency acceptance requires a dedicated cell with at least 100 completions and window-level bounds"},
            "limitations": ["Synthetic fixed request mix; not proof of application quality", "True token-level ITL unavailable"]}
