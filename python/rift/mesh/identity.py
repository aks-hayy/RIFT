"""Private controller CA for mTLS node identities."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import os
from pathlib import Path


class NodeCertificateAuthority:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.key_path = self.root / "controller-ca.key.pem"
        self.cert_path = self.root / "controller-ca.cert.pem"
        self._ensure_authority()

    @staticmethod
    def _imports():
        try:
            from cryptography import x509
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
        except ImportError as exc:
            raise RuntimeError(
                "mTLS enrollment requires the 'cryptography' package from RIFT dependencies"
            ) from exc
        return x509, hashes, serialization, ec, ExtendedKeyUsageOID, NameOID

    def _ensure_authority(self) -> None:
        x509, hashes, serialization, ec, _, NameOID = self._imports()
        if self.key_path.is_file() and self.cert_path.is_file():
            self._load_authority()
            return
        if self.key_path.exists() or self.cert_path.exists():
            raise RuntimeError("controller CA is incomplete; refusing to replace partial identity")
        self.root.mkdir(parents=True, exist_ok=True)
        key = ec.generate_private_key(ec.SECP256R1())
        now = datetime.now(timezone.utc)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "RIFT Mesh Controller CA")])
        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(key, hashes.SHA256())
        )
        key_bytes = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        cert_bytes = certificate.public_bytes(serialization.Encoding.PEM)
        self._exclusive_write(self.key_path, key_bytes, 0o600)
        self._exclusive_write(self.cert_path, cert_bytes, 0o644)
        self._key = key
        self._certificate = certificate

    @staticmethod
    def _exclusive_write(path: Path, content: bytes, mode: int) -> None:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        try:
            os.write(descriptor, content)
        finally:
            os.close(descriptor)

    def _load_authority(self) -> None:
        x509, _, serialization, _, _, _ = self._imports()
        try:
            self._key = serialization.load_pem_private_key(self.key_path.read_bytes(), password=None)
            self._certificate = x509.load_pem_x509_certificate(self.cert_path.read_bytes())
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"controller CA cannot be loaded: {exc}") from exc
        if self._certificate.public_key().public_numbers() != self._key.public_key().public_numbers():
            raise RuntimeError("controller CA private key does not match its certificate")

    def ca_fingerprint(self) -> str:
        _, hashes, _, _, _, _ = self._imports()
        return "sha256:" + self._certificate.fingerprint(hashes.SHA256()).hex()

    def ca_certificate_pem(self) -> str:
        _, _, serialization, _, _, _ = self._imports()
        return self._certificate.public_bytes(serialization.Encoding.PEM).decode("ascii")

    def issue_node_certificate(
        self,
        *,
        node_id: str,
        csr_pem: str,
        validity_days: int = 90,
        addresses: list[str] | None = None,
    ) -> dict[str, str]:
        x509, hashes, serialization, _, ExtendedKeyUsageOID, NameOID = self._imports()
        return self._issue_identity_certificate(
            x509=x509,
            hashes=hashes,
            serialization=serialization,
            ExtendedKeyUsageOID=ExtendedKeyUsageOID,
            NameOID=NameOID,
            identity_kind="node",
            identity_id=node_id,
            csr_pem=csr_pem,
            validity_days=validity_days,
            addresses=addresses,
        )

    def issue_controller_certificate(
        self,
        *,
        controller_id: str,
        csr_pem: str,
        validity_days: int = 365,
        addresses: list[str] | None = None,
    ) -> dict[str, str]:
        x509, hashes, serialization, _, ExtendedKeyUsageOID, NameOID = self._imports()
        return self._issue_identity_certificate(
            x509=x509,
            hashes=hashes,
            serialization=serialization,
            ExtendedKeyUsageOID=ExtendedKeyUsageOID,
            NameOID=NameOID,
            identity_kind="controller",
            identity_id=controller_id,
            csr_pem=csr_pem,
            validity_days=validity_days,
            addresses=addresses,
        )

    def _issue_identity_certificate(
        self,
        *,
        x509,
        hashes,
        serialization,
        ExtendedKeyUsageOID,
        NameOID,
        identity_kind: str,
        identity_id: str,
        csr_pem: str,
        validity_days: int,
        addresses: list[str] | None,
    ) -> dict[str, str]:
        if validity_days <= 0 or validity_days > 365:
            raise ValueError("identity certificate validity must be between 1 and 365 days")
        try:
            csr = x509.load_pem_x509_csr(csr_pem.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as exc:
            raise ValueError("invalid PEM certificate signing request") from exc
        if not csr.is_signature_valid:
            raise ValueError("CSR signature is invalid")
        common_names = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        if len(common_names) != 1 or common_names[0].value != identity_id:
            raise PermissionError("CSR common name must match the enrolled identity")
        now = datetime.now(timezone.utc)
        san_names = [x509.UniformResourceIdentifier(f"rift-{identity_kind}:{identity_id}")]
        for address in addresses or []:
            value = str(address).strip()
            if not value:
                continue
            try:
                san_names.append(x509.IPAddress(ipaddress.ip_address(value)))
            except ValueError:
                san_names.append(x509.DNSName(value))
        certificate = (
            x509.CertificateBuilder()
            .subject_name(csr.subject)
            .issuer_name(self._certificate.subject)
            .public_key(csr.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=validity_days))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(
                x509.ExtendedKeyUsage(
                    [ExtendedKeyUsageOID.CLIENT_AUTH, ExtendedKeyUsageOID.SERVER_AUTH]
                ),
                critical=True,
            )
            .add_extension(
                x509.SubjectAlternativeName(san_names),
                critical=False,
            )
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(self._key.public_key()),
                critical=False,
            )
            .sign(self._key, hashes.SHA256())
        )
        certificate_pem = certificate.public_bytes(serialization.Encoding.PEM).decode("ascii")
        fingerprint = "sha256:" + certificate.fingerprint(hashes.SHA256()).hex()
        return {
            "certificate_pem": certificate_pem,
            "ca_certificate_pem": self.ca_certificate_pem(),
            "fingerprint": fingerprint,
        }


__all__ = ["NodeCertificateAuthority"]
