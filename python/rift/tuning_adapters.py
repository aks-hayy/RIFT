"""Backend-specific search policies used by the shared tuning coordinator.

Adapters propose configurations; the coordinator owns measurements and promotion.
No adapter may change the identity of a deployed service.
"""
from __future__ import annotations

import copy
import hashlib
import inspect
import json
import math
from dataclasses import dataclass
from typing import Any, Mapping


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def accelerator_family(hardware: Mapping[str, Any]) -> str:
    explicit = hardware.get("accelerator_family")
    if explicit in {"cuda", "rocm", "xpu", "cpu"}:
        return str(explicit)
    for family, names in (("cuda", ("cuda_available",)), ("rocm", ("rocm_available", "hip_available")), ("xpu", ("xpu_available",))):
        if any(hardware.get(name) is True for name in names):
            return family
    return "cpu"


@dataclass(frozen=True)
class Parameter:
    name: str
    flag: str
    group: str
    kind: str
    values: tuple[Any, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    platforms: tuple[str, ...] = ("cuda", "rocm", "xpu", "cpu")

    def validate(self, value: Any) -> None:
        valid = {"boolean": lambda: type(value) is bool,
                 "integer": lambda: type(value) is int,
                 "number": lambda: type(value) in (int, float) and math.isfinite(value),
                 "string": lambda: isinstance(value, str),
                 "object": lambda: isinstance(value, dict)}[self.kind]()
        if not valid or (self.values and value not in self.values):
            raise ValueError(f"invalid {self.name}: {value!r}")
        if self.minimum is not None and value < self.minimum:
            raise ValueError(f"{self.name} must be >= {self.minimum}")
        if self.maximum is not None and value > self.maximum:
            raise ValueError(f"{self.name} must be <= {self.maximum}")

    def to_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "restart_required": True}


GPU = ("cuda", "rocm", "xpu")
VLLM_PARAMETERS = (
    Parameter("max_num_batched_tokens", "--max-num-batched-tokens", "scheduler", "integer", minimum=1),
    Parameter("max_num_seqs", "--max-num-seqs", "scheduler", "integer", minimum=1),
    Parameter("enable_chunked_prefill", "--enable-chunked-prefill", "scheduler", "boolean"),
    Parameter("gpu_memory_utilization", "--gpu-memory-utilization", "memory", "number", minimum=0.05, maximum=0.95, platforms=GPU),
    Parameter("kv_cache_memory_bytes", "--kv-cache-memory-bytes", "memory", "integer", minimum=1, platforms=GPU),
    Parameter("enable_prefix_caching", "--enable-prefix-caching", "prefix_cache", "boolean"),
    Parameter("kv_cache_dtype", "--kv-cache-dtype", "kv_precision", "string", ("auto", "fp8", "fp8_e4m3", "fp8_e5m2"), platforms=GPU),
    Parameter("calculate_kv_scales", "--calculate-kv-scales", "kv_precision", "boolean", platforms=GPU),
    Parameter("enforce_eager", "--enforce-eager", "execution", "boolean", platforms=GPU),
    Parameter("attention_backend", "--attention-backend", "attention", "string", platforms=GPU),
    Parameter("compilation_config", "--compilation-config", "execution", "object", platforms=GPU),
    Parameter("cpu_offload_gb", "--cpu-offload-gb", "offload", "number", minimum=0, platforms=GPU),
    Parameter("kv_offloading_size", "--kv-offloading-size", "offload", "number", minimum=0, platforms=GPU),
    Parameter("cpu_kvcache_space", "VLLM_CPU_KVCACHE_SPACE", "cpu", "integer", minimum=1, platforms=("cpu",)),
    Parameter("cpu_omp_threads_bind", "VLLM_CPU_OMP_THREADS_BIND", "cpu", "string", platforms=("cpu",)),
)


