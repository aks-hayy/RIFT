import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from rift.orchestrator import RiftOrchestrator
from rift.operations import OperationStore
from rift.server import RiftServerRuntime


def _service():
    return {
        "backend": "llama.cpp",
        "model": {
            "source": "local",
            "local_path": "C:/models/tiny.gguf",
            "selected_file": "tiny.gguf",
            "format": "gguf",
            "quantization": "Q4_K_M",
        },
        "serving": {
            "api": "openai",
            "host": "127.0.0.1",
            "port": 11735,
            "context_length": 8192,
            "concurrency": 1,
        },
        "launch_plan": {
            "backend": "llama.cpp",
            "command": ["llama-server", "-m", "C:/models/tiny.gguf"],
            "display": "llama-server -m C:/models/tiny.gguf",
            "api_base": "http://127.0.0.1:11735",
            "openai_base": "http://127.0.0.1:11735/v1",
            "context_length": 8192,
            "concurrency": 1,
            "tuning": {"gpu_layers": 35},
        },
        "placement": {"node": "local"},
        "gateway": {"enabled": True, "host": "127.0.0.1", "port": 11734},
        "last_known_good_launch_plan": {
            "backend": "llama.cpp",
            "command": ["llama-server", "-m", "C:/models/tiny.gguf"],
            "gpu_layers": 35,
        },
    }


def test_deployment_record_survives_destroy_and_keeps_launch_details(tmp_path):
    runtime = tmp_path / "rift"
    orchestrator = RiftOrchestrator(root=tmp_path, runtime_root=runtime)
    service = _service()
    plan = {
        "plan_id": "plan-123",
        "plan_hash": "hash-123",
        "config_path": str(tmp_path / "rift.yaml"),
        "services": {"chat": service},
    }
    config = {"schema_version": 1, "project": "test", "services": {"chat": service}}
    orchestrator.write_state({"schema_version": 1, "services": {"chat": service}})

    record = orchestrator._upsert_deployment_record(
        service_name="chat",
        plan=plan,
        service=service,
        config=config,
        status="ready",
    )
    assert record["deployment_id"].startswith("dep-")
    assert record["model"]["quantization"] == "Q4_K_M"
    assert record["launch"]["context_length"] == 8192
    assert record["last_known_good"]["gpu_layers"] == 35

    destroyed = orchestrator.destroy(service_name="chat")
    assert destroyed["removed"] == ["chat"]
    saved = orchestrator.list_deployment_records()
    assert len(saved) == 1
    assert saved[0]["deployment_id"] == record["deployment_id"]
    assert saved[0]["status"] == "deleted"
    assert saved[0]["model"]["local_path"] == "C:/models/tiny.gguf"

    raw = json.loads((runtime / "deployments" / "records.json").read_text(encoding="utf-8"))
    assert raw["records"][0]["service_name"] == "chat"


def test_deployment_record_api_exposes_records_and_launch_action(tmp_path):
    class FakeOrchestrator:
        def list_deployment_records(self):
            return [{"deployment_id": "dep-1", "service_name": "chat", "status": "deleted"}]

        def relaunch_deployment(self, **kwargs):
            assert kwargs["record_id"] == "dep-1"
            assert kwargs["allow_launch"] is True
            return {"applied": True, "deployment_id": "dep-1"}

    runtime = RiftServerRuntime(
        orchestrator_factory=lambda: FakeOrchestrator(),
        operation_store=OperationStore(tmp_path / "operations"),
    )
    assert runtime.control_get("/api/rift/v2/deployment-records")["records"][0]["deployment_id"] == "dep-1"
    result = runtime.control_post(
        "/api/rift/v2/deployment-records/dep-1/launch",
        {"allow_launch": True},
    )
    assert result["applied"] is True
    runtime.shutdown()


def test_settings_snapshot_surfaces_exposure_cors_and_api_key_warnings(tmp_path, monkeypatch):
    (tmp_path / "rift.yaml").write_text(
        """schema_version: 1
nodes:
  - name: local
    host: 127.0.0.1
services:
  chat:
    model:
      id: tiny.gguf
    serving:
      host: 0.0.0.0
      port: 11735
      context_length: 4096
      concurrency: 1
    exposure: network
    gateway:
      host: 0.0.0.0
      cors_origins: [\"*\"]
      api_key_env: RIFT_TEST_SETTINGS_KEYS
""",
        encoding="utf-8",
    )
    monkeypatch.delenv("RIFT_TEST_SETTINGS_KEYS", raising=False)
    orchestrator = RiftOrchestrator(root=tmp_path, runtime_root=tmp_path / ".rift")

    gateway = orchestrator.settings_snapshot()["gateway"]

    assert gateway["bound_host"] == "0.0.0.0"
    assert gateway["cors_origins"] == ["*"]
    assert gateway["api_key_protection"] == "not_configured"
    assert any("Unrestricted CORS" in item for item in gateway["security_warnings"])
    assert any("no API key" in item for item in gateway["security_warnings"])
