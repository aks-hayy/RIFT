"""Deployment policy and supply-chain manifests for RIFT."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from typing import Any


JsonDict = dict[str, Any]


class GovernancePolicy:
    def __init__(self, policy: JsonDict | None = None) -> None:
        values = policy or {}
        self.allowed_sources = {str(item).lower() for item in values.get("allowed_sources", [])}
        self.denied_sources = {str(item).lower() for item in values.get("denied_sources", [])}
        self.allowed_licenses = {str(item).lower() for item in values.get("allowed_licenses", [])}
        self.denied_licenses = {str(item).lower() for item in values.get("denied_licenses", [])}
        self.allow_gated = bool(values.get("allow_gated", False))
        self.require_hashes = bool(values.get("require_hashes", False))
        self.allowed_backends = {str(item).lower() for item in values.get("allowed_backends", [])}

    def evaluate(self, *, model: JsonDict, backend: JsonDict | str) -> JsonDict:
        source = str(model.get("source") or "unknown").lower()
        license_name = str(model.get("license") or "unknown").lower()
        backend_name = str(backend.get("name") if isinstance(backend, dict) else backend).lower()
        violations = []
        warnings = []
        if self.allowed_sources and source not in self.allowed_sources:
            violations.append(f"model source {source} is not on the allow list")
        if source in self.denied_sources:
            violations.append(f"model source {source} is denied")
        if self.allowed_licenses and license_name not in self.allowed_licenses:
            violations.append(f"license {license_name} is not on the allow list")
        if license_name in self.denied_licenses:
            violations.append(f"license {license_name} is denied")
        if bool(model.get("gated")) and not self.allow_gated:
            violations.append("gated artifacts are not allowed by policy")
        if self.allowed_backends and backend_name not in self.allowed_backends:
            violations.append(f"backend {backend_name} is not on the allow list")
        manifest = model.get("artifact_manifest") or model.get("artifact") or {}
        if self.require_hashes:
            files = manifest.get("files", []) if isinstance(manifest, dict) else []
            if not files or any(not item.get("sha256") for item in files):
                violations.append("artifact hashes are required but incomplete")
        if license_name in ("", "unknown", "none"):
            warnings.append("model license is unknown; human review is required")
        return {
            "allowed": not violations,
            "violations": violations,
            "warnings": warnings,
            "evaluated": {
                "source": source,
                "license": license_name,
                "gated": bool(model.get("gated")),
                "backend": backend_name,
            },
        }


def deployment_manifest(
    *,
    project: str,
    plan: JsonDict,
    state: JsonDict,
    governance: JsonDict,
) -> JsonDict:
    manifest = {
        "schema_version": 1,
        "created_unix_seconds": time.time(),
        "project": project,
        "plan": plan,
        "observed_state": state,
        "governance": governance,
        "security_boundary": (
            "RIFT orchestrates third-party backends; inference data handling and backend network exposure "
            "remain governed by the selected backend and operator configuration."
        ),
    }
    manifest["sha256"] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return manifest


def write_deployment_manifest(manifest: JsonDict, path: str | Path) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(target)
    return str(target)


__all__ = ["GovernancePolicy", "deployment_manifest", "write_deployment_manifest"]
