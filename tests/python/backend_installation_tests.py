from __future__ import annotations

import contextlib
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import subprocess
import types

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

fake_core = types.ModuleType("rift._core")
fake_core.InferenceEngine = object
fake_core.__version__ = "test"
fake_core.build_info = lambda: {}
fake_core.cuda_device_count = lambda: 0
fake_core.inspect_model = lambda *args, **kwargs: {}
fake_core.parse_model_topology = lambda *args, **kwargs: {}
sys.modules.setdefault("rift._core", fake_core)


def _managed_module():
    spec = importlib.util.find_spec("rift.backends.managed_installation")
    assert spec is not None, "RIFT must provide ownership tracking for installed backends"
    return importlib.import_module("rift.backends.managed_installation")


def test_registry_records_exact_managed_target(tmp_path):
    module = _managed_module()
    runtime_home = tmp_path / "rift-home"
    target = runtime_home / "backends" / "llama.cpp"
    target.mkdir(parents=True)
    (target / "llama-server.exe").write_bytes(b"runtime")
    (target / "rift-install.json").write_text(
        json.dumps(
            {
                "backend": "llama.cpp",
                "installed": True,
                "target_dir": str(target.resolve()),
                "managed_installation": {
                    "managed_by": "RIFT",
                    "backend_id": "llama.cpp",
                    "target": str(target.resolve()),
                    "managed_paths": ["llama-server.exe", "rift-install.json"],
                },
            }
        ),
        encoding="utf-8",
    )

    recorded = module.record_managed_installation(
        runtime_home, "llama.cpp", target, "archive", {"variant": "cuda12"}
    )
    inspected = module.inspect_managed_installation(runtime_home, "llama.cpp")

    assert recorded["target"] == str(target.resolve())
    assert inspected["managed"] is True
    assert inspected["removable"] is True
    assert inspected["target"] == str(target.resolve())
    assert inspected["install_type"] == "archive"
    assert inspected["marker_path"] == str(target.resolve() / "rift-install.json")


def test_unmarked_external_runtime_is_not_removable(tmp_path):
    module = _managed_module()
    runtime_home = tmp_path / "rift-home"
    target = tmp_path / "external" / "vllm"
    target.mkdir(parents=True)

    inspected = module.inspect_managed_installation(runtime_home, "vllm")

    assert inspected["managed"] is False
    assert inspected["removable"] is False


def test_registry_rejects_target_marker_mismatch(tmp_path):
    module = _managed_module()
    runtime_home = tmp_path / "rift-home"
    target = runtime_home / "backends" / "vllm"
    target.mkdir(parents=True)
    module.record_managed_installation(runtime_home, "vllm", target, "native-venv", {"packages": ["vllm"]})
    marker = target / "rift-managed-install.json"
    metadata = json.loads(marker.read_text(encoding="utf-8"))
    metadata["target"] = str(tmp_path / "wrong-target")
    marker.write_text(json.dumps(metadata), encoding="utf-8")

    inspected = module.inspect_managed_installation(runtime_home, "vllm")

    assert inspected["managed"] is True
    assert inspected["removable"] is False
    assert "marker" in inspected["reason"].lower()


