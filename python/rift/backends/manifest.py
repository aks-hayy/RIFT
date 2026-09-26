"""Declarative capability manifests for first-party RIFT backends."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from ..adapters.contracts import ADAPTER_API_VERSION, AdapterManifest, BackendCapability


JsonDict = dict[str, Any]


class BackendManifestError(ValueError):
    """Raised when a backend manifest cannot be safely consumed."""


@dataclass(frozen=True)
class BackendManifest:
    schema_version: int
    backend_id: str
    display_name: str
    adapter_api_version: str
    upstream_project: str
    module: str
    factory: str = "create_backend"
    tuning_module: str | None = None
    tuning_factory: str = "create_tuning_adapter"
    supported_tasks: tuple[str, ...] = ()
    supported_formats: tuple[str, ...] = ()
    quantizations: tuple[str, ...] = ()
    operating_systems: tuple[str, ...] = ()
    accelerators: tuple[str, ...] = ()
    installation_methods: tuple[str, ...] = ()
    endpoints: tuple[str, ...] = ("openai",)
    features: tuple[str, ...] = ()
    tuning_profiles: tuple[str, ...] = ("speed", "cost")
    tuning_parameters: tuple[JsonDict, ...] = ()
    topology_modes: tuple[str, ...] = ("single_node", "replicated")
    evidence_status: str = "experimental"
    multi_gpu: bool = False
    streaming: bool = True
    description: str = ""

    @classmethod
    def from_file(cls, path: Path) -> "BackendManifest":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BackendManifestError(f"failed to read backend manifest {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise BackendManifestError(f"backend manifest must be an object: {path}")
        required = ("schema_version", "backend_id", "display_name", "adapter_api_version", "upstream_project", "module")
        missing = [name for name in required if not str(payload.get(name) or "").strip()]
        if missing:
            raise BackendManifestError(f"backend manifest {path} is missing: {', '.join(missing)}")
        try:
            schema_version = int(payload["schema_version"])
        except (TypeError, ValueError) as exc:
            raise BackendManifestError(f"schema_version must be an integer: {path}") from exc
        if schema_version != 1:
            raise BackendManifestError(f"unsupported backend manifest schema: {schema_version}")
        backend_id = str(payload["backend_id"]).strip()
        if any(part in backend_id for part in ("/", "\\", "..")):
            raise BackendManifestError(f"backend_id must be a simple identifier: {backend_id}")
        adapter_api_version = str(payload["adapter_api_version"]).strip()
        if adapter_api_version.split(".", 1)[0] != ADAPTER_API_VERSION.split(".", 1)[0]:
            raise BackendManifestError(
                f"backend {backend_id} uses incompatible adapter API {adapter_api_version}; host is {ADAPTER_API_VERSION}"
            )

        def strings(name: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
            value = payload.get(name, default)
            if not isinstance(value, (list, tuple)):
                raise BackendManifestError(f"{name} must be an array in {path}")
            return tuple(str(item).strip() for item in value if str(item).strip())

        raw_parameters = payload.get("tuning_parameters", ())
        if not isinstance(raw_parameters, (list, tuple)):
            raise BackendManifestError(f"tuning_parameters must be an array in {path}")
        parameters: list[JsonDict] = []
        for item in raw_parameters:
            if not isinstance(item, dict) or not str(item.get("name") or "").strip():
                raise BackendManifestError(f"every tuning parameter needs a name in {path}")
            parameters.append(dict(item))
        return cls(
            schema_version=schema_version,
            backend_id=backend_id,
            display_name=str(payload["display_name"]).strip(),
            adapter_api_version=adapter_api_version,
            upstream_project=str(payload["upstream_project"]).strip(),
            module=str(payload["module"]).strip(),
            factory=str(payload.get("factory") or "create_backend").strip(),
            tuning_module=(str(payload["tuning_module"]).strip() if payload.get("tuning_module") else None),
            tuning_factory=str(payload.get("tuning_factory") or "create_tuning_adapter").strip(),
            supported_tasks=strings("supported_tasks"),
            supported_formats=strings("supported_formats"),
            quantizations=strings("quantizations"),
            operating_systems=strings("operating_systems"),
            accelerators=strings("accelerators"),
            installation_methods=strings("installation_methods"),
            endpoints=strings("endpoints", ("openai",)),
            features=strings("features"),
            tuning_profiles=strings("tuning_profiles", ("speed", "cost")),
            tuning_parameters=tuple(parameters),
            topology_modes=strings("topology_modes", ("single_node", "replicated")),
            evidence_status=str(payload.get("evidence_status") or "experimental").strip(),
            multi_gpu=bool(payload.get("multi_gpu", False)),
            streaming=bool(payload.get("streaming", True)),
            description=str(payload.get("description") or "").strip(),
        )

    def to_dict(self) -> JsonDict:
        return {
            "schema_version": self.schema_version,
            "backend_id": self.backend_id,
            "display_name": self.display_name,
            "adapter_api_version": self.adapter_api_version,
            "upstream_project": self.upstream_project,
            "module": self.module,
            "factory": self.factory,
            "tuning_module": self.tuning_module,
            "tuning_factory": self.tuning_factory,
            "supported_tasks": list(self.supported_tasks),
            "supported_formats": list(self.supported_formats),
            "quantizations": list(self.quantizations),
            "operating_systems": list(self.operating_systems),
            "accelerators": list(self.accelerators),
            "installation_methods": list(self.installation_methods),
            "endpoints": list(self.endpoints),
            "features": list(self.features),
            "tuning_profiles": list(self.tuning_profiles),
            "tuning_parameters": [dict(item) for item in self.tuning_parameters],
            "topology_modes": list(self.topology_modes),
            "evidence_status": self.evidence_status,
            "multi_gpu": self.multi_gpu,
            "streaming": self.streaming,
            "description": self.description,
        }

    def to_adapter_manifest(self) -> AdapterManifest:
        """Convert the static manifest into the shared runtime contract."""

        return AdapterManifest(
            adapter_id=self.backend_id,
            display_name=self.display_name,
            upstream_project=self.upstream_project,
            adapter_version=self.adapter_api_version,
            adapter_api_version=self.adapter_api_version,
            kind="backend",
            capability=BackendCapability(
                tasks=self.supported_tasks,
                formats=self.supported_formats,
                quantizations=self.quantizations,
                operating_systems=self.operating_systems,
                accelerators=self.accelerators,
                installation_methods=self.installation_methods,
                endpoints=self.endpoints,
                features=self.features,
                multi_gpu=self.multi_gpu,
                streaming=self.streaming,
            ),
            evidence_status=self.evidence_status,
            description=self.description,
        )


__all__ = ["BackendManifest", "BackendManifestError"]
