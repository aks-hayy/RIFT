"""LMCache-aware vLLM overlay provider for RIFT."""

from __future__ import annotations

from pathlib import Path
import json
import os
from typing import Any

from ..adapters.contracts import ADAPTER_API_VERSION, AdapterManifest, BackendCapability
from .base import ProviderLifecycleMixin
from .openai_backend import (
    JsonDict,
    install_python_packages_isolated,
    isolated_module_detection,
    launch_process,
    module_detection,
    openai_benchmark,
    openai_health,
    python_unsupported_on_windows,
    quote_command,
)
from .vllm import VllmProvider


class LMCacheAwareProvider(ProviderLifecycleMixin):
    name = "lmcache_aware"
    manifest = AdapterManifest(
        adapter_id=name,
        display_name="LMCache overlay",
        upstream_project="LMCache/LMCache",
        adapter_version="1.0.0",
        adapter_api_version=ADAPTER_API_VERSION,
        kind="overlay",
        capability=BackendCapability(
            tasks=("chat", "completion", "prefix-heavy", "long-context"),
            formats=("safetensors", "awq", "gptq", "fp8"),
            quantizations=("awq", "gptq", "fp8", "fp16", "bf16"),
            operating_systems=("linux", "wsl2", "container"),
            accelerators=("cuda",),
            installation_methods=("isolated-python", "container", "wsl2"),
            endpoints=("openai",),
            multi_gpu=True,
        ),
        evidence_status="experimental_overlay",
        homepage="https://github.com/LMCache/LMCache",
        description="Optional KV-cache optimization overlay for a vLLM deployment.",
    )

    def __init__(self) -> None:
        self.vllm = VllmProvider()

    def detect(self, *, search_root: str | None = None) -> JsonDict:
        isolated = isolated_module_detection(search_root, "lmcache")
        lmcache = isolated if isolated.get("available") else module_detection("lmcache")
        vllm = self.vllm.detect(search_root=search_root)
        available = bool(lmcache.get("available") and vllm.get("available"))
        return {
            "backend": self.name,
            "available": available,
            "executable": vllm.get("executable") if vllm.get("available") else None,
            "source": "vllm+lmcache" if available else None,
            "module": {"lmcache": lmcache, "vllm": vllm.get("module")},
            "base_backend": "vllm",
            "version": lmcache.get("version"),
            "license": "Apache-2.0",
            "platform_notes": [
                "LMCache-aware mode is an overlay around vLLM with a KV transfer connector.",
                "Use it for long-context or prefix-reuse workloads after baseline vLLM is healthy.",
            ],
        }

    def install_plan(self) -> JsonDict:
        return {
            "backend": self.name,
            "requires_permission": True,
            "license": "Apache-2.0",
            "official_sources": [
                "https://docs.lmcache.ai/getting_started/quickstart/offload_kv_cache.html",
                "https://github.com/LMCache/LMCache",
                "https://docs.vllm.ai/en/latest/serving/online_serving/openai_compatible_server/",
            ],
            "recommended": {
                "linux_cuda": "python -m pip install vllm lmcache",
                "windows": "Use WSL2/Linux or Docker; RIFT will not silently install LMCache/vLLM on native Windows.",
            },
            "notes": [
                "The launch plan writes an LMCache config file and passes vLLM --kv-transfer-config.",
                "LMCache is only useful after vLLM itself is installable and healthy.",
            ],
        }

    def install(self, *, target_dir: str, variant: str = "auto", force: bool = False) -> JsonDict:
        del variant
        existing = self.detect(search_root=target_dir)
        if existing.get("available"):
            return {"backend": self.name, "installed": True, "changed": False, "detection": existing}
        unsupported = python_unsupported_on_windows(self.name)
        if unsupported:
            unsupported["install_plan"] = self.install_plan()
            return unsupported
        result = install_python_packages_isolated(
            ["vllm", "lmcache"], target_dir=target_dir, force=force
        )
        detection = self.detect(search_root=target_dir)
        return {
            "backend": self.name,
            "installed": bool(detection.get("available")),
            "changed": result["returncode"] == 0,
            "installer": result,
            "detection": detection,
            "install_plan": self.install_plan(),
        }

    def model_fit(self, *, model: JsonDict, hardware: JsonDict) -> JsonDict:
        vllm_fit = self.vllm.model_fit(model=model, hardware=hardware)
        return {
            "backend": self.name,
            "fits": bool(vllm_fit.get("fits")),
            "reason": (
                "Use LMCache-aware mode when prefix reuse or long-context KV pressure justifies CPU KV offload."
                if vllm_fit.get("fits")
                else vllm_fit.get("reason")
            ),
            "base_backend_fit": vllm_fit,
        }

    def plan_launch(
        self,
        *,
        model_path: str,
        host: str,
        port: int,
        context_length: int,
        concurrency: int,
        hardware: JsonDict,
        tuning: JsonDict | None = None,
    ) -> JsonDict:
        tuning = tuning or {}
        base = self.vllm.plan_launch(
            model_path=model_path,
            host=host,
            port=port,
            context_length=context_length,
            concurrency=concurrency,
            hardware=hardware,
            tuning=tuning,
        )
        args = list(base["command"])
        args.extend(
            [
                "--kv-transfer-config",
                json.dumps({"kv_connector": "LMCacheConnectorV1", "kv_role": "kv_both"}, separators=(",", ":")),
            ]
        )
        max_cpu_size = float(tuning.get("lmcache_max_local_cpu_size", self._default_cpu_cache_gb(hardware)))
        chunk_size = int(tuning.get("lmcache_chunk_size", 256))
        config_path = str(tuning.get("lmcache_config_path") or Path(".rift") / "backends" / self.name / "lmcache_config.yaml")
        config_text = f"chunk_size: {chunk_size}\nlocal_cpu: true\nmax_local_cpu_size: {max_cpu_size:g}\n"
        env = dict(base.get("env") or {})
        env["LMCACHE_CONFIG_FILE"] = config_path
        return {
            **base,
            "backend": self.name,
            "command": args,
            "display": quote_command(args),
            "env": env,
            "lmcache_config": {
                "path": config_path,
                "content": config_text,
                "chunk_size": chunk_size,
                "local_cpu": True,
                "max_local_cpu_size": max_cpu_size,
            },
            "tuning": {
                **dict(base.get("tuning") or {}),
                "lmcache_chunk_size": chunk_size,
                "lmcache_max_local_cpu_size": max_cpu_size,
                "lmcache_config_path": config_path,
            },
        }

    def _default_cpu_cache_gb(self, hardware: JsonDict) -> float:
        total_ram = int(hardware.get("total_host_ram_bytes") or 0)
        if not total_ram:
            return 2.0
        return max(1.0, min(6.0, total_ram / 1024**3 * 0.25))

    def launch(self, launch_plan: JsonDict, *, log_path: str | None = None) -> JsonDict:
        config = launch_plan.get("lmcache_config") or {}
        path = config.get("path")
        content = config.get("content")
        if path and content:
            target = Path(str(path))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(content), encoding="utf-8")
        return launch_process(self.name, launch_plan, log_path=log_path)

    def health(self, *, base_url: str, timeout_seconds: float = 2.0) -> JsonDict:
        return openai_health(self.name, base_url=base_url, timeout_seconds=timeout_seconds)

    def benchmark(
        self,
        *,
        base_url: str,
        prompt: str,
        max_tokens: int,
        timeout_seconds: float = 60.0,
    ) -> JsonDict:
        result = openai_benchmark(
            self.name,
            base_url=base_url,
            prompt=prompt,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
        )
        result["lmcache_note"] = "Benchmark is OpenAI-compatible; cache hit metrics require backend logs/metrics integration."
        return result

    def tune_candidates(self, *, launch_plan: JsonDict, hardware: JsonDict) -> list[JsonDict]:
        baseline = dict(launch_plan.get("tuning") or {})
        base_candidates = self.vllm.tune_candidates(launch_plan=launch_plan, hardware=hardware)[:4]
        candidates = []
        for candidate in base_candidates:
            merged = dict(baseline)
            merged.update(candidate)
            candidates.append(merged)
        for chunk in (128, 256, 512):
            candidate = dict(baseline)
            candidate["lmcache_chunk_size"] = chunk
            candidates.append(candidate)
        for size in (1.0, self._default_cpu_cache_gb(hardware), 6.0):
            candidate = dict(baseline)
            candidate["lmcache_max_local_cpu_size"] = float(size)
            candidates.append(candidate)
        return self._unique(candidates)

    def _unique(self, candidates: list[JsonDict]) -> list[JsonDict]:
        unique: list[JsonDict] = []
        seen = set()
        for candidate in candidates:
            key = tuple(sorted(candidate.items()))
            if key not in seen:
                seen.add(key)
                unique.append(candidate)
        return unique
