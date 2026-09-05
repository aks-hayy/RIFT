"""Deterministic virtual laboratory for RIFT mesh behavior."""

from __future__ import annotations

import random
from typing import Any

from .contracts import LinkMeasurement, MeshGraph, RuntimeOffer, TrustedNode


JsonDict = dict[str, Any]


class MeshLab:
    def __init__(self, *, seed: int = 1) -> None:
        self.seed = int(seed)
        self.random = random.Random(self.seed)
        self.nodes: list[str] = []

    def add_standard_fleet(self, count: int) -> None:
        if count <= 0:
            raise ValueError("fleet size must be positive")
        self.nodes = [f"node-{index:04d}" for index in range(count)]

    def measure(
        self,
        *,
        mode: str = "sparse",
        candidates_per_client: int = 3,
        allow_intensive: bool = False,
    ) -> JsonDict:
        count = len(self.nodes)
        if not count:
            raise ValueError("the virtual fleet is empty")
        if mode == "intensive":
            if not allow_intensive:
                raise PermissionError("intensive all-pairs measurement requires explicit authorization")
            edges = count * (count - 1)
            warning = f"intensive mode schedules {edges} directional probes"
        elif mode == "sparse":
            if candidates_per_client <= 0:
                raise ValueError("candidates_per_client must be positive")
            edges = min(count * (count - 1), count * (candidates_per_client + 1))
            warning = ""
        else:
            raise ValueError(f"unsupported measurement mode: {mode}")
        return {
            "evidence": "EMULATED",
            "seed": self.seed,
            "mode": mode,
            "node_count": count,
            "directional_edge_count": edges,
            "cost_warning": warning,
        }

    def example_elastic_graph(self) -> MeshGraph:
        chat_small = RuntimeOffer("phone-tiny", "chat", "tiny-1b", "llama.cpp", 1024, 42, 900, 4)
        chat_laptop = RuntimeOffer("laptop-chat", "chat", "qwen-7b", "llama.cpp", 8192, 76, 210, 22)
        chat_gpu = RuntimeOffer("gpu-chat", "chat", "qwen-14b", "vllm", 16384, 84, 95, 55)
        chat_cpu = RuntimeOffer("cpu-chat", "chat", "qwen-7b", "llama.cpp", 8192, 72, 520, 8)
        nodes = {
            "phone": TrustedNode("phone", "phone", offers=[chat_small], labels={"class": "android"}),
            "laptop": TrustedNode("laptop", "laptop", offers=[chat_laptop], labels={"class": "consumer"}),
            "gpu-server": TrustedNode("gpu-server", "gpu-server", offers=[chat_gpu], labels={"class": "cuda"}),
            "cpu-fallback": TrustedNode("cpu-fallback", "cpu-fallback", offers=[chat_cpu], labels={"class": "cpu"}),
        }
        links: dict[tuple[str, str], LinkMeasurement] = {}
        for source in nodes:
            for target in nodes:
                if source == target:
                    continue
                base = {
                    ("phone", "gpu-server"): 8.0,
                    ("phone", "laptop"): 12.0,
                    ("phone", "cpu-fallback"): 18.0,
                }.get((source, target), 10.0)
                links[(source, target)] = LinkMeasurement(
                    source,
                    target,
                    base,
                    base * 1.4,
                    base * 0.1,
                    0.0,
                    800.0,
                    800.0,
                    1.0,
                    "EMULATED",
                )
        return MeshGraph(nodes=nodes, links=links, evidence="EMULATED")

    @staticmethod
    def set_node_pressure(
        graph: MeshGraph,
        node_id: str,
        *,
        queue_depth: int,
        healthy: bool,
    ) -> None:
        node = graph.nodes[node_id]
        node.queue_depth = int(queue_depth)
        node.healthy = bool(healthy)


__all__ = ["MeshLab"]