def test_registry_rejects_symlink_escape(tmp_path):
    module = _managed_module()
    runtime_home = tmp_path / "rift-home"
    target = runtime_home / "backends" / "sglang"
    target.mkdir(parents=True)
    module.record_managed_installation(runtime_home, "sglang", target, "native-venv", {})
    outside = tmp_path / "outside"
    outside.mkdir()
    shutil.rmtree(target)
    try:
        os.symlink(outside, target, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlinks are unavailable on this Windows host: {exc}")

    inspected = module.inspect_managed_installation(runtime_home, "sglang")

    assert inspected["removable"] is False
    assert "path" in inspected["reason"].lower() or "link" in inspected["reason"].lower()


def test_registry_tracks_wsl_runtime_metadata(tmp_path):
    module = _managed_module()
    runtime_home = tmp_path / "rift-home"
    target = runtime_home / "backends" / "vllm"
    target.mkdir(parents=True)
    wsl_metadata = {
        "adapter_id": "vllm",
        "python": "/home/rift/.local/share/rift/backends/vllm/venv/bin/python",
        "managed_marker": "RIFT_MANAGED_VENV=/home/rift/.local/share/rift/backends/vllm/venv",
        "packages": ["vllm"],
    }
    (target / "wsl-install.json").write_text(json.dumps(wsl_metadata), encoding="utf-8")

    module.record_managed_installation(runtime_home, "vllm", target, "wsl-venv", wsl_metadata)
    inspected = module.inspect_managed_installation(runtime_home, "vllm")

    assert inspected["removable"] is True
    assert inspected["install_type"] == "wsl-venv"
    assert inspected["metadata"]["python"] == wsl_metadata["python"]


def test_explicit_target_outside_root_requires_exact_marker(tmp_path):
    module = _managed_module()
    runtime_home = tmp_path / "rift-home"
    external_target = tmp_path / "operator-chosen" / "vllm"
    external_target.mkdir(parents=True)

    module.record_managed_installation(
        runtime_home, "vllm", external_target, "native-venv", {"packages": ["vllm"]}
    )
    inspected = module.inspect_managed_installation(runtime_home, "vllm")

    assert inspected["removable"] is True
    assert inspected["target"] == str(external_target.resolve())
    marker = external_target / "rift-managed-install.json"
    metadata = json.loads(marker.read_text(encoding="utf-8"))
    metadata["target"] = str(runtime_home / "backends" / "vllm")
    marker.write_text(json.dumps(metadata), encoding="utf-8")
    assert module.inspect_managed_installation(runtime_home, "vllm")["removable"] is False


def test_cli_install_default_uses_rift_backend_root(tmp_path):
    from rift.cli.commands import _backend
    from rift.cli.console import RiftConsole
    from rift.cli.parser import build_parser

    class Provider:
        def install(self, *, target_dir, variant, force):
            self.target_dir = target_dir
            return {"installed": True, "changed": False}

    class Orchestrator:
        def __init__(self):
            self.rift_dir = tmp_path / "rift-home"
            self.providers = {"vllm": Provider()}

        def _backend_runtime_lock(self, _backend_id):
            return contextlib.nullcontext()

    orchestrator = Orchestrator()
    args = build_parser().parse_args(["backend", "install", "vllm", "--allow-install"])
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        result = _backend(args, RiftConsole(), orchestrator)

    assert result == 0
    assert orchestrator.providers["vllm"].target_dir == str(
        orchestrator.rift_dir / "backends" / "vllm"
    )


def _managed_venv(tmp_path, backend_id="vllm"):
    module = _managed_module()
    runtime_home = tmp_path / "rift-home"
    target = runtime_home / "backends" / backend_id
    (target / "venv").mkdir(parents=True)
    (target / "operator-note.txt").write_text("keep this file", encoding="utf-8")
    module.record_managed_installation(
        runtime_home,
        backend_id,
        target,
        "native-venv",
        {"managed_paths": ["venv"]},
    )
    return runtime_home, target


def _orchestrator(runtime_home):
    from rift.orchestrator import RiftOrchestrator

    orchestrator = RiftOrchestrator(runtime_root=runtime_home)
    assert hasattr(orchestrator, "backend_uninstall_plan"), "orchestrator must expose a guarded uninstall preview"
    return orchestrator


def test_uninstall_preview_reports_target_without_deleting(tmp_path):
    runtime_home, target = _managed_venv(tmp_path)
    orchestrator = _orchestrator(runtime_home)

    plan = orchestrator.backend_uninstall_plan("vllm")

    assert plan["target"] == str(target.resolve())
    assert plan["removable"] is True
    assert plan["dependent_services"] == []
    assert (target / "venv").is_dir()


def test_uninstall_requires_confirm(tmp_path):
    runtime_home, target = _managed_venv(tmp_path)
    orchestrator = _orchestrator(runtime_home)

    with pytest.raises(ValueError, match="confirm"):
        orchestrator.uninstall_backend("vllm", confirm=False)

    assert (target / "venv").is_dir()


def test_uninstall_refuses_active_dependent_service(tmp_path, monkeypatch):
    runtime_home, target = _managed_venv(tmp_path)
    orchestrator = _orchestrator(runtime_home)
    state = orchestrator.read_state()
    state["services"] = {
        "chat": {
            "backend": "vllm",
            "desired_state": "running",
            "status": "started",
            "runtime": {"pid": 4567},
        }
    }
    orchestrator.write_state(state)
    monkeypatch.setattr(orchestrator, "_process_alive", lambda _pid: True)

    with pytest.raises(ValueError, match="chat"):
        orchestrator.uninstall_backend("vllm", confirm=True)

    assert (target / "venv").is_dir()


def test_uninstall_refuses_when_service_state_cannot_be_verified(tmp_path, monkeypatch):
    runtime_home, target = _managed_venv(tmp_path)
    orchestrator = _orchestrator(runtime_home)
    monkeypatch.setattr(orchestrator, "read_state", lambda: (_ for _ in ()).throw(OSError("state unavailable")))

    plan = orchestrator.backend_uninstall_plan("vllm")

    assert plan["removable"] is False
    assert plan["dependent_services"] == ["(service state unavailable)"]
    with pytest.raises(ValueError, match="service state unavailable"):
        orchestrator.uninstall_backend("vllm", confirm=True)
    assert (target / "venv").is_dir()


def test_uninstall_refuses_live_pid_even_when_desired_state_is_stopped(tmp_path, monkeypatch):
    runtime_home, target = _managed_venv(tmp_path)
    orchestrator = _orchestrator(runtime_home)
    state = orchestrator.read_state()
    state["services"] = {
        "chat": {
            "backend": "vllm",
            "desired_state": "stopped",
            "status": "stopped",
            "runtime": {"pid": 4567},
        }
    }
    orchestrator.write_state(state)
    monkeypatch.setattr(orchestrator, "_process_alive", lambda _pid: True)

    plan = orchestrator.backend_uninstall_plan("vllm")

    assert plan["removable"] is False
    assert plan["dependent_services"] == ["chat"]
    assert (target / "venv").is_dir()


def test_uninstall_fails_closed_for_unknown_service_without_pid(tmp_path):
    runtime_home, target = _managed_venv(tmp_path)
    orchestrator = _orchestrator(runtime_home)
    state = orchestrator.read_state()
    state["services"] = {
        "chat": {
            "backend": "vllm",
            "desired_state": "running",
            "status": "unknown",
            "runtime": {},
        }
    }
    orchestrator.write_state(state)

    plan = orchestrator.backend_uninstall_plan("vllm")

    assert plan["removable"] is False
    assert plan["dependent_services"] == ["chat"]
    assert (target / "venv").is_dir()


def test_uninstall_fails_closed_for_malformed_service_record(tmp_path):
    runtime_home, target = _managed_venv(tmp_path)
    orchestrator = _orchestrator(runtime_home)
    state = orchestrator.read_state()
    state["services"] = {"chat": {"runtime": {"pid": 4567}}}
    orchestrator.write_state(state)

    plan = orchestrator.backend_uninstall_plan("vllm")

    assert plan["removable"] is False
    assert plan["dependent_services"] == ["(unverified service record: chat)"]
    assert (target / "venv").is_dir()


def test_uninstall_fails_closed_when_service_backend_fields_conflict(tmp_path):
    runtime_home, target = _managed_venv(tmp_path)
    orchestrator = _orchestrator(runtime_home)
    state = orchestrator.read_state()
    state["services"] = {
        "chat": {
            "backend": "sglang",
            "provider": "vllm",
            "desired_state": "stopped",
            "status": "stopped",
            "runtime": {},
        }
    }
    orchestrator.write_state(state)

    plan = orchestrator.backend_uninstall_plan("vllm")

    assert plan["removable"] is False
    assert plan["dependent_services"] == ["(unverified service record: chat)"]
    assert (target / "venv").is_dir()


@pytest.mark.parametrize("services", [None, [], ""])
def test_uninstall_fails_closed_for_malformed_service_collection(tmp_path, monkeypatch, services):
    _runtime_home, target = _managed_venv(tmp_path)
    orchestrator = _orchestrator(tmp_path / "rift-home")
    monkeypatch.setattr(orchestrator, "read_state", lambda: {"services": services})

    plan = orchestrator.backend_uninstall_plan("vllm")

    assert plan["removable"] is False
    assert plan["dependent_services"] == ["(service state unavailable)"]
    assert (target / "venv").is_dir()


def test_windows_process_query_access_denied_is_not_reported_dead(tmp_path, monkeypatch):
    import ctypes
    import rift.orchestrator as orchestrator_module

    orchestrator = _orchestrator(tmp_path / "rift-home")

    class Kernel32:
        def __init__(self):
            self.OpenProcess = lambda *_args: None
            self.GetExitCodeProcess = lambda *_args: 0
            self.CloseHandle = lambda *_args: None

    monkeypatch.setattr(orchestrator_module.os, "name", "nt")
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_args, **_kwargs: Kernel32(), raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 5, raising=False)

    assert orchestrator._process_alive(4567) is True
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 87, raising=False)
    assert orchestrator._process_alive(4567) is False


