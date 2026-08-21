import importlib
import json
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = ROOT / "python"
sys.path.insert(0, str(PYTHON_ROOT))


class FakeNativeEngine:
    def __init__(self, cuda_device_id=0):
        self.cuda_device_id = cuda_device_id

    def build_info(self):
        return {"version": "test", "phase": "Phase 28 + R10 primitives"}

    def hardware_profile(self):
        return {
            "cuda_available": True,
            "device_name": "Synthetic GPU",
            "total_vram_bytes": 8 * 1024**3,
            "free_vram_bytes": 7 * 1024**3,
            "total_host_ram_bytes": 16 * 1024**3,
            "compute_capability_major": 8,
            "compute_capability_minor": 9,
        }

    def inspect_model(self, model_path, **kwargs):
        return {
            "model_path": model_path,
            "config": {
                "model_type": "llama",
                "family": "LLAMA",
                "quantization": "GPTQ_INT4",
                "num_hidden_layers": 1,
                "hidden_size": 8,
                "vocab_size": 16,
            },
            "topology": {"total_model_bytes": 16, "w_max_bytes": 8},
            "profile": {"supported": True},
            "execution_policy": {"supported": True},
            "generation_readiness": {
                "ready": True,
                "issues": [],
                "output_head_mode": "DENSE_FP16_LM_HEAD_STREAMING",
            },
        }


fake_core = type(sys)("rift._core")
fake_core.InferenceEngine = FakeNativeEngine
fake_core.__version__ = "test"
fake_core.build_info = lambda: {"version": "test"}
fake_core.cuda_device_count = lambda: 1
fake_core.inspect_model = lambda model_path, **kwargs: FakeNativeEngine().inspect_model(
    model_path, **kwargs
)
fake_core.parse_model_topology = lambda *args, **kwargs: {}
sys.modules["rift._core"] = fake_core

hf_hub = importlib.import_module("rift.hf_hub")
rift = importlib.import_module("rift.rift")


FILES = {
    "config.json": json.dumps(
        {"model_type": "llama", "quantization_config": {"quant_method": "gptq"}}
    ).encode("utf-8"),
    "model.safetensors": b"safe-tensor-bytes",
    "nested/tokenizer.json": b'{"model":"tiny"}',
    "pytorch_model.bin": b"ignored",
    "../bad.json": b"unsafe",
}


class FakeHubHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/api/models/org/model/revision/main":
            siblings = [
                {"rfilename": name, "size": len(payload)}
                for name, payload in FILES.items()
            ]
            self._send_json({"sha": "abc123", "siblings": siblings})
            return
        prefix = "/org/model/resolve/main/"
        if path.startswith(prefix):
            name = path[len(prefix) :]
            if name in FILES:
                self._send_bytes(FILES[name])
                return
        self.send_error(404)

    def log_message(self, fmt, *args):
        return

    def _send_json(self, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class FakeHubServer:
    def __enter__(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeHubHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return f"http://127.0.0.1:{self.httpd.server_port}"

    def __exit__(self, exc_type, exc, tb):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


def test_file_selection_and_safety():
    files = [hf_hub.HubFile(name, len(payload)) for name, payload in FILES.items()]
    selected = hf_hub.select_hub_files(
        files,
        allow_patterns=("*.json", "*.safetensors"),
        ignore_patterns=("*.bin",),
    )
    names = [file.path for file in selected]
    assert "config.json" in names
    assert "model.safetensors" in names
    assert "nested/tokenizer.json" in names
    assert "pytorch_model.bin" not in names
    assert "../bad.json" not in names


def test_snapshot_download_and_rift_wrapper():
    with FakeHubServer() as endpoint, tempfile.TemporaryDirectory() as tmp:
        client = hf_hub.HfHubClient(endpoint=endpoint)
        dry = client.snapshot_download("org/model", dry_run=True)
        assert dry["file_count"] == 3
        assert dry["dry_run"] is True
        assert {item["path"] for item in dry["files"]} == {
            "config.json",
            "model.safetensors",
            "nested/tokenizer.json",
        }

        try:
            client.snapshot_download("org/model", dry_run=True, max_bytes=4)
        except ValueError as exc:
            assert "exceeding max_bytes" in str(exc)
        else:
            raise AssertionError("expected max_bytes rejection")

        original_disk_usage = hf_hub.shutil.disk_usage
        try:
            hf_hub.shutil.disk_usage = lambda _path: type(
                "Usage", (), {"total": 1024, "used": 1000, "free": 24}
            )()
            try:
                client.snapshot_download(
                    "org/model",
                    local_dir=str(Path(tmp) / "no-space"),
                    disk_reserve_bytes=16,
                )
            except ValueError as exc:
                assert "usable" in str(exc)
                assert "disk reserve" in str(exc)
            else:
                raise AssertionError("expected disk-capacity rejection")
        finally:
            hf_hub.shutil.disk_usage = original_disk_usage

        output_dir = Path(tmp) / "download"
        result = client.snapshot_download("org/model", local_dir=str(output_dir))
        assert result["downloaded_bytes"] == sum(
            len(FILES[name]) for name in ("config.json", "model.safetensors", "nested/tokenizer.json")
        )
        assert (output_dir / "config.json").read_bytes() == FILES["config.json"]
        assert (output_dir / "model.safetensors").read_bytes() == FILES["model.safetensors"]
        assert (output_dir / "nested" / "tokenizer.json").read_bytes() == FILES["nested/tokenizer.json"]
        assert not (output_dir / "pytorch_model.bin").exists()

        engine = rift.RiftEngine()
        wrapped = engine.pull_model_from_hub(
            "org/model",
            endpoint=endpoint,
            output_dir=str(Path(tmp) / "wrapped"),
        )
        assert wrapped["rift_phase"] == "R18"
        assert wrapped["compatibility_advice"]["support_level"] == "NATIVE_RUN_CANDIDATE"
        assert wrapped["inspection"]["rift_product"] == "RIFT"


def main():
    test_file_selection_and_safety()
    test_snapshot_download_and_rift_wrapper()
    print("rift hf hub tests passed")


if __name__ == "__main__":
    main()
