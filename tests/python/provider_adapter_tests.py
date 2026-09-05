import importlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
import types


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

fake_core = types.ModuleType("rift._core")
fake_core.InferenceEngine = object
fake_core.__version__ = "test"
fake_core.build_info = lambda: {"version": "test"}
fake_core.cuda_device_count = lambda: 0
fake_core.inspect_model = lambda *args, **kwargs: {}
fake_core.parse_model_topology = lambda *args, **kwargs: {}
sys.modules["rift._core"] = fake_core

conformance = importlib.import_module("rift.adapters.conformance")
llama_mod = importlib.import_module("rift.providers.llama_cpp")
vllm_mod = importlib.import_module("rift.providers.vllm")
sglang_mod = importlib.import_module("rift.providers.sglang")
mlx_mod = importlib.import_module("rift.providers.mlx_lm")


CUDA_HARDWARE = {
    "cuda_available": True,
    "total_vram_bytes": 24 * 1024**3,
    "total_host_ram_bytes": 64 * 1024**3,
    "identity": {"os": "linux", "architecture": "x86_64"},
}


def fake_detection(name, executable="fake-server", command_style="cli"):
    return {
        "backend": name,
        "available": True,
        "executable": executable,
        "source": "test",
        "command_style": command_style,
        "runtime_mode": "native",
        "version": "test",
        "runtime_feature_probe": {"probed": True, "supported": {}},
    }


def test_all_builtin_serving_adapters_pass_shared_contract_suite():
    adapters = [
        llama_mod.LlamaCppProvider(),
        vllm_mod.VllmProvider(),
        sglang_mod.SglangProvider(),
        mlx_mod.MlxLmProvider(),
    ]
    for adapter in adapters:
        adapter.detect = lambda search_root=None, name=adapter.name: fake_detection(name)
        report = conformance.BackendConformanceSuite().run(adapter, hardware=CUDA_HARDWARE)
        assert report["passed"], report


def test_vllm_and_sglang_container_launches_use_official_images_and_read_only_mounts():
    with tempfile.TemporaryDirectory() as tmp:
        model = Path(tmp) / "model"
        model.mkdir()
        weights = model / "model.safetensors"
        weights.write_bytes(b"fixture")
        old_vllm_runtime = vllm_mod.container_runtime_detection
        old_sglang_runtime = sglang_mod.container_runtime_detection
        runtime = lambda: {"available": True, "executable": "docker", "runtime": "docker"}
        try:
            vllm_mod.container_runtime_detection = runtime
            sglang_mod.container_runtime_detection = runtime
            vllm = vllm_mod.VllmProvider()
            vllm.detect = lambda search_root=None: {
                **fake_detection("vllm", "docker", "container"),
                "runtime_mode": "container",
            }
            vllm_plan = vllm.plan_launch(
                model_path=str(weights),
                host="127.0.0.1",
                port=18001,
                context_length=2048,
                concurrency=2,
                hardware=CUDA_HARDWARE,
            )
            assert vllm_plan["command"][:5] == ["docker", "run", "--rm", "--gpus", "all"]
            assert vllm_plan["container_image"] == vllm_mod.WINDOWS_V0_CONTAINER_IMAGE
            assert vllm_plan["container_image"] in vllm_plan["command"]
            assert any(value.endswith(":/models:ro") for value in vllm_plan["command"])
            image_index = vllm_plan["command"].index(vllm_plan["container_image"])
            assert vllm_plan["command"][image_index + 1] == "/models"
            assert "--model" not in vllm_plan["command"]
            assert ["--env", "VLLM_USE_V1=0"] == vllm_plan["command"][
                vllm_plan["command"].index("--env") : vllm_plan["command"].index("--env") + 2
            ]
            assert vllm_plan["tuning"]["vllm_use_v1"] is False

            sglang = sglang_mod.SglangProvider()
            sglang.detect = lambda search_root=None: {
                **fake_detection("sglang", "docker", "container"),
                "runtime_mode": "container",
            }
            sglang_plan = sglang.plan_launch(
                model_path=str(weights),
                host="127.0.0.1",
                port=18002,
                context_length=4096,
                concurrency=2,
                hardware=CUDA_HARDWARE,
            )
            assert sglang.container_image in sglang_plan["command"]
            assert ["python3", "-m", "sglang.launch_server"] == sglang_plan["command"][
                sglang_plan["command"].index(sglang.container_image) + 1 :
                sglang_plan["command"].index(sglang.container_image) + 4
            ]
        finally:
            vllm_mod.container_runtime_detection = old_vllm_runtime
            sglang_mod.container_runtime_detection = old_sglang_runtime


