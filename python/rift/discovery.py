"""Shared, deterministic workload normalization for model discovery."""
from __future__ import annotations

from typing import Any, Mapping
import re

from .adapters.contracts import WorkloadProfile
from .execution_policy import validate_workload_contract


_TASK_ALIASES = {
    "document": "documents",
    "docs": "documents",
    "retrieval": "rag",
    "rerank": "reranking",
    "reranker": "reranking",
    "embedding": "embeddings",
    "vlm": "vision-language",
}


def normalize_task(task: Any) -> str:
    value = str(task or "chat").strip().lower().replace("_", "-")
    return _TASK_ALIASES.get(value, value or "chat")


def model_family_matches(preference: str, model_name: str) -> bool:
    wanted = re.sub(r"[^a-z0-9]", "", str(preference).lower())
    actual = re.sub(r"[^a-z0-9]", "", str(model_name).lower())
    if not wanted or wanted in actual:
        return bool(wanted)
    family = re.match(r"[a-z]+", wanted)
    return bool(family and actual.startswith(family.group(0)) and wanted[len(family.group(0)):]
                and wanted[len(family.group(0)):] in actual[len(family.group(0)):])


def normalize_workload(
    *, task: str = "chat", workload_contract: Mapping[str, Any] | None = None
) -> WorkloadProfile:
    """Validate and flatten a compiled workload, or retain task-only behavior."""
    if workload_contract is None:
        return WorkloadProfile(task=normalize_task(task))

    contract = validate_workload_contract(workload_contract)
    performance = contract["performance"]
    quality = contract["quality"]
    capabilities = contract["capabilities"]
    policies = contract["policies"]
    return WorkloadProfile(
        task=normalize_task(contract["task"]),
        context_length=int(performance["context_tokens"]),
        concurrency=int(performance["concurrency"]),
        minimum_quality=float(quality["minimum_score"]),
        maximum_ttft_seconds=(
            float(performance["max_ttft_ms"]) / 1000
            if performance["max_ttft_ms"] is not None
            else None
        ),
        minimum_decode_tokens_per_second=(
            float(performance["min_decode_tps"])
            if performance["min_decode_tps"] is not None
            else None
        ),
        objective=str(contract["objective"]),
        request_rate=(
            float(performance["request_rate"])
            if performance["request_rate"] is not None
            else None
        ),
        decode_scope=str(performance["decode_scope"]),
        ttft_percentile=int(performance["ttft_percentile"]),
        tool_calling=bool(capabilities["tool_calling"]),
        structured_output=bool(capabilities["structured_output"]),
        network_policy=str(policies["network"]),
        backend_preference=policies["backend"],
        model_family_preference=policies["model_family"],
        quality_suite_id=str(quality["suite_id"]),
        quality_suite_version=str(quality["suite_version"]),
        quality_required_cases=tuple(quality["required_cases"]),
    )


def assess_metadata_capabilities(
    *, repo_id: str, tags: list[str], tool_calling: bool, structured_output: bool
) -> dict[str, str]:
    """Return supported/unsupported/unknown from explicit repository signals."""
    text = " ".join([repo_id, *tags]).lower().replace("-", "_")
    result: dict[str, str] = {}
    for name, required, positive, negative in (
        (
            "tool_calling",
            tool_calling,
            ("tool_calling", "function_calling", "function calling", "tools"),
            ("no_tool", "no_function_call", "tool_free", "without_tools"),
        ),
        (
            "structured_output",
            structured_output,
            ("structured_output", "structured_generation", "json_schema"),
            ("no_json", "no_structured_output", "unstructured_only"),
        ),
    ):
        if not required:
            continue
        if any(marker in text for marker in negative):
            result[name] = "unsupported"
        elif any(marker in text for marker in positive):
            result[name] = "supported"
        else:
            result[name] = "unknown"
    return result
