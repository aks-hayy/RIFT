"""Run a command inside a normalized Visual Studio C++ environment."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


def _visual_studio_environment() -> dict[str, str]:
    program_files_x86 = os.environ.get("ProgramFiles(x86)")
    if not program_files_x86:
        raise RuntimeError("ProgramFiles(x86) is not defined; this helper requires Windows")

    vswhere = Path(program_files_x86) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.is_file():
        raise RuntimeError(f"Visual Studio Installer was not found at {vswhere}")

    query = subprocess.run(
        [
            str(vswhere),
            "-latest",
            "-products",
            "*",
            "-requires",
            "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
            "-property",
            "installationPath",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    installation = query.stdout.strip().splitlines()
    if not installation:
        raise RuntimeError("Visual Studio C++ Build Tools are not installed")

    dev_command = Path(installation[0]) / "Common7" / "Tools" / "VsDevCmd.bat"
    if not dev_command.is_file():
        raise RuntimeError(f"Visual Studio developer command file was not found at {dev_command}")

    bootstrap_environment = {
        name: value for name, value in os.environ.items() if name.lower() != "path"
    }
    bootstrap_environment["PATH"] = os.environ.get("PATH") or os.environ.get("Path", "")
    command = f'call "{dev_command}" -arch=x64 -host_arch=x64 >nul && set'
    captured = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=bootstrap_environment,
        executable=os.environ.get("ComSpec", "cmd.exe"),
        shell=True,
    )
    if captured.returncode != 0:
        detail = (captured.stderr or captured.stdout).strip()
        raise RuntimeError(
            "Visual Studio developer environment initialization failed"
            + (f": {detail}" if detail else "")
        )

    environment: dict[str, str] = {}
    uppercase_path: str | None = None
    for line in captured.stdout.splitlines():
        name, separator, value = line.partition("=")
        if not separator or not name:
            continue
        if name == "PATH":
            uppercase_path = value
            continue
        if name.lower() == "path":
            environment.setdefault("PATH", value)
            continue
        environment[name] = value
    if uppercase_path is not None:
        environment["PATH"] = uppercase_path
    return environment


def _resolve_executable(value: str, environment: dict[str, str]) -> str:
    path = Path(value)
    if path.is_file():
        return str(path.resolve())
    resolved = shutil.which(value, path=environment.get("PATH"))
    if not resolved:
        raise RuntimeError(f"Executable was not found: {value}")
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a command in the latest Visual Studio x64 C++ developer environment."
    )
    parser.add_argument("executable", help="Executable path or name")
    parser.add_argument("arguments", nargs=argparse.REMAINDER, help="Arguments passed to the executable")
    args = parser.parse_args(argv)

    environment = _visual_studio_environment()
    executable = _resolve_executable(args.executable, environment)
    return subprocess.call([executable, *args.arguments], env=environment)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"windows_dev: {error}", file=sys.stderr)
        raise SystemExit(1)
