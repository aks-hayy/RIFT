"""Run cheap, deterministic release checks without installing extra tooling."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a RIFT checkout before packaging.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--allow-runtime-artifacts", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    compile_result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(root / "python")],
        cwd=root,
    )
    if compile_result.returncode:
        return compile_result.returncode

    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / "python"))
    from rift import __version__
    from rift.dashboard import bundled_dashboard_root, dashboard_launch_plan
    from rift.runtime_paths import RiftPaths
    from scripts.audit_release import audit_release

    checks = {
        "version": __version__,
        "bundled_dashboard": (bundled_dashboard_root() / "index.html").is_file(),
        "dashboard_plan": dashboard_launch_plan().dependencies_ready,
        "runtime_home_outside_checkout": RiftPaths.from_environment(cwd=root).home != root / ".rift",
    }
    audit = audit_release(root)
    if args.allow_runtime_artifacts:
        audit["status"] = "PASS_WITH_LOCAL_RUNTIME_ARTIFACTS"
        audit["note"] = "Runtime artifacts were explicitly allowed for a development checkout."
    checks["release_audit"] = audit["status"]
    print(json.dumps({"checks": checks, "audit": audit}, indent=2, sort_keys=True, default=str))
    if not all(value is True for key, value in checks.items() if key != "version"):
        return 1
    if audit["status"] == "FAIL" and not args.allow_runtime_artifacts:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
