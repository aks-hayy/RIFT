"""SGLang provider adapter for RIFT."""

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


class SglangProvider(ProviderLifecycleMixin):
    name = "sglang"
    container_image = "lmsysorg/sglang:latest-runtime"
    manifest = AdapterManifest(
        adapter_id=name,
        display_name="SGLang",
        upstream_project="sgl-project/sglang",
        adapter_version="1.0.0",
        adapter_api_version=ADAPTER_API_VERSION,
        kind="backend",
        capability=BackendCapability(
            tasks=("chat", "completion", "structured", "tool-use", "vision-language"),
            formats=("safetensors", "awq", "gptq", "fp8"),
            quantizations=("awq", "gptq", "fp8", "fp16", "bf16"),
            operating_systems=("linux", "wsl2", "container"),
            accelerators=("cuda", "rocm"),
            installation_methods=("isolated-python", "container", "wsl2"),
            endpoints=("openai",),
            features=(
                "continuous-batching",
                "radix-prefix-cache",
                "tensor-parallel",
                "structured-output",
                "tool-use",
                "multimodal",
            ),
            security_boundaries=("external-process-or-container", "rift-gateway-recommended"),
            multi_gpu=True,
        ),
        evidence_status="implemented_unverified",
        homepage="https://github.com/sgl-project/sglang",
        description="Structured and prefix-heavy serving adapter for unmodified SGLang installations.",
    )

    def detect(self, *, search_root: str | None = None) -> JsonDict:
        isolated = isolated_executable_detection(search_root, ("sglang",))
        isolated_module = isolated_module_detection(search_root, "sglang")
        executable = executable_detection(("sglang", "sglang.exe"), ("SGLANG_SERVER", "SGLANG_BIN"))
        module = module_detection("sglang")
        wsl_install = wsl_install_detection(search_root, "sglang")
        container = container_image_detection(self.container_image)
        isolated_cli = bool(isolated.get("available") and not isolated.get("python_only"))
        if isolated_cli:
            selected, runtime_mode, command_style = isolated, "native", "cli"
        elif isolated_module.get("available"):
            selected, runtime_mode, command_style = {
                "available": True,
                "executable": isolated_module["environment"]["python"],
                "source": "rift-isolated-environment",
            }, "native", "python-module"
        elif executable.get("available"):
            selected, runtime_mode, command_style = executable, "native", "cli"
        elif module.get("available"):
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
        if not version and module.get("version"):
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
        command = (
            [executable, "launch_server"]
            if command_style == "cli"
            else [executable, "-m", "sglang.launch_server"]
        )
        return probe_command_flags(
            command,
            (
                "--quantization",
                "--tp",
                "--mem-fraction-static",
                "--context-length",
                "--chunked-prefill-size",
                "--enable-hierarchical-cache",
                "--reasoning-parser",
                "--tool-call-parser",
            ),
        )

    def _platform_notes(self) -> list[str]:
        notes = ["Best supported on Linux with CUDA GPUs; SGLang docs recommend Linux for CUDA serving."]
        if os.name == "nt":
            notes.append("Native Windows execution is not treated as production-supported by RIFT; prefer WSL2 or Docker.")
        return notes

    def install_plan(self) -> JsonDict:
        return {
            "backend": self.name,
            "requires_permission": True,
            "license": "Apache-2.0",
            "official_sources": [
                "https://docs.sglang.io/docs/get-started/install",
                "https://github.com/sgl-project/sglang",
            ],
            "recommended": {
                "linux_cuda": "python -m pip install --pre sglang",
                "docker": "Use the official lmsysorg/sglang image for production-style isolation.",
                "windows": "Use WSL2/Linux or Docker; RIFT will not silently install SGLang on native Windows.",
            },
            "notes": [
                "Automatic install runs only after --allow-install.",
                "RIFT uses the documented python -m sglang.launch_server entrypoint.",
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
            result = install_container_image(self.container_image)
        elif selected_variant in ("wsl", "wsl2"):
            result = install_python_packages_wsl(
                ["sglang"],
                target_dir=target_dir,
                adapter_id=self.name,
                pre=True,
                force=force,
            )
        else:
            unsupported = python_unsupported_on_windows(self.name)
            if unsupported:
                unsupported["install_plan"] = self.install_plan()
                return unsupported
            result = install_python_packages_isolated(
                ["sglang"], target_dir=target_dir, pre=selected_variant in ("pre", "nightly"), force=force
            )
        detection = self.detect(search_root=target_dir)
        return {
            "backend": self.name,
            "installed": bool(detection.get("available")),
            "changed": bool(result.get("changed", result.get("returncode") == 0)),
            "installer": result,
            "variant": selected_variant,
            "detection": detection,
            "install_plan": self.install_plan(),
        }

    def model_fit(self, *, model: JsonDict, hardware: JsonDict) -> JsonDict:
        fmt = str(model.get("format") or "").lower()
        cuda = bool(hardware.get("cuda_available", False))
        supported_format = fmt in self.manifest.capability.formats
        fits = cuda and supported_format
        reason = (
            "SGLang is a strong external backend for structured/prefix-heavy CUDA serving."
            if fits
            else "SGLang requires CUDA plus a Hugging Face/SafeTensors style model in this RIFT adapter."
        )
        return {"backend": self.name, "fits": fits, "reason": reason}

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
        del hardware
        tuning = tuning or {}
        detect = self.detect(search_root=tuning.get("search_root"))
        runtime_mode = str(tuning.get("runtime_mode") or detect.get("runtime_mode") or "native").lower()
        executable = str(tuning.get("executable") or detect.get("executable") or sys.executable)
        command_style = str(tuning.get("command_style") or detect.get("command_style") or "python-module")
        mem_fraction = float(tuning.get("mem_fraction_static", 0.72 if os.name == "nt" else 0.80))
        if runtime_mode == "container":
            runtime = container_runtime_detection()
            if not runtime.get("available"):
                raise ValueError("container runtime requested but Docker/Podman was not detected")
            model = Path(model_path)
            args = [str(runtime["executable"]), "run", "--rm", "--gpus", "all", "--ipc=host", "-p", f"{port}:{port}"]
            if os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN"):
                args.extend(["--env", "HF_TOKEN"])
            container_model = str(model_path)
            if model.exists():
                model = model.resolve()
                mount_root = model if model.is_dir() else model.parent
                container_model = "/models" if model.is_dir() else f"/models/{model.name}"
                args.extend(["-v", f"{mount_root}:/models:ro"])
            args.extend(
                [
                    str(tuning.get("container_image") or self.container_image),
                    "python3", "-m", "sglang.launch_server",
                ]
            )
            model_path = container_model
            command_style = "container"
        elif runtime_mode == "wsl2":
            wsl = wsl_detection()
            if not wsl.get("available"):
                raise ValueError("WSL2 runtime requested but WSL was not detected")
            linux_model_path = tuning.get("wsl_model_path") or (
                windows_path_to_wsl(model_path) if Path(model_path).exists() else model_path
            )
            if not linux_model_path:
                raise ValueError("model path could not be translated for the WSL2 launch path")
            wsl_python = str((detect.get("wsl_install") or {}).get("python") or tuning.get("wsl_python") or "python3")
            args = [str(wsl["executable"]), "--", wsl_python, "-m", "sglang.launch_server"]
            model_path = str(linux_model_path)
            command_style = "wsl2"
        elif command_style == "cli":
            args = [executable, "launch_server"]
        else:
            args = [executable, "-m", "sglang.launch_server"]
        args.extend(
            [
                "--model-path",
                str(model_path),
                "--host",
                "0.0.0.0" if runtime_mode in ("container", "wsl2") else str(host),
                "--port",
                str(port),
                "--context-length",
                str(context_length),
                "--mem-fraction-static",
                f"{mem_fraction:.3f}",
            ]
        )
        if tuning.get("log_level"):
            args.extend(["--log-level", str(tuning["log_level"])])
        tensor_parallel_size = int(tuning.get("tensor_parallel_size", 1))
        if tensor_parallel_size > 1:
            args.extend(["--tp", str(tensor_parallel_size)])
        if tuning.get("quantization"):
            args.extend(["--quantization", str(tuning["quantization"])])
        return {
            "backend": self.name,
            "model_path": str(model_path),
            "command": args,
            "display": quote_command(args),
            "api_base": f"http://{host}:{port}",
            "openai_base": f"http://{host}:{port}/v1",
            "host": host,
            "port": port,
            "context_length": context_length,
            "concurrency": concurrency,
            "tuning": {
                "mem_fraction_static": mem_fraction,
                "context_length": context_length,
                "concurrency": concurrency,
                "command_style": command_style,
                "runtime_mode": runtime_mode,
                "tensor_parallel_size": tensor_parallel_size,
                "search_root": tuning.get("search_root"),
                **({"log_level": str(tuning["log_level"])} if tuning.get("log_level") else {}),
                **({"quantization": str(tuning["quantization"])} if tuning.get("quantization") else {}),
            },
        }

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
        fractions = [0.62, 0.70, 0.76] if vram <= 10 * 1024**3 else [0.76, 0.82, 0.88]
        candidates = []
        for fraction in fractions:
            candidate = dict(baseline)
            candidate["mem_fraction_static"] = fraction
            candidates.append(candidate)
        for level in ("warning", "info"):
            candidate = dict(baseline)
            candidate["log_level"] = level
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
