"""Measurement-aware hardware discovery for the RIFT control plane."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any


JsonDict = dict[str, Any]
_GIB = 1024**3
_QUERY_CACHE: dict[str, Any] = {}


def _simulation_bytes(
    values: dict[str, Any],
    *,
    bytes_keys: tuple[str, ...],
    gib_keys: tuple[str, ...],
    required: bool = False,
    default: int | None = None,
) -> int:
    for key in bytes_keys:
        if key in values and values[key] not in (None, ""):
            value = int(float(values[key]))
            if value <= 0:
                raise ValueError(f"simulated {key} must be positive")
            return value
    for key in gib_keys:
        if key in values and values[key] not in (None, ""):
            value = float(values[key])
            if value <= 0:
                raise ValueError(f"simulated {key} must be positive")
            return int(value * _GIB)
    if required:
        joined = ", ".join((*bytes_keys, *gib_keys))
        raise ValueError(f"simulation requires one of: {joined}")
    return int(default or 0)


def _simulation_value(values: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in values and values[key] not in (None, ""):
            return values[key]
    return default


def _parse_simulation_spec(spec: str | dict[str, Any]) -> tuple[dict[str, Any], Any]:
    if isinstance(spec, dict):
        return {str(key).strip().lower().replace("-", "_"): value for key, value in spec.items()}, dict(spec)
    text = str(spec or "").strip()
    if not text:
        raise ValueError("--simulate-hardware requires a profile")
    candidate_path = Path(text)
    if candidate_path.is_file():
        try:
            payload = json.loads(candidate_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"could not read simulated hardware JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("simulated hardware JSON must contain an object")
        return _parse_simulation_spec(payload)
    if text.startswith("{"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid simulated hardware JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("simulated hardware JSON must contain an object")
        return _parse_simulation_spec(payload)
    values: dict[str, Any] = {}
    for item in text.split(","):
        key, separator, value = item.partition("=")
        if not separator or not key.strip() or not value.strip():
            raise ValueError(
                "simulated hardware must be JSON or comma-separated key=value pairs"
            )
        values[key.strip().lower().replace("-", "_")] = value.strip()
    return values, text


def simulate_hardware_profile(spec: str | dict[str, Any]) -> JsonDict:
    """Build a clearly-labelled hardware profile without touching the machine.

    Required inputs are GPU name, VRAM capacity, host RAM capacity, and free
    disk capacity. Free VRAM/RAM default to their capacities and are recorded as
    assumptions so simulated recommendations cannot be mistaken for measurements.
    """

    values, original = _parse_simulation_spec(spec)
    aliases = {
        "gpu": "device_name",
        "device": "device_name",
        "vram": "vram_gb",
        "gpu_memory_gb": "vram_gb",
        "ram": "ram_gb",
        "host_ram_gb": "ram_gb",
        "free_vram": "free_vram_gb",
        "free_ram": "free_ram_gb",
        "disk_free": "disk_free_gb",
        "disk": "disk_free_gb",
        "cores": "cpu_cores",
    }
    for source, target in aliases.items():
        if source in values and target not in values:
            values[target] = values[source]

    device_name = str(_simulation_value(values, "device_name", default="Simulated GPU"))
    total_vram = _simulation_bytes(
        values,
        bytes_keys=("total_vram_bytes",),
        gib_keys=("vram_gb", "total_vram_gb"),
        required=True,
    )
    total_ram = _simulation_bytes(
        values,
        bytes_keys=("total_host_ram_bytes", "host_ram_bytes"),
        gib_keys=("ram_gb", "total_ram_gb"),
        required=True,
    )
    disk_free = _simulation_bytes(
        values,
        bytes_keys=("disk_free_bytes",),
        gib_keys=("disk_free_gb",),
        required=True,
    )
    free_vram = _simulation_bytes(
        values,
        bytes_keys=("free_vram_bytes",),
        gib_keys=("free_vram_gb",),
        default=total_vram,
    )
    free_ram = _simulation_bytes(
        values,
        bytes_keys=("free_host_ram_bytes", "free_ram_bytes"),
        gib_keys=("free_ram_gb",),
        default=total_ram,
    )
    disk_total = _simulation_bytes(
        values,
        bytes_keys=("disk_total_bytes",),
        gib_keys=("disk_total_gb",),
        default=max(disk_free, 1_000 * _GIB),
    )
    if disk_total < disk_free:
        raise ValueError("simulated disk_total_gb cannot be smaller than disk_free_gb")
    if free_vram > total_vram or free_ram > total_ram:
        raise ValueError("simulated free memory cannot exceed total memory")

    os_value = str(_simulation_value(values, "os", "platform", default="linux")).strip().lower()
    os_name = {"win": "Windows", "windows": "Windows", "linux": "Linux", "mac": "Darwin", "macos": "Darwin"}.get(os_value, os_value.title())
    cpu_cores = int(float(_simulation_value(values, "cpu_cores", "logical_cpu_count", default=8)))
    if cpu_cores <= 0:
        raise ValueError("simulated cpu_cores must be positive")
    cuda_default = not any(token in device_name.lower() for token in ("apple", "m1", "m2", "m3", "m4", "cpu"))
    cuda_available = bool(_simulation_value(values, "cuda_available", "cuda", default=cuda_default))
    capability = str(_simulation_value(values, "compute_capability", default=""))
    if capability and "." in capability:
        major_text, minor_text = capability.split(".", 1)
        capability_major, capability_minor = int(major_text), int(minor_text)
    elif "5090" in device_name:
        capability_major, capability_minor = 12, 0
    elif "4090" in device_name or "4060" in device_name or "4080" in device_name:
        capability_major, capability_minor = 8, 9
    else:
        capability_major, capability_minor = 0, 0

    storage_path = str(_simulation_value(values, "storage_path", default="<simulated-storage>"))
    identity = {
        "hostname": "simulated-host",
        "os": os_name,
        "os_release": "simulated",
        "architecture": str(_simulation_value(values, "architecture", default="simulated")),
        "cpu_model": str(_simulation_value(values, "cpu_model", default="Simulated CPU")),
        "logical_cpu_count": cpu_cores,
        "physical_cpu_count": int(float(_simulation_value(values, "physical_cpu_count", default=cpu_cores))),
        "gpu": device_name,
        "cuda_device_id": int(float(_simulation_value(values, "cuda_device_id", default=0))),
    }
    capacity = {
        "host_ram_bytes": total_ram,
        "vram_bytes": total_vram,
        "disk_total_bytes": disk_total,
        "logical_cpu_count": cpu_cores,
    }
    pressure = {
        "host_ram_free_bytes": free_ram,
        "host_ram_used_percent": round((1.0 - free_ram / total_ram) * 100.0, 3),
        "vram_free_bytes": free_vram,
        "vram_used_percent": round((1.0 - free_vram / total_vram) * 100.0, 3),
        "disk_free_bytes": disk_free,
        "disk_used_percent": round((1.0 - disk_free / disk_total) * 100.0, 3),
        "observation_note": "Simulated values supplied by the user; no local pressure was measured.",
    }
    fingerprint_source = {
        "identity": identity,
        "capacity": capacity,
        "compute_capability": [capability_major, capability_minor],
        "simulation": original,
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_source, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    assumptions = []
    if "free_vram_gb" not in values and "free_vram_bytes" not in values:
        assumptions.append("free VRAM defaults to total VRAM")
    if "free_ram_gb" not in values and "free_ram_bytes" not in values and "free_host_ram_bytes" not in values:
        assumptions.append("free host RAM defaults to total host RAM")
    if "disk_total_gb" not in values and "disk_total_bytes" not in values:
        assumptions.append("disk total defaults to the larger of free disk and 1000 GiB")
    return {
        "schema_version": 2,
        "profile_kind": "simulated",
        "created_unix_seconds": time.time(),
        "device_name": device_name,
        "cuda_available": cuda_available,
        "cuda_device_id": identity["cuda_device_id"],
        "total_vram_bytes": total_vram,
        "free_vram_bytes": free_vram,
        "total_host_ram_bytes": total_ram,
        "free_host_ram_bytes": free_ram,
        "compute_capability_major": capability_major,
        "compute_capability_minor": capability_minor,
        "estimated_h2d_bandwidth_gbps": float(_simulation_value(values, "h2d_bandwidth_gbps", default=0.0)),
        "identity": identity,
        "capacity": capacity,
        "pressure": pressure,
        "storage": {
            "path": storage_path,
            "total_bytes": disk_total,
            "free_bytes": disk_free,
            "filesystem": "simulated",
            "media_type": str(_simulation_value(values, "media_type", default="simulated")),
            "measurement_note": "Simulated storage values; no local disk was inspected.",
        },
        "power_thermal": {"available": False, "measurement": "simulated"},
        "power_profile": {"available": False, "measurement": "simulated"},
        "execution_environments": {
            "native": {"available": True, "os": os_name.lower()},
            "wsl2": {"available": os_name == "Windows", "executable": None, "note": "Simulated platform capability."},
            "container": {"available": bool(_simulation_value(values, "container", default=False)), "runtime": None, "executable": None, "note": "Simulated container capability."},
        },
        "wsl_available": os_name == "Windows",
        "container_runtime_available": bool(_simulation_value(values, "container", default=False)),
        "calibration": {"available": False, "stale": True, "result": None, "measurement": "simulated"},
        "measurement_labels": {
            "capacity": "simulated",
            "current_pressure": "simulated",
            "disk_bandwidth": "not_measured",
            "h2d_bandwidth": "simulated",
            "thermal_power": "not_measured",
        },
        "rift_managed_occupancy": {
            "running_service_count": 0,
            "services": [],
            "resource_bytes": {"host_ram_bytes": 0, "vram_bytes": 0},
            "note": "Simulated profile has no local service attribution.",
        },
        "fingerprint": fingerprint,
        "simulation": {
            "enabled": True,
            "input": original,
            "assumptions": assumptions,
            "read_only": True,
        },
    }


def simulated_disk_capacity(profile: JsonDict, *, reserve_bytes: int) -> JsonDict:
    """Return disk feasibility data from a simulated profile."""

    storage = profile.get("storage") or {}
    pressure = profile.get("pressure") or {}
    total = int(storage.get("total_bytes") or 0)
    free = int(pressure.get("disk_free_bytes") or storage.get("free_bytes") or 0)
    reserve = max(0, int(reserve_bytes))
    return {
        "path": storage.get("path") or "<simulated-storage>",
        "total_bytes": total,
        "free_bytes": free,
        "used_bytes": max(0, total - free),
        "reserve_bytes": reserve,
        "usable_bytes": max(0, free - reserve),
        "simulated": True,
    }


class HardwareAnalyzer:
    """Enrich the native CUDA profile without confusing estimates with measurements."""

    def __init__(
        self,
        root: str | Path | None = None,
        *,
        data_root: str | Path | None = None,
        calibration_ttl_seconds: int = 7 * 86400,
    ) -> None:
        self.root = Path(root) if root else Path.cwd()
        self.rift_dir = Path(data_root) if data_root is not None else self.root / ".rift"
        self.calibration_path = self.rift_dir / "calibration" / "hardware.json"
        self.calibration_ttl_seconds = max(0, int(calibration_ttl_seconds))

    def analyze(self, native: JsonDict, *, state: JsonDict | None = None) -> JsonDict:
        now = time.time()
        capacity = self._capacity(native)
        pressure = self._pressure(native, capacity)
        calibration = self._read_calibration()
        age = None
        stale = True
        if calibration:
            age = max(0.0, now - float(calibration.get("created_unix_seconds") or 0.0))
            stale = age > self.calibration_ttl_seconds
        managed = self._managed_occupancy(state or {})
        environments = self._execution_environments()
        identity = {
            "hostname": platform.node() or os.environ.get("COMPUTERNAME") or "unknown",
            "os": platform.system() or os.name,
            "os_release": platform.release(),
            "architecture": platform.machine(),
            "cpu_model": self._cpu_model(),
            "logical_cpu_count": os.cpu_count() or 0,
            "physical_cpu_count": self._physical_cpu_count(),
            "gpu": native.get("device_name"),
            "cuda_device_id": native.get("cuda_device_id", 0),
        }
        fingerprint_source = {
            "identity": identity,
            "capacity": capacity,
            "compute_capability": [
                native.get("compute_capability_major"),
                native.get("compute_capability_minor"),
            ],
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_source, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return {
            **dict(native),
            "schema_version": 2,
            "profile_kind": "measured_and_observed",
            "created_unix_seconds": now,
            "identity": identity,
            "capacity": capacity,
            "pressure": pressure,
            "rift_managed_occupancy": managed,
            "storage": self._storage_profile(),
            "power_thermal": self._nvidia_runtime_state(),
            "power_profile": self._power_profile(),
            "execution_environments": environments,
            "wsl_available": environments["wsl2"]["available"],
            "container_runtime_available": environments["container"]["available"],
            "calibration": {
                "available": bool(calibration),
                "stale": stale,
                "age_seconds": age,
                "ttl_seconds": self.calibration_ttl_seconds,
                "result": calibration,
            },
            "measurement_labels": {
                "capacity": "observed",
                "current_pressure": "observed",
                "disk_bandwidth": "measured" if calibration else "not_measured",
                "h2d_bandwidth": (
                    "measured"
                    if str((calibration or {}).get("h2d", {}).get("measurement") or "").startswith("measured")
                    else "native_estimate"
                ),
                "thermal_power": "observed_when_available",
            },
            "fingerprint": fingerprint,
        }

    def calibrate(
        self,
        *,
        sample_bytes: int = 32 * 1024**2,
        force: bool = False,
        h2d_measurement: JsonDict | None = None,
    ) -> JsonDict:
        if sample_bytes < 1024**2:
            raise ValueError("sample_bytes must be at least 1 MiB")
        current = self._read_calibration()
        if current and not force:
            age = time.time() - float(current.get("created_unix_seconds") or 0.0)
            existing_h2d_measured = (current.get("h2d") or {}).get("measurement") == "measured_pinned_cuda_events"
            if age <= self.calibration_ttl_seconds and (h2d_measurement is None or existing_h2d_measured):
                return {**current, "reused": True, "age_seconds": max(0.0, age)}

        target_dir = self.rift_dir / "calibration"
        target_dir.mkdir(parents=True, exist_ok=True)
        block = bytes(1024 * 1024)
        sample_path: Path | None = None
        written = 0
        try:
            handle = tempfile.NamedTemporaryFile(
                mode="w+b", prefix="rift-calibration-", suffix=".bin", dir=target_dir, delete=False
            )
            sample_path = Path(handle.name)
            write_started = time.perf_counter()
            with handle:
                while written < sample_bytes:
                    chunk = block[: min(len(block), sample_bytes - written)]
                    handle.write(chunk)
                    written += len(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            write_elapsed = max(time.perf_counter() - write_started, 1e-9)

            read_bytes = 0
            read_started = time.perf_counter()
            with sample_path.open("rb", buffering=0) as source:
                while True:
                    chunk = source.read(len(block))
                    if not chunk:
                        break
                    read_bytes += len(chunk)
            read_elapsed = max(time.perf_counter() - read_started, 1e-9)
        finally:
            if sample_path and sample_path.exists():
                sample_path.unlink()

        payload = {
            "schema_version": 1,
            "created_unix_seconds": time.time(),
            "sample_bytes": written,
            "disk": {
                "measurement": "measured_local_sequential_sample",
                "write_mib_s": round(written / write_elapsed / 1024**2, 3),
                "read_mib_s": round(read_bytes / read_elapsed / 1024**2, 3),
                "write_seconds": round(write_elapsed, 6),
                "read_seconds": round(read_elapsed, 6),
                "cache_caveat": "OS and device caches can influence this bounded sample.",
            },
            "h2d": h2d_measurement
            or {
                "measurement": "not_measured",
                "reason": "The native CUDA calibration hook was unavailable or failed.",
            },
            "reused": False,
        }
        self.calibration_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return payload

    def _capacity(self, native: JsonDict) -> JsonDict:
        total_ram = int(native.get("total_host_ram_bytes") or 0)
        total_vram = int(native.get("total_vram_bytes") or 0)
        disk = shutil.disk_usage(self.root)
        return {
            "host_ram_bytes": total_ram,
            "vram_bytes": total_vram,
            "disk_total_bytes": int(disk.total),
            "logical_cpu_count": os.cpu_count() or 0,
        }

    def _pressure(self, native: JsonDict, capacity: JsonDict) -> JsonDict:
        free_ram = int(native.get("free_host_ram_bytes") or 0)
        free_vram = int(native.get("free_vram_bytes") or 0)
        disk = shutil.disk_usage(self.root)
        total_ram = int(capacity.get("host_ram_bytes") or 0)
        total_vram = int(capacity.get("vram_bytes") or 0)
        return {
            "host_ram_free_bytes": free_ram,
            "host_ram_used_percent": self._used_percent(total_ram, free_ram),
            "vram_free_bytes": free_vram,
            "vram_used_percent": self._used_percent(total_vram, free_vram),
            "disk_free_bytes": int(disk.free),
            "disk_used_percent": self._used_percent(int(disk.total), int(disk.free)),
            "observation_note": "Free capacity is a point-in-time observation and may include non-RIFT workloads.",
        }

    def _storage_profile(self) -> JsonDict:
        usage = shutil.disk_usage(self.root)
        filesystem, drive_type = self._filesystem_details()
        return {
            "path": str(self.root.resolve()),
            "total_bytes": int(usage.total),
            "free_bytes": int(usage.free),
            "filesystem": filesystem,
            "media_type": drive_type,
            "measurement_note": "Run `rift calibrate` for bounded sequential throughput evidence.",
        }

    def _managed_occupancy(self, state: JsonDict) -> JsonDict:
        services = state.get("services") if isinstance(state, dict) else {}
        running = []
        for name, service in (services or {}).items():
            runtime = service.get("runtime") if isinstance(service, dict) else {}
            if runtime and runtime.get("pid"):
                running.append(
                    {
                        "service": str(name),
                        "pid": runtime.get("pid"),
                        "backend": service.get("backend"),
                    }
                )
        process_vram = self._nvidia_process_memory()
        total_ram = 0
        total_vram = 0
        for entry in running:
            pid = int(entry.get("pid") or 0)
            ram_bytes = self._process_memory_bytes(pid)
            vram_bytes = int(process_vram.get(pid) or 0)
            entry["host_ram_bytes"] = ram_bytes
            entry["vram_bytes"] = vram_bytes
            total_ram += int(ram_bytes or 0)
            total_vram += vram_bytes
        return {
            "running_service_count": len(running),
            "services": running,
            "resource_bytes": {
                "host_ram_bytes": total_ram,
                "vram_bytes": total_vram,
            },
            "note": "Attribution is a point-in-time OS/nvidia-smi sample and excludes child processes that a backend does not report under its managed PID.",
        }

    def _execution_environments(self) -> JsonDict:
        wsl = shutil.which("wsl.exe") or shutil.which("wsl")
        container = next(
            ((name, shutil.which(name)) for name in ("docker", "podman", "nerdctl") if shutil.which(name)),
            None,
        )
        return {
            "native": {"available": True, "os": platform.system().lower()},
            "wsl2": {
                "available": bool(wsl),
                "executable": wsl,
                "note": "Executable presence does not prove that a CUDA-capable distribution is configured.",
            },
            "container": {
                "available": bool(container),
                "runtime": container[0] if container else None,
                "executable": container[1] if container else None,
                "note": "Runtime presence does not prove GPU passthrough is configured.",
            },
        }

    def _physical_cpu_count(self) -> int | None:
        if os.name == "nt":
            if "windows_physical_cores" in _QUERY_CACHE:
                return _QUERY_CACHE["windows_physical_cores"]
            try:
                result = subprocess.run(
                    [
                        "powershell.exe",
                        "-NoProfile",
                        "-Command",
                        "(Get-CimInstance Win32_Processor | Measure-Object -Property NumberOfCores -Sum).Sum",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
                value = result.stdout.strip()
                count = int(value) if result.returncode == 0 and value.isdigit() else None
            except (OSError, subprocess.TimeoutExpired):
                count = None
            _QUERY_CACHE["windows_physical_cores"] = count
            return count
        cpuinfo = Path("/proc/cpuinfo")
        if cpuinfo.is_file():
            try:
                text = cpuinfo.read_text(encoding="utf-8", errors="ignore")
                pairs = set()
                physical = None
                core = None
                for line in [*text.splitlines(), ""]:
                    if not line.strip():
                        if physical is not None and core is not None:
                            pairs.add((physical, core))
                        physical = core = None
                    elif line.startswith("physical id"):
                        physical = line.split(":", 1)[1].strip()
                    elif line.startswith("core id"):
                        core = line.split(":", 1)[1].strip()
                if pairs:
                    return len(pairs)
            except OSError:
                pass
        return None

    def _filesystem_details(self) -> tuple[str, str]:
        if os.name == "nt":
            try:
                import ctypes

                root = str(self.root.resolve().anchor or self.root.resolve().drive + "\\")
                fs_buffer = ctypes.create_unicode_buffer(64)
                ctypes.windll.kernel32.GetVolumeInformationW(
                    ctypes.c_wchar_p(root),
                    None,
                    0,
                    None,
                    None,
                    None,
                    fs_buffer,
                    len(fs_buffer),
                )
                drive_type_code = int(ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(root)))
                drive_types = {2: "removable", 3: "fixed", 4: "network", 5: "optical", 6: "ramdisk"}
                return fs_buffer.value or "unknown", drive_types.get(drive_type_code, "unknown")
            except Exception:
                return "unknown", "unknown"
        try:
            result = subprocess.run(
                ["df", "-T", str(self.root.resolve())],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            lines = [line for line in result.stdout.splitlines() if line.strip()]
            if result.returncode == 0 and len(lines) >= 2:
                fields = lines[-1].split()
                return (fields[1] if len(fields) > 1 else "unknown"), "block-device"
        except (OSError, subprocess.TimeoutExpired):
            pass
        return "unknown", "unknown"

    def _process_memory_bytes(self, pid: int) -> int | None:
        if pid <= 0:
            return None
        if os.name != "nt":
            status = Path(f"/proc/{pid}/status")
            if status.is_file():
                try:
                    match = re.search(r"^VmRSS:\s+(\d+)\s+kB", status.read_text(encoding="utf-8"), re.MULTILINE)
                    return int(match.group(1)) * 1024 if match else None
                except OSError:
                    return None
            return None
        try:
            command = [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                f"(Get-Process -Id {pid} -ErrorAction Stop).WorkingSet64",
            ]
            result = subprocess.run(command, capture_output=True, text=True, timeout=2, check=False)
            value = result.stdout.strip()
            return int(value) if result.returncode == 0 and value.isdigit() else None
        except (OSError, subprocess.TimeoutExpired):
            return None

    def _nvidia_process_memory(self) -> dict[int, int]:
        executable = shutil.which("nvidia-smi")
        if not executable:
            return {}
        try:
            result = subprocess.run(
                [
                    executable,
                    "--query-compute-apps=pid,used_memory",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return {}
        usage: dict[int, int] = {}
        for line in result.stdout.splitlines():
            fields = [item.strip() for item in line.split(",")]
            if len(fields) >= 2 and fields[0].isdigit():
                try:
                    usage[int(fields[0])] = int(float(fields[1])) * 1024**2
                except ValueError:
                    continue
        return usage

    def _power_profile(self) -> JsonDict:
        if os.name != "nt":
            return {"available": False, "measurement": "not_implemented_for_platform"}
        executable = shutil.which("powercfg")
        if not executable:
            return {"available": False, "measurement": "not_available"}
        try:
            result = subprocess.run(
                [executable, "/getactivescheme"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"available": False, "measurement": "probe_failed", "error": str(exc)}
        return {
            "available": result.returncode == 0,
            "measurement": "observed" if result.returncode == 0 else "probe_failed",
            "active_scheme": result.stdout.strip() or None,
        }

    def _cpu_model(self) -> str:
        candidates = [
            platform.processor(),
            os.environ.get("PROCESSOR_IDENTIFIER", ""),
            platform.uname().processor,
        ]
        return next((str(item).strip() for item in candidates if str(item).strip()), "unknown")

    def _nvidia_runtime_state(self) -> JsonDict:
        executable = shutil.which("nvidia-smi")
        if not executable:
            return {"available": False, "measurement": "not_available"}
        command = [
            executable,
            "--query-gpu=temperature.gpu,power.draw,power.limit,utilization.gpu,pstate,pcie.link.gen.current,pcie.link.gen.max,pcie.link.width.current,pcie.link.width.max",
            "--format=csv,noheader,nounits",
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=4, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"available": False, "measurement": "probe_failed", "error": str(exc)}
        if result.returncode != 0 or not result.stdout.strip():
            return {
                "available": False,
                "measurement": "probe_failed",
                "error": result.stderr.strip()[:500],
            }
        values = [item.strip() for item in result.stdout.splitlines()[0].split(",")]
        if len(values) < 9:
            return {"available": False, "measurement": "parse_failed"}
        return {
            "available": True,
            "measurement": "observed",
            "temperature_c": self._number(values[0]),
            "power_draw_w": self._number(values[1]),
            "power_limit_w": self._number(values[2]),
            "gpu_utilization_percent": self._number(values[3]),
            "performance_state": values[4],
            "pcie_generation_current": self._number(values[5]),
            "pcie_generation_max": self._number(values[6]),
            "pcie_width_current": self._number(values[7]),
            "pcie_width_max": self._number(values[8]),
        }

    def _read_calibration(self) -> JsonDict | None:
        if not self.calibration_path.is_file():
            return None
        try:
            payload = json.loads(self.calibration_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _used_percent(total: int, free: int) -> float | None:
        if total <= 0:
            return None
        return round(max(0.0, min(100.0, (total - free) / total * 100.0)), 3)

    @staticmethod
    def _number(value: str) -> float | None:
        try:
            return float(value)
        except ValueError:
            return None


__all__ = ["HardwareAnalyzer"]
