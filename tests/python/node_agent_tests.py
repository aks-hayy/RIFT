import importlib
from pathlib import Path
import sys
import tempfile
import types


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


class FakeNativeEngine:
    def __init__(self, cuda_device_id=0):
        self.cuda_device_id = cuda_device_id

    def hardware_profile(self):
        return {
            "cuda_available": False,
            "total_vram_bytes": 0,
            "free_vram_bytes": 0,
            "total_host_ram_bytes": 16 * 1024**3,
            "free_host_ram_bytes": 12 * 1024**3,
        }

    def build_info(self):
        return {"version": "test"}


fake_core = types.ModuleType("rift._core")
fake_core.InferenceEngine = FakeNativeEngine
fake_core.__version__ = "test"
fake_core.build_info = lambda: {"version": "test"}
fake_core.cuda_device_count = lambda: 0
fake_core.inspect_model = lambda *args, **kwargs: {}
fake_core.parse_model_topology = lambda *args, **kwargs: {}
sys.modules["rift._core"] = fake_core


node_agent_mod = importlib.import_module("rift.node_agent")
transport_mod = importlib.import_module("rift.transport")
cluster_mod = importlib.import_module("rift.cluster")
registry_mod = importlib.import_module("rift.adapters.registry")
contracts = importlib.import_module("rift.adapters.contracts")
rift_yaml = importlib.import_module("rift.rift_yaml")


class MinimalOrchestrator:
    def discover(self, **_kwargs):
        return {"nodes": [{"hardware": {"total_host_ram_bytes": 16}, "backends": {}}]}

    def scan_local_models(self, _path):
        return []

    def status(self):
        return {"services": {}}

    def read_state(self):
        return {
            "services": {
                "chat": {
                    "runtime": {"api_base": "http://127.0.0.1:11999"},
                    "desired_state": "running",
                }
            }
        }


class FakeAgentTransport:
    name = "rift_agent"

    def __init__(self):
        self.submissions = []

    def submit_desired_state(self, node, *, generation, config, allow_remote=False):
        self.submissions.append((node, generation, config, allow_remote))
        return {"accepted": True, "generation": generation}

    def reconcile(self, node, *, permissions, allow_remote=False):
        return {"reconciled": True, "applied": True, "permissions": permissions}


class ThirdPartyBackend:
    name = "cluster-test"
    manifest = contracts.AdapterManifest(
        adapter_id=name,
        display_name="Cluster test",
        upstream_project="tests/cluster",
        adapter_version="1.0.0",
        adapter_api_version=contracts.ADAPTER_API_VERSION,
        kind="backend",
        capability=contracts.BackendCapability(
            tasks=("chat",),
            formats=("future-format",),
            quantizations=("int4",),
            operating_systems=("linux", "windows"),
            accelerators=("cpu",),
        ),
    )

    def probe(self, *, search_root=None):
        return {"available": True}

    def capabilities(self):
        return self.manifest.capability.to_dict()

    def install_plan(self):
        return {}

    def install(self, **_kwargs):
        return {"installed": True}

    def evaluate_fit(self, **_kwargs):
        return {"fits": True}

    def build_launch_spec(self, **_kwargs):
        return {}

    def launch(self, *_args, **_kwargs):
        return {}

    def health(self, **_kwargs):
        return {"healthy": True}

    def benchmark(self, **_kwargs):
        return {}

    def tuning_space(self, **_kwargs):
        return []

    def stop(self, **_kwargs):
        return {"stopped": True}

    def recover(self, *_args, **_kwargs):
        return {}


def policy():
    return node_agent_mod.NodeAgentPolicy(
        node_id="node-a",
        host="127.0.0.1",
        port=11750,
        certificate="node.crt",
        private_key="node.key",
        client_ca="ca.crt",
    )


def test_authenticated_inference_proxy_uses_managed_backend_route():
    class FakeResponse:
        status = 200
        headers = {"Content-Type": "application/json"}

        def read(self, _limit=None):
            return b'{"id":"chatcmpl-test","choices":[{"message":{"content":"ok"}}]}'

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    with tempfile.TemporaryDirectory() as tmp:
        agent_policy = node_agent_mod.NodeAgentPolicy(
            **{**policy().__dict__, "allow_inference": True}
        )
        controller = node_agent_mod.NodeAgentController(
            root=tmp,
            policy=agent_policy,
            orchestrator=MinimalOrchestrator(),
        )
        original = node_agent_mod.urlopen
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["body"] = request.data
            captured["timeout"] = timeout
            return FakeResponse()

        node_agent_mod.urlopen = fake_urlopen
        try:
            result = controller.inference(
                {
                    "service": "chat",
                    "path": "/v1/chat/completions",
                    "body": {"model": "local", "messages": [{"role": "user", "content": "hi"}]},
                }
            )
        finally:
            node_agent_mod.urlopen = original
        assert result["status"] == 200
        assert result["body"]["choices"][0]["message"]["content"] == "ok"
        assert captured["url"] == "http://127.0.0.1:11999/v1/chat/completions"


