"""Standards-oriented telemetry exporters with bounded failure behavior."""

from __future__ import annotations

import json
from queue import Empty, Full, Queue
import threading
from typing import Any
from urllib.request import Request, urlopen


class PrometheusExporter:
    @staticmethod
    def render(samples: list[dict[str, Any]]) -> str:
        mapping = {
            "cpu_percent": ("rift_telemetry_cpu_utilization_percent", "gauge"),
            "process_cpu_percent": ("rift_telemetry_service_cpu_utilization_percent", "gauge"),
            "host_ram_available_bytes": ("rift_telemetry_host_ram_available_bytes", "gauge"),
            "host_ram_pressure_percent": ("rift_telemetry_host_ram_pressure_percent", "gauge"),
            "cpu_temperature_c": ("rift_telemetry_cpu_temperature_celsius", "gauge"),
            "process_rss_bytes": ("rift_telemetry_service_memory_bytes", "gauge"),
            "gpu_utilization_percent": ("rift_telemetry_gpu_utilization_percent", "gauge"),
            "gpu_temperature_c": ("rift_telemetry_gpu_temperature_celsius", "gauge"),
            "gpu_vram_used_bytes": ("rift_telemetry_gpu_vram_used_bytes", "gauge"),
            "gpu_vram_pressure_percent": ("rift_telemetry_gpu_vram_pressure_percent", "gauge"),
            "gpu_power_watts": ("rift_telemetry_gpu_power_watts", "gauge"),
        }
        lines: list[str] = []
        declared: set[str] = set()
        for item in samples:
            labels = item.get("labels") or {}
            label_text = ",".join(f'{key}="{str(value).replace(chr(34), chr(92) + chr(34))}"' for key, value in sorted(labels.items()))
            label_text = "{" + label_text + "}" if label_text else ""
            sample = item.get("sample") or item
            for key, (name, kind) in mapping.items():
                value = sample.get(key)
                if not isinstance(value, (int, float)):
                    continue
                if name not in declared:
                    lines.extend((f"# HELP {name} RIFT resource telemetry", f"# TYPE {name} {kind}"))
                    declared.add(name)
                lines.append(f"{name}{label_text} {float(value)}")
        return "\n".join(lines) + ("\n" if lines else "")


class OtlpHttpExporter:
    """Optional OTLP/HTTP JSON forwarder; drops oldest data under pressure."""

    def __init__(self, endpoint: str, *, max_queue: int = 1024, timeout_seconds: float = 5.0) -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.queue: Queue[dict[str, Any]] = Queue(maxsize=max_queue)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="rift-otlp", daemon=True)
        self._thread.start()

    def submit(self, payload: dict[str, Any]) -> bool:
        try:
            self.queue.put_nowait(payload)
            return True
        except Full:
            try:
                self.queue.get_nowait()
                self.queue.put_nowait(payload)
                return False
            except (Empty, Full):
                return False

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=self.timeout_seconds + 1.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                payload = self.queue.get(timeout=0.2)
            except Empty:
                continue
            try:
                request = Request(self.endpoint, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
                with urlopen(request, timeout=self.timeout_seconds):
                    pass
            except Exception:
                # Export must never affect service availability. The durable
                # RIFT store remains the source of truth for replay/export.
                continue


__all__ = ["OtlpHttpExporter", "PrometheusExporter"]
