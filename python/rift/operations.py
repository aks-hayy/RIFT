"""Durable idempotency records for controller API operations."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from typing import Any
import uuid


JsonDict = dict[str, Any]


class OperationStore:
    """Persist request results so client retries cannot duplicate mutations."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def operation_id(self, request_id: str) -> str:
        return "op-" + hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:24]

    def load(self, request_id: str) -> JsonDict | None:
        path = self._path(request_id)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def begin(self, request_id: str, *, action: str, actor: str | None = None) -> JsonDict:
        request_id = self._validate_request_id(request_id)
        existing = self.load(request_id)
        if existing is not None:
            return existing
        record = {
            "schema_version": 1,
            "request_id": request_id,
            "operation_id": self.operation_id(request_id),
            "action": action,
            "actor": actor or "anonymous",
            "status": "RUNNING",
            "created_unix_seconds": time.time(),
        }
        self._write(request_id, record)
        return record

    def complete(self, request_id: str, *, result: JsonDict, status: str = "SUCCEEDED") -> JsonDict:
        record = self.load(request_id) or self.begin(request_id, action="unknown")
        record.update(
            {
                "status": status,
                "completed_unix_seconds": time.time(),
                "result": result,
            }
        )
        self._write(request_id, record)
        return record

    def fail(self, request_id: str, *, error: str) -> JsonDict:
        record = self.load(request_id) or self.begin(request_id, action="unknown")
        record.update(
            {
                "status": "FAILED",
                "completed_unix_seconds": time.time(),
                "error": error,
            }
        )
        self._write(request_id, record)
        return record

    def _path(self, request_id: str) -> Path:
        digest = hashlib.sha256(str(request_id).encode("utf-8")).hexdigest()
        return self.root / f"{digest}.json"

    @staticmethod
    def _validate_request_id(request_id: str) -> str:
        value = str(request_id or "").strip()
        if not value or len(value) > 200:
            raise ValueError("request_id must be between 1 and 200 characters")
        return value

    def _write(self, request_id: str, payload: JsonDict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        target = self._path(request_id)
        temporary = target.with_suffix(f".{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        temporary.replace(target)


__all__ = ["OperationStore"]
