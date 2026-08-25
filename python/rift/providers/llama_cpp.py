"""llama.cpp provider adapter for RIFT."""

from __future__ import annotations

import json
import os
import platform
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen
import zipfile

from ..adapters.contracts import ADAPTER_API_VERSION, AdapterManifest, BackendCapability
from .base import ProviderLifecycleMixin

JsonDict = dict[str, Any]


class LlamaCppProvider(ProviderLifecycleMixin):
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
        target = Path(target_dir)
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

        target.mkdir(parents=True, exist_ok=True)
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
        downloads_dir.mkdir(parents=True, exist_ok=True)
        extracted = []
        for asset in selected_assets:
            name = str(asset["name"])
            url = str(asset["browser_download_url"])
            archive = downloads_dir / name
            self._download_asset(url, archive)
            if archive.suffix.lower() == ".zip":
                with zipfile.ZipFile(archive) as package:
                    package.extractall(target)
            else:
                shutil.copy2(archive, target / name)
            extracted.append({"name": name, "url": url, "bytes": archive.stat().st_size})

        detection = self.detect(search_root=str(target))
        install_record = {
            "backend": self.name,
            "installed": bool(detection.get("available")),
            "changed": True,
            "target_dir": str(target),
            "variant": variant,
            "release": {
                "tag_name": release.get("tag_name"),
                "html_url": release.get("html_url"),
            },
            "assets": extracted,
            "detection": detection,
            "license": "MIT",
            "official_source": "https://github.com/ggml-org/llama.cpp/releases",
        }
        (target / "rift-install.json").write_text(
            json.dumps(install_record, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        if not detection.get("available"):
            install_record["reason"] = "archives extracted but llama-server executable was not found"
        return install_record

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
        if not self._select_windows_assets(latest_assets, variant=variant):
            candidates.extend(self._release_history_info())
        seen_tags: set[str] = set()
        for release in candidates:
            tag = str(release.get("tag_name") or release.get("html_url") or "")
            if tag in seen_tags:
                continue
            seen_tags.add(tag)
            assets = release.get("assets", [])
            selected_assets = self._select_windows_assets(assets, variant=variant)
            if selected_assets:
                return {
                    "release": release,
                    "assets": assets,
                    "selected_assets": selected_assets,
                }
        return {"release": latest, "assets": latest_assets, "selected_assets": []}

    def _select_windows_assets(self, assets: list[JsonDict], *, variant: str) -> list[JsonDict]:
        candidates = [
            asset
            for asset in assets
            if isinstance(asset, dict)
            and isinstance(asset.get("name"), str)
            and isinstance(asset.get("browser_download_url"), str)
            and asset["name"].lower().endswith(".zip")
        ]
        wants_cuda = variant.lower() in ("auto", "cuda", "cuda12", "cuda13")
        wants_cpu = variant.lower() == "cpu"
        if variant.lower() == "auto":
            wants_cuda = bool(os.environ.get("CUDA_PATH") or os.environ.get("CUDA_HOME"))
            wants_cpu = not wants_cuda

        def score(asset: JsonDict) -> int:
            name = str(asset["name"]).lower()
            value = 0
            if "win" in name:
                value += 20
            if "x64" in name or "amd64" in name:
                value += 20
            if "server" in name or "bin" in name:
                value += 5
            if wants_cpu:
                if "cuda" in name or "vulkan" in name or "opencl" in name or "sycl" in name or "hip" in name:
                    value -= 30
                if "cpu" in name:
                    value += 15
            if wants_cuda:
                if "cuda" in name or "cu12" in name or "cu13" in name:
                    value += 25
                if variant.lower() in ("cuda12", "auto") and ("cu12" in name or "cuda-12" in name or "cuda12" in name):
                    value += 12
                if variant.lower() == "cuda13" and ("cu13" in name or "cuda-13" in name or "cuda13" in name):
                    value += 12
                if "cudart" in name and "llama" not in name:
                    value -= 8
            return value

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
        ]
        if not binary_candidates:
            return []
        binary_candidates.sort(key=score, reverse=True)
        primary = binary_candidates[0]
        selected = [primary]

        primary_name = str(primary["name"]).lower()
        if "cuda" in primary_name or "cu12" in primary_name or "cu13" in primary_name:
            cuda_runtime_assets = [
                asset
                for asset in primary_candidates
                if asset is not primary
                and self._is_runtime_support_asset(str(asset["name"]))
            ]
            cuda_runtime_assets.sort(key=score, reverse=True)
            if cuda_runtime_assets:
                selected.append(cuda_runtime_assets[0])
        return selected

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
        gpu_layers = int(tuning.get("gpu_layers", 999))
        batch = int(tuning.get("batch", 512))
        ubatch = int(tuning.get("ubatch", 128))
        threads = int(tuning.get("threads", max(1, (os.cpu_count() or 4) // 2)))
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
        ]
        if bool(tuning.get("mlock", False)):
            args.append("--mlock")
        if bool(tuning.get("no_mmap", False)):
            args.append("--no-mmap")
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
                "mlock": bool(tuning.get("mlock", False)),
                "no_mmap": bool(tuning.get("no_mmap", False)),
                "search_root": tuning.get("search_root"),
            },
        }

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
    ) -> JsonDict:
        payload = {
            "model": "rift-managed",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "stream": False,
        }
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
        }

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

    def tune_candidates(self, *, launch_plan: JsonDict, hardware: JsonDict) -> list[JsonDict]:
        baseline = dict(launch_plan.get("tuning") or {})
        total_vram = int(hardware.get("total_vram_bytes") or 0)
        batches = [256, 512, 768] if total_vram <= 10 * 1024**3 else [512, 1024, 1536]
        candidates = []
        for batch in batches:
            candidate = dict(baseline)
            candidate["batch"] = batch
            candidate["ubatch"] = min(int(candidate.get("ubatch", 128)), batch)
            candidates.append(candidate)
        cpu_threads = os.cpu_count() or 4
        for threads in sorted({max(1, cpu_threads // 4), max(1, cpu_threads // 2), cpu_threads}):
            candidate = dict(baseline)
            candidate["threads"] = threads
            candidates.append(candidate)
        unique: list[JsonDict] = []
        seen = set()
        for candidate in candidates:
            key = tuple(sorted(candidate.items()))
            if key not in seen:
                seen.add(key)
                unique.append(candidate)
        return unique
