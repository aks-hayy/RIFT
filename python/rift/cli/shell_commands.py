"""Parser-backed command and help handling for the interactive RIFT shell."""

from __future__ import annotations

import argparse
import os
import shlex
import sys
from collections.abc import Callable, Sequence
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from typing import Any

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

from .commands import execute
from .console import RiftConsole


def _subparser_for(parser: argparse.ArgumentParser, name: str) -> argparse.ArgumentParser | None:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            candidate = action.choices.get(name)
            if isinstance(candidate, argparse.ArgumentParser):
                return candidate
    return None


def shell_help_text(parser: argparse.ArgumentParser, path: Sequence[str]) -> str:
    """Return formatted parser help for the root, a group, or a command."""

    current = parser
    for name in path:
        child = _subparser_for(current, str(name))
        if child is None:
            parent = " ".join(path[: path.index(name)])
            target = f"{parent} {name}".strip()
            return f"No help available for: {target}\n"
        current = child
    text = current.format_help()
    if not path:
        text += (
            "\nInteractive shell controls:\n"
            "  help [GROUP [COMMAND]]  Show main, group, or command help\n"
            "  exit, quit, Ctrl+C      Leave the RIFT shell\n"
            "  Tab                     Complete commands and options\n"
        )
    return text


class ShellCompleter(Completer):
    """Complete parser subcommands and options without guessing values."""

    def __init__(self, parser: argparse.ArgumentParser) -> None:
        self.parser = parser

    def get_completions(self, document: Document, complete_event):
        text = document.text_before_cursor
        try:
            tokens = shlex.split(text, posix=(os.name != "nt"))
        except ValueError:
            return
        if text and text[-1].isspace():
            current = ""
        elif tokens:
            current = tokens.pop()
        else:
            current = ""
        if tokens and tokens[0].lower() == "rift":
            tokens.pop(0)

        help_mode = bool(tokens and tokens[0].lower() == "help")
        if help_mode:
            tokens = tokens[1:]
        target = self.parser
        for token in tokens:
            if token.startswith("-"):
                return
            child = _subparser_for(target, token)
            if child is None:
                return
            target = child

        candidates: list[str] = []
        for action in target._actions:
            if isinstance(action, argparse._SubParsersAction):
                candidates.extend(action.choices.keys())
            elif not help_mode:
                candidates.extend(action.option_strings)
        prefix = current.casefold()
        for candidate in dict.fromkeys(candidates):
            if candidate.casefold().startswith(prefix):
                yield Completion(candidate[len(current):], start_position=-len(current))


def execute_shell_line(
    line: str,
    parser: argparse.ArgumentParser,
    console: RiftConsole,
    executor: Callable[[Any, RiftConsole], int] = execute,
) -> int | None:
    """Parse one shell line and execute it through the existing CLI handler."""

    try:
        tokens = shlex.split(line, posix=(os.name != "nt"))
    except ValueError as exc:
        print(f"RIFT shell: {exc}", file=sys.stderr)
        return 2
    if tokens and tokens[0].lower() == "rift":
        tokens.pop(0)
    if not tokens:
        return None

    command = tokens[0].lower()
    if command in {"exit", "quit"} and len(tokens) == 1:
        return None
    if command == "help":
        help_text = shell_help_text(parser, tokens[1:])
        print(help_text, end="")
        return 0

    stdout = StringIO()
    stderr = StringIO()
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            args = parser.parse_args(tokens)
    except SystemExit as exc:
        output = stdout.getvalue()
        error = stderr.getvalue()
        if output:
            print(output, end="")
        if error:
            print(error, end="", file=sys.stderr)
        return int(exc.code or 0)

    return int(executor(args, console))


__all__ = ["ShellCompleter", "execute_shell_line", "shell_help_text"]
