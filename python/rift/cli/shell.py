"""Interactive RIFT command shell."""

from __future__ import annotations

import argparse
import asyncio
import os
import shlex
import shutil
from collections.abc import Callable
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.application import run_in_terminal
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.input import Input
from prompt_toolkit.output import Output

from rift.runtime_paths import RiftPaths

from .console import RiftConsole
from .parser import build_parser
from .shell_commands import ShellCompleter, execute_shell_line
from .shell_status import StatusCollector, format_status_toolbar


async def _run_prompt(
    *,
    parser: argparse.ArgumentParser,
    no_color: bool,
    session_factory: Callable[..., Any],
    status_factory: Callable[..., Any],
    input: Input | None = None,
    output: Output | None = None,
) -> int:
    status = status_factory(RiftPaths.from_environment())
    console = RiftConsole(no_color=no_color)
    stop_event = asyncio.Event()
    tasks = [
        asyncio.create_task(status.run_system(stop_event), name="rift-shell-system-status"),
        asyncio.create_task(status.run_rift(stop_event), name="rift-shell-rift-status"),
    ]

    def toolbar() -> list[tuple[str, str]]:
        width = shutil.get_terminal_size((100, 24)).columns
        return format_status_toolbar(status.snapshot(), width)

    session_options: dict[str, Any] = {
        "history": InMemoryHistory(),
        "completer": ShellCompleter(parser),
        "refresh_interval": 1.0,
        "bottom_toolbar": toolbar,
    }
    if input is not None:
        session_options["input"] = input
    if output is not None:
        session_options["output"] = output

    try:
        session = session_factory(**session_options)
        while True:
            try:
                line = await session.prompt_async("rift> ")
            except (KeyboardInterrupt, EOFError):
                break
            if not line.strip():
                continue
            try:
                tokens = shlex.split(line, posix=(os.name != "nt"))
            except ValueError:
                tokens = []
            if tokens and tokens[0].lower() == "rift":
                tokens.pop(0)
            if len(tokens) == 1 and tokens[0].lower() in {"exit", "quit"}:
                break
            try:
                result = await run_in_terminal(
                    lambda: execute_shell_line(line, parser, console),
                    in_executor=True,
                )
            except Exception as exc:
                console.error(f"Command failed: {exc}")
                continue
            if result is None:
                break
        return 0
    finally:
        stop_event.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def run_shell(
    *,
    parser: argparse.ArgumentParser | None = None,
    no_color: bool = False,
    session_factory: Callable[..., Any] = PromptSession,
    status_factory: Callable[..., Any] = StatusCollector,
    input: Input | None = None,
    output: Output | None = None,
) -> int:
    """Run the interactive prompt in the current console."""

    return asyncio.run(
        _run_prompt(
            parser=parser or build_parser(),
            no_color=no_color,
            session_factory=session_factory,
            status_factory=status_factory,
            input=input,
            output=output,
        )
    )


__all__ = ["run_shell"]
