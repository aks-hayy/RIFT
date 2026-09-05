"""Autonomous tuning primitives shared by RIFT's controller, CLI, and UI.

This module deliberately contains no process launching.  It owns the immutable
tuning contract, bounded llama.cpp candidate generation, profile gates, and a
small durable run journal.  The orchestrator supplies backend-specific process
and deployment operations around these primitives.
"""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
import json
import math
import platform
from pathlib import Path
import sqlite3
import threading
import time
import uuid
from typing import Any, Iterable, Mapping


JsonDict = dict[str, Any]
LOCKED_KEYS = frozenset(
    {
        "model_path",
        "model_sha256",
        "weight_quantization",
        "cache_type_k",
        "cache_type_v",
        "context_length",
        "concurrency",
        "gpu_layers",
        "spec_draft_model",
        "spec_draft_sha256",
    }
)
PROFILE_NAMES = frozenset({"speed", "cost"})


class GpuEnergySampler:
    """Best-effort GPU energy sampler isolated from the monitoring supervisor.

    The normal telemetry supervisor remains the source of truth for service
    monitoring.  A profiled run owns one short-lived sampler so candidate
    measurements cannot change the supervisor's sessions or accounting state.
    ``nvidia-smi`` exposes instantaneous power on Windows; integrating those
    samples is therefore explicit about coverage and availability in reports.
    """

    def __init__(self, *, interval_seconds: float = 0.5, collector: Any | None = None) -> None:
        if interval_seconds <= 0.0:
            raise ValueError("interval_seconds must be positive")
        self.interval_seconds = float(interval_seconds)
        self._collector = collector
        self._samples: list[tuple[float, float]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._started_at: float | None = None

    def _collect(self) -> tuple[float, float] | None:
        if self._collector is None:
            from .telemetry.collectors import LocalCollector

            self._collector = LocalCollector()
        try:
            sample = self._collector.collect()
        except Exception:
            return None
        power = _finite_number(sample.get("gpu_power_watts"))
        observed = _finite_number(sample.get("observed_at"))
        if power is None or observed is None or power < 0.0:
            return None
        return observed, power

    def sample_once(self) -> None:
        sample = self._collect()
        if sample is not None:
            self._samples.append(sample)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._samples.clear()
        self._started_at = time.time()
        self.sample_once()

        def worker() -> None:
            while not self._stop.wait(self.interval_seconds):
                self.sample_once()

        self._thread = threading.Thread(target=worker, name="rift-tuning-gpu-energy", daemon=True)
        self._thread.start()

    def stop(self) -> JsonDict:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.interval_seconds * 2.0))
        self.sample_once()
        self._thread = None
        samples = sorted(self._samples)
        joules = 0.0
        covered_seconds = 0.0
        for (previous_at, previous_power), (observed_at, power) in zip(samples, samples[1:]):
            delta = max(0.0, observed_at - previous_at)
            # Trapezoidal integration is less biased than multiplying by the
            # last sample when the workload changes power between polls.
            joules += ((previous_power + power) / 2.0) * delta
            covered_seconds += delta
        stopped_at = time.time()
        elapsed_seconds = max(0.0, stopped_at - float(self._started_at or stopped_at))
        coverage_ratio = min(1.0, covered_seconds / elapsed_seconds) if elapsed_seconds > 0.0 else 0.0
        return {
            "available": bool(samples) and covered_seconds > 0.0,
            "method": "nvidia-smi power.draw integration",
            "scope": "gpu_device",
            "attribution": "aggregate_device_power",
            "attribution_limit": "includes other workloads sharing the GPU",
            "gpu_joules": round(joules, 6),
            "samples": len(samples),
            "covered_seconds": round(covered_seconds, 6),
            "elapsed_seconds": round(elapsed_seconds, 6),
            "coverage_ratio": round(coverage_ratio, 6),
            "power_samples": [
                {"observed_at": observed_at, "power_watts": power}
                for observed_at, power in samples
            ],
        }


