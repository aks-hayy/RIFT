"""Release hygiene and dependency provenance audit for RIFT."""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from typing import Any


JsonDict = dict[str, Any]

_MODEL_SUFFIXES = {".gguf", ".safetensors", ".bin", ".pt", ".pth"}
_SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "rift", ".venv", "venv"}
_GENERATED_DIRS = {
    ".rift",
    "build",
    "dist",
    "node_modules",
    ".output",
    ".tanstack",
    ".wrangler",
    "_skbuild",
    "wheelhouse",
}
_SECRET_NAMES = {".env", ".env.local", "id_rsa", "id_ed25519"}
_KNOWN_PYTHON = {
    "pyyaml": {"license": "MIT", "url": "https://github.com/yaml/pyyaml/blob/main/LICENSE"},
    "zeroconf": {"license": "LGPL-2.1-or-later", "url": "https://github.com/python-zeroconf/python-zeroconf/blob/master/LICENSE"},
    "cryptography": {"license": "Apache-2.0 OR BSD-3-Clause", "url": "https://github.com/pyca/cryptography/blob/main/LICENSE"},
    "setuptools": {"license": "MIT", "url": "https://github.com/pypa/setuptools/blob/main/LICENSE"},
    "wheel": {"license": "MIT", "url": "https://github.com/pypa/wheel/blob/main/LICENSE.txt"},
}


def audit_release(root: str | Path) -> JsonDict:
    base = Path(root).resolve()
    runtime_violations = _runtime_violations(base)
    dependencies = _dependency_inventory(base)
    unresolved = list(dependencies["unresolved_licenses"])
    tracked = _tracked_violations(base, runtime_violations)
    return {
        "status": "PASS" if not runtime_violations and not unresolved and (base / "LICENSE").is_file() else "FAIL",
        "root": str(base),
        "tracked_violations": tracked,
        "dependency_inventory": dependencies["inventory"],
        "unresolved_licenses": sorted(set(unresolved)),
        "runtime_artifact_violations": runtime_violations,
        "license_file_present": (base / "LICENSE").is_file(),
        "legal_boundary": "This audit checks repository hygiene and recorded provenance; it is not legal advice and does not clear model or backend licenses.",
    }


def _runtime_violations(root: Path) -> list[JsonDict]:
    violations: list[JsonDict] = []
    seen_dirs: set[str] = set()
    for current, dirs, files in _walk(root):
        relative_dir = current.relative_to(root).as_posix() if current != root else ""
        for directory in list(dirs):
            if directory in _GENERATED_DIRS:
                path = "/".join(item for item in (relative_dir, directory) if item)
                if path not in seen_dirs:
                    violations.append({"path": path, "kind": "generated_runtime_directory"})
                    seen_dirs.add(path)
                dirs.remove(directory)
        for filename in files:
            path = current / filename
            relative = path.relative_to(root).as_posix()
            if filename in _SECRET_NAMES or filename.endswith((".pem", ".key")):
                violations.append({"path": relative, "kind": "secret_or_private_key"})
            elif path.suffix.lower() in _MODEL_SUFFIXES:
                violations.append({"path": relative, "kind": "model_weight"})
            elif path.suffix.lower() == ".zip":
                violations.append({"path": relative, "kind": "source_or_runtime_archive"})
    return violations


def _walk(root: Path):
    for current, dirs, files in __import__("os").walk(root):
        dirs[:] = [item for item in dirs if item not in _SKIP_DIRS]
        if Path(current).resolve() == (root / "models").resolve():
            dirs[:] = [item for item in dirs if item != "local"]
        yield Path(current), dirs, files


def _tracked_violations(root: Path, runtime: list[JsonDict]) -> list[JsonDict]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "ls-files"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return [{"path": item["path"], "kind": item["kind"], "source": "filesystem-fallback"} for item in runtime]
    tracked_paths = set(completed.stdout.splitlines())
    return [item for item in runtime if item["path"] in tracked_paths]


def _dependency_inventory(root: Path) -> JsonDict:
    inventory: list[JsonDict] = []
    unresolved: list[str] = []
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            document = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            unresolved.append(f"pyproject.toml: {exc}")
        else:
            dependencies = list((document.get("project") or {}).get("dependencies") or [])
            dependencies.extend(list((document.get("build-system") or {}).get("requires") or []))
            for requirement in dependencies:
                name = re.split(r"[<>=!~;\[]", str(requirement), maxsplit=1)[0].strip()
                key = name.lower()
                license_data = _KNOWN_PYTHON.get(key)
                item = {"name": name, "source": "python", "requirement": requirement}
                if license_data:
                    item.update(license_data)
                else:
                    item["license_status"] = "unresolved"
                    unresolved.append(name)
                inventory.append(item)

    for frontend in (root / "ui", root / "dashboard"):
        package_json = frontend / "package.json"
        lockfile = frontend / "package-lock.json"
        if not package_json.is_file():
            continue
        try:
            package = json.loads(package_json.read_text(encoding="utf-8"))
            lock = json.loads(lockfile.read_text(encoding="utf-8")) if lockfile.is_file() else {}
        except (OSError, json.JSONDecodeError) as exc:
            unresolved.append(f"{frontend.name}: {exc}")
            continue
        lock_packages = lock.get("packages") if isinstance(lock, dict) else {}
        direct = {
            **(package.get("dependencies") or {}),
            **(package.get("devDependencies") or {}),
        }
        for name, requirement in direct.items():
            metadata = lock_packages.get(f"node_modules/{name}") if isinstance(lock_packages, dict) else None
            item = {"name": name, "source": f"npm:{frontend.name}", "requirement": requirement}
            if isinstance(metadata, dict) and metadata.get("license"):
                item["license"] = metadata["license"]
                item["version"] = metadata.get("version")
            else:
                item["license_status"] = "unresolved"
                unresolved.append(f"npm:{frontend.name}:{name}")
            inventory.append(item)
    return {"inventory": inventory, "unresolved_licenses": unresolved}


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Audit RIFT release hygiene and dependency provenance.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = audit_release(args.root)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"RIFT release audit: {report['status']}")
        print(f"Runtime violations: {len(report['runtime_artifact_violations'])}")
        print(f"Unresolved licenses: {len(report['unresolved_licenses'])}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
