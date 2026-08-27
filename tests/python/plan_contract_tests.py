import json
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from rift.operations import OperationStore
from rift.server import RiftServerRuntime


class CapturingOrchestrator:
    def __init__(self, root: Path):
        self.root = root
        self.calls = []

    def plan_recommendation_run(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "plan_id": "plan-1",
            "plan_hash": "hash-1",
            "config_path": str(self.root / "plan.yaml"),
            "services": {kwargs["service_name"]: {"backend": kwargs["backend_kind"]}},
        }


def test_plan_creation_preserves_all_reviewed_deployment_intent(tmp_path):
    orchestrator = CapturingOrchestrator(tmp_path)
    runtime = RiftServerRuntime(
        orchestrator_factory=lambda: orchestrator,
        operation_store=OperationStore(tmp_path / "operations"),
    )

    result = runtime.control_post(
        "/api/rift/v2/plans",
        {
            "recommendation_run_id": "run-1",
            "selector": "artifact-1",
            "artifact_id": "artifact-1",
            "backend_kind": "vllm",
            "target_node_id": "node-2",
            "service_name": "coding",
            "exposure": "lan",
        },
    )

    assert result["plan_id"] == "plan-1"
    assert orchestrator.calls == [
        {
            "run_id": "run-1",
            "selector": "artifact-1",
            "artifact_id": "artifact-1",
            "backend_kind": "vllm",
            "target_node_id": "node-2",
            "service_name": "coding",
            "exposure": "lan",
            "output": None,
        }
    ]


def test_operation_store_rejects_same_request_id_with_different_payload(tmp_path):
    store = OperationStore(tmp_path / "operations")
    first = store.begin(
        "request-1",
        action="/api/rift/v2/plans",
        actor="operator",
        payload={"plan_id": "plan-1", "plan_hash": "hash-1"},
    )
    assert first["status"] == "RUNNING"

    try:
        store.begin(
            "request-1",
            action="/api/rift/v2/plans",
            actor="operator",
            payload={"plan_id": "plan-2", "plan_hash": "hash-2"},
        )
    except ValueError as exc:
        assert "payload" in str(exc)
    else:
        raise AssertionError("a reused request ID with a different payload must be rejected")


def test_operation_store_reports_atomic_claim_ownership(tmp_path):
    store = OperationStore(tmp_path / "operations")
    first, first_claimed = store.begin_claim(
        "claim-once",
        action="/api/rift/v2/apply",
        payload={"service": "chat"},
    )
    second, second_claimed = store.begin_claim(
        "claim-once",
        action="/api/rift/v2/apply",
        payload={"service": "chat"},
    )
    assert first_claimed is True
    assert second_claimed is False
    assert second["operation_id"] == first["operation_id"]


def test_operation_store_persists_progress_and_can_reload_by_operation_id(tmp_path):
    store = OperationStore(tmp_path / "operations")
    started = store.begin("request-2", action="/api/rift/apply", actor="operator", payload={})
    store.update(
        "request-2",
        stage="launching",
        message="Starting backend",
        percent=None,
        details={"service": "chat"},
    )

    loaded = store.load_operation(started["operation_id"])
    assert loaded is not None
    assert loaded["stage"] == "launching"
    assert loaded["percent"] is None
    assert loaded["details"] == {"service": "chat"}


def test_operation_store_can_cancel_running_operation_without_losing_payload(tmp_path):
    store = OperationStore(tmp_path / "operations")
    started = store.begin(
        "cancel-me",
        action="/api/rift/v2/plans/p1/apply",
        payload={"x": 1},
    )
    cancelled = store.cancel(started["operation_id"], reason="operator requested cancellation")
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["stage"] == "cancelled"
    assert cancelled["payload_sha256"] == started["payload_sha256"]
    assert "operator requested cancellation" in cancelled["message"]


def test_server_background_apply_returns_operation_and_persists_result(tmp_path):
    class SlowOrchestrator:
        def apply(self, **kwargs):
            time.sleep(0.02)
            assert kwargs["plan_id"] == "plan-1"
            return {"applied": True, "plan_id": "plan-1", "results": []}

    runtime = RiftServerRuntime(
        orchestrator_factory=SlowOrchestrator,
        operation_store=OperationStore(tmp_path / "operations"),
    )
    request_id = "async-apply"
    operation = runtime.operation_store.begin(
        request_id,
        action="/api/rift/v2/plans/plan-1/apply",
        payload={"plan_hash": "hash-1"},
    )
    started = runtime.start_background_operation(
        "/api/rift/v2/plans/plan-1/apply",
        {"plan_hash": "hash-1"},
        request_id=request_id,
        operation=operation,
        authorization=None,
    )
    assert started["operation_id"] == operation["operation_id"]
    assert started["status"] == "RUNNING"
    for _ in range(50):
        record = runtime.operation_store.load_operation(operation["operation_id"])
        if record and record["status"] == "SUCCEEDED":
            break
        time.sleep(0.01)
    record = runtime.operation_store.load_operation(operation["operation_id"])
    assert record is not None
    assert record["status"] == "SUCCEEDED"
    assert record["result"]["applied"] is True
    runtime.shutdown()


def test_server_background_operations_serialize_by_service(tmp_path):
    active = 0
    maximum = 0
    guard = __import__("threading").Lock()

    runtime = RiftServerRuntime(operation_store=OperationStore(tmp_path / "operations"))

    def slow_control_post(path, payload, *, authorization=None, progress=None):
        nonlocal active, maximum
        with guard:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.04)
        with guard:
            active -= 1
        return {"available": True, "service": payload["service"]}

    runtime.control_post = slow_control_post
    operations = []
    for index in range(2):
        request_id = f"serialized-{index}"
        operation = runtime.operation_store.begin(
            request_id,
            action="/api/rift/benchmark",
            payload={"service": "same-service", "index": index},
        )
        operations.append(
            runtime.start_background_operation(
                "/api/rift/benchmark",
                {"service": "same-service", "index": index},
                request_id=request_id,
                operation=operation,
                authorization=None,
            )
        )
    for _ in range(100):
        records = [runtime.operation_store.load_operation(item["operation_id"]) for item in operations]
        if all(record and record["status"] == "SUCCEEDED" for record in records):
            break
        time.sleep(0.01)
    assert maximum == 1
    runtime.shutdown()
