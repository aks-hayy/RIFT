"""Shared primitives used by backend-owned tuning adapters.

The coordinator owns lifecycle, measurement, and promotion.  Backend folders
own the parameter space and proposal policy; this module only contains the
small, backend-neutral value objects they share.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Mapping


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def accelerator_family(hardware: Mapping[str, Any]) -> str:
    explicit = hardware.get("accelerator_family")
    if explicit in {"cuda", "rocm", "xpu", "cpu"}:
        return str(explicit)
    for family, names in (
        ("cuda", ("cuda_available",)),
        ("rocm", ("rocm_available", "hip_available")),
        ("xpu", ("xpu_available",)),
    ):
        if any(hardware.get(name) is True for name in names):
            return family
    return "cpu"


@dataclass(frozen=True)
class Parameter:
    name: str
    flag: str
    group: str
    kind: str
    values: tuple[Any, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    platforms: tuple[str, ...] = ("cuda", "rocm", "xpu", "cpu")

    def validate(self, value: Any) -> None:
        valid = {
            "boolean": lambda: type(value) is bool,
            "integer": lambda: type(value) is int,
            "number": lambda: type(value) in (int, float) and math.isfinite(value),
            "string": lambda: isinstance(value, str),
            "object": lambda: isinstance(value, dict),
        }[self.kind]()
        if not valid or (self.values and value not in self.values):
            raise ValueError(f"invalid {self.name}: {value!r}")
        if self.minimum is not None and value < self.minimum:
            raise ValueError(f"{self.name} must be >= {self.minimum}")
        if self.maximum is not None and value > self.maximum:
            raise ValueError(f"{self.name} must be <= {self.maximum}")

    def to_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "restart_required": True}


class BackendTuningAdapter:
    """Base contract for a folder-owned tuning adapter."""

    backend = ""

    def __init__(self, provider: Any):
        self.provider = provider

    def resolve_configuration(self, deployment: Mapping[str, Any]) -> dict[str, Any]:
        plan = deployment.get("launch_plan", deployment)
        return copy.deepcopy({k: v for k, v in (plan.get("tuning") or {}).items() if v is not None})

    def validate(self, configuration, identity, requirements, resources):
        errors = []
        for key in IDENTITY_KEYS:
            if configuration.get(key) != identity.get(key):
                errors.append(f"locked deployment setting changed: {key}")
        return errors

    def build_launch_spec(self, **kwargs):
        return self.provider.plan_launch(**kwargs)

    def collect_diagnostics(self, runtime):
        return {"backend": self.backend, "qualification": "unqualified"}

    def explain(self, candidate, evidence):
        return {
            "changes": candidate,
            "measurement_ids": evidence.get("measurement_ids", []),
            "causal_attribution": "configuration-level; no ablation performed",
        }


IDENTITY_KEYS = frozenset(
    {
        "model_path",
        "model_sha256",
        "weight_quantization",
        "quantization",
        "dtype",
        "tokenizer",
        "tokenizer_revision",
        "revision",
        "chat_template",
        "tool_call_parser",
        "reasoning_parser",
        "generation_config",
        "tensor_parallel_size",
        "pipeline_parallel_size",
        "container_image",
        "executable",
        "runtime_mode",
        "command_style",
        "vllm_use_v1",
        "context_length",
        "concurrency",
        "device_ids",
        "accelerator_family",
        "speculative_config",
        "wsl_distribution",
        "wsl_python",
        "wsl_model_path",
        "runtime_feature_probe",
    }
)


__all__ = [
    "BackendTuningAdapter",
    "IDENTITY_KEYS",
    "Parameter",
    "accelerator_family",
    "canonical_hash",
]
