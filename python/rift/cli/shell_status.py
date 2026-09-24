"""Best-effort, read-only live status for the interactive RIFT shell."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from collections import deque
from pathlib import Path
from typing import Any

from rift.runtime_paths import RiftPaths
from rift.telemetry.collectors import LocalCollector


_SPARKS = " ▁▂▃▄▅▆▇█"


def _read_state_database(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    uri = path.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=0.2) as connection:
        row = connection.execute(
            "SELECT payload FROM control_state WHERE id = 1"
        ).fetchone()
    if row is None:
        return None
    value = json.loads(str(row[0]))
    return value if isinstance(value, dict) else None


def _read_state_mirror(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None


def _entries(value: Any) -> list[dict[str, Any]] | None:
    if isinstance(value, dict):
        if any(not isinstance(item, dict) for item in value.values()):
            return None
        return [
            {"name": str(name), **item}
            for name, item in value.items()
        ]
    if isinstance(value, list):
        if any(not isinstance(item, dict) for item in value):
            return None
        return [dict(item) for item in value]
    return None


def _status_from_state(state: dict[str, Any], source: str) -> dict[str, Any]:
    services = _entries(state.get("services"))
    nodes = _entries(state.get("nodes"))
    return {
        "available": True,
        "source": source,
        "service_count": len(services) if services is not None else None,
        "node_count": len(nodes) if nodes is not None else None,
        "services": [
            {
                "name": str(item.get("name") or item.get("id") or "service"),
                "status": str(
                    item.get("phase")
                    or item.get("status")
                    or item.get("health")
                    or "unknown"
                ),
            }
            for item in (services or [])
        ],
        "nodes": [
            {
                "name": str(item.get("name") or item.get("node_id") or item.get("id") or "node"),
                "status": str(item.get("phase") or item.get("status") or "unknown"),
            }
            for item in (nodes or [])
        ],
        "error": None,
    }


def read_status_snapshot(paths: RiftPaths) -> dict[str, Any]:
    """Read persisted service/node state without creating or changing files."""

    try:
        state = _read_state_database(paths.state)
        if state is not None:
            return _status_from_state(state, "sqlite")
    except (OSError, sqlite3.Error, ValueError, TypeError, json.JSONDecodeError):
        pass

    try:
        state = _read_state_mirror(paths.state_mirror)
        if state is not None:
            return _status_from_state(state, "json")
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass

    return {
        "available": False,
        "source": "unavailable",
        "service_count": None,
        "node_count": None,
        "services": [],
        "nodes": [],
        "error": "RIFT state is unavailable",
    }


class StatusCollector:
    """Refresh host readings and persisted RIFT state independently."""

    def __init__(
        self,
        paths: RiftPaths,
        *,
        system_interval: float = 1.0,
        rift_interval: float = 5.0,
        local_collector: LocalCollector | None = None,
        snapshot_reader=read_status_snapshot,
    ) -> None:
        self.paths = paths
        self.system_interval = max(0.1, float(system_interval))
        self.rift_interval = max(0.1, float(rift_interval))
        self._local_collector = local_collector or LocalCollector()
        self._snapshot_reader = snapshot_reader
        self._lock = threading.RLock()
        self._system: dict[str, Any] = {
            "cpu_percent": None,
            "host_ram_pressure_percent": None,
            "gpu_utilization_percent": None,
            "availability": {"host": "warming"},
        }
        self._rift: dict[str, Any] = {
            "available": False,
            "source": "unavailable",
            "service_count": None,
            "node_count": None,
            "services": [],
            "nodes": [],
            "error": "RIFT status has not been sampled",
        }
        self._cpu_history: deque[float] = deque(maxlen=20)
        self._memory_history: deque[float] = deque(maxlen=20)

    def refresh_system(self) -> None:
        try:
            sample = self._local_collector.collect()
            with self._lock:
                self._system = dict(sample)
                cpu = sample.get("cpu_percent")
                memory = sample.get("host_ram_pressure_percent")
                if isinstance(cpu, (int, float)):
                    self._cpu_history.append(float(cpu))
                if isinstance(memory, (int, float)):
                    self._memory_history.append(float(memory))
        except Exception as exc:
            with self._lock:
                self._system = {
                    "cpu_percent": None,
                    "host_ram_pressure_percent": None,
                    "gpu_utilization_percent": None,
                    "availability": {"host": f"unavailable: {exc}"},
                }

    def refresh_rift(self) -> None:
        try:
            value = self._snapshot_reader(self.paths)
        except Exception as exc:
            value = {
                "available": False,
                "source": "unavailable",
                "service_count": None,
                "node_count": None,
                "services": [],
                "nodes": [],
                "error": str(exc),
            }
        with self._lock:
            self._rift = dict(value)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "system": dict(self._system),
                "rift": dict(self._rift),
                "cpu_history": tuple(self._cpu_history),
                "memory_history": tuple(self._memory_history),
            }

    async def run_system(self, stop_event: asyncio.Event) -> None:
        await self._run_periodic(self.refresh_system, self.system_interval, stop_event)

    async def run_rift(self, stop_event: asyncio.Event) -> None:
        await self._run_periodic(self.refresh_rift, self.rift_interval, stop_event)

    @staticmethod
    async def _run_periodic(callback, interval: float, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            await asyncio.to_thread(callback)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass


def _sparkline(values: Any) -> str:
    numbers = [float(value) for value in values if isinstance(value, (int, float))]
    if not numbers:
        return ""
    low = min(numbers)
    high = max(numbers)
    if high == low:
        return _SPARKS[4] * len(numbers)
    span = high - low
    return "".join(_SPARKS[1 + round((value - low) / span * 7)] for value in numbers)


def _percent(value: Any) -> str:
    return f"{round(float(value))}%" if isinstance(value, (int, float)) else "unknown"


def _count(value: Any) -> str:
    return str(value) if isinstance(value, int) else "?"


def format_status_toolbar(snapshot: dict[str, Any], width: int) -> list[tuple[str, str]]:
    """Return a compact prompt_toolkit toolbar that never invents zero values."""

    system = snapshot.get("system") or {}
    rift = snapshot.get("rift") or {}
    cpu = _percent(system.get("cpu_percent"))
    memory = _percent(system.get("host_ram_pressure_percent"))
    gpu = _percent(system.get("gpu_utilization_percent"))
    services = _count(rift.get("service_count"))
    nodes = _count(rift.get("node_count"))
    cpu_graph = _sparkline(snapshot.get("cpu_history"))
    memory_graph = _sparkline(snapshot.get("memory_history"))

    if width >= 88:
        text = (
            f" RIFT  CPU {cpu} {cpu_graph}  MEM {memory} {memory_graph}"
            f"  GPU {gpu}  SERVICES {services}  NODES {nodes} "
        )
    elif width >= 64:
        text = f" RIFT  CPU {cpu}  MEM {memory}  GPU {gpu}  SVC {services}  NODES {nodes} "
    else:
        text = f" RIFT CPU {cpu} MEM {memory} GPU {gpu} SVC {services} NODE {nodes} "
    if len(text) > max(1, width):
        text = text[: max(1, width - 1)] + "…"
    return [("class:bottom-toolbar", text)]


__all__ = ["StatusCollector", "format_status_toolbar", "read_status_snapshot"]
