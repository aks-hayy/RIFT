"""Optional-native boundary for RIFT's control plane.

The control plane is useful without CUDA. Native inference helpers are exposed
only when the compiled extension is installed; callers can inspect the
capability report instead of failing during package import.
"""

from __future__ import annotations

import ctypes
import os
import platform
from typing import Any


InferenceEngine = None
__version__ = "1.3.0"


class ControlPlaneRuntime:
    """Small runtime facade used when the optional native module is absent."""

    def build_info(self) -> dict[str, Any]:
        return build_info()

    def hardware_profile(self) -> dict[str, Any]:
        total_ram, free_ram = _host_memory_bytes()
        return {
            "cuda_available": False,
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
