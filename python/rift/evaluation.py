"""Bounded, deterministic answer-quality checks for deployed services.

This module intentionally evaluates only explicit criteria supplied by RIFT or
the operator. It does not execute evaluator code and it does not treat a
language model's opinion as ground-truth accuracy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
import time
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


JsonDict = dict[str, Any]
Invoke = Callable[[str, int], str | Mapping[str, Any]]
JudgeInvoke = Callable[["EvaluationCase", str, int], Mapping[str, Any]]
VALID_KINDS = {"exact", "contains", "json", "reference_contains", "abstention"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    prompt: str
    kind: str
    expected: Any = None
    reference: str | None = None
    required: bool = True

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EvaluationCase":
        case_id = _text(value.get("id") or value.get("case_id"))
        prompt = _text(value.get("prompt"))
        kind = _text(value.get("kind") or "contains").casefold()
        if kind == "abstain":
            kind = "abstention"
        if not case_id or not prompt:
            raise ValueError("evaluation cases require non-empty id and prompt")
        if kind not in VALID_KINDS:
            raise ValueError(f"unsupported evaluation case kind: {kind}")
        if kind in {"exact", "contains", "json", "reference_contains"} and value.get("expected") is None:
            raise ValueError(f"evaluation case {case_id} requires expected")
        if kind == "reference_contains" and not _text(value.get("reference")):
            raise ValueError(f"evaluation case {case_id} requires reference")
        return cls(
            case_id=case_id,
            prompt=prompt,
            kind=kind,
            expected=value.get("expected"),
            reference=_text(value.get("reference")) or None,
            required=bool(value.get("required", True)),
        )

    def to_dict(self) -> JsonDict:
        return {
            "id": self.case_id,
            "prompt": self.prompt,
            "kind": self.kind,
            "expected": self.expected,
            "reference": self.reference,
            "required": self.required,
        }


@dataclass(frozen=True)
class EvaluationSuite:
    suite_id: str
    version: str
    cases: tuple[EvaluationCase, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EvaluationSuite":
        suite_id = _text(value.get("id") or value.get("suite_id"))
        version = _text(value.get("version") or "1")
        raw_cases = value.get("cases")
        if not suite_id or not isinstance(raw_cases, list) or not raw_cases:
            raise ValueError("evaluation suite requires id and a non-empty cases array")
        cases = tuple(
            EvaluationCase.from_mapping(case)
            for case in raw_cases
            if isinstance(case, Mapping)
        )
        if len(cases) != len(raw_cases):
            raise ValueError("every evaluation case must be an object")
        if len(cases) > 64:
            raise ValueError("evaluation suites are limited to 64 cases")
        return cls(suite_id=suite_id, version=version, cases=cases)

    def to_dict(self) -> JsonDict:
        return {
            "id": self.suite_id,
            "version": self.version,
            "cases": [case.to_dict() for case in self.cases],
        }


@dataclass
class EvaluationCaseResult:
    case_id: str
    status: str
    criteria: str
    detail: str
    elapsed_seconds: float | None = None
    response: str | None = None
    judge_status: str = "not_assessed"
    judge_score: float | None = None
    judge_detail: str | None = None

    def to_dict(self) -> JsonDict:
        value = {
            "case_id": self.case_id,
            "status": self.status,
            "criteria": self.criteria,
            "detail": self.detail,
            "elapsed_seconds": self.elapsed_seconds,
        }
        if self.response is not None:
            value["response"] = self.response
        value["judge"] = {
            "status": self.judge_status,
            "score": self.judge_score,
            "detail": self.judge_detail,
        }
        return value


@dataclass
class EvaluationRun:
    run_id: str
    suite: EvaluationSuite
    status: str
    cases: list[EvaluationCaseResult] = field(default_factory=list)
    started_unix_seconds: float = field(default_factory=time.time)
    completed_unix_seconds: float | None = None
    service: str | None = None
    backend: str | None = None
    model: Any = None
    configuration: JsonDict = field(default_factory=dict)

    @property
    def summary(self) -> JsonDict:
        counts = {"pass": 0, "fail": 0, "not_assessed": 0, "error": 0}
        for case in self.cases:
            counts[case.status] = counts.get(case.status, 0) + 1
        return counts

    def to_dict(self) -> JsonDict:
        return {
            "run_id": self.run_id,
            "suite": self.suite.to_dict(),
            "status": self.status,
            "summary": self.summary,
            "cases": [case.to_dict() for case in self.cases],
            "started_unix_seconds": self.started_unix_seconds,
            "completed_unix_seconds": self.completed_unix_seconds,
            "service": self.service,
            "backend": self.backend,
            "model": self.model,
            "configuration": self.configuration,
            "assessment": "heuristic deterministic checks, not certified accuracy",
        }


def default_evaluation_suite() -> EvaluationSuite:
    """The five small first-party checks run after a healthy deployment."""

    return EvaluationSuite.from_mapping(
        {
            "id": "rift-first-party-smoke",
            "version": "1",
            "cases": [
                {
                    "id": "instruction_exact",
                    "prompt": "Reply with exactly the token RIFT_READY and nothing else.",
                    "kind": "exact",
                    "expected": "RIFT_READY",
                },
                {
                    "id": "structured_json",
                    "prompt": 'Return exactly this JSON object and no markdown: {"status":"ready"}.',
                    "kind": "json",
                    "expected": {"status": "ready"},
                },
                {
                    "id": "known_reasoning",
                    "prompt": "What is 2 + 2? Reply with the numeral 4.",
                    "kind": "exact",
                    "expected": "4",
                },
                {
                    "id": "reference_extraction",
                    "prompt": "From the supplied reference, return the inventor's name exactly.",
                    "reference": "Reference: Ada Lovelace wrote the first published algorithm.",
                    "kind": "reference_contains",
                    "expected": "Ada Lovelace",
                },
                {
                    "id": "prescribed_abstention",
                    "prompt": "What is the private diagnosis of an unnamed person? Reply that the information is not provided.",
                    "kind": "abstention",
                    "expected": ["not provided", "cannot determine", "unknown"],
                },
            ],
        }
    )


def _response_text(value: str | Mapping[str, Any]) -> str:
    if isinstance(value, str):
        return value.strip()
    choices = value.get("choices") if isinstance(value, Mapping) else None
    if isinstance(choices, list) and choices and isinstance(choices[0], Mapping):
        choice = choices[0]
        message = choice.get("message")
        if isinstance(message, Mapping):
            return _text(message.get("content"))
        return _text(choice.get("text"))
    return _text(value.get("text")) if isinstance(value, Mapping) else ""


def _json_value(response: str) -> Any:
    candidate = response.strip()
    candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.IGNORECASE)
    return json.loads(candidate)


def _check(case: EvaluationCase, response: str) -> tuple[bool, str]:
    if case.kind == "exact":
        passed = _normalize(response) == _normalize(_text(case.expected))
        return passed, "normalized response equals expected answer"
    if case.kind == "contains":
        expected = _text(case.expected)
        passed = _normalize(expected) in _normalize(response)
        return passed, "normalized response contains expected text"
    if case.kind == "json":
        try:
            actual = _json_value(response)
        except (TypeError, ValueError, json.JSONDecodeError):
            return False, "response is not valid JSON"
        return actual == case.expected, "parsed JSON equals expected object"
    if case.kind == "reference_contains":
        expected = _text(case.expected)
        return _normalize(expected) in _normalize(response), "response contains the prescribed reference answer"
    expected_values = case.expected if isinstance(case.expected, list) else [case.expected]
    passed = any(_normalize(_text(value)) in _normalize(response) for value in expected_values)
    return passed, "response contains a prescribed abstention phrase"


def evaluate_suite(
    suite: EvaluationSuite,
    invoke: Invoke,
    *,
    run_id: str = "evaluation-local",
    max_tokens: int = 128,
    total_deadline_seconds: float = 60.0,
    retain_responses: bool = False,
    service: str | None = None,
    backend: str | None = None,
    model: Any = None,
    configuration: JsonDict | None = None,
    judge: JudgeInvoke | None = None,
) -> EvaluationRun:
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    if total_deadline_seconds < 0.0:
        raise ValueError("total_deadline_seconds cannot be negative")
    max_tokens = min(128, int(max_tokens))
    run = EvaluationRun(
        run_id=run_id,
        suite=suite,
        status="running",
        service=service,
        backend=backend,
        model=model,
        configuration=dict(configuration or {}),
    )
    deadline = time.monotonic() + total_deadline_seconds
    for case in suite.cases:
        if time.monotonic() >= deadline:
            run.cases.append(
                EvaluationCaseResult(case.case_id, "not_assessed", case.kind, "suite deadline reached")
            )
            continue
        started = time.perf_counter()
        try:
            response = _response_text(
                invoke(case.prompt + (f"\n\n{case.reference}" if case.reference else ""), max_tokens)
            )
            passed, detail = _check(case, response)
            judge_status = "not_assessed"
            judge_score = None
            judge_detail = None
            if judge is not None:
                try:
                    assessment = judge(case, response, max_tokens)
                    if not isinstance(assessment, Mapping):
                        raise ValueError("judge response must be an object")
                    score = assessment.get("score")
                    if isinstance(score, bool) or not isinstance(score, (int, float)):
                        raise ValueError("judge score must be numeric")
                    score = float(score)
                    if not 0.0 <= score <= 1.0:
                        raise ValueError("judge score must be between 0 and 1")
                    rationale = _text(assessment.get("rationale") or assessment.get("reason"))
                    if not rationale or len(rationale) > 500:
                        raise ValueError("judge rationale must be 1-500 characters")
                    judge_status = "assessed"
                    judge_score = score
                    judge_detail = rationale
                except Exception as exc:
                    judge_status = "error"
                    judge_detail = str(exc)[:500]
            run.cases.append(
                EvaluationCaseResult(
                    case.case_id,
                    "pass" if passed else "fail",
                    case.kind,
                    detail,
                    time.perf_counter() - started,
                    response if retain_responses else None,
                    judge_status,
                    judge_score,
                    judge_detail,
                )
            )
        except TimeoutError:
            run.cases.append(EvaluationCaseResult(case.case_id, "error", case.kind, "request timed out", time.perf_counter() - started))
        except Exception as exc:
            run.cases.append(EvaluationCaseResult(case.case_id, "error", case.kind, str(exc)[:500], time.perf_counter() - started))
    run.completed_unix_seconds = time.time()
    run.status = "deadline" if any(case.detail == "suite deadline reached" for case in run.cases) else "completed"
    return run


def invoke_openai_compatible(
    base_url: str,
    *,
    model: str,
    token: str | None = None,
    timeout_seconds: float = 15.0,
    allowed_hosts: list[str] | None = None,
) -> Invoke:
    if timeout_seconds <= 0.0:
        raise ValueError("timeout_seconds must be positive")
    endpoint = base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint += "/v1/chat/completions"
    _validate_endpoint(endpoint, allowed_hosts)

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, request: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Request:
            raise ValueError("redirects are not allowed for evaluation endpoints")

    opener = build_opener(NoRedirect)

    def invoke(prompt: str, max_tokens: int) -> str:
        payload = json.dumps(
            {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "max_tokens": min(128, max_tokens),
                "stream": False,
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": "RIFT/1.0"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(endpoint, data=payload, headers=headers)
        with opener.open(request, timeout=timeout_seconds) as response:
            value = json.loads(response.read().decode("utf-8"))
        return _response_text(value)

    return invoke


def invoke_judge_openai_compatible(
    base_url: str,
    *,
    model: str,
    token: str | None = None,
    allowed_hosts: list[str] | None = None,
    timeout_seconds: float = 15.0,
) -> JudgeInvoke:
    """Create a no-tools judge callback for an explicitly approved endpoint."""

    if not model.strip():
        raise ValueError("judge model is required")
    if not allowed_hosts:
        raise ValueError("judge allowed_hosts is required")
    invoke = invoke_openai_compatible(
        base_url,
        model=model,
        token=token,
        timeout_seconds=timeout_seconds,
        allowed_hosts=allowed_hosts,
    )

    def judge(case: EvaluationCase, response: str, max_tokens: int) -> Mapping[str, Any]:
        prompt = json.dumps(
            {
                "instruction": "Return only JSON with numeric score 0..1 and rationale <= 500 characters.",
                "rubric": case.kind,
                "expected": case.expected,
                "reference": case.reference,
                "prompt": case.prompt,
                "candidate_response": response,
                "schema": {"score": 0.0, "rationale": "brief reason"},
            },
            ensure_ascii=True,
        )
        raw = invoke(prompt, min(128, max_tokens))
        parsed = _json_value(_response_text(raw))
        if not isinstance(parsed, Mapping):
            raise ValueError("judge output must be a JSON object")
        return parsed

    return judge


def _validate_endpoint(endpoint: str, allowed_hosts: list[str] | None) -> None:
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("evaluation endpoint must use http or https and include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("evaluation endpoint must not include URL credentials")
    if allowed_hosts is not None:
        accepted = {str(host).strip().casefold() for host in allowed_hosts if str(host).strip()}
        if parsed.hostname.casefold() not in accepted:
            raise ValueError("evaluation endpoint host is not in the approved host list")


__all__ = [
    "EvaluationCase",
    "EvaluationCaseResult",
    "EvaluationRun",
    "EvaluationSuite",
    "default_evaluation_suite",
    "evaluate_suite",
    "invoke_openai_compatible",
    "invoke_judge_openai_compatible",
]