def _finite_number(value: Any, *, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


@dataclass(frozen=True)
class TuningContract:
    """Immutable run permissions and deployment properties."""

    service: str
    profile: str
    model_path: str
    locked: JsonDict
    context_length: int
    concurrency: int
    kv_precision_search: bool = True
    ngram_speculation: bool = True

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "TuningContract":
        service = str(value.get("service") or "").strip()
        profile = str(value.get("profile") or "").strip().lower()
        model_path = str(value.get("model_path") or "").strip()
        if not service or profile not in PROFILE_NAMES or not model_path:
            raise ValueError("tuning contract requires service, speed/cost profile, and model_path")
        try:
            context_length = int(value.get("context_length"))
            concurrency = int(value.get("concurrency"))
        except (TypeError, ValueError) as exc:
            raise ValueError("tuning contract requires integer context_length and concurrency") from exc
        if context_length <= 0 or concurrency <= 0:
            raise ValueError("context_length and concurrency must be positive")

        locked = {
            key: value[key]
            for key in LOCKED_KEYS
            if key in value and value[key] is not None
        }
        locked.setdefault("model_path", model_path)
        locked.setdefault("context_length", context_length)
        locked.setdefault("concurrency", concurrency)
        return cls(
            service=service,
            profile=profile,
            model_path=model_path,
            locked=locked,
            context_length=context_length,
            concurrency=concurrency,
            kv_precision_search=bool(value.get("kv_precision_search", True)),
            ngram_speculation=bool(value.get("ngram_speculation", True)),
        )

    def to_dict(self) -> JsonDict:
        return {
            "service": self.service,
            "profile": self.profile,
            "model_path": self.model_path,
            "context_length": self.context_length,
            "concurrency": self.concurrency,
            "kv_precision_search": self.kv_precision_search,
            "ngram_speculation": self.ngram_speculation,
            "locked": dict(self.locked),
        }


def candidate_is_allowed(contract: TuningContract, candidate: Mapping[str, Any]) -> bool:
    """Return whether a candidate preserves all contract-owned properties."""

    if not contract.ngram_speculation:
        if candidate.get("ngram_speculation") is True:
            return False
        if candidate.get("spec_type") == "ngram-mod":
            return False
        if any(str(key).startswith("spec_ngram_mod_") for key in candidate):
            return False

    for key in LOCKED_KEYS:
        if key in {"cache_type_k", "cache_type_v"} and contract.kv_precision_search:
            continue
        if key in candidate and key in contract.locked:
            if candidate[key] != contract.locked[key]:
                return False
    return True


def _candidate_key(candidate: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((str(key), repr(value)) for key, value in candidate.items()))


def generate_llama_candidates(
    *,
    baseline: Mapping[str, Any],
    contract: TuningContract,
    physical_cores: int,
    logical_processors: int,
    total_vram_bytes: int,
    maximum: int = 24,
    capabilities: Mapping[str, Any] | None = None,
) -> list[JsonDict]:
    """Generate a deterministic, bounded first-pass llama.cpp search set."""

    if maximum <= 0:
        raise ValueError("maximum candidate count must be positive")
    if physical_cores <= 0 or logical_processors <= 0:
        raise ValueError("CPU counts must be positive")

    # Provider summaries often include optional knobs with ``None`` to make
    # serialization convenient.  They are not launch values and must not be
    # turned into a literal ``--cache-type-k None`` candidate.
    seed = {key: value for key, value in baseline.items() if value is not None}
    minimal_capabilities = capabilities is not None
    if not minimal_capabilities:
        seed.setdefault("batch", 512)
        seed.setdefault("ubatch", 128)
        seed.setdefault("threads", max(1, physical_cores // 2))
        seed.setdefault("threads_batch", int(seed["threads"]))
        seed.setdefault("gpu_layers", 999)
        seed.setdefault("flash_attn", "auto")
        seed.setdefault("poll", 50)
        seed.setdefault("poll_batch", 1)
        seed.setdefault("parallel", contract.concurrency)
    for key, value in contract.locked.items():
        seed[key] = value if key == "gpu_layers" else seed.setdefault(key, value)

    candidates: list[JsonDict] = []
    caps = capabilities or {}
    raw_flags = caps.get("flags", ())
    flags = {str(flag).lower().replace("_", "-") for flag in raw_flags}

    def supported(name: str) -> bool:
        aliases = {
            "kv-unified": ("kv_unified", "kv-unified"),
            "kv-offload": ("kv_offload", "kv-offload"),
            "no-host": ("no_host", "no-host"),
            "op-offload": ("op_offload", "op-offload"),
            "load-mode": ("load_mode", "load-mode"),
            "continuous-batching": ("continuous_batching", "continuous-batching"),
            "cpu-priority": ("cpu_priority", "priority", "cpu-priority"),
            "cpu-affinity": ("cpu_affinity", "affinity", "cpu-affinity"),
            "spec-type": ("spec_type", "spec-type"),
            "spec-draft-model": ("spec_draft_model", "spec-draft-model"),
            "spec-draft-n-max": ("spec_draft_n_max", "spec-draft-n-max"),
            "spec-draft-n-min": ("spec_draft_n_min", "spec-draft-n-min"),
            "spec-draft-p-min": ("spec_draft_p_min", "spec-draft-p-min"),
            "spec-draft-p-split": ("spec_draft_p_split", "spec-draft-p-split"),
            "spec-draft-ngl": ("spec_draft_ngl", "spec-draft-ngl"),
            "spec-draft-device": ("spec_draft_device", "spec-draft-device"),
            "spec-ngram-mod-n-min": ("spec_ngram_mod_n_min", "spec-ngram-mod-n-min"),
            "spec-ngram-mod-n-max": ("spec_ngram_mod_n_max", "spec-ngram-mod-n-max"),
            "spec-ngram-mod-n-match": ("spec_ngram_mod_n_match", "spec-ngram-mod-n-match"),
        }
        return name in flags or name.replace("-", "_") in flags or any(
            key in caps for key in aliases.get(name, (name,))
        )

    # Do not carry launch controls into candidates when the probed binary does
    # not advertise them.  Immutable identity and ordinary baseline fields are
    # always retained.
    unsupported_controls = {
        "kv_unified": "kv-unified", "kv_offload": "kv-offload", "no_host": "no-host",
        "repack": "repack", "load_mode": "load-mode", "op_offload": "op-offload",
        "continuous_batching": "continuous-batching", "priority": "cpu-priority",
        "cpu_affinity": "cpu-affinity", "numa": "numa",
        "prio": "cpu-priority",
    }
    for key, capability in unsupported_controls.items():
        if not supported(capability):
            seed.pop(key, None)

    unsupported_spec_controls = {
        "spec_type": "spec-type", "spec_draft_model": "spec-draft-model",
        "spec_draft_n_max": "spec-draft-n-max", "spec_draft_n_min": "spec-draft-n-min",
        "spec_draft_p_min": "spec-draft-p-min", "spec_draft_p_split": "spec-draft-p-split",
        "spec_draft_ngl": "spec-draft-ngl", "spec_draft_device": "spec-draft-device",
        "spec_ngram_mod_n_min": "spec-ngram-mod-n-min",
        "spec_ngram_mod_n_max": "spec-ngram-mod-n-max",
        "spec_ngram_mod_n_match": "spec-ngram-mod-n-match",
    }
    for key, capability in unsupported_spec_controls.items():
        if not supported(capability):
            seed.pop(key, None)
    if not contract.ngram_speculation:
        # An explicit user switch must also clear an inherited optimized
        # launch plan; omitting the controls from new candidates alone would
        # otherwise leave the currently deployed n-gram mode active.
        seed.pop("spec_ngram_mod_n_min", None)
        seed.pop("spec_ngram_mod_n_max", None)
        seed.pop("spec_ngram_mod_n_match", None)
        if seed.get("spec_type") == "ngram-mod":
            seed.pop("spec_type", None)

    def add(value: Mapping[str, Any]) -> None:
        if len(candidates) >= maximum:
            return
        item = dict(value)
        if not candidate_is_allowed(contract, item):
            return
        if int(item.get("batch", 1)) <= 0 or int(item.get("ubatch", 1)) <= 0:
            return
        if int(item.get("ubatch", 1)) > int(item.get("batch", 1)):
            return
        if _candidate_key(item) not in {_candidate_key(existing) for existing in candidates}:
            candidates.append(item)

    def family(items: Iterable[Mapping[str, Any]]) -> None:
        """Add one representative per family before spending budget on products."""
        for item in items:
            if len(candidates) >= maximum:
                return
            add(item)

    # A successful help probe is not a reason to disable ordinary controls;
    # it is the reason to gate each one precisely. An explicit empty/partial
    # capability map must not synthesize flags the binary did not advertise.
    standard_variations = capabilities is None or any(
        supported(name)
        for name in ("batch-size", "ubatch-size", "threads", "threads-batch",
                     "flash-attn", "poll", "poll-batch", "parallel")
    )
    standard_allowed = lambda name: capabilities is None or supported(name)

    def with_standard_controls(
        value: Mapping[str, Any],
        *,
        batch: int | None = None,
        ubatch: int | None = None,
        threads: int | None = None,
        threads_batch: int | None = None,
    ) -> JsonDict:
        """Apply only standard controls explicitly advertised by the probe.

        Combined candidates (for example KV precision + batch) must use the
        same capability gate as their single-family counterparts.  Keeping
        this at the mutation boundary prevents a supported family from
        smuggling an unadvertised launch flag into the bounded search.
        """

        item = dict(value)
        updates = (
            ("batch", batch, "batch-size"),
            ("ubatch", ubatch, "ubatch-size"),
            ("threads", threads, "threads"),
            ("threads_batch", threads_batch, "threads-batch"),
        )
        for key, candidate_value, capability in updates:
            if candidate_value is not None and standard_allowed(capability):
                item[key] = candidate_value
        return item

    # Always retain the untouched seed as the first provider candidate.
    add(seed)

    # KV precision is an explicit first-class tuning control. Put a compact
    # set of quality-preserving and memory-saving pairs near the front of the
    # bounded search so a small candidate budget cannot starve this family
    # behind scheduler/CPU variants. The full Cartesian product follows only
    # after representative pairs have been tested.
    if contract.kv_precision_search:
        k_types = list(caps.get("cache_type_k") or ("f16",))
        v_types = list(caps.get("cache_type_v") or ("f16",))
        preferred_pairs = [
            ("f16", "f16"),
            ("q8_0", "q8_0"),
            ("q4_0", "q4_0"),
            ("q4_1", "q4_1"),
            ("iq4_nl", "iq4_nl"),
            ("f16", "q8_0"),
            ("q8_0", "f16"),
            ("f16", "q4_0"),
            ("q4_0", "f16"),
        ]
        seen_pairs: set[tuple[str, str]] = set()
        pairs = []
        for k, v in preferred_pairs:
            if k in k_types and v in v_types and (k, v) not in seen_pairs:
                pairs.append((k, v))
                seen_pairs.add((k, v))
        pairs.extend(
            (k, v)
            for k in k_types
            for v in v_types
            if (k, v) not in seen_pairs
        )
        # Include both isolated precision changes and the high-value
        # precision+batch combinations early enough for a bounded run.
        family({**seed, "cache_type_k": k, "cache_type_v": v} for k, v in pairs[:5])
        for k, v in pairs[1:3]:
            family(
                with_standard_controls(
                    {**seed, "cache_type_k": k, "cache_type_v": v},
                    batch=batch,
                    ubatch=min(batch, 128),
                )
                for batch in (512, 1024)
            )

    # Speculation is only synthesized for llama.cpp's built-in n-gram mode.
    # Draft-model candidates are allowed only when the caller supplied the
    # exact local artifact, which remains locked by the contract.
    if contract.ngram_speculation and supported("spec-type"):
        draft_model = seed.get("spec_draft_model")
        if draft_model:
            if supported("spec-draft-n-max"):
                family(
                    {**seed, "spec_type": seed.get("spec_type", "draft-simple"),
                     "spec_draft_n_max": value}
                    for value in (3, 5, 8, 12)
                )
            if supported("spec-draft-n-min"):
                family(
                    {**seed, "spec_type": seed.get("spec_type", "draft-simple"),
                     "spec_draft_n_min": value}
                    for value in (1, 2)
                )
            if supported("spec-draft-ngl") and "spec_draft_ngl" not in seed:
                family({**seed, "spec_type": seed.get("spec_type", "draft-simple"), "spec_draft_ngl": 0} for _ in (0,))
        else:
            family({**seed, "spec_type": "ngram-mod"} for _ in (0,))
            if supported("spec-ngram-mod-n-min"):
                family({**seed, "spec_type": "ngram-mod", "spec_ngram_mod_n_min": value} for value in (1, 2))
            if supported("spec-ngram-mod-n-max"):
                family({**seed, "spec_type": "ngram-mod", "spec_ngram_mod_n_max": value} for value in (4, 8, 12))
            if supported("spec-ngram-mod-n-match"):
                family({**seed, "spec_type": "ngram-mod", "spec_ngram_mod_n_match": value} for value in (16, 24, 32))

    # Reserve one representative for every supported optional family before
    # filling large standard families.  Without this reservation a 24-candidate
    # run can spend its entire budget on KV/batch/thread combinations and never
    # test supported runtime-memory or load-mode controls at all.
    optional_families = {
        "kv-unified": ("kv_unified", (True, False)),
        "kv-offload": ("kv_offload", (True, False)),
        "no-host": ("no_host", (True, False)),
        "repack": ("repack", (True, False)),
        "op-offload": ("op_offload", (True, False)),
    }
    for capability, (key, values) in optional_families.items():
        if supported(capability):
            family(({**seed, key: values[0]} for _ in (0,)))
    if supported("load-mode"):
        family(({**seed, "load_mode": "auto"} for _ in (0,)))
    if supported("priority") or supported("cpu-priority"):
        family(({**seed, "prio": 0} for _ in (0,)))
    if supported("affinity") or supported("cpu-affinity"):
        family(({**seed, "cpu_affinity": tuple(range(min(physical_cores, 4)))} for _ in (0,)))
    # The Windows CUDA build advertises NUMA flags but ``numa=auto`` can fail
    # server readiness.  Keep this Linux-only until the backend proves the
    # setting is safe on the current platform.
    numa_supported = supported("numa") and platform.system().lower() != "windows"
    if numa_supported:
        family(({**seed, "numa": "auto"} for _ in (0,)))

    batches = [128, 256, 512, 1024, 2048]
    if total_vram_bytes > 10 * 1024**3:
        batches.extend([3072, 4096])
    # Reserve slots for each independent knob family before filling in
    # combinations.  A small budget must still test CPU parallelism, flash
    # attention, and scheduler polling rather than spending every trial on
    # batch-size variants.
    if standard_variations and standard_allowed("batch-size"):
        family(
            with_standard_controls(
                seed,
                batch=batch,
                ubatch=min(batch, 128),
            )
            for batch in batches
        )

    thread_values = sorted(
        {
            1,
            max(1, physical_cores // 2),
            physical_cores,
            logical_processors,
        }
    )
    if standard_variations and standard_allowed("threads"):
        family(({**seed, "threads": threads} for threads in thread_values))
    if standard_variations and standard_allowed("threads-batch"):
        family(({**seed, "threads_batch": threads} for threads in thread_values))

    if standard_variations and standard_allowed("flash-attn"):
        family(({**seed, "flash_attn": value} for value in ("on", "off", "auto")))

    if standard_variations and standard_allowed("poll"):
        family(({**seed, "poll": poll} for poll in (0, 25, 50)))
    if standard_variations and standard_allowed("poll-batch"):
        family(({**seed, "poll_batch": poll} for poll in (0, 1, 25)))

    if supported("continuous-batching"):
        family(({**seed, "continuous_batching": value} for value in (True, False)))
    if standard_allowed("parallel") and (supported("parallel") or (capabilities is None and contract.concurrency > 1)):
        family(({**seed, "parallel": value} for value in sorted({1, contract.concurrency, max(1, contract.concurrency * 2)})))

    for capability, (key, values) in optional_families.items():
        if supported(capability):
            family(({**seed, key: value} for value in values))
    if supported("load-mode"):
        family(({**seed, "load_mode": value} for value in ("auto", "mmap", "mlock", "mmap+mlock")))
    if supported("priority") or supported("cpu-priority"):
        family(({**seed, "prio": value} for value in (0, 10)))
    if supported("affinity") or supported("cpu-affinity"):
        family(({**seed, "cpu_affinity": tuple(range(min(physical_cores, 4)))} ,))
    if numa_supported:
        family(({**seed, "numa": value} for value in ("auto", "distribute")))

    for batch, ubatch, threads in (
        (batch, min(batch, 128), threads)
        for batch in batches
        for threads in thread_values
    ):
        if not standard_variations or len(candidates) >= maximum:
            break
        add(
            with_standard_controls(
                seed,
                batch=batch,
                ubatch=ubatch,
                threads=threads,
                threads_batch=threads,
            )
        )

    # Spend any remaining budget on the full K/V product only after each
    # representative and high-value combined candidate has had a chance to
    # run. This preserves explicit KV search under small CLI budgets.
    if contract.kv_precision_search:
        family({**seed, "cache_type_k": k, "cache_type_v": v} for k in k_types for v in v_types)

    return candidates[:maximum]


@dataclass(frozen=True)
class SpeedMeasurement:
    latency_seconds: float
    ttft_seconds: float | None
    tokens: int
    failures: int
    tokens_per_second: float | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SpeedMeasurement":
        latency = _finite_number(value.get("latency_seconds"), default=0.0) or 0.0
        ttft = _finite_number(value.get("ttft_seconds"))
        tokens = max(0, int(value.get("tokens") or 0))
        tokens_per_second = _finite_number(value.get("tokens_per_second"))
        if tokens_per_second is None and latency > 0.0 and tokens > 0:
            tokens_per_second = tokens / latency
        return cls(
            latency_seconds=max(0.0, latency),
            ttft_seconds=None if ttft is None else max(0.0, ttft),
            tokens=tokens,
            failures=max(0, int(value.get("failures") or 0)),
            tokens_per_second=None if tokens_per_second is None else max(0.0, tokens_per_second),
        )

    def to_dict(self) -> JsonDict:
        return {
            "latency_seconds": self.latency_seconds,
            "ttft_seconds": self.ttft_seconds,
            "tokens": self.tokens,
            "failures": self.failures,
            "tokens_per_second": self.tokens_per_second,
        }


@dataclass(frozen=True)
class CostMeasurement:
    gpu_joules: float
    requests: int
    latency_seconds: float
    cpu_seconds: float
    failures: int

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CostMeasurement":
        return cls(
            gpu_joules=max(0.0, _finite_number(value.get("gpu_joules"), default=0.0) or 0.0),
            requests=max(0, int(value.get("requests") or 0)),
            latency_seconds=max(0.0, _finite_number(value.get("latency_seconds"), default=0.0) or 0.0),
            cpu_seconds=max(0.0, _finite_number(value.get("cpu_seconds"), default=0.0) or 0.0),
            failures=max(0, int(value.get("failures") or 0)),
        )

    @property
    def gpu_joules_per_request(self) -> float | None:
        return self.gpu_joules / self.requests if self.requests > 0 else None

    def to_dict(self) -> JsonDict:
        return {
            "gpu_joules": self.gpu_joules,
            "requests": self.requests,
            "latency_seconds": self.latency_seconds,
            "cpu_seconds": self.cpu_seconds,
            "failures": self.failures,
            "gpu_joules_per_request": self.gpu_joules_per_request,
        }


def _measurement_dict(value: Any) -> JsonDict:
    if isinstance(value, (SpeedMeasurement, CostMeasurement)):
        return value.to_dict()
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError("candidate measurement must be a mapping or tuning measurement")


def select_profile_winner(
    profile: str,
    *,
    baseline: SpeedMeasurement | CostMeasurement,
    candidates: Iterable[Mapping[str, Any]],
) -> JsonDict:
    """Select a feasible candidate whose measured improvement interval is positive."""

    profile = str(profile).strip().lower()
    if profile not in PROFILE_NAMES:
        raise ValueError("profile must be speed or cost")
    baseline_dict = _measurement_dict(baseline)
    baseline_failures = int(baseline_dict.get("failures") or 0)
    if baseline_failures:
        return {"outcome": "invalid_baseline", "selected": None, "rejected": []}

    feasible: list[JsonDict] = []
    rejected: list[JsonDict] = []
    for raw in candidates:
        measurement = _measurement_dict(raw.get("measurement"))
        interval = raw.get("improvement_interval")
        reason: str | None = None
        if not isinstance(interval, (tuple, list)) or len(interval) != 2:
            reason = "missing improvement interval"
        elif float(interval[0]) <= 0.0:
            reason = "improvement interval includes no improvement"
        elif int(measurement.get("failures") or 0) > 0:
            reason = "candidate produced failures"

        if profile == "speed":
            baseline_latency = float(baseline_dict.get("latency_seconds") or 0.0)
            candidate_latency = float(measurement.get("latency_seconds") or 0.0)
            baseline_tokens_per_second = float(
                baseline_dict.get("tokens_per_second")
                or ((baseline_dict.get("tokens") or 0) / baseline_latency if baseline_latency > 0 else 0.0)
            )
            candidate_tokens_per_second = float(
                measurement.get("tokens_per_second")
                or ((measurement.get("tokens") or 0) / candidate_latency if candidate_latency > 0 else 0.0)
            )
            if baseline_latency <= 0.0 or candidate_latency <= 0.0:
                reason = reason or "missing latency measurement"
            if baseline_tokens_per_second <= 0.0 or candidate_tokens_per_second <= 0.0:
                reason = reason or "missing throughput measurement"
            if candidate_latency > baseline_latency * 1.05:
                reason = reason or "latency regression exceeds the profile guard"
            objective = (
                candidate_tokens_per_second / baseline_tokens_per_second - 1.0
                if baseline_tokens_per_second > 0.0
                else -math.inf
            )
        else:
            baseline_requests = int(baseline_dict.get("requests") or 0)
            candidate_requests = int(measurement.get("requests") or 0)
            baseline_energy = float(baseline_dict.get("gpu_joules") or 0.0)
            candidate_energy = float(measurement.get("gpu_joules") or 0.0)
            baseline_cpu = float(baseline_dict.get("cpu_seconds") or 0.0)
            candidate_cpu = float(measurement.get("cpu_seconds") or 0.0)
            if baseline_requests <= 0 or candidate_requests <= 0:
                reason = reason or "missing request count"
            if candidate_cpu > baseline_cpu * 1.10 and baseline_cpu > 0.0:
                reason = reason or "CPU work increase exceeds the cost guard"
            baseline_latency = float(baseline_dict.get("latency_seconds") or 0.0)
            candidate_latency = float(measurement.get("latency_seconds") or 0.0)
            if baseline_latency > 0.0 and candidate_latency > baseline_latency * 1.10:
                reason = reason or "latency regression exceeds the cost guard"
            baseline_per_request = baseline_energy / baseline_requests if baseline_requests else math.inf
            candidate_per_request = candidate_energy / candidate_requests if candidate_requests else math.inf
            objective = 1.0 - candidate_per_request / baseline_per_request if baseline_per_request else -math.inf

        item = {
            "config": dict(raw.get("config") or {}),
            "measurement": measurement,
            "improvement_interval": [float(interval[0]), float(interval[1])] if isinstance(interval, (tuple, list)) and len(interval) == 2 else None,
            "objective_improvement": objective,
        }
        if reason:
            item["rejection_reason"] = reason
            rejected.append(item)
        else:
            feasible.append(item)

    feasible.sort(key=lambda item: float(item["objective_improvement"]), reverse=True)
    selected = feasible[0] if feasible else None
    return {
        "outcome": "improved" if selected else "no_improvement",
        "selected": selected,
        "rejected": rejected,
        "feasible": feasible,
    }


class TuningStore:
    """Small SQLite journal for tuning runs and progress events."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS tuning_runs ("
                "run_id TEXT PRIMARY KEY, created REAL NOT NULL, payload TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS tuning_events ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, created REAL NOT NULL, payload TEXT NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path))
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def create_run(self, payload: Mapping[str, Any]) -> JsonDict:
        run_id = str(payload.get("run_id") or f"tune-{uuid.uuid4().hex[:20]}")
        now = time.time()
        record = {"run_id": run_id, "status": "QUEUED", "created": now, **dict(payload)}
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO tuning_runs(run_id, created, payload) VALUES(?, ?, ?)",
                (run_id, now, json.dumps(record, sort_keys=True, default=str)),
            )
        return record

    def update_run(self, run_id: str, updates: Mapping[str, Any]) -> JsonDict:
        with self._connection() as connection:
            row = connection.execute("SELECT payload FROM tuning_runs WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(f"unknown tuning run: {run_id}")
            record = json.loads(str(row[0]))
            record.update(dict(updates))
            record["updated"] = time.time()
            connection.execute(
                "UPDATE tuning_runs SET payload = ? WHERE run_id = ?",
                (json.dumps(record, sort_keys=True, default=str), run_id),
            )
        return record

    def append_event(self, run_id: str, event: Mapping[str, Any]) -> JsonDict:
        now = time.time()
        record = {"event_id": uuid.uuid4().hex, "created": now, **dict(event)}
        with self._connection() as connection:
            if connection.execute("SELECT 1 FROM tuning_runs WHERE run_id = ?", (run_id,)).fetchone() is None:
                raise KeyError(f"unknown tuning run: {run_id}")
            connection.execute(
                "INSERT INTO tuning_events(run_id, created, payload) VALUES(?, ?, ?)",
                (run_id, now, json.dumps(record, sort_keys=True, default=str)),
            )
        return record

    def get_run(self, run_id: str) -> JsonDict:
        with self._connection() as connection:
            row = connection.execute("SELECT payload FROM tuning_runs WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(f"unknown tuning run: {run_id}")
            record = json.loads(str(row[0]))
            events = connection.execute(
                "SELECT payload FROM tuning_events WHERE run_id = ? ORDER BY id ASC", (run_id,)
            ).fetchall()
        record["events"] = [json.loads(str(row[0])) for row in events]
        return record

    def list_runs(self, *, limit: int = 50) -> list[JsonDict]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload FROM tuning_runs ORDER BY created DESC LIMIT ?", (int(limit),)
            ).fetchall()
        return [json.loads(str(row[0])) for row in rows]


__all__ = [
    "CostMeasurement",
    "GpuEnergySampler",
    "SpeedMeasurement",
    "TuningContract",
    "TuningStore",
    "candidate_is_allowed",
    "generate_llama_candidates",
    "select_profile_winner",
]
