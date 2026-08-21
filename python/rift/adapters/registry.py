"""Dynamic adapter discovery and manifest-driven compatibility ranking."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.metadata
import os
from pathlib import Path
import platform
from typing import Any, Callable, Iterable

from .contracts import (
    ADAPTER_API_VERSION,
    AdapterDiagnostic,
    AdapterManifest,
    ArtifactAdapter,
    ArtifactVariant,
    BackendAdapter,
    CompatibilityResult,
    JsonDict,
)


class AdapterRegistryError(RuntimeError):
    pass


@dataclass(frozen=True)
class AdapterRegistration:
    adapter: Any
    source: str
    enabled: bool
    diagnostics: tuple[AdapterDiagnostic, ...] = ()


class AdapterRegistry:
    """Registry for built-in and independently packaged RIFT adapters."""

    def __init__(
        self,
        *,
        builtins: Iterable[Any] = (),
        entry_point_group: str,
        disabled: Iterable[str] = (),
        load_entry_points: bool = True,
        strict_conflicts: bool = False,
    ) -> None:
        self.entry_point_group = entry_point_group
        environment_disabled = {
            item.strip()
            for item in os.getenv("RIFT_DISABLED_ADAPTERS", "").split(",")
            if item.strip()
        }
        self.disabled = {str(item) for item in disabled} | environment_disabled
        self.strict_conflicts = bool(strict_conflicts)
        self._registrations: dict[str, AdapterRegistration] = {}
        self._host_diagnostics: list[AdapterDiagnostic] = []
        for adapter in builtins:
            self.register(adapter, source="builtin")
        if load_entry_points:
            self._load_entry_points()

    def register(self, adapter: Any, *, source: str) -> None:
        adapter_id = self._adapter_id(adapter)
        diagnostics = tuple(self._validate(adapter))
        if adapter_id in self._registrations:
            current = self._registrations[adapter_id]
            diagnostic = AdapterDiagnostic(
                "error",
                "ADAPTER_ID_CONFLICT",
                f"Adapter id {adapter_id} was supplied by both {current.source} and {source}; the first registration remains active.",
                "Rename or disable one adapter package with RIFT_DISABLED_ADAPTERS.",
            )
            self._host_diagnostics.append(diagnostic)
            if self.strict_conflicts:
                raise AdapterRegistryError(diagnostic.message)
            return
        self._registrations[adapter_id] = AdapterRegistration(
            adapter=adapter,
            source=source,
            enabled=adapter_id not in self.disabled and not any(
                item.level == "error" for item in diagnostics
            ),
            diagnostics=diagnostics,
        )

    def enabled(self) -> dict[str, Any]:
        return {
            key: registration.adapter
            for key, registration in self._registrations.items()
            if registration.enabled
        }

    def all(self) -> dict[str, AdapterRegistration]:
        return dict(self._registrations)

    def get(self, adapter_id: str) -> Any | None:
        registration = self._registrations.get(adapter_id)
        return registration.adapter if registration and registration.enabled else None

    def diagnostics(self) -> JsonDict:
        return {
            "adapter_api_version": ADAPTER_API_VERSION,
            "entry_point_group": self.entry_point_group,
            "disabled_adapter_ids": sorted(self.disabled),
            "host_diagnostics": [item.to_dict() for item in self._host_diagnostics],
            "adapters": {
                key: {
                    "source": registration.source,
                    "enabled": registration.enabled,
                    "manifest": self._manifest_dict(registration.adapter),
                    "diagnostics": [item.to_dict() for item in registration.diagnostics],
                }
                for key, registration in sorted(self._registrations.items())
            },
        }

    def _load_entry_points(self) -> None:
        try:
            points = importlib.metadata.entry_points()
            selected = points.select(group=self.entry_point_group) if hasattr(points, "select") else points.get(self.entry_point_group, [])
        except Exception as exc:
            raise AdapterRegistryError(f"failed to enumerate {self.entry_point_group}: {exc}") from exc
        for point in selected:
            try:
                loaded = point.load()
                adapter = loaded() if isinstance(loaded, type) or callable(loaded) and not hasattr(loaded, "manifest") else loaded
                self.register(adapter, source=f"entry-point:{point.name}")
            except AdapterRegistryError as exc:
                self._host_diagnostics.append(
                    AdapterDiagnostic("error", "ENTRY_POINT_REGISTRATION_FAILED", str(exc))
                )
            except Exception as exc:
                broken = _BrokenAdapter(point.name, str(exc))
                self.register(broken, source=f"entry-point:{point.name}")

    def _adapter_id(self, adapter: Any) -> str:
        manifest = getattr(adapter, "manifest", None)
        adapter_id = getattr(manifest, "adapter_id", None) or getattr(adapter, "adapter_id", None) or getattr(adapter, "name", None)
        if not adapter_id:
            raise AdapterRegistryError("adapter does not expose an id")
        return str(adapter_id)

    def _validate(self, adapter: Any) -> list[AdapterDiagnostic]:
        manifest = getattr(adapter, "manifest", None)
        diagnostics: list[AdapterDiagnostic] = []
        if not isinstance(manifest, AdapterManifest):
            diagnostics.append(AdapterDiagnostic("error", "INVALID_MANIFEST", "Adapter manifest is missing or invalid."))
            return diagnostics
        if manifest.kind not in ("backend", "artifact", "overlay", "converter"):
            diagnostics.append(AdapterDiagnostic("error", "INVALID_ADAPTER_KIND", f"Unknown adapter kind: {manifest.kind}"))
            return diagnostics
        if manifest.adapter_api_version.split(".", 1)[0] != ADAPTER_API_VERSION.split(".", 1)[0]:
            diagnostics.append(
                AdapterDiagnostic(
                    "error",
                    "ADAPTER_API_INCOMPATIBLE",
                    f"Adapter API {manifest.adapter_api_version} is incompatible with host API {ADAPTER_API_VERSION}.",
                )
            )
        elif manifest.adapter_api_version != ADAPTER_API_VERSION:
            diagnostics.append(
                AdapterDiagnostic(
                    "warning",
                    "ADAPTER_API_MINOR_DIFFERENCE",
                    f"Adapter API {manifest.adapter_api_version} differs from host API {ADAPTER_API_VERSION}; major versions are compatible.",
                )
            )
        required = (
            ("backend", ("probe", "capabilities", "install_plan", "install", "evaluate_fit", "build_launch_spec", "launch", "health", "benchmark", "tuning_space", "stop", "recover")),
            ("artifact", ("detect", "inspect", "resolve_files", "validate", "estimate_resources", "compatible_backends")),
            ("converter", ("can_convert", "plan_conversion", "convert")),
        )
        methods = next((items for kind, items in required if kind == manifest.kind), ())
        missing = [name for name in methods if not callable(getattr(adapter, name, None))]
        if missing:
            diagnostics.append(AdapterDiagnostic("error", "MISSING_METHODS", f"Missing adapter methods: {', '.join(missing)}"))
        return diagnostics

    @staticmethod
    def _manifest_dict(adapter: Any) -> JsonDict | None:
        manifest = getattr(adapter, "manifest", None)
        return manifest.to_dict() if isinstance(manifest, AdapterManifest) else None


class BackendAdapterHost(AdapterRegistry):
    def rank(
        self,
        *,
        artifact: ArtifactVariant | JsonDict,
        hardware: JsonDict,
        workload: str,
        search_root: str | Path | None = None,
        detection_cache: dict[str, JsonDict] | None = None,
    ) -> list[CompatibilityResult]:
        artifact_dict = artifact.to_dict() if isinstance(artifact, ArtifactVariant) else dict(artifact)
        fmt = str(artifact_dict.get("format") or "unknown").lower()
        quant = str(artifact_dict.get("quantization") or "").lower()
        architecture = str(artifact_dict.get("architecture") or "unknown").lower()
        validation = artifact_dict.get("validation") if isinstance(artifact_dict.get("validation"), dict) else {}
        artifact_ready = bool(validation.get("serving_ready", validation.get("valid", True)))
        results: list[CompatibilityResult] = []
        for adapter_id, adapter in self.enabled().items():
            manifest: AdapterManifest = adapter.manifest
            cap = manifest.capability
            task_supported = self._task_supported(cap.tasks, workload)
            format_supported = fmt in {item.lower() for item in cap.formats}
            advertised_quants = {item.lower() for item in cap.quantizations}
            quant_supported = (
                not quant
                or not advertised_quants
                or quant in advertised_quants
                or any(quant.startswith(f"{item}_") for item in advertised_quants)
            )
            architecture_supported = "*" in cap.architectures or architecture in {item.lower() for item in cap.architectures}
            platform_supported, platform_reason = self._platform_supported(cap.operating_systems, hardware)
            try:
                fit = adapter.evaluate_fit(artifact=artifact_dict, hardware=hardware, workload=workload)
            except Exception as exc:
                fit = {"fits": False, "reason": f"adapter fit evaluation failed: {exc}"}
            probe_root = str(Path(search_root or Path.cwd() / ".rift" / "backends") / adapter_id)
            cache_key = f"{adapter_id}:{probe_root}"
            if detection_cache is not None and cache_key in detection_cache:
                detection = dict(detection_cache[cache_key])
            else:
                try:
                    detection = adapter.probe(search_root=probe_root)
                except Exception as exc:
                    detection = {"available": False, "error": str(exc)}
                if detection_cache is not None:
                    detection_cache[cache_key] = dict(detection)
            installed = bool(detection.get("available"))
            runtime_supported = True
            feature_probe = detection.get("runtime_feature_probe") if isinstance(detection.get("runtime_feature_probe"), dict) else {}
            probed_flags = feature_probe.get("flags") if isinstance(feature_probe.get("flags"), dict) else {}
            if installed and quant and "--quantization" in probed_flags and not probed_flags["--quantization"]:
                runtime_supported = False
            compatible = (
                artifact_ready
                and task_supported
                and format_supported
                and quant_supported
                and architecture_supported
                and platform_supported
                and runtime_supported
                and bool(fit.get("fits"))
            )
            support = "AVAILABLE_NOW" if compatible and installed else "INSTALLABLE_BACKEND" if compatible else "UNSUPPORTED"
            reasons = [str(fit.get("reason") or "No adapter fit explanation was returned.")]
            if not artifact_ready:
                missing = ", ".join(str(item) for item in validation.get("missing_dependencies") or [])
                reasons.append(
                    "Artifact validation did not prove serving readiness."
                    + (f" Missing: {missing}." if missing else "")
                )
            if not task_supported:
                reasons.append(f"{adapter_id} does not advertise workload task {workload}.")
            if not format_supported:
                reasons.append(f"{adapter_id} does not advertise artifact format {fmt}.")
            if not quant_supported:
                reasons.append(f"{adapter_id} does not advertise quantization {quant}.")
            if not architecture_supported:
                reasons.append(f"{adapter_id} does not advertise architecture {architecture}.")
            if not platform_supported:
                reasons.append(platform_reason)
            if not runtime_supported:
                reasons.append(
                    "The detected backend version does not expose its documented quantization launch option."
                )
            elif installed and detection.get("version"):
                reasons.append(f"Detected upstream backend version: {detection['version']}.")
            reasons.append("Backend is detected." if installed else "Backend installation is required.")
            score = (
                (0.16 if task_supported else 0.0)
                + (0.10 if artifact_ready else 0.0)
                + (0.32 if format_supported else 0.0)
                + (0.10 if quant_supported else 0.0)
                + (0.08 if architecture_supported else 0.0)
                + (0.15 if platform_supported else 0.0)
                + (0.05 if runtime_supported else 0.0)
                + (0.18 if fit.get("fits") else 0.0)
                + (0.07 if installed else 0.0)
                + self._workload_bonus(adapter_id, workload)
            )
            results.append(
                CompatibilityResult(
                    adapter_id=adapter_id,
                    compatible=compatible,
                    platform_supported=platform_supported,
                    hardware_fit=bool(fit.get("fits")),
                    installed=installed,
                    support_level=support,
                    score=round(score, 6),
                    reasons=tuple(reasons),
                )
            )
        results.sort(key=lambda item: (not item.compatible, -item.score, item.adapter_id))
        return results

    @staticmethod
    def _task_supported(advertised: tuple[str, ...], workload: str) -> bool:
        tasks = {str(item).strip().lower() for item in advertised}
        if "*" in tasks:
            return True
        requested = str(workload or "chat").strip().lower()
        aliases = {
            "code": {"coding", "chat", "completion"},
            "coding": {"coding", "chat", "completion"},
            "general": {"chat", "completion"},
            "text-generation": {"chat", "completion"},
            "embedding": {"embeddings"},
            "feature-extraction": {"embeddings"},
            "reranker": {"reranking"},
            "rerank": {"reranking"},
            "vlm": {"vision-language"},
            "image-text-to-text": {"vision-language"},
            "agent": {"tool-use", "structured", "chat"},
        }
        accepted = aliases.get(requested, {requested})
        return bool(tasks.intersection(accepted))

    @staticmethod
    def _platform_supported(supported: tuple[str, ...], hardware: JsonDict) -> tuple[bool, str]:
        if not supported:
            return True, "Adapter does not restrict the host operating system."
        identity = hardware.get("identity") if isinstance(hardware.get("identity"), dict) else {}
        current = str(identity.get("os") or platform.system() or os.name).lower()
        aliases = {"windows": "windows", "nt": "windows", "linux": "linux", "darwin": "macos", "macos": "macos"}
        current = aliases.get(current, current)
        allowed = {aliases.get(str(item).lower(), str(item).lower()) for item in supported}
        if current == "windows" and "wsl2" in allowed:
            if hardware.get("wsl_available"):
                return True, "Adapter can use the detected WSL2 execution path."
            if "container" in allowed and hardware.get("container_runtime_available"):
                return True, "Adapter can use the detected container runtime on Windows."
            return False, "Adapter requires WSL2 or a supported container runtime on Windows; neither is detected."
        if current in allowed or "*" in allowed:
            return True, f"Host platform {current} is supported."
        if "container" in allowed:
            if hardware.get("container_runtime_available"):
                return True, "Adapter can use the detected container runtime."
            return False, "Adapter requires a supported container runtime, which is not currently detected."
        return False, f"Host platform {current} is not in the adapter platform set: {', '.join(sorted(allowed))}."

    @staticmethod
    def _workload_bonus(adapter_id: str, workload: str) -> float:
        key = workload.lower()
        if adapter_id == "sglang" and key in {"agent", "structured", "coding", "tool-use"}:
            return 0.06
        if adapter_id == "vllm" and key in {"throughput", "batch", "chat", "completion"}:
            return 0.04
        if adapter_id == "mlx-lm" and key in {"chat", "coding"}:
            return 0.03
        if adapter_id == "llama.cpp":
            return 0.02
        return 0.0


class _BrokenAdapter:
    def __init__(self, name: str, error: str) -> None:
        self.name = name
        self.manifest = AdapterManifest(
            adapter_id=name,
            display_name=name,
            upstream_project="unknown",
            adapter_version="0",
            adapter_api_version=ADAPTER_API_VERSION,
            kind="broken",
            capability=_empty_capability(),
            evidence_status="broken",
            description=error,
        )


def _empty_capability():
    from .contracts import BackendCapability

    return BackendCapability(tasks=(), formats=())


__all__ = [
    "AdapterRegistration",
    "AdapterRegistry",
    "AdapterRegistryError",
    "BackendAdapterHost",
]