def test_vllm_and_sglang_wsl_launch_paths_are_explicit():
    old_vllm_wsl = vllm_mod.wsl_detection
    old_sglang_wsl = sglang_mod.wsl_detection
    try:
        available = lambda: {"available": True, "executable": "wsl.exe"}
        vllm_mod.wsl_detection = available
        sglang_mod.wsl_detection = available
        vllm = vllm_mod.VllmProvider()
        vllm.detect = lambda search_root=None: {
            **fake_detection("vllm", "/rift/vllm/python", "python-module"),
            "runtime_mode": "wsl2",
            "wsl_install": {"python": "/rift/vllm/python"},
        }
        plan = vllm.plan_launch(
            model_path="org/model",
            host="127.0.0.1",
            port=18003,
            context_length=1024,
            concurrency=1,
            hardware=CUDA_HARDWARE,
        )
        assert plan["command"][:6] == ["wsl.exe", "--", "env", "VLLM_USE_V1=0", "/rift/vllm/python", "-m"]
        assert "0.0.0.0" in plan["command"]

        sglang = sglang_mod.SglangProvider()
        sglang.detect = lambda search_root=None: {
            **fake_detection("sglang", "/rift/sglang/python", "python-module"),
            "runtime_mode": "wsl2",
            "wsl_install": {"python": "/rift/sglang/python"},
        }
        plan = sglang.plan_launch(
            model_path="org/model",
            host="127.0.0.1",
            port=18004,
            context_length=1024,
            concurrency=1,
            hardware=CUDA_HARDWARE,
        )
        assert plan["command"][:4] == ["wsl.exe", "--", "/rift/sglang/python", "-m"]
        assert "0.0.0.0" in plan["command"]
    finally:
        vllm_mod.wsl_detection = old_vllm_wsl
        sglang_mod.wsl_detection = old_sglang_wsl


def test_mlx_platform_fit_and_raw_server_security_gate():
    provider = mlx_mod.MlxLmProvider()
    provider.detect = lambda search_root=None: fake_detection(
        "mlx-lm", "/rift/mlx/python", "python-module"
    )
    apple = {
        "total_host_ram_bytes": 32 * 1024**3,
        "identity": {"os": "macos", "architecture": "arm64"},
    }
    fit = provider.model_fit(
        model={"format": "mlx", "total_bytes": 8 * 1024**3}, hardware=apple
    )
    assert fit["fits"]
    plan = provider.plan_launch(
        model_path="org/mlx-model",
        host="127.0.0.1",
        port=18005,
        context_length=4096,
        concurrency=1,
        hardware=apple,
    )
    assert plan["security"] == "loopback_only_use_rift_gateway"
    try:
        provider.plan_launch(
            model_path="org/mlx-model",
            host="0.0.0.0",
            port=18005,
            context_length=4096,
            concurrency=1,
            hardware=apple,
        )
    except ValueError as exc:
        assert "loopback" in str(exc)
    else:
        raise AssertionError("MLX-LM raw server accepted direct network exposure")


def test_llama_install_falls_back_when_latest_release_has_only_marker_assets():
    provider = llama_mod.LlamaCppProvider()
    marker_release = {
        "tag_name": "b9352",
        "html_url": "https://github.com/ggml-org/llama.cpp/releases/tag/b9352",
        "assets": [{"name": "nightly-tag.txt"}],
    }
    usable_asset = {
        "name": "llama-b10486-bin-win-cuda-12.4-x64.zip",
        "browser_download_url": "https://example.invalid/llama.zip",
    }
    fallback_release = {
        "tag_name": "b10486",
        "html_url": "https://github.com/ggml-org/llama.cpp/releases/tag/b10486",
        "assets": [usable_asset],
    }
    provider._latest_release_info = lambda: marker_release
    provider._release_history_info = lambda: [marker_release, fallback_release]
    selected = provider._select_install_release(variant="cuda12")
    assert selected["release"]["tag_name"] == "b10486"
    assert selected["assets"] == [usable_asset]


class OpenAIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.endswith("/v1/models"):
            body = b'{"data":[{"id":"fixture-model"}]}'
        else:
            body = b'{"status":"ok"}'
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length))
        OpenAIHandler.last_model = payload.get("model")
        body = json.dumps(
            {
                "choices": [{"message": {"content": "one two three four"}}],
                "usage": {"completion_tokens": 4},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return

    last_model = None


def test_openai_health_and_benchmark_contract_for_all_new_adapters():
    server = ThreadingHTTPServer(("127.0.0.1", 0), OpenAIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        for provider in (
            vllm_mod.VllmProvider(),
            sglang_mod.SglangProvider(),
            mlx_mod.MlxLmProvider(),
        ):
            assert provider.health(base_url=base)["healthy"]
            result = provider.benchmark(
                base_url=base, prompt="hello", max_tokens=4, timeout_seconds=5
            )
            assert result["generated_tokens_estimate"] == 4
            assert result["tokens_per_second_estimate"] > 0
            assert result["model_id"] == "fixture-model"
            assert OpenAIHandler.last_model == "fixture-model"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def main():
    test_all_builtin_serving_adapters_pass_shared_contract_suite()
    test_llama_install_falls_back_when_latest_release_has_only_marker_assets()
    test_vllm_and_sglang_container_launches_use_official_images_and_read_only_mounts()
    test_vllm_and_sglang_wsl_launch_paths_are_explicit()
    test_mlx_platform_fit_and_raw_server_security_gate()
    test_openai_health_and_benchmark_contract_for_all_new_adapters()
    print("RIFT provider adapter tests passed")


if __name__ == "__main__":
    main()
