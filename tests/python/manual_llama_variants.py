"""Isolated llama.cpp variant sweep used to identify a real speed path."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from rift.providers.llama_cpp import LlamaCppProvider


MODEL = ROOT / "models" / "Qwen--Qwen2.5-3B-Instruct-GGUF" / "qwen2.5-3b-instruct-q4_k_m.gguf"
EXE = ROOT / ".rift-runtime" / "backends" / "llama.cpp" / "llama-server.exe"
PORT = 11845


def request(base_url: str, prompt: str, max_tokens: int = 128) -> dict:
    body = json.dumps({
        "model": "rift-managed",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "stream": False,
        "seed": 17,
        "temperature": 0.0,
    }).encode("utf-8")
    started = time.perf_counter()
    with urlopen(Request(
        f"{base_url}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
    ), timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8"))
    payload["wall_seconds"] = time.perf_counter() - started
    return payload


def wait_ready(base_url: str) -> None:
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with urlopen(f"{base_url}/health", timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("variant server did not become healthy")


def main() -> None:
    provider = LlamaCppProvider()
    hardware = {"total_vram_bytes": 8 * 1024**3}
    variants = [
        ("baseline", {"batch": 128, "ubatch": 128, "threads": 16, "threads_batch": 16, "flash_attn": "auto"}),
        ("large-ubatch", {"batch": 512, "ubatch": 512, "threads": 16, "threads_batch": 16, "flash_attn": "auto"}),
        ("large-ubatch-flash", {"batch": 512, "ubatch": 512, "threads": 16, "threads_batch": 16, "flash_attn": "on"}),
        ("q8-large-ubatch", {"batch": 512, "ubatch": 512, "threads": 16, "threads_batch": 16, "cache_type_k": "q8_0", "cache_type_v": "q8_0"}),
        ("q4-large-ubatch", {"batch": 512, "ubatch": 512, "threads": 16, "threads_batch": 16, "cache_type_k": "q4_0", "cache_type_v": "q4_0"}),
        ("q4-nohost", {"batch": 512, "ubatch": 512, "threads": 16, "threads_batch": 16, "cache_type_k": "q4_0", "cache_type_v": "q4_0", "no_host": True}),
        ("q4-kv-unified", {"batch": 512, "ubatch": 512, "threads": 16, "threads_batch": 16, "cache_type_k": "q4_0", "cache_type_v": "q4_0", "kv_unified": True}),
        ("explicit-cuda", {"batch": 512, "ubatch": 512, "threads": 16, "threads_batch": 16, "device": "CUDA0", "split_mode": "none", "main_gpu": 0}),
        ("q4-explicit-cuda", {"batch": 512, "ubatch": 512, "threads": 16, "threads_batch": 16, "cache_type_k": "q4_0", "cache_type_v": "q4_0", "device": "CUDA0", "split_mode": "none", "main_gpu": 0}),
        ("repack-op-offload", {"batch": 512, "ubatch": 512, "threads": 16, "threads_batch": 16, "repack": True, "op_offload": True}),
    ]
    results = []
    for name, tuning in variants:
        plan = provider.plan_launch(
            model_path=str(MODEL), host="127.0.0.1", port=PORT,
            context_length=8192, concurrency=1, hardware=hardware,
            tuning={**tuning, "search_root": str(EXE.parent)},
        )
        process = subprocess.Popen(plan["command"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            wait_ready(plan["api_base"])
            for _ in range(2):
                request(plan["api_base"], "Explain one benefit of local inference in one paragraph.", 128)
            samples = [request(plan["api_base"], "Explain one benefit of local inference in one paragraph.", 128) for _ in range(3)]
            speeds = [float((item.get("timings") or {}).get("predicted_per_second") or 0.0) for item in samples]
            results.append({"name": name, "tuning": tuning, "speeds": speeds, "median": sorted(speeds)[len(speeds) // 2]})
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
