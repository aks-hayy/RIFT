"""Static acceptance checks for the RIFT Elastic Intelligence Mesh OCI slice.

These tests intentionally require no container runtime. They validate the deploy
manifests and image definitions that can be checked on every development host.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy"
COMPOSE_PATH = DEPLOY / "compose.mesh.yaml"
EXPECTED_SERVICES = {"controller", "node", "gateway", "emulator"}
EXPECTED_DOCKERFILES = {
    "controller": "deploy/containers/Controller.Dockerfile",
    "node": "deploy/containers/Node.Dockerfile",
    "gateway": "deploy/containers/Gateway.Dockerfile",
    "emulator": "deploy/containers/Emulator.Dockerfile",
}


def _load_compose() -> dict[str, Any]:
    # JSON is a strict subset of YAML 1.2. Keeping this Compose example in that
    # subset makes validation dependency-free while remaining valid Compose.
    return json.loads(COMPOSE_PATH.read_text(encoding="utf-8"))


def _environment_mapping(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(key): str(item) for key, item in value.items()}
    if isinstance(value, list):
        result: dict[str, str] = {}
        for item in value:
            key, separator, setting = str(item).partition("=")
            result[key] = setting if separator else ""
        return result
    return {}


class ContainerManifestTests(unittest.TestCase):
    def test_required_container_files_exist(self) -> None:
        required = [
            COMPOSE_PATH,
            DEPLOY / "config" / "node-agent.yaml",
            DEPLOY / "config" / "rift.yaml",
            DEPLOY / "entrypoints" / "controller.py",
            DEPLOY / "entrypoints" / "emulator.py",
            DEPLOY / "healthcheck.py",
            ROOT / "docs" / "guides" / "mesh-containers.md",
        ]
        required.extend(ROOT / path for path in EXPECTED_DOCKERFILES.values())
        for path in required:
            self.assertTrue(path.is_file(), f"required deployment file is missing: {path}")

    def test_compose_declares_the_four_mesh_roles(self) -> None:
        compose = _load_compose()
        self.assertEqual(set((compose.get("services") or {}).keys()), EXPECTED_SERVICES)
        self.assertIn("volumes", compose)
        self.assertIn("networks", compose)

    def test_services_are_health_checked_persistent_and_least_privileged(self) -> None:
        services = _load_compose()["services"]
        for name, service in services.items():
            with self.subTest(service=name):
                self.assertEqual(service.get("privileged", False), False)
                self.assertTrue(service.get("read_only"), "root filesystem must be read-only")
                self.assertIn("ALL", service.get("cap_drop") or [])
                self.assertIn("no-new-privileges:true", service.get("security_opt") or [])
                self.assertTrue(service.get("init"), "PID 1 signal forwarding must be enabled")
                self.assertTrue(service.get("profiles"), "every role needs an explicit profile")
                self.assertIn("healthcheck", service)
                self.assertTrue(service["healthcheck"].get("test"))
                mounts = service.get("volumes") or []
                self.assertTrue(
                    any("/var/lib/rift" in str(mount) for mount in mounts),
                    "every role must persist RIFT state",
                )
                build = service.get("build") or {}
                self.assertEqual(build.get("context"), "..")
                self.assertEqual(build.get("dockerfile"), EXPECTED_DOCKERFILES[name])

    def test_no_baked_or_literal_secrets(self) -> None:
        secret_key = re.compile(r"(token|password|secret|private[_-]?key)", re.IGNORECASE)
        services = _load_compose()["services"]
        for name, service in services.items():
            for key, value in _environment_mapping(service.get("environment")).items():
                if secret_key.search(key):
                    self.assertTrue(
                        value == "" or value.startswith("${"),
                        f"{name}.{key} must be supplied at runtime, not embedded",
                    )

        for dockerfile in EXPECTED_DOCKERFILES.values():
            text = (ROOT / dockerfile).read_text(encoding="utf-8")
            self.assertNotRegex(text, r"(?im)^\s*(COPY|ADD)\s+.*(secret|\.pem|\.key)")
            self.assertNotRegex(text, r"(?im)^\s*ENV\s+\S*(TOKEN|PASSWORD|SECRET)\S*\s*=\s*[^$\s]+")

    def test_images_install_the_rift_wheel_and_run_as_non_root(self) -> None:
        for name, dockerfile in EXPECTED_DOCKERFILES.items():
            text = (ROOT / dockerfile).read_text(encoding="utf-8")
            with self.subTest(image=name):
                self.assertRegex(text, r"(?m)^FROM\s+python:3\.12-slim\s*$")
                self.assertIn("pip install --no-cache-dir .", text)
                self.assertNotIn("CMAKE_ARGS", text)
                self.assertNotIn("nvidia/cuda", text)
                self.assertRegex(text, r"(?m)^USER\s+(?!root\b)\S+")
                self.assertRegex(text, r"(?m)^(ENTRYPOINT|CMD)\s+")


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ContainerManifestTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
