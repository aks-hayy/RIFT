import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))

from rift.execution_policy import ACTIONS, content_hash
from rift.server import RiftServerRuntime
from rift.workload_compiler import compile_workload


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


def test_compile_accepts_uploaded_schema_and_revision_preserves_it(tmp_path, monkeypatch):
    monkeypatch.setenv("RIFT_HOME", str(tmp_path))
    runtime = RiftServerRuntime()
    schema = {"type": "object", "properties": {"total": {"type": "number"}}, "required": ["total"]}
    draft = runtime.control_post("/api/rift/v2/workloads/compile", {
        "workload": "Return strict JSON invoice output",
        "output_schema": schema,
        "output_schema_filename": "invoice.schema.json",
    })
    artifact = draft["contract"]["output_schema"]
    assert artifact["filename"] == "invoice.schema.json"
    assert len(artifact["sha256"]) == 64
    assert not any("Upload a JSON Schema" in question for question in draft["questions"])
    edited = runtime.control_put("/api/rift/v2/workloads/" + draft["draft_id"], {"revision": 1, "workload": "Return strict JSON invoice output with a total"})
    assert edited["contract"]["output_schema"]["sha256"] == artifact["sha256"]


def test_medical_workload_compile_exposes_uptime_monitoring_objective(tmp_path, monkeypatch):
    monkeypatch.setenv("RIFT_HOME", str(tmp_path))
    runtime = RiftServerRuntime()
    schema = {"type": "object", "properties": {"patient_id": {"type": "string"}}, "required": ["patient_id"]}
    draft = runtime.control_post("/api/rift/v2/workloads/compile", {
        "workload": "Offline medical summarizer, 32K context, 99.9% uptime, strict JSON, no external network",
        "confirm_default_quality": True,
        "output_schema": schema,
        "output_schema_filename": "ehr.schema.json",
    })
    objective = draft["contract"]["monitoring"]["objectives"][0]
    assert objective["metric"] == "service.availability_ratio"
    assert objective["threshold"] == 0.999
    assert draft["contract"]["monitoring"]["observation_window_seconds"] == 2592000


def test_recommendation_api_forwards_workload_endpoint_refresh_and_search_limit(tmp_path):
    class Engine:
        def __init__(self):
            self.kwargs = None

        def recommend_models(self, **kwargs):
            self.kwargs = kwargs
            return {"recommendations": [], "query_arms": []}

    class Orchestrator:
        def __init__(self):
            self.rift_dir = tmp_path
            self.engine = Engine()

    orchestrator = Orchestrator()
    runtime = RiftServerRuntime(orchestrator_factory=lambda: orchestrator)
    contract = compile_workload("RAG assistant, 16K context", confirm_default_quality=True)["contract"]
    runtime.control_post("/api/rift/v2/recommendations", {
        "task": "chat",
        "endpoint": "https://hub.example",
        "refresh": True,
        "search_candidate_limit": 400,
        "workload_contract": contract,
    })
    assert orchestrator.engine.kwargs["task"] == "chat"
    assert orchestrator.engine.kwargs["endpoint"] == "https://hub.example"
    assert orchestrator.engine.kwargs["refresh"] is True
    assert orchestrator.engine.kwargs["search_candidate_limit"] == 400
    assert orchestrator.engine.kwargs["workload_contract"] == contract