def test_native_installer_refuses_unmarked_existing_environment(tmp_path, monkeypatch):
    from rift.providers.openai_backend import install_python_packages_isolated

    target = tmp_path / "backends" / "vllm"
    python = target / "venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"operator-owned python")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("must not run pip in an unowned environment"),
    )

    with pytest.raises(ValueError, match="not verified as RIFT-managed"):
        install_python_packages_isolated(
            ["vllm"], target_dir=target, backend_id="vllm", force=True
        )

    assert python.read_bytes() == b"operator-owned python"


def test_native_installer_rejects_redirected_target_before_writing(tmp_path, monkeypatch):
    from rift.providers import openai_backend
    from rift.providers.openai_backend import install_python_packages_isolated

    target = tmp_path / "redirected" / "vllm"
    monkeypatch.setattr(
        openai_backend,
        "path_redirection_reason",
        lambda path: "fixture junction" if Path(path) == target else None,
        raising=False,
    )

    with pytest.raises(ValueError, match="fixture junction"):
        install_python_packages_isolated(
            ["vllm"], target_dir=target, backend_id="vllm", force=True
        )

    assert not target.exists()


def test_wsl_installer_checks_remote_venv_ownership_before_reuse(tmp_path, monkeypatch):
    from rift.providers import openai_backend

    monkeypatch.setattr(
        openai_backend,
        "wsl_detection",
        lambda: {"available": True, "executable": "wsl.exe"},
    )
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 73, "", "unowned WSL environment")

    monkeypatch.setattr(subprocess, "run", run)

    result = openai_backend.install_python_packages_wsl(
        ["vllm"], target_dir=tmp_path / "vllm", adapter_id="vllm", force=True
    )

    assert result["installed"] is False
    assert calls
    assert "RIFT_MANAGED_VENV" in calls[0][-1]
    assert "unowned WSL environment" in result["stderr_tail"]


