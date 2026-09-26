from __future__ import annotations

import asyncio
import sys
import json
import sqlite3
import types
from pathlib import Path

import pytest


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
    assert "shell" in main_help
    assert "exit" in main_help
    assert "Ctrl+C" in main_help
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


def test_shell_completer_uses_nested_parser_commands_and_options() -> None:
    from prompt_toolkit.completion import CompleteEvent
    from prompt_toolkit.document import Document

    from rift.cli.shell_commands import ShellCompleter

    completer = ShellCompleter(build_parser())

    def completions(text: str) -> set[str]:
        return {
            item.text
            for item in completer.get_completions(Document(text), CompleteEvent())
        }

    assert "model" in completions("")
    assert "recommend" in completions("model ")
    assert "--task" in completions("model recommend ")
    assert completions("model pull C:\\models\\custom.gguf") == set()


def test_shell_prompt_uses_ephemeral_history_completion_and_refreshing_toolbar(monkeypatch) -> None:
    from prompt_toolkit.input import DummyInput
    from prompt_toolkit.output import DummyOutput

    from rift.cli import shell

    captured = {}

    class FakeStatus:
        def __init__(self, paths):
            self.stopped = []

        def snapshot(self):
            return {"system": {}, "rift": {}}

        async def run_system(self, stop_event):
            await stop_event.wait()
            self.stopped.append("system")

        async def run_rift(self, stop_event):
            await stop_event.wait()
            self.stopped.append("rift")

    class FakeSession:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.lines = iter(["exit"])

        async def prompt_async(self, prompt):
            captured["prompt"] = prompt
            return next(self.lines)

    async def direct_terminal(callback, *, in_executor):
        return callback()

    monkeypatch.setattr(shell, "run_in_terminal", direct_terminal)

    result = shell.run_shell(
        parser=build_parser(),
        no_color=True,
        session_factory=lambda **kwargs: FakeSession(**kwargs),
        status_factory=FakeStatus,
        input=DummyInput(),
        output=DummyOutput(),
    )

    assert result == 0
    assert captured["prompt"] == "rift> "
    assert captured["refresh_interval"] == 1.0
    assert captured["history"].__class__.__name__ == "InMemoryHistory"
    assert captured["completer"].__class__.__name__ == "ShellCompleter"
    assert captured["bottom_toolbar"]()  # toolbar is computed from current status


def test_default_prompt_session_handles_eof_without_creating_rift_state() -> None:
    from prompt_toolkit.input import DummyInput
    from prompt_toolkit.output import DummyOutput

    from rift.cli.shell import run_shell

    assert run_shell(
        parser=build_parser(), input=DummyInput(), output=DummyOutput()
    ) == 0


def test_shell_prompt_remains_usable_when_status_refresh_fails(monkeypatch) -> None:
    from rift.cli import shell

    prompts = []

    class FailingStatus:
        def __init__(self, paths):
            pass

        def snapshot(self):
            return {"system": {}, "rift": {}}

        async def run_system(self, stop_event):
            raise RuntimeError("telemetry unavailable")

        async def run_rift(self, stop_event):
            raise RuntimeError("state unavailable")

    class FakeSession:
        def __init__(self, **kwargs):
            pass

        async def prompt_async(self, prompt):
            prompts.append(prompt)
            if len(prompts) == 1:
                return "help model recommend"
            return "exit"

    async def direct_terminal(callback, *, in_executor):
        return callback()

    monkeypatch.setattr(shell, "run_in_terminal", direct_terminal)
    monkeypatch.setattr(shell, "execute_shell_line", lambda *args: 0)
    assert shell.run_shell(
        parser=build_parser(),
        session_factory=lambda **kwargs: FakeSession(**kwargs),
        status_factory=FailingStatus,
    ) == 0
    assert prompts == ["rift> ", "rift> "]


def test_shell_ctrl_c_and_eof_close_prompt_and_sampler(monkeypatch) -> None:
    from rift.cli import shell

    for raised in (KeyboardInterrupt(), EOFError()):
        stopped = []

        class FakeStatus:
            def __init__(self, paths):
                pass

            def snapshot(self):
                return {"system": {}, "rift": {}}

            async def run_system(self, stop_event):
                try:
                    await stop_event.wait()
                finally:
                    stopped.append("system")

            async def run_rift(self, stop_event):
                try:
                    await stop_event.wait()
                finally:
                    stopped.append("rift")

        class FakeSession:
            def __init__(self, **kwargs):
                pass

            async def prompt_async(self, prompt):
                await asyncio.sleep(0)
                raise raised

        assert shell.run_shell(
            parser=build_parser(),
            session_factory=lambda **kwargs: FakeSession(**kwargs),
            status_factory=FakeStatus,
        ) == 0
        assert sorted(stopped) == ["rift", "system"]


def test_shell_command_runs_in_terminal_executor_and_recovers_from_error(monkeypatch) -> None:
    from rift.cli import shell

    lines = iter(["model recommend --task chat", "exit"])
    captured = []

    class FakeStatus:
        def __init__(self, paths):
            pass

        def snapshot(self):
            return {"system": {}, "rift": {}}

        async def run_system(self, stop_event):
            await stop_event.wait()

        async def run_rift(self, stop_event):
            await stop_event.wait()

    class FakeSession:
        def __init__(self, **kwargs):
            pass

        async def prompt_async(self, prompt):
            return next(lines)

    async def fake_run_in_terminal(callback, *, in_executor):
        captured.append(in_executor)
        return callback()

    monkeypatch.setattr(shell, "run_in_terminal", fake_run_in_terminal)
    monkeypatch.setattr(
        shell,
        "execute_shell_line",
        lambda *args: (_ for _ in ()).throw(RuntimeError("command failed")),
    )
    assert shell.run_shell(
        parser=build_parser(),
        session_factory=lambda **kwargs: FakeSession(**kwargs),
        status_factory=FakeStatus,
    ) == 0
    assert captured == [True]


