from __future__ import annotations

import asyncio
import sys
import json
import sqlite3
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

core = types.ModuleType("rift._core")
core.InferenceEngine = object
core.__version__ = "test"
core.build_info = lambda: {}
core.cuda_device_count = lambda: 0
core.inspect_model = lambda *args, **kwargs: {}
core.parse_model_topology = lambda *args, **kwargs: {}
sys.modules.setdefault("rift._core", core)

from rift.cli.console import RiftConsole
from rift.cli.parser import build_parser
from rift.cli.shell_commands import execute_shell_line, shell_help_text
from rift.runtime_paths import RiftPaths
from rift.cli.shell_status import StatusCollector, format_status_toolbar, read_status_snapshot


def test_shell_dispatch_uses_existing_executor_for_nested_command() -> None:
    calls = []
    parser = build_parser()
    code = execute_shell_line(
        "model recommend --task chat",
        parser,
        RiftConsole(no_color=True),
        executor=lambda args, console: calls.append(args) or 7,
    )

    assert code == 7
    assert calls[0].command == "model"
    assert calls[0].model_command == "recommend"
    assert calls[0].task == "chat"


def test_shell_dispatch_strips_optional_rift_prefix() -> None:
    calls = []
    code = execute_shell_line(
        "rift mesh service list",
        build_parser(),
        RiftConsole(no_color=True),
        executor=lambda args, console: calls.append(args) or 0,
    )

    assert code == 0
    assert calls[0].command == "mesh"
    assert calls[0].mesh_command == "service"
    assert calls[0].mesh_service_command == "list"


def test_shell_help_levels_follow_the_existing_parser() -> None:
    parser = build_parser()

    main_help = shell_help_text(parser, [])
    model_help = shell_help_text(parser, ["model"])
    recommend_help = shell_help_text(parser, ["model", "recommend"])

    assert "model" in main_help
    assert "recommend" in model_help
    assert "--task" in recommend_help


def test_shell_help_never_calls_the_command_executor(capsys) -> None:
    def forbidden_executor(args, console):
        raise AssertionError("help must not execute a command")

    code = execute_shell_line(
        "help model recommend",
        build_parser(),
        RiftConsole(no_color=True),
        executor=forbidden_executor,
    )

    assert code == 0
    assert "--task" in capsys.readouterr().out


def test_shell_parser_errors_return_status_two_instead_of_exiting(capsys) -> None:
    code = execute_shell_line(
        "model recommend --not-a-real-option",
        build_parser(),
        RiftConsole(no_color=True),
        executor=lambda args, console: 0,
    )

    assert code == 2
    assert "unrecognized arguments" in capsys.readouterr().err


def test_status_snapshot_reads_sqlite_without_rewriting_state_or_mirror(tmp_path) -> None:
    paths = RiftPaths(tmp_path / "rift-home")
    paths.home.mkdir()
    payload = {
        "services": {"chat": {"phase": "healthy"}},
        "nodes": {"node-a": {"status": "enrolled"}},
    }
    with sqlite3.connect(paths.state) as connection:
        connection.execute(
            "CREATE TABLE control_state (id INTEGER PRIMARY KEY, revision INTEGER NOT NULL, "
            "updated_unix_seconds REAL NOT NULL, payload TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO control_state VALUES (1, 1, 1.0, ?)",
            (json.dumps(payload),),
        )
    paths.state_mirror.write_text("keep this mirror byte for byte", encoding="utf-8")
    state_before = paths.state.read_bytes()
    mirror_before = paths.state_mirror.read_bytes()

    snapshot = read_status_snapshot(paths)

    assert snapshot["available"] is True
    assert snapshot["source"] == "sqlite"
    assert snapshot["service_count"] == 1
    assert snapshot["node_count"] == 1
    assert paths.state.read_bytes() == state_before
    assert paths.state_mirror.read_bytes() == mirror_before


def test_status_snapshot_uses_legacy_json_without_creating_sqlite(tmp_path) -> None:
    paths = RiftPaths(tmp_path / "rift-home")
    paths.home.mkdir()
    paths.state_mirror.write_text(
        json.dumps({"services": {}, "nodes": {}}), encoding="utf-8"
    )

    snapshot = read_status_snapshot(paths)

    assert snapshot["available"] is True
    assert snapshot["source"] == "json"
    assert snapshot["service_count"] == 0
    assert snapshot["node_count"] == 0
    assert not paths.state.exists()


def test_status_snapshot_does_not_count_malformed_entries_as_zero(tmp_path) -> None:
    paths = RiftPaths(tmp_path / "rift-home")
    paths.home.mkdir()
    paths.state_mirror.write_text(
        json.dumps({"services": {"chat": "invalid entry"}, "nodes": {}}),
        encoding="utf-8",
    )

    snapshot = read_status_snapshot(paths)

    assert snapshot["available"] is True
    assert snapshot["service_count"] is None
    assert snapshot["node_count"] == 0


