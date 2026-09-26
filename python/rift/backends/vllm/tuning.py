"""vLLM-owned tuning policy and parameter descriptors."""
from __future__ import annotations

from typing import Any

from ...tuning_base import BackendTuningAdapter, Parameter, accelerator_family, canonical_hash


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


class VllmTuningAdapter(BackendTuningAdapter):
    backend = "vllm"

    def probe(self, deployment):
        plan = deployment.get("launch_plan", deployment)
        tuning = plan.get("tuning") or {}
        family = tuning.get("accelerator_family", "cuda")
        probe_fn = getattr(self.provider, "probe_tuning_runtime", None)
        feature_probe = (
            probe_fn(plan)
            if callable(probe_fn)
            else self.provider.detect(search_root=tuning.get("search_root")).get("runtime_feature_probe", {})
        )
        flags = feature_probe.get("flags") or {}
        parameters = [p.to_dict() for p in VLLM_PARAMETERS if family in p.platforms and flags.get(p.flag) is True]
        if family == "cpu" and feature_probe.get("probed"):
            parameters.extend(
                p.to_dict()
                for p in VLLM_PARAMETERS
                if family in p.platforms and p.flag.startswith("VLLM_") and p.to_dict() not in parameters
            )
        return {
            "schema_version": 1,
            "backend": self.backend,
            "profiles": ["speed", "cost"],
            "parameters": parameters,
            "groups": sorted({p["group"] for p in parameters}),
            "runtime": {"runtime_mode": tuning.get("runtime_mode"), "runtime_feature_probe": feature_probe},
            "qualification": "unqualified",
            "accelerator_family": family,
        }

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

        def add(**changes: Any):
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
        if contract.kv_precision_search and baseline.get("kv_scales_verified") is True:
            for dtype in ("auto", "fp8_e4m3"):
                add(kv_cache_dtype=dtype)
        for value in (tokens, tokens * 2):
            add(max_num_batched_tokens=value, max_num_seqs=contract.concurrency, enable_chunked_prefill=True)
        return result


def create_tuning_adapter(provider):
    return VllmTuningAdapter(provider)


__all__ = ["VLLM_PARAMETERS", "VllmTuningAdapter", "create_tuning_adapter"]
