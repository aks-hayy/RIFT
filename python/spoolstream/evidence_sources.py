"""Permissioned external benchmark evidence sources for RIFT."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Protocol
from urllib.request import urlopen

from .evidence import EvidenceLevel, EvidenceRecord


JsonDict = dict[str, Any]


class BenchmarkEvidenceSource(Protocol):
    source_id: str

    def load(self) -> list[EvidenceRecord]: ...

    def diagnostics(self) -> JsonDict: ...


@dataclass
class JsonEvidenceSource:
    """Load a signed, explicitly permitted JSON evidence snapshot.

    Remote URLs are disabled by default. Unsigned snapshots are always rejected
    so a local cache cannot silently become a trusted leaderboard source.
    """

    path_or_url: str | Path
    source_id: str
    trusted_keys_path: str | Path | None = None
    allow_remote: bool = False

    def __post_init__(self) -> None:
        self._status: JsonDict = {
            "source_id": self.source_id,
            "available": False,
            "verified": False,
        }

    def load(self) -> list[EvidenceRecord]:
        try:
            envelope = self._read()
        except (OSError, ValueError) as exc:
            self._status.update({"available": True, "reason": str(exc)})
            return []
        payload = envelope.get("payload") if isinstance(envelope, dict) else None
        if not isinstance(payload, dict):
            self._status.update({"available": True, "reason": "snapshot payload is not an object"})
            return []
        if str(payload.get("source_id") or self.source_id) != self.source_id:
            self._status.update({"available": True, "reason": "snapshot source_id does not match provider"})
            return []
        status = self._verify(envelope)
        self._status.update(status)
        if not status.get("verified"):
            return []
        try:
            records = [self._record(item, payload) for item in payload.get("records", [])]
        except (TypeError, ValueError) as exc:
            self._status.update({"verified": False, "reason": str(exc)})
            return []
        self._status["record_count"] = len(records)
        return records

    def diagnostics(self) -> JsonDict:
        return dict(self._status)

    def _read(self) -> JsonDict:
        value = str(self.path_or_url)
        if value.startswith(("http://", "https://")):
            if not self.allow_remote:
                raise ValueError("remote evidence loading is disabled; pass allow_remote=True explicitly")
            with urlopen(value, timeout=10) as response:
                body = response.read()
        else:
            body = Path(value).read_bytes()
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("evidence snapshot must be a JSON object")
        return payload

    def _verify(self, envelope: JsonDict) -> JsonDict:
        signature = envelope.get("signature")
        if not isinstance(signature, dict):
            return {"available": True, "verified": False, "reason": "unsigned snapshot is rejected"}
        if str(signature.get("algorithm") or "").lower() != "ed25519":
            return {"available": True, "verified": False, "reason": "snapshot must use Ed25519"}
        key_id = str(signature.get("key_id") or "")
        trusted = self._trusted_keys()
        public_key = trusted.get(key_id)
        if not public_key:
            return {"available": True, "verified": False, "reason": "snapshot signing key is not trusted"}
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

            canonical = json.dumps(
                envelope["payload"], separators=(",", ":"), sort_keys=True
            ).encode("utf-8")
            Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key)).verify(
                base64.b64decode(str(signature.get("value") or "")), canonical
            )
        except ImportError:
            return {"available": True, "verified": False, "reason": "cryptography is not installed"}
        except Exception as exc:
            return {"available": True, "verified": False, "reason": f"signature verification failed: {exc}"}
        return {
            "available": True,
            "verified": True,
            "key_id": key_id,
            "algorithm": "ed25519",
        }

    def _trusted_keys(self) -> dict[str, str]:
        if not self.trusted_keys_path:
            return {}
        try:
            payload = json.loads(Path(self.trusted_keys_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return {
            str(item.get("id")): str(item.get("public_key"))
            for item in (payload.get("keys") or [])
            if isinstance(item, dict) and item.get("id") and item.get("public_key")
        }

    def _record(self, item: Any, payload: JsonDict) -> EvidenceRecord:
        if not isinstance(item, dict):
            raise ValueError("evidence record must be an object")
        subject = str(item.get("subject") or "")
        benchmark = str(item.get("benchmark") or "")
        task = str(item.get("task") or "")
        metric = str(item.get("metric") or "")
        if not subject or not benchmark or not task or not metric:
            raise ValueError("evidence record requires subject, benchmark, task, and metric")
        normalized = item.get("normalized_value")
        if isinstance(normalized, bool) or not isinstance(normalized, (int, float)):
            raise ValueError("evidence normalized_value must be numeric")
        if not 0.0 <= float(normalized) <= 1.0:
            raise ValueError("evidence normalized_value must be between 0 and 1")
        observed = item.get("observed_unix_seconds", payload.get("observed_unix_seconds"))
        if isinstance(observed, bool) or not isinstance(observed, (int, float)):
            raise ValueError("evidence observed_unix_seconds must be numeric")
        return EvidenceRecord(
            level=EvidenceLevel.CURATED_EVALUATION,
            subject=subject,
            claim=str(item.get("claim") or "Published benchmark evidence."),
            source=str(item.get("source") or self.source_id),
            metric=metric,
            value=item.get("value", normalized),
            collected_unix_seconds=float(observed),
            reproducible=bool(item.get("reproducible", False)),
            benchmark=benchmark,
            task=task,
            normalized_value=float(normalized),
            observed_unix_seconds=float(observed),
            model_revision=item.get("model_revision"),
            artifact_id=item.get("artifact_id"),
            backend=item.get("backend"),
            hardware_fingerprint=item.get("hardware_fingerprint"),
            relation=str(item.get("relation") or "direct"),
            confidence=max(0.0, min(1.0, float(item.get("confidence", 1.0)))),
            provenance=str(item.get("provenance") or "published"),
        )


__all__ = ["BenchmarkEvidenceSource", "JsonEvidenceSource"]
