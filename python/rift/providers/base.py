"""Provider contracts for external LLM serving backends."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
import signal
import time
from typing import Any, Protocol

from ..adapters.contracts import ADAPTER_API_VERSION, AdapterManifest


JsonDict = dict[str, Any]


@dataclass(frozen=True)
class ProviderCommand:
    args: list[str]
    display: str
    env: dict[str, str] = field(default_factory=dict)


class BackendProvider(Protocol):
    name: str

    def detect(self, *, search_root: str | None = None) -> JsonDict:
        ...

    def install_plan(self) -> JsonDict:
        ...

    def install(
        self,
        *,
        target_dir: str,
        variant: str = "auto",
        force: bool = False,
    ) -> JsonDict:
        ...

    def model_fit(self, *, model: JsonDict, hardware: JsonDict) -> JsonDict:
        ...

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
        ...

    def health(self, *, base_url: str, timeout_seconds: float = 2.0) -> JsonDict:
        ...

    def readiness(self, *, base_url: str, timeout_seconds: float = 2.0) -> JsonDict:
        ...

    def benchmark(
        self,
        *,
        base_url: str,
        prompt: str,
        max_tokens: int,
        timeout_seconds: float = 60.0,
    ) -> JsonDict:
        ...

    def tune_candidates(self, *, launch_plan: JsonDict, hardware: JsonDict) -> list[JsonDict]:
        ...

    def launch(self, launch_plan: JsonDict, *, log_path: str | None = None) -> JsonDict:
        ...

    def stop(self, *, pid: int) -> JsonDict:
        ...

    def recover(self, launch_plan: JsonDict, *, log_path: str | None = None) -> JsonDict:
        ...

    def capabilities(self) -> JsonDict:
        ...


_CAPABILITIES: dict[str, JsonDict] = {
    "llama.cpp": {
        "status": "verified_local",
        "operating_systems": ["windows", "linux", "macos"],
        "accelerators": ["cpu", "cuda", "metal", "vulkan"],
        "formats": ["gguf"],
        "multi_gpu": True,
        "api": "openai_compatible",
        "streaming": True,
        "tuning_knobs": ["context_length", "gpu_layers", "batch", "ubatch", "threads", "mmap", "mlock"],
    },
    "vllm": {
        "status": "implemented_platform_gate_pending",
        "operating_systems": ["linux", "wsl2"],
        "accelerators": ["cuda", "rocm", "cpu_limited"],
        "formats": ["safetensors", "awq", "gptq", "fp16", "bf16"],
        "multi_gpu": True,
        "api": "openai_compatible",
        "streaming": True,
        "tuning_knobs": ["gpu_memory_utilization", "max_num_seqs", "max_num_batched_tokens"],
    },
    "sglang": {
        "status": "implemented_platform_gate_pending",
        "operating_systems": ["linux", "wsl2"],
        "accelerators": ["cuda"],
        "formats": ["safetensors", "awq", "gptq", "fp16", "bf16"],
        "multi_gpu": True,
        "api": "openai_compatible",
        "streaming": True,
        "tuning_knobs": ["mem_fraction_static", "tp_size", "chunked_prefill_size"],
    },
    "lmcache_aware": {
        "status": "experimental_overlay",
        "operating_systems": ["linux", "wsl2"],
        "accelerators": ["cuda"],
        "formats": ["safetensors", "awq", "gptq", "fp16", "bf16"],
        "multi_gpu": True,
        "api": "openai_compatible",
        "streaming": True,
        "overlay": True,
        "tuning_knobs": ["local_cpu", "max_local_cpu_size", "remote_url"],
    },
}


class ProviderLifecycleMixin:
    """Lifecycle operations shared by external OpenAI-compatible providers."""

    name: str

    def probe(self, *, search_root: str | None = None) -> JsonDict:
        return self.detect(search_root=search_root)

    def evaluate_fit(
        self,
        *,
        artifact: JsonDict,
        hardware: JsonDict,
        workload: str = "chat",
    ) -> JsonDict:
        del workload
        model = {
            **dict(artifact),
            "size": artifact.get("total_bytes") or artifact.get("size"),
            "estimated_download_bytes": artifact.get("total_bytes") or artifact.get("estimated_download_bytes"),
        }
        return self.model_fit(model=model, hardware=hardware)

    def build_launch_spec(self, **kwargs: Any) -> JsonDict:
        return self.plan_launch(**kwargs)

    def tuning_space(self, *, launch_plan: JsonDict, hardware: JsonDict) -> list[JsonDict]:
        return self.tune_candidates(launch_plan=launch_plan, hardware=hardware)

    def capabilities(self) -> JsonDict:
        manifest = getattr(self, "manifest", None)
        if isinstance(manifest, AdapterManifest):
            values = manifest.capability.to_dict()
            values.update(
                {
                    "status": manifest.evidence_status,
                    "adapter_id": manifest.adapter_id,
                    "adapter_version": manifest.adapter_version,
                    "adapter_api_version": manifest.adapter_api_version,
                    "upstream_project": manifest.upstream_project,
                    "manifest": manifest.to_dict(),
                }
            )
        else:
            values = dict(_CAPABILITIES.get(self.name, {}))
        values.setdefault("status", "experimental")
        values["backend"] = self.name
        return values

    def readiness(self, *, base_url: str, timeout_seconds: float = 2.0) -> JsonDict:
        result = dict(self.health(base_url=base_url, timeout_seconds=timeout_seconds))
        result["ready"] = bool(result.get("healthy"))
        result["check"] = "readiness"
        return result

    def stop(self, *, pid: int) -> JsonDict:
        if int(pid) <= 0:
            raise ValueError("pid must be positive")
        try:
            os.kill(int(pid), signal.SIGTERM)
        except ProcessLookupError:
            return {"backend": self.name, "pid": int(pid), "stopped": True, "already_stopped": True}
        except OSError as exc:
            return {"backend": self.name, "pid": int(pid), "stopped": False, "error": str(exc)}
        return {
            "backend": self.name,
            "pid": int(pid),
            "stopped": True,
            "requested_unix_seconds": time.time(),
        }

    def recover(self, launch_plan: JsonDict, *, log_path: str | None = None) -> JsonDict:
        result = dict(self.launch(launch_plan, log_path=log_path))
        result["recovery"] = True
        return result


def provider_lifecycle_gate(provider: Any) -> JsonDict:
    required = (
        "probe",
        "capabilities",
        "install_plan",
        "install",
        "evaluate_fit",
        "build_launch_spec",
        "launch",
        "health",
        "benchmark",
        "tuning_space",
        "stop",
        "recover",
    )
    missing = [name for name in required if not callable(getattr(provider, name, None))]
    capabilities = provider.capabilities() if not missing else {}
    manifest = getattr(provider, "manifest", None)
    manifest_valid = isinstance(manifest, AdapterManifest)
    api_compatible = bool(
        manifest_valid
        and manifest.adapter_api_version.split(".", 1)[0]
        == ADAPTER_API_VERSION.split(".", 1)[0]
    )
    advertised = str(
        manifest.evidence_status if manifest_valid else capabilities.get("status") or "experimental"
    )
    return {
        "backend": getattr(provider, "name", "unknown"),
        "contract_complete": not missing,
        "missing_methods": missing,
        "capabilities": capabilities,
        "adapter_manifest_valid": manifest_valid,
        "adapter_api_version": manifest.adapter_api_version if manifest_valid else None,
        "host_adapter_api_version": ADAPTER_API_VERSION,
        "adapter_api_compatible": api_compatible,
        "advertised_status": advertised,
        "production_ready_claim": advertised in ("verified_local", "production", "verified_physical"),
        "gate_passed": not missing and bool(capabilities) and manifest_valid and api_compatible,
        "note": "Contract completeness does not replace real backend/platform acceptance testing.",
    }
