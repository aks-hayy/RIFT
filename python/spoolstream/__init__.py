"""Python entrypoint for the RIFT control plane.

The CUDA/native module is optional. Importing RIFT must remain valid on
controller-only, CPU-only, macOS, and non-NVIDIA installations.
"""

try:
    from ._core import (
        InferenceEngine,
        __version__,
        build_info,
        cuda_device_count,
        inspect_model,
        parse_model_topology,
    )
except ImportError:
    from ._fallback_core import (
        InferenceEngine,
        __version__,
        build_info,
        cuda_device_count,
        inspect_model,
        parse_model_topology,
    )
from .hf_hub import HfHubClient, HubFile
from .artifacts import ArtifactManifest
from .benchmarking import BenchmarkSuite
from .benchmark_catalog import benchmark_site_catalog
from .evidence import EvidenceEngine, EvidenceLevel, EvidenceRecord, aggregate_quality_evidence
from .evidence_sources import BenchmarkEvidenceSource, JsonEvidenceSource
from .gateway import GatewayPolicy, RiftGatewayRuntime
from .orchestrator import ApplyPermissions, RiftOrchestrator
from .state_store import StateConflictError, StateStore
from .system_profile import HardwareAnalyzer
from .runtime_paths import RiftPaths
from .rift import (
    BackendKind,
    DeploymentStrategy,
    RiftCompatibilityLevel,
    RiftEngine,
    RiftMode,
    RiftProductInfo,
    UsabilityVerdict,
)

__all__ = [
    "BackendKind",
    "ApplyPermissions",
    "ArtifactManifest",
    "BenchmarkSuite",
    "benchmark_site_catalog",
    "DeploymentStrategy",
    "HfHubClient",
    "HubFile",
    "EvidenceEngine",
    "EvidenceLevel",
    "EvidenceRecord",
    "aggregate_quality_evidence",
    "BenchmarkEvidenceSource",
    "JsonEvidenceSource",
    "GatewayPolicy",
    "InferenceEngine",
    "RiftCompatibilityLevel",
    "RiftEngine",
    "RiftGatewayRuntime",
    "RiftMode",
    "RiftOrchestrator",
    "StateConflictError",
    "StateStore",
    "RiftProductInfo",
    "UsabilityVerdict",
    "HardwareAnalyzer",
    "RiftPaths",
    "__version__",
    "build_info",
    "cuda_device_count",
    "inspect_model",
    "parse_model_topology",
]
