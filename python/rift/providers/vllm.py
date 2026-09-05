"""vLLM provider adapter for RIFT."""

from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Any

from ..adapters.contracts import ADAPTER_API_VERSION, AdapterManifest, BackendCapability
from .base import ProviderLifecycleMixin
from .openai_backend import (
    JsonDict,
    container_image_detection,
    container_runtime_detection,
    executable_detection,
    install_container_image,
    install_python_packages_isolated,
    install_python_packages_wsl,
    isolated_executable_detection,
    isolated_module_detection,
    launch_process,
    module_detection,
    openai_benchmark,
    openai_health,
    probe_command_flags,
    python_unsupported_on_windows,
    quote_command,
    run_version_command,
    windows_path_to_wsl,
    wsl_detection,
    wsl_install_detection,
)


_MODEL_FILE_SUFFIXES = frozenset(
    {".safetensors", ".bin", ".gguf", ".pt", ".pth", ".ckpt", ".onnx"}
)
WINDOWS_V0_CONTAINER_IMAGE = "vllm/vllm-openai:v0.17.1"


def _model_directory_reference(model_path: str) -> str:
    """Return the directory vLLM must inspect for config, tokenizer, and weights."""
    raw_path = str(model_path).strip()
    if not raw_path:
        raise ValueError("vLLM requires a model directory or model identifier")

    path = Path(raw_path)
    if path.exists():
        return str(path.parent if path.is_file() else path)

    filename = path.name.lower()
    if path.suffix.lower() in _MODEL_FILE_SUFFIXES or filename.endswith(".safetensors.index.json"):
        parent = str(path.parent)
        return parent if parent not in ("", ".") else "."
    return raw_path


def _vllm_v1_disabled(runtime_mode: str, tuning: JsonDict) -> bool:
    """Avoid vLLM V1 UVA initialization where this host path cannot provide UVA."""
    explicit = tuning.get("vllm_use_v1")
    if explicit is not None:
        return str(explicit).strip().lower() not in {"1", "true", "yes", "on"}
    return os.name == "nt" and runtime_mode in {"native", "container", "wsl2"}


