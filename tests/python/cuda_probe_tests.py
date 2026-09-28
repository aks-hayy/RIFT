from __future__ import annotations

import ctypes
import importlib
import importlib.util
from pathlib import Path
import shutil


def _module():
    spec = importlib.util.find_spec("rift.cuda_probe")
    assert spec is not None, "rift.cuda_probe must provide device-based CUDA detection"
    return importlib.import_module("rift.cuda_probe")


def test_os_gpu_inventory_finds_nvidia_without_nvidia_smi(monkeypatch):
    module = _module()
    monkeypatch.setattr(
        module,
        "_enumerate_hardware",
        lambda: {
            "available": True,
            "devices": [{"name": "NVIDIA GeForce RTX fixture", "vendor_id": "10de"}],
            "source": "Windows Win32_VideoController",
            "reason": None,
        },
    )
    monkeypatch.setattr(module, "_find_nvidia_smi", lambda: None)

    result = module.probe_nvidia_gpu()

    assert result["available"] is True
    assert result["devices"][0]["vendor_id"] == "10de"
    assert result["source"] == "Windows Win32_VideoController"


def test_nvidia_smi_on_path_adds_diagnostics(monkeypatch, tmp_path):
    module = _module()
    monkeypatch.setattr(
        module,
        "_enumerate_hardware",
        lambda: {
            "available": True,
            "devices": [{"name": "NVIDIA fixture", "vendor_id": "10de"}],
            "source": "Linux PCI sysfs",
            "reason": None,
        },
    )
    smi = tmp_path / "nvidia-smi"
    monkeypatch.setattr(module, "_find_nvidia_smi", lambda: smi)
    monkeypatch.setattr(module, "_run_nvidia_smi", lambda _path: "NVIDIA-SMI 999 fixture")

    result = module.probe_nvidia_gpu()

    assert result["available"] is True
    assert result["diagnostics"]["nvidia_smi"] == "NVIDIA-SMI 999 fixture"


def test_nvidia_smi_outside_path_is_discovered(monkeypatch, tmp_path):
    module = _module()
    driver_dir = tmp_path / "NVIDIA" / "NVSMI"
    driver_dir.mkdir(parents=True)
    smi = driver_dir / "nvidia-smi.exe"
    smi.write_bytes(b"fixture")
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    monkeypatch.setattr(module, "_nvidia_smi_candidates", lambda: [smi])

    assert module._find_nvidia_smi() == smi


def test_missing_gpu_inventory_is_reported(monkeypatch):
    module = _module()
    monkeypatch.setattr(
        module,
        "_enumerate_hardware",
        lambda: {
            "available": False,
            "devices": [],
            "source": "Linux PCI sysfs",
            "reason": "no NVIDIA GPU detected",
        },
    )
    monkeypatch.setattr(module, "_find_nvidia_smi", lambda: None)

    result = module.probe_nvidia_gpu()

    assert result["available"] is False
    assert result["devices"] == []
    assert "no NVIDIA GPU detected" in result["reason"]


class _Driver:
    def __init__(self, *, init_result=0, device_count=1, count_result=0):
        self.init_result = init_result
        self.device_count = device_count
        self.count_result = count_result

    def cuInit(self, flags):
        assert flags == 0
        return self.init_result

    def cuDeviceGetCount(self, output):
        ctypes.cast(output, ctypes.POINTER(ctypes.c_int))[0] = self.device_count
        return self.count_result


def test_cuda_driver_init_and_device_count_succeed(monkeypatch):
    module = _module()
    monkeypatch.setattr(module, "_load_cuda_library", lambda: (_Driver(device_count=2), "nvcuda.dll"))

    result = module.probe_cuda_driver()

    assert result["available"] is True
    assert result["device_count"] == 2
    assert result["driver_library"] == "nvcuda.dll"


def test_cuda_driver_init_failure_is_reported(monkeypatch):
    module = _module()
    monkeypatch.setattr(module, "_load_cuda_library", lambda: (_Driver(init_result=35), "nvcuda.dll"))

    result = module.probe_cuda_driver()

    assert result["available"] is False
    assert result["device_count"] == 0
    assert "cuInit" in result["reason"]


def test_cuda_device_count_zero_is_unavailable(monkeypatch):
    module = _module()
    monkeypatch.setattr(module, "_load_cuda_library", lambda: (_Driver(device_count=0), "nvcuda.dll"))

    result = module.probe_cuda_driver()

    assert result["available"] is False
    assert result["device_count"] == 0
    assert "cuDeviceGetCount" in result["reason"]


def test_missing_cuda_driver_symbol_is_reported(monkeypatch):
    module = _module()
    monkeypatch.setattr(module, "_load_cuda_library", lambda: (object(), "nvcuda.dll"))

    result = module.probe_cuda_driver()

    assert result["available"] is False
    assert "cuInit" in result["reason"] or "cuDeviceGetCount" in result["reason"]