IDENTITY_KEYS = frozenset({
    "model_path", "model_sha256", "weight_quantization", "quantization", "dtype",
    "tokenizer", "tokenizer_revision", "revision", "chat_template", "tool_call_parser",
    "reasoning_parser", "generation_config", "tensor_parallel_size", "pipeline_parallel_size",
    "container_image", "executable", "runtime_mode", "command_style", "vllm_use_v1",
    "context_length", "concurrency", "device_ids", "accelerator_family", "speculative_config",
    "wsl_distribution", "wsl_python", "runtime_feature_probe",
})


class BackendTuningAdapter:
    backend = ""

    def __init__(self, provider: Any):
        self.provider = provider

    def resolve_configuration(self, deployment: Mapping[str, Any]) -> dict[str, Any]:
        plan = deployment.get("launch_plan", deployment)
        return copy.deepcopy({k: v for k, v in (plan.get("tuning") or {}).items() if v is not None})

    def validate(self, configuration, identity, requirements, resources):
        errors = []
        for key in IDENTITY_KEYS:
            if configuration.get(key) != identity.get(key):
                errors.append(f"locked deployment setting changed: {key}")
        return errors

    def build_launch_spec(self, **kwargs):
        return self.provider.plan_launch(**kwargs)

    def collect_diagnostics(self, runtime):
        return {"backend": self.backend, "qualification": "unqualified"}

    def explain(self, candidate, evidence):
        return {"changes": candidate, "measurement_ids": evidence.get("measurement_ids", []),
                "causal_attribution": "configuration-level; no ablation performed"}


class LlamaCppTuningAdapter(BackendTuningAdapter):
    backend = "llama.cpp"

    def probe(self, deployment):
        return {"backend": self.backend, "profiles": ["speed", "cost"],
                "qualification": "legacy_local_evidence; shared coordinator requires qualification",
                "groups": ["placement", "batching", "cpu", "kv_precision", "execution", "speculation"],
                "parameters": [], "schema_version": 1}

    def propose(self, *, launch_plan, hardware, contract):
        fn = getattr(self.provider, "tuning_space", self.provider.tune_candidates if hasattr(self.provider, "tune_candidates") else None)
        kwargs = {"launch_plan": launch_plan, "hardware": hardware}
        if "contract" in inspect.signature(fn).parameters:
            kwargs["contract"] = contract
        return fn(**kwargs)


