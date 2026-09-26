"""Deterministic, review-first workload compilation.

The compiler deliberately produces an executable contract only for the small
text-workload subset understood by :mod:`rift.execution_policy`.  Everything
else is retained as an unsupported requirement and becomes a review question;
it is never silently discarded or promoted to a permission.
"""
from __future__ import annotations

import html
import json
import re
import unicodedata
from collections.abc import Mapping
from typing import Any

from .execution_policy import content_hash, validate_json_schema


_NUMBER = r"(?:\d+(?:[.,]\d+)?)"


def _norm_text(value: Any) -> str:
    text = html.unescape(unicodedata.normalize("NFKC", str(value or "")))
    return re.sub(r"\s+", " ", text.replace("\u00a0", " ")).strip()


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None and number.is_integer() else None


def _nested(value: Mapping[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _first_number(text: str, patterns: list[str]) -> tuple[float | None, str | None]:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _number(match.group(1)), match.group(0)
    return None, None


def _source(pointer: str, evidence: str, source: str, *, confidence: float = 1.0, enforcement: str = "hard") -> dict[str, Any]:
    return {"source": source, "evidence": evidence, "confidence": confidence, "enforcement": enforcement}


def _task(value: Any, text: str) -> tuple[str, str, float]:
    raw = _norm_text(value).lower()
    haystack = f"{raw} {text.lower()}"
    if "coding" in haystack or "programming" in haystack or "developer" in haystack:
        return "coding", "coding terms or task identifier", 0.96
    if "rag" in haystack or "retrieval" in haystack:
        return "rag", "RAG/retrieval terms or task identifier", 0.96
    if "invoice" in haystack or "extract" in haystack or "document" in haystack or "json" in haystack:
        return "documents", "document/extraction terms or task identifier", 0.88
    return "chat", "general conversational workload", 0.62


def _bool_explicit(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"yes", "true", "required", "on", "enable", "enabled"}:
            return True
        if lowered in {"no", "false", "not required", "optional", "off", "disabled"}:
            return False
    return None


def _schema_artifact(value: Any, *, filename: str | None = None) -> dict[str, Any]:
    """Normalize an uploaded JSON Schema into a contract artifact."""
    if isinstance(value, Mapping) and "schema" in value and "sha256" in value:
        schema_value = value.get("schema")
        filename = filename or str(value.get("filename") or "output-schema.json")
    else:
        schema_value = value
        filename = filename or "output-schema.json"
    schema = validate_json_schema(schema_value)
    safe_name = str(filename).replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not safe_name or safe_name in {".", ".."}:
        raise ValueError("output schema filename must be a non-empty basename")
    return {
        "schema": schema,
        "sha256": content_hash(schema),
        "filename": safe_name,
        "media_type": "application/schema+json",
    }


def compile_workload(
    request: Any,
    *,
    draft_id: str | None = None,
    revision: int = 1,
    confirm_default_quality: bool = False,
    output_schema: Mapping[str, Any] | None = None,
    output_schema_filename: str | None = None,
) -> dict[str, Any]:
    """Compile JSON/mapping or natural language into a reviewable draft."""
    structured = isinstance(request, Mapping)
    data: Mapping[str, Any] = request if structured else {}
    text = _norm_text(json.dumps(request, ensure_ascii=False) if structured else request)
    provenance: dict[str, Any] = {}
    questions: list[str] = []
    warnings: list[str] = []
    unsupported: list[dict[str, Any]] = []

    def mark(pointer: str, evidence: str, source: str, *, confidence: float = 1.0, enforcement: str = "hard") -> None:
        provenance[pointer] = _source(pointer, evidence, source, confidence=confidence, enforcement=enforcement)

    # Exact values in a structured request have precedence over textual inference.
    task_value = data.get("task") if structured else None
    task, task_evidence, task_conf = _task(task_value, text)
    mark("/task", task_evidence, "explicit" if task_value is not None else "inferred", confidence=1.0 if task_value is not None else task_conf)

    objective_value = data.get("objective") if structured else None
    objective_raw = _norm_text(objective_value).lower()
    if objective_raw not in {"balanced", "speed", "cost"}:
        if re.search(r"\b(cost|joule|energy|cheap|efficient)\b", text, re.I):
            objective_raw, objective_evidence = "cost", "cost/energy language"
        elif re.search(
            r"\b(?:speed|fast|throughput|latency|tps)\b|\b(?:tokens?|tok)\s*(?:/|per)\s*(?:s|sec(?:ond)?)\b",
            text,
            re.I,
        ):
            objective_raw, objective_evidence = "speed", "speed/throughput language"
        else:
            objective_raw, objective_evidence = "balanced", "policy default"
        mark("/objective", objective_evidence, "inferred" if objective_evidence != "policy default" else "default", confidence=0.9 if objective_raw != "balanced" else 0.55, enforcement="preference")
    else:
        mark("/objective", str(objective_value), "explicit", enforcement="preference")

    slos = data.get("slos") if isinstance(data.get("slos"), Mapping) else {}
    perf_data = data.get("performance") if isinstance(data.get("performance"), Mapping) else {}
    def value_for(*keys: str) -> Any:
        for container in (perf_data, slos, data):
            for key in keys:
                if isinstance(container, Mapping) and key in container:
                    return container[key], key
        return None, None

    decode_value, decode_key = value_for("min_decode_tps", "min_tokens_per_second", "decode_tps", "throughput")
    decode = _number(decode_value)
    decode_evidence = f"$.{decode_key}" if decode_key else None
    if decode is None:
        # Accept the forms people naturally use in a workload request:
        # ``tokens/s``, ``tokens per s`` and ``tokens per second``.  The
        # previous expression only accepted the abbreviated ``s`` form, so a
        # perfectly explicit NL requirement could silently become null.
        rate_unit = r"(?:decode\s*)?(?:tokens?|tok)(?:\s+per)?\s*(?:/\s*)?(?:s(?:ec(?:ond)?)?)"
        decode, decode_evidence = _first_number(
            text,
            [
                rf"(?:at least|minimum|min(?:imum)?|target)[^0-9]{{0,30}}({_NUMBER})\s*{rate_unit}",
                rf"(?:decode|throughput)[^0-9]{{0,30}}({_NUMBER})\s*{rate_unit}",
            ],
        )
    if decode is None:
        decode = None
        decode_evidence = None
        mark("/performance/min_decode_tps", "not specified", "default", enforcement="hard")
    else:
        mark("/performance/min_decode_tps", decode_evidence or str(decode), "explicit" if decode_key else "explicit", enforcement="hard")

    ttft_value, ttft_key = value_for("max_ttft_ms", "ttft_ms")
    ttft = _number(ttft_value)
    ttft_evidence = f"$.{ttft_key}" if ttft_key else None
    if ttft is not None:
        mark("/performance/max_ttft_ms", ttft_evidence or str(ttft), "explicit")
    else:
        match = re.search(rf"(?:under|below|within|less than|maximum|max)[^0-9]{{0,20}}({_NUMBER})\s*(milliseconds?|ms|seconds?|s)", text, re.I)
        if match:
            ttft = _number(match.group(1))
            if match.group(2).lower().startswith("s"):
                ttft = (ttft or 0) * 1000
            ttft_evidence = match.group(0)
            mark("/performance/max_ttft_ms", ttft_evidence, "explicit")
    if ttft is None:
        mark("/performance/max_ttft_ms", "not specified", "default", enforcement="hard")

    context_value, context_key = value_for("context_tokens", "context_window", "context_per_user", "context")
    context = _integer(context_value)
    context_evidence = f"$.{context_key}" if context_key else None
    if context is None:
        match = re.search(
            rf"({_NUMBER})\s*(k|m)?\s*(?:tokens?\s*)?(?:context(?:\s+window)?)",
            text,
            re.I,
        )
        if not match:
            match = re.search(rf"(?:context|context window)[^0-9]{{0,10}}({_NUMBER})\s*(k|m)?", text, re.I)
        if match:
            context = _integer(match.group(1))
            multiplier = (match.group(2) or "").lower()
            context = context * (1024 if multiplier == "k" else 1024 * 1024 if multiplier == "m" else 1)
            context_evidence = match.group(0)
    context = context or 2048
    mark("/performance/context_tokens", context_evidence or "policy default 2048", "explicit" if context_evidence else "default")

    concurrency_value, concurrency_key = value_for("concurrency", "concurrent_users", "users")
    concurrency = _integer(concurrency_value)
    if concurrency is None:
        match = re.search(rf"({_NUMBER})\s*(?:concurrent users?|users?|parallel slots?)", text, re.I)
        concurrency = _integer(match.group(1)) if match else 1
        concurrency_evidence = match.group(0) if match else "default concurrency 1"
    else:
        concurrency_evidence = f"$.{concurrency_key}"
    mark("/performance/concurrency", concurrency_evidence, "explicit" if concurrency_key or concurrency != 1 else "default")

    request_rate_value, request_rate_key = value_for("request_rate", "target_qps", "qps")
    request_rate = _number(request_rate_value)
    if request_rate is None:
        match = re.search(rf"({_NUMBER})\s*(?:qps|requests?\s*(?:/|per)\s*s(?:econd)?)", text, re.I)
        request_rate = _number(match.group(1)) if match else None
        request_rate_evidence = match.group(0) if match else None
    else:
        request_rate_evidence = f"$.{request_rate_key}"
    if request_rate is not None:
        mark("/performance/request_rate", request_rate_evidence or str(request_rate), "explicit")
    else:
        mark("/performance/request_rate", "not specified", "default")

    scope_raw = str(perf_data.get("decode_scope") or slos.get("decode_scope") or "").lower()
    if scope_raw not in {"per_request", "aggregate"}:
        if re.search(r"\b(per user|per request|each user|each request)\b", text, re.I):
            scope_raw = "per_request"
        elif re.search(r"\b(aggregate|overall|total|combined)\b", text, re.I):
            scope_raw = "aggregate"
        else:
            scope_raw = "per_request"
            if concurrency > 1 and decode is not None:
                questions.append("Is the throughput requirement per request/user or aggregate across concurrent users?")
        mark("/performance/decode_scope", scope_raw, "explicit" if scope_raw in {"per_request", "aggregate"} and (perf_data.get("decode_scope") or slos.get("decode_scope")) else "inferred", enforcement="hard")
    else:
        mark("/performance/decode_scope", scope_raw, "explicit", enforcement="hard")

    percentile = perf_data.get("ttft_percentile", slos.get("ttft_percentile", data.get("ttft_percentile")))
    if percentile is None:
        percentile = 95
        if re.search(r"first (?:answer|token)|responds? within|response within", text, re.I) and not re.search(r"p95|95th|percentile", text, re.I):
            questions.append("Should the TTFT requirement be evaluated as p95? The text gives a threshold but no percentile.")
        mark("/performance/ttft_percentile", "v1 reviewed p95 default", "default", enforcement="hard")
    else:
        percentile = _integer(percentile)
        mark("/performance/ttft_percentile", f"$.{('performance.' if perf_data.get('ttft_percentile') is not None else 'slos.') }ttft_percentile", "explicit", enforcement="hard")

    tool_value = _nested(data, "capabilities", "tool_calling") if structured else None
    if tool_value is None and structured:
        tool_value = data.get("tool_calling")
    tool_required = _bool_explicit(tool_value)
    if tool_required is None:
        tool_required = bool(re.search(r"\b(tools?|function calling)\s+(?:are\s+)?required|tool calling required|with tools", text, re.I))
        tool_source = "inferred" if tool_required else "default"
        mark("/capabilities/tool_calling", "tool requirement language" if tool_required else "not required by default", tool_source, confidence=0.9 if tool_required else 0.7)
    else:
        mark("/capabilities/tool_calling", str(tool_value), "explicit")

    structured_value = _nested(data, "capabilities", "structured_output") if structured else None
    structured_output = _bool_explicit(structured_value)
    if structured_output is None:
        structured_output = bool(re.search(
            r"strict (?:json|schema)|structured output|gbnf|json schema|"
            r"\bjson\s+(?:output|format|only|required)\b|\breturn\b[^.]{0,40}\bjson\b",
            text,
            re.I,
        ))
        mark("/capabilities/structured_output", "structured-output language" if structured_output else "not required by default", "inferred" if structured_output else "default")
    else:
        mark("/capabilities/structured_output", str(structured_value), "explicit")

    # A strict JSON requirement is only executable when the exact schema is
    # attached.  The schema may arrive as a UI/API upload or as a structured
    # workload field; the explicit function argument wins when both exist.
    schema_value: Any = output_schema
    if schema_value is None and structured:
        if "output_schema" in data:
            schema_value = data.get("output_schema")
        elif "json_schema" in data:
            schema_value = data.get("json_schema")
    schema_artifact: dict[str, Any] | None = None
    if schema_value is not None:
        schema_artifact = _schema_artifact(schema_value, filename=output_schema_filename)
        mark("/output_schema", f"uploaded JSON Schema {schema_artifact['filename']} ({schema_artifact['sha256'][:12]}…)", "explicit", enforcement="hard")
    elif structured_output:
        if re.search(r"\b(?:ehr|electronic health record|our)\s+schema\b", text, re.I):
            questions.append("Strict JSON output is required. Upload the versioned EHR JSON Schema before approval so RIFT can validate conformance.")
        else:
            questions.append("Strict JSON output is required. Upload a JSON Schema file before approval so RIFT can validate conformance.")
        mark("/output_schema", "required for strict JSON acceptance", "default", confidence=0.0, enforcement="hard")

    # Organisation-specific schemas (for example EHR contracts) are handled by
    # the same uploaded-artifact path; JSON syntax alone is never treated as
    # proof of conformance.

    network = _norm_text(_nested(data, "policies", "network") if structured else "").lower()
    # Do not treat a prohibition such as "no external network access" or
    # "air-gapped" as a positive network requirement.  The previous broad
    # expression made ordinary offline requests require an unnecessary review
    # question whenever they explained what must be blocked.
    network_prohibition = bool(re.search(
        r"\b(?:no|without|never|zero|air[- ]gapped)\b[^.]{0,40}\b(?:internet|network)\b",
        text,
        re.I,
    ))
    network_conflict = bool(re.search(r"\boffline\b", text, re.I)) and bool(
        re.search(r"\bonline\b|internet|network access", text, re.I)
    ) and not network_prohibition
    if network_conflict:
        questions.append("Network policy conflict: the request contains both offline and online/network language; choose one.")
    if not network:
        network = "offline" if re.search(r"\boffline|no network|without internet", text, re.I) else "approved_sources"
        mark("/policies/network", network, "explicit" if network == "offline" else "default", enforcement="policy")
    else:
        if network not in {"offline", "approved_sources"}:
            questions.append(f"Network policy {network!r} is unsupported; choose offline or approved_sources.")
        mark("/policies/network", f"$.policies.network", "explicit", enforcement="policy")

    backend = _nested(data, "policies", "backend") if structured else None
    if backend is None and structured:
        backend = data.get("backend_target") or data.get("backend")
    backend = _norm_text(backend) or None
    if backend and backend.lower() in {"llama-server", "llama_cpp", "llama-cpp"}:
        backend = "llama.cpp"
    elif backend and backend.lower() in {"vllm-server", "vllm_server"}:
        backend = "vllm"
    if backend is None:
        match = re.search(r"\b(llama\.cpp|llama-server|vllm|vllm-server|sglang|mlx)\b", text, re.I)
        backend = match.group(1).lower() if match else None
        if backend == "llama-server":
            backend = "llama.cpp"
        if backend == "vllm-server":
            backend = "vllm"
        mark("/policies/backend", backend or "backend selected from model/hardware", "inferred" if backend else "default", enforcement="preference")
    else:
        mark("/policies/backend", "$.policies.backend", "explicit", enforcement="preference")

    model_family = _nested(data, "policies", "model_family") if structured else None
    if model_family is None and structured:
        model_family = data.get("target_model_family")
    model_family = _norm_text(model_family) or None
    if model_family is None:
        match = re.search(r"\b((?:llama|qwen|mistral|gemma)[\w.\- ]{0,30}\d+[bBmM])\b", text, re.I)
        model_family = _norm_text(match.group(1)) if match else None
        mark("/policies/model_family", model_family or "model selected from workload/hardware", "inferred" if model_family else "default", enforcement="preference")
    else:
        mark("/policies/model_family", "$.target_model_family" if "target_model_family" in data else "$.policies.model_family", "explicit", enforcement="preference")

    quality = data.get("quality") if isinstance(data.get("quality"), Mapping) else {}
    suite_id = _norm_text(quality.get("suite_id")) or "rift-text-core"
    suite_version = _norm_text(quality.get("suite_version")) or "v1"
    try:
        floor_value = float(quality.get("minimum_score")) if quality.get("minimum_score") is not None else None
    except (TypeError, ValueError):
        floor_value = None
    floor = floor_value if floor_value is not None and 0 <= floor_value <= 1 else 0.9
    required_cases = quality.get("required_cases")
    if not isinstance(required_cases, list) or not required_cases:
        required_cases = ["response_nonempty"]
        if not confirm_default_quality:
            questions.append("Choose or confirm a versioned quality suite and minimum score before approval.")
            mark("/quality/suite_id", "compiler default; requires review", "default", confidence=0.4)
        else:
            mark("/quality/suite_id", "operator confirmed compiler default rift-text-core/v1", "explicit")
    else:
        required_cases = [str(item).strip() for item in required_cases if str(item).strip()]
        mark("/quality/suite_id", "$.quality.suite_id", "explicit")
    mark("/quality/suite_version", "$.quality.suite_version" if quality.get("suite_version") else "compiler default", "explicit" if quality.get("suite_version") else "default")
    mark("/quality/minimum_score", "$.quality.minimum_score" if quality.get("minimum_score") is not None else "compiler default 0.9", "explicit" if quality.get("minimum_score") is not None else "default")
    mark("/quality/required_cases", "$.quality.required_cases" if quality.get("required_cases") else "compiler default", "explicit" if quality.get("required_cases") else "default")

    policies = {"network": network, "backend": backend, "model_family": model_family}
    service_name = _norm_text(_nested(data, "service", "name") if structured else "") or "workload-service"
    if structured and isinstance(data.get("service"), Mapping):
        mark("/service/name", "$.service.name", "explicit")
    else:
        mark("/service/name", "default workload-service", "default", enforcement="preference")

    known_top = {"schema_version", "task", "objective", "slos", "performance", "quality", "capabilities", "policies", "service", "constraints", "backend_target", "target_model_family", "runtime_flags", "workload_id", "workload_text", "request", "gbnf_schema", "json_schema", "output_schema", "chaos_injection", "allow_partial_offload"}
    for key in data:
        if key not in known_top:
            unsupported.append({"path": f"$.{key}", "value": data[key], "reason": "not supported by the v1 executable contract"})
    for key in ("constraints", "runtime_flags", "gbnf_schema", "chaos_injection", "allow_partial_offload"):
        if key in data:
            unsupported.append({"path": f"$.{key}", "value": data[key], "reason": "captured for review; evaluator/executor is not implemented"})
    for phrase in ("flashattention", "flash attention", "prompt caching", "gbnf", "json schema"):
        if phrase == "json schema" and schema_artifact is not None:
            continue
        if re.search(rf"\b{re.escape(phrase)}\b", text, re.I) and not any(phrase in str(item.get("value", "")).lower() for item in unsupported):
            unsupported.append({"path": "$.natural_language", "value": phrase, "reason": "captured for review; evaluator/executor is not implemented"})
    if re.search(r"ignore (?:all )?previous instructions|grant .*permission|run .*shell|delete .*files", text, re.I):
        warnings.append("Input contains instruction-like text; it cannot grant RIFT permissions or actions.")
    if unsupported:
        warnings.append("Some requirements are visible below but are not executable in v1.")

    uptime_match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*uptime", text, re.I)
    if uptime_match:
        uptime_value = float(uptime_match.group(1))
        # The built-in objective monitor supplies a bounded, editable default
        # window.  The deployment run still reports coverage and does not
        # claim that a short smoke test proves the long-horizon SLO.
        observation_window_seconds = 30 * 24 * 60 * 60
        probe_interval_seconds = 30
        error_budget_seconds = round(observation_window_seconds * max(0.0, 1.0 - (uptime_value / 100.0)), 6)
        monitoring = {
            "objectives": [{
                "id": "uptime_slo",
                "metric": "service.availability_ratio",
                "operator": ">=",
                "threshold": round(uptime_value / 100.0, 12),
                "aggregation": "ratio",
                "window_seconds": float(observation_window_seconds),
                "consecutive_breaches": 1,
                "recovery_consecutive": 1,
                "alerts": [],
            }],
            "observation_window_seconds": observation_window_seconds,
            "probe_interval_seconds": probe_interval_seconds,
            "error_budget_seconds": error_budget_seconds,
            "source": "compiler_default_30_day_window",
        }
        provenance["/reliability/uptime_percent"] = {
            "source": "explicit",
            "evidence": uptime_match.group(0),
            "confidence": 1.0,
            "enforcement": "hard",
        }
        provenance["/monitoring/objectives/uptime_slo"] = {
            "source": "default",
            "evidence": "built-in service objective monitor",
            "confidence": 0.8,
            "enforcement": "hard",
        }
        warnings.append("99.9% uptime was mapped to the built-in availability monitor with a default 30-day observation window; review the window before approval. A short run cannot prove the full SLO.")
    else:
        monitoring = None

    contract = {
        "schema_version": 1,
        "task": task,
        "objective": objective_raw,
        "performance": {
            "min_decode_tps": decode,
            "decode_scope": scope_raw,
            "max_ttft_ms": ttft,
            "ttft_percentile": percentile or 95,
            "context_tokens": context,
            "concurrency": concurrency,
            "request_rate": request_rate,
        },
        "quality": {"suite_id": suite_id, "suite_version": suite_version, "minimum_score": floor, "required_cases": required_cases},
        "capabilities": {"tool_calling": tool_required, "structured_output": structured_output},
        "policies": policies,
        "service": {"name": service_name},
    }
    if tool_required:
        warnings.append(
            "RIFT will verify core tool-call emission for the exact deployment; real tool execution, brokering, permissions, and side effects remain the user's harness responsibility."
        )
        provenance["/capabilities/tool_calling_scope"] = {
            "source": "default",
            "evidence": "RIFT capability boundary",
            "confidence": 1.0,
            "enforcement": "policy",
        }
    if schema_artifact is not None:
        contract["output_schema"] = schema_artifact
    if monitoring is not None:
        contract["monitoring"] = monitoring
    # Explicitly preserve unsupported input as provenance, never executable fields.
    if unsupported:
        provenance["/unsupported_requirements"] = {"source": "explicit", "evidence": "structured input", "confidence": 1.0, "enforcement": "hard"}
    provenance["/_compiler"] = {
        "warnings": warnings,
        "unsupported_requirements": unsupported,
        "limitations": ["Compiler is deterministic and review-first; execution still requires an explicit approval envelope."] if not questions else ["Resolve review questions before approval; execution remains gated by the approval envelope."],
    }
    return {
        "schema_version": 1,
        "draft_id": draft_id,
        "revision": revision,
        "status": "COMPILED",
        "input": request,
        "contract": contract,
        "contract_hash": content_hash(contract),
        "provenance": provenance,
        "questions": sorted(set(questions)),
        "warnings": warnings,
        "unsupported_requirements": unsupported,
        "limitations": ["Compiler is deterministic and review-first; execution still requires an explicit approval envelope."] if not questions else ["Resolve review questions before approval; execution remains gated by the approval envelope."],
    }


compile_request = compile_workload

__all__ = ["compile_workload", "compile_request"]
