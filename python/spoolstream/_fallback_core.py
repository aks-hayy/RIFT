"""Optional-native boundary for RIFT's control plane.

The control plane is useful without CUDA. Native inference helpers are exposed
only when the compiled extension is installed; callers can inspect the
capability report instead of failing during package import.
"""

from __future__ import annotations

from typing import Any


InferenceEngine = None
__version__ = "1.3.0"


class ControlPlaneRuntime:
    """Small runtime facade used when the optional native module is absent."""

    def build_info(self) -> dict[str, Any]:
        return build_info()

    def hardware_profile(self) -> dict[str, Any]:
        return {
            "cuda_available": False,
            "device_count": 0,
            "device_name": None,
            "cuda_device_id": 0,
            "compute_capability_major": None,
            "compute_capability_minor": None,
            "total_vram_bytes": 0,
            "free_vram_bytes": 0,
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


__all__ = [
    "InferenceEngine",
    "ControlPlaneRuntime",
    "__version__",
    "build_info",
    "cuda_device_count",
    "inspect_model",
    "parse_model_topology",
]
