"""Durable recommendation and verification run storage."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time
from typing import Any

from .runtime_paths import RiftPaths


JsonDict = dict[str, Any]
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class RecommendationStore:
    """Persist immutable recommendation evidence under the RIFT runtime home."""

    def __init__(self, root: str | Path | None = None) -> None:
        base = Path(root) if root is not None else RiftPaths.from_environment().home
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

    def list_pulled_models(self, *, limit: int = 50) -> JsonDict:
        """Return recommendation winners whose downloaded artifact still exists."""

        if limit <= 0:
            raise ValueError("limit must be positive")
        entries: list[JsonDict] = []
        if not self.recommendation_dir.is_dir():
            return {"kind": "pulled_model", "count": 0, "models": entries}
        seen_paths: set[str] = set()
        paths = sorted(
            self.recommendation_dir.glob("*.json"),
            key=lambda item: item.stat().st_mtime_ns,
            reverse=True,
        )
        for path in paths:
            if len(entries) >= limit:
                break
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            pulled = payload.get("pull_best")
            if not isinstance(pulled, dict):
                continue
            local_dir = str(pulled.get("local_dir") or pulled.get("output_dir") or "").strip()
            if not local_dir:
                continue
            local_path = Path(local_dir).expanduser()
            if not local_path.is_absolute():
                local_path = Path.cwd() / local_path
            if not local_path.exists():
                continue
            normalized_path = str(local_path.resolve())
            if normalized_path in seen_paths:
                continue
            seen_paths.add(normalized_path)
            recommendations = [
                item for item in payload.get("recommendations", []) if isinstance(item, dict)
            ]
            selected = recommendations[0] if recommendations else {}
            categories = payload.get("categories") or {}
            best = categories.get("best_estimated_fit") or categories.get("best_estimated")
            if isinstance(best, dict):
                best_repo = str(best.get("repo_id") or "")
                best_artifact = str(best.get("artifact_id") or "")
                best_file = str(best.get("selected_file") or "")
                selected = next(
                    (
                        item for item in recommendations
                        if str(item.get("repo_id") or "") == best_repo
                        and (
                            not best_artifact
                            or str(
                                (item.get("selected_artifact") or item.get("artifact") or {}).get("artifact_id")
                                or ""
                            )
                            == best_artifact
                        )
                        and (not best_file or str(item.get("selected_file") or "") == best_file)
                    ),
                    selected,
                )
            artifact = selected.get("selected_artifact") or selected.get("artifact") or {}
            quality = selected.get("quality_evidence") or {}
            entries.append(
                {
                    "recommendation_run_id": payload.get("recommendation_run_id") or path.stem,
                    "task": payload.get("task") or "chat",
                    "repo_id": selected.get("repo_id"),
                    "revision": selected.get("revision") or pulled.get("revision"),
                    "selected_file": selected.get("selected_file") or pulled.get("selected_file"),
                    "format": selected.get("format") or artifact.get("format"),
                    "quantization": selected.get("quantization") or artifact.get("quantization"),
                    "backend": selected.get("backend") or selected.get("recommended_backend"),
                    "score": selected.get("final_score") or selected.get("score"),
                    "size_bytes": (
                        selected.get("selected_download_bytes")
                        or artifact.get("total_bytes")
                        or pulled.get("total_known_bytes")
                    ),
                    "evidence": (
                        "MEASURED_LOCAL" if quality.get("local_records", 0)
                        else "PUBLISHED" if quality.get("published_records", 0)
                        else "ESTIMATED"
                    ),
                    "reasons": list(selected.get("evidence") or [])[:3],
                    "local_dir": normalized_path,
                    "pulled_at": pulled.get("completed_unix_seconds") or pulled.get("downloaded_at"),
                }
            )
        return {"kind": "pulled_model", "count": len(entries), "models": entries}

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
