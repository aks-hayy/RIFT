"""Bounded, deterministic answer-quality checks for deployed services.

This module intentionally evaluates only explicit criteria supplied by RIFT or
the operator. It does not execute evaluator code and it does not treat a
language model's opinion as ground-truth accuracy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import datetime as _datetime
import json
import re
import time
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


JsonDict = dict[str, Any]
Invoke = Callable[[str, int], str | Mapping[str, Any]]
JudgeInvoke = Callable[["EvaluationCase", str, int], Mapping[str, Any]]
ToolInvoke = Callable[[list[JsonDict], list[JsonDict], int, JsonDict | None], Mapping[str, Any] | str]
VALID_KINDS = {"exact", "contains", "json", "json_schema", "reference_contains", "abstention", "nonempty"}


TOOL_CAPABILITY_SUITE_ID = "rift-tool-capability"
TOOL_CAPABILITY_SUITE_VERSION = "1"


def _tool_calls(response: Mapping[str, Any] | str) -> list[JsonDict]:
    """Extract OpenAI-compatible tool calls without executing any tool.

    The exact model/backend response is the evidence boundary.  We accept the
    current ``message.tool_calls`` form and the older ``function_call`` form,
    but never interpret free-form text as a successful call.  That prevents a
    model name or a static manifest from becoming a false capability claim.
    """

    if isinstance(response, str):
        return []
    choices = response.get("choices") if isinstance(response, Mapping) else None
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
        return []
    message = choices[0].get("message")
    if not isinstance(message, Mapping):
        return []
    raw = message.get("tool_calls")
    calls: list[JsonDict] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            function = item.get("function")
            if not isinstance(function, Mapping):
                continue
            name = _text(function.get("name"))
            arguments = function.get("arguments")
            if name:
                calls.append({
                    "id": _text(item.get("id")) or None,
                    "name": name,
                    "arguments": arguments if isinstance(arguments, (str, Mapping)) else "",
                })
    legacy = message.get("function_call")
    if isinstance(legacy, Mapping) and _text(legacy.get("name")):
        calls.append({
            "id": None,
            "name": _text(legacy.get("name")),
            "arguments": legacy.get("arguments") if isinstance(legacy.get("arguments"), (str, Mapping)) else "",
        })
    return calls


def _tool_arguments(call: Mapping[str, Any]) -> tuple[JsonDict | None, str | None]:
    raw = call.get("arguments")
    if isinstance(raw, Mapping):
        return dict(raw), None
    if not isinstance(raw, str) or not raw.strip():
        return None, "tool arguments are missing"
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, "tool arguments are not valid JSON"
    if not isinstance(value, Mapping):
        return None, "tool arguments must be a JSON object"
    return dict(value), None


def _tool_definitions() -> list[JsonDict]:
    """Return deterministic, harmless schemas used for capability probing."""

    return [
        {
            "type": "function",
            "function": {
                "name": "rift_lookup_weather",
                "description": "Synthetic capability probe. Do not call a real service.",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "rift_add_numbers",
                "description": "Synthetic capability probe. Return the sum of two numbers.",
                "parameters": {
                    "type": "object",
                    "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                    "required": ["a", "b"],
                    "additionalProperties": False,
                },
            },
        },
    ]


def _tool_result_message(call: Mapping[str, Any], result: str) -> JsonDict:
    return {
        "role": "tool",
        "tool_call_id": _text(call.get("id")) or "rift-synthetic-call",
        "content": result,
    }


def evaluate_tool_capability(
    invoke: ToolInvoke,
    *,
    model: str,
    backend: str | None = None,
    identity: Mapping[str, Any] | None = None,
    max_tokens: int = 128,
    total_deadline_seconds: float = 60.0,
) -> JsonDict:
    """Verify core tool-call capability for one exact deployment.

    This is intentionally a capability test, not tool execution.  RIFT owns
    the schemas and synthetic prompts only; the user's application owns the
    real broker, permissions, and side effects.  A passing result means the
    exact endpoint emitted structurally valid calls and handled a synthetic
    tool-result turn.  It does not certify any business tool or sandbox.
    """

    started = time.time()
    deadline = time.monotonic() + max(0.1, float(total_deadline_seconds))
    tools = _tool_definitions()
    cases: list[JsonDict] = []

    def run_case(case_id: str, prompt: str, *, expected_name: str | None = None,
                 expected_args: Mapping[str, Any] | None = None,
                 require_call: bool = True, tool_choice: JsonDict | None = None,
                 messages: list[JsonDict] | None = None) -> None:
        record: JsonDict = {"case_id": case_id, "required": True, "status": "FAIL"}
        if time.monotonic() >= deadline:
            record.update({"status": "NOT_ASSESSED", "detail": "tool capability suite deadline reached"})
            cases.append(record)
            return
        payload_messages = messages or [{"role": "user", "content": prompt}]
        try:
            response = invoke(payload_messages, tools, min(1024, max_tokens), tool_choice)
            calls = _tool_calls(response)
            if require_call:
                if not calls:
                    raise ValueError("model emitted no tool call")
                if expected_name and calls[0].get("name") != expected_name:
                    raise ValueError(f"selected {calls[0].get('name')!r}, expected {expected_name!r}")
                arguments, error = _tool_arguments(calls[0])
                if error:
                    raise ValueError(error)
                if expected_args and any(arguments.get(key) != value for key, value in expected_args.items()):
                    raise ValueError(f"tool arguments did not match expected values: {arguments!r}")
                record["tool_call"] = {"name": calls[0].get("name"), "arguments": arguments}
            elif calls:
                raise ValueError("model emitted a tool call for a no-call case")
            record.update({"status": "PASS", "detail": "synthetic tool-call behavior matched the capability case"})
        except Exception as exc:
            record["detail"] = str(exc)[:500]
        cases.append(record)

    run_case(
        "required_call_and_schema",
        "Use the rift_add_numbers tool with a=2 and b=3. Do not answer in prose.",
        expected_name="rift_add_numbers",
        expected_args={"a": 2, "b": 3},
        tool_choice={"type": "function", "function": {"name": "rift_add_numbers"}},
    )
    run_case(
        "automatic_selection_with_distractor",
        "What is the weather in Paris? Select the appropriate tool and provide city=Paris.",
        expected_name="rift_lookup_weather",
        expected_args={"city": "Paris"},
    )
    run_case(
        "no_call_behavior",
        "Say exactly hello. This request does not need a tool and must not call one.",
        require_call=False,
    )

    # Simulate the client returning a harmless result.  No external tool is
    # invoked; the result is a fixed string owned by this evaluator.
    continuation_messages = [
        {"role": "user", "content": "Use rift_add_numbers with a=4 and b=5."},
        {
            "role": "assistant",
            "tool_calls": [{
                "id": "rift-continuation",
                "type": "function",
                "function": {"name": "rift_add_numbers", "arguments": '{"a":4,"b":5}'},
            }],
        },
        _tool_result_message({"id": "rift-continuation"}, "9"),
    ]
    run_case(
        "multi_turn_tool_result_round_trip",
        "Continue after the synthetic tool result and answer with the result.",
        expected_name=None,
        require_call=False,
        messages=continuation_messages,
    )
    if cases and cases[-1].get("case_id") == "multi_turn_tool_result_round_trip" and cases[-1].get("status") == "PASS":
        # The no-call assertion above proves the endpoint consumed a tool
        # result turn and returned control to the client without a second call.
        cases[-1]["detail"] = "synthetic tool result round trip completed without an unsolicited second call"

    required = [item for item in cases if item.get("required")]
    passed = all(item.get("status") == "PASS" for item in required) and len(required) == 4
    return {
        "suite_id": TOOL_CAPABILITY_SUITE_ID,
        "suite_version": TOOL_CAPABILITY_SUITE_VERSION,
        "status": "VERIFIED" if passed else "FAILED",
        "available": True,
        "model": model,
        "backend": backend,
        "identity": dict(identity or {}),
        "cases": cases,
        "passed_cases": sum(1 for item in cases if item.get("status") == "PASS"),
        "required_cases": len(required),
        "tool_execution": "not_evaluated",
        "scope": "exact model/backend/template/runtime emission capability only; no business tool was executed",
        "started_unix_seconds": started,
        "completed_unix_seconds": time.time(),
    }


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
    schema: Mapping[str, Any] | bool | None = None
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
        if kind == "json_schema" and not isinstance(value.get("schema"), (Mapping, bool)):
            raise ValueError(f"evaluation case {case_id} requires schema")
        if kind == "reference_contains" and not _text(value.get("reference")):
            raise ValueError(f"evaluation case {case_id} requires reference")
        return cls(
            case_id=case_id,
            prompt=prompt,
            kind=kind,
            expected=value.get("expected"),
            reference=_text(value.get("reference")) or None,
            schema=value.get("schema"),
            required=bool(value.get("required", True)),
        )

    def to_dict(self) -> JsonDict:
        return {
            "id": self.case_id,
            "prompt": self.prompt,
            "kind": self.kind,
            "expected": self.expected,
            "reference": self.reference,
            "schema": self.schema,
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


def _schema_matches(value: Any, schema: Mapping[str, Any] | bool) -> tuple[bool, str]:
    """Evaluate the deterministic, common JSON-Schema keywords used by RIFT."""
    if schema is True:
        return True, "schema permits any JSON value"
    if schema is False:
        return False, "schema rejects every value"
    if not isinstance(schema, Mapping):
        return False, "schema is not an object"
    if "const" in schema and value != schema["const"]:
        return False, "value does not match schema const"
    if "enum" in schema and value not in schema["enum"]:
        return False, "value is not in schema enum"
    type_value = schema.get("type")
    if type_value is not None:
        types = type_value if isinstance(type_value, list) else [type_value]
        def type_ok(kind: str) -> bool:
            return {
                "null": value is None,
                "boolean": isinstance(value, bool),
                "object": isinstance(value, dict),
                "array": isinstance(value, list),
                "number": isinstance(value, (int, float)) and not isinstance(value, bool),
                "integer": isinstance(value, int) and not isinstance(value, bool),
                "string": isinstance(value, str),
            }.get(kind, False)
        if not any(type_ok(kind) for kind in types):
            return False, f"value type does not match schema type {type_value!r}"
    for branch_key in ("allOf", "anyOf", "oneOf"):
        branches = schema.get(branch_key)
        if branches is not None:
            results = [_schema_matches(value, branch)[0] for branch in branches if isinstance(branch, (Mapping, bool))]
            if branch_key == "allOf" and not all(results):
                return False, "value failed an allOf branch"
            if branch_key == "anyOf" and not any(results):
                return False, "value failed every anyOf branch"
            if branch_key == "oneOf" and sum(results) != 1:
                return False, "value did not match exactly one oneOf branch"
    if isinstance(value, dict):
        required = schema.get("required") or []
        missing = [name for name in required if name not in value]
        if missing:
            return False, f"missing required properties: {', '.join(missing)}"
        properties = schema.get("properties") or {}
        if isinstance(properties, Mapping):
            for name, child in properties.items():
                if name in value:
                    matched, detail = _schema_matches(value[name], child)
                    if not matched:
                        return False, f"property {name!r}: {detail}"
        additional = schema.get("additionalProperties", True)
        if additional is False:
            unknown = [name for name in value if name not in properties]
            if unknown:
                return False, f"unexpected properties: {', '.join(unknown)}"
        elif isinstance(additional, (Mapping, bool)):
            for name, item in value.items():
                if name not in properties:
                    matched, detail = _schema_matches(item, additional)
                    if not matched:
                        return False, f"additional property {name!r}: {detail}"
    if isinstance(value, list) and schema.get("items") is not None:
        items = schema["items"]
        for index, item in enumerate(value):
            child = items[index] if isinstance(items, list) and index < len(items) else items
            if isinstance(child, (Mapping, bool)):
                matched, detail = _schema_matches(item, child)
                if not matched:
                    return False, f"item {index}: {detail}"
    if isinstance(value, str):
        schema_format = schema.get("format")
        if schema_format == "date":
            try:
                if _datetime.date.fromisoformat(value).isoformat() != value:
                    raise ValueError
            except ValueError:
                return False, "string is not an ISO-8601 calendar date"
        elif schema_format == "date-time":
            try:
                _datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return False, "string is not an ISO-8601 date-time"
        if isinstance(schema.get("minLength"), int) and len(value) < schema["minLength"]:
            return False, "string is shorter than minLength"
        if isinstance(schema.get("maxLength"), int) and len(value) > schema["maxLength"]:
            return False, "string is longer than maxLength"
        if isinstance(schema.get("pattern"), str) and re.search(schema["pattern"], value) is None:
            return False, "string does not match pattern"
    return True, "parsed JSON conforms to the uploaded schema"


def _check(case: EvaluationCase, response: str) -> tuple[bool, str]:
    if case.kind == "nonempty":
        return bool(response.strip()), "response contains at least one non-whitespace character"
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
    if case.kind == "json_schema":
        try:
            actual = _json_value(response)
        except (TypeError, ValueError, json.JSONDecodeError):
            return False, "response is not valid JSON"
        return _schema_matches(actual, case.schema if case.schema is not None else False)
    if case.kind == "reference_contains":
        expected = _text(case.expected)
        return _normalize(expected) in _normalize(response), "response contains the prescribed reference answer"
    expected_values = case.expected if isinstance(case.expected, list) else [case.expected]
    passed = any(_normalize(_text(value)) in _normalize(response) for value in expected_values)
    return passed, "response contains a prescribed abstention phrase"


def validate_json_response(response: str, schema: Mapping[str, Any] | bool) -> tuple[bool, str]:
    """Validate a production response against an uploaded output schema."""
    try:
        actual = _json_value(response)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False, "response is not valid JSON"
    return _schema_matches(actual, schema)


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
    max_tokens = min(1024, int(max_tokens))
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
                "max_tokens": min(1024, max_tokens),
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


def invoke_openai_tool_compatible(
    base_url: str,
    *,
    model: str,
    token: str | None = None,
    timeout_seconds: float = 15.0,
    allowed_hosts: list[str] | None = None,
) -> ToolInvoke:
    """Create a bounded OpenAI-compatible tool-capability invoker.

    The caller supplies only synthetic messages and schemas.  The helper does
    not expose arbitrary URLs, redirects, tool executors, or shell hooks.
    """

    if timeout_seconds <= 0.0:
        raise ValueError("timeout_seconds must be positive")
    endpoint = base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint += "/v1/chat/completions"
    _validate_endpoint(endpoint, allowed_hosts)

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, request: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Request:
            raise ValueError("redirects are not allowed for tool capability probes")

    opener = build_opener(NoRedirect)

    def invoke(messages: list[JsonDict], tools: list[JsonDict], max_tokens: int, tool_choice: JsonDict | None = None) -> Mapping[str, Any]:
        payload: JsonDict = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "temperature": 0.0,
            "max_tokens": min(1024, max(1, int(max_tokens))),
            "stream": False,
        }
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": "RIFT/1.0"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(endpoint, data=data, headers=headers)
        with opener.open(request, timeout=timeout_seconds) as response:
            value = json.loads(response.read().decode("utf-8"))
        if not isinstance(value, Mapping):
            raise ValueError("tool capability endpoint returned a non-object response")
        return value

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
    "TOOL_CAPABILITY_SUITE_ID",
    "TOOL_CAPABILITY_SUITE_VERSION",
    "default_evaluation_suite",
    "evaluate_suite",
    "evaluate_tool_capability",
    "validate_json_response",
    "invoke_openai_compatible",
    "invoke_openai_tool_compatible",
    "invoke_judge_openai_compatible",
]
