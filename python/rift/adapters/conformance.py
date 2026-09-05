"""Reusable conformance gates for built-in and third-party RIFT adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import ADAPTER_API_VERSION, AdapterManifest, JsonDict


@dataclass(frozen=True)
class ConformanceCheck:
    name: str
    passed: bool
    detail: str

    def to_dict(self) -> JsonDict:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


class BackendConformanceSuite:
    """Exercise the side-effect-free adapter surface and optional fake lifecycle."""

    required_methods = (
        "probe",
        "capabilities",
        "install_plan",
        "install",
        "evaluate_fit",
        "build_launch_spec",
        "launch",
        "health",
        "benchmark",
        "tuning_space",
        "stop",
        "recover",
    )

    def run(
        self,
        adapter: Any,
        *,
        artifact: JsonDict | None = None,
        hardware: JsonDict | None = None,
        exercise_fake_lifecycle: bool = False,
    ) -> JsonDict:
        checks: list[ConformanceCheck] = []
        manifest = getattr(adapter, "manifest", None)
        checks.append(
            ConformanceCheck(
                "manifest",
                isinstance(manifest, AdapterManifest),
                "AdapterManifest is present." if isinstance(manifest, AdapterManifest) else "AdapterManifest is missing.",
            )
        )
        api_compatible = bool(
            isinstance(manifest, AdapterManifest)
            and manifest.adapter_api_version.split(".", 1)[0]
            == ADAPTER_API_VERSION.split(".", 1)[0]
        )
        checks.append(
            ConformanceCheck(
                "api_version",
                api_compatible,
                f"host={ADAPTER_API_VERSION}, adapter={getattr(manifest, 'adapter_api_version', None)}",
            )
        )
        missing = [name for name in self.required_methods if not callable(getattr(adapter, name, None))]
        checks.append(
            ConformanceCheck(
                "method_contract",
                not missing,
                "complete" if not missing else f"missing: {', '.join(missing)}",
            )
        )
        if missing or not isinstance(manifest, AdapterManifest):
            return self._report(adapter, checks)

        artifact = artifact or {
            "artifact_id": "conformance:tiny",
            "format": manifest.capability.formats[0] if manifest.capability.formats else "unknown",
            "quantization": manifest.capability.quantizations[0] if manifest.capability.quantizations else None,
            "architecture": "llama",
            "total_bytes": 64 * 1024**2,
        }
        hardware = hardware or {
            "cuda_available": True,
            "total_vram_bytes": 24 * 1024**3,
            "free_vram_bytes": 22 * 1024**3,
            "total_host_ram_bytes": 64 * 1024**3,
            "identity": {"os": "linux", "architecture": "x86_64"},
        }
        operations = (
            ("probe_result", lambda: adapter.probe(search_root=".rift/backends/conformance"), dict),
            ("capabilities_result", adapter.capabilities, dict),
            ("install_plan_result", adapter.install_plan, dict),
            (
                "fit_result",
                lambda: adapter.evaluate_fit(artifact=artifact, hardware=hardware, workload="chat"),
                dict,
            ),
            (
                "launch_spec_result",
                lambda: adapter.build_launch_spec(
                    model_path="conformance-model",
                    host="127.0.0.1",
                    port=11999,
                    context_length=512,
                    concurrency=1,
                    hardware=hardware,
                    tuning={},
                ),
                dict,
            ),
        )
        launch_spec: JsonDict = {}
        for name, operation, expected in operations:
            try:
                result = operation()
                passed = isinstance(result, expected)
                if name == "launch_spec_result" and passed:
                    launch_spec = result
                    passed = bool(result.get("command")) and bool(result.get("api_base"))
                checks.append(ConformanceCheck(name, passed, type(result).__name__))
            except Exception as exc:
                checks.append(ConformanceCheck(name, False, str(exc)))

        try:
            tuning = adapter.tuning_space(launch_plan=launch_spec, hardware=hardware)
            checks.append(ConformanceCheck("tuning_space_result", isinstance(tuning, list), type(tuning).__name__))
        except Exception as exc:
            checks.append(ConformanceCheck("tuning_space_result", False, str(exc)))

        install_plan = adapter.install_plan()
        checks.append(
            ConformanceCheck(
                "permissioned_install",
                bool(install_plan.get("requires_permission")),
                "install plan declares an explicit permission requirement",
            )
        )
        if exercise_fake_lifecycle and launch_spec:
            self._exercise_lifecycle(adapter, launch_spec, checks)
        return self._report(adapter, checks)

    def _exercise_lifecycle(
        self,
        adapter: Any,
        launch_spec: JsonDict,
        checks: list[ConformanceCheck],
    ) -> None:
        runtime: JsonDict = {}
        operations = (
            ("launch", lambda: adapter.launch(launch_spec), dict),
            ("health", lambda: adapter.health(base_url=launch_spec["api_base"]), dict),
            (
                "benchmark",
                lambda: adapter.benchmark(
                    base_url=launch_spec["api_base"], prompt="RIFT conformance", max_tokens=4
                ),
                dict,
            ),
        )
        for name, operation, expected in operations:
            try:
                value = operation()
                if name == "launch":
                    runtime = value
                checks.append(ConformanceCheck(name, isinstance(value, expected), type(value).__name__))
            except Exception as exc:
                checks.append(ConformanceCheck(name, False, str(exc)))
        if runtime.get("pid"):
            try:
                value = adapter.stop(pid=int(runtime["pid"]))
                checks.append(ConformanceCheck("stop", isinstance(value, dict), type(value).__name__))
            except Exception as exc:
                checks.append(ConformanceCheck("stop", False, str(exc)))
        try:
            value = adapter.recover(launch_spec)
            checks.append(ConformanceCheck("recover", isinstance(value, dict), type(value).__name__))
        except Exception as exc:
            checks.append(ConformanceCheck("recover", False, str(exc)))

    @staticmethod
    def _report(adapter: Any, checks: list[ConformanceCheck]) -> JsonDict:
        failed = [item for item in checks if not item.passed]
        return {
            "adapter_id": getattr(getattr(adapter, "manifest", None), "adapter_id", getattr(adapter, "name", "unknown")),
            "passed": not failed,
            "checks": [item.to_dict() for item in checks],
            "failed_checks": [item.name for item in failed],
        }


class ArtifactConformanceSuite:
    """Validate exact-artifact adapters without relying on RIFT core maps."""

    required_methods = (
        "detect",
        "inspect",
        "resolve_files",
        "validate",
        "estimate_resources",
        "compatible_backends",
    )

    def run(
        self,
        adapter: Any,
        *,
        source: JsonDict,
        hardware: JsonDict | None = None,
    ) -> JsonDict:
        checks: list[ConformanceCheck] = []
        manifest = getattr(adapter, "manifest", None)
        manifest_valid = isinstance(manifest, AdapterManifest) and manifest.kind == "artifact"
        checks.append(
            ConformanceCheck(
                "manifest",
                manifest_valid,
                "artifact AdapterManifest is present" if manifest_valid else "artifact manifest is missing or has the wrong kind",
            )
        )
        api_compatible = bool(
            manifest_valid
            and manifest.adapter_api_version.split(".", 1)[0]
            == ADAPTER_API_VERSION.split(".", 1)[0]
        )
        checks.append(
            ConformanceCheck(
                "api_version",
                api_compatible,
                f"host={ADAPTER_API_VERSION}, adapter={getattr(manifest, 'adapter_api_version', None)}",
            )
        )
        missing = [name for name in self.required_methods if not callable(getattr(adapter, name, None))]
        checks.append(
            ConformanceCheck(
                "method_contract",
                not missing,
                "complete" if not missing else f"missing: {', '.join(missing)}",
            )
        )
        if missing or not api_compatible:
            return self._report(adapter, checks)
        try:
            detected = adapter.detect(source)
            checks.append(ConformanceCheck("detect", detected is True, str(detected)))
        except Exception as exc:
            checks.append(ConformanceCheck("detect", False, str(exc)))
            return self._report(adapter, checks)
        try:
            variants = adapter.inspect(source)
            checks.append(
                ConformanceCheck(
                    "inspect",
                    isinstance(variants, list) and bool(variants),
                    f"variant_count={len(variants) if isinstance(variants, list) else 'invalid'}",
                )
            )
        except Exception as exc:
            checks.append(ConformanceCheck("inspect", False, str(exc)))
            return self._report(adapter, checks)
        if not variants:
            return self._report(adapter, checks)
        variant = variants[0]
        operations = (
            ("resolve_files", lambda: adapter.resolve_files(variant), list),
            ("validate", lambda: adapter.validate(variant), dict),
            (
                "estimate_resources",
                lambda: adapter.estimate_resources(
                    variant,
                    hardware
                    or {
                        "total_vram_bytes": 8 * 1024**3,
                        "total_host_ram_bytes": 16 * 1024**3,
                    },
                ),
                dict,
            ),
            ("compatible_backends", lambda: adapter.compatible_backends(variant), tuple),
        )
        for name, operation, expected in operations:
            try:
                result = operation()
                passed = isinstance(result, expected)
                if name == "resolve_files":
                    passed = passed and bool(result) and all(item.get("path") for item in result)
                if name == "validate":
                    passed = passed and "valid" in result and "serving_ready" in result
                checks.append(ConformanceCheck(name, passed, type(result).__name__))
            except Exception as exc:
                checks.append(ConformanceCheck(name, False, str(exc)))
        return self._report(adapter, checks)

    @staticmethod
    def _report(adapter: Any, checks: list[ConformanceCheck]) -> JsonDict:
        failed = [item for item in checks if not item.passed]
        return {
            "adapter_id": getattr(getattr(adapter, "manifest", None), "adapter_id", getattr(adapter, "adapter_id", "unknown")),
            "passed": not failed,
            "checks": [item.to_dict() for item in checks],
            "failed_checks": [item.name for item in failed],
        }


__all__ = ["ArtifactConformanceSuite", "BackendConformanceSuite", "ConformanceCheck"]
