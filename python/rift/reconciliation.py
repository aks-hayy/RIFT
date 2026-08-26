"""Bounded desired-state reconciliation for the local controller process."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Any, Callable


@dataclass(frozen=True)
class ReconcilePolicy:
    interval_seconds: float = 5.0
    allow_recovery: bool = False
    max_iterations: int = 0

    def __post_init__(self) -> None:
        if self.interval_seconds <= 0.0:
            raise ValueError("reconciliation interval must be positive")
        if self.max_iterations < 0:
            raise ValueError("max_iterations cannot be negative")


class RiftReconciler:
    """Run the orchestrator's idempotent reconcile operation on a bounded loop."""

    def __init__(
        self,
        orchestrator: Any,
        *,
        policy: ReconcilePolicy | None = None,
        on_report: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.orchestrator = orchestrator
        self.policy = policy or ReconcilePolicy()
        self.on_report = on_report

    def reconcile_once(self, *, service_name: str | None = None) -> dict[str, Any]:
        report = self.orchestrator.reconcile(
            service_name=service_name,
            allow_recovery=self.policy.allow_recovery,
        )
        if self.on_report is not None:
            self.on_report(report)
        return report

    def run(
        self,
        stop_event: threading.Event | None = None,
        *,
        service_name: str | None = None,
    ) -> dict[str, Any]:
        event = stop_event or threading.Event()
        reports: list[dict[str, Any]] = []
        completed = 0
        while not event.is_set() and (
            self.policy.max_iterations == 0 or completed < self.policy.max_iterations
        ):
            try:
                report = self.reconcile_once(service_name=service_name)
            except Exception as exc:  # keep the long-lived controller loop alive
                report = {
                    "rift_product": "RIFT",
                    "status": "error",
                    "service": service_name,
                    "error": str(exc),
                }
                if self.on_report is not None:
                    self.on_report(report)
            completed += 1
            if self.policy.max_iterations and len(reports) < 20:
                reports.append(report)
            event.wait(self.policy.interval_seconds)
        return {
            "rift_product": "RIFT",
            "iterations_completed": completed,
            "allow_recovery": self.policy.allow_recovery,
            "interval_seconds": self.policy.interval_seconds,
            "samples": reports,
        }


__all__ = ["ReconcilePolicy", "RiftReconciler"]