def test_wsl_installer_requires_canonical_runtime_path(tmp_path, monkeypatch):
    from rift.providers import openai_backend

    monkeypatch.setattr(
        openai_backend,
        "wsl_detection",
        lambda: {"available": True, "executable": "wsl.exe"},
    )
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 74, "", "WSL runtime path is redirected")

    monkeypatch.setattr(subprocess, "run", run)
    result = openai_backend.install_python_packages_wsl(
        ["vllm"], target_dir=tmp_path / "vllm", adapter_id="vllm", force=True
    )

    assert result["installed"] is False
    assert "realpath" in calls[0][-1]
    assert "WSL runtime path is redirected" in result["stderr_tail"]


def test_uninstall_removes_only_managed_target(tmp_path):
    runtime_home, target = _managed_venv(tmp_path)
    orchestrator = _orchestrator(runtime_home)

    result = orchestrator.uninstall_backend("vllm", confirm=True)

    assert result["uninstalled"] is True
    assert not (target / "venv").exists()
    assert (target / "operator-note.txt").read_text(encoding="utf-8") == "keep this file"


def test_cli_uninstall_preview_then_confirm_removes_only_managed_runtime(tmp_path):
    from rift.cli.commands import _backend
    from rift.cli.console import RiftConsole
    from rift.cli.parser import build_parser

    runtime_home, target = _managed_venv(tmp_path)
    orchestrator = _orchestrator(runtime_home)
    output = io.StringIO()
    preview_args = build_parser().parse_args(["backend", "uninstall", "vllm"])
    with contextlib.redirect_stdout(output):
        preview_status = _backend(preview_args, RiftConsole(no_color=True), orchestrator)
    assert preview_status == 2
    assert str(target.resolve()) in output.getvalue()
    assert (target / "venv").is_dir()

    confirm_args = build_parser().parse_args(["backend", "uninstall", "vllm", "--confirm"])
    with contextlib.redirect_stdout(output):
        remove_status = _backend(confirm_args, RiftConsole(no_color=True), orchestrator)
    assert remove_status == 0
    assert not (target / "venv").exists()
    assert (target / "operator-note.txt").read_text(encoding="utf-8") == "keep this file"


