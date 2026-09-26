import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


def test_workload_compiler_extracts_natural_language_with_provenance():
    from rift.workload_contracts import compile_workload
    draft = compile_workload("Private coding assistant, at least 30 tok/s, under 1.5 seconds, 8K context, tools required")
    assert draft.contract.task == "coding"
    assert draft.contract.performance["min_decode_tps"] == 30
    assert draft.contract.performance["max_ttft_ms"] == 1500
    assert draft.contract.performance["context_tokens"] == 8192
    assert draft.contract.capabilities["tool_calling"]["required"] is True
    assert draft.contract.annotations["/task"].source == "inferred"


def test_structured_compilation_and_stale_approval_are_fail_closed():
    import pytest
    from rift.workload_contracts import ApprovalEnvelope, approve_workload, compile_workload
    draft = compile_workload({"task": "chat", "slos": {"context_tokens": 4096, "concurrency": 1, "min_decode_tps": 10}})
    assert draft.contract.contract_hash
    with pytest.raises(ValueError):
        approve_workload(draft, contract_hash="wrong", envelope=ApprovalEnvelope("wrong", False, False, False, False, False, False, 1, 1, 60, 0))
