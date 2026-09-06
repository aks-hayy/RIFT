"""Signed, monotonic model catalog records."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _canonical(value: dict[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class CatalogEntry:
    entry_id: str
    repository: str
    revision: str
    filename: str
    digest: str
    license: str
    size_bytes: int
    baseline: dict[str, object]

    def __post_init__(self) -> None:
        if not self.entry_id.strip() or not self.repository.strip() or not self.revision.strip():
            raise ValueError("catalog entry identity is required")
        if Path(self.filename).name != self.filename or not self.filename.strip():
            raise ValueError("catalog filename must be a single file name")
        if not self.digest.startswith("sha256:") or len(self.digest) != 71:
            raise ValueError("catalog digest must be sha256:<64 hex characters>")
        try:
            int(self.digest[7:], 16)
        except ValueError as exc:
            raise ValueError("catalog digest must be sha256:<64 hex characters>") from exc
        if self.size_bytes < 0:
            raise ValueError("catalog size_bytes must be nonnegative")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class SignedCatalogStore:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.key_path = self.root / "catalog-signing-key.pem"
        self.catalog_path = self.root / "catalog.json"
        self._key = self._load_or_create_key()

    def _load_or_create_key(self) -> Ed25519PrivateKey:
        if self.key_path.is_file():
            key = serialization.load_pem_private_key(self.key_path.read_bytes(), password=None)
            if not isinstance(key, Ed25519PrivateKey):
                raise ValueError("catalog signing key is not Ed25519")
            return key
        key = Ed25519PrivateKey.generate()
        self.key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        try:
            self.key_path.chmod(0o600)
        except OSError:
            pass
        return key

    def public_key(self) -> bytes:
        return self._key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def key_id(self) -> str:
        return hashlib.sha256(self.public_key()).hexdigest()[:16]

    def sign(
        self,
        *,
        sequence: int,
        entries: list[CatalogEntry],
        issued_at: float,
        expires_at: float,
    ) -> dict[str, object]:
        if sequence < 1 or expires_at <= issued_at:
            raise ValueError("catalog sequence and validity window are invalid")
        body: dict[str, object] = {
            "schema_version": 1,
            "sequence": int(sequence),
            "issued_at": float(issued_at),
            "expires_at": float(expires_at),
            "key_id": self.key_id(),
            "entries": [entry.to_dict() for entry in entries],
        }
        body["signature"] = self._encode(self._key.sign(_canonical(body)))
        return body

    def accept(self, signed: dict[str, object], *, now: float) -> dict[str, object]:
        payload = dict(signed)
        signature_text = str(payload.pop("signature") or "")
        try:
            signature = self._decode(signature_text)
            if str(payload.get("key_id")) != self.key_id():
                raise ValueError("catalog key id is not trusted")
            self._key.public_key().verify(signature, _canonical(payload))
        except Exception as exc:
            raise ValueError("catalog signature is invalid") from exc
        if int(payload.get("schema_version") or 0) != 1:
            raise ValueError("unsupported catalog schema")
        sequence = int(payload.get("sequence") or 0)
        previous = self._load_last_sequence()
        if sequence <= previous:
            raise ValueError("catalog rollback or duplicate sequence rejected")
        if float(now) >= float(payload.get("expires_at") or 0):
            raise TimeoutError("catalog has expired")
        entries = payload.get("entries")
        if not isinstance(entries, list):
            raise ValueError("catalog entries must be an array")  # noqa: TRY004 - malformed wire data is a value error
        normalized = [CatalogEntry(**item).to_dict() for item in entries if isinstance(item, dict)]
        if len(normalized) != len(entries):
            raise ValueError("catalog entries must be objects")
        payload["entries"] = normalized
        payload["signature"] = signature_text
        pending = self.catalog_path.with_suffix(".json.tmp")
        pending.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        pending.replace(self.catalog_path)
        return dict(payload)

    def current(self) -> dict[str, object] | None:
        if not self.catalog_path.is_file():
            return None
        try:
            value = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"catalog state is unreadable: {self.catalog_path}") from exc
        return value if isinstance(value, dict) else None

    def _load_last_sequence(self) -> int:
        value = self.current()
        return int(value.get("sequence") or 0) if value else 0

    @staticmethod
    def _encode(value: bytes) -> str:
        import base64

        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

    @staticmethod
    def _decode(value: str) -> bytes:
        import base64

        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


__all__ = ["CatalogEntry", "SignedCatalogStore"]
