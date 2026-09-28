"""Best-effort NVIDIA hardware and CUDA Driver API probes.

These probes intentionally avoid CUDA Toolkit environment variables and do
not install optional frameworks. Host inventory, driver availability, and a
backend executable's own device support are separate capabilities.
"""

from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
from typing import Any


JsonDict = dict[str, Any]
_NVIDIA_VENDOR_ID = "10de"


def _windows_powershell() -> Path | None:
    system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR")
    if not system_root:
        return None
    return Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"


def _enumerate_windows_gpus() -> JsonDict:
    powershell = _windows_powershell()
    if powershell is None or not powershell.is_file():
        return {
            "available": False,
            "inventory_available": False,
            "devices": [],
            "source": "Windows Win32_VideoController",
            "reason": "Windows GPU inventory unavailable: SystemRoot PowerShell was not found",
        }

    query = (
        "Get-CimInstance Win32_VideoController | "
        "Select-Object Name, PNPDeviceID, AdapterCompatibility, VideoProcessor | "
        "ConvertTo-Json -Compress"
    )
    try:
        completed = subprocess.run(
            [str(powershell), "-NoProfile", "-NonInteractive", "-Command", query],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except Exception as exc:
        return {
            "available": False,
            "inventory_available": False,
            "devices": [],
            "source": "Windows Win32_VideoController",
            "reason": f"Windows GPU inventory unavailable: {exc}",
        }
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "PowerShell query failed").strip()
        return {
            "available": False,
            "inventory_available": False,
            "devices": [],
            "source": "Windows Win32_VideoController",
            "reason": f"Windows GPU inventory unavailable: {detail[:300]}",
        }

    try:
        payload = json.loads(completed.stdout or "null")
    except (TypeError, json.JSONDecodeError) as exc:
        return {
            "available": False,
            "inventory_available": False,
            "devices": [],
            "source": "Windows Win32_VideoController",
            "reason": f"Windows GPU inventory returned invalid JSON: {exc}",
        }
    adapters = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else []
    nvidia_devices = []
    for adapter in adapters:
        if not isinstance(adapter, dict):
            continue
        identity = " ".join(
            str(adapter.get(key) or "")
            for key in ("Name", "PNPDeviceID", "AdapterCompatibility", "VideoProcessor")
        )
        if "nvidia" not in identity.lower() and "ven_10de" not in identity.lower():
            continue
        nvidia_devices.append(
            {
                "name": str(adapter.get("Name") or adapter.get("VideoProcessor") or "NVIDIA GPU"),
                "vendor_id": _NVIDIA_VENDOR_ID,
                "device_id": _windows_pnp_device_id(adapter.get("PNPDeviceID")),
                "source": "Windows Win32_VideoController",
            }
        )
    reason = None if nvidia_devices else "no NVIDIA GPU detected in Win32_VideoController"
    return {
        "available": bool(nvidia_devices),
        "inventory_available": True,
        "devices": nvidia_devices,
        "source": "Windows Win32_VideoController",
        "reason": reason,
    }


def _windows_pnp_device_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    marker = "DEV_"
    upper = value.upper()
    start = upper.find(marker)
    if start < 0:
        return None
    return value[start + len(marker) : start + len(marker) + 4]


def _enumerate_linux_gpus() -> JsonDict:
    pci_root = Path("/sys/bus/pci/devices")
    if not pci_root.is_dir():
        return {
            "available": False,
            "inventory_available": False,
            "devices": [],
            "source": "Linux PCI sysfs",
            "reason": "Linux GPU inventory unavailable: PCI sysfs directory was not found",
        }

    devices = []
    try:
        pci_devices = sorted(pci_root.iterdir())
    except OSError as exc:
        return {
            "available": False,
            "inventory_available": False,
            "devices": [],
            "source": "Linux PCI sysfs",
            "reason": f"Linux GPU inventory unavailable: {exc}",
        }

    for path in pci_devices:
        try:
            vendor = (path / "vendor").read_text(encoding="ascii").strip().lower().removeprefix("0x")
            device_id = (path / "device").read_text(encoding="ascii").strip().lower().removeprefix("0x")
            device_class = (path / "class").read_text(encoding="ascii").strip().lower().removeprefix("0x")
        except (OSError, UnicodeError):
            continue
        # 0x03 is a display controller; 0x12 is an accelerator device.
        if vendor == _NVIDIA_VENDOR_ID and device_class[:2] in ("03", "12"):
            devices.append(
                {
                    "name": f"NVIDIA PCI device {path.name}",
                    "vendor_id": _NVIDIA_VENDOR_ID,
                    "device_id": device_id,
                    "pci_address": path.name,
                    "source": "Linux PCI sysfs",
                }
            )

    reason = None if devices else "no NVIDIA GPU detected in Linux PCI sysfs"
    return {
        "available": bool(devices),
        "inventory_available": True,
        "devices": devices,
        "source": "Linux PCI sysfs",
        "reason": reason,
    }


