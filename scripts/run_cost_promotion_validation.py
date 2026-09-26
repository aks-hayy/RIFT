"""Focused real-device Cost profile promotion validation."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))


def main() -> int:
    from rift.orchestrator import ApplyPermissions, RiftOrchestrator
    from rift.rift_yaml import read_yaml, write_yaml

    model = ROOT / "models" / "Qwen--Qwen2.5-3B-Instruct-GGUF" / "Qwen2.5-3B-Instruct-Q4_K_M.gguf"
    server = ROOT / ".rift-runtime" / "backends" / "llama.cpp" / "llama-server.exe"
    if not model.is_file() or not server.is_file():
        raise SystemExit("required local model or llama-server is missing")
    os.environ["LLAMA_CPP_SERVER"] = str(server.resolve())
    output = ROOT / ".rift-runtime" / "reports" / "real-tuning-validation-final" / "raw" / "3b-llama-cpp-cost-promoted.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix="rift-promote-3b-cost-"))
    service_name = "promote3bcost"
    orch = None
    started = time.time()
    try:
        conf = read_yaml(ROOT / "rift.yaml")
        service = dict(conf["services"]["chat"])
        for key in ("model", "serving", "policy", "gateway", "monitoring", "recovery"):
            service[key] = dict(service[key])
        model_path = str(model.resolve())
        service["model"].update({"source": "local", "id": model_path, "selected_file": model_path, "local_path": model_path, "format": "gguf", "artifact": {}, "quantization": "Q4_K_M"})
        service["serving"].update({"port": 19431, "context_length": 4096, "concurrency": 1, "tuning": {"gpu_layers": 999, "batch": 128, "ubatch": 128, "threads": 1, "threads_batch": 1, "parallel": 1, "flash_attn": "auto", "ngram_speculation": False}})
        service["gateway"]["enabled"] = False
        service["policy"].update({"backend": "llama.cpp", "allow_download": False, "allow_install": False})
        service["monitoring"]["enabled"] = False
        conf["services"] = {service_name: service}
        config = temp_root / "rift.yaml"
        write_yaml(config, conf)
        orch = RiftOrchestrator(root=temp_root, runtime_root=temp_root / ".rift-runtime")
        deployed = orch.apply(config_path=config, permissions=ApplyPermissions(allow_launch=True))
        if not deployed.get("applied"):
            raise RuntimeError(f"baseline deployment failed: {deployed.get('reason')}")
        observation = {}
        for _ in range(180):
            observation = orch.status().get("services", {}).get(service_name, {}).get("observation", {})
            if observation.get("healthy"):
                break
            time.sleep(1)
        if not observation.get("healthy"):
            raise RuntimeError(f"baseline did not become healthy: {observation}")
        report = orch.profiled_tune_service(
            service_name=service_name,
            profile="cost",
            usage="interactive",
            allow_restart=True,
            prompt="Write a detailed technical explanation of local inference energy efficiency in at least 180 words.",
            candidate_limit=4,
            warmup_runs=1,
            repeats=20,
            max_tokens=256,
            target_tokens_per_second=1.0,
            budget_seconds=900,
            accuracy_tolerance=0.25,
            accuracy_case_tolerance=0.5,
        )
        report_path = Path(str(report.get("report_path") or ""))
        if report_path.is_file():
            shutil.copy2(report_path, output)
        print({"outcome": report.get("outcome"), "applied": report.get("applied"), "decision": report.get("decision"), "run_id": report.get("run_id"), "report": str(output), "final_improvement_interval": report.get("final_improvement_interval"), "elapsed_seconds": time.time() - started})
        return 0 if report.get("outcome") == "improved" and report.get("applied") else 2
    finally:
        if orch is not None:
            try:
                print({"teardown": orch.destroy(service_name=service_name)})
            except Exception as exc:
                print({"teardown_error": str(exc)})
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
