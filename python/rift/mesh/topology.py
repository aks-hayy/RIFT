"""Bounded link measurement orchestration for mesh topology planning."""

from __future__ import annotations

from typing import Callable, Iterable

from .contracts import LinkMeasurement


class TopologyMeasurer:
    def __init__(
        self,
        *,
        probe: Callable[[str, str], LinkMeasurement],
        clock: Callable[[], float],
    ) -> None:
        self.probe = probe
        self.clock = clock

    def measure(
        self,
        node_ids: Iterable[str],
        *,
        mode: str = "sparse",
        candidates_per_node: int = 3,
        allow_intensive: bool = False,
    ) -> dict[str, object]:
        nodes = sorted(set(node_ids))
        if len(nodes) < 2:
            return {"mode": mode, "links": [], "evidence": "NO_MEASUREMENTS"}
        if mode == "intensive" and not allow_intensive:
            raise PermissionError("intensive all-pairs measurement requires explicit consent")
        if mode not in {"sparse", "intensive"}:
            raise ValueError(f"unsupported measurement mode: {mode}")
        if candidates_per_node <= 0:
            raise ValueError("candidates_per_node must be positive")
        pairs: list[tuple[str, str]] = []
        if mode == "intensive":
            pairs = [(source, target) for source in nodes for target in nodes if source != target]
        else:
            for index, source in enumerate(nodes):
                for offset in range(1, min(candidates_per_node, len(nodes) - 1) + 1):
                    pairs.append((source, nodes[(index + offset) % len(nodes)]))
        links = []
        evidence = set()
        errors = []
        for source, target in pairs:
            try:
                measurement = self.probe(source, target)
                links.append(dict(measurement.__dict__))
                evidence.add(measurement.evidence)
            except Exception as exc:
                errors.append({"source": source, "target": target, "error": str(exc)})
        return {
            "mode": mode,
            "measured_at": float(self.clock()),
            "links": links,
            "errors": errors,
            "evidence": next(iter(evidence)) if len(evidence) == 1 else "MIXED",
            "cost": {
                "directional_probe_count": len(pairs),
                "all_pairs": mode == "intensive",
            },
        }


__all__ = ["TopologyMeasurer"]
