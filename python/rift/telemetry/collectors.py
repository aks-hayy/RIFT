"""Best-effort cross-platform local resource collectors."""

from __future__ import annotations

import ctypes
import os
import subprocess
import time
from typing import Any

try:  # psutil is optional so telemetry never prevents a service from starting.
    import psutil  # type: ignore
except Exception:  # pragma: no cover - depends on the host image
    psutil = None


def _windows_memory() -> tuple[int | None, int | None]:
    if os.name != "nt":
        return None, None
    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_uint32), ("memory_load", ctypes.c_uint32),
                    ("total", ctypes.c_uint64), ("available", ctypes.c_uint64),
                    ("total_page", ctypes.c_uint64), ("available_page", ctypes.c_uint64),
                    ("total_virtual", ctypes.c_uint64), ("available_virtual", ctypes.c_uint64),
                    ("available_extended", ctypes.c_uint64)]
    status = MemoryStatus()
    status.length = ctypes.sizeof(MemoryStatus)
    try:
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.total), int(status.available)
    except Exception:
        pass
    return None, None


def _windows_cpu_times() -> tuple[int, int] | None:
    if os.name != "nt":
        return None
    class FileTime(ctypes.Structure):
        _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]
    idle, kernel, user = FileTime(), FileTime(), FileTime()
    try:
        if ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
            def ticks(value: FileTime) -> int:
                return (int(value.high) << 32) | int(value.low)
            return ticks(idle), ticks(kernel) + ticks(user)
    except Exception:
        pass
    return None


def _nvidia_snapshot() -> dict[str, Any]:
    """Read stable, low-cost fields from nvidia-smi when present."""
    command = [
        "nvidia-smi", "--query-gpu=index,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw,power.limit,clocks.sm,pstate",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=1.5, check=False)
    except (OSError, subprocess.SubprocessError):
        return {"available": False, "reason": "nvidia-smi unavailable"}
    if result.returncode != 0 or not result.stdout.strip():
        return {"available": False, "reason": (result.stderr or "nvidia-smi returned no data").strip()}
    devices = []
    for line in result.stdout.splitlines():
        values = [item.strip() for item in line.split(",")]
        if len(values) < 9:
            continue
        def number(value: str) -> float | None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
        devices.append({
            "index": int(number(values[0]) or 0),
            "temperature_c": number(values[1]),
            "utilization_percent": number(values[2]),
            "vram_used_bytes": (number(values[3]) or 0.0) * 1024 * 1024 if number(values[3]) is not None else None,
            "vram_total_bytes": (number(values[4]) or 0.0) * 1024 * 1024 if number(values[4]) is not None else None,
            "power_watts": number(values[5]),
            "power_limit_watts": number(values[6]),
            "clock_sm_mhz": number(values[7]),
            "pstate": values[8] or None,
        })
    return {"available": bool(devices), "devices": devices}


