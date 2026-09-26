"""Tests for exact model/backend tool-call capability verification."""

from __future__ import annotations

from typing import Any

from rift.evaluation import evaluate_tool_capability


def _call(name: str, arguments: dict[str, Any], call_id: str = "call-1") -> dict[str, Any]:
    import json

    return {
        "choices": [{
            "message": {
                "role": "assistant",
                "tool_calls": [{
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments)},
                }],
            }
        }]
    }


def test_tool_capability_suite_accepts_core_behavior() -> None:
    def invoke(messages, tools, max_tokens, tool_choice):
        text = str(messages[-1].get("content") or "")
        if "does not need a tool" in text or messages[-1].get("role") == "tool":
            return {"choices": [{"message": {"role": "assistant", "content": "hello"}}]}
        if "weather" in text.lower():
            return _call("rift_lookup_weather", {"city": "Paris"})
        return _call("rift_add_numbers", {"a": 2, "b": 3})

    result = evaluate_tool_capability(invoke, model="fixture", backend="llama.cpp")
    assert result["status"] == "VERIFIED"
    assert result["tool_execution"] == "not_evaluated"
    assert result["passed_cases"] == 4
    assert result["scope"].startswith("exact model/backend/template/runtime")


def test_static_capability_claim_cannot_replace_live_probe() -> None:
    def invoke(messages, tools, max_tokens, tool_choice):
        # Looks like a normal answer even though a manifest could advertise
        # tool support.  The exact endpoint must fail closed.
        return {"choices": [{"message": {"role": "assistant", "content": "I can call tools."}}]}

    result = evaluate_tool_capability(invoke, model="fixture", backend="vllm")
    assert result["status"] == "FAILED"
    assert any(case["status"] == "FAIL" for case in result["cases"])


def test_legacy_function_call_shape_is_accepted() -> None:
    def invoke(messages, tools, max_tokens, tool_choice):
        text = str(messages[-1].get("content") or "")
        if "does not need a tool" in text or messages[-1].get("role") == "tool":
            return {"choices": [{"message": {"role": "assistant", "content": "hello"}}]}
        return {"choices": [{"message": {"function_call": {"name": "rift_add_numbers", "arguments": '{"a":2,"b":3}'}}}]}

    result = evaluate_tool_capability(invoke, model="fixture", backend="legacy")
    assert result["status"] == "FAILED"  # distractor and continuation are intentionally unsupported
    assert result["cases"][0]["status"] == "PASS"


if __name__ == "__main__":
    test_tool_capability_suite_accepts_core_behavior()
    test_static_capability_claim_cannot_replace_live_probe()
    test_legacy_function_call_shape_is_accepted()
    print("tool_capability_tests: PASS")
