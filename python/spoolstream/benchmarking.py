"""Reproducible benchmark statistics and regression gates for RIFT."""

from __future__ import annotations

import math
import platform
import statistics
import time
from typing import Any, Callable


JsonDict = dict[str, Any]

DEFAULT_PROMPT_SUITE = (
    {
        "id": "short-instruction-v1",
        "task": "chat",
        "prompt": "Explain one practical benefit of local LLM inference in two sentences.",
        "max_tokens": 48,
    },
    {
        "id": "structured-json-v1",
        "task": "structured",
        "prompt": "Return JSON with keys name and purpose describing RIFT.",
        "max_tokens": 48,
    },
    {
        "id": "code-small-v1",
        "task": "coding",
        "prompt": "Write a Python function that returns the median of a non-empty list.",
        "max_tokens": 96,
    },
)


class BenchmarkSuite:
    def __init__(self, suite: tuple[JsonDict, ...] = DEFAULT_PROMPT_SUITE) -> None:
        self.suite = tuple(dict(item) for item in suite)

    def run(
        self,
        benchmark: Callable[..., JsonDict],
        *,
        base_url: str,
        warmups: int = 1,
        repetitions: int = 3,
        cold_cache: bool = False,
        metadata: JsonDict | None = None,
    ) -> JsonDict:
        if warmups < 0 or repetitions <= 0:
            raise ValueError("warmups cannot be negative and repetitions must be positive")
        started = time.time()
        results = []
        for case in self.suite:
            warmup_results = [
                benchmark(
                    base_url=base_url,
                    prompt=case["prompt"],
                    max_tokens=int(case["max_tokens"]),
                )
                for _ in range(warmups)
            ]
            samples = [
                benchmark(
                    base_url=base_url,
                    prompt=case["prompt"],
                    max_tokens=int(case["max_tokens"]),
                )
                for _ in range(repetitions)
            ]
            summary = summarize_samples(samples)
            results.append(
                {
                    "case": case,
                    "warmup_count": len(warmup_results),
                    "samples": samples,
                    "summary": summary,
                }
            )
        aggregate_tps = [
            float(result["summary"]["median_tokens_per_second"])
            for result in results
            if result["summary"].get("median_tokens_per_second") is not None
        ]
        aggregate_latency = [
            float(result["summary"]["p95_elapsed_seconds"])
            for result in results
            if result["summary"].get("p95_elapsed_seconds") is not None
        ]
        return {
            "schema_version": 2,
            "suite_id": "rift-core-v1",
            "created_unix_seconds": started,
            "cache_state": "cold_requested" if cold_cache else "warm_or_unspecified",
            "warmups": warmups,
            "repetitions": repetitions,
            "host": {
                "platform": platform.platform(),
                "python": platform.python_version(),
            },
            "metadata": metadata or {},
            "cases": results,
            "summary": {
                "valid": bool(results) and all(result["summary"]["valid"] for result in results),
                "median_tokens_per_second": round(statistics.median(aggregate_tps), 6)
                if aggregate_tps
                else None,
                "p95_elapsed_seconds": round(max(aggregate_latency), 6)
                if aggregate_latency
                else None,
                "case_count": len(results),
            },
        }


def summarize_samples(samples: list[JsonDict]) -> JsonDict:
    throughputs = []
    latencies = []
    first_token = []
    generated = []
    for sample in samples:
        elapsed = _number(sample.get("elapsed_seconds"))
        tokens = int(sample.get("generated_tokens_estimate") or sample.get("generated_tokens") or 0)
        throughput = _number(
            sample.get("decode_tokens_per_second")
            or sample.get("tokens_per_second_estimate")
            or sample.get("tokens_per_second")
        )
        if throughput is None and elapsed and tokens:
            throughput = tokens / elapsed
        ttft = _number(sample.get("time_to_first_token_seconds_estimate") or sample.get("first_token_seconds"))
        if throughput is not None and throughput > 0:
            throughputs.append(throughput)
        if elapsed is not None and elapsed > 0:
            latencies.append(elapsed)
        if ttft is not None and ttft >= 0:
            first_token.append(ttft)
        generated.append(tokens)
    return {
        "valid": bool(samples) and bool(throughputs) and all(tokens > 0 for tokens in generated),
        "sample_count": len(samples),
        "median_tokens_per_second": _rounded_median(throughputs),
        "p95_tokens_per_second": _rounded_percentile(throughputs, 0.95),
        "median_elapsed_seconds": _rounded_median(latencies),
        "p95_elapsed_seconds": _rounded_percentile(latencies, 0.95),
        "median_first_token_seconds": _rounded_median(first_token),
        "p95_first_token_seconds": _rounded_percentile(first_token, 0.95),
        "generated_tokens": generated,
    }


def regression_decision(
    baseline: JsonDict,
    candidate: JsonDict,
    *,
    throughput_drop_limit: float = 0.03,
    latency_increase_limit: float = 0.08,
) -> JsonDict:
    baseline_tps = _number(baseline.get("median_tokens_per_second")) or 0.0
    candidate_tps = _number(candidate.get("median_tokens_per_second")) or 0.0
    baseline_p95 = _number(baseline.get("p95_elapsed_seconds"))
    candidate_p95 = _number(candidate.get("p95_elapsed_seconds"))
    throughput_delta = candidate_tps / baseline_tps - 1.0 if baseline_tps > 0 else None
    latency_delta = (
        candidate_p95 / baseline_p95 - 1.0
        if baseline_p95 and candidate_p95 is not None and baseline_p95 > 0
        else None
    )
    reasons = []
    if candidate_tps <= 0:
        reasons.append("candidate produced no valid throughput measurement")
    if throughput_delta is not None and throughput_delta < -abs(throughput_drop_limit):
        reasons.append(f"throughput regressed by {abs(throughput_delta) * 100:.2f}%")
    if latency_delta is not None and latency_delta > abs(latency_increase_limit):
        reasons.append(f"p95 latency increased by {latency_delta * 100:.2f}%")
    return {
        "promote": not reasons,
        "rollback": bool(reasons),
        "throughput_delta_percent": round(throughput_delta * 100.0, 3)
        if throughput_delta is not None
        else None,
        "p95_latency_delta_percent": round(latency_delta * 100.0, 3)
        if latency_delta is not None
        else None,
        "reasons": reasons,
        "thresholds": {
            "throughput_drop_percent": throughput_drop_limit * 100.0,
            "p95_latency_increase_percent": latency_increase_limit * 100.0,
        },
    }


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _rounded_percentile(values: list[float], quantile: float) -> float | None:
    value = _percentile(values, quantile)
    return round(value, 6) if value is not None else None


def _rounded_median(values: list[float]) -> float | None:
    return round(statistics.median(values), 6) if values else None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


__all__ = ["BenchmarkSuite", "DEFAULT_PROMPT_SUITE", "regression_decision", "summarize_samples"]
