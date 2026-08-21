import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


def test_canonical_console_and_release_tree() -> None:
    from rift.dashboard import find_dashboard_root

    assert find_dashboard_root(ROOT) == (ROOT / "ui").resolve()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "seismic-deploy-main" not in readme
    assert not (ROOT / "seismic-deploy-main.zip").exists()
    assert (ROOT / "python" / "rift" / "web" / "static" / "index.html").is_file()
    assert ".rift/" in (ROOT / ".gitignore").read_text(encoding="utf-8")


def test_release_manifest_does_not_include_operator_storage() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "pyproject.toml").write_text(
            '[project]\nname = "rift-fixture"\n',
            encoding="utf-8",
        )
        assert "models/local" not in (root / "pyproject.toml").read_text(encoding="utf-8")


def main() -> None:
    test_canonical_console_and_release_tree()
    test_release_manifest_does_not_include_operator_storage()
    print("repository_layout_tests: PASS")


if __name__ == "__main__":
    main()
