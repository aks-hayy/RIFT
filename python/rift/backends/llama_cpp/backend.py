"""llama.cpp provider adapter for RIFT."""

from __future__ import annotations

import json
import copy
import os
import platform
from pathlib import Path
from pathlib import PurePosixPath
import re
import shutil
import subprocess
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen
import zipfile

from ...adapters.contracts import ADAPTER_API_VERSION, AdapterManifest, BackendCapability
from ...cuda_probe import probe_cuda_driver, probe_nvidia_gpu
from ...tuning_engine import TuningContract, generate_llama_candidates
from ...providers.base import ProviderLifecycleMixin
from ...runtime_paths import path_redirection_reason

JsonDict = dict[str, Any]


class LlamaCppProvider(ProviderLifecycleMixin):
    _capability_cache: dict[tuple[str, str], JsonDict] = {}
    name = "llama.cpp"
    release_api_url = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
    release_history_api_url = "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=20"
    manifest = AdapterManifest(
        adapter_id=name,
        display_name="llama.cpp",
        upstream_project="ggml-org/llama.cpp",
        adapter_version="1.0.0",
        adapter_api_version=ADAPTER_API_VERSION,
        kind="backend",
        capability=BackendCapability(
            tasks=("chat", "completion", "embeddings", "reranking", "vision-language"),
            formats=("gguf",),
            quantizations=("q2", "q3", "q4", "q5", "q6", "q8", "iq", "f16", "bf16"),
            operating_systems=("windows", "linux", "macos"),
            accelerators=("cpu", "cuda", "metal", "vulkan"),
            installation_methods=("release-archive", "native", "container"),
            endpoints=("openai", "embeddings", "reranking"),
            features=(
                "continuous-batching",
                "grammar-constrained-output",
                "speculative-decoding",
                "cpu-offload",
                "tensor-split",
                "multimodal-with-mmproj",
            ),
            security_boundaries=("external-process", "rift-gateway-recommended"),
            multi_gpu=True,
        ),
        evidence_status="verified_local",
        homepage="https://github.com/ggml-org/llama.cpp",
        description="Portable GGUF inference backend operated as an external llama-server process.",
    )

    def detect(self, *, search_root: str | None = None) -> JsonDict:
        checked: list[str] = []
        env_names = ("LLAMA_CPP_SERVER", "LLAMA_SERVER", "LLAMA_CPP_BIN")
        for name in env_names:
            checked.append(f"${name}")
            value = os.environ.get(name)
            if value and Path(value).is_file():
                return self._detected(value, checked, source=f"env:{name}")

        for executable in ("llama-server", "llama-server.exe"):
            checked.append(executable)
            found = shutil.which(executable)
            if found:
                return self._detected(found, checked, source="PATH")

        roots = []
        if search_root:
            roots.append(Path(search_root))
        roots.append(Path.cwd() / ".rift" / "backends" / "llama.cpp")
        for root in roots:
            for name in ("llama-server.exe", "llama-server"):
                candidate = root / name
                checked.append(str(candidate))
                if candidate.is_file():
                    return self._detected(str(candidate), checked, source=str(root))
            if root.exists():
                for candidate in root.rglob("llama-server.exe" if os.name == "nt" else "llama-server"):
                    checked.append(str(candidate))
                    if candidate.is_file():
                        return self._detected(str(candidate), checked, source=str(root))

        return {
            "backend": self.name,
            "available": False,
            "executable": None,
            "source": None,
            "checked": checked,
            "version": None,
            "license": "MIT",
        }

    def _detected(self, executable: str, checked: list[str], *, source: str) -> JsonDict:
        return {
            "backend": self.name,
            "available": True,
            "executable": executable,
            "source": source,
            "checked": checked,
            "version": self._version(executable),
            "license": "MIT",
        }

    def _version(self, executable: str) -> str | None:
        try:
            completed = subprocess.run(
                [executable, "--version"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception:
            return None
        text = (completed.stdout or completed.stderr or "").strip()
        return text.splitlines()[0][:200] if text else None

    def install_plan(self) -> JsonDict:
        return {
            "backend": self.name,
            "requires_permission": True,
            "license": "MIT",
            "official_sources": [
                "https://github.com/ggml-org/llama.cpp/releases",
                "https://github.com/ggml-org/llama.cpp",
            ],
            "windows": {
                "recommended": "Download the official release archive containing llama-server.exe and set LLAMA_CPP_SERVER.",
                "portable_target": ".rift/backends/llama.cpp/llama-server.exe",
            },
            "linux": {
                "recommended": "Install/build llama.cpp from the official repository and put llama-server on PATH.",
            },
            "notes": [
                "RIFT does not bundle llama.cpp by default.",
                "Automatic install downloads official release archives only after --allow-install.",
                "RIFT installs into .rift/backends/llama.cpp by default and does not mutate system PATH.",
            ],
        }

    def install(
        self,
        *,
        target_dir: str,
        variant: str = "auto",
        force: bool = False,
    ) -> JsonDict:
        target_input = Path(target_dir).expanduser()
        if reason := path_redirection_reason(target_input):
            return {"installed": False, "changed": False, "reason": f"backend target is unsafe: {reason}"}
        target = target_input.resolve(strict=False)
        existing = self.detect(search_root=str(target))
        if existing.get("available") and not force:
            return {
                "installed": True,
                "changed": False,
                "reason": "llama.cpp is already available",
                "detection": existing,
            }

        system = platform.system().lower()
        machine = platform.machine().lower()
        if system != "windows" or machine not in ("amd64", "x86_64"):
            return {
                "installed": False,
                "changed": False,
                "reason": "automatic llama.cpp install currently supports official Windows x64 release archives only",
                "install_plan": self.install_plan(),
            }

        previous_managed_paths: set[str] = set()
        initial_files: set[str] = set()
        if target.exists():
            if not target.is_dir():
                return {"installed": False, "changed": False, "reason": "backend target is not a directory"}
            redirected = next((path for path in target.rglob("*") if path_redirection_reason(path)), None)
            if redirected is not None:
                return {
                    "installed": False,
                    "changed": False,
                    "reason": f"backend target contains a symlink or reparse point: {redirected}",
                }
            existing_marker = target / "rift-install.json"
            if reason := path_redirection_reason(existing_marker):
                return {"installed": False, "changed": False, "reason": f"install marker path is unsafe: {reason}"}
            if existing_marker.is_file():
                try:
                    previous_record = json.loads(existing_marker.read_text(encoding="utf-8"))
                    previous_ownership = previous_record.get("managed_installation") or {}
                    previous_managed_paths = set(previous_ownership.get("managed_paths") or [])
                except (OSError, UnicodeError, json.JSONDecodeError, AttributeError):
                    return {"installed": False, "changed": False, "reason": "existing RIFT install marker is invalid"}
                if (
                    previous_record.get("backend") != self.name
                    or str(previous_record.get("target_dir") or "") != str(target)
                    or not previous_managed_paths
                ):
                    return {
                        "installed": False,
                        "changed": False,
                        "reason": "existing install target is not a verifiable RIFT-managed archive",
                    }
            initial_files = self._archive_target_files(target)
            unowned_files = initial_files - previous_managed_paths - {"rift-install.json"}
            if unowned_files:
                return {
                    "installed": False,
                    "changed": False,
                    "reason": "backend target contains files not owned by RIFT; choose a dedicated target",
                    "unowned_files": sorted(unowned_files)[:20],
                }
        target.mkdir(parents=True, exist_ok=True)
        if reason := path_redirection_reason(target):
            return {"installed": False, "changed": False, "reason": f"backend target is unsafe: {reason}"}
        selected_release = self._select_install_release(variant=variant)
        release = selected_release["release"]
        assets = selected_release["assets"]
        selected_assets = selected_release["selected_assets"]
        if not selected_assets:
            return {
                "installed": False,
                "changed": False,
                "reason": f"no suitable Windows x64 llama.cpp release asset was found for variant={variant}",
                "release": {
                    "tag_name": release.get("tag_name"),
                    "html_url": release.get("html_url"),
                },
                "available_assets": [asset.get("name") for asset in assets if asset.get("name")],
            }

        downloads_dir = target / "_downloads"
        if reason := path_redirection_reason(downloads_dir):
            return {"installed": False, "changed": False, "reason": f"download directory is unsafe: {reason}"}
        downloads_dir.mkdir(parents=True, exist_ok=True)
        extracted = []
        files_created_during_install: set[str] = set()
        for asset in selected_assets:
            name = str(asset["name"])
            url = str(asset["browser_download_url"])
            archive = downloads_dir / name
            if reason := path_redirection_reason(archive):
                return {"installed": False, "changed": False, "reason": f"download target is unsafe: {reason}"}
            archive_relative = archive.relative_to(target).as_posix()
            if archive.exists() and archive_relative not in previous_managed_paths:
                return {
                    "installed": False,
                    "changed": False,
                    "reason": "download target contains an unowned file",
                    "path": archive_relative,
                }
            self._download_asset(url, archive)
            if archive.suffix.lower() == ".zip":
                with zipfile.ZipFile(archive) as package:
                    for member in package.infolist():
                        relative = self._safe_archive_member(target, member.filename)
                        if relative is None:
                            continue
                        destination = target / Path(*PurePosixPath(relative).parts)
                        if (
                            destination.exists()
                            and relative not in previous_managed_paths
                            and relative not in files_created_during_install
                            and not destination.is_dir()
                        ):
                            return {
                                "installed": False,
                                "changed": False,
                                "reason": "archive would overwrite an unowned target file",
                                "path": relative,
                            }
                        if not member.is_dir():
                            files_created_during_install.add(relative)
                    package.extractall(target)
            else:
                asset_target = target / name
                asset_relative = asset_target.relative_to(target).as_posix()
                if asset_target.exists() and asset_relative not in previous_managed_paths:
                    return {
                        "installed": False,
                        "changed": False,
                        "reason": "archive asset would overwrite an unowned target file",
                        "path": asset_relative,
                    }
                shutil.copy2(archive, target / name)
            extracted.append({"name": name, "url": url, "bytes": archive.stat().st_size})

        detection = self._detect_target_server(target)
        install_record = {
            "backend": self.name,
            "installed": bool(detection.get("available")),
            "changed": True,
            "target_dir": str(target),
            "variant": variant,
            "managed_installation": {
                "managed_by": "RIFT",
                "backend_id": self.name,
                "install_type": "archive",
                "target": str(target),
                "managed_paths": sorted(
                    previous_managed_paths
                    | (self._archive_target_files(target) - initial_files)
                    | {"rift-install.json"}
                ),
            },
            "release": {
                "tag_name": release.get("tag_name"),
                "html_url": release.get("html_url"),
            },
            "assets": extracted,
            "detection": detection,
            "license": "MIT",
            "official_source": "https://github.com/ggml-org/llama.cpp/releases",
        }
        for probe_name in ("gpu_probe", "cuda_probe"):
            if probe_name in selected_release:
                install_record[probe_name] = selected_release[probe_name]
        install_record.setdefault(
            "gpu_probe",
            {
                "available": None,
                "status": "not_run",
                "reason": "hardware inventory is not used to override an explicit variant",
            },
        )
        install_record.setdefault(
            "cuda_probe",
            {
                "available": None,
                "device_count": None,
                "status": "not_run",
                "reason": "CUDA driver probing is only used for automatic variant selection",
            },
        )
        selected_cuda_asset = any(
            self._is_cuda_build_asset(str(asset.get("name") or ""))
            for asset in selected_assets
            if isinstance(asset, dict)
        )
        install_record["cuda_executable_probe"] = (
            self._probe_cuda_executable(detection.get("executable"))
            if selected_cuda_asset
            else {
                "available": False,
                "status": "not_applicable",
                "reason": "the selected llama.cpp archive is not a CUDA build",
            }
        )
        if not detection.get("available"):
            install_record["reason"] = "archives extracted but llama-server executable was not found"
        install_marker = target / "rift-install.json"
        if reason := path_redirection_reason(install_marker):
            return {"installed": False, "changed": False, "reason": f"install marker path is unsafe: {reason}"}
        install_marker.write_text(
            json.dumps(install_record, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return install_record

    @staticmethod
    def _archive_target_files(target: Path) -> set[str]:
        return {
            path.relative_to(target).as_posix()
            for path in target.rglob("*")
            if path.is_file() and not path.is_symlink()
        }

    @staticmethod
    def _safe_archive_member(target: Path, member: str) -> str | None:
        normalized = str(member or "").replace("\\", "/")
        path = PurePosixPath(normalized)
        if not normalized or path.is_absolute() or any(part in {".", ".."} for part in path.parts):
            raise ValueError(f"unsafe path in llama.cpp archive: {member}")
        if path.parts and ":" in path.parts[0]:
            raise ValueError(f"unsafe path in llama.cpp archive: {member}")
        if normalized.endswith("/"):
            return None
        destination = target.joinpath(*path.parts)
        resolved_target = target.resolve(strict=False)
        if reason := path_redirection_reason(destination):
            raise ValueError(f"unsafe path in llama.cpp archive: {member}: {reason}")
        try:
            destination.resolve(strict=False).relative_to(resolved_target)
        except ValueError as exc:
            raise ValueError(f"unsafe path in llama.cpp archive: {member}") from exc
        if any(parent.is_symlink() for parent in (destination, *destination.parents) if parent != target.parent):
            raise ValueError(f"archive path crosses a symlink or reparse point: {member}")
        return path.as_posix()

    def _latest_release_info(self) -> JsonDict:
        request = Request(self.release_api_url, headers={"User-Agent": "RIFT/1.0"})
        with urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("GitHub latest release response was not an object")
        return payload

    def _release_history_info(self) -> list[JsonDict]:
        request = Request(self.release_history_api_url, headers={"User-Agent": "RIFT/1.0"})
        with urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, list):
            raise ValueError("GitHub release history response was not an array")
        return [release for release in payload if isinstance(release, dict)]

    def _select_install_release(self, *, variant: str) -> dict[str, Any]:
        latest = self._latest_release_info()
        candidates = [latest]
        latest_assets = latest.get("assets", [])
        probes = self._probe_auto_cuda() if variant.lower() == "auto" else None
        latest_selected = self._select_windows_assets(
            latest_assets,
            variant=variant,
            _probe_results=probes,
        )
        if not latest_selected:
            candidates.extend(self._release_history_info())
        seen_tags: set[str] = set()
        for release in candidates:
            tag = str(release.get("tag_name") or release.get("html_url") or "")
            if tag in seen_tags:
                continue
            seen_tags.add(tag)
            assets = release.get("assets", [])
            selected_assets = (
                latest_selected
                if release is latest
                else self._select_windows_assets(assets, variant=variant, _probe_results=probes)
            )
            if selected_assets:
                result = {
                    "release": release,
                    "assets": assets,
                    "selected_assets": selected_assets,
                }
                if probes is not None:
                    result.update(probes)
                return result
        result = {"release": latest, "assets": latest_assets, "selected_assets": []}
        if probes is not None:
            result.update(probes)
        return result

    def _probe_auto_cuda(self) -> JsonDict:
        try:
            gpu_probe = probe_nvidia_gpu()
        except Exception as exc:
            gpu_probe = {
                "available": False,
                "inventory_available": False,
                "devices": [],
                "reason": f"NVIDIA GPU probe failed: {exc}",
            }
        if not bool(gpu_probe.get("available")):
            cuda_probe = {
                "available": False,
                "device_count": 0,
                "driver_library": None,
                "status": "skipped",
                "reason": "CUDA driver probe skipped because NVIDIA GPU inventory did not confirm a device",
            }
        else:
            try:
                cuda_probe = probe_cuda_driver()
            except Exception as exc:
                cuda_probe = {
                    "available": False,
                    "device_count": 0,
                    "driver_library": None,
                    "reason": f"CUDA driver probe failed: {exc}",
                }
        cuda_probe = dict(cuda_probe)
        cuda_probe["available"] = bool(
            cuda_probe.get("available") and int(cuda_probe.get("device_count") or 0) > 0
        )
        return {"gpu_probe": dict(gpu_probe), "cuda_probe": cuda_probe}

    def _select_windows_assets(
        self,
        assets: list[JsonDict],
        *,
        variant: str,
        _probe_results: JsonDict | None = None,
    ) -> list[JsonDict]:
        candidates = [
            asset
            for asset in assets
            if isinstance(asset, dict)
            and isinstance(asset.get("name"), str)
            and isinstance(asset.get("browser_download_url"), str)
            and asset["name"].lower().endswith(".zip")
        ]
        selected_variant = variant.lower()
        wants_cuda = selected_variant in ("cuda", "cuda12", "cuda13")
        wants_cpu = selected_variant == "cpu"
        if variant.lower() == "auto":
            probes = _probe_results if _probe_results is not None else self._probe_auto_cuda()
            wants_cuda = bool(
                (probes.get("gpu_probe") or {}).get("available")
                and (probes.get("cuda_probe") or {}).get("available")
                and int((probes.get("cuda_probe") or {}).get("device_count") or 0) > 0
            )
            wants_cpu = not wants_cuda

        primary_candidates = [
            asset
            for asset in candidates
            if "win" in str(asset["name"]).lower()
            and ("x64" in str(asset["name"]).lower() or "amd64" in str(asset["name"]).lower())
        ]
        binary_candidates = [
            asset
            for asset in primary_candidates
            if not self._is_runtime_support_asset(str(asset["name"]))
            and self._asset_matches_variant(str(asset["name"]), variant, wants_cuda=wants_cuda, wants_cpu=wants_cpu)
        ]
        if not binary_candidates:
            return []
        binary_candidates.sort(
            key=lambda asset: (
                "server" in str(asset["name"]).lower(),
                "bin" in str(asset["name"]).lower(),
                "cpu" in str(asset["name"]).lower() if wants_cpu else False,
            ),
            reverse=True,
        )
        primary = binary_candidates[0]
        selected = [primary]

        primary_name = str(primary["name"]).lower()
        if self._is_cuda_build_asset(primary_name):
            cuda_runtime_assets = [
                asset
                for asset in primary_candidates
                if asset is not primary
                and self._is_runtime_support_asset(str(asset["name"]))
                and self._asset_matches_variant(str(asset["name"]), variant, wants_cuda=True, wants_cpu=False)
            ]
            cuda_runtime_assets.sort(key=lambda asset: str(asset["name"]).lower())
            if cuda_runtime_assets:
                selected.append(cuda_runtime_assets[0])
        return selected

    @classmethod
    def _asset_matches_variant(
        cls,
        name: str,
        variant: str,
        *,
        wants_cuda: bool,
        wants_cpu: bool,
    ) -> bool:
        lower = name.lower()
        is_cuda = cls._is_cuda_build_asset(lower)
        if wants_cuda:
            if not is_cuda:
                return False
            if variant.lower() in ("cuda12", "cuda13"):
                return cls._cuda_asset_version(lower) == variant[-2:]
            return True
        if wants_cpu:
            return not is_cuda and not any(
                accelerator in lower
                for accelerator in ("vulkan", "opencl", "sycl", "hip", "rocm", "metal")
            )
        return False

    @staticmethod
    def _cuda_asset_version(name: str) -> str | None:
        match = re.search(r"(?:cuda(?:runtime)?|cudart|cu)[._ -]?(12|13)(?:[._-]|$)", name.lower())
        return match.group(1) if match else None

    def _detect_target_server(self, target: Path) -> JsonDict:
        """Detect only a llama-server executable contained in the just-installed target."""
        canonical_target = target.resolve(strict=False)
        names = ("llama-server.exe", "llama-server")
        checked: list[str] = []
        for name in names:
            direct = target / name
            checked.append(str(direct))
            candidates = [direct]
            if target.is_dir():
                candidates.extend(target.rglob(name))
            for candidate in candidates:
                if not candidate.is_file() or candidate.is_symlink():
                    continue
                try:
                    canonical = candidate.resolve(strict=True)
                    canonical.relative_to(canonical_target)
                except (OSError, ValueError):
                    continue
                if candidate not in (direct,):
                    checked.append(str(candidate))
                return self._detected(str(canonical), checked, source="rift-managed-install")
        return {
            "backend": self.name,
            "available": False,
            "executable": None,
            "source": None,
            "checked": checked,
            "version": None,
            "license": "MIT",
        }

    @staticmethod
    def _is_cuda_build_asset(name: str) -> bool:
        lower = name.lower()
        return (
            "cuda" in lower
            or re.search(r"\bcu(?:12|13)(?:[._-]|$)", lower) is not None
            or re.search(r"(?:^|[._ -])cudart[._ -]?(?:12|13)(?:[._-]|$)", lower) is not None
        )

    @staticmethod
    def _probe_cuda_executable(executable: str | None) -> JsonDict:
        if not executable:
            return {
                "available": False,
                "status": "unknown",
                "reason": "llama-server executable was not found for CUDA verification",
            }
        try:
            completed = subprocess.run(
                [str(executable), "--list-devices"],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
        except Exception as exc:
            return {
                "available": False,
                "status": "error",
                "executable": str(executable),
                "reason": f"llama-server --list-devices could not run: {exc}",
            }
        output = "\n".join(value for value in (completed.stdout, completed.stderr) if value).strip()
        if completed.returncode != 0:
            return {
                "available": False,
                "status": "error",
                "executable": str(executable),
                "returncode": completed.returncode,
                "reason": f"llama-server --list-devices exited with code {completed.returncode}",
                "output": output[-1000:],
            }

        lines = [line.strip() for line in output.splitlines() if line.strip()]
        header_index = next(
            (
                index
                for index, line in enumerate(lines)
                if re.search(r"available\s+devices\s*:|devices\s*:\s*$", line, re.IGNORECASE)
            ),
            None,
        )
        if header_index is None:
            return {
                "available": False,
                "status": "unknown",
                "executable": str(executable),
                "reason": "llama-server --list-devices output could not be parsed",
                "output": output[-1000:],
            }
        device_lines = lines[header_index + 1 :]
        cuda_devices = [
            line
            for line in device_lines
            if re.search(r"\bcuda(?:\d+)?\s*[:(\[]", line, re.IGNORECASE)
        ]
        if cuda_devices:
            return {
                "available": True,
                "status": "verified",
                "executable": str(executable),
                "devices": cuda_devices,
                "reason": None,
            }
        return {
            "available": False,
            "status": "verified",
            "executable": str(executable),
            "devices": device_lines,
            "reason": "llama-server --list-devices did not list a CUDA device",
        }

    def _is_runtime_support_asset(self, name: str) -> bool:
        lower = name.lower()
        return (
            lower.startswith("cudart-")
            or "cudart" in lower
            or "cuda-runtime" in lower
            or "runtime" in lower and "llama" not in lower
        )

    def _download_asset(self, url: str, target: Path) -> None:
        request = Request(url, headers={"User-Agent": "RIFT/1.0"})
        part = target.with_suffix(target.suffix + ".part")
        with urlopen(request, timeout=120) as response, part.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
        part.replace(target)

    def select_gguf(
        self,
        files: list[JsonDict],
        *,
        hardware: JsonDict,
        intent: str = "balanced",
        disk_budget_bytes: int | None = None,
    ) -> JsonDict:
        if not files:
            raise ValueError("no GGUF files were provided")
        total_vram = int(hardware.get("total_vram_bytes") or 0)
        total_ram = int(hardware.get("total_host_ram_bytes") or 0)
        preferred = self._preferred_quant_order(total_vram, intent=intent)
        memory_envelope = max(1, int(total_vram * 0.82 + total_ram * 0.20))
        scored = []
        for artifact in self._gguf_artifacts(files):
            path = str(artifact["path"])
            size = int(artifact.get("size") or 0)
            lower = path.lower()
            quant = str(artifact.get("quantization") or "unknown")
            quant_score = len(preferred) + 5
            for index, quant in enumerate(preferred):
                if quant in lower:
                    quant_score = index
                    break
            penalty = 0
            if "q2_" in lower or "q3_" in lower:
                penalty += 20
            if not artifact.get("complete", True):
                penalty += 100
            if size and size > memory_envelope:
                penalty += 35
            if disk_budget_bytes is not None and size and size > disk_budget_bytes:
                penalty += 200
            if not size:
                penalty += 8
            scored.append((quant_score + penalty, size or 10**18, path, artifact))
        scored.sort(key=lambda item: item[:3])
        chosen = dict(scored[0][3])
        size = int(chosen.get("size") or 0)
        chosen["disk_feasible"] = (
            None if disk_budget_bytes is None or not size else size <= disk_budget_bytes
        )
        chosen["memory_fit"] = None if not size else size <= memory_envelope
        chosen["decision"] = {
            "reason": [
                f"Selected {chosen.get('path')} using llama.cpp quant preference for this hardware.",
                f"Preference order: {', '.join(preferred)}.",
                (
                    f"Exact artifact size is {size} bytes across {chosen.get('shard_count', 1)} file(s)."
                    if size
                    else "Artifact size is unknown; download feasibility remains provisional."
                ),
            ],
            "rejected_alternatives": [
                {
                    "path": item[2],
                    "rank": rank + 2,
                    "quantization": item[3].get("quantization"),
                    "size": item[3].get("size"),
                }
                for rank, item in enumerate(scored[1:8])
            ],
        }
        return chosen

    def _preferred_quant_order(self, total_vram: int, *, intent: str = "balanced") -> list[str]:
        intent_key = str(intent or "balanced").lower()
        if intent_key in ("quality", "accuracy"):
            if total_vram <= 10 * 1024**3:
                return ["q5_k_m", "q6_k", "q4_k_m", "q5_k_s", "q4_k_s", "q8_0"]
            return ["q6_k", "q8_0", "q5_k_m", "q4_k_m", "q5_k_s"]
        if intent_key in ("speed", "performance"):
            return ["q4_k_s", "q4_k_m", "q3_k_m", "q3_k_s", "q5_k_s", "q5_k_m"]
        if total_vram <= 10 * 1024**3:
            return ["q4_k_m", "q5_k_m", "q4_k_s", "q5_k_s", "q6_k", "q8_0"]
        if total_vram <= 24 * 1024**3:
            return ["q5_k_m", "q6_k", "q4_k_m", "q8_0", "q5_k_s"]
        return ["q6_k", "q8_0", "q5_k_m", "q4_k_m"]

    def _gguf_artifacts(self, files: list[JsonDict]) -> list[JsonDict]:
        groups: dict[str, JsonDict] = {}
        for source in files:
            path = str(source.get("path") or source.get("name") or "")
            lower = path.lower()
            if not lower.endswith(".gguf") or "mmproj" in lower:
                continue
            shard = re.match(r"^(.*?)-(\d{5})-of-(\d{5})\.gguf$", path, re.IGNORECASE)
            key = path
            shard_index = 1
            shard_total = 1
            if shard:
                key = f"{shard.group(1)}-of-{shard.group(3)}"
                shard_index = int(shard.group(2))
                shard_total = int(shard.group(3))
            group = groups.setdefault(
                key,
                {
                    "path": path,
                    "selected_files": [],
                    "size": 0,
                    "size_known": True,
                    "shard_count": shard_total,
                    "seen_shards": set(),
                    "quantization": self._gguf_quantization(path),
                },
            )
            group["selected_files"].append(path)
            group["seen_shards"].add(shard_index)
            size = source.get("size")
            if isinstance(size, int) and size >= 0:
                group["size"] += size
            else:
                group["size_known"] = False
        artifacts: list[JsonDict] = []
        for group in groups.values():
            group["selected_files"] = sorted(group["selected_files"])
            group["path"] = group["selected_files"][0]
            group["complete"] = len(group.pop("seen_shards")) == int(group["shard_count"])
            if not group.pop("size_known"):
                group["size"] = 0
            artifacts.append(group)
        if not artifacts:
            raise ValueError("no usable GGUF model artifacts were provided")
        return artifacts

    def _gguf_quantization(self, path: str) -> str:
        lower = path.lower()
        match = re.search(
            r"(?:^|[-.])(iq\d(?:_[a-z0-9]+)+|q\d(?:_[a-z0-9]+)+|bf16|f16)(?:[-.]|$)",
            lower,
        )
        return match.group(1).upper() if match else "UNKNOWN"

    def model_fit(self, *, model: JsonDict, hardware: JsonDict) -> JsonDict:
        fmt = str(model.get("format") or "").lower()
        size = int(model.get("size") or model.get("estimated_download_bytes") or 0)
        total_vram = int(hardware.get("total_vram_bytes") or 0)
        total_ram = int(hardware.get("total_host_ram_bytes") or 0)
        supported_format = fmt == "gguf"
        fits = supported_format and (
            not size or size < max(total_vram + int(total_ram * 0.55), 1)
        )
        return {
            "backend": self.name,
            "fits": fits,
            "model_bytes": size,
            "reason": (
                "GGUF can run through llama.cpp with partial/offloaded layers."
                if fits
                else f"llama.cpp requires GGUF, and the artifact must fit the VRAM/host-RAM policy (format={fmt or 'unknown'})."
            ),
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
        executable = (
            tuning.get("executable")
            or self.detect(search_root=tuning.get("search_root")).get("executable")
            or "llama-server"
        )
        capabilities = self.probe_tuning_capabilities(str(executable))
        supported_flags = {str(item).lower().replace("_", "-") for item in capabilities.get("flags", ())}

        def supports(name: str) -> bool:
            return name in supported_flags or not capabilities.get("probed", False)
        gpu_layers = int(tuning.get("gpu_layers", 999))
        batch = int(tuning.get("batch", 512))
        ubatch = int(tuning.get("ubatch", 128))
        threads = int(tuning.get("threads", max(1, (os.cpu_count() or 4) // 2)))
        threads_batch = int(tuning.get("threads_batch", threads))
        parallel = int(tuning.get("parallel", concurrency))
        args = [
            str(executable),
            "-m",
            str(model_path),
            "--host",
            str(host),
            "--port",
            str(port),
            "--ctx-size",
            str(context_length),
            "--n-gpu-layers",
            str(gpu_layers),
            "--batch-size",
            str(batch),
            "--ubatch-size",
            str(ubatch),
            "--threads",
            str(threads),
            "--threads-batch",
            str(threads_batch),
            "--parallel",
            str(parallel),
        ]
        schema_file = str(
            tuning.get("json_schema_file")
            or tuning.get("structured_output_schema_file")
            or ""
        ).strip()
        structured_output: JsonDict | None = None
        if schema_file:
            if not Path(schema_file).is_file():
                raise ValueError(f"structured output schema file does not exist: {schema_file}")
            # A schema constraint is a correctness boundary, not an optional
            # optimization knob.  Never silently launch without it when an
            # exact runtime probe says the flag is unavailable.
            if not capabilities.get("probed", False) or not capabilities.get("supports_json_schema_file", False):
                raise ValueError(
                    "llama.cpp runtime does not provide a verified --json-schema-file capability"
                )
            # The exact llama.cpp build used by the workload path applies the
            # grammar to the Jinja assistant marker for some chat templates,
            # producing a 400 before generation.  Pure content parsing keeps
            # the launch-level JSON grammar on the generated payload while
            # remaining compatible with the OpenAI chat endpoint.
            if "no-jinja" in supported_flags:
                args.append("--no-jinja")
            args.extend(["--json-schema-file", schema_file])
            structured_output = {
                "mode": "json_schema_file",
                "schema_file": schema_file,
                "chat_template_mode": "no-jinja" if "no-jinja" in supported_flags else "default",
            }
        if capabilities.get("probed", False):
            for option in ("--threads-batch", "--parallel"):
                if option not in supported_flags:
                    while option in args:
                        index = args.index(option)
                        del args[index : index + 2]
        if tuning.get("flash_attn") is not None and supports("flash-attn"):
            args.extend(["--flash-attn", str(tuning["flash_attn"])])
        if tuning.get("poll") is not None and supports("poll"):
            args.extend(["--poll", str(int(tuning["poll"]))])
        if tuning.get("poll_batch") is not None and supports("poll-batch"):
            args.extend(["--poll-batch", str(int(tuning["poll_batch"]))])
        if tuning.get("cache_type_k") is not None and supports("cache-type-k"):
            args.extend(["--cache-type-k", str(tuning["cache_type_k"])])
        if tuning.get("cache_type_v") is not None and supports("cache-type-v"):
            args.extend(["--cache-type-v", str(tuning["cache_type_v"])])
        if tuning.get("continuous_batching") is not None and supports("cont-batching"):
            args.append("--cont-batching" if bool(tuning["continuous_batching"]) else "--no-cont-batching")
        if bool(tuning.get("mlock", False)) and supports("mlock"):
            args.append("--mlock")
        if bool(tuning.get("no_mmap", False)) and supports("no-mmap"):
            args.append("--no-mmap")
        def boolean_flag(key: str, positive: str, negative: str | None = None) -> None:
            if key not in tuning or tuning[key] is None or not supports(positive):
                return
            value = bool(tuning[key])
            flag = positive if value else negative
            if flag:
                args.append("--" + flag)

        boolean_flag("kv_unified", "kv-unified", "no-kv-unified")
        boolean_flag("kv_offload", "kv-offload", "no-kv-offload")
        boolean_flag("no_host", "no-host", None)
        boolean_flag("repack", "repack", "no-repack")
        boolean_flag("op_offload", "op-offload", "no-op-offload")
        for key, flag in (("load_mode", "load-mode"), ("prio", "prio"),
                          ("cpu_mask", "cpu-mask"), ("cpu_range", "cpu-range"),
                          ("cpu_strict", "cpu-strict"), ("numa", "numa"),
                          ("device", "device"), ("tensor_split", "tensor-split"),
                          ("split_mode", "split-mode"), ("main_gpu", "main-gpu"),
                          ("n_cpu_ffn", "n-cpu-ffn"), ("fit", "fit"),
                          ("fit_target", "fit-target"), ("fit_ctx", "fit-ctx")):
            if key in tuning and tuning[key] is not None and supports(flag):
                args.extend(["--" + flag, str(tuning[key])])
        for key, flag in (
            ("spec_type", "spec-type"),
            ("spec_draft_model", "spec-draft-model"),
            ("spec_draft_n_max", "spec-draft-n-max"),
            ("spec_draft_n_min", "spec-draft-n-min"),
            ("spec_draft_p_min", "spec-draft-p-min"),
            ("spec_draft_p_split", "spec-draft-p-split"),
            ("spec_draft_ngl", "spec-draft-ngl"),
            ("spec_draft_device", "spec-draft-device"),
            ("spec_ngram_mod_n_min", "spec-ngram-mod-n-min"),
            ("spec_ngram_mod_n_max", "spec-ngram-mod-n-max"),
            ("spec_ngram_mod_n_match", "spec-ngram-mod-n-match"),
        ):
            # ``ngram_speculation`` is a user-facing switch, not a llama.cpp
            # flag.  False must remove inherited speculative arguments from a
            # previously optimized launch plan; draft-model speculation remains
            # independently controllable through its explicit draft settings.
            if (
                tuning.get("ngram_speculation") is False
                and (key == "spec_type" and tuning.get(key) == "ngram-mod"
                     or key.startswith("spec_ngram_mod_"))
            ):
                continue
            if key in tuning and tuning[key] is not None and supports(flag):
                args.extend(["--" + flag, str(tuning[key])])
        return {
            "backend": self.name,
            "model_path": str(model_path),
            "command": args,
            "display": " ".join(f'"{arg}"' if " " in arg else arg for arg in args),
            "api_base": f"http://{host}:{port}",
            "openai_base": f"http://{host}:{port}/v1",
            "host": host,
            "port": port,
            "context_length": context_length,
            "concurrency": concurrency,
            "tuning": {
                "gpu_layers": gpu_layers,
                "batch": batch,
                "ubatch": ubatch,
                "threads": threads,
                "threads_batch": threads_batch,
                "parallel": parallel,
                "flash_attn": tuning.get("flash_attn", "auto"),
                "poll": tuning.get("poll"),
                "poll_batch": tuning.get("poll_batch"),
                "cache_type_k": tuning.get("cache_type_k"),
                "cache_type_v": tuning.get("cache_type_v"),
                "continuous_batching": tuning.get("continuous_batching"),
                "mlock": bool(tuning.get("mlock", False)),
                "no_mmap": bool(tuning.get("no_mmap", False)),
                "kv_unified": tuning.get("kv_unified"),
                "kv_offload": tuning.get("kv_offload"),
                "no_host": tuning.get("no_host"),
                "repack": tuning.get("repack"),
                "load_mode": tuning.get("load_mode"),
                "op_offload": tuning.get("op_offload"),
                "prio": tuning.get("prio"),
                "cpu_mask": tuning.get("cpu_mask"),
                "cpu_range": tuning.get("cpu_range"),
                "cpu_strict": tuning.get("cpu_strict"),
                "numa": tuning.get("numa"),
                "device": tuning.get("device"),
                "tensor_split": tuning.get("tensor_split"),
                "split_mode": tuning.get("split_mode"),
                "main_gpu": tuning.get("main_gpu"),
                "n_cpu_ffn": tuning.get("n_cpu_ffn"),
                "fit": tuning.get("fit"),
                "fit_target": tuning.get("fit_target"),
                "fit_ctx": tuning.get("fit_ctx"),
                "spec_type": tuning.get("spec_type"),
                "spec_draft_model": tuning.get("spec_draft_model"),
                "spec_draft_n_max": tuning.get("spec_draft_n_max"),
                "spec_draft_n_min": tuning.get("spec_draft_n_min"),
                "spec_draft_p_min": tuning.get("spec_draft_p_min"),
                "spec_draft_p_split": tuning.get("spec_draft_p_split"),
                "spec_draft_ngl": tuning.get("spec_draft_ngl"),
                "spec_draft_device": tuning.get("spec_draft_device"),
                "spec_ngram_mod_n_min": tuning.get("spec_ngram_mod_n_min"),
                "spec_ngram_mod_n_max": tuning.get("spec_ngram_mod_n_max"),
                "spec_ngram_mod_n_match": tuning.get("spec_ngram_mod_n_match"),
                "ngram_speculation": bool(tuning.get("ngram_speculation", True)),
                "search_root": tuning.get("search_root"),
                "json_schema_file": schema_file or None,
            },
            "capabilities": capabilities,
            "structured_output": structured_output,
        }

    @staticmethod
    def _parse_tuning_capabilities(help_text: str) -> JsonDict:
        """Parse llama-server help deterministically into launch capabilities."""
        flags: set[str] = set()
        cache_types: dict[str, list[str]] = {}
        known_types = ("f16", "bf16", "q8_0", "q4_0", "q4_1", "iq4_nl", "q5_0", "q5_1", "q5_k", "q5_k_m", "q5_k_s")
        pending_cache: str | None = None
        for line in str(help_text or "").splitlines():
            names = re.findall(r"(?<![\w-])--([a-zA-Z][a-zA-Z0-9-]*)", line)
            for name in names:
                flags.add(name.lower())
            option_match = re.search(r"--cache-type-([kv])\b", line.lower())
            if option_match:
                pending_cache = f"cache_type_{option_match.group(1)}"
            elif names:
                pending_cache = None
            for suffix in ("k", "v"):
                if f"cache-type-{suffix}" in line.lower():
                    values = [value for value in known_types if re.search(rf"(?<![a-z0-9]){re.escape(value)}(?![a-z0-9])", line.lower())]
                    if values:
                        cache_types[f"cache_type_{suffix}"] = values
                    elif f"cache-type-{suffix}" in flags:
                        cache_types[f"cache_type_{suffix}"] = ["f16"]
            if pending_cache and "cache-type-" not in line.lower():
                values = [value for value in known_types if re.search(rf"(?<![a-z0-9]){re.escape(value)}(?![a-z0-9])", line.lower())]
                if values:
                    cache_types[pending_cache] = values
                    # The option declaration often contains only its default
                    # (f16), followed by an ``allowed values`` continuation.
                    # Consume the continuation and clear the pending key so a
                    # later default/help line cannot overwrite the full list.
                    if len(values) > 1 or "allowed values" in line.lower():
                        pending_cache = None
        supports_json_schema = "json-schema" in flags
        supports_json_schema_file = "json-schema-file" in flags
        return {
            "flags": flags,
            "cache_types": cache_types,
            **{key: list(values) for key, values in cache_types.items()},
            "supports_json_schema": supports_json_schema,
            "supports_json_schema_file": supports_json_schema_file,
        }

    @classmethod
    def probe_tuning_capabilities(cls, executable: str) -> JsonDict:
        """Probe one exact executable, caching by path identity/version metadata."""
        path = str(executable)
        try:
            stat = Path(path).stat()
            identity = f"{stat.st_mtime_ns}:{stat.st_size}"
        except OSError:
            identity = "missing"
        key = (path, identity)
        if key in cls._capability_cache:
            return copy.deepcopy(cls._capability_cache[key])
        try:
            result = subprocess.run([path, "--help"], capture_output=True, text=True, timeout=5, check=False)
            text = (result.stdout or "") + "\n" + (result.stderr or "")
            if result.returncode != 0 and not text.strip():
                raise OSError(f"help probe exited {result.returncode}")
            capabilities = cls._parse_tuning_capabilities(text)
            capabilities["probed"] = True
            capabilities["executable"] = path
        except (OSError, subprocess.SubprocessError, UnicodeError):
            capabilities = {
                "flags": {"batch-size", "ubatch-size", "threads", "threads-batch", "parallel", "flash-attn", "poll", "poll-batch", "cache-type-k", "cache-type-v", "cont-batching", "mlock", "no-mmap", "kv-unified", "no-kv-unified", "kv-offload", "no-kv-offload", "no-host", "repack", "no-repack", "load-mode", "op-offload", "no-op-offload", "prio", "cpu-mask", "cpu-range", "cpu-strict", "numa", "device", "tensor-split"},
                "cache_types": {}, "cache_type_k": list(("f16", "bf16", "q8_0", "q4_0", "q4_1", "iq4_nl", "q5_0", "q5_1", "q5_k", "q5_k_m", "q5_k_s")),
                "cache_type_v": list(("f16", "bf16", "q8_0", "q4_0", "q4_1", "iq4_nl", "q5_0", "q5_1", "q5_k", "q5_k_m", "q5_k_s")),
                "supports_json_schema": False, "supports_json_schema_file": False,
                "probed": False, "executable": path,
            }
        cls._capability_cache[key] = copy.deepcopy(capabilities)
        return copy.deepcopy(capabilities)

    def launch(self, launch_plan: JsonDict, *, log_path: str | None = None) -> JsonDict:
        args = [str(arg) for arg in launch_plan.get("command") or []]
        if not args:
            raise ValueError("launch_plan.command is required")
        stdout = subprocess.DEVNULL
        stderr = subprocess.STDOUT
        handle = None
        if log_path:
            Path(log_path).parent.mkdir(parents=True, exist_ok=True)
            handle = Path(log_path).open("ab")
            stdout = handle
            stderr = subprocess.STDOUT
        creationflags = 0
        if os.name == "nt":
            creationflags = (
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
            )
        try:
            try:
                process = subprocess.Popen(args, stdout=stdout, stderr=stderr, creationflags=creationflags)
            except OSError:
                process = subprocess.Popen(args, stdout=stdout, stderr=stderr)
        finally:
            if handle:
                handle.close()
        return {
            "backend": self.name,
            "pid": process.pid,
            "started_unix_seconds": int(time.time()),
            "api_base": launch_plan.get("api_base"),
            "openai_base": launch_plan.get("openai_base"),
        }

    def health(self, *, base_url: str, timeout_seconds: float = 2.0) -> JsonDict:
        urls = [f"{base_url.rstrip('/')}/health", f"{base_url.rstrip('/')}/v1/models"]
        errors = []
        for url in urls:
            try:
                request = Request(url, headers={"User-Agent": "RIFT/1.0"})
                with urlopen(request, timeout=timeout_seconds) as response:
                    body = response.read(4096).decode("utf-8", errors="replace")
                return {
                    "backend": self.name,
                    "healthy": 200 <= int(response.status) < 500,
                    "status_code": int(response.status),
                    "url": url,
                    "body_preview": body[:500],
                }
            except URLError as exc:
                errors.append(str(exc))
            except Exception as exc:
                errors.append(str(exc))
        return {"backend": self.name, "healthy": False, "errors": errors}

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
        payload = {
            "model": "rift-managed",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "stream": False,
        }
        if seed is not None:
            payload["seed"] = int(seed)
        if temperature is not None:
            payload["temperature"] = float(temperature)
        if ignore_eos:
            payload["ignore_eos"] = True
        data = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{base_url.rstrip('/')}/v1/chat/completions",
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "RIFT/1.0"},
        )
        started = time.perf_counter()
        with urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8", errors="replace")
        elapsed = max(time.perf_counter() - started, 1.0e-9)
        generated = self._count_generated_tokens(raw)
        parsed: JsonDict = {}
        try:
            decoded = json.loads(raw)
            parsed = decoded if isinstance(decoded, dict) else {}
        except json.JSONDecodeError:
            parsed = {}
        timings = parsed.get("timings") if isinstance(parsed.get("timings"), dict) else {}
        decode_tps_value = timings.get("predicted_per_second")
        decode_tps = float(decode_tps_value) if isinstance(decode_tps_value, (int, float)) else 0.0
        predicted_ms_value = timings.get("predicted_ms")
        predicted_seconds = (
            float(predicted_ms_value) / 1000.0
            if isinstance(predicted_ms_value, (int, float))
            else None
        )
        prompt_tps_value = timings.get("prompt_per_second")
        prompt_tps = (
            float(prompt_tps_value)
            if isinstance(prompt_tps_value, (int, float))
            else None
        )
        first_token_latency = (
            max(0.0, elapsed - predicted_seconds)
            if predicted_seconds is not None
            else None
        )
        return {
            "backend": self.name,
            "status_code": int(response.status),
            "elapsed_seconds": elapsed,
            "generated_tokens_estimate": generated,
            "tokens_per_second_estimate": (
                decode_tps if decode_tps > 0.0 else generated / elapsed if generated else None
            ),
            "decode_tokens_per_second": decode_tps or None,
            "prompt_tokens_per_second": prompt_tps,
            "time_to_first_token_seconds_estimate": first_token_latency,
            "backend_timings": timings,
            "response_preview": raw[:1000],
            "response_text": self._response_text(parsed),
            "text": self._response_text(parsed),
            "finish_reason": self._finish_reason(parsed),
        }

    @staticmethod
    def _response_text(payload: JsonDict) -> str:
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            return ""
        choice = choices[0]
        message = choice.get("message") if isinstance(choice.get("message"), dict) else choice
        return str(message.get("content") or message.get("text") or "")

    @staticmethod
    def _finish_reason(payload: JsonDict) -> str | None:
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            value = choices[0].get("finish_reason")
            return str(value) if value is not None else None
        return None

    def _count_generated_tokens(self, raw: str) -> int:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return max(1, len(re.findall(r"\S+", raw)))
        usage = payload.get("usage") if isinstance(payload, dict) else None
        if isinstance(usage, dict) and isinstance(usage.get("completion_tokens"), int):
            return int(usage["completion_tokens"])
        text = ""
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else {}
            if isinstance(message, dict):
                text = str(message.get("content") or "")
        return max(1, len(re.findall(r"\S+", text))) if text else 0

    def tuning_space(
        self,
        *,
        launch_plan: JsonDict,
        hardware: JsonDict,
        contract: JsonDict | TuningContract | None = None,
    ) -> list[JsonDict]:
        baseline = dict(launch_plan.get("tuning") or {})
        serving = launch_plan.get("serving") or {}
        serving_context = int(
            launch_plan.get("context_length")
            or serving.get("context_length")
            or 4096
        )
        concurrency = int(launch_plan.get("concurrency") or 1)
        model_path = str(launch_plan.get("model_path") or "model.gguf")
        if isinstance(contract, TuningContract):
            resolved_contract = contract
        else:
            contract_value = dict(contract or {})
            contract_value.update(
                {
                    "service": str(contract_value.get("service") or "unknown"),
                    "profile": str(contract_value.get("profile") or "speed"),
                    "model_path": str(contract_value.get("model_path") or model_path),
                    "context_length": int(contract_value.get("context_length") or serving_context),
                    "concurrency": int(contract_value.get("concurrency") or concurrency),
                }
            )
            for key in ("model_sha256", "weight_quantization", "cache_type_k", "cache_type_v"):
                if contract_value.get(key) is None:
                    contract_value.pop(key, None)
            resolved_contract = TuningContract.from_mapping(contract_value)
        executable = str(baseline.get("executable") or launch_plan.get("executable") or "")
        if not executable:
            search_root = str(
                baseline.get("search_root")
                or launch_plan.get("search_root")
                or ""
            )
            if search_root:
                detected = self.detect(search_root=search_root)
                executable = str(detected.get("executable") or "")
        executable = executable or "llama-server"
        capabilities = launch_plan.get("capabilities")
        if not isinstance(capabilities, dict):
            capabilities = self.probe_tuning_capabilities(executable)
        generation_capabilities = capabilities if capabilities.get("probed", False) else None
        candidates = generate_llama_candidates(
            baseline=baseline,
            contract=resolved_contract,
            physical_cores=max(1, int(hardware.get("physical_cores") or (os.cpu_count() or 4))),
            logical_processors=max(1, int(hardware.get("logical_processors") or (os.cpu_count() or 4))),
            total_vram_bytes=int(hardware.get("total_vram_bytes") or 0),
            capabilities=generation_capabilities,
        )
        return candidates

    def tune_candidates(self, *, launch_plan: JsonDict, hardware: JsonDict) -> list[JsonDict]:
        return self.tuning_space(launch_plan=launch_plan, hardware=hardware)




def create_backend() -> LlamaCppProvider:
    return LlamaCppProvider()

__all__ = ["LlamaCppProvider", "create_backend"]
