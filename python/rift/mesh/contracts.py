"""Versioned, transport-neutral records shared by every RIFT mesh node."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
from typing import Any


JsonDict = dict[str, Any]


class TrustState(str, Enum):
    DISCOVERED_UNTRUSTED = "DISCOVERED_UNTRUSTED"
    PAIRING_PENDING = "PAIRING_PENDING"
    ENROLLED = "ENROLLED"
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


class PrivacyPolicy(str, Enum):
    LOCAL_ONLY = "LOCAL_ONLY"
    MESH_ALLOWED = "MESH_ALLOWED"


@dataclass(frozen=True)
class NodeSighting:
    sighting_id: str
    provider: str
    endpoint: str
    node_hint: str
    api_version: str
    bootstrap_fingerprint: str
    observed_at: float
    expires_at: float
    interface_id: str = ""
    trust_state: TrustState = TrustState.DISCOVERED_UNTRUSTED
    metadata: JsonDict = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        provider: str,
        endpoint: str,
        node_hint: str,
        api_version: str,
        bootstrap_fingerprint: str,
        ttl_seconds: float,
        observed_at: float,
        interface_id: str = "",
        metadata: JsonDict | None = None,
    ) -> "NodeSighting":
        if not provider.strip():
            raise ValueError("discovery provider is required")
        if not endpoint.startswith("https://"):
            raise ValueError("bootstrap endpoint must use https://")
        if ttl_seconds <= 0:
            raise ValueError("sighting TTL must be positive")
        if not bootstrap_fingerprint.strip():
            raise ValueError("bootstrap fingerprint is required")
        identity = "\0".join((provider, endpoint, node_hint, bootstrap_fingerprint))
        return cls(
            sighting_id=hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24],
            provider=provider,
            endpoint=endpoint,
            node_hint=node_hint,
            api_version=api_version,
            bootstrap_fingerprint=bootstrap_fingerprint,
            observed_at=float(observed_at),
            expires_at=float(observed_at) + float(ttl_seconds),
            interface_id=interface_id,
            metadata=dict(metadata or {}),
        )

    def is_expired(self, now: float) -> bool:
        return float(now) >= self.expires_at

    def to_dict(self) -> JsonDict:
        result = dict(self.__dict__)
        result["trust_state"] = self.trust_state.value
        return result


@dataclass(frozen=True)
class RuntimeOffer:
    offer_id: str
    task: str
    model_id: str
    backend: str
    context_tokens: int
    quality_score: float
    first_token_ms: float
    decode_tokens_per_second: float
    local_only: bool = False


@dataclass
class TrustedNode:
    node_id: str
    hostname: str
    trust_state: TrustState = TrustState.ACTIVE
    healthy: bool = True
    queue_depth: int = 0
    labels: dict[str, str] = field(default_factory=dict)
    offers: list[RuntimeOffer] = field(default_factory=list)


@dataclass(frozen=True)
class CapabilitySnapshot:
    node_id: str
    sequence: int
    observed_at: float
    hardware: JsonDict
    runtime_offers: tuple[RuntimeOffer, ...]
    power: JsonDict = field(default_factory=dict)
    pressure: JsonDict = field(default_factory=dict)
    evidence: str = "EMULATED"


@dataclass(frozen=True)
class LinkMeasurement:
    source_node_id: str
    target_node_id: str
    rtt_p50_ms: float
    rtt_p95_ms: float
    jitter_ms: float
    loss_ratio: float
    upload_mbps: float
    download_mbps: float
    observed_at: float
    evidence: str


@dataclass
class MeshGraph:
    nodes: dict[str, TrustedNode]
    links: dict[tuple[str, str], LinkMeasurement]
    evidence: str = "EMULATED"

    def link(self, source: str, target: str) -> LinkMeasurement | None:
        if source == target:
            return LinkMeasurement(source, target, 0.0, 0.0, 0.0, 0.0, 1e9, 1e9, 0.0, self.evidence)
        return self.links.get((source, target))


@dataclass(frozen=True)
class InferenceIntent:
    source_node_id: str
    task: str
    minimum_context_tokens: int
    privacy: PrivacyPolicy = PrivacyPolicy.MESH_ALLOWED
    minimum_quality_score: float = 0.0


@dataclass(frozen=True)
class RouteCandidate:
    node_id: str
    offer_id: str
    execution_mode: str
    score: float
    predicted_first_token_ms: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RouteDecision:
    selected: RouteCandidate
    fallbacks: tuple[RouteCandidate, ...]
    rejected: tuple[JsonDict, ...]
    evidence: str

