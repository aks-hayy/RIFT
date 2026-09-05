"""Shared helpers for OpenAI-compatible external backend adapters."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Any
import venv
from urllib.error import URLError
from urllib.request import Request, urlopen


JsonDict = dict[str, Any]


def quote_command(args: list[str]) -> str:
    return " ".join(f'"{arg}"' if " " in arg else arg for arg in args)


def module_detection(module_name: str) -> JsonDict:
    spec = importlib.util.find_spec(module_name)
    if spec is None:
        return {"available": False, "module": module_name, "version": None}
    try:
        version = importlib.metadata.version(module_name)
    except importlib.metadata.PackageNotFoundError:
        version = None
    return {
        "available": True,
        "module": module_name,
        "version": version,
        "origin": spec.origin,
    }


def executable_detection(names: tuple[str, ...], env_names: tuple[str, ...]) -> JsonDict:
    checked: list[str] = []
    for env_name in env_names:
        checked.append(f"${env_name}")
        value = os.environ.get(env_name)
        if value and Path(value).is_file():
            return {
                "available": True,
                "executable": value,
                "source": f"env:{env_name}",
                "checked": checked,
            }
    for name in names:
        checked.append(name)
        found = shutil.which(name)
        if found:
            return {
                "available": True,
                "executable": found,
                "source": "PATH",
                "checked": checked,
            }
    return {
        "available": False,
        "executable": None,
        "source": None,
        "checked": checked,
    }


def run_version_command(args: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except Exception:
        return None
    text = (completed.stdout or completed.stderr or "").strip()
    return text.splitlines()[0][:200] if text else None


def probe_command_flags(command: list[str], flags: tuple[str, ...]) -> JsonDict:
    try:
        completed = subprocess.run(
            [*command, "--help"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"probed": False, "command": command, "error": str(exc), "flags": {}}
    text = f"{completed.stdout}\n{completed.stderr}"
    return {
        "probed": completed.returncode == 0 or bool(text.strip()),
        "command": command,
        "returncode": completed.returncode,
        "flags": {flag: flag in text for flag in flags},
        "output_sha256": __import__("hashlib").sha256(text.encode("utf-8")).hexdigest(),
    }


def install_python_packages(packages: list[str], *, pre: bool = False) -> JsonDict:
    args = [sys.executable, "-m", "pip", "install"]
    if pre:
        args.append("--pre")
    args.extend(packages)
    started = time.perf_counter()
    completed = subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    elapsed = time.perf_counter() - started
    return {
        "command": args,
        "display": quote_command(args),
        "returncode": completed.returncode,
        "elapsed_seconds": elapsed,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }


def isolated_environment_paths(target_dir: str | Path) -> JsonDict:
    root = Path(target_dir).resolve()
    environment = root / "venv"
    if os.name == "nt":
        python = environment / "Scripts" / "python.exe"
        binaries = environment / "Scripts"
    else:
        python = environment / "bin" / "python"
        binaries = environment / "bin"
    return {
        "root": str(root),
        "environment": str(environment),
        "python": str(python),
        "binaries": str(binaries),
    }


def isolated_executable_detection(
    target_dir: str | Path | None,
    names: tuple[str, ...],
) -> JsonDict:
    if not target_dir:
        return {"available": False, "executable": None, "source": None, "checked": []}
    paths = isolated_environment_paths(target_dir)
    binaries = Path(paths["binaries"])
    checked = []
    for name in names:
        candidates = [binaries / name]
        if os.name == "nt" and not name.lower().endswith(".exe"):
            candidates.append(binaries / f"{name}.exe")
        for candidate in candidates:
            checked.append(str(candidate))
            if candidate.is_file():
                return {
                    "available": True,
                    "executable": str(candidate),
                    "source": "rift-isolated-environment",
                    "checked": checked,
                    "environment": paths,
                }
    python = Path(paths["python"])
    return {
        "available": python.is_file(),
        "executable": str(python) if python.is_file() else None,
        "source": "rift-isolated-python" if python.is_file() else None,
        "checked": checked + [str(python)],
        "environment": paths,
        "python_only": python.is_file(),
    }


def install_python_packages_isolated(
    packages: list[str],
    *,
    target_dir: str | Path,
    pre: bool = False,
    force: bool = False,
) -> JsonDict:
    paths = isolated_environment_paths(target_dir)
    environment = Path(paths["environment"])
    python = Path(paths["python"])
    if force and environment.exists():
        import shutil as _shutil

        _shutil.rmtree(environment)
    if not python.is_file():
        Path(paths["root"]).mkdir(parents=True, exist_ok=True)
        venv.EnvBuilder(with_pip=True, clear=False, symlinks=os.name != "nt").create(environment)
    args = [str(python), "-m", "pip", "install", "--disable-pip-version-check"]
    if pre:
        args.append("--pre")
    args.extend(packages)
    started = time.perf_counter()
    completed = subprocess.run(args, check=False, capture_output=True, text=True, timeout=1800)
    return {
        "command": args,
        "display": quote_command(args),
        "returncode": completed.returncode,
        "elapsed_seconds": time.perf_counter() - started,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
        "environment": paths,
        "isolated": True,
    }


def isolated_module_detection(target_dir: str | Path | None, module_name: str) -> JsonDict:
    if not target_dir:
        return {"available": False, "module": module_name, "version": None}
    paths = isolated_environment_paths(target_dir)
    python = Path(paths["python"])
    if not python.is_file():
        return {
            "available": False,
            "module": module_name,
            "version": None,
            "environment": paths,
        }
    script = (
        "import importlib.metadata,importlib.util,json;"
        f"m={module_name!r};s=importlib.util.find_spec(m);"
        "v=None;"
        "\ntry:v=importlib.metadata.version(m.replace('_','-'))"
        "\nexcept importlib.metadata.PackageNotFoundError:pass"
        "\nprint(json.dumps({'available':s is not None,'module':m,'version':v,'origin':getattr(s,'origin',None)}))"
    )
    try:
        completed = subprocess.run(
            [str(python), "-c", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        payload = json.loads(completed.stdout.strip()) if completed.returncode == 0 else {}
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        payload = {}
    return {
        "available": bool(payload.get("available")),
        "module": module_name,
        "version": payload.get("version"),
        "origin": payload.get("origin"),
        "environment": paths,
    }


def container_runtime_detection() -> JsonDict:
    for name in ("docker", "podman"):
        executable = shutil.which(name)
        if executable:
            return {
                "available": True,
                "runtime": name,
                "executable": executable,
                "version": run_version_command([executable, "--version"]),
            }
    return {"available": False, "runtime": None, "executable": None}


def container_image_detection(image: str) -> JsonDict:
    runtime = container_runtime_detection()
    if not runtime.get("available"):
        return {**runtime, "image": image, "image_available": False}
    try:
        completed = subprocess.run(
            [str(runtime["executable"]), "image", "inspect", image],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {**runtime, "image": image, "image_available": False, "error": str(exc)}
    return {
        **runtime,
        "image": image,
        "image_available": completed.returncode == 0,
        "error": completed.stderr.strip()[:1000] if completed.returncode else None,
    }


def install_container_image(image: str) -> JsonDict:
    runtime = container_runtime_detection()
    if not runtime.get("available"):
        return {
            "installed": False,
            "changed": False,
            "image": image,
            "reason": "Docker or Podman is required for the requested container install.",
        }
    args = [str(runtime["executable"]), "pull", image]
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=1800,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "installed": False,
            "changed": False,
            "image": image,
            "command": args,
            "error": str(exc),
        }
    return {
        "installed": completed.returncode == 0,
        "changed": completed.returncode == 0,
        "image": image,
        "command": args,
        "display": quote_command(args),
        "returncode": completed.returncode,
        "elapsed_seconds": time.perf_counter() - started,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }


def wsl_detection() -> JsonDict:
    executable = shutil.which("wsl") or shutil.which("wsl.exe")
    if os.name != "nt" or not executable:
        return {"available": False, "executable": executable}
    try:
        completed = subprocess.run(
            [executable, "--status"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "executable": executable, "error": str(exc)}
    distributions: list[str] = []
    if completed.returncode == 0:
        try:
            listed = subprocess.run(
                [executable, "--list", "--quiet"],
                check=False,
                capture_output=True,
                timeout=5,
            )
            decoded = listed.stdout.decode("utf-16-le", errors="ignore") if b"\x00" in listed.stdout else listed.stdout.decode(errors="ignore")
            distributions = [item.strip().replace("\x00", "") for item in decoded.splitlines() if item.strip().replace("\x00", "")]
        except (OSError, subprocess.TimeoutExpired):
            distributions = []
    return {
        "available": completed.returncode == 0,
        "executable": executable,
        "status": (completed.stdout or completed.stderr).strip()[:1000],
        "distributions": distributions,
    }


def install_python_packages_wsl(
    packages: list[str],
    *,
    target_dir: str | Path,
    adapter_id: str,
    pre: bool = False,
    force: bool = False,
) -> JsonDict:
    wsl = wsl_detection()
    if not wsl.get("available"):
        return {
            "installed": False,
            "changed": False,
            "reason": "WSL2 is not available.",
            "wsl": wsl,
        }
    safe_id = re.sub(r"[^a-zA-Z0-9._-]+", "-", adapter_id).strip("-") or "adapter"
    environment = f"$HOME/.local/share/rift/backends/{safe_id}/venv"
    quoted_packages = " ".join(_shell_quote(item) for item in packages)
    pre_flag = " --pre" if pre else ""
    reset = f"rm -rf {environment} && " if force else ""
    script = (
        "set -eu; "
        f"{reset}"
        f"python3 -m venv {environment}; "
        f"{environment}/bin/python -m pip install --disable-pip-version-check{pre_flag} {quoted_packages}; "
        f"printf '\nRIFT_WSL_PYTHON=%s\n' \"$HOME/.local/share/rift/backends/{safe_id}/venv/bin/python\""
    )
    args = [str(wsl["executable"]), "--", "bash", "-lc", script]
    started = time.perf_counter()
    try:
        completed = subprocess.run(args, check=False, capture_output=True, text=True, timeout=1800)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"installed": False, "changed": False, "command": args, "error": str(exc)}
    match = re.search(r"RIFT_WSL_PYTHON=(.+)", completed.stdout)
    python_path = match.group(1).strip() if match else None
    metadata = {
        "adapter_id": adapter_id,
        "python": python_path,
        "packages": packages,
        "installed_unix_seconds": time.time(),
    }
    target = Path(target_dir)
    if completed.returncode == 0 and python_path:
        target.mkdir(parents=True, exist_ok=True)
        (target / "wsl-install.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return {
        "installed": completed.returncode == 0 and bool(python_path),
        "changed": completed.returncode == 0,
        "command": args,
        "display": quote_command(args[:4]) + " <isolated-install-script>",
        "returncode": completed.returncode,
        "elapsed_seconds": time.perf_counter() - started,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
        "wsl_python": python_path,
        "metadata": metadata,
    }


def wsl_install_detection(target_dir: str | Path | None, module_name: str) -> JsonDict:
    if not target_dir:
        return {"available": False, "module": module_name}
    metadata_path = Path(target_dir) / "wsl-install.json"
    if not metadata_path.is_file():
        return {"available": False, "module": module_name, "metadata_path": str(metadata_path)}
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"available": False, "module": module_name, "metadata_path": str(metadata_path)}
    wsl = wsl_detection()
    python_path = str(metadata.get("python") or "")
    if not wsl.get("available") or not python_path:
        return {"available": False, "module": module_name, "metadata": metadata, "wsl": wsl}
    try:
        completed = subprocess.run(
            [str(wsl["executable"]), "--", python_path, "-c", f"import {module_name};print('RIFT_OK')"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "module": module_name, "metadata": metadata, "error": str(exc)}
    return {
        "available": completed.returncode == 0 and "RIFT_OK" in completed.stdout,
        "module": module_name,
        "python": python_path,
        "source": "rift-wsl-isolated-environment",
        "metadata": metadata,
        "error": completed.stderr.strip()[:1000] if completed.returncode else None,
    }


def windows_path_to_wsl(path: str | Path) -> str | None:
    wsl = wsl_detection()
    if not wsl.get("available"):
        return None
    try:
        completed = subprocess.run(
            [str(wsl["executable"]), "--", "wslpath", "-a", str(Path(path).resolve())],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and value else None


def _shell_quote(value: str) -> str:
    return "'" + str(value).replace("'", "'\"'\"'") + "'"


def openai_health(backend: str, *, base_url: str, timeout_seconds: float = 2.0) -> JsonDict:
    urls = [f"{base_url.rstrip('/')}/health", f"{base_url.rstrip('/')}/v1/models"]
    errors = []
    for url in urls:
        try:
            request = Request(url, headers={"User-Agent": "RIFT/1.0"})
            with urlopen(request, timeout=timeout_seconds) as response:
                body = response.read(4096).decode("utf-8", errors="replace")
            return {
                "backend": backend,
                "healthy": 200 <= int(response.status) < 500,
                "status_code": int(response.status),
                "url": url,
                "body_preview": body[:500],
            }
        except URLError as exc:
            errors.append(str(exc))
        except Exception as exc:
            errors.append(str(exc))
    return {"backend": backend, "healthy": False, "errors": errors}


def openai_benchmark(
    backend: str,
    *,
    base_url: str,
    prompt: str,
    max_tokens: int,
    timeout_seconds: float = 60.0,
) -> JsonDict:
    model_id = resolve_openai_model_id(
        base_url=base_url,
        timeout_seconds=min(timeout_seconds, 5.0),
    )
    payload = {
        "model": model_id or "rift-managed",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        _openai_route(base_url, "/v1/chat/completions"),
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "RIFT/1.0"},
    )
    started = time.perf_counter()
    with urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read().decode("utf-8", errors="replace")
    elapsed = max(time.perf_counter() - started, 1.0e-9)
    generated = count_generated_tokens(raw)
    return {
        "backend": backend,
        "status_code": int(response.status),
        "elapsed_seconds": elapsed,
        "generated_tokens_estimate": generated,
        "tokens_per_second_estimate": generated / elapsed if generated else None,
        "model_id": model_id or "rift-managed",
        "model_id_source": "server_catalog" if model_id else "fallback",
        "response_preview": raw[:1000],
    }


def resolve_openai_model_id(*, base_url: str, timeout_seconds: float = 5.0) -> str | None:
    """Read the live model identifier required by an OpenAI-compatible server.

    Backends commonly advertise a filesystem path (for example ``/models``) when
    launched from a mounted directory. Sending RIFT's internal placeholder or the
    original Hub repository ID then produces a misleading 404 even though the
    server is healthy. The catalog endpoint is the portable source of truth.
    """

    try:
        request = Request(
            _openai_route(base_url, "/v1/models"),
            headers={"Accept": "application/json", "User-Agent": "RIFT/1.0"},
        )
        with urlopen(request, timeout=max(float(timeout_seconds), 0.1)) as response:
            payload = json.loads(response.read(128 * 1024).decode("utf-8", errors="replace"))
    except Exception:
        return None

    models = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        return None
    for item in models:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "").strip()
        if model_id:
            return model_id
    return None


def _openai_route(base_url: str, route: str) -> str:
    root = str(base_url).rstrip("/")
    if root.endswith("/v1") and route.startswith("/v1"):
        return root + route[3:]
    return root + route


def count_generated_tokens(raw: str) -> int:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return max(1, len(re.findall(r"\S+", raw)))
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if isinstance(usage, dict) and isinstance(usage.get("completion_tokens"), int):
        return int(usage["completion_tokens"])
    text = ""
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else {}
        if isinstance(message, dict):
            text = str(message.get("content") or "")
    return max(1, len(re.findall(r"\S+", text))) if text else 0


def launch_process(backend: str, launch_plan: JsonDict, *, log_path: str | None = None) -> JsonDict:
    args = [str(arg) for arg in launch_plan.get("command") or []]
    if not args:
        raise ValueError("launch_plan.command is required")
    stdout = subprocess.DEVNULL
    stderr = subprocess.STDOUT
    handle = None
    if log_path:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        handle = Path(log_path).open("ab")
        stdout = handle
        stderr = subprocess.STDOUT
    env = os.environ.copy()
    env.update({str(k): str(v) for k, v in (launch_plan.get("env") or {}).items()})
    creationflags = 0
    if os.name == "nt":
        creationflags = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
        )
    try:
        try:
            process = subprocess.Popen(args, stdout=stdout, stderr=stderr, env=env, creationflags=creationflags)
        except OSError:
            process = subprocess.Popen(args, stdout=stdout, stderr=stderr, env=env)
    finally:
        if handle:
            handle.close()
    return {
        "backend": backend,
        "pid": process.pid,
        "started_unix_seconds": int(time.time()),
        "api_base": launch_plan.get("api_base"),
        "openai_base": launch_plan.get("openai_base"),
    }


def python_unsupported_on_windows(backend: str) -> JsonDict | None:
    if os.name != "nt":
        return None
    return {
        "backend": backend,
        "installed": False,
        "changed": False,
        "reason": (
            f"automatic {backend} install is not enabled on native Windows. "
            "Use WSL2/Linux, Docker, or an official backend-specific install, then rerun detection."
        ),
    }