def test_status_snapshot_reports_unknown_without_creating_state_files(tmp_path) -> None:
    paths = RiftPaths(tmp_path / "rift-home")

    snapshot = read_status_snapshot(paths)

    assert snapshot["available"] is False
    assert snapshot["service_count"] is None
    assert snapshot["node_count"] is None
    assert not paths.home.exists()


def test_status_snapshot_reports_unknown_for_corrupt_state_without_repairing(tmp_path) -> None:
    paths = RiftPaths(tmp_path / "rift-home")
    paths.home.mkdir()
    paths.state.write_bytes(b"not a sqlite database")
    paths.state_mirror.write_text("not json", encoding="utf-8")
    database_before = paths.state.read_bytes()
    mirror_before = paths.state_mirror.read_bytes()

    snapshot = read_status_snapshot(paths)

    assert snapshot["available"] is False
    assert snapshot["service_count"] is None
    assert snapshot["node_count"] is None
    assert paths.state.read_bytes() == database_before
    assert paths.state_mirror.read_bytes() == mirror_before


def test_status_snapshot_reads_wal_database_without_creating_state_files(tmp_path) -> None:
    paths = RiftPaths(tmp_path / "rift-home")
    paths.home.mkdir()
    payload = {"services": {}, "nodes": {}}
    connection = sqlite3.connect(paths.state)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            "CREATE TABLE control_state (id INTEGER PRIMARY KEY, revision INTEGER NOT NULL, "
            "updated_unix_seconds REAL NOT NULL, payload TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO control_state VALUES (1, 1, 1.0, ?)",
            (json.dumps(payload),),
        )
        connection.commit()
        paths.state_mirror.write_text("unchanged", encoding="utf-8")
        names_before = {path.name for path in paths.home.iterdir()}
        database_before = paths.state.read_bytes()
        mirror_before = paths.state_mirror.read_bytes()

        snapshot = read_status_snapshot(paths)

        assert snapshot["source"] == "sqlite"
        assert snapshot["service_count"] == 0
        assert snapshot["node_count"] == 0
        assert {path.name for path in paths.home.iterdir()} == names_before
        assert paths.state.read_bytes() == database_before
        assert paths.state_mirror.read_bytes() == mirror_before
    finally:
        connection.close()


def test_status_collector_keeps_failed_sources_unknown_not_zero(tmp_path) -> None:
    class FailingLocalCollector:
        def collect(self):
            raise OSError("telemetry unavailable")

    def failing_snapshot_reader(paths):
        raise OSError("state unavailable")

    collector = StatusCollector(
        RiftPaths(tmp_path / "rift-home"),
        local_collector=FailingLocalCollector(),
        snapshot_reader=failing_snapshot_reader,
    )
    collector.refresh_system()
    collector.refresh_rift()

    snapshot = collector.snapshot()
    toolbar = "".join(text for _, text in format_status_toolbar(snapshot, 100))

    assert snapshot["system"]["cpu_percent"] is None
    assert snapshot["system"]["host_ram_pressure_percent"] is None
    assert snapshot["rift"]["service_count"] is None
    assert snapshot["rift"]["node_count"] is None
    assert "CPU unknown" in toolbar
    assert "SERVICES ?" in toolbar
    assert "NODES ?" in toolbar


def test_status_collector_refresh_loops_run_at_independent_intervals(tmp_path) -> None:
    calls = {"system": 0, "rift": 0}
    stop_event = asyncio.Event()

    class CountingLocalCollector:
        def collect(self):
            calls["system"] += 1
            return {"cpu_percent": 12.0, "host_ram_pressure_percent": 34.0}

    def count_rift_snapshot(paths):
        calls["rift"] += 1
        return {
            "available": True,
            "source": "sqlite",
            "service_count": 0,
            "node_count": 0,
            "services": [],
            "nodes": [],
            "error": None,
        }

    collector = StatusCollector(
        RiftPaths(tmp_path / "rift-home"),
        system_interval=0.11,
        rift_interval=0.22,
        local_collector=CountingLocalCollector(),
        snapshot_reader=count_rift_snapshot,
    )

    async def run_refreshers() -> None:
        system_task = asyncio.create_task(collector.run_system(stop_event))
        rift_task = asyncio.create_task(collector.run_rift(stop_event))
        await asyncio.sleep(0.48)
        stop_event.set()
        await asyncio.gather(system_task, rift_task)

    asyncio.run(run_refreshers())

    assert calls["system"] >= 4
    assert calls["rift"] >= 2
