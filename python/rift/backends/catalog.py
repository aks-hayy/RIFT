"""Discovery and lazy loading for first-party backend folders."""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import os
from pathlib import Path
from typing import Any

from ..adapters.contracts import ADAPTER_API_VERSION
from .manifest import BackendManifest, BackendManifestError


class BackendCatalogError(RuntimeError):
    """Raised when a backend folder cannot be loaded."""


@dataclass(frozen=True)
class BackendRegistration:
    manifest: BackendManifest
    folder: Path
    enabled: bool = True
    diagnostics: tuple[str, ...] = ()


class BackendCatalog:
    """Manifest catalog with lazy implementation loading.

    Discovery is intentionally limited to first-party folders. Runtime code is
    imported only after the selector asks for a specific backend.
    """

    def __init__(self, registrations: dict[str, BackendRegistration], diagnostics: tuple[str, ...] = ()):
        self._registrations = dict(registrations)
        self._diagnostics = tuple(diagnostics)

    @classmethod
    def discover(cls, root: Path | str | None = None) -> "BackendCatalog":
        backend_root = Path(root) if root is not None else Path(__file__).resolve().parent
        disabled = {item.strip() for item in os.getenv("RIFT_DISABLED_ADAPTERS", "").split(",") if item.strip()}
        registrations: dict[str, BackendRegistration] = {}
        diagnostics: list[str] = []
        if not backend_root.is_dir():
            return cls({}, (f"backend folder does not exist: {backend_root}",))
        for folder in sorted(item for item in backend_root.iterdir() if item.is_dir() and not item.name.startswith("__")):
            manifest_path = folder / "manifest.json"
            if not manifest_path.is_file():
                diagnostics.append(f"ignored backend folder without manifest: {folder.name}")
                continue
            try:
                manifest = BackendManifest.from_file(manifest_path)
            except BackendManifestError as exc:
                diagnostics.append(str(exc))
                continue
            if manifest.backend_id in registrations:
                diagnostics.append(f"duplicate backend id: {manifest.backend_id}")
                continue
            enabled = manifest.backend_id not in disabled
            folder_diagnostics: list[str] = []
            if manifest.adapter_api_version != ADAPTER_API_VERSION:
                folder_diagnostics.append(
                    f"manifest API {manifest.adapter_api_version} differs from host {ADAPTER_API_VERSION}"
                )
            if not (folder / "__init__.py").is_file():
                folder_diagnostics.append("backend folder is missing __init__.py")
                enabled = False
            registrations[manifest.backend_id] = BackendRegistration(
                manifest=manifest,
                folder=folder,
                enabled=enabled,
                diagnostics=tuple(folder_diagnostics),
            )
        return cls(registrations, tuple(diagnostics))

    def manifests(self) -> dict[str, BackendManifest]:
        return {
            backend_id: registration.manifest
            for backend_id, registration in sorted(self._registrations.items())
            if registration.enabled
        }

    def all(self) -> dict[str, BackendRegistration]:
        return dict(self._registrations)

    def get(self, backend_id: str) -> BackendManifest | None:
        registration = self._registrations.get(str(backend_id))
        return registration.manifest if registration and registration.enabled else None

    def diagnostics(self) -> dict[str, Any]:
        return {
            "adapter_api_version": ADAPTER_API_VERSION,
            "host_diagnostics": list(self._diagnostics),
            "backends": {
                key: {
                    "enabled": value.enabled,
                    "folder": str(value.folder),
                    "manifest": value.manifest.to_dict(),
                    "diagnostics": list(value.diagnostics),
                }
                for key, value in sorted(self._registrations.items())
            },
        }

    def load(self, backend_id: str) -> Any:
        registration = self._registrations.get(str(backend_id))
        if registration is None or not registration.enabled:
            raise BackendCatalogError(f"backend is not registered or is disabled: {backend_id}")
        try:
            module = importlib.import_module(registration.manifest.module)
            factory = getattr(module, registration.manifest.factory)
            provider = factory()
        except (ImportError, AttributeError, TypeError) as exc:
            raise BackendCatalogError(f"failed to load backend {backend_id}: {exc}") from exc
        actual_name = str(getattr(provider, "name", ""))
        if actual_name != registration.manifest.backend_id:
            raise BackendCatalogError(
                f"backend factory identity mismatch: manifest={registration.manifest.backend_id}, provider={actual_name}"
            )
        # The manifest is the source of truth for selection metadata. The
        # provider's class-level manifest remains only as a compatibility
        # fallback for direct legacy imports.
        provider.manifest = registration.manifest.to_adapter_manifest()
        if not all(callable(getattr(provider, method, None)) for method in (
            "probe", "capabilities", "install_plan", "install", "evaluate_fit", "build_launch_spec",
            "launch", "health", "benchmark", "tuning_space", "stop", "recover",
        )):
            raise BackendCatalogError(f"backend {backend_id} does not satisfy the serving contract")
        return provider

    def load_tuning_adapter(self, backend_id: str, provider: Any) -> Any | None:
        registration = self._registrations.get(str(backend_id))
        if registration is None or not registration.enabled or not registration.manifest.tuning_module:
            return None
        try:
            module = importlib.import_module(registration.manifest.tuning_module)
            factory = getattr(module, registration.manifest.tuning_factory)
            adapter = factory(provider)
        except (ImportError, AttributeError, TypeError) as exc:
            raise BackendCatalogError(f"failed to load tuning adapter for {backend_id}: {exc}") from exc
        return adapter


def backend_catalog() -> BackendCatalog:
    return BackendCatalog.discover()


__all__ = ["BackendCatalog", "BackendCatalogError", "BackendRegistration", "backend_catalog"]
