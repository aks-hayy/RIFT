"""Managed node identity, configuration, and enrollment cryptography."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from pathlib import Path
import platform
import secrets
import uuid
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


JsonDict = dict[str, Any]


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid encoded enrollment payload") from exc


def _atomic_json(path: Path, payload: JsonDict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    pending.replace(path)
    if os.name != "nt":
        path.chmod(0o600)


def _atomic_text(path: Path, content: str, *, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(content, encoding="utf-8")
    pending.replace(path)
    if private and os.name != "nt":
        path.chmod(0o600)


def _atomic_bytes(path: Path, content: bytes, *, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_bytes(content)
    pending.replace(path)
    if private and os.name != "nt":
        path.chmod(0o600)


@dataclass(frozen=True)
class ManagedNodeIdentity:
    node_id: str
    display_name: str
    host: str
    port: int
    identity_path: Path
    config_path: Path


class ManagedNodeStore:
    """Own node bootstrap state under the platform RIFT runtime directory."""

    def __init__(self, root: str | Path, *, checkout_root: str | Path | None = None) -> None:
        self.root = Path(root).expanduser().resolve()
        self.checkout_root = None if checkout_root is None else Path(checkout_root).expanduser().resolve()
        if self.checkout_root is not None and self.root == self.checkout_root / ".rift":
            raise ValueError("managed node state must not use checkout-local .rift")
        self.node_dir = self.root / "node"
        self.identity_path = self.node_dir / "identity.json"
        self.config_path = self.node_dir / "config.yaml"
        self.enrollment_path = self.node_dir / "enrollment.json"
        self.credentials_path = self.node_dir / "credentials.json"

    def ensure_identity(
        self,
        *,
        display_name: str | None = None,
        host: str = "0.0.0.0",
        port: int = 11750,
    ) -> ManagedNodeIdentity:
        if not 1 <= int(port) <= 65535:
            raise ValueError("node agent port must be between 1 and 65535")
        existing = self._read_identity()
        if existing is not None:
            return existing

        resolved_name = (display_name or platform.node() or "rift-node").strip()
        if not resolved_name:
            resolved_name = "rift-node"
        identity = {
            "schema_version": 1,
            "node_id": f"node-{uuid.uuid4().hex}",
            "display_name": resolved_name,
            "created_at": __import__("time").time(),
        }
        self.node_dir.mkdir(parents=True, exist_ok=True)
        _atomic_json(self.identity_path, identity)
        self.write_config(
            {
                "version": 1,
                "managed": True,
                "node_id": identity["node_id"],
                "display_name": resolved_name,
                "host": host,
                "port": int(port),
                "controller": {},
                "tls": {
                    "certificate": str(self.node_dir / "tls" / "node.crt.pem"),
                    "private_key": str(self.node_dir / "tls" / "node.key.pem"),
                    "client_ca": str(self.node_dir / "tls" / "controller-ca.crt.pem"),
                    "minimum_version": "TLSv1.2",
                    "client_certificate_required": True,
                },
                "permissions": {
                    "allow_download": False,
                    "allow_install": False,
                    "allow_launch": False,
                    "allow_inference": False,
                },
            }
        )
        return ManagedNodeIdentity(
            node_id=str(identity["node_id"]),
            display_name=resolved_name,
            host=host,
            port=int(port),
            identity_path=self.identity_path,
            config_path=self.config_path,
        )

    def _read_identity(self) -> ManagedNodeIdentity | None:
        if not self.identity_path.is_file():
            return None
        try:
            payload = json.loads(self.identity_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"managed node identity is unreadable: {self.identity_path}") from exc
        node_id = str(payload.get("node_id") or "").strip()
        if not node_id:
            raise RuntimeError(f"managed node identity has no node_id: {self.identity_path}")
        config = self.read_config()
        return ManagedNodeIdentity(
            node_id=node_id,
            display_name=str(payload.get("display_name") or "rift-node"),
            host=str(config.get("host") or "0.0.0.0"),
            port=int(config.get("port") or 11750),
            identity_path=self.identity_path,
            config_path=self.config_path,
        )

    def read_config(self) -> JsonDict:
        if not self.config_path.is_file():
            return {}
        from .rift_yaml import read_yaml

        payload = read_yaml(self.config_path)
        if not isinstance(payload, dict):
            raise RuntimeError(f"managed node config is not an object: {self.config_path}")
        return dict(payload)

    def write_config(self, payload: JsonDict) -> None:
        import yaml

        _atomic_text(
            self.config_path,
            yaml.safe_dump(payload, sort_keys=False, default_flow_style=False),
            private=True,
        )

    def update_config(self, updates: JsonDict) -> JsonDict:
        config = self.read_config()
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(config.get(key), dict):
                config[key] = {**dict(config[key]), **value}
            else:
                config[key] = value
        self.write_config(config)
        return config

    def update_permissions(self, permissions: JsonDict) -> JsonDict:
        allowed = {"allow_download", "allow_install", "allow_launch", "allow_inference"}
        unknown = set(permissions) - allowed
        if unknown:
            raise ValueError("unknown node permissions: " + ", ".join(sorted(unknown)))
        current = self.read_config()
        existing = dict(current.get("permissions") or {})
        existing.update(permissions)
        return self.update_config({"permissions": existing})

    def ensure_csr(self, node_id: str) -> JsonDict:
        if not node_id.strip():
            raise ValueError("node_id is required for CSR creation")
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID

        tls_dir = self.node_dir / "tls"
        key_path = tls_dir / "node.key.pem"
        csr_path = tls_dir / "node.csr.pem"
        if key_path.is_file() and csr_path.is_file():
            return {
                "private_key_path": str(key_path),
                "csr_path": str(csr_path),
                "csr_pem": csr_path.read_text(encoding="ascii"),
            }
        if key_path.exists() or csr_path.exists():
            raise RuntimeError("managed node key and CSR are incomplete; refusing replacement")
        key = ec.generate_private_key(ec.SECP256R1())
        csr = (
            x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, node_id)]))
            .sign(key, hashes.SHA256())
        )
        _atomic_bytes(
            key_path,
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ),
            private=True,
        )
        csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode("ascii")
        _atomic_text(csr_path, csr_pem, private=True)
        return {"private_key_path": str(key_path), "csr_path": str(csr_path), "csr_pem": csr_pem}

    def save_enrollment(self, payload: JsonDict) -> None:
        _atomic_json(self.enrollment_path, payload)

    def clear_enrollment(self) -> None:
        if self.enrollment_path.exists():
            self.enrollment_path.unlink()


@dataclass(frozen=True)
class PairingResult:
    code: str
    envelope_key: bytes
    transcript_hash: str

    def encrypt(self, payload: JsonDict) -> JsonDict:
        nonce = secrets.token_bytes(12)
        aad = self.transcript_hash.encode("ascii")
        ciphertext = AESGCM(self.envelope_key).encrypt(
            nonce,
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            aad,
        )
        return {
            "version": 1,
            "transcript_hash": self.transcript_hash,
            "nonce": _b64(nonce),
            "ciphertext": _b64(ciphertext),
        }

    def decrypt(self, envelope: JsonDict) -> JsonDict:
        try:
            if int(envelope.get("version")) != 1:
                raise ValueError
            if str(envelope.get("transcript_hash")) != self.transcript_hash:
                raise ValueError
            plaintext = AESGCM(self.envelope_key).decrypt(
                _unb64(str(envelope["nonce"])),
                _unb64(str(envelope["ciphertext"])),
                self.transcript_hash.encode("ascii"),
            )
            value = json.loads(plaintext.decode("utf-8"))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OverflowError, InvalidTag) as exc:
            raise ValueError("encrypted enrollment payload is invalid or tampered") from exc
        if not isinstance(value, dict):
            raise ValueError("encrypted enrollment payload must be an object")
        return value


class PairingHandshake:
    """X25519 transcript binding with a human-verifiable six-digit SAS."""

    def __init__(self, private_key: X25519PrivateKey, *, role: str) -> None:
        if role not in {"node", "controller"}:
            raise ValueError("pairing role must be node or controller")
        self._private_key = private_key
        self.role = role

    @classmethod
    def create(cls, *, role: str) -> "PairingHandshake":
        return cls(X25519PrivateKey.generate(), role=role)

    @property
    def public_key(self) -> bytes:
        return self._private_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )

    def complete(self, peer_public_key: bytes, transcript: str) -> PairingResult:
        try:
            peer = X25519PublicKey.from_public_bytes(bytes(peer_public_key))
        except (TypeError, ValueError) as exc:
            raise ValueError("pairing public key is invalid") from exc
        transcript_bytes = transcript.encode("utf-8")
        shared = self._private_key.exchange(peer)
        material = HKDF(
            algorithm=hashes.SHA256(),
            length=64,
            salt=None,
            info=b"RIFT node enrollment v1\0" + transcript_bytes,
        ).derive(shared)
        sas_key, envelope_key = material[:32], material[32:]
        digest = hmac.new(sas_key, transcript_bytes, hashlib.sha256).digest()
        code = f"{int.from_bytes(digest[:4], 'big') % 1_000_000:06d}"
        transcript_hash = hashlib.sha256(transcript_bytes).hexdigest()
        return PairingResult(code=code, envelope_key=envelope_key, transcript_hash=transcript_hash)


__all__ = [
    "ManagedNodeIdentity",
    "ManagedNodeStore",
    "PairingHandshake",
    "PairingResult",
]
