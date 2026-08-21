"""Durable recommendation and verification run storage."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time
from typing import Any


JsonDict = dict[str, Any]
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class RecommendationStore:
    """Persist immutable discovery evidence and verification outcomes under .rift."""

    def __init__(self, root: str | Path | None = None) -> None:
        base = Path(root) if root is not None else Path.cwd() / ".rift"
        self.root = base
        self.recommendation_dir = base / "recommendations"
        self.verification_dir = base / "verification-runs"

    def recommendation_path(self, run_id: str) -> Path:
        return self.recommendation_dir / f"{self._validate_id(run_id)}.json"

    def verification_path(self, run_id: str) -> Path:
        return self.verification_dir / f"{self._validate_id(run_id)}.json"

    def save_recommendation(self, payload: JsonDict) -> str:
        run_id = str(payload.get("recommendation_run_id") or payload.get("run_id") or "")
        if not run_id:
            raise ValueError("recommendation payload does not contain a run id")
        target = self.recommendation_path(run_id)
        self._atomic_json(target, payload)
        return str(target)

    def load_recommendation(self, run_id: str) -> JsonDict:
        return self._read_required(self.recommendation_path(run_id), "recommendation run")

    def list_recommendations(self, *, limit: int = 50) -> JsonDict:
        return self._list(self.recommendation_dir, limit=limit, kind="recommendation")

    def save_verification(self, payload: JsonDict) -> str:
        run_id = str(payload.get("verification_run_id") or payload.get("run_id") or "")
        if not run_id:
            raise ValueError("verification payload does not contain a run id")
        target = self.verification_path(run_id)
        self._atomic_json(target, payload)
        return str(target)

    def load_verification(self, run_id: str) -> JsonDict:
        return self._read_required(self.verification_path(run_id), "verification run")

    def list_verifications(self, *, limit: int = 50) -> JsonDict:
        return self._list(self.verification_dir, limit=limit, kind="verification")

    def _list(self, directory: Path, *, limit: int, kind: str) -> JsonDict:
        if limit <= 0:
            raise ValueError("limit must be positive")
        entries: list[JsonDict] = []
        if directory.is_dir():
            paths = sorted(
                directory.glob("*.json"),
                key=lambda item: item.stat().st_mtime_ns,
                reverse=True,
            )
            for path in paths[:limit]:
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                entries.append(
                    {
                        "run_id": payload.get(f"{kind}_run_id") or payload.get("run_id"),
                        "created_unix_seconds": payload.get("created_unix_seconds"),
                        "task": payload.get("task")
                        or (payload.get("workload_profile") or {}).get("task"),
                        "status": payload.get("status"),
                        "path": str(path),
                    }
                )
        return {"kind": kind, "count": len(entries), "runs": entries}

    @staticmethod
    def _validate_id(run_id: str) -> str:
        value = str(run_id).strip()
        if not _RUN_ID.fullmatch(value):
            raise ValueError("run id contains unsupported characters")
        return value

    @staticmethod
    def _read_required(path: Path, label: str) -> JsonDict:
        if not path.is_file():
            raise ValueError(f"{label} does not exist: {path.stem}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{label} is corrupt: {path}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"{label} must contain a JSON object")
        return payload

    @staticmethod
    def _atomic_json(path: Path, payload: JsonDict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
        try:
            temporary.write_text(
                json.dumps(payload, indent=2, sort_keys=True, default=str),
                encoding="utf-8",
            )
            temporary.replace(path)
        finally:
            if temporary.exists():
                temporary.unlink()


__all__ = ["RecommendationStore"]
