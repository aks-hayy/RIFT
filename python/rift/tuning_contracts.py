"""Versioned backend-neutral contracts shared by API, CLI, and evidence.

The coordinator still accepts legacy dictionaries at its boundary. These
records provide a stable typed interchange for new clients and the future
workload controller without changing serving adapter ownership.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from typing import Any, Mapping


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str).encode()).hexdigest()


@dataclass(frozen=True)
class DeploymentIdentity:
    model_revision: str
    artifact_hash: str
    tokenizer: str
    chat_template: str
    backend: str
    backend_build: str
    runtime: str
    precision: str
    devices: tuple[str, ...] = ()
    schema_version: int = 1

    def __post_init__(self):
        if self.schema_version != 1 or not self.model_revision or not self.artifact_hash or not self.backend:
            raise ValueError("deployment identity is incomplete")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"devices": list(self.devices)}

    @property
    def identity_hash(self) -> str:
        return _hash(self.to_dict())


@dataclass(frozen=True)
class AcceptanceSpec:
    suite_id: str
    suite_version: str
    minimum_score: float
    required_cases: tuple[str, ...] = ()
    max_ttft_ms: float | None = None
    min_decode_tps: float | None = None
    schema_version: int = 1

    def __post_init__(self):
        if not self.suite_id or not self.suite_version or not 0 <= self.minimum_score <= 1:
            raise ValueError("acceptance requires a versioned suite and score in [0, 1]")
        for value in (self.max_ttft_ms, self.min_decode_tps):
            if value is not None and value <= 0:
                raise ValueError("acceptance thresholds must be positive")


@dataclass(frozen=True)
class TuningRequest:
    service: str
    profile: str
    usage: str
    acceptance: AcceptanceSpec
    candidate_limit: int = 24
    budget_seconds: float | None = None
    kv_precision_search: bool = True
    parent_run_id: str | None = None
    contract_hash: str | None = None
    schema_version: int = 1

    def __post_init__(self):
        if self.profile not in {"speed", "cost"} or self.usage not in {"interactive", "shared"}:
            raise ValueError("unsupported tuning profile or usage")
        if self.candidate_limit < 1 or (self.budget_seconds is not None and self.budget_seconds <= 0):
            raise ValueError("candidate_limit and budget_seconds must be positive")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def request_hash(self) -> str:
        return _hash(self.to_dict())


@dataclass(frozen=True)
class TuningCapabilities:
    backend: str
    supported_profiles: tuple[str, ...]
    parameters: tuple[Mapping[str, Any], ...]
    measurement_availability: Mapping[str, Any]
    qualification: str
    schema_version: int = 1

    def __post_init__(self):
        if not self.backend or any(profile not in {"speed", "cost"} for profile in self.supported_profiles):
            raise ValueError("invalid tuning capability contract")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"supported_profiles": list(self.supported_profiles), "parameters": [dict(item) for item in self.parameters]}


@dataclass(frozen=True)
class CandidateConfiguration:
    identity: DeploymentIdentity
    effective_settings: Mapping[str, Any]
    delta_from_baseline: Mapping[str, Any] = field(default_factory=dict)
    proposal_reason: str = ""
    schema_version: int = 1

    @property
    def configuration_hash(self) -> str:
        return _hash({"identity": self.identity.to_dict(), "settings": dict(self.effective_settings)})


@dataclass(frozen=True)
class MeasurementRecord:
    metric: str
    value: float | None
    unit: str
    source: str
    observed_at: str
    scope: str
    uncertainty: Mapping[str, Any] = field(default_factory=dict)
    exclusions: tuple[str, ...] = ()
    schema_version: int = 1

    def __post_init__(self):
        if not self.metric or not self.unit or not self.source or not self.scope:
            raise ValueError("measurement provenance is required")
        if self.value is not None and (isinstance(self.value, bool) or not isinstance(self.value, (int, float))):
            raise ValueError("measurement value must be numeric or null")


@dataclass(frozen=True)
class EvidenceReport:
    run_id: str
    requirements: tuple[Mapping[str, Any], ...]
    baseline: Mapping[str, Any]
    winner: Mapping[str, Any] | None
    provenance: Mapping[str, Any]
    limitations: tuple[str, ...] = ()
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def report_hash(self) -> str:
        return _hash(self.to_dict())


__all__ = ["AcceptanceSpec", "CandidateConfiguration", "DeploymentIdentity", "EvidenceReport", "MeasurementRecord", "TuningCapabilities", "TuningRequest"]
