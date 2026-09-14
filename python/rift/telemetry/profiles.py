"""Metric catalog and low-overhead collection profiles.

Profiles describe what RIFT records for a service.  The collector may expose
more fields than a service selected; filtering happens before persistence so
the same telemetry store and API can serve both minimal and detailed runs.
"""

from __future__ import annotations

from typing import Any, Iterable


DEFAULT_PROFILE = "default"


_METRIC_CATALOG: dict[str, dict[str, Any]] = {
    "cpu_percent": {
        "label": "Host CPU utilization",
        "description": "Total host CPU utilization.",
        "unit": "%",
        "kind": "gauge",
        "scope": "host",
        "source": "local",
        "default": True,
    },
    "process_cpu_percent": {
        "label": "Service CPU utilization",
        "description": "CPU utilization of the service process tree.",
        "unit": "%",
        "kind": "gauge",
        "scope": "service",
        "source": "local",
        "default": True,
    },
    "process_rss_bytes": {
        "label": "Service memory",
        "description": "Resident memory used by the service process tree.",
        "unit": "bytes",
        "kind": "gauge",
        "scope": "service",
        "source": "local",
        "default": True,
    },
    "host_ram_pressure_percent": {
        "label": "Host RAM pressure",
        "description": "Host virtual-memory pressure percentage.",
        "unit": "%",
        "kind": "gauge",
        "scope": "host",
        "source": "local",
        "default": True,
    },
    "cpu_temperature_c": {
        "label": "CPU temperature",
        "description": "Best-effort CPU/package temperature when a host sensor is available.",
        "unit": "°C",
        "kind": "gauge",
        "scope": "host",
        "source": "local",
        "default": False,
    },
    "gpu_utilization_percent": {
        "label": "GPU utilization",
        "description": "Primary GPU utilization percentage.",
        "unit": "%",
        "kind": "gauge",
        "scope": "node",
        "source": "nvidia-smi",
        "default": True,
    },
    "gpu_temperature_c": {
        "label": "GPU temperature",
        "description": "Primary GPU temperature.",
        "unit": "°C",
        "kind": "gauge",
        "scope": "node",
        "source": "nvidia-smi",
        "default": False,
    },
    "gpu_vram_used_bytes": {
        "label": "GPU VRAM used",
        "description": "Aggregate VRAM used by visible GPUs.",
        "unit": "bytes",
        "kind": "gauge",
        "scope": "node",
        "source": "nvidia-smi",
        "default": False,
    },
    "gpu_vram_pressure_percent": {
        "label": "GPU VRAM pressure",
        "description": "Aggregate visible GPU VRAM pressure percentage.",
        "unit": "%",
        "kind": "gauge",
        "scope": "node",
        "source": "nvidia-smi",
        "default": True,
    },
    "gpu_power_watts": {
        "label": "GPU power",
        "description": "Aggregate GPU power draw; energy is derived from this series.",
        "unit": "W",
        "kind": "gauge",
        "scope": "node",
        "source": "nvidia-smi",
        "default": True,
    },
    "request.error_ratio": {
        "label": "Request error ratio",
        "description": "Failed gateway requests divided by completed gateway requests.",
        "unit": "ratio",
        "kind": "gauge",
        "scope": "service",
        "source": "rift-gateway",
        "default": False,
    },
    "service.availability_ratio": {
        "label": "Service availability ratio",
        "description": "Successful gateway requests divided by all gateway requests.",
        "unit": "ratio",
        "kind": "gauge",
        "scope": "service",
        "source": "rift-gateway",
        "default": False,
    },
    "request.average_latency_seconds": {
        "label": "Average request latency",
        "description": "Average completed gateway request latency.",
        "unit": "s",
        "kind": "gauge",
        "scope": "service",
        "source": "rift-gateway",
        "default": False,
    },
    "request.last_latency_seconds": {
        "label": "Last request latency",
        "description": "Latency of the most recently completed gateway request.",
        "unit": "s",
        "kind": "gauge",
        "scope": "service",
        "source": "rift-gateway",
        "default": False,
    },
}