class VllmTuningAdapter(BackendTuningAdapter):
    backend = "vllm"

    def probe(self, deployment):
        plan = deployment.get("launch_plan", deployment)
        tuning = plan.get("tuning") or {}
        family = tuning.get("accelerator_family", "cuda")
        probe_fn = getattr(self.provider, "probe_tuning_runtime", None)
        feature_probe = probe_fn(plan) if callable(probe_fn) else self.provider.detect(search_root=tuning.get("search_root")).get("runtime_feature_probe", {})
        flags = feature_probe.get("flags") or {}
        parameters = [p.to_dict() for p in VLLM_PARAMETERS if family in p.platforms and flags.get(p.flag) is True]
        if family == "cpu" and feature_probe.get("probed"):
            # CPU controls are environment variables, not CLI flags. Their
            # applicability is established by the selected vLLM CPU runtime;
            # they must never leak into GPU launches.
            parameters.extend(p.to_dict() for p in VLLM_PARAMETERS if family in p.platforms and p.flag.startswith("VLLM_") and p.to_dict() not in parameters)
        return {"schema_version": 1, "backend": self.backend, "profiles": ["speed", "cost"],
                "parameters": parameters, "groups": sorted({p["group"] for p in parameters}),
                "runtime": {"runtime_mode": tuning.get("runtime_mode"), "runtime_feature_probe": feature_probe},
                "qualification": "unqualified", "accelerator_family": family}

    def validate(self, configuration, identity, requirements, resources):
        errors = super().validate(configuration, identity, requirements, resources)
        family = configuration.get("accelerator_family") or accelerator_family(resources)
        for p in VLLM_PARAMETERS:
            if p.name in configuration:
                try:
                    p.validate(configuration[p.name])
                    if family not in p.platforms:
                        errors.append(f"{p.name} is not supported on {family}")
                except ValueError as exc:
                    errors.append(str(exc))
        if configuration.get("enable_chunked_prefill") is False:
            if configuration.get("max_num_batched_tokens", 0) < requirements.context_length:
                errors.append("without chunked prefill the token budget must cover context")
        if not requirements.kv_precision_search:
            for key in ("kv_cache_dtype", "calculate_kv_scales"):
                if configuration.get(key) != identity.get(key):
                    errors.append(f"KV precision search disabled: {key}")
        return errors

    def propose(self, *, launch_plan, hardware, contract):
        baseline = self.resolve_configuration(launch_plan)
        cap = self.probe(launch_plan)
        supported = {p["name"] for p in cap["parameters"]}
        flags = cap["runtime"]["runtime_feature_probe"].get("flags") or {}
        result = []
        seen = {canonical_hash(baseline)}
        def add(**changes):
            if not set(changes).issubset(supported):
                return
            for p in VLLM_PARAMETERS:
                if p.name in changes and changes[p.name] is False and flags.get("--no-" + p.flag[2:]) is not True:
                    return
            candidate = {**baseline, **changes}
            if self.validate(candidate, baseline, contract, hardware):
                return
            key = canonical_hash(candidate)
            if key not in seen:
                result.append(candidate)
                seen.add(key)
        tokens = int(baseline.get("max_num_batched_tokens", 1024))
        for value in sorted({max(128, tokens // 2), tokens, tokens * 2, tokens * 4}):
            add(max_num_batched_tokens=value)
        for value in sorted({1, contract.concurrency, contract.concurrency * 2}):
            add(max_num_seqs=value)
        for enabled in (True, False):
            add(enable_chunked_prefill=enabled)
            add(enable_prefix_caching=enabled)
            add(enforce_eager=enabled)
        if not baseline.get("kv_cache_memory_bytes"):
            util = float(baseline.get("gpu_memory_utilization", 0.78))
            for value in (max(0.1, util - 0.08), min(0.95, util + 0.04)):
                add(gpu_memory_utilization=round(value, 3))
        # Runtime support is necessary but not sufficient for KV precision changes.
        # Only use already recorded scaling assets; never calibrate/alter weights.
        if contract.kv_precision_search and baseline.get("kv_scales_verified") is True:
            for dtype in ("auto", "fp8_e4m3"):
                add(kv_cache_dtype=dtype)
        for value in (tokens, tokens * 2):
            add(max_num_batched_tokens=value, max_num_seqs=contract.concurrency, enable_chunked_prefill=True)
        return result


class TuningAdapterRegistry:
    """Small registry deliberately separate from serving-provider discovery."""

    def __init__(self) -> None:
        self._types: dict[str, type[BackendTuningAdapter]] = {}

    def register(self, backend: str, adapter_type: type[BackendTuningAdapter]) -> None:
        if not backend.strip() or not issubclass(adapter_type, BackendTuningAdapter):
            raise ValueError("a backend id and BackendTuningAdapter subclass are required")
        self._types[backend.strip()] = adapter_type

    def create(self, backend: str, provider: Any) -> BackendTuningAdapter | None:
        adapter_type = self._types.get(str(backend).strip())
        return adapter_type(provider) if adapter_type else None


_REGISTRY = TuningAdapterRegistry()
_REGISTRY.register("llama.cpp", LlamaCppTuningAdapter)
_REGISTRY.register("vllm", VllmTuningAdapter)


def tuning_adapter(backend: str, provider: Any) -> BackendTuningAdapter | None:
    return _REGISTRY.create(backend, provider)


def register_tuning_adapter(backend: str, adapter_type: type[BackendTuningAdapter]) -> None:
    _REGISTRY.register(backend, adapter_type)


__all__ = ["BackendTuningAdapter", "LlamaCppTuningAdapter", "VLLM_PARAMETERS", "VllmTuningAdapter", "register_tuning_adapter", "tuning_adapter"]
