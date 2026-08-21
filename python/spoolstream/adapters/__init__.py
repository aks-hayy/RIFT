"""RIFT adapter contracts, dynamic registries, and built-in hosts."""

from .contracts import *
from .artifacts import (
    ArtifactAdapterHost,
    artifact_adapter_host,
    builtin_artifact_adapters,
    source_from_candidate,
    source_from_local,
)
from .registry import AdapterRegistration, AdapterRegistry, AdapterRegistryError, BackendAdapterHost
from .conformance import BackendConformanceSuite, ConformanceCheck

__all__ = [
    "AdapterRegistration",
    "AdapterRegistry",
    "AdapterRegistryError",
    "ArtifactAdapterHost",
    "BackendAdapterHost",
    "BackendConformanceSuite",
    "ConformanceCheck",
    "artifact_adapter_host",
    "builtin_artifact_adapters",
    "source_from_candidate",
    "source_from_local",
]
