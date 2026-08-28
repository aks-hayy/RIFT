"""Backend-neutral resource telemetry for RIFT-managed services.

The package deliberately keeps collection, persistence, policy and exports
separate.  A provider only has to expose a PID (or a future runtime scope);
the same supervisor can then observe llama.cpp, vLLM, or any other service.
"""

from .collectors import LocalCollector
from .exporters import OtlpHttpExporter, PrometheusExporter
from .forwarding import TelemetryForwarder
from .lifecycle import TelemetrySupervisor
from .policy import ResourcePolicy
from .store import TelemetryStore

__all__ = ["LocalCollector", "OtlpHttpExporter", "PrometheusExporter", "ResourcePolicy", "TelemetryForwarder", "TelemetryStore", "TelemetrySupervisor"]
