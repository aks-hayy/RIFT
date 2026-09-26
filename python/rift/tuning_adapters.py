"""Compatibility facade for backend-owned tuning adapters.

New first-party adapters live under ``rift.backends.<backend>.tuning``.  This
module remains as a small import-compatible facade for existing callers and
external extensions while the catalog is the source of discovery.
"""
from __future__ import annotations

from typing import Any

from .tuning_base import (
    BackendTuningAdapter,
    IDENTITY_KEYS,
    Parameter,
    accelerator_family,
    canonical_hash,
)
from .backends.llama_cpp.tuning import LlamaCppTuningAdapter
from .backends.vllm.tuning import VLLM_PARAMETERS, VllmTuningAdapter


class TuningAdapterRegistry:
    """Compatibility registry for explicitly registered extensions."""

    def __init__(self) -> None:
        self._types: dict[str, type[BackendTuningAdapter]] = {}

    def register(self, backend: str, adapter_type: type[BackendTuningAdapter]) -> None:
        if not backend.strip() or not issubclass(adapter_type, BackendTuningAdapter):
            raise ValueError("a backend id and BackendTuningAdapter subclass are required")
        self._types[backend.strip()] = adapter_type

    def create(self, backend: str, provider: Any) -> BackendTuningAdapter | None:
        adapter_type = self._types.get(str(backend).strip())
        return adapter_type(provider) if adapter_type else None


_REGISTRY = TuningAdapterRegistry()


def tuning_adapter(backend: str, provider: Any) -> BackendTuningAdapter | None:
    try:
        from .backends import BackendCatalogError, backend_catalog

        adapter = backend_catalog().load_tuning_adapter(backend, provider)
        if adapter is not None:
            return adapter
    except (BackendCatalogError, ImportError):
        pass
    return _REGISTRY.create(backend, provider)


def register_tuning_adapter(backend: str, adapter_type: type[BackendTuningAdapter]) -> None:
    _REGISTRY.register(backend, adapter_type)


__all__ = [
    "BackendTuningAdapter",
    "IDENTITY_KEYS",
    "LlamaCppTuningAdapter",
    "Parameter",
    "VLLM_PARAMETERS",
    "VllmTuningAdapter",
    "accelerator_family",
    "canonical_hash",
    "register_tuning_adapter",
    "tuning_adapter",
]
