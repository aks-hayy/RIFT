"""Cryptographically signed, short-lived route grants."""

from __future__ import annotations

import base64
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@dataclass(frozen=True)
class RouteGrant:
    grant_id: str
    controller_id: str
    source_node_id: str
    service_id: str
    model_id: str | None
    primary_node_id: str
    fallback_node_ids: tuple[str, ...]
    inference_endpoint: str
    policy_hash: str
    issued_at: float
    expires_at: float
    nonce: str = ""

    def __post_init__(self) -> None:
        required = {
            "grant_id": self.grant_id,
            "controller_id": self.controller_id,
            "source_node_id": self.source_node_id,
            "service_id": self.service_id,
            "primary_node_id": self.primary_node_id,
            "inference_endpoint": self.inference_endpoint,
            "policy_hash": self.policy_hash,
        }
        if any(not str(value).strip() for value in required.values()):
            raise ValueError("route grant identity and endpoint fields are required")
        if not self.inference_endpoint.startswith("https://"):
            raise ValueError("route grant endpoint must use HTTPS")
        if self.expires_at <= self.issued_at:
            raise ValueError("route grant expiry must be after issue time")

    def payload(self) -> dict[str, object]:
        value = asdict(self)
        value["fallback_node_ids"] = list(self.fallback_node_ids)
        return value

    @classmethod
    def from_payload(cls, value: dict[str, object]) -> RouteGrant:
        return cls(
            grant_id=str(value["grant_id"]),
            controller_id=str(value["controller_id"]),
            source_node_id=str(value["source_node_id"]),
            service_id=str(value["service_id"]),
            model_id=(str(value["model_id"]) if value.get("model_id") else None),
            primary_node_id=str(value["primary_node_id"]),
            fallback_node_ids=tuple(str(item) for item in value.get("fallback_node_ids") or ()),
            inference_endpoint=str(value["inference_endpoint"]),
            policy_hash=str(value["policy_hash"]),
            issued_at=float(value["issued_at"]),
            expires_at=float(value["expires_at"]),
            nonce=str(value.get("nonce") or ""),
        )


class RouteGrantSigner:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_file():
            self._key = serialization.load_pem_private_key(self.path.read_bytes(), password=None)
            if not isinstance(self._key, ec.EllipticCurvePrivateKey):
                raise ValueError("route grant key is not an EC private key")
        else:
            self._key = ec.generate_private_key(ec.SECP256R1())
            self.path.write_bytes(
                self._key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
            try:
                self.path.chmod(0o600)
            except OSError:
                pass

    def public_key(self) -> bytes:
        return self._key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def issue(self, grant: RouteGrant) -> str:
        payload = grant.payload()
        payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        signature = self._key.sign(payload_bytes, ec.ECDSA(hashes.SHA256()))
        envelope = {"v": 1, "payload": payload, "signature": _b64(signature)}
        return _b64(json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode("utf-8"))


class RouteGrantVerifier:
    def __init__(self, public_key_pem: bytes):
        key = serialization.load_pem_public_key(public_key_pem)
        if not isinstance(key, ec.EllipticCurvePublicKey):
            raise ValueError("route grant key is not an EC public key")  # noqa: TRY004 - preserve verifier API
        self._key = key

    def verify(self, token: str, *, now: float) -> RouteGrant:
        try:
            envelope = json.loads(_unb64(token).decode("utf-8"))
            if envelope.get("v") != 1:
                raise ValueError("unsupported route grant version")
            payload = envelope["payload"]
            signature = _unb64(str(envelope["signature"]))
            payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
            self._key.verify(signature, payload_bytes, ec.ECDSA(hashes.SHA256()))
            grant = RouteGrant.from_payload(payload)
        except Exception as exc:
            raise ValueError("route grant signature is invalid") from exc
        if float(now) >= grant.expires_at:
            raise TimeoutError("route grant is expired")
        if float(now) + 300 < grant.issued_at:
            raise ValueError("route grant is not yet valid")
        return grant


__all__ = ["RouteGrant", "RouteGrantSigner", "RouteGrantVerifier"]
