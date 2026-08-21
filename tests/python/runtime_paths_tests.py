import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


def test_runtime_paths_are_external_and_migration_is_previewed_and_backed_up():
    from rift.runtime_paths import RiftPaths

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        checkout = root / "checkout"
        legacy = checkout / ".rift"
        legacy.mkdir(parents=True)
        (legacy / "state.json").write_text(
            json.dumps({"schema_version": 1, "services": {"chat": {"status": "stopped"}}}),
            encoding="utf-8",
        )
        model_dir = checkout / "models" / "local"
        model_dir.mkdir(parents=True)
        model = model_dir / "fixture.gguf"
        model.write_bytes(b"fixture-model")

        paths = RiftPaths(root / "runtime").create()
        preview = paths.migration_preview(source_root=checkout)
        assert preview["write_required"] is True
        assert not (paths.home / "legacy-state").exists()
        assert model.exists()

        result = paths.migrate_checkout(source_root=checkout, write=True)
        assert result["applied"] is True
        assert len(result["copied"]) == 2
        assert list((paths.home / "backups").glob("checkout-migration-*.zip"))
        migrated_model = paths.models / "local" / "fixture.gguf"
        assert migrated_model.read_bytes() == model.read_bytes()
        assert hashlib.sha256(migrated_model.read_bytes()).hexdigest() == hashlib.sha256(model.read_bytes()).hexdigest()
        assert model.exists(), "copy-first migration must not delete operator data"


def test_runtime_paths_never_accept_checkout_dot_rift_as_explicit_home():
    from rift.runtime_paths import RiftPaths

    with tempfile.TemporaryDirectory() as tmp:
        checkout = Path(tmp)
        previous = os.environ.get("RIFT_HOME")
        os.environ["RIFT_HOME"] = str(checkout / ".rift")
        try:
            RiftPaths.from_environment(cwd=checkout)
        except ValueError:
            pass
        else:
            raise AssertionError("checkout-local .rift was accepted as runtime home")
        finally:
            if previous is None:
                os.environ.pop("RIFT_HOME", None)
            else:
                os.environ["RIFT_HOME"] = previous


if __name__ == "__main__":
    test_runtime_paths_are_external_and_migration_is_previewed_and_backed_up()
    test_runtime_paths_never_accept_checkout_dot_rift_as_explicit_home()
    print("runtime_paths_tests: PASS")
