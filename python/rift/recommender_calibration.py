"""Reproducible hardware matrices for recommendation calibration.

The matrix deliberately labels its reference as an external-evidence baseline.
It is a comparison harness, not a claim that one leaderboard is universal
ground truth for model intelligence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


_WEAKER = (
    ("mobile_android", "Adreno 750 shared GPU", 1, 8, 32, "android", False),
    ("gtx1050", "GTX 1050", 2, 8, 64, "windows", True),
    ("gtx1650", "GTX 1650", 4, 8, 80, "windows", True),
    ("rx6400", "Radeon RX 6400", 4, 16, 120, "windows", False),
    ("arc_a380", "Intel Arc A380", 6, 16, 160, "windows", False),
)

_STRONGER = (
    ("rtx3060", "RTX 3060", 12, 32, 240, "windows", True),
    ("rtx4070", "RTX 4070", 12, 32, 400, "linux", True),
    ("rtx4080", "RTX 4080", 16, 64, 600, "linux", True),
    ("rtx4090", "RTX 4090", 24, 64, 800, "linux", True),
    ("rtx5090", "RTX 5090", 32, 128, 1200, "linux", True),
)


def _simulated_spec(
    scenario_id: str,
    device_name: str,
    vram_gb: int,
    ram_gb: int,
    disk_gb: int,
    os_name: str,
    cuda: bool,
    variant: int,
) -> str:
    # Vary free capacity so the matrix covers idle, moderately occupied, and
    # heavily occupied machines instead of testing only total capacities.
    free_vram = max(1, vram_gb - (variant % 3))
    free_ram = max(2, ram_gb - (variant * 2))
    return (
        f"gpu={device_name},vram_gb={vram_gb},ram_gb={ram_gb},"
        f"disk_free_gb={disk_gb - variant * 4},os={os_name},cuda={str(cuda).lower()},"
        f"free_vram_gb={free_vram},free_ram_gb={free_ram},"
        f"cpu_cores={max(4, ram_gb // 2)},scenario={scenario_id}-{variant}"
    )


def build_calibration_scenarios(
    *,
    real_profile: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return one real reference plus 50 controlled simulated scenarios."""

    scenarios: list[dict[str, Any]] = [
        {
            "scenario_id": "real_workstation",
            "profile_kind": "real",
            "relative_tier": "reference",
            "reference_label": "external_evidence_baseline",
            "hardware_profile": dict(real_profile or {}),
            "simulation_spec": None,
        }
    ]
    for tier, devices in (("weaker", _WEAKER), ("stronger", _STRONGER)):
        for device_id, name, vram, ram, disk, os_name, cuda in devices:
            for variant in range(1, 6):
                scenario_id = f"{device_id}-{variant}"
                scenarios.append(
                    {
                        "scenario_id": scenario_id,
                        "profile_kind": "simulated",
                        "relative_tier": tier,
                        "reference_label": "external_evidence_baseline",
                        "hardware_profile": {
                            "device_name": name,
                            "total_vram_gb": vram,
                            "total_host_ram_gb": ram,
                            "disk_free_gb": disk - variant * 4,
                            "os": os_name,
                            "cuda_available": cuda,
                        },
                        "simulation_spec": _simulated_spec(
                            scenario_id,
                            name,
                            vram,
                            ram,
                            disk,
                            os_name,
                            cuda,
                            variant,
                        ),
                    }
                )
    return scenarios


def run_calibration_matrix(
    engine: Any,
    scenarios: list[dict[str, Any]],
    *,
    task: str = "chat",
    endpoint: str = "https://huggingface.co",
    cache_dir: str | Path | None = None,
    candidate_limit: int = 50,
    enrichment_cap: int = 5,
    artifact_enrichment_cap: int = 2,
    max_download_gb: float = 12.0,
) -> dict[str, Any]:
    """Run the same bounded live-Hub search across a hardware matrix.

    The returned rows preserve whether each result was real or simulated and
    expose the benchmark-site catalog supplied by RIFT. They intentionally do
    not call the local verification path or download models.
    """

    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        try:
            result = engine.recommend_models(
                task=task,
                top=3,
                candidate_limit=candidate_limit,
                enrichment_cap=enrichment_cap,
                artifact_enrichment_cap=artifact_enrichment_cap,
                max_download_gb=max_download_gb,
                endpoint=endpoint,
                cache_dir=str(cache_dir) if cache_dir else None,
                persist_run=False,
                simulated_hardware=scenario.get("simulation_spec"),
            )
            recommendations = result.get("recommendations") or []
            winner = next(
                (
                    item
                    for item in recommendations
                    if item.get("support_level") != "UNSUPPORTED"
                ),
                None,
            )
            rows.append(
                {
                    "scenario_id": scenario["scenario_id"],
                    "profile_kind": scenario["profile_kind"],
                    "relative_tier": scenario["relative_tier"],
                    "reference_label": scenario["reference_label"],
                    "winner": _compact_recommendation(winner),
                    "top_recommendations": [_compact_recommendation(item) for item in recommendations],
                    "query_arm_count": result.get("discovery", {}).get("query_arm_count", 0),
                    "candidate_counts": result.get("candidate_counts", {}),
                    "benchmark_sources": [
                        item.get("source_id") for item in result.get("benchmark_sources", [])
                    ],
                    "status": "ok" if winner else "no_feasible_candidate",
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "scenario_id": scenario["scenario_id"],
                    "profile_kind": scenario["profile_kind"],
                    "relative_tier": scenario["relative_tier"],
                    "reference_label": scenario["reference_label"],
                    "status": "error",
                    "error": str(exc),
                }
            )
    return {
        "schema_version": 1,
        "method": "external_evidence_baseline_vs_rift_bounded_live_hub_search",
        "task": task,
        "side_effects": {"download": False, "install": False, "launch": False, "local_verify": False},
        "reference_interpretation": (
            "External benchmark sites are evidence references, not universal ground truth. "
            "Agreement must be evaluated per task and capability, not as one accuracy score."
        ),
        "scenario_count": len(scenarios),
        "summary": {
            "real_profiles": sum(item.get("profile_kind") == "real" for item in rows),
            "simulated_profiles": sum(item.get("profile_kind") == "simulated" for item in rows),
            "successful_searches": sum(item.get("status") == "ok" for item in rows),
            "no_feasible_candidate": sum(item.get("status") == "no_feasible_candidate" for item in rows),
            "errors": sum(item.get("status") == "error" for item in rows),
        },
        "rows": rows,
    }


def _compact_recommendation(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    scores = item.get("scores") or {}
    return {
        "repo_id": item.get("repo_id"),
        "parameters_b": item.get("parameters_b"),
        "format": item.get("format"),
        "quantization": item.get("quantization"),
        "selected_file": item.get("selected_file"),
        "backend": item.get("backend"),
        "support_level": item.get("support_level"),
        "score": item.get("final_score"),
        "quality_proxy": scores.get("quality_proxy"),
        "hardware_fit": scores.get("hardware_fit"),
        "evidence_coverage": item.get("evidence_coverage"),
    }


__all__ = ["build_calibration_scenarios", "run_calibration_matrix"]
