"""Platform-aware operator storage paths for RIFT."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import platform


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
            return cls(Path(explicit).expanduser().resolve())

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


__all__ = ["RiftPaths"]
