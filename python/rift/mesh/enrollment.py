"""Explicit pairing and certificate-gated node enrollment state."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import secrets
import time
from typing import Callable

from .contracts import NodeSighting, TrustState


class EnrollmentService:
    def __init__(
        self,
        *,
        state_path: Path,
        clock: Callable[[], float] = time.time,
        code_factory: Callable[[], str] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.state_path = Path(state_path)
        self._clock = clock
        self._code_factory = code_factory or (lambda: f"{secrets.randbelow(1_000_000):06d}")
        self._id_factory = id_factory or (lambda: f"enroll-{secrets.token_hex(8)}")
        self._state = self._load()

    def _load(self) -> dict[str, object]:
        if not self.state_path.is_file():
            return {"schema_version": 1, "enrollments": {}, "nodes": {}}
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"failed to load enrollment state {self.state_path}: {exc}") from exc
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            raise RuntimeError(f"unsupported enrollment state schema: {self.state_path}")
        value.setdefault("enrollments", {})
        value.setdefault("nodes", {})
        return value

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        pending = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        pending.write_text(json.dumps(self._state, indent=2, sort_keys=True), encoding="utf-8")
        pending.replace(self.state_path)

    @staticmethod
    def _node_id(sighting: NodeSighting) -> str:
        digest = hashlib.sha256(sighting.bootstrap_fingerprint.encode("utf-8")).hexdigest()[:16]
        return f"node-{digest}"

    def begin(self, sighting: NodeSighting, *, ttl_seconds: int = 120) -> dict[str, object]:
        if ttl_seconds <= 0 or ttl_seconds > 900:
            raise ValueError("enrollment TTL must be between 1 and 900 seconds")
        now = float(self._clock())
        enrollment_id = self._id_factory()
        code = self._code_factory()
        if not (len(code) == 6 and code.isdigit()):
            raise ValueError("pairing code factory must return six decimal digits")
        pairing_salt = secrets.token_bytes(16)
        pairing_hash = hashlib.scrypt(
            code.encode("ascii"), salt=pairing_salt, n=2**14, r=8, p=1
        )
        record = {
            "enrollment_id": enrollment_id,
            "sighting_id": sighting.sighting_id,
            "node_id": self._node_id(sighting),
            "node_hint": sighting.node_hint,
            "endpoint": sighting.endpoint,
            "provider": sighting.provider,
            "bootstrap_fingerprint": sighting.bootstrap_fingerprint,
            "pairing_salt": pairing_salt.hex(),
            "pairing_hash": pairing_hash.hex(),
            "created_at": now,
            "expires_at": now + ttl_seconds,
            "state": TrustState.PAIRING_PENDING.value,
        }
        enrollments = self._state["enrollments"]
        assert isinstance(enrollments, dict)
        enrollments[enrollment_id] = record
        self._save()
        return self._public_record(record)

    def _record(self, enrollment_id: str) -> dict[str, object]:
        enrollments = self._state["enrollments"]
        assert isinstance(enrollments, dict)
        record = enrollments.get(enrollment_id)
        if not isinstance(record, dict):
            raise KeyError(f"unknown enrollment: {enrollment_id}")
        return record

    def approve(self, enrollment_id: str, pairing_code: str) -> dict[str, object]:
        record = self._record(enrollment_id)
        if record.get("state") != TrustState.PAIRING_PENDING.value:
            raise RuntimeError(f"enrollment is not pending: {enrollment_id}")
        if float(self._clock()) >= float(record["expires_at"]):
            record["state"] = "EXPIRED"
            self._save()
            raise TimeoutError("pairing challenge has expired")
        supplied_hash = hashlib.scrypt(
            str(pairing_code).encode("ascii"),
            salt=bytes.fromhex(str(record["pairing_salt"])),
            n=2**14,
            r=8,
            p=1,
        ).hex()
        if not secrets.compare_digest(str(record["pairing_hash"]), supplied_hash):
            raise PermissionError("pairing code does not match")
        record["state"] = TrustState.ENROLLED.value
        record["approved_at"] = float(self._clock())
        node = {
            "node_id": record["node_id"],
            "hostname": record["node_hint"],
            "endpoint": record["endpoint"],
            "provider": record["provider"],
            "trust_state": TrustState.ENROLLED.value,
            "mtls_status": "CERTIFICATE_REQUIRED",
            "certificate_fingerprint": None,
            "routable": False,
            "enrolled_at": record["approved_at"],
            "last_seen_at": record["approved_at"],
            "hardware": {},
            "runtime_offers": [],
        }
        nodes = self._state["nodes"]
        assert isinstance(nodes, dict)
        nodes[str(node["node_id"])] = node
        self._save()
        return {"enrollment": self._public_record(record), "node": dict(node)}

    def adopt_approved(
        self,
        *,
        enrollment_id: str,
        node_id: str,
        node_hint: str,
        endpoint: str,
        provider: str = "controller-bootstrap",
        bootstrap_fingerprint: str = "sha256:managed-bootstrap",
    ) -> dict[str, object]:
        """Persist a node approved by the managed bootstrap handshake."""

        if not enrollment_id.strip() or not node_id.strip() or not endpoint.strip():
            raise ValueError("managed enrollment identity and endpoint are required")
        enrollments = self._state["enrollments"]
        nodes = self._state["nodes"]
        assert isinstance(enrollments, dict)
        assert isinstance(nodes, dict)
        existing = enrollments.get(enrollment_id)
        if isinstance(existing, dict):
            if existing.get("node_id") != node_id:
                raise RuntimeError("enrollment id is already bound to another node")
            return {"enrollment": self._public_record(existing), "node": dict(nodes[str(node_id)])}
        now = float(self._clock())
        record = {
            "enrollment_id": enrollment_id,
            "sighting_id": f"bootstrap-{enrollment_id}",
            "node_id": node_id,
            "node_hint": node_hint,
            "endpoint": endpoint,
            "provider": provider,
            "bootstrap_fingerprint": bootstrap_fingerprint,
            "created_at": now,
            "approved_at": now,
            "state": TrustState.ENROLLED.value,
        }
        node = {
            "node_id": node_id,
            "hostname": node_hint,
            "endpoint": endpoint,
            "provider": provider,
            "trust_state": TrustState.ENROLLED.value,
            "mtls_status": "CERTIFICATE_ISSUED",
            "certificate_fingerprint": None,
            "routable": False,
            "enrolled_at": now,
            "last_seen_at": now,
            "hardware": {},
            "runtime_offers": [],
        }
        enrollments[enrollment_id] = record
        nodes[node_id] = node
        self._save()
        return {"enrollment": self._public_record(record), "node": dict(node)}

    def activate(self, enrollment_id: str, *, certificate_fingerprint: str) -> dict[str, object]:
        if not certificate_fingerprint.strip():
            raise ValueError("certificate fingerprint is required")
        record = self._record(enrollment_id)
        if record.get("state") != TrustState.ENROLLED.value:
            raise RuntimeError("pairing must be approved before certificate activation")
        nodes = self._state["nodes"]
        assert isinstance(nodes, dict)
        node = nodes.get(str(record["node_id"]))
        if not isinstance(node, dict):
            raise RuntimeError("enrolled node record is missing")
        record["state"] = TrustState.ACTIVE.value
        node["trust_state"] = TrustState.ACTIVE.value
        node["mtls_status"] = "ACTIVE"
        node["certificate_fingerprint"] = certificate_fingerprint
        node["routable"] = True
        node["activated_at"] = float(self._clock())
        node_token = secrets.token_urlsafe(32)
        node["node_token_hash"] = hashlib.sha256(node_token.encode("utf-8")).hexdigest()
        self._save()
        public_node = {key: value for key, value in node.items() if key != "node_token_hash"}
        return {"enrollment": self._public_record(record), "node": public_node, "node_token": node_token}

    def revoke(self, node_id: str) -> dict[str, object]:
        nodes = self._state["nodes"]
        assert isinstance(nodes, dict)
        node = nodes.get(node_id)
        if not isinstance(node, dict):
            raise KeyError(f"unknown node: {node_id}")
        node["trust_state"] = TrustState.REVOKED.value
        node["mtls_status"] = "REVOKED"
        node["routable"] = False
        node["revoked_at"] = float(self._clock())
        self._save()
        return dict(node)

    def update_capability(self, node_id: str, snapshot: dict[str, object]) -> dict[str, object]:
        nodes = self._state["nodes"]
        assert isinstance(nodes, dict)
        node = nodes.get(node_id)
        if not isinstance(node, dict):
            raise KeyError(f"unknown node: {node_id}")
        if node.get("trust_state") != TrustState.ACTIVE.value:
            raise PermissionError("only active mTLS nodes may publish capabilities")
        sequence = int(snapshot.get("sequence") or 0)
        if sequence <= int(node.get("capability_sequence") or 0):
            raise ValueError("capability sequence must increase monotonically")
        offers = snapshot.get("runtime_offers") or []
        if not isinstance(offers, list):
            raise ValueError("runtime_offers must be an array")
        node["capability_sequence"] = sequence
        node["last_seen_at"] = float(snapshot.get("observed_at") or self._clock())
        node["hardware"] = dict(snapshot.get("hardware") or {})
        node["runtime_offers"] = [dict(offer) for offer in offers if isinstance(offer, dict)]
        node["power"] = dict(snapshot.get("power") or {})
        node["pressure"] = dict(snapshot.get("pressure") or {})
        node["healthy"] = bool(snapshot.get("healthy", True))
        node["queue_depth"] = int(snapshot.get("queue_depth") or 0)
        self._save()
        return dict(node)

    def record_telemetry(self, node_id: str, snapshot: dict[str, object], token: str | None = None) -> dict[str, object]:
        nodes = self._state["nodes"]
        assert isinstance(nodes, dict)
        node = nodes.get(node_id)
        if not isinstance(node, dict):
            raise KeyError(f"unknown node: {node_id}")
        if node.get("trust_state") != TrustState.ACTIVE.value:
            raise PermissionError("only active mTLS nodes may publish telemetry")
        token_hash = str(node.get("node_token_hash") or "")
        if not token or not token_hash or not secrets.compare_digest(
            hashlib.sha256(token.encode("utf-8")).hexdigest(), token_hash
        ):
            raise PermissionError("telemetry requires the active node credential")
        sequence = int(snapshot.get("sequence") or 0)
        if sequence <= int(node.get("telemetry_sequence") or 0):
            raise ValueError("telemetry sequence must increase monotonically")
        batch = snapshot.get("samples")
        if batch is not None and (not isinstance(batch, list) or len(batch) > 1000):
            raise ValueError("telemetry samples must be a list of at most 1000 items")
        allowed = {
            "sequence", "observed_at", "battery_percent", "charging", "available_memory_bytes",
            "low_memory", "thermal_status", "runtime_state", "active_model_sha256",
            "samples", "session_id", "cpu_percent", "process_cpu_percent", "host_ram_pressure_percent",
            "host_ram_available_bytes", "gpu_utilization_percent", "gpu_temperature_c",
            "gpu_vram_used_bytes", "gpu_vram_total_bytes", "gpu_power_watts", "gpu_devices",
            "gpu_vram_pressure_percent", "cpu_temperature_c",
            "availability", "stale_after_seconds",
        }
        telemetry = {key: value for key, value in snapshot.items() if key in allowed}
        telemetry["sequence"] = sequence
        telemetry["observed_at"] = float(snapshot.get("observed_at") or self._clock())
        node["telemetry_sequence"] = sequence
        node["telemetry"] = telemetry
        node["telemetry_received_at"] = float(self._clock())
        node["telemetry_stale"] = (float(self._clock()) - telemetry["observed_at"]) > 6.0
        node["last_seen_at"] = telemetry["observed_at"]
        self._save()
        return dict(telemetry)

    def list_nodes(self) -> list[dict[str, object]]:
        nodes = self._state["nodes"]
        assert isinstance(nodes, dict)
        return [dict(nodes[key]) for key in sorted(nodes)]

    def list_enrollments(self) -> list[dict[str, object]]:
        """Return persisted enrollment records without pairing secrets."""

        enrollments = self._state["enrollments"]
        assert isinstance(enrollments, dict)
        return [
            self._public_record(enrollments[key])
            for key in sorted(enrollments)
            if isinstance(enrollments[key], dict)
        ]

    @staticmethod
    def _public_record(record: dict[str, object]) -> dict[str, object]:
        private = {"pairing_code", "pairing_salt", "pairing_hash"}
        return {key: value for key, value in record.items() if key not in private}


__all__ = ["EnrollmentService"]
