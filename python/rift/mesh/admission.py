"""Bounded request admission and failover coordination for mesh gateways."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class _Request:
    request_id: str
    candidates: tuple[str, ...]
    deadline: float
    index: int = 0
    status: str = "DISPATCHING"
    attempts: list[dict[str, object]] = field(default_factory=list)
    response: object | None = None


class RequestCoordinator:
    """Retry each admitted route at most once, then wait only until a hard deadline."""

    def __init__(self, *, wait_timeout_seconds: float = 30.0, max_queue: int = 256, clock: Callable[[], float] = time.monotonic):
        if wait_timeout_seconds <= 0:
            raise ValueError("wait_timeout_seconds must be positive")
        if max_queue < 1:
            raise ValueError("max_queue must be positive")
        self.wait_timeout_seconds = float(wait_timeout_seconds)
        self.max_queue = int(max_queue)
        self.clock = clock
        self._requests: dict[str, _Request] = {}

    def submit(self, request_id: str, candidates: list[str] | tuple[str, ...]) -> dict[str, object]:
        request_id = str(request_id or "").strip()
        if not request_id:
            raise ValueError("request_id is required")
        if request_id in self._requests:
            raise ValueError("request_id is already admitted")
        unique = tuple(dict.fromkeys(str(item).strip() for item in candidates if str(item).strip()))
        if not unique:
            raise ValueError("at least one route candidate is required")
        active = sum(item.status in {"DISPATCHING", "WAITING_RECOVERY"} for item in self._requests.values())
        if active >= self.max_queue:
            raise RuntimeError("mesh admission queue is full")
        item = _Request(request_id, unique, self.clock() + self.wait_timeout_seconds)
        self._requests[request_id] = item
        return self._view(item)

    def fail(self, request_id: str, node_id: str, reason: str) -> dict[str, object]:
        item = self._get(request_id)
        self._ensure_open(item)
        if item.status != "DISPATCHING" or item.candidates[item.index] != node_id:
            raise ValueError("failure does not match the active route attempt")
        item.attempts.append({"node_id": node_id, "reason": str(reason), "at": self.clock()})
        item.index += 1
        if item.index < len(item.candidates):
            return self._view(item)
        item.status = "WAITING_RECOVERY"
        return self._view(item)

    def complete(self, request_id: str, response: object) -> dict[str, object]:
        item = self._get(request_id)
        self._ensure_open(item)
        item.status = "COMPLETED"
        item.response = response
        return self._view(item)

    def expire(self, request_id: str) -> dict[str, object]:
        item = self._get(request_id)
        if item.status in {"COMPLETED", "TIMED_OUT"}:
            return self._view(item)
        if self.clock() < item.deadline:
            return self._view(item)
        item.status = "TIMED_OUT"
        return self._view(item)

    def status(self, request_id: str) -> dict[str, object]:
        return self._view(self._get(request_id))

    def _get(self, request_id: str) -> _Request:
        try:
            return self._requests[str(request_id)]
        except KeyError as exc:
            raise KeyError(f"unknown request: {request_id}") from exc

    def _ensure_open(self, item: _Request) -> None:
        if item.status in {"COMPLETED", "TIMED_OUT"}:
            raise RuntimeError(f"request is already {item.status.lower()}")
        if self.clock() >= item.deadline:
            item.status = "TIMED_OUT"
            raise TimeoutError("request admission deadline expired")

    @staticmethod
    def _view(item: _Request) -> dict[str, object]:
        result: dict[str, object] = {
            "request_id": item.request_id,
            "status": item.status,
            "deadline": item.deadline,
            "attempts": list(item.attempts),
        }
        if item.status == "DISPATCHING":
            result["node_id"] = item.candidates[item.index]
        if item.response is not None:
            result["response"] = item.response
        return result


__all__ = ["RequestCoordinator"]