def test_shell_parser_errors_return_to_prompt(monkeypatch, capsys) -> None:
    from rift.cli import shell

    lines = iter(["model recommend --not-a-real-option", "exit"])
    prompts = []

    class FakeStatus:
        def __init__(self, paths):
            pass

        def snapshot(self):
            return {"system": {}, "rift": {}}

        async def run_system(self, stop_event):
            await stop_event.wait()

        async def run_rift(self, stop_event):
            await stop_event.wait()

    class FakeSession:
        def __init__(self, **kwargs):
            pass

        async def prompt_async(self, prompt):
            prompts.append(prompt)
            return next(lines)

    async def direct_terminal(callback, *, in_executor):
        return callback()

    monkeypatch.setattr(shell, "run_in_terminal", direct_terminal)
    assert shell.run_shell(
        parser=build_parser(),
        session_factory=lambda **kwargs: FakeSession(**kwargs),
        status_factory=FakeStatus,
    ) == 0
    assert prompts == ["rift> ", "rift> "]
    assert "unrecognized arguments" in capsys.readouterr().err


def test_shell_toolbar_adapts_to_normal_and_narrow_widths() -> None:
    snapshot = {
        "system": {"cpu_percent": 24, "host_ram_pressure_percent": 61},
        "rift": {"service_count": 2, "node_count": 3},
        "cpu_history": [10, 20, 30],
        "memory_history": [50, 60, 70],
    }

    for width in (100, 60):
        toolbar = format_status_toolbar(snapshot, width)[0][1]
        assert "CPU" in toolbar
        assert "MEM" in toolbar
        assert "SVC" in toolbar or "SERVICES" in toolbar
        assert "NODE" in toolbar
        assert len(toolbar) <= width


def test_cli_one_shot_command_does_not_open_shell(monkeypatch) -> None:
    from rift import cli

    called = []
    monkeypatch.setattr(cli, "execute", lambda args, console: called.append(args) or 9)
    monkeypatch.setattr("rift.cli.shell.run_shell", lambda **kwargs: pytest.fail("shell called"), raising=False)

    assert cli.main(["model", "recommend", "--task", "chat"]) == 9
    assert called[0].command == "model"
    assert called[0].model_command == "recommend"


def test_explicit_shell_uses_current_console_and_forwards_no_color(monkeypatch) -> None:
    from rift import cli
    from rift.cli import shell

    calls = []
    monkeypatch.setattr(shell, "run_shell", lambda **kwargs: calls.append(kwargs) or 4)

    assert cli.main(["--no-color", "shell"]) == 4
    assert calls == [{"parser": calls[0]["parser"], "no_color": True}]
    assert calls[0]["parser"].parse_args(["shell"]).command == "shell"


def test_non_tty_bare_invocation_prints_help_without_running_shell(monkeypatch, capsys) -> None:
    from rift import cli

    monkeypatch.setattr(cli, "_stdin_stdout_are_ttys", lambda: False)
    monkeypatch.setattr(cli, "_launch_shell_window", lambda: pytest.fail("window launched"))
    monkeypatch.setattr(cli, "_is_windows", lambda: True)

    assert cli.main([]) == 0
    assert "RIFT fits LLM deployments" in capsys.readouterr().out


def test_bare_windows_tty_launches_one_shell_child(monkeypatch) -> None:
    from rift import cli

    calls = []
    monkeypatch.setattr(cli, "_stdin_stdout_are_ttys", lambda: True)
    monkeypatch.setattr(cli, "_is_windows", lambda: True)
    monkeypatch.setattr(cli, "_launch_shell_window", lambda: calls.append("new-window") or 0)
    monkeypatch.setattr("rift.cli.shell.run_shell", lambda **kwargs: pytest.fail("parent prompt started"), raising=False)

    assert cli.main([]) == 0
    assert calls == ["new-window"]


def test_windows_launcher_opens_one_child_with_shell_subcommand(monkeypatch) -> None:
    from rift import cli

    calls = []
    monkeypatch.setattr(cli.subprocess, "CREATE_NEW_CONSOLE", 0x10, raising=False)
    monkeypatch.setattr(cli.subprocess, "Popen", lambda args, **kwargs: calls.append((args, kwargs)))

    assert cli._launch_shell_window() == 0
    assert calls == [
        (
            [sys.executable, "-m", "rift.cli", "shell"],
            {"creationflags": 0x10, "close_fds": True},
        )
    ]


def test_json_mode_rejects_interactive_shell(monkeypatch, capsys) -> None:
    from rift import cli

    assert cli.main(["--json", "shell"]) == 2
    assert "cannot emit a single JSON response" in capsys.readouterr().err


def test_bare_posix_tty_runs_shell_in_process(monkeypatch) -> None:
    from rift import cli
    from rift.cli import shell

    calls = []
    monkeypatch.setattr(cli, "_stdin_stdout_are_ttys", lambda: True)
    monkeypatch.setattr(cli, "_is_windows", lambda: False)
    monkeypatch.setattr(shell, "run_shell", lambda **kwargs: calls.append(kwargs) or 0)

    assert cli.main([]) == 0
    assert calls == [{"parser": calls[0]["parser"]}]


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
