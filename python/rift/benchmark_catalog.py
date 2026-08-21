"""Official benchmark sources that RIFT can use as evidence provenance.

RIFT does not scrape or redistribute leaderboard tables by default.  The
catalog gives the recommender a stable, human-readable map of what each source
measures and where an operator can obtain a permitted snapshot.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class BenchmarkSite:
    source_id: str
    label: str
    tasks: tuple[str, ...]
    metrics: tuple[str, ...]
    official_url: str
    methodology_url: str
    evidence_kind: str
    caveat: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["tasks"] = list(self.tasks)
        payload["metrics"] = list(self.metrics)
        return payload


_SITES: tuple[BenchmarkSite, ...] = (
    BenchmarkSite(
        source_id="arena",
        label="LMSYS Chatbot Arena",
        tasks=("chat", "general"),
        metrics=("preference_score", "elo"),
        official_url="https://lmarena.ai/leaderboard",
        methodology_url="https://www.lmsys.org/blog/2024-03-01-policy/",
        evidence_kind="human_preference",
        caveat="Human preference is not a speed, coding, or local-deployment measurement.",
    ),
    BenchmarkSite(
        source_id="evalplus",
        label="EvalPlus",
        tasks=("coding",),
        metrics=("pass_at_1", "humaneval_plus", "mbpp_plus"),
        official_url="https://evalplus.github.io/leaderboard.html",
        methodology_url="https://github.com/evalplus/evalplus",
        evidence_kind="executable_code_correctness",
        caveat="Code correctness scores do not measure conversational quality or serving speed.",
    ),
    BenchmarkSite(
        source_id="livebench",
        label="LiveBench",
        tasks=("chat", "reasoning", "coding"),
        metrics=("overall_score", "category_score"),
        official_url="https://livebench.ai/",
        methodology_url="https://github.com/LiveBench/LiveBench",
        evidence_kind="fresh_task_evaluation",
        caveat="Scores are benchmark-family evidence and require model/revision matching.",
    ),
    BenchmarkSite(
        source_id="bigcodebench",
        label="BigCodeBench",
        tasks=("coding", "agent"),
        metrics=("pass_at_1", "pass_at_5"),
        official_url="https://bigcode-bench.github.io/",
        methodology_url="https://github.com/bigcode-project/bigcodebench",
        evidence_kind="real_world_code_generation",
        caveat="Results depend on prompt split, sampling, and execution backend.",
    ),
)


def benchmark_site_catalog() -> list[dict[str, Any]]:
    """Return the public benchmark registry without fetching remote data."""

    return [site.to_dict() for site in _SITES]


def benchmark_site_ids() -> tuple[str, ...]:
    return tuple(site.source_id for site in _SITES)


__all__ = ["BenchmarkSite", "benchmark_site_catalog", "benchmark_site_ids"]
