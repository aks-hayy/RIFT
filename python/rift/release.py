"""Schema migration and redacted diagnostic bundles for RIFT releases."""

from __future__ import annotations

import json
from pathlib import Path
import platform
import time
import zipfile
from typing import Any

from .observability import ObservabilityStore
from .state_store import StateStore


JsonDict = dict[str, Any]
CURRENT_STATE_SCHEMA = 2
CURRENT_CONFIG_SCHEMA = 2


def migrate_state(state: JsonDict) -> tuple[JsonDict, list[str]]:
    result = json.loads(json.dumps(state or {}))
    version = int(result.get("schema_version") or 1)
    changes = []
    if version < 2:
        result.setdefault("controller", {})
        result["controller"].setdefault("desired_generation", 1)
        result["controller"].setdefault("observed_generation", 1)
        for service in (result.get("services") or {}).values():
            service.setdefault("desired_state", "running" if service.get("runtime") else "stopped")
            service.setdefault("status", "unknown")
        result["schema_version"] = 2
        changes.append("migrated state schema 1 to 2 with controller generations")
        version = 2
    if version > CURRENT_STATE_SCHEMA:
        raise ValueError(f"state schema {version} is newer than supported {CURRENT_STATE_SCHEMA}")
    return result, changes


def migrate_config(config: JsonDict) -> tuple[JsonDict, list[str]]:
    result = json.loads(json.dumps(config or {}))
    version = int(result.get("schema_version") or result.get("version") or 1)
    changes = []
    if "schema_version" not in result:
        result["schema_version"] = version
        changes.append("added schema_version to legacy configuration")
    if version < 2:
        result.setdefault("governance", {"allow_gated": False, "require_hashes": False})
        result.setdefault("observability", {"retention_days": 30, "max_events": 10000})
        result["schema_version"] = 2
        result["version"] = 2
        changes.append("migrated config schema 1 to 2 with governance and observability policies")
        version = 2
    if version > CURRENT_CONFIG_SCHEMA:
        raise ValueError(f"config schema {version} is newer than supported {CURRENT_CONFIG_SCHEMA}")
    return result, changes


class DiagnosticBundle:
    def __init__(self, root: str | Path | None = None, *, data_root: str | Path | None = None) -> None:
        self.root = Path(root) if root else Path.cwd()
        self.rift_dir = Path(data_root) if data_root is not None else self.root / ".rift"
        self.redactor = ObservabilityStore(root=self.root, data_root=self.rift_dir)

    def create(self, output: str | Path | None = None) -> JsonDict:
        stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        target = Path(output) if output else self.rift_dir / "diagnostics" / f"rift-diagnostics-{stamp}.zip"
        target.parent.mkdir(parents=True, exist_ok=True)
        included = []
        summary = {
            "schema_version": 1,
            "created_unix_seconds": time.time(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "root": str(self.root.resolve()),
            "privacy": "Known secret-like fields and bearer tokens are redacted; inspect before sharing.",
        }
        state_db = self.rift_dir / "state.db"
        if state_db.is_file():
            try:
                summary["state_store"] = {
                    "authoritative": str(state_db),
                    "compatibility_mirror": str(self.rift_dir / "state.json"),
                    "revision": StateStore(state_db, legacy_path=self.rift_dir / "state.json").revision,
                    "backup_policy": "Use the controller backup API before moving or restoring state.",
                }
            except (OSError, ValueError):
                summary["state_store"] = {
                    "authoritative": ".rift/state.db",
                    "status": "unreadable",
                }
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("diagnostic-summary.json", json.dumps(summary, indent=2, sort_keys=True))
            for path in self._candidate_files():
                try:
                    raw = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                try:
                    relative = path.relative_to(self.root).as_posix()
                except ValueError:
                    relative = f"runtime/{path.relative_to(self.rift_dir).as_posix()}"
                if path.suffix.lower() == ".json":
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        content = str(self.redactor.redact(raw))
                    else:
                        content = json.dumps(self.redactor.redact(payload), indent=2, sort_keys=True)
                else:
                    content = str(self.redactor.redact(raw))
                archive.writestr(relative, content)
                included.append(relative)
        return {"created": True, "path": str(target), "included_files": included, "summary": summary}

    def _candidate_files(self) -> list[Path]:
        data_files = (
            self.rift_dir / "state.json",
            self.rift_dir / "discovery" / "latest.json",
            self.rift_dir / "plans" / "latest.json",
            self.rift_dir / "generated" / "latest.json",
            self.rift_dir / "gateway" / "metrics.json",
            self.rift_dir / "observability" / "timeline.jsonl",
        )
        files = [path for path in data_files if path.is_file()]
        files.extend(path for path in (self.root / "rift.yaml", self.root / "cluster.yaml") if path.is_file())
        for folder in ("incidents", "reports", "logs"):
            root = self.rift_dir / folder
            if root.is_dir():
                files.extend(sorted(path for path in root.glob("*") if path.is_file())[-20:])
        return list(dict.fromkeys(files))


__all__ = [
    "CURRENT_CONFIG_SCHEMA",
    "CURRENT_STATE_SCHEMA",
    "DiagnosticBundle",
    "migrate_config",
    "migrate_state",
]