class LocalCollector:
    """Collect node and process data without assuming a serving backend."""

    def __init__(self) -> None:
        self._last_cpu = None
        self._last_at = None
        self._last_process_cpu: dict[int, tuple[float, float]] = {}

    def collect(self, *, process_id: int | None = None, service_name: str | None = None) -> dict[str, Any]:
        observed_at = time.time()
        sample: dict[str, Any] = {
            "observed_at": observed_at,
            "service_name": service_name,
            "process_id": process_id,
            "collector": "local",
            "collection_interval_seconds": None,
            "cpu_percent": None,
            "cpu_seconds": None,
            "host_ram_total_bytes": None,
            "host_ram_available_bytes": None,
            "host_ram_used_bytes": None,
            "host_ram_pressure_percent": None,
            "process_cpu_percent": None,
            "process_cpu_seconds": None,
            "process_rss_bytes": None,
            "process_private_bytes": None,
            "process_io_read_bytes": None,
            "process_io_write_bytes": None,
            "process_thread_count": None,
            "cpu_temperature_c": None,
            "gpu_utilization_percent": None,
            "gpu_temperature_c": None,
            "gpu_vram_used_bytes": None,
            "gpu_vram_total_bytes": None,
            "gpu_vram_pressure_percent": None,
            "gpu_power_watts": None,
            "gpu_power_limit_watts": None,
            "gpu_clock_sm_mhz": None,
            "gpu_pstate": None,
            "gpu_devices": [],
            "availability": {},
        }
        interval = None if self._last_at is None else max(0.0, observed_at - self._last_at)
        sample["collection_interval_seconds"] = interval
        self._last_at = observed_at

        if psutil is not None:
            try:
                sample["cpu_percent"] = float(psutil.cpu_percent(interval=None))
                sample["cpu_seconds"] = float(sum(psutil.cpu_times()))
                memory = psutil.virtual_memory()
                sample["host_ram_total_bytes"] = int(memory.total)
                sample["host_ram_available_bytes"] = int(memory.available)
                sample["host_ram_used_bytes"] = int(memory.used)
                sample["host_ram_pressure_percent"] = float(memory.percent)
                sample["availability"].update({"cpu": "measured", "host_ram": "measured"})
                try:
                    temperatures = psutil.sensors_temperatures()
                    readings = [
                        float(item.current)
                        for values in temperatures.values()
                        for item in values
                        if getattr(item, "current", None) is not None
                    ]
                    if readings:
                        sample["cpu_temperature_c"] = max(readings)
                        sample["availability"]["cpu_temperature"] = "measured"
                    else:
                        sample["availability"]["cpu_temperature"] = "unavailable: no sensor readings"
                except (AttributeError, OSError, RuntimeError):
                    sample["availability"]["cpu_temperature"] = "unavailable: host sensor API"
            except Exception as exc:
                sample["availability"]["host"] = f"unavailable: {exc}"
        else:
            total, available = _windows_memory()
            if total is not None and available is not None:
                sample.update({
                    "host_ram_total_bytes": total,
                    "host_ram_available_bytes": available,
                    "host_ram_used_bytes": total - available,
                    "host_ram_pressure_percent": (total - available) * 100.0 / total if total else None,
                })
                sample["availability"]["host_ram"] = "measured"
            cpu_times = _windows_cpu_times()
            if cpu_times is not None and self._last_cpu is not None:
                idle_delta = max(0, cpu_times[0] - self._last_cpu[0])
                total_delta = max(0, cpu_times[1] - self._last_cpu[1])
                sample["cpu_percent"] = (1.0 - idle_delta / total_delta) * 100.0 if total_delta else None
                sample["availability"]["cpu"] = "measured"
            else:
                sample["availability"]["cpu"] = "warming: Windows GetSystemTimes requires two samples"
            if cpu_times is not None:
                self._last_cpu = cpu_times
            sample["availability"].setdefault("cpu_temperature", "unavailable: host sensor API")

        if process_id is not None:
            self._collect_process(sample, process_id)
        gpu = _nvidia_snapshot()
        if gpu.get("available"):
            devices = gpu.get("devices") or []
            first = devices[0] if devices else {}
            def total_or_none(key: str) -> float | None:
                values = [float(item[key]) for item in devices if isinstance(item.get(key), (int, float))]
                return sum(values) if values else None
            sample.update({
                "gpu_utilization_percent": first.get("utilization_percent"),
                "gpu_temperature_c": first.get("temperature_c"),
                "gpu_vram_used_bytes": total_or_none("vram_used_bytes"),
                "gpu_vram_total_bytes": total_or_none("vram_total_bytes"),
                "gpu_power_watts": total_or_none("power_watts"),
                "gpu_power_limit_watts": total_or_none("power_limit_watts"),
                "gpu_clock_sm_mhz": first.get("clock_sm_mhz"),
                "gpu_pstate": first.get("pstate"),
                "gpu_devices": devices,
            })
            if sample["gpu_vram_used_bytes"] is not None and sample["gpu_vram_total_bytes"]:
                sample["gpu_vram_pressure_percent"] = (
                    float(sample["gpu_vram_used_bytes"])
                    / float(sample["gpu_vram_total_bytes"])
                    * 100.0
                )
            sample["availability"]["gpu"] = "measured"
        else:
            sample["availability"]["gpu"] = str(gpu.get("reason") or "unavailable")
        return sample

    def _collect_process(self, sample: dict[str, Any], process_id: int) -> None:
        if psutil is None:
            sample["availability"]["process"] = "unavailable: install psutil for process-tree accounting"
            return
        try:
            root = psutil.Process(process_id)
            processes = [root, *root.children(recursive=True)]
            cpu_seconds = 0.0
            rss = 0
            read_bytes = 0
            write_bytes = 0
            threads = 0
            private_bytes = 0
            private_available = True
            for process in processes:
                try:
                    times = process.cpu_times()
                    cpu_seconds += float(times.user + times.system)
                    rss += int(process.memory_info().rss)
                    try:
                        private_bytes += int(process.memory_full_info().uss)
                    except (AttributeError, psutil.Error, OSError):
                        private_available = False
                    io = process.io_counters()
                    read_bytes += int(io.read_bytes)
                    write_bytes += int(io.write_bytes)
                    threads += int(process.num_threads())
                except (psutil.Error, OSError):
                    continue
            previous = self._last_process_cpu.get(process_id)
            now = float(sample["observed_at"])
            process_cpu_percent = 0.0
            if previous is not None:
                previous_seconds, previous_at = previous
                elapsed = now - previous_at
                if elapsed > 0:
                    # Normalize aggregate process CPU to host utilization so
                    # the value is comparable with psutil.cpu_percent().
                    process_cpu_percent = max(
                        0.0,
                        (cpu_seconds - previous_seconds)
                        / elapsed
                        / max(1, os.cpu_count() or 1)
                        * 100.0,
                    )
            self._last_process_cpu[process_id] = (cpu_seconds, now)
            sample.update({
                "process_cpu_percent": process_cpu_percent,
                "process_cpu_seconds": cpu_seconds,
                "process_rss_bytes": rss,
                "process_private_bytes": private_bytes if private_available else None,
                "process_io_read_bytes": read_bytes,
                "process_io_write_bytes": write_bytes,
                "process_thread_count": threads,
            })
            sample["availability"]["process"] = "measured"
        except (psutil.Error, OSError, ValueError) as exc:
            sample["availability"]["process"] = f"unavailable: {exc}"


__all__ = ["LocalCollector"]
