"""Backend provider registry for RIFT orchestration."""

from __future__ import annotations

from ..adapters.registry import BackendAdapterHost
from .base import BackendProvider, ProviderLifecycleMixin, provider_lifecycle_gate
from .lmcache_aware import LMCacheAwareProvider
from .llama_cpp import LlamaCppProvider
from .mlx_lm import MlxLmProvider
from .sglang import SglangProvider
from .vllm import VllmProvider


def backend_adapter_host(*, load_entry_points: bool = True) -> BackendAdapterHost:
    return BackendAdapterHost(
        builtins=(LlamaCppProvider(), VllmProvider(), SglangProvider(), MlxLmProvider()),
        entry_point_group="rift.backend_adapters",
        load_entry_points=load_entry_points,
    )


def backend_adapter_registry(*, load_entry_points: bool = True) -> dict[str, BackendProvider]:
    return backend_adapter_host(load_entry_points=load_entry_points).enabled()


def overlay_registry() -> dict[str, ProviderLifecycleMixin]:
    overlay = LMCacheAwareProvider()
    return {overlay.name: overlay}


def provider_registry() -> dict[str, BackendProvider]:
    """Compatibility facade retained for one release.

    New recommendation and orchestration code uses backend_adapter_registry and
    keeps optimization overlays separate.
    """
    return {**backend_adapter_registry(), **overlay_registry()}


__all__ = [
    "BackendProvider",
    "ProviderLifecycleMixin",
    "LMCacheAwareProvider",
    "LlamaCppProvider",
    "MlxLmProvider",
    "SglangProvider",
    "VllmProvider",
    "backend_adapter_host",
    "backend_adapter_registry",
    "overlay_registry",
    "provider_registry",
    "provider_lifecycle_gate",
]
