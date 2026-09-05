"""Release boundary tests for running RIFT without the optional native module."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import types


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


def test_rift_imports_without_native_module() -> None:
    sys.modules.pop("rift", None)
    sys.modules.pop("rift._core", None)

    import rift

    assert rift.cuda_device_count() == 0
    assert rift.build_info()["native_available"] is False
    assert rift.InferenceEngine is None


def test_runtime_paths_default_outside_checkout() -> None:
    from rift.runtime_paths import RiftPaths

    with tempfile.TemporaryDirectory() as directory:
        checkout = Path(directory) / "checkout"
        checkout.mkdir()
        previous = os.environ.pop("RIFT_HOME", None)
        try:
            paths = RiftPaths.from_environment(cwd=checkout)
            assert paths.home != checkout / ".rift"
            assert paths.state.parent == paths.home
            assert paths.models != checkout / "models"
        finally:
            if previous is not None:
                os.environ["RIFT_HOME"] = previous


def test_runtime_paths_honor_explicit_rift_home() -> None:
    from rift.runtime_paths import RiftPaths

    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory) / "rift-home"
        previous = os.environ.get("RIFT_HOME")
        os.environ["RIFT_HOME"] = str(home)
        try:
            paths = RiftPaths.from_environment()
            assert paths.home == home
            assert paths.state == home / "state.db"
            assert paths.models == home / "models"
        finally:
            if previous is None:
                os.environ.pop("RIFT_HOME", None)
            else:
                os.environ["RIFT_HOME"] = previous


def test_project_build_is_pure_python() -> None:
    import tomllib

    document = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    build_system = document["build-system"]
    assert build_system["build-backend"] == "setuptools.build_meta"
    assert all("scikit-build" not in item.lower() for item in build_system["requires"])
    assert "setuptools" in " ".join(build_system["requires"]).lower()


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and isinstance(value, types.FunctionType):
            value()
    print("control_plane_bootstrap_tests: PASS")
