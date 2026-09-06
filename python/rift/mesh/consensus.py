"""Controller profile and leadership fencing for safe management writes."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from enum import Enum
from pathlib import Path


class ControllerProfile(str, Enum):
    SIMPLE = "SIMPLE"
    PRODUCTION = "PRODUCTION"


class ControllerFence:
    def __init__(self, path: Path | str, *, controller_id: str, profile: ControllerProfile = ControllerProfile.SIMPLE):
        if not controller_id.strip():
            raise ValueError("controller_id is required")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.controller_id = controller_id
        self.profile = ControllerProfile(profile)
        self._state = self._load()

    def _load(self) -> dict[str, object]:
        if not self.path.is_file():
            state = {
                "schema_version": 1,
                "controller_id": self.controller_id,
                "profile": self.profile.value,
                "epoch": 1,
                "leader_id": self.controller_id,
                "quorum": True,
                "secret": secrets.token_hex(32),
            }
            self._write(state)
            return state
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"controller fence state is unreadable: {self.path}") from exc
        if not isinstance(value, dict) or int(value.get("schema_version") or 0) != 1:
            raise RuntimeError("unsupported controller fence schema")
        if str(value.get("controller_id")) != self.controller_id:
            raise PermissionError("controller fence belongs to another controller")
        return value

    def _write(self, value: dict[str, object]) -> None:
        pending = self.path.with_suffix(self.path.suffix + ".tmp")
        pending.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
        pending.replace(self.path)

    def set_quorum(self, available: bool) -> None:
        if self.profile is ControllerProfile.SIMPLE and not available:
            raise ValueError("simple controller profile does not model quorum loss")
        self._state["quorum"] = bool(available)
        self._write(self._state)

    def become_leader(self, leader_id: str) -> dict[str, object]:
        if not str(leader_id).strip():
            raise ValueError("leader_id is required")
        self._state["epoch"] = int(self._state.get("epoch") or 0) + 1
        self._state["leader_id"] = str(leader_id)
        self._write(self._state)
        return {"epoch": self._state["epoch"], "leader_id": self._state["leader_id"]}

    def issue(self, action: str, payload: dict[str, object], *, ttl_seconds: int, now: float) -> dict[str, object]:
        if not str(action).strip():
            raise ValueError("operation action is required")
        if ttl_seconds <= 0 or ttl_seconds > 3600:
            raise ValueError("operation authority TTL must be between 1 and 3600 seconds")
        if self.profile is ControllerProfile.PRODUCTION and not bool(self._state.get("quorum")):
            raise PermissionError("quorum is unavailable; management writes are fenced")
        authority = {
            "schema_version": 1,
            "authority_id": f"authority-{secrets.token_hex(8)}",
            "controller_id": self.controller_id,
            "leader_id": str(self._state["leader_id"]),
            "epoch": int(self._state["epoch"]),
            "action": str(action),
            "payload": dict(payload),
            "issued_at": float(now),
            "expires_at": float(now) + ttl_seconds,
        }
        authority["signature"] = self._sign(authority)
        return authority

    def validate(self, authority: dict[str, object], *, now: float) -> dict[str, object]:
        value = dict(authority)
        signature = str(value.pop("signature") or "")
        if not hmac.compare_digest(signature, self._sign(value)):
            raise PermissionError("operation authority signature is invalid")
        if int(value.get("epoch") or 0) != int(self._state.get("epoch") or 0):
            raise PermissionError("operation authority epoch is stale")
        if str(value.get("leader_id")) != str(self._state.get("leader_id")):
            raise PermissionError("operation authority leader is stale")
        if float(now) >= float(value.get("expires_at") or 0):
            raise TimeoutError("operation authority is expired")
        return value

    def _sign(self, value: dict[str, object]) -> str:
        body = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hmac.new(bytes.fromhex(str(self._state["secret"])), body, hashlib.sha256).hexdigest()


__all__ = ["ControllerFence", "ControllerProfile"]
