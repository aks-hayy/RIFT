import importlib
import sys
import tempfile
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = ROOT / "python"
sys.path.insert(0, str(PYTHON_ROOT))


class FakeNativeEngine:
    def __init__(self, cuda_device_id=0):
        self.cuda_device_id = cuda_device_id

    def hardware_profile(self):
        return {}

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

cluster_mod = importlib.import_module("rift.cluster")
rift_yaml_mod = importlib.import_module("rift.rift_yaml")


def test_emulated_cluster_lifecycle_tuning_and_disaster_recovery():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cluster_path = root / "cluster.yaml"
        rift_yaml_mod.write_yaml(cluster_path, cluster_mod.example_emulated_cluster())
        controller = cluster_mod.RiftClusterController(root=root)

        discovery = controller.discover(cluster_config=cluster_path)
        assert discovery["summary"]["node_count"] == 3
        assert discovery["summary"]["ready_nodes"] == 3

        checked = controller.check(cluster_config=cluster_path)
        assert checked["valid"] is True
        assert checked["placement_summary"]["scheduled_instances"] == 3

        blocked = controller.apply(cluster_config=cluster_path)
        assert blocked["applied"] is False
        assert blocked["required_permission"] == "allow_deploy"

        deployed = controller.apply(cluster_config=cluster_path, allow_deploy=True)
        assert deployed["applied"] is True
        assert len(deployed["deployed_instances"]) == 3
        assert (root / ".rift" / "cluster" / "state.db").is_file()
        status = controller.status()
        assert status["summary"]["phases"] == {"running": 3}

        benchmark = controller.benchmark()
        assert benchmark["measurement_mode"] == "deterministic_emulation"
        assert benchmark["summary"]["aggregate_tokens_per_second"] > 0.0
        assert benchmark["summary"]["all_usable"] is True

        tuned = controller.tune(service_name="coder")
        assert len(tuned["results"]) == 1
        assert tuned["results"][0]["improvement_percent"] > 0.0

        laptop_instance = next(
            item
            for item in controller.status()["instances"]
            if item["node"] == "laptop-4060"
        )
        failed = controller.inject_failure(node_name="laptop-4060", kind="node_down")
        assert laptop_instance["instance_id"] in failed["affected_instances"]
        observed = controller.monitor(allow_recovery=False)
        assert observed["healthy"] is False
        recovered = controller.monitor(allow_recovery=True)
        recovered_item = next(
            item for item in recovered["results"] if item["instance_id"] == laptop_instance["instance_id"]
        )
        assert recovered_item["action"] == "rescheduled"
        assert recovered_item["healthy"] is True

        coder_instance = next(
            item for item in controller.status()["instances"] if item["service"] == "coder"
        )
        controller.inject_failure(
            instance_id=coder_instance["instance_id"],
            kind="process_crash",
        )
        process_recovery = controller.monitor(allow_recovery=True)
        coder_result = next(
            item
            for item in process_recovery["results"]
            if item["instance_id"] == coder_instance["instance_id"]
        )
        assert coder_result["action"] == "restarted"
        assert coder_result["healthy"] is True

        final_status = controller.status()
        assert final_status["summary"]["incident_count"] == 2
        assert final_status["summary"]["phases"] == {"running": 3}

        destroyed = controller.destroy()
        assert len(destroyed["stopped_instances"]) == 3
        assert controller.status()["summary"]["phases"] == {"stopped": 3}


def test_cluster_recovery_on_fresh_state_is_actionable():
    with tempfile.TemporaryDirectory() as tmp:
        controller = cluster_mod.RiftClusterController(root=Path(tmp))

        result = controller.monitor(allow_recovery=True)

        assert result["available"] is False
        assert result["healthy"] is False
        assert result["results"] == []
        assert "cluster apply" in result["message"]


