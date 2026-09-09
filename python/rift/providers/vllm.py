"""vLLM provider adapter for RIFT."""

from __future__ import annotations

import os
import json
from pathlib import Path
import sys
from typing import Any

from ..adapters.contracts import ADAPTER_API_VERSION, AdapterManifest, BackendCapability
from .base import ProviderLifecycleMixin
from ..tuning_adapters import VLLM_PARAMETERS, accelerator_family
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
    # A Windows host does not identify the engine running inside Linux.
    # Retain V0 only for an explicitly selected legacy deployment.
    return tuning.get("container_image") == WINDOWS_V0_CONTAINER_IMAGE


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
        container_image: str | None = None,
        wsl_distribution: str | None = None,
    ) -> JsonDict:
        if not selected.get("available"):
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
        if runtime_mode == "container":
            command = [executable, "run", "--rm", "--pull", "never", "--network", "none", container_image or self._preferred_container_image()]
        elif runtime_mode == "wsl2":
            wsl = wsl_detection()
            command = [str(wsl.get("executable") or "wsl.exe")]
            if wsl_distribution:
                command.extend(["--distribution", wsl_distribution])
            command.extend(["--", executable, "-m", "vllm.entrypoints.openai.api_server"])
        return probe_command_flags(
            command,
            tuple(p.flag for p in VLLM_PARAMETERS if p.flag.startswith("--")) + tuple("--no-" + p.flag[2:] for p in VLLM_PARAMETERS if p.kind == "boolean") + (
                "--quantization",
                "--tensor-parallel-size",
                "--pipeline-parallel-size",
                "--max-model-len",
                "--gpu-memory-utilization",
                "--enable-prefix-caching",
                "--kv-cache-dtype",
            ),
        )

    def probe_tuning_runtime(self, launch_plan: JsonDict) -> JsonDict:
        """Probe the deployed execution environment, never an alternative runtime.

        Help only establishes argument syntax. Successful trial launch and
        qualification evidence are separate requirements.
        """
        tuning = launch_plan.get("tuning") or {}
        command = launch_plan.get("command") or []
        mode = tuning.get("runtime_mode", "native")
        executable = tuning.get("executable")
        if mode == "wsl2":
            executable = tuning.get("wsl_python")
        elif command:
            executable = command[0]
        return self._feature_probe(
            selected={"available": bool(executable), "executable": executable},
            runtime_mode=mode,
            command_style=tuning.get("command_style", "cli"),
            container_image=tuning.get("container_image") or launch_plan.get("container_image"),
            wsl_distribution=tuning.get("wsl_distribution"),
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
        selected_variant = variant.lower()
        existing = self.detect(search_root=target_dir)
        if selected_variant == "auto":
            if existing.get("available"):
                return {"backend": self.name, "installed": True, "changed": False, "detection": existing}
            if os.name == "nt" and container_runtime_detection().get("available"):
                selected_variant = "container"
            elif os.name == "nt" and wsl_detection().get("available"):
                selected_variant = "wsl2"
            else:
                selected_variant = "isolated-python"
        else:
            # An explicit variant is an instruction to install/use that runtime.
            # Do not let an already-detected alternative (for example Docker)
            # short-circuit a requested WSL or native installation.
            desired_mode = "container" if selected_variant in ("container", "docker", "podman") else (
                "wsl2" if selected_variant in ("wsl", "wsl2") else "native"
            )
            if existing.get("available") and existing.get("runtime_mode") == desired_mode:
                return {"backend": self.name, "installed": True, "changed": False, "detection": existing}
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
        family = accelerator_family(hardware)
        size = int(model.get("size") or model.get("estimated_download_bytes") or 0)
        vram = int(hardware.get("total_host_ram_bytes") or 0) if family == "cpu" else int(hardware.get("total_vram_bytes") or 0)
        supported_format = fmt in self.manifest.capability.formats
        # Unknown size is an admissible planning state for local selectors
        # (the artifact may not exist yet); it is marked preliminary and must
        # be resolved by startup allocation before promotion.
        context = int(model.get("context_length") or model.get("max_model_len") or 4096)
        concurrency = int(model.get("concurrency") or 1)
        config = model.get("config") if isinstance(model.get("config"), dict) else {}
        layers = int(config.get("num_hidden_layers") or config.get("n_layer") or 0)
        hidden = int(config.get("hidden_size") or config.get("n_embd") or 0)
        kv_heads = int(config.get("num_key_value_heads") or config.get("num_attention_heads") or 0)
        head_dim = int(config.get("head_dim") or (hidden // max(1, int(config.get("num_attention_heads") or 1)))) if hidden else 0
        kv_bytes = 2  # effective baseline KV dtype is conservatively treated as fp16
        kv_estimate = (2 * layers * kv_heads * head_dim * kv_bytes * context * concurrency) if layers and kv_heads and head_dim else 0
        reserve = max(512 * 1024**2, int(vram * 0.08))
        required = size + kv_estimate + reserve
        fits = supported_format and vram > 0 and (size == 0 or required < int(vram * 0.92))
        reasons = []
        if not supported_format:
            reasons.append(f"format {fmt or 'unknown'} is not the preferred vLLM path in RIFT.")
        if size > 0 and not fits:
            reasons.append("Known artifact size and sufficient memory headroom are required; context-aware allocation must be validated at launch.")
        elif size == 0 and supported_format:
            reasons.append("Artifact size is unknown; storage and context-aware allocation must be validated before launch.")
        if not reasons:
            reasons.append(f"Preliminary {family} artifact fit; runtime allocation is not yet verified.")
        return {
            "backend": self.name,
            "fits": fits,
            "model_bytes": size,
            "accelerator_family": family,
            "fit_evidence": "context_aware_estimate" if kv_estimate else "preliminary_weight_capacity_only",
            "estimated_kv_bytes": kv_estimate,
            "estimated_required_bytes": required,
            "reserve_bytes": reserve,
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
        tuning = dict(tuning or {})
        family = str(tuning.get("accelerator_family") or accelerator_family(hardware))
        if family not in {"cuda", "rocm", "xpu", "cpu"}:
            raise ValueError("unsupported accelerator family")
        tuning["accelerator_family"] = family
        for parameter in VLLM_PARAMETERS:
            if parameter.name in tuning:
                parameter.validate(tuning[parameter.name])
                if family not in parameter.platforms:
                    raise ValueError(f"{parameter.name} cannot be used on {family}")
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
                "--name",
                container_name,
                "--ipc=host",
                "-p",
                f"{host}:{port}:{port}",
            ]
            if family == "cuda":
                args.extend(["--gpus", str(tuning.get("device_ids") or "all")])
            elif family == "rocm":
                args.extend(["--device", "/dev/kfd", "--device", "/dev/dri"])
            elif family == "xpu":
                args.extend(["--device", "/dev/dri"])
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
            if family != "cuda" and not tuning.get("container_image"):
                raise ValueError(f"{family} requires an explicitly selected compatible container image")
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
            args = [str(wsl["executable"])]
            if tuning.get("wsl_distribution"):
                args.extend(["--distribution", str(tuning["wsl_distribution"])])
            args.append("--")
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
        if family != "cpu" and not tuning.get("kv_cache_memory_bytes"):
            args.extend(["--gpu-memory-utilization", f"{gpu_util:.3f}"])
        # A saved plan pins the probe so tuning cannot borrow flags from a
        # newly discovered runtime in another environment.
        feature_probe = tuning.get("runtime_feature_probe") or detect.get("runtime_feature_probe") or {}
        flags = feature_probe.get("flags") or {}
        encoded = {"max_num_batched_tokens", "max_num_seqs", "gpu_memory_utilization"}
        for parameter in VLLM_PARAMETERS:
            if parameter.name not in tuning or parameter.name in encoded:
                continue
            value = tuning[parameter.name]
            parameter.validate(value)
            if family not in parameter.platforms:
                raise ValueError(f"{parameter.name} cannot be used on {family}")
            if parameter.flag.startswith("VLLM_"):
                if runtime_mode == "native":
                    process_env[parameter.flag] = str(value)
                elif runtime_mode == "container":
                    image_index = args.index(container_image)
                    args[image_index:image_index] = ["--env", f"{parameter.flag}={value}"]
                else:
                    pos = args.index("--") + 1
                    if args[pos] != "env":
                        args.insert(pos, "env")
                    args.insert(pos + 1, f"{parameter.flag}={value}")
                continue
            if flags.get(parameter.flag) is not True:
                raise ValueError(f"Installed runtime has not verified {parameter.flag}")
            if parameter.kind == "boolean":
                flag = parameter.flag if value else "--no-" + parameter.flag[2:]
                if not value and flags.get(flag) is not True:
                    raise ValueError(f"Installed runtime has not verified {flag}")
                args.append(flag)
            else:
                args.extend([parameter.flag, json.dumps(value, sort_keys=True) if isinstance(value, dict) else str(value)])
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
                **{p.name: tuning[p.name] for p in VLLM_PARAMETERS if p.name in tuning},
                "accelerator_family": family,
                "command_style": command_style,
                "runtime_mode": runtime_mode,
                **({"gpu_memory_utilization": gpu_util} if family != "cpu" and not tuning.get("kv_cache_memory_bytes") else {}),
                "max_num_seqs": max_seqs,
                "max_num_batched_tokens": max_batched_tokens,
                "dtype": str(tuning.get("dtype", "auto")),
                "generation_config": str(tuning.get("generation_config", "vllm")),
                "tensor_parallel_size": tensor_parallel_size,
                "vllm_use_v1": not disable_v1,
                "container_image": container_image if runtime_mode == "container" else None,
                "container_name": container_name if runtime_mode == "container" else None,
                "search_root": tuning.get("search_root"),
                "executable": executable,
                "wsl_python": wsl_python if runtime_mode == "wsl2" else None,
                "wsl_distribution": tuning.get("wsl_distribution"),
                "device_ids": tuning.get("device_ids"),
                "runtime_feature_probe": feature_probe,
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
        seed: int | None = None,
        temperature: float | None = None,
        ignore_eos: bool = False,
    ) -> JsonDict:
        return openai_benchmark(
            self.name,
            base_url=base_url,
            prompt=prompt,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
            seed=seed,
            temperature=temperature,
            ignore_eos=ignore_eos,
            stream=True,
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
        # Keep the known Windows-compatible image as the discovery fallback.
        # This is a runtime selection rule, not a blanket V0 decision: a
        # Linux/WSL/container plan may pin another image explicitly.
        if os.name == "nt":
            return WINDOWS_V0_CONTAINER_IMAGE
        return self.container_image

    def _unique(self, candidates: list[JsonDict]) -> list[JsonDict]:
        import json
        unique: list[JsonDict] = []
        seen = set()
        for candidate in candidates:
            key = json.dumps(candidate, sort_keys=True, default=str)
            if key not in seen:
                seen.add(key)
                unique.append(candidate)
        return unique
