"""Backend-neutral resource telemetry for RIFT-managed services.

The package deliberately keeps collection, persistence, policy and exports
separate.  A provider only has to expose a PID (or a future runtime scope);
the same supervisor can then observe llama.cpp, vLLM, or any other service.
"""

from .collectors import LocalCollector
from .alerts import AlertDispatcher, MemoryAlertAdapter, WebhookAlertAdapter
from .exporters import OtlpHttpExporter, PrometheusExporter
from .forwarding import TelemetryForwarder
from .lifecycle import TelemetrySupervisor
from .objectives import AGGREGATIONS, OPERATORS, ObjectiveEvaluator, normalize_objectives, required_metrics
from .policy import ResourcePolicy
from .profiles import DEFAULT_PROFILE, filter_sample, metric_catalog, profile_catalog, resolve_selection
from .store import TelemetryStore

__all__ = [
    "DEFAULT_PROFILE",
    "AlertDispatcher",
    "MemoryAlertAdapter",
    "WebhookAlertAdapter",
    "LocalCollector",
    "OtlpHttpExporter",
    "PrometheusExporter",
    "ResourcePolicy",
    "TelemetryForwarder",
    "TelemetryStore",
    "TelemetrySupervisor",
    "ObjectiveEvaluator",
    "AGGREGATIONS",
    "OPERATORS",
    "normalize_objectives",
    "required_metrics",
    "filter_sample",
    "metric_catalog",
    "profile_catalog",
    "resolve_selection",
]
