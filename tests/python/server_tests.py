import importlib
import json
import sys
import threading
import types
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = ROOT / "python"
sys.path.insert(0, str(PYTHON_ROOT))


class FakeNativeEngine:
    def __init__(self, cuda_device_id=0):
        self.cuda_device_id = cuda_device_id


fake_core = types.ModuleType("rift._core")
fake_core.InferenceEngine = FakeNativeEngine
fake_core.__version__ = "test"
fake_core.build_info = lambda: {"version": "test"}
fake_core.cuda_device_count = lambda: 1
fake_core.inspect_model = lambda *args, **kwargs: {}
fake_core.parse_model_topology = lambda *args, **kwargs: {}
sys.modules["rift._core"] = fake_core

server_mod = importlib.import_module("rift.server")


class FakeEngine:
    def run(self, **kwargs):
        return {
            "status": "ok",
            "text": "hi",
            "usability_verdict": "SLOW",
            "recommendations": ["test"],
            "tokens_per_second": 1.0,
            "generated_tokens": 1,
            "total_seconds": 1.0,
            "backend_metrics": {},
        }

    def list_reports(self):
        return {"reports": [{"path": "latest", "usability_verdict": "SLOW"}]}

    def compatibility_advice(self, model_path):
        return {"model_path": model_path, "family": "LLAMA", "support_level": "TEST"}

    def plan_model(self, model_path, **kwargs):
        return {
            "model_path": model_path,
            "selected_backend": "llama.cpp",
            "backend_decision": {"selected_backend": "llama.cpp", "backend_label": "llama.cpp"},
            "serving_plan": {"backend": "llama.cpp", "runnable_now": False},
            "kv_plan": {"pressure": "LOW"},
        }


def fake_factory():
    return FakeEngine()


class FakeOrchestrator:
    def discover(self, *, write=False):
        assert write is False
        return {
            "nodes": [
                {
                    "hardware": {
                        "capacity": {"vram_bytes": 8 * 1024**3},
                        "rift_managed_occupancy": {"running_service_count": 1},
                    }
                }
            ]
        }


class FakeMeshController:
    def __init__(self):
        self.scan_count = 0

    def discover(self, providers=None, *, options=None):
        self.scan_count += 1
        return {
            "api_version": "2",
            "evidence": "LIVE_DISCOVERY",
            "sightings": [
                {
                    "sighting_id": "seen-1",
                    "node_hint": "node-a",
                    "trust_state": "DISCOVERED_UNTRUSTED",
                }
            ],
            "providers": providers or [],
            "scan_count": self.scan_count,
        }

    def sightings(self):
        return {"api_version": "2", "sightings": [], "scan_count": self.scan_count}

    def nodes(self):
        return {"api_version": "2", "nodes": []}

    def topology(self):
        return {"api_version": "2", "nodes": [], "links": [], "evidence": "TEST"}

    def begin_enrollment(self, sighting_id, *, ttl_seconds=120):
        return {
            "enrollment_id": "enroll-1",
            "sighting_id": sighting_id,
            "expires_at": 1000 + ttl_seconds,
            "state": "PAIRING_PENDING",
        }

    def approve_enrollment(self, enrollment_id, pairing_code):
        assert enrollment_id == "enroll-1"
        assert pairing_code == "123456"
        return {"node": {"node_id": "node-1", "trust_state": "ENROLLED"}}

    def activate_enrollment(self, enrollment_id, certificate_fingerprint):
        return {
            "node": {
                "node_id": "node-1",
                "trust_state": "ACTIVE",
                "certificate_fingerprint": certificate_fingerprint,
            }
        }

    def issue_node_certificate(self, enrollment_id, csr_pem):
        return {
            "node": {"node_id": "node-1", "trust_state": "ACTIVE", "routable": True},
            "certificate_pem": "CERT",
            "ca_certificate_pem": "CA",
        }

    def update_capability(self, node_id, snapshot):
        return {"api_version": "2", "node": {"node_id": node_id, "sequence": snapshot["sequence"]}}

    def record_link(self, payload):
        return {"api_version": "2", "link": payload}

    def resolve_route(self, payload):
        return {
            "api_version": "2",
            "decision": {"selected": {"node_id": "node-1"}},
            "lease": {"service_id": payload["service_id"]},
        }


