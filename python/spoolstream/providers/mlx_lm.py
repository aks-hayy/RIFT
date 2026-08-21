"""MLX-LM backend adapter owned by RIFT."""

from __future__ import annotations

import os
import platform
import sys
from typing import Any

from ..adapters.contracts import ADAPTER_API_VERSION, AdapterManifest, BackendCapability
from .base import ProviderLifecycleMixin
from .openai_backend import (
    JsonDict,
    executable_detection,
    install_python_packages_isolated,
    isolated_executable_detection,
    isolated_module_detection,
    launch_process,
    module_detection,
    openai_benchmark,
    openai_health,
    probe_command_flags,
    quote_command,
    run_version_command,
)


class MlxLmProvider(ProviderLifecycleMixin):
    name = "mlx-lm"
    manifest = AdapterManifest(
        adapter_id=name,
        display_name="MLX-LM",
        upstream_project="ml-explore/mlx-lm",
        adapter_version="1.0.0",
        adapter_api_version=ADAPTER_API_VERSION,
        kind="backend",
        capability=BackendCapability(
            tasks=("chat", "completion"),
            formats=("mlx",),
            quantizations=("mlx", "2bit", "3bit", "4bit", "6bit", "8bit", "fp16", "bf16"),
            operating_systems=("macos",),
            accelerators=("metal",),
            installation_methods=("isolated-python",),
            endpoints=("openai",),
            features=("unified-memory", "prompt-caching", "speculative-decoding"),
            security_boundaries=("loopback-only", "rift-gateway-required-for-network-exposure"),
            multi_gpu=False,
        ),
        evidence_status="implemented_unverified_local_only",
        homepage="https://github.com/ml-explore/mlx-lm",
        description="Apple Silicon MLX-LM server adapter; RIFT gateway protection is required for managed exposure.",
    )

    def detect(self, *, search_root: str | None = None) -> JsonDict:
        isolated = isolated_executable_detection(search_root, ("mlx_lm.server", "mlx_lm"))
        isolated_module = isolated_module_detection(search_root, "mlx_lm")
        executable = executable_detection(
            ("mlx_lm.server", "mlx_lm"),
            ("MLX_LM_SERVER", "MLX_LM_BIN"),
        )
        module = module_detection("mlx_lm")
        if isolated.get("available") and not isolated.get("python_only"):
            selected, command_style = isolated, "cli"
        elif isolated_module.get("available"):
            selected, command_style = {
                "available": True,
                "executable": isolated_module["environment"]["python"],
                "source": "rift-isolated-environment",
            }, "python-module"
        elif executable.get("available"):
            selected, command_style = executable, "cli"
        elif module.get("available"):
            selected, command_style = {
                "available": True,
                "executable": sys.executable,
                "source": "python-module",
            }, "python-module"
        else:
            selected, command_style = {}, None
        available = bool(selected.get("available"))
        version = None
        if selected.get("available") and command_style == "cli":
            version = run_version_command([str(selected["executable"]), "--help"])
        if not version and isolated_module.get("version"):
            version = str(isolated_module["version"])
        if not version and module.get("version"):
            version = str(module["version"])
        supported_host = self._supported_host()
        feature_probe = self._feature_probe(selected, command_style)
        return {
            "backend": self.name,
            "available": available,
            "executable": selected.get("executable") if selected.get("available") else sys.executable if module.get("available") else None,
            "source": selected.get("source"),
            "checked": [*isolated.get("checked", []), *executable.get("checked", [])],
            "module": module,
            "isolated_module": isolated_module,
            "command_style": command_style,
            "version": version,
            "license": "MIT",
            "supported_host": supported_host,
            "security": {
                "raw_server_exposure": "local_development_only",
                "managed_requirement": "Route non-loopback access through the authenticated RIFT gateway.",
            },
            "adapter_manifest": self.manifest.to_dict(),
            "runtime_feature_probe": feature_probe,
        }

    @staticmethod
    def _feature_probe(selected: JsonDict, command_style: str | None) -> JsonDict:
        if not selected.get("available"):
            return {"probed": False, "reason": "MLX-LM is not installed."}
        executable = str(selected.get("executable") or "")
        command = [executable] if command_style == "cli" else [executable, "-m", "mlx_lm.server"]
        return probe_command_flags(
            command,
            ("--model", "--host", "--port", "--draft-model", "--num-draft-tokens"),
        )

    def install_plan(self) -> JsonDict:
        return {
            "backend": self.name,
            "requires_permission": True,
            "license": "MIT",
            "official_sources": [
                "https://github.com/ml-explore/mlx-lm",
                "https://pypi.org/project/mlx-lm/",
            ],
            "supported_host": self._supported_host(),
            "recommended": {
                "macos_apple_silicon": "Install mlx-lm into an isolated .rift/backends/mlx-lm/venv environment.",
            },
            "notes": [
                "Automatic installation runs only after --allow-install.",
                "The upstream HTTP server is kept on loopback and should be exposed through the RIFT gateway.",
            ],
        }

    def install(self, *, target_dir: str, variant: str = "auto", force: bool = False) -> JsonDict:
        del variant
        existing = self.detect(search_root=target_dir)
        if existing.get("available"):
            return {"backend": self.name, "installed": True, "changed": False, "detection": existing}
        host = self._supported_host()
        if not host["supported"]:
            return {
                "backend": self.name,
                "installed": False,
                "changed": False,
                "reason": host["reason"],
                "install_plan": self.install_plan(),
            }
        result = install_python_packages_isolated(["mlx-lm"], target_dir=target_dir, force=force)
        detection = self.detect(search_root=target_dir)
        return {
            "backend": self.name,
            "installed": bool(detection.get("available")),
            "changed": result["returncode"] == 0,
            "pip": result,
            "detection": detection,
            "install_plan": self.install_plan(),
        }

    def model_fit(self, *, model: JsonDict, hardware: JsonDict) -> JsonDict:
        fmt = str(model.get("format") or "").lower()
        host = self._supported_host(hardware)
        size = int(model.get("size") or model.get("total_bytes") or model.get("estimated_download_bytes") or 0)
        total_ram = int(hardware.get("total_host_ram_bytes") or (hardware.get("capacity") or {}).get("host_ram_bytes") or 0)
        supported_format = fmt == "mlx"
        memory_fit = not size or not total_ram or size <= int(total_ram * 0.72)
        fits = host["supported"] and supported_format and memory_fit
        reasons = [host["reason"]]
        if not supported_format:
            reasons.append(f"MLX-LM requires an MLX-compatible artifact, not {fmt or 'unknown'}.")
        if not memory_fit:
            reasons.append("Artifact exceeds the conservative unified-memory serving envelope.")
        if fits:
            reasons.append("MLX artifact fits the conservative Apple unified-memory policy.")
        return {"backend": self.name, "fits": fits, "model_bytes": size, "reason": " ".join(reasons)}

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
        if host not in ("127.0.0.1", "localhost", "::1") and not tuning.get("allow_direct_exposure"):
            raise ValueError("MLX-LM raw server must bind to loopback unless allow_direct_exposure is explicitly set")
        detection = self.detect(search_root=tuning.get("search_root"))
        command_style = str(tuning.get("command_style") or detection.get("command_style") or "python-module")
        executable = str(tuning.get("executable") or detection.get("executable") or sys.executable)
        if command_style == "cli":
            args = [executable]
            if not executable.lower().endswith("server"):
                args.append("server")
        else:
            args = [executable, "-m", "mlx_lm.server"]
        args.extend(["--model", str(model_path), "--host", str(host), "--port", str(port)])
        if tuning.get("draft_model"):
            args.extend(["--draft-model", str(tuning["draft_model"])])
        if tuning.get("num_draft_tokens") is not None:
            args.extend(["--num-draft-tokens", str(int(tuning["num_draft_tokens"]))])
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
            "security": "loopback_only_use_rift_gateway",
            "warnings": (
                ["MLX-LM raw server concurrency is not promoted as production-safe; route through the RIFT gateway."]
                if concurrency > 1
                else []
            ),
            "tuning": {
                "command_style": command_style,
                "draft_model": tuning.get("draft_model"),
                "num_draft_tokens": tuning.get("num_draft_tokens"),
                "search_root": tuning.get("search_root"),
            },
        }

    def launch(self, launch_plan: JsonDict, *, log_path: str | None = None) -> JsonDict:
        return launch_process(self.name, launch_plan, log_path=log_path)

    def health(self, *, base_url: str, timeout_seconds: float = 2.0) -> JsonDict:
        return openai_health(self.name, base_url=base_url, timeout_seconds=timeout_seconds)

    def benchmark(self, *, base_url: str, prompt: str, max_tokens: int, timeout_seconds: float = 60.0) -> JsonDict:
        return openai_benchmark(self.name, base_url=base_url, prompt=prompt, max_tokens=max_tokens, timeout_seconds=timeout_seconds)

    def tune_candidates(self, *, launch_plan: JsonDict, hardware: JsonDict) -> list[JsonDict]:
        del hardware
        baseline = dict(launch_plan.get("tuning") or {})
        candidates = [baseline]
        if baseline.get("draft_model"):
            for count in (2, 3, 4):
                candidate = dict(baseline)
                candidate["num_draft_tokens"] = count
                candidates.append(candidate)
        return candidates

    @staticmethod
    def _supported_host(hardware: JsonDict | None = None) -> JsonDict:
        identity = (hardware or {}).get("identity") if isinstance((hardware or {}).get("identity"), dict) else {}
        system = str(identity.get("os") or platform.system()).lower()
        machine = str(identity.get("architecture") or platform.machine()).lower()
        supported = system in ("darwin", "macos") and machine in ("arm64", "aarch64")
        return {
            "supported": supported,
            "os": system,
            "architecture": machine,
            "reason": (
                "Apple Silicon host is supported by this MLX-LM adapter."
                if supported
                else "MLX-LM adapter currently targets Apple Silicon macOS hosts."
            ),
        }


__all__ = ["MlxLmProvider"]
