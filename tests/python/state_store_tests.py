import json
import importlib.util
import sqlite3
from pathlib import Path
import sys
import tempfile
import threading


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "rift_state_store_under_test", ROOT / "python" / "rift" / "state_store.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
StateConflictError = MODULE.StateConflictError
StateStore = MODULE.StateStore


def test_state_store_imports_legacy_json_and_writes_sqlite_authoritatively():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        legacy = root / "state.json"
        legacy.write_text(
            json.dumps({"schema_version": 2, "services": {"chat": {"status": "stopped"}}}),
            encoding="utf-8",
        )
        store = StateStore(root / "state.db", legacy_path=legacy)

        state = store.read()
        assert state["services"]["chat"]["status"] == "stopped"
        assert store.revision == 1

        revision = store.write({"schema_version": 2, "services": {"chat": {"status": "healthy"}}})
        assert revision == 2
        assert store.read()["services"]["chat"]["status"] == "healthy"
        assert json.loads(legacy.read_text(encoding="utf-8"))["services"]["chat"]["status"] == "healthy"


def test_state_store_rejects_stale_revision_and_restores_backup():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = StateStore(root / "state.db", legacy_path=root / "state.json")
        store.write({"schema_version": 2, "services": {}, "marker": "first"})
        backup = root / "backup.db"
        store.backup(backup)
        store.write({"schema_version": 2, "services": {}, "marker": "second"})

        try:
            store.write({"schema_version": 2, "services": {}, "marker": "stale"}, expected_revision=1)
        except StateConflictError:
            pass
        else:
            raise AssertionError("stale state revision was accepted")

        store.restore(backup)
        assert store.read()["marker"] == "first"

        corrupt = root / "corrupt.db"
        corrupt.write_text("not a sqlite database", encoding="utf-8")
        try:
            store.restore(corrupt)
        except ValueError as exc:
            assert "backup" in str(exc).lower()
        else:
            raise AssertionError("corrupt state backup was accepted")
        assert store.read()["marker"] == "first"

        malformed = root / "malformed.db"
        connection = sqlite3.connect(malformed)
        connection.execute("CREATE TABLE unrelated(value TEXT)")
        connection.commit()
        connection.close()
        try:
            store.restore(malformed)
        except ValueError as exc:
            assert "control_state" in str(exc)
        else:
            raise AssertionError("malformed state backup was accepted")
        assert store.read()["marker"] == "first"


def test_state_store_serializes_legacy_mirror_writes_across_readers():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        database = root / "state.db"
        legacy = root / "state.json"
        StateStore(database, legacy_path=legacy).write(
            {"schema_version": 2, "services": {}, "marker": "concurrent"}
        )
        errors = []

        def read_state():
            try:
                StateStore(database, legacy_path=legacy).read()
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        workers = [threading.Thread(target=read_state) for _ in range(12)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=5)

        assert not errors, errors
        assert json.loads(legacy.read_text(encoding="utf-8"))["marker"] == "concurrent"


def main():
    test_state_store_imports_legacy_json_and_writes_sqlite_authoritatively()
    test_state_store_rejects_stale_revision_and_restores_backup()
    test_state_store_serializes_legacy_mirror_writes_across_readers()
    print("RIFT state store tests passed")


if __name__ == "__main__":
    main()
