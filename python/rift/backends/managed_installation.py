"""Ownership registry and safety checks for RIFT-installed backend runtimes."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import shutil
import subprocess
import tempfile
from typing import Any

from ..providers.openai_backend import wsl_detection
from ..runtime_paths import RiftPaths


JsonDict = dict[str, Any]
_SCHEMA_VERSION = 1
_INSTALL_TYPES = {"archive", "native-venv", "wsl-venv"}
_NATIVE_MARKER = "rift-managed-install.json"


def _validate_backend_id(backend_id: str) -> str:
    value = str(backend_id or "").strip()
    if (
        not value
        or value in {".", ".."}
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", value)
    ):
        raise ValueError("backend id is invalid")
    return value


def _absolute(path: str | Path) -> Path:
    return Path(os.path.abspath(os.fspath(Path(path).expanduser())))


def _path_redirection_reason(path: Path) -> str | None:
    """Reject symlink/junction path traversal before touching managed data."""
    absolute = _absolute(path)
    try:
        resolved = absolute.resolve(strict=False)
    except OSError as exc:
        return f"path could not be canonicalized: {exc}"
    if os.path.normcase(str(absolute)) != os.path.normcase(str(resolved)):
        return "path resolves through a symlink or reparse point"

    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            return f"path component could not be inspected: {exc}"
        attributes = int(getattr(info, "st_file_attributes", 0))
        reparse_point = bool(attributes & 0x400)
        is_junction = getattr(current, "is_junction", lambda: False)()
        if stat.S_ISLNK(info.st_mode) or reparse_point or is_junction:
            return f"path traverses a symlink or reparse point: {current}"
    return None


def _registry_path(runtime_home: str | Path) -> tuple[Path, Path]:
    home = _absolute(runtime_home)
    paths = RiftPaths(home)
    return paths.backends, paths.backend_registry


def _read_json(path: Path) -> JsonDict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"ownership marker could not be read: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("ownership marker must contain a JSON object")
    return payload


def _write_json_atomic(path: Path, payload: JsonDict) -> None:
    reason = _path_redirection_reason(path.parent)
    if reason:
        raise ValueError(reason)
    path.parent.mkdir(parents=True, exist_ok=True)
    reason = _path_redirection_reason(path.parent)
    if reason:
        raise ValueError(reason)
    if path.exists() and (reason := _path_redirection_reason(path)):
        raise ValueError(reason)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            json.dump(payload, temporary, indent=2, sort_keys=True)
            temporary.write("\n")
        os.replace(temporary_name, path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _marker_name(install_type: str) -> str:
    return "rift-install.json" if install_type == "archive" else _NATIVE_MARKER


def _validate_target_scope(runtime_home: Path, backend_id: str, target: Path) -> None:
    backends_root = runtime_home / "backends"
    if target == runtime_home or target == backends_root:
        raise ValueError("backend target must be a dedicated runtime directory")
    try:
        target.relative_to(runtime_home)
    except ValueError:
        return
    try:
        relative_to_backends = target.relative_to(backends_root)
    except ValueError as exc:
        raise ValueError("managed backend target cannot be inside RIFT_HOME outside its backends directory") from exc
    if not relative_to_backends.parts:
        raise ValueError("backend target must be a dedicated runtime directory")
    if target.parent == backends_root and target.name != backend_id:
        raise ValueError("default backend target directory must match the backend id")


def _managed_relative_paths(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("ownership marker does not list managed runtime paths")
    paths: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("managed runtime path is invalid")
        relative = Path(item)
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError("managed runtime path must remain inside the backend target")
        normalized = relative.as_posix()
        if normalized not in paths:
            paths.append(normalized)
    return paths


def _canonical_recorded_path(value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("ownership record has no canonical target path")
    return _absolute(value)


def _validate_archive_marker(backend_id: str, target: Path, marker_path: Path) -> JsonDict:
    marker = _read_json(marker_path)
    marker_backend = str(marker.get("backend") or "").strip()
    if marker_backend != backend_id:
        raise ValueError("archive ownership marker backend does not match the registry")
    if marker.get("installed") is not True:
        raise ValueError("archive ownership marker does not report a successful installation")
    marker_target = marker.get("target_dir")
    if not isinstance(marker_target, str) or _absolute(marker_target) != target:
        raise ValueError("archive ownership marker target does not match the registry")
    ownership = marker.get("managed_installation")
    if ownership is not None:
        if not isinstance(ownership, dict):
            raise ValueError("archive ownership marker has invalid RIFT ownership metadata")
        if ownership.get("managed_by") != "RIFT" or ownership.get("backend_id") != backend_id:
            raise ValueError("archive ownership marker does not identify a RIFT installation")
        if _canonical_recorded_path(ownership.get("target")) != target:
            raise ValueError("archive ownership marker target does not match the registry")
    return marker


def _validate_native_marker(
    backend_id: str,
    target: Path,
    install_type: str,
    marker_path: Path,
) -> JsonDict:
    marker = _read_json(marker_path)
    if marker.get("managed_by") != "RIFT":
        raise ValueError("RIFT ownership marker is missing or invalid")
    if marker.get("backend_id") != backend_id:
        raise ValueError("RIFT ownership marker backend does not match the registry")
    if marker.get("install_type") != install_type:
        raise ValueError("RIFT ownership marker installation type does not match the registry")
    if _canonical_recorded_path(marker.get("target")) != target:
        raise ValueError("RIFT ownership marker target does not match the registry")
    return marker


def record_managed_installation(
    runtime_home: str | Path,
    backend_id: str,
    target: str | Path,
    install_type: str,
    metadata: dict[str, Any],
) -> JsonDict:
    """Record a successfully installed, dedicated RIFT runtime directory."""
    backend = _validate_backend_id(backend_id)
    kind = str(install_type or "").strip().lower()
    if kind not in _INSTALL_TYPES:
        raise ValueError(f"unsupported RIFT installation type: {kind or '(empty)'}")
    runtime_home = _absolute(runtime_home)
    backends_root, registry_path = _registry_path(runtime_home)
    target_path = _absolute(target)
    _validate_target_scope(runtime_home, backend, target_path)
    for path, label in ((backends_root, "backend registry directory"), (target_path, "backend target")):
        reason = _path_redirection_reason(path)
        if reason:
            raise ValueError(f"{label} is unsafe: {reason}")
    if not target_path.is_dir():
        raise ValueError("backend target directory does not exist")

    marker_path = target_path / _marker_name(kind)
    if _path_redirection_reason(marker_path):
        raise ValueError("backend ownership marker path is unsafe")
    marker_path.resolve(strict=False)
    safe_metadata = dict(metadata) if isinstance(metadata, dict) else {}
    if kind == "archive":
        archive_marker = _validate_archive_marker(backend, target_path, marker_path)
        ownership = archive_marker.get("managed_installation")
        if isinstance(ownership, dict):
            safe_metadata.setdefault("managed_paths", ownership.get("managed_paths"))
        if "managed_paths" in safe_metadata:
            safe_metadata["managed_paths"] = _managed_relative_paths(safe_metadata["managed_paths"])
    else:
        if kind == "wsl-venv":
            wsl_marker = target_path / "wsl-install.json"
            if _path_redirection_reason(wsl_marker):
                raise ValueError("WSL runtime metadata path is unsafe")
            wsl_metadata = _read_json(wsl_marker)
            python_path = str(wsl_metadata.get("python") or "")
            managed_marker = str(wsl_metadata.get("managed_marker") or "")
            safe_id = re.sub(r"[^a-zA-Z0-9._-]+", "-", backend).strip("-") or "adapter"
            expected_suffix = f"/.local/share/rift/backends/{safe_id}/venv/bin/python"
            if (
                wsl_metadata.get("adapter_id") != backend
                or not python_path.endswith(expected_suffix)
                or not managed_marker.startswith("RIFT_MANAGED_VENV=")
                or not managed_marker.endswith(f"/.local/share/rift/backends/{safe_id}/venv")
            ):
                raise ValueError("WSL runtime metadata does not identify the dedicated RIFT venv")
            safe_metadata.setdefault("wsl_python", python_path)
            safe_metadata.setdefault("managed_marker", managed_marker)
            safe_metadata.setdefault("managed_paths", [])
        else:
            safe_metadata.setdefault("managed_paths", ["venv"])
            safe_metadata["managed_paths"] = _managed_relative_paths(safe_metadata["managed_paths"])
        marker = {
            "managed_by": "RIFT",
            "backend_id": backend,
            "target": str(target_path),
            "install_type": kind,
            "metadata": safe_metadata,
        }
        if marker_path.exists():
            _validate_native_marker(backend, target_path, kind, marker_path)
        else:
            _write_json_atomic(marker_path, marker)

    registry_reason = _path_redirection_reason(backends_root)
    if registry_reason:
        raise ValueError(f"backend registry directory is unsafe: {registry_reason}")
    if registry_path.exists() and (reason := _path_redirection_reason(registry_path)):
        raise ValueError(f"backend registry file is unsafe: {reason}")
    if registry_path.is_file():
        registry = _read_json(registry_path)
        if registry.get("schema_version") != _SCHEMA_VERSION:
            raise ValueError("backend ownership registry schema version is unsupported")
    else:
        registry = {"schema_version": _SCHEMA_VERSION, "installations": {}}
    installations = registry.get("installations")
    if not isinstance(installations, dict):
        raise ValueError("backend ownership registry is invalid")
    previous = installations.get(backend)
    entry = {
        "backend_id": backend,
        "target": str(target_path),
        "install_type": kind,
        "marker_path": str(marker_path),
        "metadata": safe_metadata,
    }
    if isinstance(previous, dict) and previous.get("target") != entry["target"]:
        raise ValueError("backend already has an ownership record for a different target")
    installations[backend] = entry
    registry = {"schema_version": _SCHEMA_VERSION, "installations": installations}
    _write_json_atomic(registry_path, registry)
    return inspect_managed_installation(runtime_home, backend)


def record_install_result(
    runtime_home: str | Path,
    backend_id: str,
    target: str | Path,
    install_result: dict[str, Any],
) -> JsonDict:
    """Register a successful provider install when it owns a dedicated target."""
    backend = _validate_backend_id(backend_id)
    target_path = _absolute(target)
    result = install_result if isinstance(install_result, dict) else {}
    archive_marker_exists = (target_path / "rift-install.json").is_file()
    if not result.get("installed") or (not result.get("changed") and not archive_marker_exists):
        return inspect_managed_installation(runtime_home, backend)

    installer = result.get("installer") if isinstance(result.get("installer"), dict) else {}
    if not installer and isinstance(result.get("pip"), dict):
        installer = result["pip"]
    install_type = str(installer.get("install_type") or "")
    if (target_path / "rift-install.json").is_file():
        install_type = "archive"
    elif (target_path / "wsl-install.json").is_file() or installer.get("wsl_python"):
        install_type = "wsl-venv"
    elif (target_path / "venv").is_dir() or installer.get("isolated"):
        install_type = "native-venv"
    elif install_type not in _INSTALL_TYPES:
        # Container images and external/global installs are not exclusive
        # filesystem targets and must not be claimed by this registry.
        return {
            **inspect_managed_installation(runtime_home, backend),
            "reason": "installation has no dedicated RIFT-owned runtime directory",
        }

    metadata: JsonDict = {}
    if result.get("variant"):
        metadata["variant"] = str(result["variant"])
    if install_type == "archive":
        metadata["assets"] = [
            str(item.get("name"))
            for item in result.get("assets", [])
            if isinstance(item, dict) and item.get("name")
        ]
        archive_marker = _read_json(target_path / "rift-install.json")
        ownership = archive_marker.get("managed_installation")
        metadata["managed_paths"] = (
            _managed_relative_paths(ownership.get("managed_paths"))
            if isinstance(ownership, dict)
            else []
        )
    elif install_type == "wsl-venv":
        wsl_path = target_path / "wsl-install.json"
        wsl_metadata = _read_json(wsl_path)
        metadata["wsl_python"] = str(wsl_metadata.get("python") or installer.get("wsl_python") or "")
        metadata["managed_marker"] = str(wsl_metadata.get("managed_marker") or installer.get("managed_marker") or "")
        metadata["packages"] = list(wsl_metadata.get("packages") or [])
    else:
        environment = installer.get("environment")
        metadata["environment"] = str(environment.get("environment")) if isinstance(environment, dict) else str(target_path / "venv")
        if isinstance(environment, dict):
            metadata["python"] = str(environment.get("python") or "")
    return record_managed_installation(runtime_home, backend, target_path, install_type, metadata)


def inspect_managed_installation(runtime_home: str | Path, backend_id: str) -> JsonDict:
    """Return ownership/removal readiness without modifying the filesystem."""
    try:
        backend = _validate_backend_id(backend_id)
    except ValueError as exc:
        return {
            "backend_id": str(backend_id or ""),
            "managed": False,
            "removable": False,
            "install_type": None,
            "target": None,
            "marker_path": None,
            "reason": str(exc),
        }

    _backends_root, registry_path = _registry_path(runtime_home)
    base: JsonDict = {
        "backend_id": backend,
        "managed": False,
        "removable": False,
        "install_type": None,
        "target": None,
        "marker_path": None,
    }
    if not registry_path.exists():
        default_target = _backends_root / backend
        default_marker = default_target / "rift-install.json"
        if default_marker.is_file() and not _path_redirection_reason(default_target):
            try:
                if _path_redirection_reason(default_marker):
                    raise ValueError("archive ownership marker path is unsafe")
                archive_marker = _validate_archive_marker(backend, default_target.resolve(strict=False), default_marker)
                ownership = archive_marker.get("managed_installation")
                managed_paths = (
                    _managed_relative_paths(ownership.get("managed_paths"))
                    if isinstance(ownership, dict)
                    else []
                )
                if not managed_paths:
                    return {
                        **base,
                        "managed": True,
                        "install_type": "archive",
                        "target": str(default_target.resolve(strict=False)),
                        "marker_path": str(default_marker.resolve(strict=False)),
                        "removable": False,
                        "reason": "legacy archive marker does not list managed runtime files",
                    }
                return {
                    **base,
                    "managed": True,
                    "removable": True,
                    "install_type": "archive",
                    "target": str(default_target.resolve(strict=False)),
                    "marker_path": str(default_marker.resolve(strict=False)),
                    "managed_paths": managed_paths,
                    "metadata": {},
                    "reason": None,
                    "registry_recorded": False,
                }
            except (OSError, ValueError):
                pass
        return {**base, "reason": "no RIFT ownership record exists; external or unmarked runtimes are not removable"}
    if reason := _path_redirection_reason(registry_path.parent):
        return {**base, "reason": f"backend registry path is unsafe: {reason}"}
    if reason := _path_redirection_reason(registry_path):
        return {**base, "reason": f"backend registry file is unsafe: {reason}"}
    try:
        registry = _read_json(registry_path)
    except ValueError as exc:
        return {**base, "reason": str(exc)}
    if registry.get("schema_version") != _SCHEMA_VERSION:
        return {**base, "reason": "backend ownership registry schema version is unsupported"}
    installations = registry.get("installations")
    entry = installations.get(backend) if isinstance(installations, dict) else None
    if not isinstance(entry, dict):
        return {**base, "reason": "no RIFT ownership record exists; external or unmarked runtimes are not removable"}

    base.update(
        {
            "managed": True,
            "install_type": entry.get("install_type"),
            "target": entry.get("target"),
            "marker_path": entry.get("marker_path"),
            "metadata": entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {},
        }
    )
    try:
        if entry.get("backend_id") != backend:
            raise ValueError("registry backend identity does not match the requested backend")
        kind = str(entry.get("install_type") or "")
        if kind not in _INSTALL_TYPES:
            raise ValueError("registry installation type is unsupported")
        target_path = _canonical_recorded_path(entry.get("target"))
        _validate_target_scope(_absolute(runtime_home), backend, target_path)
        if reason := _path_redirection_reason(target_path):
            raise ValueError(f"backend target path is unsafe: {reason}")
        if not target_path.is_dir():
            raise ValueError("recorded backend target directory no longer exists")
        expected_marker = target_path / _marker_name(kind)
        recorded_marker = _canonical_recorded_path(entry.get("marker_path"))
        if recorded_marker != expected_marker:
            raise ValueError("registry marker path is outside the recorded backend target")
        if reason := _path_redirection_reason(recorded_marker):
            raise ValueError(f"backend marker path is unsafe: {reason}")
        if not recorded_marker.is_file():
            raise ValueError("backend ownership marker is missing")
        if kind == "archive":
            archive_marker = _validate_archive_marker(backend, target_path, recorded_marker)
            ownership = archive_marker.get("managed_installation")
            paths = (
                _managed_relative_paths(ownership.get("managed_paths"))
                if isinstance(ownership, dict)
                else []
            )
            entry_metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
            registry_paths = _managed_relative_paths(entry_metadata.get("managed_paths"))
            if not paths or paths != registry_paths:
                raise ValueError("archive managed-file list does not match the RIFT ownership registry")
        else:
            marker = _validate_native_marker(backend, target_path, kind, recorded_marker)
            marker_metadata = marker.get("metadata") if isinstance(marker.get("metadata"), dict) else {}
            paths = _managed_relative_paths(marker_metadata.get("managed_paths"))
            entry_metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
            registry_paths = _managed_relative_paths(entry_metadata.get("managed_paths"))
            if paths != registry_paths:
                raise ValueError("managed runtime paths do not match the RIFT ownership registry")
            if kind == "native-venv" and paths != ["venv"]:
                raise ValueError("native backend ownership marker must target only its dedicated venv")
            if kind == "wsl-venv":
                wsl_path = target_path / "wsl-install.json"
                if reason := _path_redirection_reason(wsl_path):
                    raise ValueError(f"WSL runtime metadata path is unsafe: {reason}")
                wsl_metadata = _read_json(wsl_path)
                if (
                    wsl_metadata.get("adapter_id") != backend
                    or wsl_metadata.get("python") != (marker.get("metadata") or {}).get("wsl_python")
                    or wsl_metadata.get("managed_marker") != (marker.get("metadata") or {}).get("managed_marker")
                ):
                    raise ValueError("WSL runtime metadata does not match the RIFT ownership marker")
        base["managed_paths"] = paths
        return {**base, "removable": True, "reason": None}
    except (OSError, ValueError) as exc:
        return {**base, "removable": False, "reason": str(exc)}


def _remove_wsl_environment(backend_id: str) -> None:
    wsl = wsl_detection()
    if not wsl.get("available") or not wsl.get("executable"):
        raise OSError("WSL is unavailable; the managed WSL runtime was not removed")
    safe_id = _validate_backend_id(backend_id)
    environment = f"$HOME/.local/share/rift/backends/{safe_id}/venv"
    script = (
        "set -eu; "
        f"environment=\"{environment}\"; marker=\"$environment/.rift-managed-install\"; "
        f"expected=\"RIFT_MANAGED_VENV=$HOME/.local/share/rift/backends/{safe_id}/venv\"; "
        "[ -f \"$marker\" ] && [ \"$(cat \"$marker\")\" = \"$expected\" ] "
        "|| { echo 'RIFT WSL ownership marker mismatch; runtime left untouched' >&2; exit 73; }; "
        "rm -rf -- \"$environment\""
    )
    args = [str(wsl["executable"]), "--", "bash", "-lc", script]
    try:
        completed = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OSError(f"WSL backend removal failed: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "WSL cleanup command failed").strip()
        raise OSError(f"WSL backend removal failed: {detail[:500]}")


def _prune_empty_directories(path: Path, target: Path) -> None:
    parent = path.parent
    while parent != target:
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def _remove_archive_files(target: Path, managed_paths: list[str]) -> None:
    for relative in managed_paths:
        if relative == "rift-install.json":
            continue
        path = target / Path(relative)
        try:
            path.relative_to(target)
        except ValueError as exc:
            raise ValueError("managed archive file escapes its backend target") from exc
        if reason := _path_redirection_reason(path):
            raise ValueError(f"managed archive path is unsafe: {reason}")
        if not path.exists():
            continue
        if not path.is_file():
            raise ValueError(f"managed archive path is not a file: {relative}")
        path.unlink()
        _prune_empty_directories(path, target)


def remove_managed_installation(runtime_home: str | Path, backend_id: str) -> JsonDict:
    """Remove only registered runtime paths after revalidating every boundary."""
    backend = _validate_backend_id(backend_id)
    installation = inspect_managed_installation(runtime_home, backend)
    if not installation.get("removable"):
        raise ValueError(str(installation.get("reason") or "backend installation is not removable"))
    target = _canonical_recorded_path(installation.get("target"))
    _validate_target_scope(_absolute(runtime_home), backend, target)
    marker_path = _canonical_recorded_path(installation.get("marker_path"))
    kind = str(installation.get("install_type") or "")
    managed_paths = _managed_relative_paths(installation.get("managed_paths"))
    if reason := _path_redirection_reason(target):
        raise ValueError(f"backend target path is unsafe: {reason}")
    if marker_path.parent != target or _path_redirection_reason(marker_path):
        raise ValueError("backend ownership marker path is unsafe")

    registry_backends, registry_path = _registry_path(runtime_home)
    registry_recorded = bool(installation.get("registry_recorded", True))
    registry: JsonDict | None = None
    if registry_recorded:
        if reason := _path_redirection_reason(registry_backends):
            raise ValueError(f"backend registry path is unsafe: {reason}")
        if reason := _path_redirection_reason(registry_path):
            raise ValueError(f"backend registry file is unsafe: {reason}")
        registry = _read_json(registry_path)
        if registry.get("schema_version") != _SCHEMA_VERSION:
            raise ValueError("backend ownership registry schema version is unsupported")

    marker_bytes = marker_path.read_bytes()
    wsl_marker = target / "wsl-install.json"
    wsl_marker_bytes = wsl_marker.read_bytes() if kind == "wsl-venv" else None
    try:
        if kind == "wsl-venv":
            # inspect_managed_installation already validated the exact adapter
            # id and dedicated WSL venv path before this remote deletion.
            _remove_wsl_environment(backend)
        elif kind == "native-venv":
            venv_path = target / "venv"
            if reason := _path_redirection_reason(venv_path):
                raise ValueError(f"native backend venv path is unsafe: {reason}")
            if venv_path.exists():
                if not venv_path.is_dir():
                    raise ValueError("native backend venv is not a directory")
                shutil.rmtree(venv_path)
        elif kind == "archive":
            _remove_archive_files(target, managed_paths)
        else:
            raise ValueError("registry installation type is unsupported")

        if marker_path.exists():
            marker_path.unlink()
        if kind == "wsl-venv" and wsl_marker.exists():
            wsl_marker.unlink()
        if registry is not None:
            installations = registry.get("installations")
            if not isinstance(installations, dict) or backend not in installations:
                raise ValueError("backend ownership registry entry disappeared during removal")
            del installations[backend]
            _write_json_atomic(registry_path, {"schema_version": _SCHEMA_VERSION, "installations": installations})
    except Exception:
        # Keep the registry useful for a retry if metadata removal succeeded
        # but the final registry update failed.
        if registry is not None and not marker_path.exists():
            marker_path.write_bytes(marker_bytes)
        if kind == "wsl-venv" and wsl_marker_bytes is not None and not wsl_marker.exists():
            wsl_marker.write_bytes(wsl_marker_bytes)
        raise

    try:
        target.rmdir()
        target_removed = True
    except OSError:
        target_removed = False
    return {
        "uninstalled": True,
        "backend_id": backend,
        "target": str(target),
        "target_removed": target_removed,
    }
