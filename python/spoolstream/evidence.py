"""Evidence levels and recommendation provenance for RIFT."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import base64
from enum import Enum
import json
import math
from pathlib import Path
import time
from typing import Any


JsonDict = dict[str, Any]


class EvidenceLevel(str, Enum):
    VERIFIED_LOCAL = "VERIFIED_LOCAL"
    REPRODUCIBLE_BENCHMARK = "REPRODUCIBLE_BENCHMARK"
    CURATED_EVALUATION = "CURATED_EVALUATION"
    PUBLISHER_DECLARED = "PUBLISHER_DECLARED"
    HUB_METADATA = "HUB_METADATA"
    ESTIMATED = "ESTIMATED"
    UNKNOWN = "UNKNOWN"


_LEVEL_WEIGHT = {
    EvidenceLevel.VERIFIED_LOCAL: 1.0,
    EvidenceLevel.REPRODUCIBLE_BENCHMARK: 0.9,
    EvidenceLevel.CURATED_EVALUATION: 0.78,
    EvidenceLevel.PUBLISHER_DECLARED: 0.55,
    EvidenceLevel.HUB_METADATA: 0.4,
    EvidenceLevel.ESTIMATED: 0.25,
    EvidenceLevel.UNKNOWN: 0.0,
}


@dataclass(frozen=True)
class EvidenceRecord:
    level: EvidenceLevel
    subject: str
    claim: str
    source: str
    metric: str | None = None
    value: Any = None
    collected_unix_seconds: float | None = None
    reproducible: bool = False
    benchmark: str | None = None
    task: str | None = None
    normalized_value: float | None = None
    observed_unix_seconds: float | None = None
    model_revision: str | None = None
    artifact_id: str | None = None
    backend: str | None = None
    hardware_fingerprint: str | None = None
    relation: str = "unknown"
    confidence: float = 0.0
    provenance: str = "unknown"

    def to_dict(self) -> JsonDict:
        payload = asdict(self)
        payload["level"] = self.level.value
        return payload

    @classmethod
    def from_dict(cls, payload: JsonDict) -> "EvidenceRecord":
        if not isinstance(payload, dict):
            raise ValueError("evidence record must be an object")
        level = payload.get("level", EvidenceLevel.UNKNOWN)
        try:
            level = level if isinstance(level, EvidenceLevel) else EvidenceLevel(str(level))
        except ValueError as exc:
            raise ValueError(f"unknown evidence level: {level}") from exc
        return cls(
            level=level,
            subject=str(payload.get("subject") or ""),
            claim=str(payload.get("claim") or ""),
            source=str(payload.get("source") or ""),
            metric=payload.get("metric"),
            value=payload.get("value"),
            collected_unix_seconds=_optional_float(payload.get("collected_unix_seconds")),
            reproducible=bool(payload.get("reproducible", False)),
            benchmark=payload.get("benchmark"),
            task=payload.get("task"),
            normalized_value=_optional_float(payload.get("normalized_value")),
            observed_unix_seconds=_optional_float(
                payload.get("observed_unix_seconds", payload.get("collected_unix_seconds"))
            ),
            model_revision=payload.get("model_revision"),
            artifact_id=payload.get("artifact_id"),
            backend=payload.get("backend"),
            hardware_fingerprint=payload.get("hardware_fingerprint"),
            relation=str(payload.get("relation") or "unknown"),
            confidence=_bounded_float(payload.get("confidence", 0.0)),
            provenance=str(payload.get("provenance") or "unknown"),
        )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("evidence numeric values cannot be boolean")
    try:
        converted = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"evidence numeric value is invalid: {value!r}") from exc
    if not math.isfinite(converted):
        raise ValueError("evidence numeric values must be finite")
    return converted


def _bounded_float(value: Any) -> float:
    converted = _optional_float(value)
    return 0.0 if converted is None else max(0.0, min(1.0, converted))


def aggregate_quality_evidence(
    records: list[EvidenceRecord],
    task: str,
    *,
    now: float | None = None,
) -> JsonDict:
    """Aggregate comparable evidence without conflating unrelated benchmarks.

    Values must already be normalized by the provider within their benchmark family.
    The raw records remain in the assessment response for auditability.
    """

    current = time.time() if now is None else now
    comparable: list[tuple[EvidenceRecord, float]] = []
    relation_weight = {"direct": 1.0, "variant": 0.85, "lineage": 0.65, "inherited": 0.35}
    level_weight = {
        EvidenceLevel.VERIFIED_LOCAL: 1.0,
        EvidenceLevel.REPRODUCIBLE_BENCHMARK: 0.9,
        EvidenceLevel.CURATED_EVALUATION: 0.78,
        EvidenceLevel.PUBLISHER_DECLARED: 0.55,
        EvidenceLevel.HUB_METADATA: 0.4,
        EvidenceLevel.ESTIMATED: 0.25,
        EvidenceLevel.UNKNOWN: 0.0,
    }
    for record in records:
        if record.task not in (None, task) or record.normalized_value is None:
            continue
        if not record.benchmark or not record.metric:
            continue
        value = _bounded_float(record.normalized_value)
        relation = relation_weight.get(record.relation.lower(), 0.0)
        provenance_weight = level_weight.get(record.level, 0.0)
        timestamp = record.observed_unix_seconds or record.collected_unix_seconds
        age_days = max(0.0, (current - timestamp) / 86400.0) if timestamp else 365.0
        age_decay = 0.5 ** (age_days / 365.0)
        weight = relation * provenance_weight * max(0.0, min(1.0, record.confidence or 1.0)) * age_decay
        if weight > 0.0:
            comparable.append((record, weight))

    published = [record for record, _ in comparable if record.level not in (EvidenceLevel.VERIFIED_LOCAL, EvidenceLevel.REPRODUCIBLE_BENCHMARK)]
    local = [record for record, _ in comparable if record.level in (EvidenceLevel.VERIFIED_LOCAL, EvidenceLevel.REPRODUCIBLE_BENCHMARK)]
    if not comparable:
        return {
            "score": None,
            "coverage": 0,
            "freshness": "unknown",
            "confidence": 0.0,
            "published_records": 0,
            "local_records": 0,
            "claim_boundary": "metadata_or_estimate_only",
            "benchmarks": [],
        }

    total_weight = sum(weight for _, weight in comparable)
    score = sum(record.normalized_value * weight for record, weight in comparable) / total_weight
    timestamps = [record.observed_unix_seconds or record.collected_unix_seconds for record, _ in comparable]
    valid_timestamps = [item for item in timestamps if item]
    newest_age_days = (current - max(valid_timestamps)) / 86400.0 if valid_timestamps else None
    freshness = "unknown" if newest_age_days is None else "fresh" if newest_age_days <= 90 else "stale"
    coverage = len({record.benchmark for record, _ in comparable})
    confidence = min(1.0, (total_weight / max(1.0, len(comparable))) + min(0.2, coverage * 0.05))
    return {
        "score": round(max(0.0, min(1.0, score)), 6),
        "coverage": coverage,
        "freshness": freshness,
        "confidence": round(confidence, 6),
        "published_records": len(published),
        "local_records": len(local),
        "claim_boundary": "local_measurement" if local and not published else "published_quality_evidence",
        "benchmarks": sorted({str(record.benchmark) for record, _ in comparable}),
    }


class EvidenceEngine:
    """Combines curated, local, and metadata evidence without flattening provenance."""

    def __init__(
        self,
        root: str | Path | None = None,
        *,
        data_root: str | Path | None = None,
    ) -> None:
        self.root = Path(root) if root else Path.cwd()
        self.evidence_dir = (
            Path(data_root) if data_root is not None else self.root / ".rift"
        ) / "evidence"
        self.registry_path = self.evidence_dir / "registry.json"
        self.feed_path = self.evidence_dir / "intelligence-feed.json"
        self.trusted_keys_path = self.evidence_dir / "trusted-keys.json"
        self.local_path = self.evidence_dir / "local.jsonl"

    def assess_candidate(
        self,
        candidate: JsonDict,
        *,
        task: str = "chat",
        external_records: list[EvidenceRecord] | None = None,
    ) -> JsonDict:
        repo_id = str(candidate.get("repo_id") or candidate.get("id") or "unknown")
        records: list[EvidenceRecord] = []
        registry_records, feed_status = self._registry_records(repo_id, task)
        records.extend(registry_records)
        records.extend(self._local_records(repo_id, task))
        records.extend(
            record
            for record in (external_records or [])
            if record.subject == repo_id and record.task in (None, task)
        )

        eval_payload = candidate.get("evaluation_evidence") or candidate.get("eval_results")
        if eval_payload:
            records.append(
                EvidenceRecord(
                    level=EvidenceLevel.PUBLISHER_DECLARED,
                    subject=repo_id,
                    claim="Repository exposes structured evaluation metadata.",
                    source="huggingface_model_card",
                    metric="structured_eval_metadata",
                    value=eval_payload,
                )
            )
        if candidate.get("likes") is not None or candidate.get("downloads") is not None:
            records.append(
                EvidenceRecord(
                    level=EvidenceLevel.HUB_METADATA,
                    subject=repo_id,
                    claim="Community activity is available as a popularity signal, not an accuracy result.",
                    source="huggingface_hub",
                    metric="community_activity",
                    value={"likes": candidate.get("likes"), "downloads": candidate.get("downloads")},
                )
            )
        if not records:
            records.append(
                EvidenceRecord(
                    level=EvidenceLevel.UNKNOWN,
                    subject=repo_id,
                    claim="No quality evidence beyond unstructured model metadata was found.",
                    source="rift",
                )
            )

        quality_evidence = aggregate_quality_evidence(records, task)

        best = max(records, key=lambda record: _LEVEL_WEIGHT[record.level])
        independent_sources = len({record.source for record in records if record.source})
        reproducible = sum(1 for record in records if record.reproducible)
        confidence = min(
            1.0,
            _LEVEL_WEIGHT[best.level]
            + min(0.12, max(0, independent_sources - 1) * 0.04)
            + min(0.10, reproducible * 0.05),
        )
        return {
            "subject": repo_id,
            "task": task,
            "highest_level": best.level.value,
            "confidence": round(confidence, 6),
            "independent_source_count": independent_sources,
            "records": [record.to_dict() for record in records],
            "quality_evidence": quality_evidence,
            "intelligence_feed": feed_status,
            "claim_boundary": (
                "RIFT may rank this candidate using the listed signals, but only VERIFIED_LOCAL or "
                "REPRODUCIBLE_BENCHMARK evidence supports a measured performance claim."
            ),
        }

    def record_local_result(
        self,
        *,
        repo_id: str,
        task: str,
        metrics: JsonDict,
        artifact: str | None = None,
        backend: str | None = None,
        model_revision: str | None = None,
        hardware_fingerprint: str | None = None,
    ) -> JsonDict:
        if not repo_id.strip():
            raise ValueError("repo_id is required")
        record = EvidenceRecord(
            level=EvidenceLevel.VERIFIED_LOCAL,
            subject=repo_id,
            claim="RIFT completed a local measured benchmark for this artifact/backend combination.",
            source="rift_local_benchmark",
            metric=task,
            value={"metrics": metrics, "artifact": artifact, "backend": backend},
            collected_unix_seconds=time.time(),
            reproducible=True,
            benchmark="rift_local_benchmark",
            task=task,
            model_revision=model_revision,
            artifact_id=artifact,
            backend=backend,
            hardware_fingerprint=hardware_fingerprint,
            relation="direct",
            confidence=1.0,
            provenance="measured_local",
        ).to_dict()
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        with self.local_path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(record, sort_keys=True) + "\n")
        return record

    def _registry_records(self, repo_id: str, task: str) -> tuple[list[EvidenceRecord], JsonDict]:
        source_path = self.feed_path if self.feed_path.is_file() else self.registry_path
        if not source_path.is_file():
            return [], {"available": False, "verified": False, "reason": "no curated feed is installed"}
        try:
            envelope = json.loads(source_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return [], {"available": True, "verified": False, "reason": "curated feed is unreadable"}
        payload, status = self._verified_feed_payload(envelope, source_path)
        if payload is None:
            return [], status
        entries = payload.get("models", {}) if isinstance(payload, dict) else {}
        model = entries.get(repo_id, {}) if isinstance(entries, dict) else {}
        records = []
        for item in model.get("evidence", []) if isinstance(model, dict) else []:
            if not isinstance(item, dict) or item.get("task") not in (None, task):
                continue
            records.append(
                EvidenceRecord(
                    level=EvidenceLevel.CURATED_EVALUATION,
                    subject=repo_id,
                    claim=str(item.get("claim") or "Curated evaluation result."),
                    source=str(item.get("source") or "rift_curated_registry"),
                    metric=item.get("metric"),
                    value=item.get("value"),
                    collected_unix_seconds=item.get("collected_unix_seconds"),
                    reproducible=bool(item.get("reproducible", False)),
                    benchmark=item.get("benchmark") or item.get("metric"),
                    task=item.get("task") or task,
                    normalized_value=_optional_float(item.get("normalized_value")),
                    observed_unix_seconds=_optional_float(
                        item.get("observed_unix_seconds", item.get("collected_unix_seconds"))
                    ),
                    model_revision=item.get("model_revision"),
                    artifact_id=item.get("artifact_id"),
                    backend=item.get("backend"),
                    hardware_fingerprint=item.get("hardware_fingerprint"),
                    relation=str(item.get("relation") or "unknown"),
                    confidence=_bounded_float(item.get("confidence", 0.0)),
                    provenance=str(item.get("provenance") or "curated"),
                )
            )
        return records, status

    def _verified_feed_payload(
        self,
        envelope: JsonDict,
        source_path: Path,
    ) -> tuple[JsonDict | None, JsonDict]:
        if "payload" not in envelope or "signature" not in envelope:
            return None, {
                "available": True,
                "verified": False,
                "path": str(source_path),
                "reason": "unsigned curated data is not used as trusted recommendation evidence",
            }
        signature = envelope.get("signature") if isinstance(envelope.get("signature"), dict) else {}
        algorithm = str(signature.get("algorithm") or "").lower()
        key_id = str(signature.get("key_id") or "")
        if algorithm != "ed25519" or not key_id:
            return None, {
                "available": True,
                "verified": False,
                "path": str(source_path),
                "reason": "feed must use an Ed25519 signature and trusted key id",
            }
        trusted = self._trusted_keys()
        public_key = trusted.get(key_id)
        if not public_key:
            return None, {
                "available": True,
                "verified": False,
                "path": str(source_path),
                "key_id": key_id,
                "reason": "feed signing key is not trusted locally",
            }
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

            canonical = json.dumps(
                envelope["payload"], separators=(",", ":"), sort_keys=True
            ).encode("utf-8")
            Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key)).verify(
                base64.b64decode(str(signature.get("value") or "")), canonical
            )
        except ImportError:
            return None, {
                "available": True,
                "verified": False,
                "path": str(source_path),
                "key_id": key_id,
                "reason": "cryptography is not installed; signed feed verification is fail-closed",
            }
        except Exception as exc:
            return None, {
                "available": True,
                "verified": False,
                "path": str(source_path),
                "key_id": key_id,
                "reason": f"signature verification failed: {exc}",
            }
        payload = envelope.get("payload")
        if not isinstance(payload, dict):
            return None, {
                "available": True,
                "verified": False,
                "path": str(source_path),
                "reason": "verified feed payload is not an object",
            }
        return payload, {
            "available": True,
            "verified": True,
            "path": str(source_path),
            "key_id": key_id,
            "algorithm": algorithm,
        }

    def _trusted_keys(self) -> dict[str, str]:
        if not self.trusted_keys_path.is_file():
            return {}
        try:
            payload = json.loads(self.trusted_keys_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        keys = payload.get("keys") if isinstance(payload, dict) else None
        return {
            str(item.get("id")): str(item.get("public_key"))
            for item in (keys or [])
            if isinstance(item, dict) and item.get("id") and item.get("public_key")
        }

    def _local_records(self, repo_id: str, task: str) -> list[EvidenceRecord]:
        if not self.local_path.is_file():
            return []
        records = []
        try:
            lines = self.local_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        for line in lines[-500:]:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if item.get("subject") != repo_id or item.get("metric") != task:
                continue
            records.append(
                EvidenceRecord(
                    level=EvidenceLevel.VERIFIED_LOCAL,
                    subject=repo_id,
                    claim=str(item.get("claim") or "Locally verified result."),
                    source=str(item.get("source") or "rift_local_benchmark"),
                    metric=task,
                    value=item.get("value"),
                    collected_unix_seconds=item.get("collected_unix_seconds"),
                    reproducible=True,
                    benchmark=item.get("benchmark") or "rift_local_benchmark",
                    task=item.get("task") or task,
                    normalized_value=_optional_float(item.get("normalized_value")),
                    observed_unix_seconds=_optional_float(
                        item.get("observed_unix_seconds", item.get("collected_unix_seconds"))
                    ),
                    model_revision=item.get("model_revision"),
                    artifact_id=item.get("artifact_id"),
                    backend=item.get("backend"),
                    hardware_fingerprint=item.get("hardware_fingerprint"),
                    relation=str(item.get("relation") or "direct"),
                    confidence=_bounded_float(item.get("confidence", 1.0)),
                    provenance=str(item.get("provenance") or "measured_local"),
                )
            )
        return records


__all__ = [
    "EvidenceEngine",
    "EvidenceLevel",
    "EvidenceRecord",
    "aggregate_quality_evidence",
]
