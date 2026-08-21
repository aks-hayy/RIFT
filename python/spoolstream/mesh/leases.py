"""Persisted, short-lived route leases for controller-disconnected operation."""

from __future__ import annotations

import json
from pathlib import Path
import secrets
import time
from typing import Callable, Iterable


class RouteLeaseStore:
    def __init__(self, path: Path | str, *, clock: Callable[[], float] = time.time) -> None:
        self.path = Path(path)
        self.clock = clock
        self._state = self._load()

    def _load(self) -> dict[str, object]:
        if not self.path.is_file():
            return {"schema_version": 1, "leases": {}}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"failed to load route leases: {exc}") from exc
        if value.get("schema_version") != 1 or not isinstance(value.get("leases"), dict):
            raise RuntimeError("unsupported route lease schema")
        return value

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(self._state, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self.path)

    @staticmethod
    def _key(source_node_id: str, service_id: str) -> str:
        return f"{source_node_id}\0{service_id}"

    def issue(
        self,
        *,
        source_node_id: str,
        service_id: str,
        primary_node_id: str,
        fallback_node_ids: Iterable[str],
        ttl_seconds: int,
        policy_hash: str,
        controller_id: str = "controller",
        inference_endpoint: str | None = None,
        bearer_token: str | None = None,
    ) -> dict[str, object]:
        if ttl_seconds <= 0 or ttl_seconds > 3600:
            raise ValueError("route lease TTL must be between 1 and 3600 seconds")
        if not policy_hash:
            raise ValueError("policy hash is required")
        now = float(self.clock())
        lease = {
            "lease_id": f"lease-{secrets.token_hex(8)}",
            "source_node_id": source_node_id,
            "service_id": service_id,
            "primary_node_id": primary_node_id,
            "fallback_node_ids": list(dict.fromkeys(fallback_node_ids)),
            "policy_hash": policy_hash,
            "issued_at": now,
            "expires_at": now + ttl_seconds,
            "controller_id": controller_id,
            "inference_endpoint": inference_endpoint or "https://127.0.0.1:8443",
            "bearer_token": bearer_token or secrets.token_urlsafe(32),
        }
        leases = self._state["leases"]
        assert isinstance(leases, dict)
        leases[self._key(source_node_id, service_id)] = lease
        self._save()
        return dict(lease)

    def resolve(self, source_node_id: str, service_id: str, *, policy_hash: str) -> dict[str, object]:
        leases = self._state["leases"]
        assert isinstance(leases, dict)
        lease = leases.get(self._key(source_node_id, service_id))
        if not isinstance(lease, dict):
            raise KeyError("no cached route lease")
        if str(lease["policy_hash"]) != policy_hash:
            raise PermissionError("cached route lease belongs to a different policy")
        if float(self.clock()) >= float(lease["expires_at"]):
            raise TimeoutError("cached route lease has expired")
        return dict(lease)


__all__ = ["RouteLeaseStore"]