def request_json(base_url, path, payload=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(base_url + path, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=5) as response:
        body = response.read().decode("utf-8")
        return response.status, response.headers.get("Content-Type"), body


def request_with_origin(base_url, path, origin):
    request = urllib.request.Request(base_url + path, headers={"Origin": origin})
    with urllib.request.urlopen(request, timeout=5) as response:
        return (
            response.status,
            response.headers.get("Access-Control-Allow-Origin"),
            response.headers.get("Access-Control-Allow-Credentials"),
        )


def test_server_routes_and_streaming():
    runtime = server_mod.RiftServerRuntime(model_path="fixture", engine_factory=fake_factory)
    httpd = server_mod.create_rift_server(host="127.0.0.1", port=0, runtime=runtime)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{httpd.server_port}"
    try:
        status, _, body = request_json(base_url, "/rift/status")
        assert status == 200
        assert json.loads(body)["busy"] is False

        status, _, body = request_json(base_url, "/health")
        assert status == 200
        assert json.loads(body)["service"] == "rift"

        status, _, body = request_json(base_url, "/api/rift/plan")
        assert status == 200
        assert json.loads(body)["selected_backend"] == "llama.cpp"

        status, _, body = request_json(base_url, "/rift/compatibility")
        assert status == 200
        assert json.loads(body)["support_level"] == "TEST"

        status, _, body = request_json(base_url, "/rift/reports")
        assert status == 200
        assert json.loads(body)["reports"][0]["usability_verdict"] == "SLOW"

        status, content_type, body = request_json(
            base_url,
            "/v1/chat/completions",
            {
                "stream": True,
                "messages": [{"role": "user", "content": "hello"}],
                "max_tokens": 1,
            },
        )
        assert status == 200
        assert content_type.startswith("text/event-stream")
        assert "data: [DONE]" in body
        assert "rift-chat-local" in body
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_runtime_cors_origins_allow_custom_dashboard_ports():
    runtime = server_mod.RiftServerRuntime(cors_origins=("http://127.0.0.1:8971",))
    httpd = server_mod.create_rift_server(host="127.0.0.1", port=0, runtime=runtime)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{httpd.server_port}"
    try:
        status, allowed_origin, allow_credentials = request_with_origin(
            base_url, "/health", "http://127.0.0.1:8971"
        )
        assert status == 200
        assert allowed_origin == "http://127.0.0.1:8971"
        assert allow_credentials == "true"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_hardware_control_route_uses_state_aware_discovery():
    runtime = server_mod.RiftServerRuntime(orchestrator_factory=FakeOrchestrator)
    hardware = runtime.control_get("/api/rift/hardware")
    assert hardware["capacity"]["vram_bytes"] == 8 * 1024**3
    assert hardware["rift_managed_occupancy"]["running_service_count"] == 1


def test_mesh_control_routes_use_one_persistent_controller():
    mesh = FakeMeshController()
    runtime = server_mod.RiftServerRuntime(mesh_controller_factory=lambda: mesh)
    first = runtime.control_post("/api/rift/v2/mesh/discover", {"providers": ["mdns"]})
    second = runtime.control_post("/api/rift/v2/mesh/discover", {})
    assert first["scan_count"] == 1
    assert second["scan_count"] == 2
    assert runtime.control_get("/api/rift/v2/mesh/sightings")["scan_count"] == 2
    assert runtime.control_get("/api/rift/v2/mesh/nodes")["nodes"] == []
    assert runtime.control_get("/api/rift/v2/mesh/topology")["evidence"] == "TEST"

    challenge = runtime.control_post(
        "/api/rift/v2/mesh/enrollments", {"sighting_id": "seen-1", "ttl_seconds": 60}
    )
    assert challenge["state"] == "PAIRING_PENDING"
    assert "pairing_code" not in challenge
    approved = runtime.control_post(
        "/api/rift/v2/mesh/enrollments/enroll-1/approve", {"pairing_code": "123456"}
    )
    assert approved["node"]["trust_state"] == "ENROLLED"
    activated = runtime.control_post(
        "/api/rift/v2/mesh/enrollments/enroll-1/activate",
        {"certificate_fingerprint": "sha256:cert"},
    )
    assert activated["node"]["trust_state"] == "ACTIVE"
    certificate = runtime.control_post(
        "/api/rift/v2/mesh/enrollments/enroll-1/certificate", {"csr_pem": "CSR"}
    )
    assert certificate["node"]["routable"] is True
    capability = runtime.control_post(
        "/api/rift/v2/mesh/nodes/node-1/capabilities", {"sequence": 2}
    )
    assert capability["node"]["sequence"] == 2
    link = runtime.control_post(
        "/api/rift/v2/mesh/links",
        {"source_node_id": "node-1", "target_node_id": "node-2"},
    )
    assert link["link"]["target_node_id"] == "node-2"
    route = runtime.control_post(
        "/api/rift/v2/mesh/routes/resolve", {"service_id": "chat"}
    )
    assert route["lease"]["service_id"] == "chat"


def test_service_accounting_api_reads_and_updates_the_selected_service(tmp_path):
    from rift.operations import OperationStore
    from rift.orchestrator import RiftOrchestrator
    from rift.rift_yaml import write_yaml

    orchestrator = RiftOrchestrator(root=tmp_path)
    write_yaml(tmp_path / "rift.yaml", orchestrator.default_config())
    runtime = server_mod.RiftServerRuntime(
        orchestrator_factory=lambda: orchestrator,
        operation_store=OperationStore(tmp_path / "operations"),
    )
    try:
        path = "/api/rift/v2/services/chat/telemetry/accounting"
        initial = runtime.control_get(path)
        assert initial["configured"] is False
        updated = runtime.control_post(
            path,
            {"accounting": {"electricity_price_per_kwh": 0.22}},
        )
        assert updated["electricity_price_per_kwh"] == 0.22
        assert updated["electricity_price_source"] == "service"
        assert runtime.control_get(path)["electricity_price_per_kwh"] == 0.22
    finally:
        runtime.shutdown()
        orchestrator.close()


def main():
    test_server_routes_and_streaming()
    test_runtime_cors_origins_allow_custom_dashboard_ports()
    test_hardware_control_route_uses_state_aware_discovery()
    test_mesh_control_routes_use_one_persistent_controller()
    print("rift server tests passed")


if __name__ == "__main__":
    main()