def _enumerate_hardware() -> JsonDict:
    system = platform.system().lower()
    if system == "windows":
        return _enumerate_windows_gpus()
    if system == "linux":
        return _enumerate_linux_gpus()
    return {
        "available": False,
        "inventory_available": False,
        "devices": [],
        "source": f"{system or 'unknown'} hardware inventory",
        "reason": f"NVIDIA GPU inventory is not implemented for {system or 'this platform'}",
    }


def _nvidia_smi_candidates() -> list[Path]:
    candidates: list[Path] = []
    system = platform.system().lower()
    if system == "windows":
        system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR")
        if system_root:
            candidates.append(Path(system_root) / "System32" / "nvidia-smi.exe")
        candidates.extend(
            [
                Path(os.environ.get("ProgramFiles", "C:/Program Files"))
                / "NVIDIA Corporation"
                / "NVSMI"
                / "nvidia-smi.exe",
                Path("C:/Windows/System32/nvidia-smi.exe"),
            ]
        )
    elif system == "linux":
        candidates.extend(
            [
                Path("/usr/bin/nvidia-smi"),
                Path("/usr/local/bin/nvidia-smi"),
                Path("/usr/lib/wsl/lib/nvidia-smi"),
            ]
        )
    return candidates


def _find_nvidia_smi() -> Path | None:
    from_path = shutil.which("nvidia-smi")
    if from_path:
        return Path(from_path)
    for candidate in _nvidia_smi_candidates():
        if candidate.is_file():
            return candidate
    return None


def _run_nvidia_smi(executable: Path) -> str | None:
    try:
        completed = subprocess.run(
            [str(executable), "--query-gpu=name,uuid", "--format=csv,noheader"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return None
    output = (completed.stdout or completed.stderr or "").strip()
    return output[:500] if output else None


def probe_nvidia_gpu() -> JsonDict:
    """Return NVIDIA PCI/device inventory; nvidia-smi is diagnostics only."""
    result = _enumerate_hardware()
    inventory = {
        "available": bool(result.get("available")),
        "inventory_available": bool(result.get("inventory_available", True)),
        "devices": list(result.get("devices") or []),
        "source": str(result.get("source") or "unknown hardware inventory"),
        "reason": result.get("reason"),
        "diagnostics": {},
    }
    smi = _find_nvidia_smi()
    if smi is not None:
        inventory["diagnostics"]["nvidia_smi_path"] = str(smi)
        output = _run_nvidia_smi(smi)
        if output:
            inventory["diagnostics"]["nvidia_smi"] = output
    return inventory


def _load_cuda_library() -> tuple[Any, str]:
    system = platform.system().lower()
    if system == "windows":
        library_name = "nvcuda.dll"
        loader = getattr(ctypes, "WinDLL", ctypes.CDLL)
        return loader(library_name), library_name
    if system == "linux":
        library_name = "libcuda.so.1"
        return ctypes.CDLL(library_name), library_name
    raise OSError(f"CUDA Driver API probing is not supported on {system or 'this platform'}")


def probe_cuda_driver() -> JsonDict:
    """Call CUDA Driver API initialization and device-count functions."""
    library_name: str | None = None
    try:
        driver, library_name = _load_cuda_library()
    except Exception as exc:
        return {
            "available": False,
            "device_count": 0,
            "driver_library": library_name,
            "reason": f"CUDA driver library unavailable: {exc}",
        }

    try:
        cu_init = getattr(driver, "cuInit")
        cu_device_get_count = getattr(driver, "cuDeviceGetCount")
    except AttributeError as exc:
        return {
            "available": False,
            "device_count": 0,
            "driver_library": library_name,
            "reason": f"CUDA Driver API symbol unavailable: {exc}",
        }

    try:
        init_result = int(cu_init(0))
    except Exception as exc:
        return {
            "available": False,
            "device_count": 0,
            "driver_library": library_name,
            "reason": f"CUDA Driver API cuInit failed: {exc}",
        }
    if init_result != 0:
        return {
            "available": False,
            "device_count": 0,
            "driver_library": library_name,
            "reason": f"CUDA Driver API cuInit failed with error code {init_result}",
        }

    device_count = ctypes.c_int(0)
    try:
        count_result = int(cu_device_get_count(ctypes.byref(device_count)))
    except Exception as exc:
        return {
            "available": False,
            "device_count": 0,
            "driver_library": library_name,
            "reason": f"CUDA Driver API cuDeviceGetCount failed: {exc}",
        }
    if count_result != 0:
        return {
            "available": False,
            "device_count": 0,
            "driver_library": library_name,
            "reason": f"CUDA Driver API cuDeviceGetCount failed with error code {count_result}",
        }
    if device_count.value <= 0:
        return {
            "available": False,
            "device_count": 0,
            "driver_library": library_name,
            "reason": "CUDA Driver API cuDeviceGetCount returned zero devices",
        }
    return {
        "available": True,
        "device_count": int(device_count.value),
        "driver_library": library_name,
        "reason": None,
    }
