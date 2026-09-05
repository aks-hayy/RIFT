"""Ephemeral controller-side enrollment sessions for managed RIFT nodes."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import secrets
import time
from typing import Callable

from ..node_enrollment import PairingHandshake, PairingResult


@dataclass
class _Session:
    enrollment_id: str
    node_id: str
    display_name: str
    endpoint: str
    csr_pem: str
    created_at: float
    expires_at: float
    transcript: str
    controller_public_key: str
    result: PairingResult
    state: str = "PAIRING_PENDING"
    attempts: int = 0
    approved_at: float | None = None


class EnrollmentWindow:
    """Bounded enrollment window with human-approved SAS pairing."""

    def __init__(
        self,
        *,
        controller_id: str,
        clock: Callable[[], float] = time.time,
        id_factory: Callable[[], str] | None = None,
        max_pending: int = 100,
    ) -> None:
        if not controller_id.strip():
            raise ValueError("controller_id is required")
        if max_pending <= 0:
            raise ValueError("max_pending must be positive")
        self.controller_id = controller_id
        self.clock = clock
        self.id_factory = id_factory or (lambda: f"enroll-{secrets.token_hex(8)}")
        self.max_pending = max_pending
        self._expires_at = 0.0
        self._sessions: dict[str, _Session] = {}

    def open(self, *, ttl_seconds: int = 600) -> dict[str, object]:
        if ttl_seconds <= 0 or ttl_seconds > 3600:
            raise ValueError("enrollment window TTL must be between 1 and 3600 seconds")
        self._expires_at = float(self.clock()) + ttl_seconds
        return self.status()

    def close(self) -> dict[str, object]:
        self._expires_at = 0.0
        return self.status()

    def is_open(self) -> bool:
        return self._expires_at > float(self.clock())

    def status(self, enrollment_id: str | None = None) -> dict[str, object]:
        if enrollment_id is not None:
            return self.status_for(enrollment_id)
        return {
            "controller_id": self.controller_id,
            "open": self.is_open(),
            "expires_at": self._expires_at or None,
            "pending_count": sum(
                session.state == "PAIRING_PENDING" and session.expires_at > float(self.clock())
                for session in self._sessions.values()
            ),
        }

    def begin(
        self,
        *,
        node_id: str,
        display_name: str,
        endpoint: str,
        csr_pem: str,
        node_public_key: bytes,
        ttl_seconds: int = 120,
    ) -> dict[str, object]:
        now = float(self.clock())
        if not self.is_open():
            raise PermissionError("controller enrollment window is closed")
        if ttl_seconds <= 0 or ttl_seconds > 600:
            raise ValueError("enrollment TTL must be between 1 and 600 seconds")
        pending = sum(session.state == "PAIRING_PENDING" and session.expires_at > now for session in self._sessions.values())
        if pending >= self.max_pending:
            raise RuntimeError("controller enrollment queue is full")
        if not node_id.strip() or not display_name.strip() or not endpoint.startswith("https://"):
            raise ValueError("node_id, display_name, and HTTPS endpoint are required")
        enrollment_id = str(self.id_factory())
        controller_handshake = PairingHandshake.create(role="controller")
        controller_public_key = controller_handshake.public_key.hex()
        transcript = "|".join(
            (
                "rift-enrollment-v1",
                self.controller_id,
                enrollment_id,
                node_id,
                hashlib.sha256(csr_pem.encode("utf-8")).hexdigest(),
                bytes(node_public_key).hex(),
                controller_public_key,
            )
        )
        result = controller_handshake.complete(bytes(node_public_key), transcript)
        session = _Session(
            enrollment_id=enrollment_id,
            node_id=node_id,
            display_name=display_name,
            endpoint=endpoint,
            csr_pem=csr_pem,
            created_at=now,
            expires_at=min(now + ttl_seconds, self._expires_at),
            transcript=transcript,
            controller_public_key=controller_public_key,
            result=result,
        )
        self._sessions[enrollment_id] = session
        return self._public(session)

    def _get(self, enrollment_id: str) -> _Session:
        session = self._sessions.get(enrollment_id)
        if session is None:
            raise KeyError(f"unknown enrollment: {enrollment_id}")
        if float(self.clock()) >= session.expires_at and session.state in {"PAIRING_PENDING", "ENROLLED"}:
            session.state = "EXPIRED"
            raise TimeoutError("enrollment challenge has expired")
        return session

    def status_for(self, enrollment_id: str) -> dict[str, object]:
        return self._public(self._get(enrollment_id))

    def approve(self, enrollment_id: str, pairing_code: str) -> dict[str, object]:
        session = self._get(enrollment_id)
        if session.state != "PAIRING_PENDING":
            raise RuntimeError(f"enrollment is not pending: {enrollment_id}")
        if len(pairing_code) != 6 or not pairing_code.isdigit():
            raise ValueError("pairing code must contain six digits")
        session.attempts += 1
        if not secrets.compare_digest(session.result.code, pairing_code):
            if session.attempts >= 5:
                session.state = "REJECTED"
            raise PermissionError("pairing code does not match")
        session.state = "ENROLLED"
        session.approved_at = float(self.clock())
        return self._public(session)

    def cancel(self, enrollment_id: str) -> dict[str, object]:
        session = self._get(enrollment_id)
        session.state = "CANCELLED"
        return self._public(session)

    def encrypt_for(self, enrollment_id: str, payload: dict[str, object]) -> dict[str, object]:
        session = self._get(enrollment_id)
        if session.state not in {"ENROLLED", "CERTIFICATE_ISSUED"}:
            raise PermissionError("enrollment must be approved before issuing credentials")
        return session.result.encrypt(payload)

    def session(self, enrollment_id: str) -> dict[str, object]:
        session = self._get(enrollment_id)
        return {
            **self._public(session),
            "csr_pem": session.csr_pem,
            "endpoint": session.endpoint,
            "node_id": session.node_id,
            "display_name": session.display_name,
        }

    def list_sessions(self) -> list[dict[str, object]]:
        """Return safe pending/issued enrollment metadata for the operator UI."""

        values: list[dict[str, object]] = []
        for enrollment_id in sorted(self._sessions):
            try:
                values.append(self.status_for(enrollment_id))
            except TimeoutError:
                values.append({"enrollment_id": enrollment_id, "state": "EXPIRED"})
        return values

    def has_session(self, enrollment_id: str) -> bool:
        return enrollment_id in self._sessions

    def mark_certificate_issued(self, enrollment_id: str) -> dict[str, object]:
        session = self._get(enrollment_id)
        if session.state not in {"ENROLLED", "CERTIFICATE_ISSUED"}:
            raise RuntimeError(f"enrollment is not ready for certificate issuance: {enrollment_id}")
        session.state = "CERTIFICATE_ISSUED"
        return self._public(session)

    def mark_active(self, enrollment_id: str) -> dict[str, object]:
        session = self._get(enrollment_id)
        if session.state not in {"CERTIFICATE_ISSUED", "ACTIVE"}:
            raise RuntimeError(f"enrollment is not ready for activation: {enrollment_id}")
        session.state = "ACTIVE"
        return self._public(session)

    @staticmethod
    def _public(session: _Session) -> dict[str, object]:
        return {
            "enrollment_id": session.enrollment_id,
            "node_id": session.node_id,
            "display_name": session.display_name,
            "endpoint": session.endpoint,
            "created_at": session.created_at,
            "expires_at": session.expires_at,
            "state": session.state,
            "attempts": session.attempts,
            "approved_at": session.approved_at,
            "controller_public_key": session.controller_public_key,
            "transcript": session.transcript,
        }


__all__ = ["EnrollmentWindow"]
