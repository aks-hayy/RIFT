"""Optional-native boundary for RIFT's control plane.

The control plane is useful without CUDA. Native inference helpers are exposed
only when the compiled extension is installed; callers can inspect the
capability report instead of failing during package import.
"""

from __future__ import annotations

import ctypes
import csv
import os
import platform
import shutil
import subprocess
from io import StringIO
from typing import Any


InferenceEngine = None
__version__ = "1.3.0"


def _infer_compute_capability(device_name: str) -> tuple[int | None, int | None]:
    """Return a conservative NVIDIA architecture mapping from the device name."""

    name = device_name.upper()
    if "RTX 50" in name:
        return 12, 0
    if "RTX 40" in name:
        return 8, 9
    if "RTX 30" in name or "A10" in name or "A40" in name:
        return 8, 6
    if "RTX 20" in name or "GTX 16" in name or "T4" in name:
        return 7, 5
    if "V100" in name:
        return 7, 0
    if "P100" in name:
        return 6, 0
    if "K80" in name:
        return 3, 7
    return None, None


def _nvidia_hardware_profile() -> dict[str, Any]:
    """Read GPU identity and memory through the installed NVIDIA driver tools."""

    executable = shutil.which("nvidia-smi")
    if not executable:
        return {}

    query = "name,memory.total,memory.free,driver_version"
    try:
        completed = subprocess.run(
            [executable, f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return {}
    if completed.returncode != 0:
        return {}

    devices: list[dict[str, Any]] = []
    for row in csv.reader(StringIO(completed.stdout or "")):
        if len(row) < 4:
            continue
        name = row[0].strip()
        if not name:
            continue
        try:
            total_vram = int(float(row[1].strip()) * 1024**2)
            free_vram = int(float(row[2].strip()) * 1024**2)
        except ValueError:
            continue
        major, minor = _infer_compute_capability(name)
        devices.append(
            {
                "index": len(devices),
                "name": name,
                "total_vram_bytes": total_vram,
                "free_vram_bytes": max(0, min(total_vram, free_vram)),
                "driver_version": row[3].strip(),
                "compute_capability_major": major,
                "compute_capability_minor": minor,
            }
        )
    if not devices:
        return {}

    primary = devices[0]
    return {
        "cuda_available": True,
        "native_cuda_runtime_available": False,
        "driver_visible": True,
        "device_count": len(devices),
        "device_name": primary["name"],
        "cuda_device_id": primary["index"],
        "compute_capability_major": primary["compute_capability_major"],
        "compute_capability_minor": primary["compute_capability_minor"],
        "total_vram_bytes": primary["total_vram_bytes"],
        "free_vram_bytes": primary["free_vram_bytes"],
        "driver_version": primary["driver_version"],
        "devices": devices,
        "measurement": "observed_nvidia_smi",
    }


class ControlPlaneRuntime:
    """Small runtime facade used when the optional native module is absent."""

    def build_info(self) -> dict[str, Any]:
        return build_info()

    def hardware_profile(self) -> dict[str, Any]:
        total_ram, free_ram = _host_memory_bytes()
        profile = {
            "cuda_available": False,
            "native_cuda_runtime_available": False,
            "device_count": 0,
            "device_name": None,
            "cuda_device_id": 0,
            "compute_capability_major": None,
            "compute_capability_minor": None,
            "total_vram_bytes": 0,
            "free_vram_bytes": 0,
            "total_host_ram_bytes": total_ram,
            "free_host_ram_bytes": free_ram,
        }
        profile.update(_nvidia_hardware_profile())
        return profile

    def measure_h2d_bandwidth(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "available": False,
            "measurement": "unavailable_without_native_cuda_runtime",
            "sample_bytes": int(kwargs.get("sample_bytes") or 0),
            "iterations": int(kwargs.get("iterations") or 0),
        }


def build_info() -> dict[str, Any]:
    return {
        "native_available": False,
        "cuda_available": False,
        "backend": "python-control-plane",
        "message": "Optional native CUDA runtime is not installed",
    }


def cuda_device_count() -> int:
    # This is the optional native CUDA runtime count, not a best-effort
    # hardware observation. The control plane may still report an NVIDIA GPU
    # through its portable profile without claiming CUDA execution support.
    return 0


def inspect_model(*args: Any, **kwargs: Any) -> dict[str, Any]:
    raise RuntimeError(
        "native model inspection is unavailable; use rift model inspect for "
        "format-neutral control-plane inspection"
    )


def parse_model_topology(*args: Any, **kwargs: Any) -> dict[str, Any]:
    raise RuntimeError(
        "native topology parsing is unavailable; install an optional native "
        "runtime only for experimental CUDA topology work"
    )


def _host_memory_bytes() -> tuple[int, int]:
    """Read host memory without adding a platform-specific dependency."""

    if platform.system().lower() == "windows":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_phys", ctypes.c_ulonglong),
                ("avail_phys", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("avail_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("avail_virtual", ctypes.c_ulonglong),
                ("avail_extended", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        try:
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.total_phys), int(status.avail_phys)
        except (AttributeError, OSError):
            pass
    try:
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        total_pages = int(os.sysconf("SC_PHYS_PAGES"))
        available_pages = int(os.sysconf("SC_AVPHYS_PAGES"))
        return page_size * total_pages, page_size * available_pages
    except (AttributeError, OSError, ValueError):
        return 0, 0


__all__ = [
    "InferenceEngine",
    "ControlPlaneRuntime",
    "__version__",
    "build_info",
    "cuda_device_count",
    "inspect_model",
    "parse_model_topology",
]
