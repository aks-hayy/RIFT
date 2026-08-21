import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def test_release_audit_detects_runtime_and_unknown_dependency_violations() -> None:
    from scripts.audit_release import audit_release

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "LICENSE").write_text("Apache License", encoding="utf-8")
        (root / "pyproject.toml").write_text(
            '[project]\nname = "fixture"\ndependencies = ["unknown-package>=1"]\n',
            encoding="utf-8",
        )
        (root / "model.gguf").write_bytes(b"model")
        (root / ".rift").mkdir()
        (root / ".rift" / "state.json").write_text("{}", encoding="utf-8")
        (root / "snapshot.zip").write_bytes(b"zip")
        report = audit_release(root)
        violations = report["runtime_artifact_violations"]
        assert any(item["path"] == "model.gguf" for item in violations)
        assert any(item["path"].startswith(".rift") for item in violations)
        assert any(item["path"] == "snapshot.zip" for item in violations)
        assert "unknown-package" in report["unresolved_licenses"]
        assert report["status"] == "FAIL"


def test_release_audit_accepts_clean_minimal_fixture() -> None:
    from scripts.audit_release import audit_release

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "LICENSE").write_text("Apache License", encoding="utf-8")
        (root / "pyproject.toml").write_text(
            '[project]\nname = "fixture"\ndependencies = ["PyYAML>=6"]\n',
            encoding="utf-8",
        )
        report = audit_release(root)
        assert report["status"] == "PASS"
        assert report["runtime_artifact_violations"] == []
        assert report["unresolved_licenses"] == []


def main() -> None:
    test_release_audit_detects_runtime_and_unknown_dependency_violations()
    test_release_audit_accepts_clean_minimal_fixture()
    print("release_audit_tests: PASS")


if __name__ == "__main__":
    main()
