"""Small, fail-safe alert adapter boundary for objective transitions."""

from __future__ import annotations

import json
from typing import Any, Mapping, Protocol
from urllib.request import Request, urlopen


class AlertAdapter(Protocol):
    name: str

    def send(self, event: Mapping[str, Any]) -> None: ...


class MemoryAlertAdapter:
    name = "memory"

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def send(self, event: Mapping[str, Any]) -> None:
        self.events.append(dict(event))


class WebhookAlertAdapter:
    name = "webhook"

    def __init__(self, endpoint: str, *, timeout_seconds: float = 5.0) -> None:
        if not str(endpoint).strip():
            raise ValueError("webhook endpoint is required")
        self.endpoint = str(endpoint)
        self.timeout_seconds = max(0.1, float(timeout_seconds))

    def send(self, event: Mapping[str, Any]) -> None:
        request = Request(
            self.endpoint,
            data=json.dumps(dict(event), separators=(",", ":"), default=str).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self.timeout_seconds):
            pass


class AlertDispatcher:
    def __init__(self, adapters: Mapping[str, AlertAdapter] | None = None) -> None:
        self.adapters = {str(name): adapter for name, adapter in (adapters or {}).items()}

    def register(self, adapter: AlertAdapter) -> None:
        self.adapters[str(adapter.name)] = adapter

    def dispatch(self, event: Mapping[str, Any], *, adapters: list[str] | None = None) -> dict[str, int]:
        names = list(adapters or self.adapters.keys())
        sent = 0
        failed = 0
        for name in names:
            adapter = self.adapters.get(str(name))
            if adapter is None:
                failed += 1
                continue
            try:
                adapter.send(event)
                sent += 1
            except Exception:
                # Alert delivery is deliberately outside the service critical
                # path. The objective event remains durable in SQLite.
                failed += 1
        return {"sent": sent, "failed": failed}


__all__ = ["AlertAdapter", "AlertDispatcher", "MemoryAlertAdapter", "WebhookAlertAdapter"]
