import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))

from rift.execution_policy import ACTIONS, content_hash
from rift.server import RiftServerRuntime


def _policy():
    return {
        "schema_version": 1,
        "actions": {name: True for name in ACTIONS},
        "targets": ["local"], "sources": ["huggingface"], "licenses": ["Apache-2.0"],
        "network": "approved_sources",
        "limits": {"exploration_seconds": 600, "max_artifacts": 2, "tuning_candidates": 4,
                    "per_artifact_bytes": 1000, "total_download_bytes": 2000},
        "allow_quantization_alternatives": False, "exposure": "loopback", "operations_mode": "recover",
    }


def test_compile_list_get_and_edit_are_immutable(tmp_path, monkeypatch):
    monkeypatch.setenv("RIFT_HOME", str(tmp_path))
    runtime = RiftServerRuntime()
    draft = runtime.control_post("/api/rift/v2/workloads/compile", {"workload": "chat, at least 10 tok/s"})
    assert draft["revision"] == 1 and draft["status"] == "COMPILED"
    assert runtime.control_get("/api/rift/v2/workloads/" + draft["draft_id"])["contract_hash"] == draft["contract_hash"]
    persisted = runtime.control_get("/api/rift/v2/workloads/" + draft["draft_id"])
    assert persisted["limitations"]
    edited = runtime.control_put("/api/rift/v2/workloads/" + draft["draft_id"], {"revision": 1, "workload": "coding, at least 20 tok/s"})
    assert edited["revision"] == 2
    assert runtime.control_get("/api/rift/v2/workloads/" + draft["draft_id"], {"revision": ["1"]})["status"] == "SUPERSEDED"
    assert runtime.control_get("/api/rift/v2/workloads")["drafts"][0]["revision"] == 2
    with pytest.raises(ValueError, match="stale"):
        runtime.control_put("/api/rift/v2/workloads/" + draft["draft_id"], {"revision": 1, "workload": "chat"})


def test_approval_stays_review_only_and_requires_saved_policy(tmp_path, monkeypatch):
    monkeypatch.setenv("RIFT_HOME", str(tmp_path))
    runtime = RiftServerRuntime()
    store = runtime.workload_store()
    policy = _policy()
    saved = store.save_policy("local", policy, expected_revision=0)
    draft = runtime.control_post("/api/rift/v2/workloads/compile", {
        "workload": {"task": "coding", "objective": "speed", "performance": {"context_tokens": 2048, "concurrency": 1, "ttft_percentile": 95},
                      "quality": {"suite_id": "suite", "suite_version": "1", "minimum_score": .9, "required_cases": ["code"]},
                      "capabilities": {"tool_calling": False, "structured_output": False},
                      "policies": {"network": "approved_sources", "backend": None, "model_family": None}, "service": {"name": "coder"}}
    })
    # Compiler still asks for an explicit quality review only when it had to default it.
    assert draft["questions"] == []
    approval = runtime.control_post("/api/rift/v2/workloads/" + draft["draft_id"] + "/approve", {
        "revision": draft["revision"], "contract_hash": draft["contract_hash"], "policy_id": "local",
        "policy_revision": saved["revision"], "envelope": policy, "envelope_hash": content_hash(policy),
    })
    assert approval["status"] == "APPROVED"
    assert approval["deployment_started"] is False