_PROFILE_CATALOG: dict[str, dict[str, Any]] = {
    "minimal": {
        "name": "Minimal",
        "description": "Low-overhead service and accelerator health.",
        "metrics": [
            "process_cpu_percent",
            "process_rss_bytes",
            "gpu_utilization_percent",
            "gpu_vram_pressure_percent",
        ],
    },
    DEFAULT_PROFILE: {
        "name": "Default",
        "description": "Balanced live resource telemetry for normal deployments.",
        "metrics": [key for key, value in _METRIC_CATALOG.items() if value.get("default")],
    },
    "performance": {
        "name": "Performance",
        "description": "Adds host pressure signals for diagnosing contention.",
        "metrics": list(_METRIC_CATALOG),
    },
    "cost": {
        "name": "Cost",
        "description": "Power and memory signals for energy and capacity accounting.",
        "metrics": [
            "process_cpu_percent",
            "process_rss_bytes",
            "host_ram_pressure_percent",
            "gpu_vram_used_bytes",
            "gpu_vram_pressure_percent",
            "gpu_power_watts",
        ],
    },
}


def metric_catalog() -> dict[str, dict[str, Any]]:
    """Return a JSON-safe copy of the available Stage 1 metric catalog."""

    return {key: dict(value, id=key) for key, value in _METRIC_CATALOG.items()}


def profile_catalog() -> dict[str, dict[str, Any]]:
    """Return a JSON-safe copy of the built-in profile catalog."""

    return {
        key: dict(value, id=key, metrics=list(value["metrics"]))
        for key, value in _PROFILE_CATALOG.items()
    }


def _metric_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        values: Iterable[Any] = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        raise ValueError("telemetry metrics must be an array or comma-separated string")
    result = []
    for item in values:
        metric = str(item).strip()
        if metric and metric not in result:
            result.append(metric)
    return result


def resolve_selection(resources: dict[str, Any] | None = None) -> dict[str, Any]:
    """Normalize a service resource selection into a profile and metric list."""

    values = resources if isinstance(resources, dict) else {}
    profile = str(values.get("profile") or DEFAULT_PROFILE).strip().lower()
    explicit = _metric_list(values.get("metrics"))
    if explicit is None:
        if profile == "custom":
            raise ValueError("custom telemetry profile requires metrics")
        selected = list(_PROFILE_CATALOG.get(profile, {}).get("metrics") or [])
        if profile not in _PROFILE_CATALOG:
            raise ValueError(f"unknown telemetry profile: {profile}")
    else:
        selected = explicit
        if profile not in _PROFILE_CATALOG and profile != "custom":
            raise ValueError(f"unknown telemetry profile: {profile}")
    unknown = [metric for metric in selected if metric not in _METRIC_CATALOG]
    if unknown:
        raise ValueError(f"unknown telemetry metric: {unknown[0]}")
    if not selected:
        raise ValueError("telemetry metrics must not be empty")
    return {"profile": profile, "metrics": selected}


_IDENTITY_FIELDS = {
    "observed_at",
    "service_name",
    "process_id",
    "collector",
    "collection_interval_seconds",
}


def filter_sample(sample: dict[str, Any], metrics: Iterable[str] | None) -> dict[str, Any]:
    """Keep identity fields and selected metric fields before persistence."""

    if metrics is None:
        return dict(sample)
    selected = set(metrics)
    result = {key: value for key, value in sample.items() if key in _IDENTITY_FIELDS or key in selected}
    availability = sample.get("availability")
    if isinstance(availability, dict):
        categories: set[str] = set()
        if selected.intersection({"cpu_percent", "process_cpu_percent"}):
            categories.add("cpu")
        if selected.intersection({"process_cpu_percent", "process_rss_bytes"}):
            categories.add("process")
        if selected.intersection({"host_ram_pressure_percent"}):
            categories.add("host_ram")
        if "cpu_temperature_c" in selected:
            categories.add("cpu_temperature")
        if selected.intersection({
            "gpu_utilization_percent",
            "gpu_temperature_c",
            "gpu_vram_used_bytes",
            "gpu_vram_pressure_percent",
            "gpu_power_watts",
        }):
            categories.add("gpu")
        result["availability"] = {key: value for key, value in availability.items() if key in categories}
    return result


__all__ = [
    "DEFAULT_PROFILE",
    "filter_sample",
    "metric_catalog",
    "profile_catalog",
    "resolve_selection",
]
