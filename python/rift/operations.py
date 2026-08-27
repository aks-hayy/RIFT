"""Durable idempotency records for controller API operations."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import threading
import time
from typing import Any
import uuid


JsonDict = dict[str, Any]


class OperationStore:
    """Persist request results so client retries cannot duplicate mutations."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self._lock = threading.RLock()

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

    def begin(
        self,
        request_id: str,
        *,
        action: str,
        actor: str | None = None,
        payload: Any | None = None,
    ) -> JsonDict:
        record, _ = self.begin_claim(
            request_id,
            action=action,
            actor=actor,
            payload=payload,
        )
        return record

    def begin_claim(
        self,
        request_id: str,
        *,
        action: str,
        actor: str | None = None,
        payload: Any | None = None,
    ) -> tuple[JsonDict, bool]:
        """Return an operation and whether this call created its record.

        The creation flag is important at the HTTP boundary: an existing
        record can be observed between the initial read and the atomic file
        claim, so callers must not infer ownership from a prior read alone.
        """
        request_id = self._validate_request_id(request_id)
        payload_hash = self._payload_hash(payload)
        with self._lock:
            existing = self.load(request_id)
            if existing is not None:
                if existing.get("action") != action or existing.get("payload_sha256") != payload_hash:
                    raise ValueError("request_id is already bound to a different operation payload")
                return existing, False
            now = time.time()
            record = {
                "schema_version": 2,
                "request_id": request_id,
                "operation_id": self.operation_id(request_id),
                "action": action,
                "actor": actor or "anonymous",
                "status": "RUNNING",
                "stage": "queued",
                "message": "Operation accepted",
                "percent": 0.0,
                "payload_sha256": payload_hash,
                "created_unix_seconds": now,
                "updated_unix_seconds": now,
            }
            # Claim the request path atomically. This closes the cross-process
            # race where two controller workers could both accept one request ID.
            self.root.mkdir(parents=True, exist_ok=True)
            target = self._path(request_id)
            try:
                descriptor = os.open(
                    str(target),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0),
                    0o600,
                )
            except FileExistsError:
                for _ in range(50):
                    existing = self.load(request_id)
                    if existing is not None:
                        self._validate_existing(existing, action, payload_hash)
                        return existing, False
                    time.sleep(0.01)
                raise RuntimeError("operation request is being claimed by another controller worker")
            try:
                encoded = json.dumps(record, indent=2, sort_keys=True, default=str).encode("utf-8")
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
            except Exception:
                try:
                    target.unlink()
                except OSError:
                    pass
                raise
            return record, True

    def complete(self, request_id: str, *, result: JsonDict, status: str = "SUCCEEDED") -> JsonDict:
        with self._lock:
            record = self.load(request_id) or self.begin(request_id, action="unknown")
            if record.get("status") != "RUNNING":
                return record
            record.update(
                {
                    "status": status,
                    "stage": "succeeded" if status == "SUCCEEDED" else record.get("stage"),
                    "percent": 100.0 if status == "SUCCEEDED" else record.get("percent"),
                    "completed_unix_seconds": time.time(),
                    "updated_unix_seconds": time.time(),
                    "result": result,
                }
            )
            self._write(request_id, record)
            return record

    def fail(self, request_id: str, *, error: str) -> JsonDict:
        with self._lock:
            record = self.load(request_id) or self.begin(request_id, action="unknown")
            if record.get("status") != "RUNNING":
                return record
            record.update(
                {
                    "status": "FAILED",
                    "stage": "failed",
                    "completed_unix_seconds": time.time(),
                    "updated_unix_seconds": time.time(),
                    "error": error,
                }
            )
            self._write(request_id, record)
            return record

    def cancel(self, operation_id: str, *, reason: str = "Operation cancelled") -> JsonDict:
        """Cancel a queued/running operation at a safe orchestration checkpoint."""

        with self._lock:
            record = self.load_operation(operation_id)
            if record is None:
                raise KeyError(f"operation not found: {operation_id}")
            if record.get("status") != "RUNNING":
                return record
            record.update(
                {
                    "status": "CANCELLED",
                    "stage": "cancelled",
                    "message": str(reason),
                    "completed_unix_seconds": time.time(),
                    "updated_unix_seconds": time.time(),
                }
            )
            self._write(str(record["request_id"]), record)
            return record

    def mark_running_interrupted(self) -> list[JsonDict]:
        """Mark operations abandoned by a controller restart for operator review."""

        interrupted: list[JsonDict] = []
        with self._lock:
            for record in self.list_operations(limit=100000):
                if record.get("status") != "RUNNING":
                    continue
                record.update(
                    {
                        "status": "INTERRUPTED",
                        "stage": "interrupted",
                        "message": "Controller restarted before this operation completed",
                        "completed_unix_seconds": time.time(),
                        "updated_unix_seconds": time.time(),
                    }
                )
                self._write(str(record["request_id"]), record)
                interrupted.append(record)
        return interrupted

    def update(
        self,
        request_id: str,
        *,
        stage: str,
        message: str,
        percent: float | None,
        details: JsonDict | None = None,
    ) -> JsonDict:
        """Persist an observable stage without inventing progress percentages."""

        if not str(stage).strip():
            raise ValueError("operation stage must not be empty")
        if percent is not None and not 0.0 <= float(percent) <= 100.0:
            raise ValueError("operation percent must be between 0 and 100 or null")
        with self._lock:
            record = self.load(request_id)
            if record is None:
                raise KeyError(f"operation request not found: {request_id}")
            if record.get("status") != "RUNNING":
                return record
            record.update(
                {
                    "stage": str(stage),
                    "message": str(message),
                    "percent": None if percent is None else float(percent),
                    "updated_unix_seconds": time.time(),
                }
            )
            if details is not None:
                record["details"] = dict(details)
            self._write(request_id, record)
            return record

    def load_operation(self, operation_id: str) -> JsonDict | None:
        value = str(operation_id or "").strip()
        if not value:
            return None
        if not self.root.is_dir():
            return None
        for path in self.root.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict) and payload.get("operation_id") == value:
                return payload
        return None

    def list_operations(self, *, limit: int = 100) -> list[JsonDict]:
        if limit <= 0:
            raise ValueError("operation limit must be positive")
        if not self.root.is_dir():
            return []
        records: list[JsonDict] = []
        for path in self.root.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict) and payload.get("operation_id"):
                records.append(payload)
        records.sort(key=lambda item: float(item.get("created_unix_seconds") or 0), reverse=True)
        return records[:limit]

    @staticmethod
    def _payload_hash(payload: Any | None) -> str | None:
        if payload is None:
            return None
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

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
        encoded = json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8")
        try:
            with temporary.open("wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(target)
        finally:
            try:
                temporary.unlink()
            except OSError:
                pass

    @staticmethod
    def _validate_existing(existing: JsonDict, action: str, payload_hash: str | None) -> None:
        if existing.get("action") != action or existing.get("payload_sha256") != payload_hash:
            raise ValueError("request_id is already bound to a different operation payload")


__all__ = ["OperationStore"]
