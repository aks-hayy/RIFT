"""Offline, deterministic workload compilation primitives.

This module is intentionally not wired into setup yet. It provides the
immutable contract boundary that the future autonomous deployment controller
will use, without granting a compiler any deployment permissions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import html
import json
import re
from typing import Any, Mapping


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str).encode()).hexdigest()


@dataclass(frozen=True)
class Annotation:
    source: str
    evidence: str
    confidence: float
    enforcement: str


@dataclass(frozen=True)
class WorkloadContractV1:
    task: str
    objective: str
    performance: Mapping[str, Any]
    quality: Mapping[str, Any]
    capabilities: Mapping[str, Any]
    policies: Mapping[str, Any]
    service: Mapping[str, Any]
    annotations: Mapping[str, Annotation] = field(default_factory=dict)
    schema_version: int = 1

    def __post_init__(self):
        if self.schema_version != 1 or self.task not in {"chat", "coding", "documents", "rag", "agent", "custom"}:
            raise ValueError("invalid workload task or schema")
        if self.objective not in {"balanced", "speed", "cost"}:
            raise ValueError("invalid workload objective")
        for key in ("context_tokens", "concurrency"):
            if int(self.performance.get(key, 0)) <= 0:
                raise ValueError(f"performance.{key} must be positive")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["annotations"] = {key: asdict(annotation) for key, annotation in self.annotations.items()}
        return value

    @property
    def contract_hash(self) -> str:
        return _hash(self.to_dict())


@dataclass(frozen=True)
class WorkloadDraft:
    draft_id: str
    revision: int
    original_request: str
    contract: WorkloadContractV1
    warnings: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()
    status: str = "COMPILED"

    def to_dict(self) -> dict[str, Any]:
        return {"draft_id": self.draft_id, "revision": self.revision, "original_request": self.original_request,
                "contract": self.contract.to_dict(), "warnings": list(self.warnings), "unresolved": list(self.unresolved), "status": self.status,
                "contract_hash": self.contract.contract_hash}


@dataclass(frozen=True)
class ApprovalEnvelope:
    contract_hash: str
    allow_download: bool
    allow_install: bool
    allow_temporary_launch: bool
    allow_restart: bool
    allow_promote: bool
    allow_remote: bool
    max_artifacts: int
    candidate_limit: int
    budget_seconds: float
    total_download_bytes: int
    cleanup_rejected_artifacts: bool = False

    def __post_init__(self):
        if not self.contract_hash or min(self.max_artifacts, self.candidate_limit) < 1 or self.total_download_bytes < 0 or self.budget_seconds <= 0:
            raise ValueError("approval limits must be nonnegative with a positive time budget")

    @property
    def envelope_hash(self) -> str:
        return _hash(asdict(self))


def _number(text: str, pattern: str) -> float | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return float(match.group(1)) if match else None


def compile_workload(request: str | Mapping[str, Any], *, draft_id: str = "draft-local", revision: int = 1) -> WorkloadDraft:
    """Compile JSON or natural language without network/model calls."""
    original = json.dumps(request, sort_keys=True) if isinstance(request, Mapping) else html.unescape(str(request)).strip()
    if isinstance(request, Mapping):
        data = dict(request)
        slos = dict(data.get("slos") or data.get("performance") or {})
        constraints = dict(data.get("constraints") or {})
        task = str(data.get("task") or "chat").lower()
        objective = str(data.get("objective") or "balanced").lower()
        decode = slos.get("min_decode_tps", slos.get("min_tokens_per_second"))
        ttft = slos.get("max_ttft_ms")
        context = slos.get("context_tokens", slos.get("context_window", 4096))
        concurrency = slos.get("concurrency", slos.get("concurrent_users", 1))
        tools = data.get("tool_calling", data.get("capabilities", {}).get("tool_calling", False))
        if isinstance(tools, Mapping): tools = tools.get("required", False)
        backend = constraints.get("backend") or data.get("backend_target")
        ann = {
            "/performance/min_decode_tps": Annotation("explicit", "JSON", 1.0, "hard") if decode is not None else Annotation("default", "no value", 1.0, "preference"),
            "/performance/context_tokens": Annotation("explicit", "JSON", 1.0, "hard"),
        }
        warnings = []
        quality = dict(data.get("quality") or {"suite_id": None, "suite_version": None, "minimum_score": None})
        if data.get("gbnf_schema") or slos.get("strict_json"): warnings.append("Structured-output requirement is recorded but no evaluator is enabled in the dormant compiler path.")
    else:
        text = original.lower()
        task = "coding" if any(word in text for word in ("coding", "code assistant", "programming")) else "chat"
        objective = "cost" if "cost" in text or "joule" in text else "speed" if "speed" in text or "throughput" in text else "balanced"
        decode = _number(original, r"(?:at least|min(?:imum)?|>=)\s*(\d+(?:\.\d+)?)\s*(?:tokens?|tok|tps)")
        ttft = _number(original, r"(?:under|below|<=|within|max(?:imum)?)\s*(\d+(?:\.\d+)?)\s*(?:ms|milliseconds?)")
        if ttft is None:
            seconds = _number(original, r"(?:under|below|within)\s*(\d+(?:\.\d+)?)\s*(?:s|sec|seconds?)")
            ttft = seconds * 1000 if seconds is not None else None
        context = _number(original, r"(\d+(?:\.\d+)?)\s*k\s*(?:context|tokens?)")
        context = int(context * 1024) if context is not None else 4096
        concurrency = int(_number(original, r"(?:concurrency|concurrent users?|users?)\s*(?:of|=|:)?\s*(\d+)") or 1)
        tools = bool(re.search(r"tools?\s*(?:required|yes|needed)|tool calling\s*[:=]\s*yes", text))
        backend = "llama.cpp" if "llama.cpp" in text else None
        ann = {
            "/task": Annotation("inferred", "natural language", .95, "preference"),
            "/performance/context_tokens": Annotation("explicit" if "context" in text else "default", original, 1.0 if "context" in text else .8, "hard"),
            "/capabilities/tool_calling/required": Annotation("explicit" if "tool" in text else "default", original, 1.0 if "tool" in text else .8, "hard" if tools else "preference"),
        }
        warnings = ["Quality suite and floor require review before approval."]
    performance = {"min_decode_tps": decode, "max_ttft_ms": ttft, "context_tokens": int(context), "concurrency": int(concurrency)}
    if not isinstance(request, Mapping):
        quality = {"suite_id": None, "suite_version": None, "minimum_score": None}
    capabilities = {"tool_calling": {"required": bool(tools), "level": "core", "parallel_required": False}}
    policies = {"offline": bool(isinstance(request, Mapping) and (request.get("offline") or request.get("network") == "offline")), "allow_quantization_change": False, "backend": backend}
    contract = WorkloadContractV1(task=task, objective=objective, performance=performance, quality=quality, capabilities=capabilities, policies=policies, service={"name": "rift-workload"}, annotations=ann)
    unresolved = () if quality.get("suite_id") and quality.get("suite_version") and quality.get("minimum_score") is not None else ("quality.suite_id", "quality.minimum_score")
    return WorkloadDraft(draft_id=draft_id, revision=revision, original_request=original, contract=contract, warnings=tuple(warnings), unresolved=unresolved)


def approve_workload(draft: WorkloadDraft, *, contract_hash: str, envelope: ApprovalEnvelope) -> dict[str, Any]:
    if draft.status != "COMPILED" or draft.unresolved:
        raise ValueError("workload has unresolved hard requirements")
    if contract_hash != draft.contract.contract_hash or envelope.contract_hash != contract_hash:
        raise ValueError("stale workload contract or approval envelope")
    return {"status": "APPROVED", "draft_id": draft.draft_id, "revision": draft.revision, "contract_hash": contract_hash, "envelope_hash": envelope.envelope_hash}


__all__ = ["ApprovalEnvelope", "Annotation", "WorkloadContractV1", "WorkloadDraft", "approve_workload", "compile_workload"]
