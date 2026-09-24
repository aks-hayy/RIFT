from __future__ import annotations

import sys
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