def test_uninstall_preserves_models_and_neighbor_backend(tmp_path):
    runtime_home, _target = _managed_venv(tmp_path)
    model = runtime_home / "models" / "model.gguf"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"model data")
    neighbor = runtime_home / "backends" / "sglang" / "venv" / "keep.txt"
    neighbor.parent.mkdir(parents=True)
    neighbor.write_text("neighbor", encoding="utf-8")
    orchestrator = _orchestrator(runtime_home)

    orchestrator.uninstall_backend("vllm", confirm=True)

    assert model.read_bytes() == b"model data"
    assert neighbor.read_text(encoding="utf-8") == "neighbor"


def test_uninstall_wsl_uses_only_verified_runtime_path(tmp_path, monkeypatch):
    module = _managed_module()
    runtime_home = tmp_path / "rift-home"
    target = runtime_home / "backends" / "vllm"
    target.mkdir(parents=True)
    wsl_metadata = {
        "adapter_id": "vllm",
        "python": "/home/rift/.local/share/rift/backends/vllm/venv/bin/python",
        "managed_marker": "RIFT_MANAGED_VENV=/home/rift/.local/share/rift/backends/vllm/venv",
        "packages": ["vllm"],
    }
    (target / "wsl-install.json").write_text(json.dumps(wsl_metadata), encoding="utf-8")
    module.record_managed_installation(runtime_home, "vllm", target, "wsl-venv", wsl_metadata)
    monkeypatch.setattr(module, "wsl_detection", lambda: {"available": True, "executable": "wsl.exe"}, raising=False)
    calls = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda args, **kwargs: calls.append(args) or subprocess.CompletedProcess(args, 0, "", ""),
    )

    result = _orchestrator(runtime_home).uninstall_backend("vllm", confirm=True)

    assert result["uninstalled"] is True
    assert calls == [
        [
            "wsl.exe",
            "--",
            "bash",
            "-lc",
            "set -eu; environment=\"$HOME/.local/share/rift/backends/vllm/venv\"; "
            "marker=\"$environment/.rift-managed-install\"; "
            "expected=\"RIFT_MANAGED_VENV=$HOME/.local/share/rift/backends/vllm/venv\"; "
            "[ -f \"$marker\" ] && [ \"$(cat \"$marker\")\" = \"$expected\" ] "
            "|| { echo 'RIFT WSL ownership marker mismatch; runtime left untouched' >&2; exit 73; }; "
            "rm -rf -- \"$environment\"",
        ]
    ]


def test_backend_runtime_lock_serializes_same_backend_instances(tmp_path):
    import threading

    shared_home = tmp_path / "shared-runtime"
    first = _orchestrator(shared_home)
    second = _orchestrator(shared_home)
    first_inside = threading.Event()
    release_first = threading.Event()
    second_inside = threading.Event()

    def hold_first():
        with first._backend_runtime_lock("vllm"):
            first_inside.set()
            assert release_first.wait(5)

    def enter_second():
        assert first_inside.wait(5)
        with second._backend_runtime_lock("vllm"):
            second_inside.set()

    first_thread = threading.Thread(target=hold_first)
    second_thread = threading.Thread(target=enter_second)
    first_thread.start()
    second_thread.start()
    try:
        assert first_inside.wait(5)
        assert not second_inside.wait(0.15)
        release_first.set()
        assert second_inside.wait(5)
    finally:
        release_first.set()
        first_thread.join(5)
        second_thread.join(5)
    assert not first_thread.is_alive()
    assert not second_thread.is_alive()


def test_failed_uninstall_keeps_registry_entry(tmp_path, monkeypatch):
    module = _managed_module()
    runtime_home, target = _managed_venv(tmp_path)
    orchestrator = _orchestrator(runtime_home)

    def fail_remove(*_args, **_kwargs):
        raise OSError("fixture removal failure")

    monkeypatch.setattr(module.shutil, "rmtree", fail_remove)
    with pytest.raises(OSError, match="fixture removal failure"):
        orchestrator.uninstall_backend("vllm", confirm=True)

    assert module.inspect_managed_installation(runtime_home, "vllm")["managed"] is True
    assert (target / "venv").is_dir()


def test_backend_status_exposes_removable_installation(tmp_path):
    from rift.backends.vllm.backend import VllmProvider

    runtime_home, _target = _managed_venv(tmp_path)
    orchestrator = _orchestrator(runtime_home)
    provider = VllmProvider()
    provider.detect = lambda search_root=None: {"backend": "vllm", "available": True, "executable": "vllm"}
    orchestrator.providers = {"vllm": provider}

    status = orchestrator.backend_status()

    assert status["providers"]["vllm"]["installation"]["removable"] is True
