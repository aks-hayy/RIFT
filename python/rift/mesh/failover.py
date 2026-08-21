"""Controller recovery mechanisms with explicit manual and quorum gates."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
import secrets
import time


class ControllerRecovery:
    def __init__(self, path: Path | str, *, recovery_key: str) -> None:
        if len(recovery_key) < 16:
            raise ValueError("recovery key must contain at least 16 characters")
        self.path = Path(path)
        self._salt = secrets.token_bytes(16)
        self._expected = hashlib.scrypt(
            recovery_key.encode("utf-8"), salt=self._salt, n=2**14, r=8, p=1
        )

    def promote_manual(self, node_id: str, *, recovery_key: str) -> dict[str, object]:
        supplied = hashlib.scrypt(
            recovery_key.encode("utf-8"), salt=self._salt, n=2**14, r=8, p=1
        )
        if not hmac.compare_digest(self._expected, supplied):
            raise PermissionError("recovery key is invalid")
        record = {
            "controller_node_id": node_id,
            "mode": "manual-recovery-key",
            "promoted_at": time.time(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
        return record


class QuorumElection:
    def __init__(self, *, voters: list[str]) -> None:
        unique = tuple(sorted(set(voters)))
        if len(unique) < 3 or len(unique) % 2 == 0:
            raise ValueError("automatic controller election requires an odd quorum of at least 3 voters")
        self.voters = unique
        self._votes: dict[int, dict[str, str]] = {}

    def vote(self, *, term: int, voter: str, candidate: str) -> None:
        if voter not in self.voters or candidate not in self.voters:
            raise PermissionError("only configured voters may vote or become controller")
        if term <= 0:
            raise ValueError("election term must be positive")
        votes = self._votes.setdefault(term, {})
        previous = votes.get(voter)
        if previous is not None and previous != candidate:
            raise RuntimeError("a voter cannot vote twice in one term")
        votes[voter] = candidate

    def winner(self, *, term: int) -> str | None:
        votes = self._votes.get(term, {})
        threshold = len(self.voters) // 2 + 1
        for candidate in self.voters:
            if sum(1 for value in votes.values() if value == candidate) >= threshold:
                return candidate
        return None


__all__ = ["ControllerRecovery", "QuorumElection"]
