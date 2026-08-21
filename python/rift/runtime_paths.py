"""Platform-aware operator storage paths for RIFT."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import platform
import shutil
import time
import zipfile
from typing import Any


@dataclass(frozen=True)
class RiftPaths:
    """All mutable RIFT data lives outside the source checkout by default."""

    home: Path

    @property
    def state(self) -> Path:
        return self.home / "state.db"

    @property
    def state_mirror(self) -> Path:
        return self.home / "state.json"

    @property
    def models(self) -> Path:
        return self.home / "models"

    @property
    def cache(self) -> Path:
        return self.home / "cache"

    @property
    def logs(self) -> Path:
        return self.home / "logs"

    @property
    def reports(self) -> Path:
        return self.home / "reports"

    @property
    def certificates(self) -> Path:
        return self.home / "certificates"

    @property
    def backends(self) -> Path:
        return self.home / "backends"

    @property
    def operations(self) -> Path:
        return self.home / "operations"

    @classmethod
    def from_environment(cls, *, cwd: str | Path | None = None) -> "RiftPaths":
        explicit = os.environ.get("RIFT_HOME")
        if explicit and explicit.strip():
            resolved = Path(explicit).expanduser().resolve()
            if cwd is not None and resolved == Path(cwd).expanduser().resolve() / ".rift":
                raise ValueError("RIFT_HOME must not resolve to the source checkout .rift directory")
            return cls(resolved)

        system = platform.system().lower()
        if system == "windows":
            base = os.environ.get("LOCALAPPDATA")
            home = Path(base) / "RIFT" if base else Path.home() / "AppData" / "Local" / "RIFT"
        elif system == "darwin":
            home = Path.home() / "Library" / "Application Support" / "RIFT"
        else:
            base = os.environ.get("XDG_STATE_HOME")
            home = Path(base) / "rift" if base else Path.home() / ".local" / "state" / "rift"

        resolved = home.expanduser().resolve()
        if cwd is not None and resolved == Path(cwd).expanduser().resolve() / ".rift":
            raise ValueError("RIFT_HOME must not resolve to the source checkout .rift directory")
        return cls(resolved)

    def create(self) -> "RiftPaths":
        for path in (
            self.home,
            self.models,
            self.cache,
            self.logs,
            self.reports,
            self.certificates,
            self.backends,
            self.operations,
        ):
            path.mkdir(parents=True, exist_ok=True)
        return self

    @staticmethod
    def legacy_checkout_root(cwd: str | Path | None = None) -> Path:
        return (Path(cwd) if cwd is not None else Path.cwd()).expanduser().resolve()

    def migration_preview(self, *, source_root: str | Path | None = None) -> dict[str, Any]:
        """Describe checkout-local state without reading model contents into memory."""

        source = self.legacy_checkout_root(source_root)
        candidates = {
            "state": source / ".rift",
            "models": source / "models" / "local",
            "selected_models": source / "models" / "rift-selected",
        }
        entries = []
        for name, path in candidates.items():
            if not path.exists():
                continue
            files = [item for item in path.rglob("*") if item.is_file()]
            entries.append(
                {
                    "name": name,
                    "source": str(path),
                    "target": str(self.home / ("models" if name != "state" else "legacy-state")),
                    "file_count": len(files),
                    "bytes": sum(item.stat().st_size for item in files),
                }
            )
        return {
            "source_root": str(source),
            "target_root": str(self.home),
            "write_required": bool(entries),
            "entries": entries,
            "backup_required": bool(entries),
            "message": (
                "Preview only. No files were changed. Use --write after reviewing the backup plan."
                if entries
                else "No checkout-local RIFT state or model directory was found."
            ),
        }

    def migrate_checkout(
        self,
        *,
        source_root: str | Path | None = None,
        move: bool = False,
        write: bool = False,
    ) -> dict[str, Any]:
        """Move legacy runtime data only after a backup-first, conflict-checked plan."""

        preview = self.migration_preview(source_root=source_root)
        if not write:
            return {**preview, "applied": False}
        if not preview["entries"]:
            return {**preview, "applied": False}

        source = self.legacy_checkout_root(source_root)
        self.create()
        stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        backup_dir = self.home / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"checkout-migration-{stamp}.zip"
        with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for entry in preview["entries"]:
                path = Path(entry["source"])
                for item in ([path] if path.is_file() else path.rglob("*")):
                    if item.is_file():
                        archive.write(item, item.relative_to(source).as_posix())

        copied: list[dict[str, Any]] = []
        conflicts: list[str] = []
        for entry in preview["entries"]:
            source_path = Path(entry["source"])
            if entry["name"] == "state":
                target_path = self.home / "legacy-state"
            else:
                target_path = self.models / source_path.name
            if target_path.exists() and source_path.is_dir():
                for item in source_path.rglob("*"):
                    if not item.is_file():
                        continue
                    destination = target_path / item.relative_to(source_path)
                    if destination.exists() and _sha256(item) != _sha256(destination):
                        conflicts.append(str(destination))
            elif target_path.exists() and source_path.is_file() and _sha256(source_path) != _sha256(target_path):
                conflicts.append(str(target_path))
        if conflicts:
            raise RuntimeError(
                "legacy migration found conflicting files; review the backup and resolve: "
                + ", ".join(conflicts[:10])
            )

        for entry in preview["entries"]:
            source_path = Path(entry["source"])
            target_path = self.home / "legacy-state" if entry["name"] == "state" else self.models / source_path.name
            if source_path.is_dir():
                shutil.copytree(source_path, target_path, dirs_exist_ok=True)
            else:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, target_path)
            copied.append({"source": str(source_path), "target": str(target_path)})
            if move:
                if source_path.is_dir():
                    shutil.rmtree(source_path)
                else:
                    source_path.unlink()
        return {
            **preview,
            "applied": True,
            "moved": move,
            "backup": str(backup_path),
            "copied": copied,
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


__all__ = ["RiftPaths"]
