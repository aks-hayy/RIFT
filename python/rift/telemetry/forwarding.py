"""Durable node-to-controller telemetry forwarding."""

from __future__ import annotations

from typing import Any, Callable

from .store import TelemetryStore


class TelemetryForwarder:
    def __init__(self, store: TelemetryStore, send_batch: Callable[[dict[str, Any]], dict[str, Any]], *, batch_size: int = 100) -> None:
        self.store = store
        self.send_batch = send_batch
        self.batch_size = max(1, int(batch_size))

    def flush(self) -> dict[str, Any]:
        due = self.store.due_outbox(limit=self.batch_size)
        if not due:
            return {"sent": 0, "pending": 0}
        payload = {"stream": due[0]["stream"], "sequence_start": due[0]["sequence"], "samples": [item["payload"] for item in due]}
        try:
            result = self.send_batch(payload)
        except Exception as exc:
            for item in due:
                self.store.retry_outbox(item["stream"], item["sequence"], retry_after_seconds=min(300.0, 2.0 ** min(8, int(item["attempts"]))))
            return {"sent": 0, "pending": len(due), "error": str(exc)}
        accepted = int(result.get("accepted") or len(due)) if isinstance(result, dict) else len(due)
        for item in due[:accepted]:
            self.store.acknowledge(item["stream"], item["sequence"])
        return {"sent": min(accepted, len(due)), "pending": max(0, len(due) - accepted), "ack": result}


__all__ = ["TelemetryForwarder"]
