"""RIFT command-line entry point."""

from __future__ import annotations

import os
import sys
import traceback

from .commands import execute
from .console import RiftConsole
from .parser import build_parser


_COMPATIBILITY_ALIASES: dict[str, list[str]] = {}


def _normalize_argv(argv: list[str]) -> tuple[list[str], str | None]:
    values = list(argv)
    for option in ("--json", "--no-color", "--debug"):
        if option in values:
            values.remove(option)
            values.insert(0, option)
    command_index = next((index for index, value in enumerate(values) if not value.startswith("-")), None)
    if command_index is None:
        return values, None
    old = values[command_index]
    replacement = _COMPATIBILITY_ALIASES.get(old)
    if not replacement:
        warning = None
    else:
        values[command_index : command_index + 1] = replacement
        warning = f"`rift {old}` is deprecated; use `rift {' '.join(replacement)}`."
    option_aliases = {
        "--overwrite": "--force",
        "--models-dir": "--models",
        "--interval-seconds": "--interval",
        "--warmup-runs": "--warmups",
        "--startup-timeout-seconds": "--startup-timeout",
    }
    values = [option_aliases.get(value, value) for value in values]
    return values, warning


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    normalized, compatibility_warning = _normalize_argv(raw)
    parser = build_parser()
    args = parser.parse_args(normalized)
    console = RiftConsole(json_output=args.json, no_color=args.no_color)
    command_parts = [args.command]
    nested_name = f"{args.command}_command"
    if hasattr(args, nested_name):
        command_parts.append(str(getattr(args, nested_name)))
    console.banner(" ".join(command_parts))
    if compatibility_warning and not args.json:
        console.warning(compatibility_warning)
    try:
        return int(execute(args, console))
    except KeyboardInterrupt:
        console.warning("Interrupted. RIFT left persisted state intact.")
        return 130
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        console.error(str(exc), hint="Run the command with --help or add --debug for a traceback.")
        if args.debug or os.environ.get("RIFT_DEBUG") == "1":
            traceback.print_exc()
        return 1
    except Exception as exc:  # defensive CLI boundary
        console.error(f"Unexpected failure: {exc}", hint="Run with --debug and attach `rift system diagnostics`.")
        if args.debug or os.environ.get("RIFT_DEBUG") == "1":
            traceback.print_exc()
        return 1


__all__ = ["build_parser", "main"]
