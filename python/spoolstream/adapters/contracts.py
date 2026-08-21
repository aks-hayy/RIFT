"""Versioned contracts shared by RIFT backend and artifact adapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol, runtime_checkable


JsonDict = dict[str, Any]
ADAPTER_API_VERSION = "1.0"


@dataclass(frozen=True)
class AdapterDiagnostic:
    level: str
    code: str
    message: str
    remediation: str | None = None

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class BackendCapability:
    tasks: tuple[str, ...]
    formats: tuple[str, ...]
    quantizations: tuple[str, ...] = ()
    architectures: tuple[str, ...] = ("*",)
    operating_systems: tuple[str, ...] = ()
    accelerators: tuple[str, ...] = ()
    installation_methods: tuple[str, ...] = ()
    endpoints: tuple[str, ...] = ("openai",)
    features: tuple[str, ...] = ()
    security_boundaries: tuple[str, ...] = ()
    multi_gpu: bool = False
    streaming: bool = True

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class AdapterManifest:
    adapter_id: str
    display_name: str
    upstream_project: str
    adapter_version: str
    adapter_api_version: str
    kind: str
    capability: BackendCapability
    evidence_status: str = "experimental"
    homepage: str | None = None
    description: str | None = None

    def to_dict(self) -> JsonDict:
        payload = asdict(self)
        payload["capability"] = self.capability.to_dict()
        return payload


@dataclass(frozen=True)
class ArtifactFile:
    path: str
    size: int | None
    role: str
    required: bool = True
    sha256: str | None = None
    etag: str | None = None

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class ArtifactVariant:
    artifact_id: str
    format: str
    quantization: str | None
    files: tuple[ArtifactFile, ...]
    total_bytes: int | None
    size_known: bool
    source: str = "unknown"
    repo_id: str | None = None
    revision: str | None = None
    architecture: str | None = None
    metadata: JsonDict = field(default_factory=dict)
    validation: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        payload = asdict(self)
        payload["files"] = [item.to_dict() for item in self.files]
        return payload


@dataclass(frozen=True)
class ModelIdentity:
    identity_id: str
    repo_id: str
    family: str
    task: str
    revision: str | None = None
    base_models: tuple[str, ...] = ()
    parameter_count: int | None = None
    languages: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    confidence: float = 0.0

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class ModelRevision:
    repo_id: str
    revision: str
    identity_id: str
    source: str
    created_unix_seconds: float | None = None
    immutable: bool = False
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class WorkloadProfile:
    task: str
    context_length: int = 8192
    concurrency: int = 1
    objective_weights: JsonDict = field(
        default_factory=lambda: {"quality": 0.40, "speed": 0.25, "fit": 0.20, "trust": 0.15}
    )
    minimum_quality: float | None = None
    maximum_ttft_seconds: float | None = None
    minimum_decode_tokens_per_second: float | None = None

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class RecommendationRun:
    run_id: str
    schema_version: int
    workload: WorkloadProfile
    candidates: tuple[DeploymentCandidate, ...]
    categories: JsonDict
    evidence_boundary: str

    def to_dict(self) -> JsonDict:
        return {
            "run_id": self.run_id,
            "schema_version": self.schema_version,
            "workload": self.workload.to_dict(),
            "candidates": [item.to_dict() for item in self.candidates],
            "categories": dict(self.categories),
            "evidence_boundary": self.evidence_boundary,
        }


@dataclass(frozen=True)
class CompatibilityResult:
    adapter_id: str
    compatible: bool
    platform_supported: bool
    hardware_fit: bool
    installed: bool
    support_level: str
    score: float
    reasons: tuple[str, ...] = ()
    diagnostics: tuple[AdapterDiagnostic, ...] = ()

    def to_dict(self) -> JsonDict:
        payload = asdict(self)
        payload["diagnostics"] = [item.to_dict() for item in self.diagnostics]
        return payload


@dataclass(frozen=True)
class LaunchSpec:
    adapter_id: str
    command: tuple[str, ...]
    env: JsonDict
    host: str
    port: int
    api_base: str
    openai_base: str | None
    model_path: str
    configuration: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        payload = asdict(self)
        payload["command"] = list(self.command)
        return payload


@dataclass(frozen=True)
class ConversionPlan:
    converter_id: str
    source_artifact: ArtifactVariant
    target_format: str
    output_path: str
    command: tuple[str, ...]
    estimated_output_bytes: int | None
    requires_permission: bool = True
    destructive: bool = False
    diagnostics: tuple[AdapterDiagnostic, ...] = ()

    def to_dict(self) -> JsonDict:
        payload = asdict(self)
        payload["source_artifact"] = self.source_artifact.to_dict()
        payload["command"] = list(self.command)
        payload["diagnostics"] = [item.to_dict() for item in self.diagnostics]
        return payload


@dataclass(frozen=True)
class DeploymentCandidate:
    candidate_id: str
    model: ModelIdentity
    artifact: ArtifactVariant
    compatibility: CompatibilityResult
    workload: str
    scores: JsonDict
    confidence: float
    evidence: tuple[JsonDict, ...] = ()

    def to_dict(self) -> JsonDict:
        return {
            "candidate_id": self.candidate_id,
            "model": self.model.to_dict(),
            "artifact": self.artifact.to_dict(),
            "compatibility": self.compatibility.to_dict(),
            "workload": self.workload,
            "scores": dict(self.scores),
            "confidence": self.confidence,
            "evidence": [dict(item) for item in self.evidence],
        }


@runtime_checkable
class BackendAdapter(Protocol):
    name: str
    manifest: AdapterManifest

    def probe(self, *, search_root: str | None = None) -> JsonDict: ...
    def capabilities(self) -> JsonDict: ...
    def install_plan(self) -> JsonDict: ...
    def install(self, *, target_dir: str, variant: str = "auto", force: bool = False) -> JsonDict: ...
    def evaluate_fit(self, *, artifact: JsonDict, hardware: JsonDict, workload: str = "chat") -> JsonDict: ...
    def build_launch_spec(self, **kwargs: Any) -> JsonDict: ...
    def launch(self, launch_plan: JsonDict, *, log_path: str | None = None) -> JsonDict: ...
    def health(self, *, base_url: str, timeout_seconds: float = 2.0) -> JsonDict: ...
    def benchmark(self, *, base_url: str, prompt: str, max_tokens: int, timeout_seconds: float = 60.0) -> JsonDict: ...
    def tuning_space(self, *, launch_plan: JsonDict, hardware: JsonDict) -> list[JsonDict]: ...
    def stop(self, *, pid: int) -> JsonDict: ...
    def recover(self, launch_plan: JsonDict, *, log_path: str | None = None) -> JsonDict: ...


@runtime_checkable
class ArtifactAdapter(Protocol):
    adapter_id: str
    adapter_api_version: str

    def detect(self, source: JsonDict) -> bool: ...
    def inspect(self, source: JsonDict) -> list[ArtifactVariant]: ...
    def resolve_files(self, variant: ArtifactVariant) -> list[JsonDict]: ...
    def validate(self, variant: ArtifactVariant) -> JsonDict: ...
    def estimate_resources(self, variant: ArtifactVariant, hardware: JsonDict) -> JsonDict: ...
    def compatible_backends(self, variant: ArtifactVariant) -> tuple[str, ...]: ...


@runtime_checkable
class ConverterAdapter(Protocol):
    adapter_id: str
    manifest: AdapterManifest

    def can_convert(self, *, source: ArtifactVariant, target_format: str) -> CompatibilityResult: ...
    def plan_conversion(
        self,
        *,
        source: ArtifactVariant,
        target_format: str,
        output_path: str,
        options: JsonDict | None = None,
    ) -> ConversionPlan: ...
    def convert(self, plan: ConversionPlan) -> JsonDict: ...


__all__ = [
    "ADAPTER_API_VERSION",
    "AdapterDiagnostic",
    "AdapterManifest",
    "ArtifactAdapter",
    "ArtifactFile",
    "ArtifactVariant",
    "BackendAdapter",
    "BackendCapability",
    "CompatibilityResult",
    "ConversionPlan",
    "ConverterAdapter",
    "DeploymentCandidate",
    "JsonDict",
    "LaunchSpec",
    "ModelIdentity",
    "ModelRevision",
    "RecommendationRun",
    "WorkloadProfile",
]
