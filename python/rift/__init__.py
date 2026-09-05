"""Public, pure-Python RIFT control-plane facade.

The optional native runtime is deliberately isolated behind ``rift._core``.
Controller, discovery, planning, and operations remain importable on machines
without CUDA or a native compiler toolchain.
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

from .artifacts import ArtifactManifest
from .benchmark_catalog import benchmark_site_catalog
from .benchmarking import BenchmarkSuite
from .benchmark_suite import (
    BenchmarkSpec,
    BenchmarkSuiteRunner,
    ResearchProtocol,
    bootstrap_confidence_interval,
    compile_benchmark_plan,
    factorial_effects,
    paired_effect,
    profile_catalog,
)
from .evidence import EvidenceEngine, EvidenceLevel, EvidenceRecord, aggregate_quality_evidence
from .evidence_sources import BenchmarkEvidenceSource, JsonEvidenceSource
from .gateway import GatewayPolicy, RiftGatewayRuntime
from .orchestrator import ApplyPermissions, RiftOrchestrator
from .rift import (
    BackendKind,
    DeploymentStrategy,
    RiftCompatibilityLevel,
    RiftEngine,
    RiftMode,
    RiftProductInfo,
    UsabilityVerdict,
)
from .hf_hub import HfHubClient, HubFile
from .runtime_paths import RiftPaths
from .reconciliation import ReconcilePolicy, RiftReconciler
from .state_store import StateConflictError, StateStore
from .system_profile import HardwareAnalyzer

__all__ = [
    "ApplyPermissions",
    "ArtifactManifest",
    "BackendKind",
    "BenchmarkSuite",
    "BenchmarkSpec",
    "BenchmarkSuiteRunner",
    "ResearchProtocol",
    "BenchmarkEvidenceSource",
    "DeploymentStrategy",
    "EvidenceEngine",
    "EvidenceLevel",
    "EvidenceRecord",
    "GatewayPolicy",
    "HfHubClient",
    "HubFile",
    "InferenceEngine",
    "JsonEvidenceSource",
    "RiftCompatibilityLevel",
    "RiftEngine",
    "RiftGatewayRuntime",
    "RiftMode",
    "RiftOrchestrator",
    "RiftPaths",
    "ReconcilePolicy",
    "RiftReconciler",
    "RiftProductInfo",
    "StateConflictError",
    "StateStore",
    "UsabilityVerdict",
    "HardwareAnalyzer",
    "aggregate_quality_evidence",
    "benchmark_site_catalog",
    "bootstrap_confidence_interval",
    "compile_benchmark_plan",
    "factorial_effects",
    "paired_effect",
    "profile_catalog",
    "build_info",
    "cuda_device_count",
    "inspect_model",
    "parse_model_topology",
    "__version__",
]
