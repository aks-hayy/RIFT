"""RIFT product-layer API for hardware-aware LLM deployment planning.

The control plane is usable without a native runtime. Optional native helpers
are capability providers, while serving remains adapter-managed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import statistics
from pathlib import Path
import time
from typing import Any, Iterable, Optional

try:
    from ._core import InferenceEngine
except ImportError:
    from ._fallback_core import ControlPlaneRuntime, InferenceEngine
else:
    # Keep the CPU control plane available when tests or embedders provide a
    # minimal native-module stub rather than a constructible CUDA runtime.
    from ._fallback_core import ControlPlaneRuntime
from .adapters.artifacts import artifact_adapter_host, source_from_candidate
from .adapters.contracts import ArtifactVariant, ModelIdentity, WorkloadProfile
from .benchmark_catalog import benchmark_site_catalog
from .evidence import EvidenceEngine
from .evidence_sources import JsonEvidenceSource
from .hf_hub import (
    DEFAULT_ALLOW_PATTERNS,
    DEFAULT_IGNORE_PATTERNS,
    HfHubClient,
    HubFile,
    disk_capacity,
    select_hub_files,
)
from .providers import backend_adapter_host
from .providers.llama_cpp import LlamaCppProvider
from .recommendations import RecommendationStore
from .runtime_paths import RiftPaths
from .system_profile import HardwareAnalyzer, simulate_hardware_profile, simulated_disk_capacity


_GIB = 1024**3


class RiftMode(str, Enum):
    """Deployment modes exposed by RIFT."""

    FAST = "FAST"
    BALANCED = "BALANCED"
    SURVIVAL = "SURVIVAL"
    REJECTED = "REJECTED"


class DeploymentStrategy(str, Enum):
    """High-level execution strategies selected by the planner."""

    GPU_RESIDENT = "GPU_RESIDENT"
    HYBRID_CACHE = "HYBRID_CACHE"
    STREAMING_SURVIVAL = "STREAMING_SURVIVAL"
    EXTERNAL_BACKEND = "EXTERNAL_BACKEND"
    REJECTED = "REJECTED"


class BackendKind(str, Enum):
    """Concrete serving backends RIFT can reason about."""

    RIFT_NATIVE = "rift_native"
    LLAMA_CPP = "llama.cpp"
    VLLM = "vllm"
    SGLANG = "sglang"
    LMCACHE_AWARE = "lmcache_aware"
    NONE = "none"


class RiftCompatibilityLevel(str, Enum):
    """Depth of RIFT support available for a model on this machine."""

    INSPECT_ONLY = "INSPECT_ONLY"
    PLAN_READY = "PLAN_READY"
    NATIVE_RUN_READY = "NATIVE_RUN_READY"
    UNSUPPORTED = "UNSUPPORTED"


class UsabilityVerdict(str, Enum):
    """User-facing verdicts for measured deployments."""

    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    USABLE = "USABLE"
    SLOW = "SLOW"
    NOT_RECOMMENDED = "NOT_RECOMMENDED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class RiftProductInfo:
    """Static product identity metadata."""

    name: str = "RIFT"
    full_name: str = "Runtime Inference Fitting Tool"
    tagline: str = "Fit local LLMs to the hardware you actually have."
    backend: str = "RIFT Python control plane with optional native backends"


class RiftEngine:
    """Hardware-aware deployment planner facade over optional capabilities.

    RIFT owns planning, reports, and serving orchestration. Native helpers are
    consulted only when installed and never required by the control plane.
    """

    def __init__(
        self,
        cuda_device_id: int = 0,
        root: str | Path | None = None,
        runtime_root: str | Path | None = None,
    ) -> None:
        self.root = Path(root).resolve() if root is not None else Path.cwd().resolve()
        self.runtime_root = (
            Path(runtime_root).resolve()
            if runtime_root is not None
            else RiftPaths.from_environment(cwd=self.root).home
            if root is None
            else self.root / ".rift"
        )
        # Some locked-down Windows workstations expose LOCALAPPDATA as a
        # read-only location (common in CI and packaged desktop sandboxes).
        # Keep the control plane usable by falling back to the checkout's
        # operator runtime only when the default location cannot be created.
        if runtime_root is None:
            try:
                self.runtime_root.mkdir(parents=True, exist_ok=True)
            except OSError:
                self.runtime_root = self.root / ".rift-runtime"
                self.runtime_root.mkdir(parents=True, exist_ok=True)
        if InferenceEngine is None:
            self.native = ControlPlaneRuntime()
        else:
            try:
                self.native = InferenceEngine(cuda_device_id=cuda_device_id)
            except TypeError:
                self.native = ControlPlaneRuntime()
        self.product = RiftProductInfo()
        self.backend_adapters = backend_adapter_host()
        self.artifact_adapters = artifact_adapter_host()
        self.evidence_engine = EvidenceEngine(root=self.root, data_root=self.runtime_root)
        # Backend probes can invoke container/Python version commands. Cache
        # them for one recommendation run so a large Hub candidate set does
        # not repeatedly pay process-start and timeout costs.
        self._backend_detection_cache: dict[str, dict[str, Any]] = {}

    def build_info(self) -> dict[str, Any]:
        info = dict(self.native.build_info())
        info.update(
            {
                "product": self.product.name,
                "product_full_name": self.product.full_name,
                "tagline": self.product.tagline,
                "backend": self.product.backend,
                "rift_phase": "M3",
            }
        )
        return info

    def hardware_profile(self, simulation: str | dict[str, Any] | None = None) -> dict[str, Any]:
        if simulation is not None:
            return simulate_hardware_profile(simulation)
        return HardwareAnalyzer(root=self.root, data_root=self.runtime_root).analyze(
            dict(self.native.hardware_profile())
        )

    def measure_h2d_bandwidth(
        self,
        *,
        sample_bytes: int = 64 * 1024**2,
        iterations: int = 8,
        warmup_iterations: int = 2,
    ) -> dict[str, Any]:
        return dict(
            self.native.measure_h2d_bandwidth(
                sample_bytes=sample_bytes,
                iterations=iterations,
                warmup_iterations=warmup_iterations,
            )
        )

    def backend_catalog(self) -> dict[str, Any]:
        """Return the backend adapters RIFT can plan around.

        This is intentionally an orchestration contract. RIFT does not claim a
        backend can run until the executable or Python package is actually
        visible on this workstation.
        """

        entries = []
        for kind in (
            BackendKind.LLAMA_CPP,
            BackendKind.VLLM,
            BackendKind.SGLANG,
            BackendKind.LMCACHE_AWARE,
            BackendKind.RIFT_NATIVE,
        ):
            entries.append(self._backend_descriptor(kind))
        return {
            "rift_product": self.product.name,
            "rift_phase": "M3",
            "backends": entries,
            "serving_adapter_registry": self.backend_adapters.diagnostics(),
            "serving_adapters": [
                adapter.manifest.to_dict()
                for _, adapter in sorted(self.backend_adapters.enabled().items())
            ],
            "compatibility_note": (
                "The enum-backed `backends` array is retained for one legacy release. "
                "New code must consume serving_adapters and adapter manifests."
            ),
        }

    def recommend_backend(
        self,
        *,
        model_path: Optional[str] = None,
        model_format: Optional[str] = None,
        model_family: Optional[str] = None,
        model_type: Optional[str] = None,
        quant_method: Optional[str] = None,
        estimated_model_bytes: int = 0,
        workload: str = "chat",
        context_length: int = 4096,
        concurrency: int = 1,
        prefix_reuse: str = "auto",
        native_generation_ready: bool = False,
        hardware: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Choose the practical serving backend for a model/hardware/workload pair."""

        if context_length <= 0:
            raise ValueError("context_length must be positive")
        if concurrency <= 0:
            raise ValueError("concurrency must be positive")

        hardware = hardware or self.hardware_profile()
        model_dir = Path(model_path) if model_path else None
        advice: dict[str, Any] = {}
        needs_local_advice = (
            model_format is None
            or model_family is None
            or model_type is None
            or quant_method is None
        )
        if needs_local_advice and model_dir is not None and model_dir.exists():
            advice = self.compatibility_advice(str(model_dir))
        if model_format is None:
            model_format = self._local_model_format(advice, model_dir)
        model_format = (model_format or "unknown").lower()
        family = (model_family or advice.get("family") or "UNKNOWN").upper()
        type_key = (model_type or advice.get("model_type") or "unknown").lower()
        quant_key = (quant_method or advice.get("quant_method") or "unknown").lower()
        workload_key = (workload or "chat").strip().lower()
        prefix_key = (prefix_reuse or "auto").strip().lower()
        prefix_heavy = self._is_prefix_heavy_workload(
            workload_key,
            context_length=context_length,
            concurrency=concurrency,
            prefix_reuse=prefix_key,
        )
        total_vram = int(hardware.get("total_vram_bytes") or 0)
        total_host = int(hardware.get("total_host_ram_bytes") or 0)
        cuda_available = bool(hardware.get("cuda_available", True))

        candidates: list[dict[str, Any]] = []

        def add_candidate(
            kind: BackendKind,
            score: float,
            reasons: list[str],
            warnings: Optional[list[str]] = None,
            *,
            base_backend: Optional[BackendKind] = None,
        ) -> None:
            descriptor = self._backend_descriptor(kind)
            install = self._backend_install_status(kind)
            candidates.append(
                {
                    "backend": kind.value,
                    "label": descriptor["label"],
                    "score": round(self._clamp01(score), 6),
                    "stable": descriptor["stable"],
                    "runtime_available": install["available"],
                    "detected_executable": install.get("detected_executable"),
                    "install_hint": descriptor["install_hint"],
                    "base_backend": base_backend.value if base_backend else None,
                    "reasons": reasons,
                    "warnings": warnings or [],
                }
            )

        if model_format == "gguf":
            score = 0.92
            if prefix_heavy:
                score -= 0.04
            add_candidate(
                BackendKind.LLAMA_CPP,
                score,
                [
                    "GGUF is the native deployment format for llama.cpp.",
                    "llama.cpp is the most reliable cross-platform backend for consumer laptops.",
                ],
                [
                    "LMCache-style prefix reuse is not available for llama.cpp in this RIFT adapter."
                ]
                if prefix_heavy
                else [],
            )
        elif model_format in ("gptq", "awq", "safetensors"):
            gpu_score = 0.72 if cuda_available else 0.28
            if quant_key in ("gptq", "awq") or model_format in ("gptq", "awq"):
                gpu_score += 0.08
            if total_vram and estimated_model_bytes and estimated_model_bytes > total_vram * 1.6:
                gpu_score -= 0.12
            add_candidate(
                BackendKind.VLLM,
                gpu_score,
                [
                    "vLLM is the best stable default for CUDA SafeTensors/AWQ/GPTQ serving.",
                    "It exposes an OpenAI-compatible API and handles batching better than a raw native path.",
                ],
                [] if cuda_available else ["CUDA was not visible in the hardware profile."],
            )
            sglang_score = gpu_score - 0.04
            if workload_key in ("agent", "rag", "tool", "coding") or prefix_heavy:
                sglang_score += 0.10
            add_candidate(
                BackendKind.SGLANG,
                sglang_score,
                [
                    "SGLang is strong for structured generation and prefix-heavy serving patterns.",
                    "It is a practical external backend while RIFT native adapters mature.",
                ],
            )
            if prefix_heavy:
                base = BackendKind.SGLANG if workload_key in ("agent", "rag", "tool") else BackendKind.VLLM
                add_candidate(
                    BackendKind.LMCACHE_AWARE,
                    0.91,
                    [
                        "The workload has enough context/concurrency/prefix reuse to benefit from KV reuse.",
                        "LMCache-aware mode keeps repeated prefixes from being recomputed by a supported backend.",
                    ],
                    base_backend=base,
                )
        else:
            add_candidate(
                BackendKind.NONE,
                0.0,
                ["RIFT cannot infer a safe backend without a known model format."],
                ["Run rift inspect or choose a GGUF/AWQ/GPTQ/SafeTensors checkpoint."],
            )

        if native_generation_ready and family == "LLAMA" and quant_key == "gptq":
            add_candidate(
                BackendKind.RIFT_NATIVE,
                0.52,
                [
                    "RIFT native survival path can execute this LLaMA GPTQ family for correctness checks.",
                    "This path is experimental and not the recommended fast serving backend yet.",
                ],
                ["Native RIFT generation is not yet the production serving path."],
            )

        if not candidates:
            add_candidate(
                BackendKind.NONE,
                0.0,
                ["No backend adapter matched this model/workload pair."],
                ["Use rift model recommend to select a better-fit model for this PC."],
            )

        candidates.sort(
            key=lambda item: (
                item["score"],
                1 if item["stable"] else 0,
                1 if item["runtime_available"] else 0,
            ),
            reverse=True,
        )
        selected = candidates[0]
        warnings = list(selected["warnings"])
        if not selected["runtime_available"] and selected["backend"] != BackendKind.NONE.value:
            warnings.append(
                f"{selected['label']} was selected as the best strategy, but it is not installed or not on PATH."
            )
        if model_format == "safetensors" and quant_key not in ("gptq", "awq", "unknown"):
            warnings.append("Dense SafeTensors may exceed this laptop's VRAM; prefer a quantized checkpoint.")
        if total_host and estimated_model_bytes and estimated_model_bytes > total_host:
            warnings.append("Estimated model files exceed total host RAM; avoid full-memory loading.")

        launch = self._backend_launch_template(
            BackendKind(selected["backend"]),
            model_path=str(model_dir) if model_dir is not None else "<model>",
            context_length=context_length,
            concurrency=concurrency,
        )
        return {
            "schema_version": 1,
            "rift_product": self.product.name,
            "rift_phase": "M3",
            "selected_backend": selected["backend"],
            "backend_label": selected["label"],
            "base_backend": selected.get("base_backend"),
            "runtime_available": selected["runtime_available"],
            "detected_executable": selected.get("detected_executable"),
            "install_hint": selected.get("install_hint"),
            "model_path": str(model_dir) if model_dir is not None else None,
            "model_format": model_format,
            "model_family": family,
            "model_type": type_key,
            "quant_method": quant_key,
            "workload": workload_key,
            "context_length": context_length,
            "concurrency": concurrency,
            "prefix_reuse": prefix_key,
            "prefix_heavy": prefix_heavy,
            "hardware_summary": {
                "cuda_available": cuda_available,
                "device_name": hardware.get("device_name"),
                "total_vram_bytes": total_vram,
                "total_host_ram_bytes": total_host,
            },
            "reasons": selected["reasons"],
            "warnings": warnings,
            "launch": launch,
            "alternatives": candidates[1:],
        }

    def inspect_model(self, model_path: str, **kwargs: Any) -> dict[str, Any]:
        native_inspect = getattr(self.native, "inspect_model", None)
        if callable(native_inspect):
            report = dict(native_inspect(model_path=model_path, **kwargs))
        else:
            # Test doubles and older optional native builds may expose the
            # module-level inspection function without attaching it to the
            # runtime object. Prefer that ABI before using the portable
            # control-plane inspection path.
            report = None
            try:
                native_module = importlib.import_module(f"{__package__}._core")

                module_inspect = getattr(native_module, "inspect_model", None)
                if callable(module_inspect):
                    try:
                        report = dict(module_inspect(model_path=model_path, **kwargs))
                    except (AttributeError, RuntimeError, NotImplementedError):
                        report = None
            except ImportError:
                report = None
            if report is None:
                report = self._portable_inspection_report(model_path)
        self._annotate_inspection(report)
        return report

    def _portable_inspection_report(self, model_path: str) -> dict[str, Any]:
        """Inspect an artifact without requiring the optional native module."""

        model_dir = Path(model_path).expanduser().resolve()
        advice = self.compatibility_advice(str(model_dir))
        files = (
            [model_dir]
            if model_dir.is_file()
            else [item for item in model_dir.rglob("*") if item.is_file()]
        )
        model_files = [
            item
            for item in files
            if item.suffix.lower() in {".gguf", ".safetensors", ".bin", ".pt", ".pth"}
        ]
        config: dict[str, Any] = {}
        config_path = model_dir.parent / "config.json" if model_dir.is_file() else model_dir / "config.json"
        if config_path.is_file():
            try:
                loaded = json.loads(config_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    config = loaded
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                config = {}
        config.update(
            {
                "model_type": advice.get("model_type") or config.get("model_type", "unknown"),
                "family": advice.get("family", "UNKNOWN"),
                "quantization": advice.get("quant_method", "unknown"),
            }
        )
        model_bytes = sum(int(item.stat().st_size) for item in model_files)
        max_file_bytes = max(
            (int(item.stat().st_size) for item in model_files),
            default=0,
        )
        return {
            "model_path": str(model_dir),
            "config": config,
            "topology": {
                "total_model_bytes": model_bytes,
                "w_max_bytes": max_file_bytes,
                "source": "portable_file_inventory",
            },
            "profile": {
                "supported": True,
                "source": "portable_control_plane",
                "hardware": self.hardware_profile(),
            },
            "execution_policy": {
                "supported": advice.get("support_level") != "UNSUPPORTED",
                "mode": "external_backend",
                "source": "backend_adapter_contract",
            },
            "generation_readiness": {
                "ready": False,
                "issues": [
                    "optional native model execution is unavailable; use a serving backend adapter"
                ],
                "output_head_mode": "EXTERNAL_BACKEND_REQUIRED",
            },
            "compatibility_advice": advice,
        }

    def load_model(self, model_path: str, **kwargs: Any) -> dict[str, Any]:
        report = dict(self.native.load_model(model_path=model_path, **kwargs))
        self._annotate_inspection(report)
        return report

    def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        result = dict(self.native.generate(prompt, **kwargs))
        result["rift_product"] = self.product.name
        result["rift_mode"] = RiftMode.SURVIVAL.value
        return result

    def decode_readiness(self) -> dict[str, Any]:
        build = self.build_info()
        native_phase = str(build.get("phase", ""))
        primitive_available = "R10" in native_phase or "decode-attention" in str(
            build.get("capability", "")
        )
        return {
            "cached_decode_attention_primitive": primitive_available,
            "full_layer_kv_cache_integration": False,
            "generate_uses_optimized_decode": False,
            "current_generate_path": "repeated_full_prefill",
            "fallback_path": "repeated_full_prefill",
            "ready_for_balanced_runtime": False,
            "next_steps": [
                "store real per-layer K/V tensors during prompt prefill",
                "read cached K/V tensors during one-token decode attention",
                "compare optimized decode logits against repeated-prefill logits",
                "promote BALANCED runtime only after parity checks pass",
            ],
        }

    def benchmark_model(
        self,
        model_path: str,
        *,
        max_read_bytes: int = 256 * 1024 * 1024,
        read_chunk_bytes: int = 4 * 1024 * 1024,
        **inspect_kwargs: Any,
    ) -> dict[str, Any]:
        if max_read_bytes <= 0:
            raise ValueError("max_read_bytes must be positive")
        if read_chunk_bytes <= 0:
            raise ValueError("read_chunk_bytes must be positive")

        model_dir = Path(model_path)
        inspect = self.inspect_model(str(model_dir), **inspect_kwargs)
        disk = self._benchmark_disk_read(model_dir, max_read_bytes, read_chunk_bytes)

        summary = inspect.get("rift_summary") or {}
        total_model_bytes = int(summary.get("total_model_bytes") or 0)
        w_max_bytes = int(summary.get("w_max_bytes") or 0)
        h2d: dict[str, Any] = {}
        for label, byte_count in (
            ("sample_read_bytes", int(disk["bytes_read"])),
            ("max_layer_bytes", w_max_bytes),
            ("total_model_bytes", total_model_bytes),
        ):
            if byte_count > 0:
                ns = int(self.native.estimate_h2d_transfer_ns(byte_count))
                h2d[label] = {
                    "bytes": byte_count,
                    "estimated_ns": ns,
                    "estimated_ms": ns / 1_000_000,
                }

        dry_run: dict[str, Any]
        try:
            dry_run = dict(self.native.benchmark_model(str(model_dir)))
        except Exception as exc:  # Existing backend benchmark is still estimate-only.
            dry_run = {"available": False, "error": str(exc)}
        else:
            dry_run["available"] = True

        return {
            "rift_product": self.product.name,
            "rift_phase": "R13",
            "model_path": str(model_dir),
            "compatibility_level": inspect.get("rift_compatibility_level"),
            "recommended_initial_mode": inspect.get("rift_recommended_initial_mode"),
            "hardware_fit_mode": inspect.get("rift_hardware_fit_mode"),
            "mode_analysis": inspect.get("rift_mode_analysis", {}),
            "decode_readiness": self.decode_readiness(),
            "model_summary": summary,
            "disk_read_benchmark": disk,
            "h2d_transfer_estimates": h2d,
            "backend_dry_run": dry_run,
            "notes": [
                "Disk benchmark is a local read sample and may be affected by OS file cache.",
                "H2D numbers are backend estimates until the native timed copy benchmark is added.",
            ],
        }

    def plan_model(
        self,
        model_path: str,
        *,
        output_path: Optional[str] = None,
        benchmark_read_bytes: int = 64 * 1024 * 1024,
        write: bool = True,
        workload: str = "chat",
        context_length: int = 4096,
        concurrency: int = 1,
        prefix_reuse: str = "auto",
        **inspect_kwargs: Any,
    ) -> dict[str, Any]:
        if context_length <= 0:
            raise ValueError("context_length must be positive")
        if concurrency <= 0:
            raise ValueError("concurrency must be positive")
        benchmark = self.benchmark_model(
            model_path,
            max_read_bytes=benchmark_read_bytes,
            **inspect_kwargs,
        )
        inspect_summary = benchmark["model_summary"]
        disk = benchmark["disk_read_benchmark"]
        total_model_bytes = int(inspect_summary.get("total_model_bytes") or 0)
        disk_gbps = float(disk.get("bandwidth_gbps") or 0.0)
        disk_floor_seconds = (
            total_model_bytes / (disk_gbps * 1_000_000_000)
            if total_model_bytes > 0 and disk_gbps > 0.0
            else None
        )
        survival_ready = (
            benchmark["compatibility_level"] == RiftCompatibilityLevel.NATIVE_RUN_READY.value
        )
        mode_analysis = benchmark.get("mode_analysis") or {}
        recommended = RiftMode(
            mode_analysis.get(
                "best_executable_mode",
                RiftMode.SURVIVAL.value if survival_ready else RiftMode.REJECTED.value,
            )
        )
        hardware = self.hardware_profile()
        compat = self.compatibility_advice(model_path)
        backend_decision = self.recommend_backend(
            model_path=model_path,
            model_format=self._local_model_format(compat, Path(model_path)),
            model_family=str(inspect_summary.get("family") or compat.get("family") or "UNKNOWN"),
            model_type=str(inspect_summary.get("model_type") or compat.get("model_type") or "unknown"),
            quant_method=str(inspect_summary.get("quantization") or compat.get("quant_method") or "unknown"),
            estimated_model_bytes=total_model_bytes,
            workload=workload,
            context_length=context_length,
            concurrency=concurrency,
            prefix_reuse=prefix_reuse,
            native_generation_ready=survival_ready,
            hardware=hardware,
        )
        kv_plan = self._kv_plan(
            inspect_summary,
            hardware=hardware,
            context_length=context_length,
            concurrency=concurrency,
            prefix_reuse=prefix_reuse,
        )
        serving_plan = self._serving_plan(
            model_path=model_path,
            backend_decision=backend_decision,
            kv_plan=kv_plan,
            workload=workload,
            context_length=context_length,
            concurrency=concurrency,
        )
        plan = {
            "schema_version": 2,
            "rift_product": self.product.name,
            "rift_phase": "M3",
            "created_unix_seconds": int(time.time()),
            "model_path": str(Path(model_path)),
            "model_fingerprint": self._model_fingerprint(Path(model_path)),
            "compatibility_level": benchmark["compatibility_level"],
            "recommended_mode": recommended.value,
            "hardware_fit_mode": mode_analysis.get("best_hardware_fit_mode", recommended.value),
            "best_executable_mode": recommended.value,
            "mode_analysis": mode_analysis,
            "decode_readiness": self.decode_readiness(),
            "balanced_cache_plan": mode_analysis.get("balanced_cache_plan", {}),
            "fallback_mode": RiftMode.REJECTED.value if recommended == RiftMode.REJECTED else RiftMode.REJECTED.value,
            "selected_backend": backend_decision["selected_backend"],
            "execution_backend": "rift_native_survival" if survival_ready else backend_decision["selected_backend"],
            "backend_decision": backend_decision,
            "serving_plan": serving_plan,
            "kv_plan": kv_plan,
            "expected": {
                "disk_stream_floor_seconds_per_full_pass": disk_floor_seconds,
                "rough_survival_tok_s_ceiling": (1.0 / disk_floor_seconds)
                if disk_floor_seconds and disk_floor_seconds > 0.0
                else None,
                "peak_vram_bytes": None,
                "peak_ram_bytes": None,
            },
            "model_summary": inspect_summary,
            "benchmark_summary": {
                "disk_read_gbps": disk_gbps,
                "disk_read_bytes": disk.get("bytes_read"),
                "h2d_transfer_estimates": benchmark.get("h2d_transfer_estimates", {}),
            },
            "candidate_modes": mode_analysis.get("candidate_modes", {}),
            "strategy": {
                "backend": backend_decision["selected_backend"],
                "weight_residency": "ssd_streamed",
                "kv_cache": "cached_attention_primitive_available_but_not_integrated"
                if self.decode_readiness()["cached_decode_attention_primitive"]
                else "minimal_tracking_currently_repeated_prefill",
                "lm_head": "dense_fp16_tiled_streaming",
                "prefetch": False,
                "decode_path": self.decode_readiness()["current_generate_path"],
                "serving_api": serving_plan.get("api_surface"),
                "launch_command": serving_plan.get("launch_command"),
                "execution_note": mode_analysis.get(
                    "execution_note",
                    "Correctness-first SURVIVAL mode; performance is not final.",
                ),
            },
            "invalidation": {
                "model_file_change": True,
                "hardware_change": True,
                "rift_schema_change": True,
            },
            "source_benchmark": benchmark,
        }
        if write:
            target = Path(output_path) if output_path else Path(model_path) / "model.riftplan"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")
            plan["plan_path"] = str(target)
        return plan

    def load_plan(self, plan_path: str) -> dict[str, Any]:
        return json.loads(Path(plan_path).read_text(encoding="utf-8"))

    def _backend_descriptor(self, kind: BackendKind) -> dict[str, Any]:
        descriptors = {
            BackendKind.LLAMA_CPP: {
                "backend": kind.value,
                "label": "llama.cpp",
                "stable": True,
                "formats": ["gguf"],
                "api_surface": ["OpenAI-compatible server", "llama.cpp native endpoints"],
                "install_hint": "Install llama.cpp and put llama-server on PATH, or set LLAMA_CPP_SERVER.",
            },
            BackendKind.VLLM: {
                "backend": kind.value,
                "label": "vLLM",
                "stable": True,
                "formats": ["awq", "gptq", "safetensors"],
                "api_surface": ["OpenAI-compatible server"],
                "install_hint": "Install vLLM in the active environment, then run python -m vllm.entrypoints.openai.api_server.",
            },
            BackendKind.SGLANG: {
                "backend": kind.value,
                "label": "SGLang",
                "stable": True,
                "formats": ["awq", "gptq", "safetensors"],
                "api_surface": ["OpenAI-compatible server", "SGLang runtime endpoints"],
                "install_hint": "Install sglang in the active environment, then run python -m sglang.launch_server.",
            },
            BackendKind.LMCACHE_AWARE: {
                "backend": kind.value,
                "label": "LMCache-aware mode",
                "stable": False,
                "formats": ["awq", "gptq", "safetensors"],
                "api_surface": ["OpenAI-compatible server through vLLM/SGLang"],
                "install_hint": "Install LMCache plus the selected base backend; use it for repeated-prefix workloads.",
            },
            BackendKind.RIFT_NATIVE: {
                "backend": kind.value,
                "label": "RIFT native survival",
                "stable": False,
                "formats": ["gptq"],
                "api_surface": ["RIFT local API", "OpenAI-compatible shim"],
                "install_hint": "Bundled with RIFT; use for correctness smoke tests until the production native runtime matures.",
            },
            BackendKind.NONE: {
                "backend": kind.value,
                "label": "No safe backend",
                "stable": True,
                "formats": [],
                "api_surface": [],
                "install_hint": "Choose a GGUF/AWQ/GPTQ/SafeTensors model or install a compatible backend.",
            },
        }
        descriptor = dict(descriptors[kind])
        descriptor["availability"] = self._backend_install_status(kind)
        return descriptor

    def _backend_install_status(self, kind: BackendKind) -> dict[str, Any]:
        if kind == BackendKind.RIFT_NATIVE:
            return {
                "available": True,
                "detected_executable": "bundled_python_extension",
                "checked": ["rift._core"],
            }
        if kind == BackendKind.NONE:
            return {"available": False, "detected_executable": None, "checked": []}

        checked: list[str] = []
        env_names = {
            BackendKind.LLAMA_CPP: ("LLAMA_CPP_SERVER", "LLAMA_SERVER", "LLAMA_CPP_BIN"),
            BackendKind.VLLM: ("VLLM_SERVER",),
            BackendKind.SGLANG: ("SGLANG_SERVER",),
            BackendKind.LMCACHE_AWARE: ("LMCACHE_SERVER",),
        }.get(kind, ())
        for name in env_names:
            value = os.environ.get(name)
            checked.append(f"${name}")
            if value and Path(value).exists():
                return {"available": True, "detected_executable": value, "checked": checked}

        executables = {
            BackendKind.LLAMA_CPP: ("llama-server", "llama-server.exe"),
            BackendKind.VLLM: ("vllm",),
            BackendKind.SGLANG: ("sglang",),
            BackendKind.LMCACHE_AWARE: ("lmcache",),
        }.get(kind, ())
        for executable in executables:
            checked.append(executable)
            found = shutil.which(executable)
            if found:
                return {"available": True, "detected_executable": found, "checked": checked}

        modules = {
            BackendKind.VLLM: ("vllm",),
            BackendKind.SGLANG: ("sglang",),
            BackendKind.LMCACHE_AWARE: ("lmcache", "lmcache_vllm"),
        }.get(kind, ())
        for module in modules:
            checked.append(f"python:{module}")
            if importlib.util.find_spec(module) is not None:
                return {"available": True, "detected_executable": f"python:{module}", "checked": checked}

        return {"available": False, "detected_executable": None, "checked": checked}

    def _local_model_format(self, advice: dict[str, Any], model_dir: Optional[Path]) -> str:
        files = advice.get("files") if isinstance(advice, dict) else {}
        if isinstance(files, dict) and files.get("gguf"):
            return "gguf"
        quant = str(advice.get("quant_method") or "").lower() if advice else ""
        if quant in ("gptq", "awq"):
            return quant
        if isinstance(files, dict) and int(files.get("safetensors_count") or 0) > 0:
            return "safetensors"
        if model_dir is not None and model_dir.is_dir():
            if any(path.suffix.lower() == ".gguf" for path in model_dir.iterdir() if path.is_file()):
                return "gguf"
            if any(path.suffix.lower() == ".safetensors" for path in model_dir.iterdir() if path.is_file()):
                return "safetensors"
        return "unknown"

    def _primary_model_artifact(self, model_path: str, model_format: str) -> str:
        model_dir = Path(model_path)
        if model_format == "gguf" and model_dir.is_dir():
            gguf = sorted(model_dir.glob("*.gguf"))
            if gguf:
                return str(gguf[0])
        return str(model_dir)

    def _is_prefix_heavy_workload(
        self,
        workload: str,
        *,
        context_length: int,
        concurrency: int,
        prefix_reuse: str,
    ) -> bool:
        if prefix_reuse in ("high", "heavy", "prefix-heavy", "yes", "true"):
            return True
        if prefix_reuse in ("low", "none", "false", "no"):
            return False
        if workload in ("agent", "rag", "retrieval", "tool", "batch"):
            return True
        return context_length >= 16384 or concurrency >= 4

    def _backend_launch_template(
        self,
        kind: BackendKind,
        *,
        model_path: str,
        context_length: int,
        concurrency: int,
    ) -> dict[str, Any]:
        artifact = self._primary_model_artifact(model_path, "gguf" if kind == BackendKind.LLAMA_CPP else "")
        if kind == BackendKind.LLAMA_CPP:
            command = (
                f"llama-server -m \"{artifact}\" --host 127.0.0.1 --port 11735 "
                f"--ctx-size {context_length} --n-gpu-layers 999"
            )
            return {
                "command": command,
                "api_base": "http://127.0.0.1:11735",
                "api_surface": "openai-compatible",
                "notes": ["Reduce --n-gpu-layers if llama.cpp reports VRAM pressure."],
            }
        if kind == BackendKind.VLLM:
            command = (
                f"python -m vllm.entrypoints.openai.api_server --model \"{model_path}\" "
                f"--host 127.0.0.1 --port 11735 --max-model-len {context_length}"
            )
            if concurrency > 1:
                command += f" --max-num-seqs {concurrency}"
            return {
                "command": command,
                "api_base": "http://127.0.0.1:11735/v1",
                "api_surface": "openai-compatible",
                "notes": ["Use quantized AWQ/GPTQ models on 8 GB VRAM."],
            }
        if kind == BackendKind.SGLANG:
            return {
                "command": (
                    f"python -m sglang.launch_server --model-path \"{model_path}\" "
                    f"--host 127.0.0.1 --port 11735 --context-length {context_length}"
                ),
                "api_base": "http://127.0.0.1:11735/v1",
                "api_surface": "openai-compatible",
                "notes": ["Best fit for structured/prefix-heavy workloads."],
            }
        if kind == BackendKind.LMCACHE_AWARE:
            return {
                "command": (
                    "set LMCACHE_CONFIG_FILE=<lmcache-config.yaml> && "
                    f"python -m vllm.entrypoints.openai.api_server --model \"{model_path}\" "
                    f"--host 127.0.0.1 --port 11735 --max-model-len {context_length}"
                ),
                "api_base": "http://127.0.0.1:11735/v1",
                "api_surface": "openai-compatible",
                "notes": ["Requires LMCache plus a supported base backend."],
            }
        if kind == BackendKind.RIFT_NATIVE:
            return {
                "command": f"rift serve --model \"{model_path}\" --host 127.0.0.1 --port 11735",
                "api_base": "http://127.0.0.1:11735/v1",
                "api_surface": "openai-compatible",
                "notes": ["Experimental correctness-first native path."],
            }
        return {
            "command": None,
            "api_base": None,
            "api_surface": "none",
            "notes": ["No safe launch command is available for this model."],
        }

    def _kv_plan(
        self,
        summary: dict[str, Any],
        *,
        hardware: dict[str, Any],
        context_length: int,
        concurrency: int,
        prefix_reuse: str,
    ) -> dict[str, Any]:
        layers = int(summary.get("layers") or 0)
        hidden = int(summary.get("hidden_size") or 0)
        total_vram = int(hardware.get("total_vram_bytes") or 0)
        free_vram = int(hardware.get("free_vram_bytes") or total_vram)
        if layers <= 0 or hidden <= 0:
            return {
                "available": False,
                "reason": "model config does not expose layer/hidden dimensions",
                "context_length": context_length,
                "concurrency": concurrency,
            }
        kv_bytes_per_token = 2 * layers * hidden * 2
        per_request = kv_bytes_per_token * context_length
        total = per_request * concurrency
        reserve = max(1 * _GIB, int(total_vram * 0.15)) if total_vram else 1 * _GIB
        kv_window = max(0, free_vram - reserve)
        safe_concurrency = max(1, kv_window // per_request) if per_request > 0 else 1
        ratio = total / kv_window if kv_window > 0 else 99.0
        if ratio <= 0.45:
            pressure = "LOW"
        elif ratio <= 0.85:
            pressure = "MEDIUM"
        else:
            pressure = "HIGH"
        return {
            "available": True,
            "context_length": context_length,
            "concurrency": concurrency,
            "prefix_reuse": prefix_reuse,
            "estimated_kv_bytes_per_token": kv_bytes_per_token,
            "estimated_kv_bytes_per_request": per_request,
            "estimated_total_kv_bytes": total,
            "estimated_total_kv_mib": round(total / (1024 * 1024), 3),
            "vram_kv_budget_bytes": kv_window,
            "max_safe_concurrency_estimate": int(safe_concurrency),
            "pressure": pressure,
            "notes": [
                "KV estimate uses FP16 K/V and full hidden-size fallback when grouped-query dimensions are unknown.",
                "Actual backend memory can differ due to paging, flash attention, and quantized KV settings.",
            ],
        }

    def _serving_plan(
        self,
        *,
        model_path: str,
        backend_decision: dict[str, Any],
        kv_plan: dict[str, Any],
        workload: str,
        context_length: int,
        concurrency: int,
    ) -> dict[str, Any]:
        launch = backend_decision.get("launch") or {}
        runtime_available = bool(backend_decision.get("runtime_available"))
        return {
            "backend": backend_decision.get("selected_backend"),
            "backend_label": backend_decision.get("backend_label"),
            "runnable_now": runtime_available,
            "model_path": model_path,
            "workload": workload,
            "context_length": context_length,
            "concurrency": concurrency,
            "api_surface": launch.get("api_surface"),
            "api_base": launch.get("api_base"),
            "launch_command": launch.get("command"),
            "install_hint": backend_decision.get("install_hint") if not runtime_available else None,
            "kv_pressure": kv_plan.get("pressure"),
            "max_safe_concurrency_estimate": kv_plan.get("max_safe_concurrency_estimate"),
            "decision_summary": {
                "reasons": backend_decision.get("reasons", []),
                "warnings": backend_decision.get("warnings", []),
            },
            "next_action": "launch_backend"
            if runtime_available
            else "install_backend_or_choose_another_recommendation",
        }

    def pull_model_from_hub(
        self,
        repo_id: str,
        *,
        revision: str = "main",
        output_dir: Optional[str] = None,
        allow_patterns: Optional[Iterable[str]] = None,
        ignore_patterns: Optional[Iterable[str]] = None,
        token: Optional[str] = None,
        dry_run: bool = False,
        max_bytes: Optional[int] = None,
        endpoint: str = "https://huggingface.co",
        inspect_after: bool = True,
    ) -> dict[str, Any]:
        repo_id = repo_id.strip()
        if not repo_id:
            raise ValueError("repo_id is required")
        max_bytes_value: Optional[int] = None
        if max_bytes is not None:
            max_bytes_value = int(max_bytes)
            if max_bytes_value <= 0:
                max_bytes_value = None
        client = HfHubClient(endpoint=endpoint, token=token)
        result = client.snapshot_download(
            repo_id,
            revision=revision,
            local_dir=output_dir,
            allow_patterns=allow_patterns,
            ignore_patterns=ignore_patterns,
            dry_run=dry_run,
            max_bytes=max_bytes_value,
        )
        result.update(
            {
                "rift_product": self.product.name,
                "rift_phase": "R18",
                "source": "huggingface_hub",
                "default_allow_patterns": list(DEFAULT_ALLOW_PATTERNS),
                "default_ignore_patterns": list(DEFAULT_IGNORE_PATTERNS),
            }
        )
        if dry_run:
            return result

        local_dir = str(Path(str(result["local_dir"])))
        try:
            result["compatibility_advice"] = self.compatibility_advice(local_dir)
        except Exception as exc:
            result["compatibility_error"] = str(exc)
        if inspect_after:
            try:
                result["inspection"] = self.inspect_model(local_dir)
            except Exception as exc:
                result["inspection_error"] = str(exc)
        return result

    def recommend_models(
        self,
        *,
        task: str = "chat",
        mode: str = "balanced",
        top: int = 10,
        candidate_limit: int = 250,
        max_download_gb: Optional[float] = None,
        formats: Optional[Iterable[str] | str] = None,
        include_gated: bool = False,
        refresh: bool = False,
        pull_best: bool = False,
        output_dir: Optional[str] = None,
        endpoint: str = "https://huggingface.co",
        token: Optional[str] = None,
        cache_dir: Optional[str] = None,
        cache_ttl_seconds: int = 24 * 60 * 60,
        enrichment_cap: int = 50,
        artifact_enrichment_cap: int = 20,
        download_root: Optional[str] = None,
        disk_reserve_gb: float = 2.0,
        run_store_root: Optional[str] = None,
        persist_run: bool = True,
        simulated_hardware: str | dict[str, Any] | None = None,
        benchmark_snapshots: Optional[Iterable[str | Path]] = None,
        model_ref: Optional[str] = None,
    ) -> dict[str, Any]:
        if top <= 0:
            raise ValueError("top must be positive")
        if candidate_limit <= 0:
            raise ValueError("candidate_limit must be positive")
        if enrichment_cap <= 0:
            raise ValueError("enrichment_cap must be positive")
        if artifact_enrichment_cap <= 0:
            raise ValueError("artifact_enrichment_cap must be positive")
        if disk_reserve_gb < 0.0:
            raise ValueError("disk_reserve_gb cannot be negative")
        if simulated_hardware is not None and pull_best:
            raise ValueError("simulated hardware is read-only; remove --pull-best before downloading")

        task_key = (task or "chat").strip().lower()
        mode_key = (mode or "balanced").strip().upper()
        formats_explicit = formats is not None
        format_set = self._normalize_recommendation_formats(formats)
        max_gb = float(max_download_gb) if max_download_gb is not None else 12.0
        if max_gb <= 0.0:
            raise ValueError("max_download_gb must be positive")
        max_bytes = int(max_gb * _GIB)
        hardware = self.hardware_profile(simulation=simulated_hardware)
        reserve_bytes = int(float(disk_reserve_gb) * _GIB)
        if simulated_hardware is not None:
            disk = simulated_disk_capacity(hardware, reserve_bytes=reserve_bytes)
        else:
            download_target = Path(download_root or output_dir or (self.runtime_root / "models"))
            disk = disk_capacity(download_target, reserve_bytes=reserve_bytes)
        client = HfHubClient(
            endpoint=endpoint,
            token=token,
            cache_dir=cache_dir,
            cache_ttl_seconds=cache_ttl_seconds,
        )
        external_evidence, benchmark_snapshot_status = self._load_benchmark_snapshots(
            benchmark_snapshots
        )

        arms = self._recommendation_query_arms(
            task_key,
            format_set,
            include_format_arms=True,
            include_family_arms=candidate_limit >= 50,
        )
        raw_candidates: dict[str, dict[str, Any]] = {}
        arm_results: list[dict[str, Any]] = []
        arm_candidates: list[list[dict[str, Any]]] = []
        per_arm_limit = min(
            50,
            max(10, math.ceil(candidate_limit / max(1, len(arms))) * 2),
        )
        if model_ref:
            reference = str(model_ref).strip().strip("/")
            reference = re.sub(r"^https?://[^/]+/", "", reference, flags=re.IGNORECASE)
            reference = reference.split("?", 1)[0].split("#", 1)[0].strip("/")
            if not reference or "/" not in reference or " " in reference:
                raise ValueError("model_ref must be a Hugging Face repository id such as org/model")
            try:
                model = client.model_info(
                    reference,
                    refresh=refresh,
                    expand=("siblings", "config", "tags", "cardData", "downloads", "likes", "lastModified"),
                )
            except Exception as exc:
                raise ValueError(f"Hugging Face repository could not be inspected: {exc}") from exc
            repo_id = self._hub_repo_id(model) or reference
            raw_candidates[repo_id] = {**model, "id": repo_id, "modelId": repo_id}

        for arm in ([] if model_ref else arms):
            try:
                models = client.search_models(
                    search=arm.get("search"),
                    pipeline_tag=arm.get("pipeline_tag"),
                    filters=arm.get("filters"),
                    sort=arm.get("sort"),
                    num_parameters=arm.get("num_parameters"),
                    limit=per_arm_limit,
                    refresh=refresh,
                    expand=("tags", "downloads", "likes", "lastModified", "siblings"),
                )
            except Exception as exc:
                arm_results.append({"name": arm["name"], "status": "error", "error": str(exc)})
                arm_candidates.append([])
                continue
            arm_results.append({"name": arm["name"], "status": "ok", "count": len(models)})
            arm_candidates.append(models)

        round_index = 0
        while len(raw_candidates) < candidate_limit:
            added = False
            for models in arm_candidates:
                if round_index >= len(models):
                    continue
                model = models[round_index]
                repo_id = self._hub_repo_id(model)
                if repo_id and repo_id not in raw_candidates:
                    raw_candidates[repo_id] = model
                    added = True
                    if len(raw_candidates) >= candidate_limit:
                        break
            if not added and all(round_index >= len(models) - 1 for models in arm_candidates):
                break
            round_index += 1

        cheap_ranked: list[dict[str, Any]] = []
        for repo_id, candidate in raw_candidates.items():
            scored = self._score_hub_candidate(
                candidate,
                hardware=hardware,
                task=task_key,
                mode=mode_key,
                allowed_formats=format_set,
                max_download_bytes=max_bytes,
                include_gated=include_gated,
                disk_profile=disk,
                external_evidence=external_evidence,
            )
            if not scored["excluded"]:
                cheap_ranked.append(scored)
        cheap_ranked.sort(key=lambda item: item["final_score"], reverse=True)

        enriched: list[dict[str, Any]] = []
        excluded_after_enrichment: set[str] = set()
        enrich_count = min(enrichment_cap, len(cheap_ranked))
        for enrich_index, item in enumerate(cheap_ranked[:enrich_count]):
            repo_id = item["repo_id"]
            try:
                info = client.model_info(
                    repo_id,
                    expand=(
                        "siblings",
                        "config",
                        "tags",
                        "cardData",
                        "likes",
                        "downloads",
                        "safetensors",
                        "pipeline_tag",
                        "lastModified",
                        "trendingScore",
                        "evalResults",
                        "model-index",
                        "baseModels",
                        "inferenceProviderMapping",
                        "library_name",
                        "usedStorage",
                        "disabled",
                        "private",
                        "gated",
                    ),
                    refresh=refresh,
                )
            except Exception as exc:
                item["warnings"].append(f"metadata enrichment failed: {exc}")
                enriched.append(item)
                continue
            merged = dict(item["raw_candidate"])
            merged.update(info)
            tree_error = None
            if (
                enrich_index < min(artifact_enrichment_cap, enrichment_cap)
            ):
                try:
                    tree_files = client.list_repo_tree(repo_id, refresh=refresh)
                    if tree_files:
                        merged["siblings"] = [
                            {"rfilename": file.path, "size": file.size}
                            for file in tree_files
                        ]
                except Exception as exc:
                    tree_error = str(exc)
            rescored = self._score_hub_candidate(
                merged,
                hardware=hardware,
                task=task_key,
                mode=mode_key,
                allowed_formats=format_set,
                max_download_bytes=max_bytes,
                include_gated=include_gated,
                disk_profile=disk,
                external_evidence=external_evidence,
            )
            if tree_error:
                rescored["warnings"].append(
                    f"exact artifact inventory failed; file choice is provisional: {tree_error}"
                )
            if not rescored["excluded"]:
                enriched.append(rescored)
            else:
                excluded_after_enrichment.add(repo_id)

        already_enriched = {item["repo_id"] for item in enriched}
        ranked = enriched + [
            item for item in cheap_ranked if item["repo_id"] not in already_enriched
            and item["repo_id"] not in excluded_after_enrichment
        ]
        ranked.sort(key=lambda item: item["final_score"], reverse=True)
        recommendations = [self._public_recommendation(item) for item in ranked[:top]]
        best_for_hardware = self._recommendation_best_for_hardware(ranked)
        categories = self._recommendation_categories(ranked)
        user_answer = self._recommendation_user_answer(best_for_hardware)
        run_id = hashlib.sha256(
            json.dumps(
                {
                    "task": task_key,
                    "hardware": hardware.get("fingerprint"),
                    "repos": [item["repo_id"] for item in ranked[:top]],
                    "created": time.time_ns(),
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()[:20]
        workload_profile = WorkloadProfile(task=task_key)
        result: dict[str, Any] = {
            "rift_product": self.product.name,
            "rift_phase": "M3_EXACT_ARTIFACT",
            "recommendation_contract": "RECOMMENDATION_V2_ADAPTER_GRAPH",
            "schema_version": 2,
            "recommendation_run_id": run_id,
            "task": task_key,
            "workload_profile": workload_profile.to_dict(),
            "mode_preference": mode_key,
            "mode_preference_deprecated": True,
            "top": top,
            "candidate_limit": candidate_limit,
            "enrichment_cap": enrichment_cap,
            "artifact_enrichment_cap": artifact_enrichment_cap,
            "max_download_gb": max_gb,
            "disk_profile": disk,
            "formats": sorted(format_set),
            "formats_explicit_constraint": formats_explicit,
            "include_gated": include_gated,
            "refresh": refresh,
            "hardware_profile": hardware,
            "hardware_simulation": hardware.get(
                "simulation",
                {"enabled": False, "read_only": True, "assumptions": []},
            ),
            "discovery": {
                "source": endpoint,
                "selection_automatic": True,
                "repository_input_required": False,
                "strategy": "bounded_multi_arm_hub_index_search",
                "query_strategy_version": "R20_DIVERSIFIED_EVIDENCE_FUNNEL",
                "query_arm_count": len(arms),
                "literal_full_hub_crawl": False,
                "finalists_enriched": len(enriched),
            },
            "query_arms": arm_results,
            "benchmark_sources": benchmark_site_catalog(),
            "benchmark_snapshot_status": benchmark_snapshot_status,
            "candidate_counts": {
                "raw": len(raw_candidates),
                "after_filters": len(cheap_ranked),
                "enriched": len(enriched),
                "returned": len(recommendations),
            },
            "best_for_hardware": best_for_hardware,
            "categories": categories,
            "answer": user_answer,
            "recommendations": recommendations,
            "adapter_diagnostics": self.backend_adapters.diagnostics(),
            "artifact_adapter_diagnostics": self.artifact_adapters.diagnostics(),
            "notes": [
                "Scores are bounded deployment recommendations, not live accuracy measurements on this PC.",
                "Quality combines task/model metadata with structured Hub evaluation evidence when present; heterogeneous benchmark values are not compared as if they were one metric.",
                "Popularity and model-card claims are treated as weak signals.",
                "RIFT does not crawl the entire Hub; it searches bounded query arms and enriches finalists only.",
                "Query arms are interleaved so a single popularity sort cannot consume the whole candidate budget.",
                "Backend choice is evaluated through dynamically registered RIFT-owned adapter manifests; upstream backends require no changes.",
                "Formats are discovered from finalist artifacts unless the user supplies an explicit --formats constraint.",
                "GGUF repositories are ranked by one exact quant artifact, not by the sum of every quant in the repository.",
                "External benchmark sites are provenance sources; only permitted signed snapshots contribute published quality evidence.",
            ],
        }
        if pull_best and recommendations:
            best = recommendations[0]
            result["pull_best"] = self.pull_model_from_hub(
                best["repo_id"],
                output_dir=output_dir,
                allow_patterns=self._artifact_pull_patterns(best),
                token=token,
                endpoint=endpoint,
                max_bytes=max_bytes,
            )
        if persist_run:
            try:
                store = RecommendationStore(
                    Path(run_store_root) if run_store_root else self.runtime_root
                )
                result["recommendation_run_path"] = str(store.recommendation_path(run_id))
                store.save_recommendation(result)
            except OSError as exc:
                result.setdefault("warnings", []).append(
                    f"recommendation run could not be persisted: {exc}"
                )
        return result

    def _recommendation_categories(self, ranked: list[dict[str, Any]]) -> dict[str, Any]:
        feasible = [item for item in ranked if item.get("support_level") != "UNSUPPORTED"]
        if not feasible:
            return {
                "best_estimated": None,
                "best_verified": None,
                "best_runnable_now": None,
                "best_after_install": None,
                "highest_quality": None,
                "fastest": None,
                "pareto_frontier": [],
                "best_published_quality": None,
                "best_estimated_fit": None,
                "best_verified_local": None,
                "fastest_verified_local": None,
                "best_deployment": None,
            }

        def compact(item: dict[str, Any] | None) -> dict[str, Any] | None:
            if item is None:
                return None
            return {
                "repo_id": item["repo_id"],
                "model_identity_id": (item.get("model_identity") or {}).get("identity_id"),
                "artifact_id": (item.get("selected_artifact") or {}).get("artifact_id"),
                "selected_file": item.get("selected_file"),
                "backend": item.get("backend"),
                "support_level": item.get("support_level"),
                "score": item.get("final_score"),
                "confidence": item.get("confidence"),
                "scores": item.get("scores"),
                "performance_estimate": item.get("performance_estimate"),
                "resource_estimate": item.get("resource_estimate"),
                "quality_evidence": item.get("quality_evidence", {}),
                "evidence_freshness": item.get("evidence_freshness", "unknown"),
                "evidence_coverage": item.get("evidence_coverage", 0),
            }

        verified = [
            item
            for item in feasible
            if self._has_exact_local_verification(item)
        ]
        runnable = [item for item in feasible if item.get("support_level") == "AVAILABLE_NOW"]
        installable = [item for item in feasible if item.get("support_level") == "INSTALLABLE_BACKEND"]
        published = [
            item
            for item in feasible
            if (item.get("quality_evidence") or {}).get("score") is not None
            and (item.get("quality_evidence") or {}).get("published_records", 0) > 0
        ]
        dimensions = (
            "quality_proxy",
            "expected_speed",
            "deployment_feasibility",
            "behavioral_safety",
            "license_trust",
            "artifact_integrity",
        )
        frontier = []
        for candidate in feasible:
            candidate_scores = candidate.get("scores") or {}
            dominated = False
            for other in feasible:
                if other is candidate:
                    continue
                other_scores = other.get("scores") or {}
                no_worse = all(float(other_scores.get(key, 0.0)) >= float(candidate_scores.get(key, 0.0)) for key in dimensions)
                strictly_better = any(float(other_scores.get(key, 0.0)) > float(candidate_scores.get(key, 0.0)) for key in dimensions)
                if no_worse and strictly_better:
                    dominated = True
                    break
            if not dominated:
                frontier.append(candidate)
        frontier.sort(key=lambda item: (float(item.get("final_score") or 0.0), float(item.get("confidence") or 0.0)), reverse=True)
        best_deployment_pool = runnable or installable or feasible
        best_published = max(
            published,
            key=lambda item: (
                float((item.get("quality_evidence") or {}).get("score") or 0.0),
                float(item.get("confidence") or 0.0),
            ),
        ) if published else None
        best_verified_local = max(verified, key=lambda item: item["final_score"]) if verified else None
        return {
            "best_estimated": compact(max(feasible, key=lambda item: (item["final_score"], item["confidence"]))),
            "best_verified": compact(max(verified, key=lambda item: item["final_score"])) if verified else None,
            "best_runnable_now": compact(max(runnable, key=lambda item: item["final_score"])) if runnable else None,
            "best_after_install": compact(max(installable, key=lambda item: item["final_score"])) if installable else None,
            "highest_quality": compact(max(feasible, key=lambda item: (item["scores"]["quality_proxy"], item["confidence"]))),
            "fastest": compact(max(feasible, key=lambda item: (item["scores"]["expected_speed"], item["scores"]["hardware_fit"]))),
            "pareto_frontier": [compact(item) for item in frontier[:20]],
            "best_published_quality": compact(best_published),
            "best_estimated_fit": compact(max(feasible, key=lambda item: (item["final_score"], item["confidence"]))),
            "best_verified_local": compact(best_verified_local),
            "fastest_verified_local": compact(
                max(verified, key=lambda item: (item["scores"]["expected_speed"], item["scores"]["hardware_fit"]))
                if verified
                else None
            ),
            "best_deployment": compact(max(best_deployment_pool, key=lambda item: (item["final_score"], item["confidence"]))),
            "claim_boundary": "Estimated categories use available evidence; best_verified requires a matching artifact/backend measurement produced locally by RIFT.",
        }

    @staticmethod
    def _has_exact_local_verification(candidate: dict[str, Any]) -> bool:
        selected_artifact = candidate.get("selected_artifact") or {}
        artifact_keys = {
            str(value)
            for value in (
                candidate.get("selected_file"),
                selected_artifact.get("artifact_id"),
            )
            if value
        }
        backend = str(candidate.get("backend") or "")
        for record in (candidate.get("evidence_provenance") or {}).get("records") or []:
            if str(record.get("level")) != "VERIFIED_LOCAL":
                continue
            value = record.get("value") if isinstance(record.get("value"), dict) else {}
            recorded_artifact = str(value.get("artifact") or "")
            recorded_backend = str(value.get("backend") or "")
            if recorded_backend == backend and recorded_artifact in artifact_keys:
                return True
        return False

    def compatibility_advice(self, model_path: str) -> dict[str, Any]:
        model_dir = Path(model_path)
        files = list(model_dir.iterdir()) if model_dir.is_dir() else []
        gguf_files = sorted(path.name for path in files if path.suffix.lower() == ".gguf")
        safetensors_files = sorted(path.name for path in files if path.suffix == ".safetensors")
        config_path = model_dir / "config.json"
        config: dict[str, Any] = {}
        if config_path.is_file():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                config = {"_parse_error": "config.json is not valid JSON"}
        model_type = str(config.get("model_type", "unknown")).lower()
        quantization = config.get("quantization_config") or {}
        quant_method = str(quantization.get("quant_method", "")).lower()
        family = "UNKNOWN"
        support_level = "UNSUPPORTED"
        native_status = "not_supported"
        recommendations: list[str] = []

        if gguf_files:
            family = "GGUF"
            support_level = "EXTERNAL_RECOMMENDED"
            native_status = "gguf_native_backend_pending"
            recommendations.append("Use llama.cpp-compatible serving today; keep RIFT for inspect/planning.")
        elif model_type in ("llama", "mllama") and quant_method == "gptq":
            family = "LLAMA"
            support_level = "NATIVE_RUN_CANDIDATE"
            native_status = "llama_gptq_safetensors_supported"
            recommendations.append("Use RIFT native SURVIVAL today; BALANCED is the next runtime target.")
        elif "qwen" in model_type:
            family = "QWEN"
            support_level = "ADAPTER_PENDING"
            native_status = "qwen_adapter_pending"
            recommendations.append("Use an external Qwen-capable runtime until the RIFT adapter lands.")
        elif "mistral" in model_type:
            family = "MISTRAL"
            support_level = "ADAPTER_PENDING"
            native_status = "mistral_adapter_pending"
            recommendations.append("RIFT needs a Mistral tensor-role adapter before native execution.")
        elif "gemma" in model_type:
            family = "GEMMA"
            support_level = "ADAPTER_PENDING"
            native_status = "gemma_adapter_pending"
            recommendations.append("RIFT needs a Gemma adapter and tokenizer handling before native execution.")
        elif "phi" in model_type:
            family = "PHI"
            support_level = "ADAPTER_PENDING"
            native_status = "phi_adapter_pending"
            recommendations.append("RIFT needs a Phi adapter before native execution.")
        elif safetensors_files:
            support_level = "INSPECT_ONLY_CANDIDATE"
            native_status = "unknown_safetensors_layout"
            recommendations.append("Run rift inspect; if it fails, use external backend recommendation mode.")
        else:
            recommendations.append("Model folder does not expose a supported checkpoint format yet.")

        estimated_bytes = 0
        for path in files:
            if path.is_file() and path.suffix.lower() in (".gguf", ".safetensors"):
                estimated_bytes += path.stat().st_size
        local_format = "gguf" if gguf_files else quant_method if quant_method in ("gptq", "awq") else "safetensors" if safetensors_files else "unknown"
        backend_decision = self.recommend_backend(
            model_path=str(model_dir),
            model_format=local_format,
            model_family=family,
            model_type=model_type,
            quant_method=quant_method or "unknown",
            estimated_model_bytes=estimated_bytes,
        )

        return {
            "rift_product": self.product.name,
            "rift_phase": "M3",
            "model_path": str(model_dir),
            "family": family,
            "model_type": model_type,
            "quant_method": quant_method or "unknown",
            "support_level": support_level,
            "native_status": native_status,
            "backend_decision": backend_decision,
            "files": {
                "gguf": gguf_files,
                "safetensors_count": len(safetensors_files),
                "has_config_json": config_path.is_file(),
                "has_tokenizer_json": (model_dir / "tokenizer.json").is_file(),
            },
            "recommendations": recommendations,
        }

    def doctor(
        self,
        model_path: Optional[str] = None,
        *,
        benchmark_read_bytes: int = 16 * 1024 * 1024,
    ) -> dict[str, Any]:
        """Run a deployment readiness diagnostic for the local PC and model."""

        checks: list[dict[str, Any]] = []

        def add_check(name: str, status: str, message: str, **details: Any) -> None:
            checks.append(
                {
                    "name": name,
                    "status": status,
                    "message": message,
                    "details": details,
                }
            )

        build = self.build_info()
        hardware = self.hardware_profile()
        if hardware.get("cuda_available", True):
            add_check(
                "cuda_runtime",
                "PASS",
                "CUDA runtime is visible to the native backend.",
                device_name=hardware.get("device_name"),
            )
        else:
            add_check("cuda_runtime", "FAIL", "CUDA runtime is not available.")

        major = int(hardware.get("compute_capability_major") or 0)
        minor = int(hardware.get("compute_capability_minor") or 0)
        if major >= 8:
            add_check(
                "cuda_compute_capability",
                "PASS",
                f"Compute capability {major}.{minor} is suitable for current CUDA kernels.",
            )
        elif major >= 7:
            add_check(
                "cuda_compute_capability",
                "WARN",
                f"Compute capability {major}.{minor} may run, but Tensor Core paths are less ideal.",
            )
        else:
            add_check(
                "cuda_compute_capability",
                "FAIL",
                f"Compute capability {major}.{minor} is below the supported runtime target.",
            )

        total_vram = int(hardware.get("total_vram_bytes") or 0)
        free_vram = int(hardware.get("free_vram_bytes") or 0)
        if total_vram >= 8 * _GIB:
            add_check(
                "vram_capacity",
                "PASS",
                "VRAM is sufficient for RIFT MVP validation and future BALANCED planning.",
                total_vram_bytes=total_vram,
                free_vram_bytes=free_vram,
            )
        elif total_vram >= 4 * _GIB:
            add_check(
                "vram_capacity",
                "WARN",
                "VRAM is low; expect only small models or SURVIVAL-style execution.",
                total_vram_bytes=total_vram,
                free_vram_bytes=free_vram,
            )
        else:
            add_check(
                "vram_capacity",
                "FAIL",
                "VRAM is below the practical CUDA execution floor for current native kernels.",
                total_vram_bytes=total_vram,
                free_vram_bytes=free_vram,
            )

        total_host_ram = int(hardware.get("total_host_ram_bytes") or 0)
        if total_host_ram >= 16 * _GIB:
            add_check(
                "host_ram_capacity",
                "PASS",
                "Host RAM is adequate for metadata, staging, and RIFT diagnostics.",
                total_host_ram_bytes=total_host_ram,
            )
        elif total_host_ram >= 8 * _GIB:
            add_check(
                "host_ram_capacity",
                "WARN",
                "Host RAM is tight; prefer bounded streaming and avoid large host caches.",
                total_host_ram_bytes=total_host_ram,
            )
        else:
            add_check(
                "host_ram_capacity",
                "FAIL",
                "Host RAM is below the current practical floor.",
                total_host_ram_bytes=total_host_ram,
            )

        inspection: dict[str, Any] | None = None
        plan: dict[str, Any] | None = None
        model_dir: Path | None = Path(model_path) if model_path else None
        if model_dir is None:
            add_check("model_path", "WARN", "No model path supplied; hardware-only doctor completed.")
        elif not model_dir.exists():
            add_check("model_path", "FAIL", f"Model path does not exist: {model_dir}")
        elif not model_dir.is_dir():
            add_check("model_path", "FAIL", f"Model path is not a directory: {model_dir}")
        else:
            add_check("model_path", "PASS", "Model directory exists.", model_path=str(model_dir))
            safetensors = sorted(model_dir.glob("*.safetensors"))
            tokenizer = model_dir / "tokenizer.json"
            config = model_dir / "config.json"
            add_check(
                "model_files",
                "PASS" if safetensors and tokenizer.is_file() and config.is_file() else "WARN",
                "Model file set checked.",
                safetensors_count=len(safetensors),
                has_tokenizer_json=tokenizer.is_file(),
                has_config_json=config.is_file(),
            )
            try:
                inspection = self.inspect_model(str(model_dir))
            except Exception as exc:
                add_check("model_inspection", "FAIL", f"Model inspection failed: {exc}")
            else:
                compatibility = inspection.get("rift_compatibility_level")
                if compatibility == RiftCompatibilityLevel.NATIVE_RUN_READY.value:
                    add_check(
                        "model_compatibility",
                        "PASS",
                        "Model is native-run-ready for at least one current backend path.",
                        compatibility_level=compatibility,
                    )
                elif compatibility in (
                    RiftCompatibilityLevel.PLAN_READY.value,
                    RiftCompatibilityLevel.INSPECT_ONLY.value,
                ):
                    add_check(
                        "model_compatibility",
                        "WARN",
                        "Model can be inspected or planned, but is not runnable yet.",
                        compatibility_level=compatibility,
                    )
                else:
                    add_check(
                        "model_compatibility",
                        "FAIL",
                        "Model is unsupported by the current RIFT runtime.",
                        compatibility_level=compatibility,
                    )
                try:
                    plan = self.plan_model(
                        str(model_dir),
                        benchmark_read_bytes=benchmark_read_bytes,
                        write=False,
                    )
                except Exception as exc:
                    add_check("deployment_plan", "WARN", f"Plan generation failed: {exc}")
                else:
                    mode_analysis = plan.get("mode_analysis", {})
                    fit_mode = mode_analysis.get("best_hardware_fit_mode")
                    executable_mode = mode_analysis.get("best_executable_mode")
                    if fit_mode != executable_mode and executable_mode != RiftMode.REJECTED.value:
                        add_check(
                            "mode_gap",
                            "WARN",
                            "Hardware appears suitable for a better mode than the current executable runtime.",
                            hardware_fit_mode=fit_mode,
                            executable_mode=executable_mode,
                        )
                    elif executable_mode == RiftMode.REJECTED.value:
                        add_check(
                            "mode_gap",
                            "FAIL",
                            "No executable deployment mode is available for this model.",
                            hardware_fit_mode=fit_mode,
                            executable_mode=executable_mode,
                        )
                    else:
                        add_check(
                            "mode_gap",
                            "PASS",
                            "Best hardware-fit mode is executable by the current runtime.",
                            hardware_fit_mode=fit_mode,
                            executable_mode=executable_mode,
                        )

        statuses = {check["status"] for check in checks}
        overall = "FAIL" if "FAIL" in statuses else "WARN" if "WARN" in statuses else "PASS"
        next_actions = self._doctor_next_actions(overall, inspection, plan)
        return {
            "rift_product": self.product.name,
            "rift_phase": "R17",
            "overall_status": overall,
            "build": build,
            "hardware": hardware,
            "model_path": str(model_dir) if model_dir is not None else None,
            "inspection_summary": (inspection or {}).get("rift_summary", {}),
            "mode_analysis": (inspection or {}).get("rift_mode_analysis", {}),
            "compatibility_advice": self.compatibility_advice(str(model_dir))
            if model_dir is not None and model_dir.exists()
            else {},
            "plan_summary": {
                "recommended_mode": (plan or {}).get("recommended_mode"),
                "hardware_fit_mode": (plan or {}).get("hardware_fit_mode"),
                "selected_backend": (plan or {}).get("selected_backend"),
                "backend_label": ((plan or {}).get("backend_decision") or {}).get("backend_label"),
                "runnable_now": ((plan or {}).get("serving_plan") or {}).get("runnable_now"),
                "launch_command": ((plan or {}).get("serving_plan") or {}).get("launch_command"),
            },
            "checks": checks,
            "next_actions": next_actions,
        }

    def run(
        self,
        *,
        prompt: str,
        model_path: Optional[str] = None,
        plan_path: Optional[str] = None,
        mode: RiftMode = RiftMode.SURVIVAL,
        max_tokens: int = 1,
        temperature: float = 0.0,
        top_p: float = 1.0,
        top_k: int = 32,
        repetition_penalty: float = 1.0,
        save_report: bool = True,
        report_path: Optional[str] = None,
    ) -> dict[str, Any]:
        if not prompt:
            raise ValueError("prompt is required")
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if mode != RiftMode.SURVIVAL:
            raise ValueError("R4 only supports SURVIVAL run mode")
        plan: Optional[dict[str, Any]] = None
        if plan_path:
            plan = self.load_plan(plan_path)
            model_path = str(plan["model_path"])
            planned_mode = plan.get("recommended_mode")
            if planned_mode != RiftMode.SURVIVAL.value:
                raise ValueError(f"plan recommended mode is not SURVIVAL: {planned_mode}")
        if not model_path:
            raise ValueError("model_path or plan_path is required")

        load_start = time.perf_counter()
        load_report = self.load_model(model_path)
        load_elapsed = time.perf_counter() - load_start
        if not load_report.get("generation_ready"):
            raise RuntimeError("model is not generation-ready for RIFT survival run")

        generation_start = time.perf_counter()
        generation = self.generate(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            repetition_penalty=repetition_penalty,
        )
        generation_elapsed = time.perf_counter() - generation_start
        generated_tokens = int(generation.get("generated_tokens") or len(generation.get("tokens", [])))
        tok_s = generated_tokens / generation_elapsed if generation_elapsed > 0.0 else 0.0

        result = {
            "rift_product": self.product.name,
            "rift_phase": "R17",
            "status": generation.get("status", "unknown"),
            "mode": mode.value,
            "model_path": str(model_path),
            "plan_path": plan_path,
            "prompt": prompt,
            "text": generation.get("text", ""),
            "full_text": generation.get("full_text", ""),
            "tokens": generation.get("tokens", []),
            "generated_tokens": generated_tokens,
            "load_seconds": load_elapsed,
            "generation_seconds": generation_elapsed,
            "total_seconds": load_elapsed + generation_elapsed,
            "tokens_per_second": tok_s,
            "first_token_seconds": generation_elapsed / generated_tokens
            if generated_tokens > 0
            else None,
            "decode_path": "repeated_full_prefill",
            "backend_metrics": {
                "layers_executed": generation.get("layers_executed"),
                "total_streamed_bytes": generation.get("total_streamed_bytes"),
                "staging_capacity_bytes": generation.get("staging_capacity_bytes"),
                "context_limit_tokens": generation.get("context_limit_tokens"),
            },
            "plan": plan,
        }
        report = self._build_usability_report(result)
        result["usability_verdict"] = report["usability_verdict"]
        result["recommendations"] = report["recommendations"]
        if save_report:
            target = Path(report_path) if report_path else self.runtime_root / "latest.riftreport.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
            result["report_path"] = str(target)
            history = self._write_report_history(report)
            result["history_report_path"] = str(history)
        return result

    def load_report(self, run: str = "latest") -> dict[str, Any]:
        path = self.runtime_root / "latest.riftreport.json" if run == "latest" else Path(run)
        return json.loads(path.read_text(encoding="utf-8"))

    def list_reports(self, limit: int = 20) -> dict[str, Any]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        reports_dir = self.runtime_root / "reports"
        entries: list[dict[str, Any]] = []
        if reports_dir.is_dir():
            for path in sorted(reports_dir.glob("*.riftreport.json"), reverse=True)[:limit]:
                try:
                    report = json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue
                metrics = report.get("metrics", {})
                entries.append(
                    {
                        "path": str(path),
                        "created_unix_seconds": report.get("created_unix_seconds"),
                        "model_path": report.get("model_path"),
                        "mode": report.get("mode"),
                        "status": report.get("status"),
                        "usability_verdict": report.get("usability_verdict"),
                        "tokens_per_second": metrics.get("tokens_per_second"),
                        "generated_tokens": metrics.get("generated_tokens"),
                    }
                )
        return {"rift_product": self.product.name, "rift_phase": "R15", "reports": entries}

    def _normalize_recommendation_formats(
        self,
        formats: Optional[Iterable[str] | str],
    ) -> set[str]:
        if formats is None:
            values = tuple(
                sorted(
                    {
                        fmt
                        for registration in artifact_adapter_host(load_entry_points=True).all().values()
                        if registration.enabled
                        for fmt in registration.adapter.manifest.capability.formats
                    }
                )
            )
        elif isinstance(formats, str):
            values = tuple(part.strip() for part in formats.split(","))
        else:
            values = tuple(str(part).strip() for part in formats)
        normalized = {value.lower() for value in values if value}
        if not normalized:
            raise ValueError("at least one format must be provided")
        aliases = {
            "safe": "safetensors",
            "safetensor": "safetensors",
            "gptq_int4": "gptq",
            "awq_int4": "awq",
        }
        return {aliases.get(value, value) for value in normalized}

    def _recommendation_query_arms(
        self,
        task: str,
        formats: set[str],
        *,
        include_format_arms: bool = False,
        include_family_arms: bool = True,
    ) -> list[dict[str, Any]]:
        task_terms = {
            "chat": "instruct",
            "coding": "code",
            "code": "code",
            "general": "",
            "embeddings": "embedding",
            "embedding": "embedding",
            "reranking": "reranker",
            "reranker": "reranker",
            "vision-language": "vision",
            "vlm": "vision",
            "structured": "instruct",
            "tool-use": "tools",
        }
        search_term = task_terms.get(task, task)
        pipeline_tags = {
            "embeddings": ("feature-extraction", "sentence-similarity"),
            "embedding": ("feature-extraction", "sentence-similarity"),
            "reranking": ("text-classification",),
            "reranker": ("text-classification",),
            "vision-language": ("image-text-to-text",),
            "vlm": ("image-text-to-text",),
        }.get(task, ("text-generation",))
        arms: list[dict[str, Any]] = [
            {
                "name": "task_downloads",
                "pipeline_tag": pipeline_tags[0],
                "search": search_term,
                "sort": "downloads",
            },
            {
                "name": "task_likes",
                "pipeline_tag": pipeline_tags[0],
                "search": search_term,
                "sort": "likes",
            },
            {
                "name": "task_trending",
                "pipeline_tag": pipeline_tags[0],
                "search": search_term,
                "sort": "trendingScore",
            },
            {
                "name": "task_recent",
                "pipeline_tag": pipeline_tags[0],
                "search": search_term,
                "sort": "lastModified",
            },
        ]
        for pipeline_tag in pipeline_tags[1:]:
            arms.append(
                {
                    "name": f"task_{pipeline_tag.replace('-', '_')}",
                    "pipeline_tag": pipeline_tag,
                    "search": search_term,
                    "sort": "downloads",
                }
            )
        if include_format_arms:
            search_formats = sorted(formats) if formats else [
                "gguf",
                "gptq",
                "awq",
                "safetensors",
            ]
            for fmt in search_formats:
                arms.append(
                    {
                        "name": f"format_{fmt}",
                        "pipeline_tag": pipeline_tags[0],
                        "search": f"{search_term} {fmt}" if search_term else fmt,
                        "sort": "downloads",
                    }
                )
        # Family arms reduce popularity/fine-tune monoculture in the bounded
        # Hub window. They are discovery hints only; artifact and backend fit
        # still decide whether a candidate can be recommended.
        if include_family_arms and task in {"chat", "general", "coding", "code", "structured", "tool-use"}:
            for family in ("qwen", "llama", "mistral", "gemma", "phi"):
                arms.append(
                    {
                        "name": f"family_{family}",
                        "pipeline_tag": pipeline_tags[0],
                        "search": family,
                        "sort": "downloads",
                    }
                )
        arms.append(
            {
                "name": "small_parameter_band",
                "pipeline_tag": pipeline_tags[0],
                "search": search_term,
                "sort": "downloads",
                "num_parameters": "min:1B,max:15B",
            }
        )
        arms.append(
            {
                "name": "medium_parameter_band",
                "pipeline_tag": pipeline_tags[0],
                "search": search_term,
                "sort": "downloads",
                "num_parameters": "min:8B,max:34B",
            }
        )
        arms.append(
            {
                "name": "large_parameter_band",
                "pipeline_tag": pipeline_tags[0],
                "search": search_term,
                "sort": "downloads",
                "num_parameters": "min:14B,max:70B",
            }
        )
        return arms

    def _load_benchmark_snapshots(
        self,
        snapshots: Optional[Iterable[str | Path]],
    ) -> tuple[list[Any], list[dict[str, Any]]]:
        records: list[Any] = []
        statuses: list[dict[str, Any]] = []
        for raw_path in snapshots or ():
            path = str(raw_path)
            source_id = Path(path).stem or "operator_snapshot"
            source = JsonEvidenceSource(
                path,
                source_id,
                trusted_keys_path=self.evidence_engine.trusted_keys_path,
                allow_remote=path.startswith(("http://", "https://")),
            )
            loaded = source.load()
            records.extend(loaded)
            statuses.append(source.diagnostics())
        return records, statuses

    def _hub_repo_id(self, candidate: dict[str, Any]) -> str:
        return str(
            candidate.get("id")
            or candidate.get("modelId")
            or candidate.get("repo_id")
            or candidate.get("name")
            or ""
        )

    def _candidate_tags(self, candidate: dict[str, Any]) -> list[str]:
        tags = candidate.get("tags") or []
        if isinstance(tags, str):
            return [tags.lower()]
        return [str(tag).lower() for tag in tags if tag is not None]

    def _candidate_siblings(self, candidate: dict[str, Any]) -> list[dict[str, Any]]:
        siblings = candidate.get("siblings") or []
        return [dict(item) for item in siblings if isinstance(item, dict)]

    def _candidate_path(self, sibling: dict[str, Any]) -> str:
        return str(sibling.get("rfilename") or sibling.get("path") or sibling.get("name") or "")

    def _candidate_file_size(self, sibling: dict[str, Any]) -> int:
        size = sibling.get("size")
        if isinstance(size, int):
            return size
        lfs = sibling.get("lfs")
        if isinstance(lfs, dict) and isinstance(lfs.get("size"), int):
            return int(lfs["size"])
        return 0

    def _candidate_selected_bytes(self, candidate: dict[str, Any]) -> tuple[int, bool]:
        selected = select_hub_files(
            [
                HubFile(self._candidate_path(sibling), self._candidate_file_size(sibling) or None)
                for sibling in self._candidate_siblings(candidate)
                if self._candidate_path(sibling)
            ],
            allow_patterns=DEFAULT_ALLOW_PATTERNS,
            ignore_patterns=DEFAULT_IGNORE_PATTERNS,
        )
        known = sum(item.size or 0 for item in selected)
        if known > 0:
            return known, False
        safetensors = candidate.get("safetensors")
        if isinstance(safetensors, dict):
            total = safetensors.get("total") or safetensors.get("total_size")
            if isinstance(total, int):
                return total, False
        used_storage = candidate.get("usedStorage") or candidate.get("used_storage")
        if isinstance(used_storage, int):
            return used_storage, False
        return 0, True

    def _candidate_effective_size(
        self,
        candidate: dict[str, Any],
        *,
        fmt: str,
        params: Optional[float],
        selected_bytes: int,
    ) -> tuple[int, str]:
        if selected_bytes > 0:
            return selected_bytes, "known_files"
        if not params or params <= 0:
            return 0, "unknown"

        tags = " ".join(self._candidate_tags(candidate))
        repo_id = self._hub_repo_id(candidate).lower()
        quantized_hint = any(
            marker in f"{repo_id} {tags}"
            for marker in ("int4", "4bit", "4-bit", "q4", "gptq", "awq", "gguf")
        )
        if fmt in ("gptq", "awq", "gguf") or quantized_hint:
            bytes_per_param = 0.58
        elif fmt == "safetensors":
            bytes_per_param = 2.05
        else:
            bytes_per_param = 1.20
        overhead = 512 * 1024 * 1024 if fmt in ("gptq", "awq", "gguf") else 256 * 1024 * 1024
        return int(params * bytes_per_param + overhead), "estimated_from_parameters"

    def _candidate_format(self, candidate: dict[str, Any]) -> str:
        repo_id = self._hub_repo_id(candidate).lower()
        tags = self._candidate_tags(candidate)
        config = candidate.get("config") or {}
        quantization = config.get("quantization_config") if isinstance(config, dict) else {}
        quant_method = ""
        if isinstance(quantization, dict):
            quant_method = str(quantization.get("quant_method") or "").lower()
        paths = [self._candidate_path(item).lower() for item in self._candidate_siblings(candidate)]
        corpus = " ".join([repo_id, quant_method, *tags, *paths])
        if "gptq" in corpus:
            return "gptq"
        if "awq" in corpus:
            return "awq"
        if any(path.endswith(".gguf") for path in paths) or "gguf" in corpus:
            return "gguf"
        if any(path.endswith(".safetensors") for path in paths) or candidate.get("safetensors"):
            return "safetensors"
        if any(path.endswith((".bin", ".pt", ".pth")) for path in paths):
            return "unsafe_blob"
        return "unknown"

    def _candidate_model_type(self, candidate: dict[str, Any]) -> str:
        config = candidate.get("config") or {}
        if isinstance(config, dict):
            model_type = config.get("model_type") or config.get("architectures")
            if isinstance(model_type, list) and model_type:
                model_type = model_type[0]
            if model_type:
                return str(model_type).lower()
        tags = " ".join(self._candidate_tags(candidate))
        repo_id = self._hub_repo_id(candidate).lower()
        for family in ("llama", "qwen", "mistral", "gemma", "phi"):
            if family in tags or family in repo_id:
                return family
        return "unknown"

    def _candidate_parameters(self, candidate: dict[str, Any]) -> Optional[float]:
        for key in ("num_parameters", "parameters", "parameter_count"):
            value = candidate.get(key)
            if isinstance(value, (int, float)) and value > 0:
                return float(value)
        haystack = " ".join([self._hub_repo_id(candidate), *self._candidate_tags(candidate)])
        match_b = re.search(r"(?<![a-z0-9])(\d+(?:\.\d+)?)\s*b(?![a-z])", haystack, re.IGNORECASE)
        if match_b:
            return float(match_b.group(1)) * 1_000_000_000
        match_m = re.search(r"(?<![a-z0-9])(\d+(?:\.\d+)?)\s*m(?![a-z])", haystack, re.IGNORECASE)
        if match_m:
            return float(match_m.group(1)) * 1_000_000
        return None

    def _candidate_license(self, candidate: dict[str, Any]) -> str:
        card = candidate.get("cardData") or candidate.get("card_data") or {}
        if isinstance(card, dict) and card.get("license"):
            return str(card["license"]).lower()
        for tag in self._candidate_tags(candidate):
            if tag.startswith("license:"):
                return tag.split(":", 1)[1]
        return "unknown"

    def _candidate_backend_decision(
        self,
        candidate: dict[str, Any],
        *,
        fmt: str,
        hardware: dict[str, Any],
        model_bytes: int,
        workload: str,
        artifact: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        model_type = self._candidate_model_type(candidate)
        artifact_payload = {
            "artifact_id": f"legacy:{self._hub_repo_id(candidate)}:{fmt}",
            "format": fmt,
            "quantization": None,
            "architecture": model_type,
            "total_bytes": model_bytes,
            **dict(artifact or {}),
        }
        ranked = self.backend_adapters.rank(
            artifact=artifact_payload,
            hardware=hardware,
            workload=workload,
            search_root=self.runtime_root / "backends",
            detection_cache=self._backend_detection_cache,
        )
        candidates = [
            {
                "backend": item.adapter_id,
                "feasible": item.compatible,
                "score": item.score,
                "format_supported": not any("does not advertise artifact format" in reason for reason in item.reasons),
                "hardware_fit": item.hardware_fit,
                "platform_supported": item.platform_supported,
                "installed": item.installed,
                "support_level": item.support_level,
                "reasons": list(item.reasons),
                "diagnostics": [entry.to_dict() for entry in item.diagnostics],
            }
            for item in ranked
        ]
        winner = next((item for item in candidates if item["feasible"]), None)
        if winner is None:
            return {
                "backend": BackendKind.NONE.value,
                "support_level": "UNSUPPORTED",
                "note": "No registered provider passed format, hardware, and platform checks.",
                "candidates": candidates,
            }
        support = "AVAILABLE_NOW" if winner["installed"] else "INSTALLABLE_BACKEND"
        note = (
            f"{winner['backend']} ranked highest through adapter-declared format, hardware, "
            "platform, workload, and installation capabilities."
        )
        return {
            "backend": winner["backend"],
            "support_level": support,
            "note": note,
            "candidates": candidates,
        }

    def _candidate_eval_evidence(self, candidate: dict[str, Any]) -> dict[str, Any]:
        raw = candidate.get("evalResults") or candidate.get("eval_results") or []
        model_index = candidate.get("model-index") or candidate.get("model_index")
        if not raw and isinstance(model_index, list):
            raw = model_index
        elif not raw:
            card = candidate.get("cardData") or candidate.get("card_data") or {}
            if isinstance(card, dict):
                raw = card.get("model-index") or card.get("model_index") or card.get("eval_results") or []

        metrics: list[dict[str, Any]] = []

        def walk(value: Any, source: str | None = None) -> None:
            if isinstance(value, list):
                for item in value:
                    walk(item, source)
                return
            if not isinstance(value, dict):
                return
            source_value = value.get("source")
            if isinstance(source_value, dict):
                source = str(source_value.get("name") or source_value.get("url") or source or "")
            metric_values = value.get("metrics")
            if isinstance(metric_values, list):
                for metric in metric_values:
                    if not isinstance(metric, dict):
                        continue
                    metric_value = metric.get("value")
                    if isinstance(metric_value, (int, float)):
                        metrics.append(
                            {
                                "name": str(metric.get("name") or metric.get("type") or "metric"),
                                "value": float(metric_value),
                                "source": source or "model_card",
                            }
                        )
            for key, nested in value.items():
                if key not in ("metrics", "source") and isinstance(nested, (list, dict)):
                    walk(nested, source)

        walk(raw)
        independent = sum(
            1
            for metric in metrics
            if any(
                marker in str(metric.get("source") or "").lower()
                for marker in ("leaderboard", "lighteval", "open llm", "community")
            )
        )
        return {
            "metric_count": len(metrics),
            "independent_metric_count": independent,
            "sample": metrics[:5],
            "present": bool(metrics),
        }

    def _score_hub_candidate(
        self,
        candidate: dict[str, Any],
        *,
        hardware: dict[str, Any],
        task: str,
        mode: str,
        allowed_formats: set[str],
        max_download_bytes: int,
        include_gated: bool,
        disk_profile: Optional[dict[str, Any]] = None,
        external_evidence: Optional[list[Any]] = None,
    ) -> dict[str, Any]:
        repo_id = self._hub_repo_id(candidate)
        tags = self._candidate_tags(candidate)
        params = self._candidate_parameters(candidate)
        resolved_variants = [
            item
            for item in self.artifact_adapters.resolve(source_from_candidate(candidate))
            if item.format in allowed_formats
        ]
        selected_variant: ArtifactVariant | None = None
        artifact_selection: dict[str, Any] | None = None
        gguf_variants = [item for item in resolved_variants if item.format == "gguf"]
        if gguf_variants:
            gguf_files = [
                {
                    "path": self._candidate_path(sibling),
                    "size": self._candidate_file_size(sibling) or None,
                }
                for sibling in self._candidate_siblings(candidate)
                if self._candidate_path(sibling).lower().endswith(".gguf")
            ]
            if gguf_files:
                try:
                    artifact_selection = LlamaCppProvider().select_gguf(
                        gguf_files,
                        hardware=hardware,
                        intent=mode.lower(),
                        disk_budget_bytes=(
                            int(disk_profile.get("usable_bytes") or 0)
                            if disk_profile
                            else None
                        ),
                    )
                except ValueError:
                    artifact_selection = None
            if artifact_selection:
                selected_path = str(artifact_selection.get("path") or "")
                selected_variant = next(
                    (
                        item
                        for item in gguf_variants
                        if selected_path in {file.path for file in item.files}
                    ),
                    None,
                )
        if selected_variant is None and resolved_variants:
            def variant_key(item: ArtifactVariant) -> tuple[bool, float, bool, int, str]:
                ranked = self.backend_adapters.rank(
                    artifact=item,
                    hardware=hardware,
                    workload=task,
                    search_root=self.runtime_root / "backends",
                    detection_cache=self._backend_detection_cache,
                )
                winner = next((entry for entry in ranked if entry.compatible), None)
                return (
                    winner is not None,
                    winner.score if winner else 0.0,
                    item.size_known,
                    -(int(item.total_bytes or 0)),
                    item.artifact_id,
                )

            selected_variant = max(resolved_variants, key=variant_key)
        fmt = selected_variant.format if selected_variant else self._candidate_format(candidate)
        if selected_variant and artifact_selection is None:
            weight_files = [
                item.path
                for item in selected_variant.files
                if item.role in ("weights", "multimodal_projection")
            ]
            dependency_files = [
                item.path
                for item in selected_variant.files
                if item.path not in weight_files
            ]
            artifact_selection = {
                "path": weight_files[0] if weight_files else None,
                "selected_files": [*weight_files, *dependency_files],
                "size": selected_variant.metadata.get("total_download_bytes") or selected_variant.total_bytes or 0,
                "quantization": selected_variant.quantization or "UNKNOWN",
                "complete": bool(selected_variant.validation.get("serving_ready", False)),
                "artifact_id": selected_variant.artifact_id,
                "format": selected_variant.format,
            }
        elif selected_variant and artifact_selection is not None:
            selected_paths = list(artifact_selection.get("selected_files") or [])
            for item in selected_variant.files:
                if (item.required or item.role == "multimodal_projection") and item.path not in selected_paths:
                    selected_paths.append(item.path)
            artifact_selection["selected_files"] = selected_paths
            selected_entries = [
                item for item in selected_variant.files if item.path in set(selected_paths)
            ]
            selected_size = (
                sum(int(item.size or 0) for item in selected_entries)
                if selected_entries and all(isinstance(item.size, int) for item in selected_entries)
                else 0
            )
            artifact_selection["size"] = selected_size or artifact_selection.get("size") or 0
            artifact_selection["complete"] = bool(
                selected_variant.validation.get("serving_ready", False)
            )
        if selected_variant and artifact_selection and artifact_selection.get("size"):
            selected_bytes = int(artifact_selection["size"])
            size_unknown = False
        elif selected_variant and selected_variant.total_bytes:
            selected_bytes = int(
                selected_variant.metadata.get("total_download_bytes")
                or selected_variant.total_bytes
            )
            size_unknown = selected_variant.metadata.get("total_download_bytes") is None
        elif artifact_selection:
            selected_bytes = int(artifact_selection.get("size") or 0)
            size_unknown = selected_bytes <= 0
        else:
            selected_bytes, size_unknown = self._candidate_selected_bytes(candidate)
        effective_bytes, size_source = self._candidate_effective_size(
            candidate,
            fmt=fmt,
            params=params,
            selected_bytes=selected_bytes,
        )
        if selected_variant and selected_variant.size_known and selected_bytes > 0:
            size_source = "exact_artifact_files"
        gated = bool(candidate.get("gated") or candidate.get("private"))
        disabled = bool(candidate.get("disabled", False))
        total_host = int(hardware.get("total_host_ram_bytes") or 0)
        warnings: list[str] = []
        evidence: list[str] = []
        excluded = False
        exclusion_reason = ""

        if not repo_id:
            excluded = True
            exclusion_reason = "missing repo id"
        elif disabled:
            excluded = True
            exclusion_reason = "repository is disabled"
        elif gated and not include_gated:
            excluded = True
            exclusion_reason = "gated/private model excluded"
        elif fmt not in allowed_formats:
            excluded = True
            exclusion_reason = f"format {fmt} is not allowed"
        elif selected_variant and not selected_variant.validation.get("serving_ready", False):
            excluded = True
            missing = ", ".join(
                str(item)
                for item in selected_variant.validation.get("missing_dependencies") or []
            )
            exclusion_reason = "artifact is not serving-ready" + (f": {missing}" if missing else "")
        elif effective_bytes and effective_bytes > max_download_bytes:
            excluded = True
            exclusion_reason = "selected artifact exceeds max_download_gb"
        elif (
            disk_profile
            and effective_bytes
            and effective_bytes > int(disk_profile.get("usable_bytes") or 0)
        ):
            excluded = True
            exclusion_reason = "selected artifact exceeds usable disk capacity"
        elif effective_bytes and total_host and effective_bytes > int(total_host * 0.70):
            excluded = True
            exclusion_reason = "selected artifact leaves insufficient host RAM headroom"

        if size_unknown:
            warnings.append("selected download size is unknown")
        if size_source == "estimated_from_parameters":
            warnings.append("download size estimated from parameter count and format")
        if fmt == "unsafe_blob":
            warnings.append("repository appears to rely on pickle-style weight blobs")
        if gated:
            warnings.append("model is gated or private")
        if disabled:
            warnings.append("repository is disabled")
        if artifact_selection:
            selected_name = str(artifact_selection.get("path") or "")
            quantization = str(artifact_selection.get("quantization") or "UNKNOWN")
            evidence.append(f"exact artifact selected: {selected_name} ({quantization})")
            if not artifact_selection.get("complete", True):
                warnings.append("selected sharded GGUF artifact is incomplete")

        total_vram = int(hardware.get("total_vram_bytes") or 0)
        free_vram = int(hardware.get("free_vram_bytes") or total_vram)
        size_ratio = effective_bytes / max_download_bytes if effective_bytes and max_download_bytes else 0.5
        hardware_fit = max(0.0, min(1.0, 1.12 - size_ratio))
        if size_source == "unknown":
            hardware_fit = 0.68
        if fmt in ("gptq", "awq", "gguf"):
            hardware_fit += 0.12
        if effective_bytes and total_host and effective_bytes > total_host:
            hardware_fit -= 0.20
            warnings.append("selected files exceed total host RAM")
        if effective_bytes and free_vram and effective_bytes < max(0, free_vram - 2 * _GIB):
            hardware_fit += 0.08
            evidence.append("estimated files are smaller than conservative free-VRAM cache window")

        # Download size and VRAM residency are different constraints. A model
        # can fit on disk while still forcing expensive CPU offload or failing
        # at startup. Reserve memory for the runtime, activations, and KV
        # cache, then score the estimated artifact against that usable window.
        usable_vram = max(0, min(total_vram, free_vram) - int(1.5 * _GIB))
        vram_ratio = effective_bytes / usable_vram if effective_bytes and usable_vram else 0.0
        if vram_ratio:
            if vram_ratio <= 0.85:
                hardware_fit += 0.10
                evidence.append("estimated artifact fits within reserved VRAM window")
            elif vram_ratio <= 1.10:
                hardware_fit -= 0.04
                warnings.append("estimated artifact leaves little VRAM for runtime state")
            else:
                offload_penalty = min(0.48, 0.16 + (vram_ratio - 1.10) * 0.28)
                hardware_fit -= offload_penalty
                warnings.append(
                    "estimated artifact exceeds the reserved VRAM window; CPU offload may reduce speed"
                )
        hardware_fit = self._clamp01(hardware_fit)

        speed = 0.45
        if fmt in ("gptq", "awq", "gguf"):
            speed += 0.25
        if effective_bytes:
            speed += max(0.0, min(0.20, (max_download_bytes - effective_bytes) / max_download_bytes * 0.20))
        if effective_bytes and free_vram and effective_bytes > max(0, free_vram - 2 * _GIB):
            speed -= 0.08
        if vram_ratio > 1.0:
            speed -= min(0.36, 0.10 + (vram_ratio - 1.0) * 0.24)
        speed = self._clamp01(speed)

        quality = 0.35
        tag_text = " ".join(tags + [repo_id.lower()])
        pipeline_tag = str(candidate.get("pipeline_tag") or candidate.get("pipelineTag") or "").lower()
        if task in ("coding", "code") and any(word in tag_text for word in ("code", "coder", "coding")):
            quality += 0.25
            evidence.append("coding-related tags/name matched task")
        if task == "chat" and any(word in tag_text for word in ("chat", "instruct", "assistant")):
            quality += 0.22
            evidence.append("chat/instruct tags/name matched task")
        if task == "chat" and any(word in tag_text for word in ("code", "coder", "coding")):
            quality -= 0.08
            warnings.append("coding-specialized model may be less ideal for general chat")
        if task in ("embeddings", "embedding"):
            if pipeline_tag in ("feature-extraction", "sentence-similarity") or any(
                word in tag_text for word in ("embedding", "sentence-transformers", "sentence-similarity")
            ):
                quality += 0.28
                evidence.append("embedding task and model capability metadata agree")
            else:
                quality -= 0.20
                warnings.append("repository does not expose a clear embedding task signal")
        if task in ("reranking", "reranker"):
            if any(word in tag_text for word in ("rerank", "cross-encoder", "sequence-classification")):
                quality += 0.28
                evidence.append("reranking/cross-encoder metadata matched task")
            else:
                quality -= 0.20
                warnings.append("repository does not expose a clear reranking signal")
        if task in ("vision-language", "vlm"):
            if pipeline_tag == "image-text-to-text" or any(
                word in tag_text for word in ("vision", "multimodal", "image-text", "vlm")
            ):
                quality += 0.28
                evidence.append("vision-language capability metadata matched task")
            else:
                quality -= 0.20
                warnings.append("repository does not expose a clear vision-language signal")
        if task in ("agent", "structured", "tool-use") and any(
            word in tag_text for word in ("tool", "function-call", "structured", "instruct")
        ):
            quality += 0.20
            evidence.append("tool/structured instruction metadata matched workload")
        if params:
            params_b = params / 1_000_000_000
            if 15.0 < params_b <= 34.0:
                quality += 0.32
                evidence.append(f"larger parameter band offers a stronger quality ceiling: {params_b:.1f}B")
            elif 9.0 < params_b <= 15.0:
                quality += 0.29
                evidence.append(f"medium parameter band balances quality and deployability: {params_b:.1f}B")
            elif 5.0 <= params_b <= 9.0:
                quality += 0.22
                evidence.append(f"7B/8B class is a strong laptop quality/performance band: {params_b:.1f}B")
            elif 3.0 <= params_b < 5.0:
                quality += 0.15
                evidence.append(f"small model band favors speed over maximum quality: {params_b:.1f}B")
            elif 34.0 < params_b <= 70.0:
                quality += 0.34
                warnings.append(f"{params_b:.1f}B parameters require a high-memory deployment")
            elif params_b < 3.0:
                quality += 0.05
                warnings.append(f"{params_b:.1f}B parameters may trade quality for speed")
        quality = self._clamp01(quality)

        quantization = str((artifact_selection or {}).get("quantization") or "UNKNOWN")
        quant_lower = quantization.lower()
        if quant_lower.startswith(("q5", "q6")):
            quality = self._clamp01(quality + 0.04)
        elif quant_lower.startswith(("q2", "q3")):
            quality = self._clamp01(quality - 0.10)
            warnings.append(f"{quantization} trades substantial quality for memory savings")
        if quant_lower.startswith("q4"):
            speed = self._clamp01(speed + 0.04)

        eval_evidence = self._candidate_eval_evidence(candidate)
        if eval_evidence["present"]:
            eval_bonus = min(0.10, 0.025 + eval_evidence["metric_count"] * 0.008)
            if eval_evidence["independent_metric_count"]:
                eval_bonus += min(
                    0.04,
                    eval_evidence["independent_metric_count"] * 0.01,
                )
            quality = self._clamp01(quality + eval_bonus)
            evidence.append(
                "structured evaluation evidence found: "
                f"{eval_evidence['metric_count']} metrics, "
                f"{eval_evidence['independent_metric_count']} independently attributed"
            )
        else:
            warnings.append("no structured evaluation results found in Hub metadata")

        downloads = int(candidate.get("downloads") or 0)
        likes = int(candidate.get("likes") or 0)
        provenance = self.evidence_engine.assess_candidate(
            {
                **candidate,
                "repo_id": repo_id,
                "evaluation_evidence": eval_evidence,
                "likes": likes,
                "downloads": downloads,
            },
            task=task,
            external_records=external_evidence,
        )
        quality_evidence = provenance.get("quality_evidence") or {}
        published_quality = quality_evidence.get("score")
        if published_quality is not None:
            quality = self._clamp01(quality * 0.70 + float(published_quality) * 0.30)
            evidence.append(
                "normalized benchmark evidence contributes to quality only: "
                f"{published_quality:.2f} across {quality_evidence.get('coverage', 0)} benchmark families"
            )
        elif quality_evidence.get("claim_boundary") == "metadata_or_estimate_only":
            warnings.append("quality score remains metadata-based; no comparable normalized benchmark evidence")

        base_models = candidate.get("baseModels") or candidate.get("base_models")
        if not base_models:
            card = candidate.get("cardData") or candidate.get("card_data") or {}
            if isinstance(card, dict):
                base_models = card.get("base_model") or card.get("base_models")
        if base_models:
            evidence.append("base-model lineage metadata is present")

        paths = [self._candidate_path(item).lower() for item in self._candidate_siblings(candidate)]
        has_safe_file = any(path.endswith((".safetensors", ".gguf")) for path in paths) or fmt in ("gguf", "safetensors", "gptq", "awq")
        has_unsafe_file = any(path.endswith((".bin", ".pt", ".pth")) for path in paths)
        license_name = self._candidate_license(candidate)
        artifact_integrity = 0.45
        integrity_status = str(
            (selected_variant.validation if selected_variant else {}).get("integrity_status")
            or "UNVERIFIED"
        )
        if integrity_status == "HASHED_COMPLETE":
            artifact_integrity = 1.0
            evidence.append("every required artifact file has a content hash")
        elif integrity_status == "HASHED_PARTIAL":
            artifact_integrity = 0.72
            warnings.append("only part of the required artifact set has content hashes")
        elif has_safe_file:
            artifact_integrity = 0.58
            warnings.append("safe serialization detected, but required-file hashes are incomplete")
        if has_unsafe_file:
            artifact_integrity = min(artifact_integrity, 0.20)
            warnings.append("pickle-style files present")

        license_trust = 0.35
        if license_name != "unknown":
            license_trust = 0.86
            evidence.append(f"license metadata present: {license_name}")
        else:
            warnings.append("license metadata not found")

        behavioral_safety = 0.50
        if any(token in tag_text for token in ("safety", "aligned", "guard", "responsible-ai")):
            behavioral_safety += 0.15
            evidence.append("publisher metadata includes an alignment or safety signal")
        if any(token in tag_text for token in ("uncensored", "abliterated", "unfiltered", "no-refusal")):
            behavioral_safety -= 0.28
            warnings.append("repository metadata indicates reduced or removed behavioral safeguards")
        card_data = candidate.get("cardData") or candidate.get("card_data") or {}
        if isinstance(card_data, dict) and any(
            key in card_data for key in ("safety_evaluation", "safety_eval", "model-index")
        ):
            behavioral_safety += 0.08
            evidence.append("model card exposes structured safety/evaluation metadata")
        behavioral_safety = self._clamp01(behavioral_safety)

        if has_safe_file:
            evidence.append("safe/lazy-loadable model file format detected")
        if gated:
            license_trust = self._clamp01(license_trust - 0.08)
        safety = self._clamp01(
            0.35 * behavioral_safety + 0.35 * license_trust + 0.30 * artifact_integrity
        )

        downloads = int(candidate.get("downloads") or 0)
        likes = int(candidate.get("likes") or 0)
        trending = float(candidate.get("trendingScore") or candidate.get("trending_score") or 0.0)
        popularity = self._clamp01(
            min(0.65, math.log10(downloads + 1) / 6.0)
            + min(0.25, math.log10(likes + 1) / 4.0)
            + min(0.10, trending / 100.0)
        )

        backend_decision = self._candidate_backend_decision(
            candidate,
            fmt=fmt,
            hardware=hardware,
            model_bytes=effective_bytes,
            workload=task,
            artifact=selected_variant.to_dict() if selected_variant else None,
        )
        backend = str(backend_decision["backend"])
        support_level = str(backend_decision["support_level"])
        evidence.append(str(backend_decision["note"]))
        support_feasibility = {
            "AVAILABLE_NOW": 1.0,
            "INSTALLABLE_BACKEND": 0.82,
            "NATIVE_RUN_CANDIDATE": 0.72,
        }.get(support_level, 0.0)
        artifact_feasibility = (
            1.0
            if selected_variant and selected_variant.validation.get("serving_ready")
            else 0.55
            if selected_variant is None
            else 0.0
        )
        disk_feasibility = (
            1.0
            if not disk_profile or not effective_bytes or effective_bytes <= int(disk_profile.get("usable_bytes") or 0)
            else 0.0
        )
        deployment_feasibility = self._clamp01(
            hardware_fit * 0.45
            + support_feasibility * 0.30
            + artifact_feasibility * 0.15
            + disk_feasibility * 0.10
        )
        final = (
            hardware_fit * 0.15
            + deployment_feasibility * 0.10
            + speed * 0.20
            + quality * 0.35
            + behavioral_safety * 0.05
            + license_trust * 0.05
            + artifact_integrity * 0.05
            + popularity * 0.05
        )
        if support_level == "UNSUPPORTED":
            final *= 0.55
        if excluded:
            final = 0.0

        confidence = 0.35
        if not size_unknown:
            confidence += 0.20
        if self._candidate_siblings(candidate):
            confidence += 0.15
        if candidate.get("config"):
            confidence += 0.15
        if eval_evidence["present"]:
            confidence += 0.10
        if base_models:
            confidence += 0.05
        if tags:
            confidence += 0.08
        if license_name != "unknown":
            confidence += 0.07
        confidence = self._clamp01(confidence)
        resource_estimate = self._artifact_resource_estimate(
            selected_variant,
            hardware=hardware,
        )
        performance_estimate = self._candidate_performance_estimate(
            provenance=provenance,
            hardware=hardware,
            model_bytes=effective_bytes,
            support_level=support_level,
        )
        identity = self._candidate_model_identity(candidate, task=task, params=params)
        deployment_candidates = [
            {
                "candidate_id": f"{identity.identity_id}:{(selected_variant.artifact_id if selected_variant else fmt)}:{item['backend']}",
                "model_identity_id": identity.identity_id,
                "artifact_id": selected_variant.artifact_id if selected_variant else None,
                "backend": item["backend"],
                "feasible": item["feasible"],
                "support_level": item.get("support_level") or ("INSTALLABLE_BACKEND" if item["feasible"] else "UNSUPPORTED"),
                "score": item["score"],
                "reasons": list(item.get("reasons") or []),
            }
            for item in backend_decision["candidates"]
        ]

        return {
            "schema_version": 2,
            "repo_id": repo_id,
            "model_identity": identity.to_dict(),
            "revision": candidate.get("sha") or candidate.get("revision"),
            "artifact_variants": [item.to_dict() for item in resolved_variants],
            "selected_artifact": selected_variant.to_dict() if selected_variant else None,
            "deployment_candidates": deployment_candidates,
            "raw_candidate": candidate,
            "excluded": excluded,
            "exclusion_reason": exclusion_reason,
            "final_score": round(final, 6),
            "confidence": round(confidence, 6),
            "scores": {
                "hardware_fit": round(hardware_fit, 6),
                "expected_speed": round(speed, 6),
                "quality_proxy": round(quality, 6),
                "safety_trust": round(safety, 6),
                "behavioral_safety": round(behavioral_safety, 6),
                "license_trust": round(license_trust, 6),
                "artifact_integrity": round(artifact_integrity, 6),
                "deployment_feasibility": round(deployment_feasibility, 6),
                "popularity": round(popularity, 6),
            },
            "score_boundaries": {
                "quality_proxy": "Task/model metadata plus attributed evaluation records; not a local quality benchmark.",
                "behavioral_safety": "Metadata evidence only; not a guarantee of safe outputs.",
                "license_trust": "Presence and clarity of declared license metadata; legal review is still required.",
                "artifact_integrity": "Required-file hash coverage and serialization safety, independent of model behavior.",
                "deployment_feasibility": "Artifact readiness, backend/platform fit, hardware capacity, and disk preflight.",
            },
            "format": fmt,
            "selected_download_bytes": selected_bytes,
            "estimated_download_bytes": effective_bytes,
            "download_size_source": size_source,
            "download_size_unknown": size_unknown,
            "selected_file": (artifact_selection or {}).get("path"),
            "selected_files": list((artifact_selection or {}).get("selected_files") or []),
            "quantization": None if quantization == "UNKNOWN" else quantization,
            "artifact_selection": artifact_selection,
            "disk_feasibility": {
                "status": (
                    "unknown"
                    if not effective_bytes
                    else "fits"
                    if not disk_profile
                    or effective_bytes <= int(disk_profile.get("usable_bytes") or 0)
                    else "insufficient"
                ),
                "required_bytes": effective_bytes or None,
                "usable_bytes": int(disk_profile.get("usable_bytes") or 0)
                if disk_profile
                else None,
                "reserve_bytes": int(disk_profile.get("reserve_bytes") or 0)
                if disk_profile
                else None,
            },
            "parameters": int(params) if params else None,
            "model_type": self._candidate_model_type(candidate),
            "gated": gated,
            "license": license_name,
            "downloads": downloads,
            "likes": likes,
            "backend": backend,
            "support_level": support_level,
            "backend_candidates": backend_decision["candidates"],
            "evaluation_evidence": eval_evidence,
            "evidence_provenance": provenance,
            "quality_evidence": quality_evidence,
            "evidence_freshness": quality_evidence.get("freshness", "unknown"),
            "evidence_coverage": quality_evidence.get("coverage", 0),
            "resource_estimate": resource_estimate,
            "performance_estimate": performance_estimate,
            "deployment_mode": self._deployment_mode_for_candidate(support_level, mode),
            "evidence": evidence,
            "warnings": warnings,
        }

    def _artifact_resource_estimate(
        self,
        variant: ArtifactVariant | None,
        *,
        hardware: dict[str, Any],
    ) -> dict[str, Any]:
        if variant is None:
            return {
                "available": False,
                "confidence": "unknown",
                "reason": "No exact artifact variant was resolved.",
            }
        adapter = next(
            (
                item
                for item in self.artifact_adapters.enabled().values()
                if str(getattr(item, "artifact_format", "")).lower() == variant.format.lower()
            ),
            None,
        )
        if adapter is None:
            return {
                "available": False,
                "confidence": "unknown",
                "reason": f"No enabled artifact estimator handles {variant.format}.",
            }
        estimate = dict(adapter.estimate_resources(variant, hardware))
        estimate.update(
            {
                "available": True,
                "confidence": "high" if variant.size_known else "low",
                "artifact_adapter": adapter.adapter_id,
            }
        )
        return estimate

    @staticmethod
    def _candidate_performance_estimate(
        *,
        provenance: dict[str, Any],
        hardware: dict[str, Any],
        model_bytes: int,
        support_level: str,
    ) -> dict[str, Any]:
        for record in provenance.get("records") or []:
            if str(record.get("level")) not in ("VERIFIED_LOCAL", "REPRODUCIBLE_BENCHMARK"):
                continue
            value = record.get("value") if isinstance(record.get("value"), dict) else {}
            metrics = value.get("metrics") if isinstance(value.get("metrics"), dict) else value
            measured = next(
                (
                    metrics.get(key)
                    for key in (
                        "tokens_per_second",
                        "decode_tokens_per_second",
                        "median_tokens_per_second",
                    )
                    if isinstance(metrics.get(key), (int, float)) and float(metrics[key]) > 0
                ),
                None,
            )
            if measured is not None:
                point = float(measured)
                return {
                    "status": "measured_local",
                    "tokens_per_second": round(point, 4),
                    "lower_tokens_per_second": round(point * 0.90, 4),
                    "upper_tokens_per_second": round(point * 1.10, 4),
                    "confidence": "high",
                    "evidence_level": record.get("level"),
                    "claim_boundary": "Range reflects repeatability allowance around a stored local measurement.",
                }

        total_vram = int(hardware.get("total_vram_bytes") or (hardware.get("capacity") or {}).get("vram_bytes") or 0)
        calibration = hardware.get("calibration") if isinstance(hardware.get("calibration"), dict) else {}
        calibration_result = calibration.get("result") if isinstance(calibration.get("result"), dict) else {}
        h2d = calibration_result.get("h2d") if isinstance(calibration_result.get("h2d"), dict) else {}
        disk = calibration_result.get("disk") if isinstance(calibration_result.get("disk"), dict) else {}
        h2d_gib_s = float(h2d.get("bandwidth_gib_s") or 0.0)
        disk_gib_s = float(disk.get("read_mib_s") or 0.0) / 1024.0
        offloaded = bool(model_bytes and total_vram and model_bytes > int(total_vram * 0.85))
        measured_limits = [item for item in (h2d_gib_s, disk_gib_s) if item > 0.0]
        if offloaded and model_bytes > 0 and measured_limits:
            io_gib_s = min(measured_limits)
            upper = io_gib_s * 1024**3 / model_bytes
            lower = upper * 0.30
            return {
                "status": "measured_io_bound_estimate",
                "tokens_per_second": round((lower + upper) / 2.0, 4),
                "lower_tokens_per_second": round(lower, 4),
                "upper_tokens_per_second": round(upper, 4),
                "confidence": "low",
                "bottleneck": "weight-streaming-io",
                "measured_h2d_gib_s": h2d_gib_s or None,
                "measured_disk_gib_s": disk_gib_s or None,
                "claim_boundary": (
                    "I/O-derived planning range only. Compute, cache reuse, backend overhead, and thermal throttling "
                    "can reduce observed decode speed; run `rift model recommend --verify` for an end-to-end result."
                ),
            }
        return {
            "status": "verification_required",
            "tokens_per_second": None,
            "lower_tokens_per_second": None,
            "upper_tokens_per_second": None,
            "confidence": "unknown",
            "support_level": support_level,
            "claim_boundary": (
                "RIFT will not invent an end-to-end throughput number without either a matching local benchmark "
                "or measured offload I/O evidence. Use `rift model recommend --verify`."
            ),
        }

    def _candidate_model_identity(
        self,
        candidate: dict[str, Any],
        *,
        task: str,
        params: float | None,
    ) -> ModelIdentity:
        repo_id = self._hub_repo_id(candidate)
        base_models = candidate.get("baseModels") or candidate.get("base_models")
        if not base_models:
            card = candidate.get("cardData") or candidate.get("card_data") or {}
            if isinstance(card, dict):
                base_models = card.get("base_model") or card.get("base_models")
        if isinstance(base_models, str):
            normalized_bases = (base_models,)
        elif isinstance(base_models, list):
            normalized_bases = tuple(str(item) for item in base_models if item)
        else:
            normalized_bases = ()
        anchor = normalized_bases[0] if normalized_bases else repo_id
        identity_id = "hf:" + re.sub(r"[^a-z0-9._/-]+", "-", anchor.lower()).strip("-")
        tags = tuple(self._candidate_tags(candidate))
        languages = tuple(
            sorted(
                {
                    item.split(":", 1)[1]
                    for item in tags
                    if item.startswith("language:") and ":" in item
                }
            )
        )
        return ModelIdentity(
            identity_id=identity_id,
            repo_id=repo_id,
            family=self._candidate_model_type(candidate),
            task=task,
            revision=str(candidate.get("sha") or candidate.get("revision") or "") or None,
            base_models=normalized_bases,
            parameter_count=int(params) if params else None,
            languages=languages,
            capabilities=tuple(sorted({task, *({"instruct"} if "instruct" in tags else set())})),
            confidence=0.9 if normalized_bases and candidate.get("config") else 0.65 if candidate.get("config") else 0.4,
        )

    def _deployment_mode_for_candidate(self, support_level: str, preferred_mode: str) -> str:
        if support_level in ("AVAILABLE_NOW", "INSTALLABLE_BACKEND"):
            return "EXTERNAL"
        if support_level == "NATIVE_RUN_CANDIDATE":
            return "SURVIVAL" if preferred_mode not in ("FAST", "BALANCED") else preferred_mode
        if support_level == "GGUF_EXTERNAL_RECOMMENDED":
            return "EXTERNAL"
        if support_level in ("CUDA_EXTERNAL_RECOMMENDED", "EXTERNAL_BACKEND_RECOMMENDED"):
            return "EXTERNAL"
        if support_level == "INSPECT_OR_EXTERNAL":
            return "INSPECT_OR_EXTERNAL"
        if support_level == "ADAPTER_PENDING":
            return "ADAPTER_PENDING"
        if support_level == "INSPECT_ONLY_CANDIDATE":
            return "INSPECT_ONLY"
        return "UNSUPPORTED"

    def _recommendation_best_for_hardware(self, ranked: list[dict[str, Any]]) -> dict[str, Any]:
        feasible = [item for item in ranked if item.get("support_level") != "UNSUPPORTED"]
        if not feasible:
            return {
                "best_performance": None,
                "best_accuracy_proxy": None,
                "best_overall": None,
                "method": "No candidate has a feasible backend for this hardware profile.",
            }

        def performance_key(item: dict[str, Any]) -> tuple[float, float]:
            scores = item["scores"]
            value = (
                scores["expected_speed"] * 0.55
                + scores["hardware_fit"] * 0.35
                + scores["safety_trust"] * 0.10
            )
            return value, item["final_score"]

        def quality_key(item: dict[str, Any]) -> tuple[float, float]:
            scores = item["scores"]
            value = (
                scores["quality_proxy"] * 0.65
                + scores["safety_trust"] * 0.20
                + scores["popularity"] * 0.15
            )
            return value, item["final_score"]

        def overall_key(item: dict[str, Any]) -> tuple[float, float]:
            return item["final_score"], item["confidence"]

        best_performance = max(feasible, key=performance_key)
        best_quality = max(feasible, key=quality_key)
        best_overall = max(feasible, key=overall_key)
        best_overall_item = self._recommendation_report_item(
            best_overall,
            selection_score=best_overall["final_score"],
            selection_reason="Highest weighted RIFT recommendation score for this laptop.",
        )
        return {
            "absolute_best": best_overall_item,
            "best_performance": self._recommendation_report_item(
                best_performance,
                selection_score=round(performance_key(best_performance)[0], 6),
                selection_reason="Highest speed/fit score among laptop-compatible candidates.",
            ),
            "best_accuracy_proxy": self._recommendation_report_item(
                best_quality,
                selection_score=round(quality_key(best_quality)[0], 6),
                selection_reason="Highest quality-proxy score among laptop-compatible candidates.",
            ),
            "best_overall": best_overall_item,
            "method": (
                "RIFT compares filtered Hub finalists using performance, quality-proxy, "
                "hardware-fit, safety/trust, and popularity/community evidence."
            ),
            "accuracy_note": (
                "This is not a live accuracy benchmark such as MMLU/HumanEval/arena evaluation. "
                "It is a quality proxy from metadata, model size band, task tags, safety "
                "signals, and community evidence."
            ),
        }

    def _recommendation_user_answer(self, best: dict[str, Any]) -> dict[str, Any]:
        absolute = best.get("absolute_best") or best.get("best_overall")
        speed = best.get("best_performance")
        quality = best.get("best_accuracy_proxy")
        if not absolute:
            return {
                "headline": "No suitable model found for this laptop.",
                "absolute_best_repo_id": None,
                "plain_english": [],
            }
        reasons = []
        if absolute.get("parameters_b") is not None:
            reasons.append(f"{absolute['parameters_b']}B parameters is a practical size for this laptop.")
        if absolute.get("selected_download_gb") is not None:
            size_label = (
                "Exact selected artifact size"
                if absolute.get("download_size_source") == "exact_artifact_files"
                else "Estimated selected download"
            )
            reasons.append(f"{size_label} is {absolute['selected_download_gb']} GB.")
        if absolute.get("selected_file"):
            reasons.append(
                f"Use {absolute['selected_file']} ({absolute.get('quantization') or 'quantization unknown'})."
            )
        scores = absolute.get("scores", {})
        if scores:
            reasons.append(
                "Strong combined fit: "
                f"quality {scores.get('quality_proxy', 0):.2f}, "
                f"speed {scores.get('expected_speed', 0):.2f}, "
                f"hardware {scores.get('hardware_fit', 0):.2f}."
            )
        if absolute.get("backend"):
            reasons.append(f"Recommended serving backend: {absolute['backend']}.")
        reasons.extend(str(item) for item in absolute.get("evidence", [])[:3])
        tradeoffs = []
        for warning in absolute.get("warnings", [])[:4]:
            tradeoffs.append(str(warning))
        if absolute.get("backend") != "rift_native_survival":
            tradeoffs.append(
                "This recommendation is laptop-first, not RIFT-runtime-first; use the advised backend until RIFT support catches up."
            )
        return {
            "headline": f"Best model for this laptop: {absolute['repo_id']}",
            "absolute_best_repo_id": absolute["repo_id"],
            "best_speed_repo_id": (speed or {}).get("repo_id"),
            "best_quality_proxy_repo_id": (quality or {}).get("repo_id"),
            "recommended_backend": absolute.get("backend"),
            "why": reasons,
            "tradeoffs": tradeoffs,
            "pull_command": absolute.get("pull_command"),
            "confidence": absolute.get("confidence"),
            "accuracy_note": best.get("accuracy_note"),
        }

    def _recommendation_report_item(
        self,
        item: dict[str, Any],
        *,
        selection_score: float,
        selection_reason: str,
    ) -> dict[str, Any]:
        params = item.get("parameters")
        bytes_selected = int(item.get("estimated_download_bytes") or item.get("selected_download_bytes") or 0)
        return {
            "repo_id": item["repo_id"],
            "model_identity": item.get("model_identity"),
            "revision": item.get("revision"),
            "selection_score": selection_score,
            "selection_reason": selection_reason,
            "final_score": item["final_score"],
            "confidence": item["confidence"],
            "scores": item["scores"],
            "format": item["format"],
            "selected_file": item.get("selected_file"),
            "selected_files": item.get("selected_files", []),
            "quantization": item.get("quantization"),
            "artifact_selection": item.get("artifact_selection"),
            "selected_artifact": item.get("selected_artifact"),
            "artifact_variants": item.get("artifact_variants", []),
            "deployment_candidates": item.get("deployment_candidates", []),
            "model_type": item["model_type"],
            "parameters_b": round(params / 1_000_000_000, 3) if params else None,
            "selected_download_gb": round(bytes_selected / _GIB, 3) if bytes_selected else None,
            "download_size_source": item.get("download_size_source"),
            "download_size_unknown": item["download_size_unknown"],
            "disk_feasibility": item.get("disk_feasibility"),
            "support_level": item["support_level"],
            "backend": item["backend"],
            "backend_candidates": item.get("backend_candidates", []),
            "evaluation_evidence": item.get("evaluation_evidence", {}),
            "evidence_provenance": item.get("evidence_provenance", {}),
            "quality_evidence": item.get("quality_evidence", {}),
            "evidence_freshness": item.get("evidence_freshness", "unknown"),
            "evidence_coverage": item.get("evidence_coverage", 0),
            "license": item["license"],
            "downloads": item["downloads"],
            "likes": item["likes"],
            "warnings": item["warnings"],
            "evidence": item["evidence"][:8],
            "pull_command": self._recommendation_pull_command(item),
        }

    def _public_recommendation(self, item: dict[str, Any]) -> dict[str, Any]:
        repo_id = item["repo_id"]
        return {
            "repo_id": repo_id,
            "schema_version": 2,
            "model_identity": item.get("model_identity"),
            "revision": item.get("revision"),
            "final_score": item["final_score"],
            "confidence": item["confidence"],
            "scores": item["scores"],
            "format": item["format"],
            "selected_file": item.get("selected_file"),
            "selected_files": item.get("selected_files", []),
            "quantization": item.get("quantization"),
            "artifact_selection": item.get("artifact_selection"),
            "selected_artifact": item.get("selected_artifact"),
            "artifact_variants": item.get("artifact_variants", []),
            "deployment_candidates": item.get("deployment_candidates", []),
            "model_type": item["model_type"],
            "parameters": item["parameters"],
            "parameters_b": round(item["parameters"] / 1_000_000_000, 3)
            if item["parameters"]
            else None,
            "selected_download_bytes": item["selected_download_bytes"],
            "estimated_download_bytes": item["estimated_download_bytes"],
            "estimated_download_gb": round(item["estimated_download_bytes"] / _GIB, 3)
            if item["estimated_download_bytes"]
            else None,
            "download_size_source": item["download_size_source"],
            "download_size_unknown": item["download_size_unknown"],
            "disk_feasibility": item.get("disk_feasibility"),
            "deployment_mode": item["deployment_mode"],
            "backend": item["backend"],
            "backend_candidates": item.get("backend_candidates", []),
            "evaluation_evidence": item.get("evaluation_evidence", {}),
            "evidence_provenance": item.get("evidence_provenance", {}),
            "quality_evidence": item.get("quality_evidence", {}),
            "evidence_freshness": item.get("evidence_freshness", "unknown"),
            "evidence_coverage": item.get("evidence_coverage", 0),
            "support_level": item["support_level"],
            "gated": item["gated"],
            "license": item["license"],
            "downloads": item["downloads"],
            "likes": item["likes"],
            "evidence": item["evidence"],
            "warnings": item["warnings"],
            "pull_command": self._recommendation_pull_command(item),
        }

    def _artifact_pull_patterns(self, recommendation: dict[str, Any]) -> list[str] | None:
        selected = [
            str(path)
            for path in recommendation.get("selected_files", [])
            if str(path).strip()
        ]
        if not selected and recommendation.get("selected_file"):
            selected = [str(recommendation["selected_file"])]
        if not selected:
            return None
        metadata = ["*.json", "*.model", "*.txt", "*.tiktoken", "*.md"]
        return list(dict.fromkeys([*selected, *metadata]))

    def _recommendation_pull_command(self, item: dict[str, Any]) -> str:
        repo_id = str(item["repo_id"])
        target = f".\\models\\{repo_id.replace('/', '--')}"
        command = f"rift model pull {repo_id} --output {target}"
        selected = [
            str(path)
            for path in item.get("selected_files", [])
            if str(path).strip()
        ]
        if not selected and item.get("selected_file"):
            selected = [str(item["selected_file"])]
        for path in selected:
            command += f' --include "{path}"'
        return command

    def _clamp01(self, value: float) -> float:
        return max(0.0, min(1.0, value))

    def _benchmark_disk_read(
        self,
        model_dir: Path,
        max_read_bytes: int,
        read_chunk_bytes: int,
    ) -> dict[str, Any]:
        files = sorted(model_dir.glob("*.safetensors"))
        if not files:
            files = sorted(path for path in model_dir.iterdir() if path.is_file())
        if not files:
            raise ValueError(f"no readable model files found in {model_dir}")

        remaining = max_read_bytes
        bytes_read = 0
        files_sampled: list[str] = []
        start = time.perf_counter()
        for path in files:
            if remaining <= 0:
                break
            files_sampled.append(str(path))
            with path.open("rb") as handle:
                while remaining > 0:
                    chunk = handle.read(min(read_chunk_bytes, remaining))
                    if not chunk:
                        break
                    bytes_read += len(chunk)
                    remaining -= len(chunk)
        elapsed = max(time.perf_counter() - start, 1.0e-9)
        return {
            "bytes_read": bytes_read,
            "elapsed_seconds": elapsed,
            "bandwidth_gbps": bytes_read / elapsed / 1_000_000_000,
            "bandwidth_mib_s": bytes_read / elapsed / (1024 * 1024),
            "max_read_bytes": max_read_bytes,
            "read_chunk_bytes": read_chunk_bytes,
            "files_sampled": files_sampled,
        }

    def _build_usability_report(self, run: dict[str, Any]) -> dict[str, Any]:
        tok_s = float(run.get("tokens_per_second") or 0.0)
        status = run.get("status")
        generated_tokens = int(run.get("generated_tokens") or 0)
        generation_seconds = float(run.get("generation_seconds") or 0.0)
        per_token = (
            [generation_seconds / generated_tokens] * min(generated_tokens, 128)
            if generated_tokens > 0 and generation_seconds > 0.0
            else []
        )
        p50 = statistics.median(per_token) if per_token else None
        p95 = per_token[int(0.95 * (len(per_token) - 1))] if per_token else None
        if status != "ok":
            verdict = UsabilityVerdict.REJECTED
        elif tok_s >= 10.0:
            verdict = UsabilityVerdict.EXCELLENT
        elif tok_s >= 3.0:
            verdict = UsabilityVerdict.GOOD
        elif tok_s >= 1.0:
            verdict = UsabilityVerdict.USABLE
        elif tok_s >= 0.05:
            verdict = UsabilityVerdict.SLOW
        else:
            verdict = UsabilityVerdict.NOT_RECOMMENDED

        recommendations: list[str] = []
        if run.get("mode") == RiftMode.SURVIVAL.value:
            recommendations.append(
                "SURVIVAL mode is correctness-first and expected to be slow."
            )
            recommendations.append(
                "Use a smaller model or wait for BALANCED/KV decode for interactive chat."
            )
        if tok_s < 1.0:
            recommendations.append(
                "Main likely bottleneck is repeated full-prefill streaming; prioritize KV decode."
            )

        return {
            "schema_version": 1,
            "rift_product": self.product.name,
            "rift_phase": "R17",
            "created_unix_seconds": int(time.time()),
            "model_path": run.get("model_path"),
            "mode": run.get("mode"),
            "status": status,
            "usability_verdict": verdict.value,
            "bottleneck_classification": "survival_repeated_prefill_streaming"
            if run.get("mode") == RiftMode.SURVIVAL.value
            else "unknown",
            "decode_path": run.get("decode_path"),
            "mode_analysis": (run.get("plan") or {}).get("mode_analysis", {}),
            "metrics": {
                "load_seconds": run.get("load_seconds"),
                "generation_seconds": run.get("generation_seconds"),
                "total_seconds": run.get("total_seconds"),
                "generated_tokens": run.get("generated_tokens"),
                "tokens_per_second": tok_s,
                "first_token_seconds": run.get("first_token_seconds"),
                "p50_token_seconds": p50,
                "p95_token_seconds": p95,
                "per_token_latency_seconds": per_token,
                "backend_metrics": run.get("backend_metrics", {}),
            },
            "recommendations": recommendations,
            "run": run,
        }

    def _write_report_history(self, report: dict[str, Any]) -> Path:
        reports_dir = self.runtime_root / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        stamp = int(report.get("created_unix_seconds") or time.time())
        model_name = Path(str(report.get("model_path") or "model")).name or "model"
        target = reports_dir / f"{stamp}-{model_name}.riftreport.json"
        suffix = 1
        while target.exists():
            target = reports_dir / f"{stamp}-{model_name}-{suffix}.riftreport.json"
            suffix += 1
        target.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        return target

    def _doctor_next_actions(
        self,
        overall: str,
        inspection: dict[str, Any] | None,
        plan: dict[str, Any] | None,
    ) -> list[str]:
        if overall == "FAIL":
            return [
                "Fix FAIL checks before attempting to run the model.",
                "Use rift inspect for detailed model-readiness blockers.",
            ]
        if not inspection:
            return ["Run rift doctor --model <path> to include model compatibility checks."]
        mode_analysis = inspection.get("rift_mode_analysis", {})
        fit_mode = mode_analysis.get("best_hardware_fit_mode")
        executable_mode = mode_analysis.get("best_executable_mode")
        actions: list[str] = []
        if fit_mode != executable_mode and executable_mode == RiftMode.SURVIVAL.value:
            actions.append(
                f"Hardware/model fit looks {fit_mode}, but only SURVIVAL is executable today."
            )
            actions.append("Prioritize BALANCED runtime: KV decode plus VRAM/RAM tensor cache.")
        if plan and plan.get("recommended_mode") == RiftMode.SURVIVAL.value:
            actions.append("Use SURVIVAL for correctness/no-OOM smoke runs, not speed claims.")
        if not actions:
            actions.append("Current model/hardware pair is aligned with the executable RIFT mode.")
        return actions

    def _model_fingerprint(self, model_dir: Path) -> str:
        digest = hashlib.sha256()
        for path in sorted(p for p in model_dir.iterdir() if p.is_file()):
            stat = path.stat()
            digest.update(path.name.encode("utf-8", errors="replace"))
            digest.update(str(stat.st_size).encode("ascii"))
            digest.update(str(stat.st_mtime_ns).encode("ascii"))
        return digest.hexdigest()

    def _mode_analysis(
        self,
        report: dict[str, Any],
        hardware: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        hardware = hardware or self.hardware_profile()
        readiness = report.get("generation_readiness") or {}
        summary = report.get("rift_summary") or {}
        total_model_bytes = int(summary.get("total_model_bytes") or 0)
        native_ready = bool(readiness.get("ready"))
        free_vram = int(hardware.get("free_vram_bytes") or 0)
        total_vram = int(hardware.get("total_vram_bytes") or 0)
        total_host_ram = int(hardware.get("total_host_ram_bytes") or 0)
        runtime_reserve = max(2 * _GIB, int(total_vram * 0.20)) if total_vram else 2 * _GIB

        fast_hardware = (
            native_ready
            and total_model_bytes > 0
            and free_vram >= total_model_bytes + runtime_reserve
        )
        balanced_hardware = (
            native_ready
            and total_model_bytes > 0
            and (
                free_vram >= int(total_model_bytes * 0.75)
                or (total_vram + int(total_host_ram * 0.25)) >= total_model_bytes + runtime_reserve
            )
        )
        survival_hardware = native_ready

        if fast_hardware:
            fit_mode = RiftMode.FAST
        elif balanced_hardware:
            fit_mode = RiftMode.BALANCED
        elif survival_hardware:
            fit_mode = RiftMode.SURVIVAL
        else:
            fit_mode = RiftMode.REJECTED

        runtime_available = {
            RiftMode.FAST: False,
            RiftMode.BALANCED: False,
            RiftMode.SURVIVAL: native_ready,
            RiftMode.REJECTED: not native_ready,
        }
        executable = RiftMode.SURVIVAL if native_ready else RiftMode.REJECTED

        candidate_modes = {
            RiftMode.FAST.value: {
                "hardware_suitable": fast_hardware,
                "runtime_available": runtime_available[RiftMode.FAST],
                "available": fast_hardware and runtime_available[RiftMode.FAST],
                "reason": "Hardware has enough free VRAM for a mostly resident path."
                if fast_hardware
                else "Model does not meet the conservative free-VRAM reserve for FAST mode.",
            },
            RiftMode.BALANCED.value: {
                "hardware_suitable": balanced_hardware,
                "runtime_available": runtime_available[RiftMode.BALANCED],
                "available": balanced_hardware and runtime_available[RiftMode.BALANCED],
                "reason": "Hardware/model pair is suitable for BALANCED, but the runtime path is pending."
                if balanced_hardware
                else "Model does not meet the current BALANCED hardware-fit heuristic.",
            },
            RiftMode.SURVIVAL.value: {
                "hardware_suitable": survival_hardware,
                "runtime_available": runtime_available[RiftMode.SURVIVAL],
                "available": survival_hardware and runtime_available[RiftMode.SURVIVAL],
                "reason": "Existing native bounded-memory backend can execute this model."
                if native_ready
                else "Model is not native-run-ready for the current survival backend.",
            },
        }

        if fit_mode != executable and executable == RiftMode.SURVIVAL:
            note = (
                f"Hardware fit is {fit_mode.value}, but current executable backend is "
                "SURVIVAL until BALANCED/FAST runtimes are implemented."
            )
        elif executable == RiftMode.REJECTED:
            note = "No executable RIFT backend is ready for this model/hardware pair."
        else:
            note = f"Executable backend matches hardware fit: {executable.value}."

        return {
            "best_hardware_fit_mode": fit_mode.value,
            "best_executable_mode": executable.value,
            "recommended_executable_mode": executable.value,
            "runtime_gap": fit_mode.value != executable.value,
            "runtime_reserve_bytes": runtime_reserve,
            "free_vram_bytes": free_vram,
            "total_vram_bytes": total_vram,
            "total_host_ram_bytes": total_host_ram,
            "total_model_bytes": total_model_bytes,
            "candidate_modes": candidate_modes,
            "balanced_cache_plan": self._balanced_cache_plan(
                total_model_bytes=total_model_bytes,
                free_vram=free_vram,
                total_vram=total_vram,
                total_host_ram=total_host_ram,
                reserve_bytes=runtime_reserve,
                native_ready=native_ready,
            ),
            "execution_note": note,
        }

    def _balanced_cache_plan(
        self,
        *,
        total_model_bytes: int,
        free_vram: int,
        total_vram: int,
        total_host_ram: int,
        reserve_bytes: int,
        native_ready: bool,
    ) -> dict[str, Any]:
        usable_vram_cache = max(0, free_vram - reserve_bytes)
        planned_vram = min(total_model_bytes, usable_vram_cache)
        remaining = max(0, total_model_bytes - planned_vram)
        planned_host = min(remaining, int(total_host_ram * 0.25))
        cached = planned_vram + planned_host
        fraction = cached / total_model_bytes if total_model_bytes > 0 else 0.0
        return {
            "runtime_available": False,
            "native_ready": native_ready,
            "planned_vram_cache_bytes": planned_vram,
            "planned_host_cache_bytes": planned_host,
            "reserved_vram_bytes": reserve_bytes,
            "estimated_weight_cache_fraction": fraction,
            "would_reduce_disk_streaming": native_ready and fraction >= 0.50,
            "promotion_blocker": "BALANCED tensor cache runtime is not implemented yet.",
            "notes": [
                "This is a planning contract, not an executable cache path yet.",
                "Runtime promotion requires real KV decode and tensor-cache hit/miss accounting.",
            ],
        }

    def _annotate_inspection(self, report: dict[str, Any]) -> None:
        readiness = report.get("generation_readiness") or {}
        config = report.get("config") or {}
        topology = report.get("topology") or {}
        profile = report.get("profile") or {}
        policy = report.get("execution_policy") or {}
        issues = list(readiness.get("issues") or [])
        native_ready = bool(readiness.get("ready"))
        if native_ready:
            level = RiftCompatibilityLevel.NATIVE_RUN_READY
            recommended = RiftMode.SURVIVAL
        elif config and topology:
            level = RiftCompatibilityLevel.PLAN_READY
            recommended = RiftMode.REJECTED
        elif config:
            level = RiftCompatibilityLevel.INSPECT_ONLY
            recommended = RiftMode.REJECTED
        else:
            level = RiftCompatibilityLevel.UNSUPPORTED
            recommended = RiftMode.REJECTED

        report["rift_product"] = self.product.name
        report["rift_phase"] = "R9"
        report["rift_compatibility_level"] = level.value
        report["rift_summary"] = {
            "model_type": config.get("model_type", "unknown"),
            "family": config.get("family", "unknown"),
            "quantization": config.get("quantization", "unknown"),
            "layers": config.get("num_hidden_layers", 0),
            "hidden_size": config.get("hidden_size", 0),
            "vocab_size": config.get("vocab_size", 0),
            "total_model_bytes": topology.get("total_model_bytes", 0),
            "w_max_bytes": topology.get("w_max_bytes", 0),
            "output_head_mode": readiness.get("output_head_mode", "unknown"),
            "policy_supported": bool(policy.get("supported", False)),
            "profile_supported": bool(profile.get("supported", False)),
            "blocker_count": len(issues),
        }
        mode_analysis = self._mode_analysis(report)
        report["rift_recommended_initial_mode"] = mode_analysis["best_executable_mode"]
        report["rift_hardware_fit_mode"] = mode_analysis["best_hardware_fit_mode"]
        report["rift_mode_analysis"] = mode_analysis
        report["rift_native_modes"] = {
            mode: details["available"]
            for mode, details in mode_analysis["candidate_modes"].items()
        }
        report["rift_blockers"] = issues


__all__ = [
    "BackendKind",
    "DeploymentStrategy",
    "RiftCompatibilityLevel",
    "RiftEngine",
    "RiftMode",
    "RiftProductInfo",
    "UsabilityVerdict",
]
