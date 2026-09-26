import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from rift.gateway_manager import GatewayManager  # noqa: E402


def test_start_main_is_idempotent_and_persists_state(tmp_path, monkeypatch):
    manager = GatewayManager(tmp_path, tmp_path / "runtime", python_executable="python")
    monkeypatch.setattr(manager, "_spawn", lambda target: {"pid": 1234})
    monkeypatch.setattr(manager, "_process_alive", lambda pid: True)
    first = manager.start_main(tmp_path / "rift.yaml")
    second = manager.start_main(tmp_path / "rift.yaml")
    assert first["started"] is True
    assert second["started"] is False
    assert second["status"] == "running"
    assert (tmp_path / "runtime" / "gateway" / "state.json").is_file()


def test_stop_main_is_idempotent(tmp_path, monkeypatch):
    manager = GatewayManager(tmp_path, tmp_path / "runtime")
    monkeypatch.setattr(manager, "_process_alive", lambda pid: True)
    killed = []
    monkeypatch.setattr(manager, "_terminate", lambda pid: killed.append(pid))
    manager._write_state({"kind": "main", "pid": 44, "status": "running"}, manager.state_path)
    assert manager.stop_main()["status"] == "stopped"
    assert killed == [44]
    assert manager.stop_main()["status"] in {"stopped", "not_started"}


def test_dead_pid_reports_stale(tmp_path, monkeypatch):
    manager = GatewayManager(tmp_path, tmp_path / "runtime")
    manager._write_state({"kind": "main", "pid": 44, "status": "running"}, manager.state_path)
    monkeypatch.setattr(manager, "_process_alive", lambda pid: False)
    assert manager.status()["status"] == "stale"


def test_group_state_uses_safe_group_path(tmp_path):
    manager = GatewayManager(tmp_path, tmp_path / "runtime")
    manager._write_group_state("team-a", {"kind": "group", "group_id": "team-a", "status": "stopped"})
    assert (tmp_path / "runtime" / "gateway" / "groups" / "team-a" / "state.json").is_file()
    payload = json.loads(
        (tmp_path / "runtime" / "gateway" / "groups" / "team-a" / "state.json").read_text()
    )
    assert payload["group_id"] == "team-a"