def test_fifty_node_heterogeneous_placement_partition_rollout_and_recovery():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        nodes = []
        for index in range(20):
            nodes.append(
                {
                    "name": f"consumer-{index:02d}",
                    "hardware": {"vram_gb": 8, "ram_gb": 24, "disk_free_gb": 100, "cpu_threads": 16},
                    "backends": ["llama.cpp"],
                    "labels": {"zone": f"consumer-{index % 4}", "class": "consumer"},
                }
            )
        for index in range(20):
            nodes.append(
                {
                    "name": f"cuda-{index:02d}",
                    "hardware": {"vram_gb": 24, "ram_gb": 64, "disk_free_gb": 300, "cpu_threads": 32},
                    "backends": ["llama.cpp", "vllm", "sglang"],
                    "labels": {"zone": f"gpu-{index % 4}", "class": "cuda"},
                }
            )
        for index in range(10):
            nodes.append(
                {
                    "name": f"cpu-{index:02d}",
                    "hardware": {"vram_gb": 0, "ram_gb": 64, "disk_free_gb": 200, "cpu_threads": 32},
                    "backends": ["llama.cpp"],
                    "labels": {"zone": f"cpu-{index % 2}", "class": "cpu"},
                }
            )
        config = {
            "version": 1,
            "mode": "emulated",
            "nodes": nodes,
            "services": {
                "chat": {
                    "replicas": 20,
                    "task": "chat",
                    "model": {
                        "id": "org/chat-7b-gguf",
                        "format": "gguf",
                        "quantization": "q4_k_m",
                        "parameters_b": 7,
                        "estimated_bytes": int(4.5 * 1024**3),
                    },
                    "serving": {"context_length": 4096, "concurrency": 1},
                    "policy": {"backend": "llama.cpp"},
                },
                "coder": {
                    "replicas": 10,
                    "task": "coding",
                    "model": {
                        "id": "org/coder-14b-awq",
                        "format": "awq",
                        "quantization": "awq",
                        "parameters_b": 14,
                        "estimated_bytes": int(8.5 * 1024**3),
                    },
                    "serving": {"context_length": 8192, "concurrency": 2},
                    "policy": {"backend": "auto"},
                    "placement": {"required_labels": {"class": "cuda"}},
                },
            },
        }
        path = root / "cluster.yaml"
        rift_yaml_mod.write_yaml(path, config)
        controller = cluster_mod.RiftClusterController(root=root)
        discovery = controller.discover(cluster_config=path)
        assert discovery["summary"]["node_count"] == 50
        plan = controller.plan(cluster_config=path)
        assert not plan["unscheduled"], plan["unscheduled"]
        assert plan["summary"]["scheduled_instances"] == 30
        assert len({item["node"] for item in plan["placements"] if item["service"] == "chat"}) == 20
        deployed = controller.apply(cluster_config=path, allow_deploy=True)
        assert deployed["applied"]

        victim = next(
            item for item in controller.status()["instances"] if item["service"] == "chat"
        )
        partition = controller.inject_failure(node_name=victim["node"], kind="network_partition")
        assert victim["instance_id"] in partition["affected_instances"]
        recovery = controller.monitor(allow_recovery=True)
        recovered = next(item for item in recovery["results"] if item["instance_id"] == victim["instance_id"])
        assert recovered["healthy"] and recovered["action"] == "rescheduled"

        rollout = controller.rollout_plan(
            service_name="chat",
            desired={"model": "org/chat-8b-gguf", "quantization": "q5_k_m"},
            strategy="canary",
        )
        assert rollout["strategy"] == "canary"
        promote = controller.rollout_gate(
            readiness={"ready": True},
            baseline={"median_tokens_per_second": 10.0, "p95_elapsed_seconds": 2.0},
            candidate={"median_tokens_per_second": 10.5, "p95_elapsed_seconds": 1.9},
        )
        assert promote["promote"]
        benchmark = controller.benchmark()
        assert benchmark["summary"]["instance_count"] == 30
        assert benchmark["measurement_mode"] == "deterministic_emulation"


def main():
    test_emulated_cluster_lifecycle_tuning_and_disaster_recovery()
    test_fifty_node_heterogeneous_placement_partition_rollout_and_recovery()
    print("RIFT cluster control tests passed")


if __name__ == "__main__":
    main()