class VllmProvider(ProviderLifecycleMixin):
    name = "vllm"
    container_image = "vllm/vllm-openai:latest"
    manifest = AdapterManifest(
        adapter_id=name,
        display_name="vLLM",
        upstream_project="vllm-project/vllm",
        adapter_version="1.0.0",
        adapter_api_version=ADAPTER_API_VERSION,
        kind="backend",
        capability=BackendCapability(
            tasks=("chat", "completion", "embeddings", "reranking", "vision-language"),
            formats=("safetensors", "awq", "gptq", "fp8"),
            quantizations=("awq", "gptq", "fp8", "fp16", "bf16"),
            operating_systems=("linux", "wsl2", "container"),
            accelerators=("cuda", "rocm", "xpu", "cpu"),
            installation_methods=("isolated-python", "container", "wsl2"),
            endpoints=("openai", "embeddings"),
            features=(
                "continuous-batching",
                "paged-attention",
                "tensor-parallel",
                "pipeline-parallel",
                "structured-output",
                "prefix-caching",
                "multimodal",
            ),
            security_boundaries=("external-process-or-container", "rift-gateway-recommended"),
            multi_gpu=True,
        ),
        evidence_status="implemented_unverified",
        homepage="https://github.com/vllm-project/vllm",
        description="High-throughput serving adapter for unmodified vLLM installations.",
    )

    def detect(self, *, search_root: str | None = None) -> JsonDict:
        isolated = isolated_executable_detection(search_root, ("vllm",))
        isolated_module = isolated_module_detection(search_root, "vllm")
        executable = executable_detection(("vllm", "vllm.exe"), ("VLLM_SERVER", "VLLM_BIN"))
        module = module_detection("vllm")
        wsl_install = wsl_install_detection(search_root, "vllm")
        container_image = self._preferred_container_image()
        container = container_image_detection(container_image)
        container["preferred_image"] = container_image
        isolated_cli = bool(isolated.get("available") and not isolated.get("python_only"))
        native_cli = bool(executable.get("available"))
        native_module = bool(module.get("available"))
        isolated_python = bool(isolated_module.get("available"))
        if isolated_cli:
            selected, runtime_mode, command_style = isolated, "native", "cli"
        elif isolated_python:
            selected, runtime_mode, command_style = {
                "available": True,
                "executable": isolated_module["environment"]["python"],
                "source": "rift-isolated-environment",
            }, "native", "python-module"
        elif native_cli:
            selected, runtime_mode, command_style = executable, "native", "cli"
        elif native_module:
            selected, runtime_mode, command_style = {
                "available": True,
                "executable": sys.executable,
                "source": "python-module",
            }, "native", "python-module"
        elif wsl_install.get("available"):
            selected, runtime_mode, command_style = {
                "available": True,
                "executable": wsl_install.get("python"),
                "source": "rift-wsl-isolated-environment",
            }, "wsl2", "python-module"
        elif container.get("image_available"):
            selected, runtime_mode, command_style = {
                "available": True,
                "executable": container.get("executable"),
                "source": "container-image",
            }, "container", "container"
        else:
            selected, runtime_mode, command_style = {}, None, None
        available = bool(selected.get("available"))
        version = None
        if available and command_style == "cli":
            version = run_version_command([str(selected["executable"]), "--version"])
        if not version and isolated_module.get("version"):
            version = str(isolated_module["version"])
        if not version and native_module and module.get("version"):
            version = str(module["version"])
        feature_probe = self._feature_probe(
            selected=selected,
            runtime_mode=runtime_mode,
            command_style=command_style,
        )
        return {
            "backend": self.name,
            "available": available,
            "executable": selected.get("executable") if selected.get("available") else sys.executable if module.get("available") else None,
            "source": selected.get("source"),
            "checked": [*isolated.get("checked", []), *executable.get("checked", [])],
            "module": module,
            "isolated_module": isolated_module,
            "command_style": command_style,
            "runtime_mode": runtime_mode,
            "version": version,
            "license": "Apache-2.0",
            "platform_notes": self._platform_notes(),
            "container": container,
            "wsl": wsl_detection(),
            "wsl_install": wsl_install,
            "adapter_manifest": self.manifest.to_dict(),
            "runtime_feature_probe": feature_probe,
        }

    def _feature_probe(
        self,
        *,
        selected: JsonDict,
        runtime_mode: str | None,
        command_style: str | None,
    ) -> JsonDict:
        if not selected.get("available") or runtime_mode != "native":
            return {
                "probed": False,
                "reason": "Runtime flags are probed after a native/isolated executable is available.",
            }
        executable = str(selected.get("executable") or "")
        if not executable:
            return {"probed": False, "reason": "No executable was selected."}
        command = (
            [executable, "-m", "vllm.entrypoints.openai.api_server"]
            if command_style == "python-module"
            else [executable, "serve"]
        )
        return probe_command_flags(
            command,
            (
                "--quantization",
                "--tensor-parallel-size",
                "--pipeline-parallel-size",
                "--max-model-len",
                "--gpu-memory-utilization",
                "--enable-prefix-caching",
                "--kv-cache-dtype",
            ),
        )

    def _platform_notes(self) -> list[str]:
        notes = ["Best supported on Linux with CUDA GPUs."]
        if os.name == "nt":
            notes.append("Native Windows execution is not treated as production-supported by RIFT; prefer WSL2 or Docker.")
        return notes

    def install_plan(self) -> JsonDict:
        return {
            "backend": self.name,
            "requires_permission": True,
            "license": "Apache-2.0",
            "official_sources": [
                "https://docs.vllm.ai/en/latest/getting_started/installation/",
                "https://github.com/vllm-project/vllm",
            ],
            "recommended": {
                "linux_cuda": "python -m pip install vllm",
                "docker": "Use the official vLLM Docker image when Python wheel compatibility is uncertain.",
                "windows": (
                    f"Use {WINDOWS_V0_CONTAINER_IMAGE} for Windows Docker/WSL GPU paths where vLLM V1 UVA is unavailable."
                ),
            },
            "notes": [
                "Automatic install runs only after --allow-install.",
                "RIFT does not bundle vLLM or mutate PATH.",
                "Large CUDA wheels may take time to download and install.",
                "vLLM 0.18 and newer no longer provide the V0 engine; the Windows compatibility image is pinned to v0.17.1.",
            ],
        }

    def install(self, *, target_dir: str, variant: str = "auto", force: bool = False) -> JsonDict:
        existing = self.detect(search_root=target_dir)
        if existing.get("available"):
            return {"backend": self.name, "installed": True, "changed": False, "detection": existing}
        selected_variant = variant.lower()
        if selected_variant == "auto":
            if os.name == "nt" and container_runtime_detection().get("available"):
                selected_variant = "container"
            elif os.name == "nt" and wsl_detection().get("available"):
                selected_variant = "wsl2"
            else:
                selected_variant = "isolated-python"
        if selected_variant in ("container", "docker", "podman"):
            container_image = self._preferred_container_image()
            result = install_container_image(container_image)
        elif selected_variant in ("wsl", "wsl2"):
            result = install_python_packages_wsl(
                ["vllm"],
                target_dir=target_dir,
                adapter_id=self.name,
                pre=False,
                force=force,
            )
        else:
            unsupported = python_unsupported_on_windows(self.name)
            if unsupported:
                unsupported["install_plan"] = self.install_plan()
                return unsupported
            result = install_python_packages_isolated(
                ["vllm"], target_dir=target_dir, pre=selected_variant in ("pre", "nightly"), force=force
            )
        detection = self.detect(search_root=target_dir)
        return {
            "backend": self.name,
            "installed": bool(detection.get("available")),
            "changed": bool(result.get("changed", result.get("returncode") == 0)),
            "installer": result,
            "variant": selected_variant,
            "container_image": container_image if selected_variant in ("container", "docker", "podman") else None,
            "detection": detection,
            "install_plan": self.install_plan(),
        }

    def model_fit(self, *, model: JsonDict, hardware: JsonDict) -> JsonDict:
        fmt = str(model.get("format") or "").lower()
        cuda = bool(hardware.get("cuda_available", False))
        size = int(model.get("size") or model.get("estimated_download_bytes") or 0)
        vram = int(hardware.get("total_vram_bytes") or 0)
        supported_format = fmt in self.manifest.capability.formats
        fits = cuda and supported_format and (not size or size < max(int(vram * 1.8), 1))
        reasons = []
        if not cuda:
            reasons.append("vLLM requires a supported accelerator for this RIFT provider path.")
        if not supported_format:
            reasons.append(f"format {fmt or 'unknown'} is not the preferred vLLM path in RIFT.")
        if size and vram and size >= int(vram * 1.8):
            reasons.append("model appears too large for practical vLLM serving on this GPU without distribution/offload.")
        if not reasons:
            reasons.append("CUDA SafeTensors/AWQ/GPTQ model can be served through vLLM when the backend is installed.")
        return {
            "backend": self.name,
            "fits": fits,
            "model_bytes": size,
            "reason": " ".join(reasons),
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
        model_reference = _model_directory_reference(model_path)
        detect = self.detect(search_root=tuning.get("search_root"))
        runtime_mode = str(tuning.get("runtime_mode") or detect.get("runtime_mode") or "native").lower()
        command_style = str(tuning.get("command_style") or detect.get("command_style") or "cli")
        executable = str(
            tuning.get("executable")
            or detect.get("executable")
            or (sys.executable if command_style == "python-module" else "vllm")
        )
        gpu_util = float(tuning.get("gpu_memory_utilization", self._default_gpu_util(hardware)))
        max_seqs = int(tuning.get("max_num_seqs", max(1, concurrency)))
        max_batched_tokens = int(tuning.get("max_num_batched_tokens", self._default_batched_tokens(hardware)))
        disable_v1 = _vllm_v1_disabled(runtime_mode, tuning)
        process_env = {"VLLM_USE_V1": "0"} if disable_v1 and runtime_mode == "native" else {}
        if runtime_mode == "container":
            runtime = container_runtime_detection()
            if not runtime.get("available"):
                raise ValueError("container runtime requested but Docker/Podman was not detected")
            model = Path(model_path)
            container_name = f"rift-vllm-{int(port)}"
            args = [
                str(runtime["executable"]),
                "run",
                "--rm",
                "--gpus",
                "all",
                "--name",
                container_name,
                "--ipc=host",
                "-p",
                f"{port}:{port}",
            ]
            if disable_v1:
                args.extend(["--env", "VLLM_USE_V1=0"])
            if os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN"):
                args.extend(["--env", "HF_TOKEN"])
            container_model = model_reference
            if model.exists():
                model = model.resolve()
                mount_root = model if model.is_dir() else model.parent
                container_model = "/models"
                args.extend(["-v", f"{mount_root}:/models:ro"])
            container_image = str(tuning.get("container_image") or self._preferred_container_image())
            args.extend(
                [
                    container_image,
                    container_model,
                ]
            )
            command_style = "container"
        elif runtime_mode == "wsl2":
            wsl = wsl_detection()
            if not wsl.get("available"):
                raise ValueError("WSL2 runtime requested but WSL was not detected")
            linux_model_path = tuning.get("wsl_model_path") or (
                windows_path_to_wsl(model_reference) if Path(model_reference).exists() else model_reference
            )
            if not linux_model_path:
                raise ValueError("model path could not be translated for the WSL2 launch path")
            wsl_python = str((detect.get("wsl_install") or {}).get("python") or tuning.get("wsl_python") or "python3")
            args = [str(wsl["executable"]), "--"]
            if disable_v1:
                args.extend(["env", "VLLM_USE_V1=0"])
            args.extend([wsl_python, "-m", "vllm.entrypoints.openai.api_server", str(linux_model_path)])
            command_style = "wsl2"
        elif command_style == "python-module":
            args = [
                executable,
                "-m",
                "vllm.entrypoints.openai.api_server",
                model_reference,
            ]
        else:
            args = [executable, "serve", model_reference]
        args.extend(
            [
                "--host",
                "0.0.0.0" if runtime_mode in ("container", "wsl2") else str(host),
                "--port",
                str(port),
                "--max-model-len",
                str(context_length),
                "--gpu-memory-utilization",
                f"{gpu_util:.3f}",
                "--max-num-seqs",
                str(max_seqs),
                "--max-num-batched-tokens",
                str(max_batched_tokens),
                "--dtype",
                str(tuning.get("dtype", "auto")),
                "--generation-config",
                str(tuning.get("generation_config", "vllm")),
            ]
        )
        quantization = tuning.get("quantization")
        if quantization:
            args.extend(["--quantization", str(quantization)])
        tensor_parallel_size = int(tuning.get("tensor_parallel_size", 1))
        if tensor_parallel_size > 1:
            args.extend(["--tensor-parallel-size", str(tensor_parallel_size)])
        return {
            "backend": self.name,
            "model_path": str(model_path),
            "model_reference": model_reference,
            "command": args,
            "env": process_env,
            "container_image": container_image if runtime_mode == "container" else None,
            "container_name": container_name if runtime_mode == "container" else None,
            "display": quote_command(args),
            "api_base": f"http://{host}:{port}",
            "openai_base": f"http://{host}:{port}/v1",
            "host": host,
            "port": port,
            "context_length": context_length,
            "concurrency": concurrency,
            "tuning": {
                "command_style": command_style,
                "runtime_mode": runtime_mode,
                "gpu_memory_utilization": gpu_util,
                "max_num_seqs": max_seqs,
                "max_num_batched_tokens": max_batched_tokens,
                "dtype": str(tuning.get("dtype", "auto")),
                "generation_config": str(tuning.get("generation_config", "vllm")),
                "tensor_parallel_size": tensor_parallel_size,
                "vllm_use_v1": not disable_v1,
                "container_image": container_image if runtime_mode == "container" else None,
                "container_name": container_name if runtime_mode == "container" else None,
                "search_root": tuning.get("search_root"),
                **({"quantization": quantization} if quantization else {}),
            },
        }

    def _default_gpu_util(self, hardware: JsonDict) -> float:
        vram = int(hardware.get("total_vram_bytes") or 0)
        return 0.78 if vram <= 10 * 1024**3 else 0.88

    def _default_batched_tokens(self, hardware: JsonDict) -> int:
        vram = int(hardware.get("total_vram_bytes") or 0)
        return 1024 if vram <= 10 * 1024**3 else 4096

    def launch(self, launch_plan: JsonDict, *, log_path: str | None = None) -> JsonDict:
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
        return openai_benchmark(
            self.name,
            base_url=base_url,
            prompt=prompt,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
        )

    def tune_candidates(self, *, launch_plan: JsonDict, hardware: JsonDict) -> list[JsonDict]:
        baseline = dict(launch_plan.get("tuning") or {})
        vram = int(hardware.get("total_vram_bytes") or 0)
        utils = [0.70, 0.76, 0.82] if vram <= 10 * 1024**3 else [0.82, 0.88, 0.92]
        tokens = [512, 1024, 1536] if vram <= 10 * 1024**3 else [2048, 4096, 8192]
        candidates = []
        for util in utils:
            candidate = dict(baseline)
            candidate["gpu_memory_utilization"] = util
            candidates.append(candidate)
        for max_tokens in tokens:
            candidate = dict(baseline)
            candidate["max_num_batched_tokens"] = max_tokens
            candidates.append(candidate)
        for max_seqs in sorted({1, int(baseline.get("max_num_seqs", 1)), 2, 4}):
            candidate = dict(baseline)
            candidate["max_num_seqs"] = max_seqs
            candidates.append(candidate)
        return self._unique(candidates)

    def _preferred_container_image(self) -> str:
        if os.name == "nt":
            return WINDOWS_V0_CONTAINER_IMAGE
        return self.container_image

    def _unique(self, candidates: list[JsonDict]) -> list[JsonDict]:
        unique: list[JsonDict] = []
        seen = set()
        for candidate in candidates:
            key = tuple(sorted(candidate.items()))
            if key not in seen:
                seen.add(key)
                unique.append(candidate)
        return unique
