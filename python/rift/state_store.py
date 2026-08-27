"""Crash-safe local state storage for the RIFT control plane."""

from __future__ import annotations

import json
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import threading
import time
from typing import Any
import uuid


JsonDict = dict[str, Any]
_MIRROR_WRITE_LOCK = threading.Lock()


class StateConflictError(RuntimeError):
    """Raised when a caller writes against an obsolete state revision."""


class StateStore:
    """SQLite WAL-backed state with a compatibility JSON mirror.

    The database is authoritative. The JSON file exists for older diagnostics,
    tooling, and human inspection; it is repaired from the database after every
    successful committed write.
    """

    def __init__(self, path: str | Path, *, legacy_path: str | Path | None = None) -> None:
        self.path = Path(path)
        self.legacy_path = Path(legacy_path) if legacy_path is not None else self.path.with_suffix(".json")

    @property
    def revision(self) -> int:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT revision FROM control_state WHERE id = 1"
            ).fetchone()
        return int(row[0]) if row else 0

    def read(self) -> JsonDict:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT revision, payload FROM control_state WHERE id = 1"
            ).fetchone()
            if row is None:
                state = self._read_legacy()
                payload = json.dumps(state, sort_keys=True, separators=(",", ":"))
                connection.execute(
                    "INSERT INTO control_state(id, revision, updated_unix_seconds, payload) VALUES(1, 1, ?, ?)",
                    (time.time(), payload),
                )
                connection.commit()
                revision = 1
            else:
                revision = int(row[0])
                state = json.loads(str(row[1]))
        if not isinstance(state, dict):
            raise ValueError("persisted RIFT state must be an object")
        self._write_mirror(state, revision)
        return state

    def write(self, state: JsonDict, *, expected_revision: int | None = None) -> int:
        if not isinstance(state, dict):
            raise ValueError("RIFT state must be an object")
        payload = json.dumps(state, sort_keys=True, separators=(",", ":"))
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT revision FROM control_state WHERE id = 1"
            ).fetchone()
            current = int(row[0]) if row else 0
            if expected_revision is not None and current != int(expected_revision):
                connection.rollback()
                raise StateConflictError(
                    f"state revision conflict: expected {expected_revision}, current {current}"
                )
            revision = current + 1
            if row is None:
                connection.execute(
                    "INSERT INTO control_state(id, revision, updated_unix_seconds, payload) VALUES(1, ?, ?, ?)",
                    (revision, time.time(), payload),
                )
            else:
                connection.execute(
                    "UPDATE control_state SET revision = ?, updated_unix_seconds = ?, payload = ? WHERE id = 1",
                    (revision, time.time(), payload),
                )
            connection.commit()
        self._write_mirror(state, revision)
        return revision

    def backup(self, destination: str | Path) -> Path:
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        destination_db = sqlite3.connect(str(target))
        try:
            with self._connection() as source:
                source.backup(destination_db)
            destination_db.commit()
        finally:
            destination_db.close()
        return target

    def restore(self, source: str | Path) -> int:
        source_path = Path(source)
        if not source_path.is_file():
            raise FileNotFoundError(f"state backup does not exist: {source_path}")
        self._validate_backup(source_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".restore.tmp")
        shutil.copy2(source_path, temporary)
        temporary.replace(self.path)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(self.path) + suffix)
            if sidecar.exists():
                sidecar.unlink()
        state = self.read()
        return self.revision

    @staticmethod
    def _validate_backup(source: Path) -> None:
        try:
            connection = sqlite3.connect(
                f"file:{source.resolve()}?mode=ro", uri=True, timeout=5.0
            )
            try:
                integrity = connection.execute("PRAGMA integrity_check").fetchone()
                if not integrity or str(integrity[0]).lower() != "ok":
                    raise ValueError(f"state backup failed SQLite integrity check: {source}")
                table = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'control_state'"
                ).fetchone()
                if table is None:
                    raise ValueError(f"state backup has no control_state table: {source}")
                row = connection.execute(
                    "SELECT id, revision, payload FROM control_state WHERE id = 1"
                ).fetchone()
                if row is None:
                    raise ValueError(f"state backup has no controller state row: {source}")
                if int(row[0]) != 1 or int(row[1]) < 1:
                    raise ValueError(f"state backup has an invalid revision: {source}")
                payload = json.loads(str(row[2]))
                if not isinstance(payload, dict):
                    raise ValueError(f"state backup payload is not an object: {source}")
            finally:
                connection.close()
        except sqlite3.DatabaseError as exc:
            raise ValueError(f"state backup is not a valid SQLite database: {source}") from exc

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.path), timeout=15.0)
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS control_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                revision INTEGER NOT NULL,
                updated_unix_seconds REAL NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    def _read_legacy(self) -> JsonDict:
        if not self.legacy_path.is_file():
            return {"schema_version": 1, "services": {}, "history": []}
        try:
            payload = json.loads(self.legacy_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"legacy RIFT state is invalid JSON: {self.legacy_path}") from exc
        if not isinstance(payload, dict):
            raise ValueError("legacy RIFT state must be an object")
        return payload

    def _write_mirror(self, state: JsonDict, revision: int) -> None:
        with _MIRROR_WRITE_LOCK:
            self.legacy_path.parent.mkdir(parents=True, exist_ok=True)
            mirror = dict(state)
            mirror["state_store"] = {
                "backend": "sqlite-wal",
                "database": str(self.path),
                "revision": revision,
            }
            # The controller and dashboard can share one RIFT_HOME on Windows.
            # Use a unique temporary file, flush it durably, and retry the
            # diagnostic mirror briefly when another process is replacing it.
            temporary = self.legacy_path.with_suffix(f".{uuid.uuid4().hex}.tmp")
            try:
                with temporary.open("w", encoding="utf-8") as handle:
                    handle.write(json.dumps(mirror, indent=2, sort_keys=True))
                    handle.flush()
                    os.fsync(handle.fileno())
                last_error: OSError | None = None
                for _ in range(5):
                    try:
                        temporary.replace(self.legacy_path)
                        return
                    except OSError as exc:
                        last_error = exc
                        time.sleep(0.02)
                if last_error is not None:
                    return
            finally:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass


__all__ = ["StateConflictError", "StateStore"]