def test_node_desired_state_generation_is_monotonic_and_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        controller = node_agent_mod.NodeAgentController(
            root=tmp,
            policy=policy(),
            orchestrator=MinimalOrchestrator(),
        )
        config = {"version": 1, "nodes": [{"name": "local"}], "services": {"chat": {}}}
        first = controller.submit_desired_state({"generation": 2, "config": config})
        assert first["changed"]
        repeated = controller.submit_desired_state({"generation": 2, "config": config})
        assert not repeated["changed"]
        for payload, expected in (
            ({"generation": 1, "config": config}, "stale"),
            ({"generation": 2, "config": {**config, "project": "different"}}, "collision"),
        ):
            try:
                controller.submit_desired_state(payload)
            except ValueError as exc:
                assert expected in str(exc)
            else:
                raise AssertionError(f"{expected} desired state was accepted")


def test_agent_transport_requires_https_and_complete_mutual_tls_material():
    transport = transport_mod.RiftAgentTransport()
    base = {
        "name": "node-a",
        "agent": {
            "url": "http://node-a:11750",
            "ca_certificate": "ca.crt",
            "client_certificate": "client.crt",
            "client_key": "client.key",
        },
    }
    try:
        transport.discovery_plan(base)
    except ValueError as exc:
        assert "https://" in str(exc)
    else:
        raise AssertionError("insecure agent URL was accepted")
    base["agent"]["url"] = "https://node-a:11750"
    base["agent"]["client_key"] = ""
    try:
        transport.discovery_plan(base)
    except ValueError as exc:
        assert "client_key" in str(exc)
    else:
        raise AssertionError("incomplete mTLS config was accepted")
    assert callable(transport_mod.PowerShellRemotingTransport().discovery_plan)
    assert callable(transport_mod.SshTransport().discovery_plan)


def test_remote_cluster_dispatches_desired_state_through_agent():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config = cluster_mod.example_emulated_cluster()
        config["mode"] = "remote"
        config["nodes"] = [config["nodes"][0]]
        config["nodes"][0].update(
            {
                "transport": "rift_agent",
                "agent": {
                    "url": "https://worker:11750",
                    "ca_certificate": "ca.crt",
                    "client_certificate": "client.crt",
                    "client_key": "client.key",
                },
            }
        )
        config["services"] = {"chat": {**config["services"]["chat"], "replicas": 1}}
        path = root / "cluster.yaml"
        rift_yaml.write_yaml(path, config)
        controller = cluster_mod.RiftClusterController(root=root)
        fake = FakeAgentTransport()
        controller.transports["rift_agent"] = fake
        blocked = controller.apply(cluster_config=path, allow_deploy=True)
        assert blocked["required_permission"] == "allow_remote"
        applied = controller.apply(
            cluster_config=path,
            allow_deploy=True,
            allow_remote=True,
            allow_download=True,
            allow_install=True,
        )
        assert applied["applied"], applied
        assert len(fake.submissions) == 1
        assert applied["remote_dispatch"][0]["ok"]


def test_cluster_accepts_new_entrypoint_format_without_core_map_changes():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        controller = cluster_mod.RiftClusterController(root=root)
        controller.backend_host = registry_mod.BackendAdapterHost(
            builtins=(ThirdPartyBackend(),),
            entry_point_group="rift.backend_adapters",
            load_entry_points=False,
        )
        config = {
            "version": 1,
            "mode": "emulated",
            "nodes": [
                {
                    "name": "future-node",
                    "hardware": {"ram_gb": 16, "disk_free_gb": 20, "vram_gb": 0},
                    "backends": ["cluster-test"],
                }
            ],
            "services": {
                "chat": {
                    "replicas": 1,
                    "task": "chat",
                    "model": {
                        "id": "org/future",
                        "format": "future-format",
                        "quantization": "int4",
                        "estimated_bytes": 1024,
                    },
                    "serving": {"context_length": 128, "concurrency": 1},
                    "policy": {"backend": "auto"},
                }
            },
        }
        path = root / "cluster.yaml"
        rift_yaml.write_yaml(path, config)
        plan = controller.plan(cluster_config=path)
        assert not plan["unscheduled"], plan
        assert plan["placements"][0]["backend"] == "cluster-test"


def main():
    test_node_desired_state_generation_is_monotonic_and_idempotent()
    test_authenticated_inference_proxy_uses_managed_backend_route()
    test_agent_transport_requires_https_and_complete_mutual_tls_material()
    test_remote_cluster_dispatches_desired_state_through_agent()
    test_cluster_accepts_new_entrypoint_format_without_core_map_changes()
    print("RIFT node agent tests passed")


if __name__ == "__main__":
    main()
