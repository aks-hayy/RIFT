import importlib
import json
import os
import sys
import tempfile
import threading
import time
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


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

gateway_mod = importlib.import_module("rift.gateway")


class FakeOrchestrator:
    def __init__(self, state):
        self.state = state

    def read_state(self):
        return self.state


class BackendState:
    def __init__(self, name, *, failure_status=None, delay_seconds=0.0):
        self.name = name
        self.failure_status = failure_status
        self.delay_seconds = delay_seconds
        self.requests = 0
        self.entered = threading.Event()


def create_backend(state):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):  # noqa: N802
            if self.path == "/v1/models":
                self._json(200, {"object": "list", "data": [{"id": state.name}]})
                return
            if self.path == "/health":
                self._json(200, {"status": "ok"})
                return
            self._json(404, {"error": "unknown"})

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            state.requests += 1
            state.entered.set()
            if state.delay_seconds:
                time.sleep(state.delay_seconds)
            if state.failure_status:
                self._json(state.failure_status, {"error": f"{state.name} unavailable"})
                return
            if payload.get("stream"):
                body = (
                    f'data: {{"choices":[{{"delta":{{"content":"{state.name}"}}}}]}}\n\n'
                    "data: [DONE]\n\n"
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self._json(
                200,
                {
                    "id": f"response-{state.name}",
                    "model": state.name,
                    "choices": [{"message": {"role": "assistant", "content": state.name}}],
                    "usage": {"prompt_tokens": 2, "completion_tokens": 1},
                },
            )

        def _json(self, status, payload):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def managed_state(primary_url, fallback_url=None):
    services = {
        "chat": {
            "backend": "fake-primary",
            "model": {"id": "primary-model"},
            "desired_state": "running",
            "status": "healthy",
            "runtime": {"pid": 101, "api_base": primary_url},
            "launch_plan": {"api_base": primary_url},
        }
    }
    if fallback_url:
        services["backup"] = {
            "backend": "fake-fallback",
            "model": {"id": "fallback-model"},
            "desired_state": "running",
            "status": "healthy",
            "runtime": {"pid": 102, "api_base": fallback_url},
            "launch_plan": {"api_base": fallback_url},
        }
    return {"schema_version": 1, "services": services}


def start_gateway(root, policy, state):
    runtime = gateway_mod.RiftGatewayRuntime(
        root=root,
        policy=policy,
        orchestrator_factory=lambda: FakeOrchestrator(state),
    )
    server = gateway_mod.create_gateway_server(host="127.0.0.1", port=0, runtime=runtime)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return runtime, server, thread, f"http://127.0.0.1:{server.server_port}"


def stop_server(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def request_json(base_url, path, payload=None, headers=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    merged = {"Content-Type": "application/json"}
    merged.update(headers or {})
    request = Request(base_url + path, data=data, headers=merged, method="POST" if data is not None else "GET")
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, dict(response.headers), response.read()
    except HTTPError as exc:
        body = exc.read()
        return exc.code, dict(exc.headers), body


def test_proxy_request_ids_streaming_metrics_and_limits():
    backend_state = BackendState("primary")
    backend, backend_thread = create_backend(backend_state)
    backend_url = f"http://127.0.0.1:{backend.server_port}"
    with tempfile.TemporaryDirectory() as tmp:
        policy = gateway_mod.GatewayPolicy(
            max_concurrent_requests=2,
            requests_per_minute=0,
            burst_requests_per_second=0,
            max_prompt_tokens=16,
            max_completion_tokens=8,
            max_total_tokens=24,
        )
        runtime, server, thread, gateway_url = start_gateway(
            tmp, policy, managed_state(backend_url)
        )
        try:
            status, headers, body = request_json(
                gateway_url,
                "/v1/chat/completions",
                {"messages": [{"role": "user", "content": "hello"}], "max_tokens": 4},
                {"X-Request-ID": "client-request-1"},
            )
            assert status == 200
            assert headers["X-Request-ID"] == "client-request-1"
            assert headers["X-RIFT-Backend-Service"] == "chat"
            assert json.loads(body)["model"] == "primary"

            status, _, body = request_json(
                gateway_url,
                "/v1/chat/completions",
                {
                    "messages": [{"role": "user", "content": "x" * 100}],
                    "max_tokens": 4,
                },
            )
            assert status == 400
            assert "prompt tokens" in json.loads(body)["error"]

            status, headers, body = request_json(
                gateway_url,
                "/v1/chat/completions",
                {
                    "stream": True,
                    "messages": [{"role": "user", "content": "stream"}],
                    "max_tokens": 4,
                },
            )
            assert status == 200
            assert headers["Content-Type"].startswith("text/event-stream")
            assert b"data: [DONE]" in body
            assert b"primary" in body

            metrics = runtime.metrics()
            assert metrics["requests_total"] == 3
            assert metrics["requests_succeeded"] == 2
            assert metrics["requests_failed"] == 1
            assert metrics["token_limit_rejected"] == 1
            assert metrics["bytes_sent"] > 0
            log_path = Path(tmp) / ".rift" / "logs" / "gateway.jsonl"
            records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
            assert len(records) == 3
            assert all(record["request_id"] for record in records)
            assert not any("Authorization" in json.dumps(record) for record in records)
        finally:
            stop_server(server, thread)
    stop_server(backend, backend_thread)


def test_rate_auth_concurrency_and_fallback():
    primary_state = BackendState("primary", failure_status=503)
    fallback_state = BackendState("fallback")
    primary, primary_thread = create_backend(primary_state)
    fallback, fallback_thread = create_backend(fallback_state)
    primary_url = f"http://127.0.0.1:{primary.server_port}"
    fallback_url = f"http://127.0.0.1:{fallback.server_port}"
    with tempfile.TemporaryDirectory() as tmp:
        policy = gateway_mod.GatewayPolicy(
            fallback_services=("backup",),
            requests_per_minute=1,
            burst_requests_per_second=10,
            max_concurrent_requests=1,
            api_key_env="RIFT_TEST_GATEWAY_KEYS",
        )
        old_key = os.environ.get("RIFT_TEST_GATEWAY_KEYS")
        os.environ["RIFT_TEST_GATEWAY_KEYS"] = "secret-key"
        runtime, server, thread, gateway_url = start_gateway(
            tmp,
            policy,
            managed_state(primary_url, fallback_url),
        )
        try:
            status, _, _ = request_json(
                gateway_url,
                "/v1/chat/completions",
                {"messages": [{"role": "user", "content": "hello"}], "max_tokens": 2},
            )
            assert status == 401

            auth = {"Authorization": "Bearer secret-key"}
            status, headers, body = request_json(
                gateway_url,
                "/v1/chat/completions",
                {"messages": [{"role": "user", "content": "hello"}], "max_tokens": 2},
                auth,
            )
            assert status == 200
            assert headers["X-RIFT-Backend-Service"] == "backup"
            assert json.loads(body)["model"] == "fallback"

            status, headers, body = request_json(
                gateway_url,
                "/v1/chat/completions",
                {"messages": [{"role": "user", "content": "again"}], "max_tokens": 2},
                auth,
            )
            assert status == 429
            assert "Retry-After" in headers
            assert "rate" in json.loads(body)["error"]
            metrics = runtime.metrics()
            assert metrics["authentication_rejected"] == 1
            assert metrics["rate_limited"] == 1
            assert metrics["fallbacks_used"] == 1
            assert primary_state.requests == 1
            assert fallback_state.requests == 1
        finally:
            stop_server(server, thread)
            if old_key is None:
                os.environ.pop("RIFT_TEST_GATEWAY_KEYS", None)
            else:
                os.environ["RIFT_TEST_GATEWAY_KEYS"] = old_key
    stop_server(primary, primary_thread)
    stop_server(fallback, fallback_thread)

    slow_state = BackendState("slow", delay_seconds=0.35)
    slow, slow_thread = create_backend(slow_state)
    slow_url = f"http://127.0.0.1:{slow.server_port}"
    with tempfile.TemporaryDirectory() as tmp:
        policy = gateway_mod.GatewayPolicy(
            max_concurrent_requests=1,
            requests_per_minute=0,
            burst_requests_per_second=0,
        )
        runtime, server, thread, gateway_url = start_gateway(tmp, policy, managed_state(slow_url))
        first_result = {}

        def first_request():
            first_result["value"] = request_json(
                gateway_url,
                "/v1/chat/completions",
                {"messages": [{"role": "user", "content": "slow"}], "max_tokens": 2},
            )

        worker = threading.Thread(target=first_request)
        worker.start()
        assert slow_state.entered.wait(timeout=2)
        try:
            status, _, body = request_json(
                gateway_url,
                "/v1/chat/completions",
                {"messages": [{"role": "user", "content": "second"}], "max_tokens": 2},
            )
            assert status == 429
            assert "concurrency" in json.loads(body)["error"]
            worker.join(timeout=3)
            assert first_result["value"][0] == 200
            assert runtime.metrics()["concurrency_rejected"] == 1
        finally:
            worker.join(timeout=3)
            stop_server(server, thread)
    stop_server(slow, slow_thread)


def test_policy_loading():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config = {
            "services": {
                "chat": {
                    "gateway": {
                        "host": "127.0.0.1",
                        "port": 18080,
                        "max_concurrent_requests": 3,
                        "fallback_services": ["backup"],
                    }
                }
            }
        }
        path = root / "rift.yaml"
        path.write_text(json.dumps(config), encoding="utf-8")
        policy = gateway_mod.load_gateway_policy(path)
        assert policy.port == 18080
        assert policy.max_concurrent_requests == 3
        assert policy.fallback_services == ("backup",)


def main():
    test_proxy_request_ids_streaming_metrics_and_limits()
    test_rate_auth_concurrency_and_fallback()
    test_policy_loading()
    print("rift gateway tests passed")


if __name__ == "__main__":
    main()
