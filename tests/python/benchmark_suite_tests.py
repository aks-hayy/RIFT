"""Contract tests for the versioned RIFT benchmark suite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rift.benchmark_suite import (
    BenchmarkSpec,
    BenchmarkSuiteRunner,
    ResearchProtocol,
    bootstrap_confidence_interval,
    compile_benchmark_plan,
    factorial_effects,
    paired_effect,
    profile_catalog,
)
from rift.orchestrator import _research_protocol_from_mapping
from rift.server import RiftServerRuntime


def test_catalog_contains_substantial_versioned_profiles() -> None:
    catalog = profile_catalog()
    ids = [item["id"] for item in catalog]
    assert ids == ["smoke", "interactive", "throughput", "context", "reliability", "quality", "research"]
    assert all(item["version"] for item in catalog)
    assert all(item["planned_workload"] for item in catalog)
    assert all(item["requirements"] for item in catalog)


def test_compile_defaults_to_smoke_and_expands_real_cases() -> None:
    plan = compile_benchmark_plan(BenchmarkSpec(target="chat"))
    assert plan["profiles"] == ["smoke"]
    assert len(plan["profile_plans"]["smoke"]["cases"]) >= 16
    assert plan["execution_order"] == ["smoke"]
    assert plan["plan_hash"]
    assert plan["limits"]["max_concurrency"] == 8


def test_compile_multiple_profiles_is_sequential_and_research_is_not_hollow() -> None:
    spec = BenchmarkSpec(
        target="chat",
        profiles=("smoke", "throughput", "quality", "research"),
        research=ResearchProtocol(recipe="repeatability", items=4, blocks=2, repetitions=2),
    )
    plan = compile_benchmark_plan(spec)
    assert plan["execution_order"] == ["smoke", "research", "quality", "throughput"]
    assert plan["profile_plans"]["throughput"]["cells"]
    research = plan["profile_plans"]["research"]
    assert research["independent_items"] == 4
    assert research["planned_requests"] == 16
    assert research["protocol"]["pilot_excluded"] is True


def test_runner_persists_all_observations_and_runs_profiles_sequentially(tmp_path: Path) -> None:
    calls: list[str] = []

    def benchmark(*, base_url: str, prompt: str, max_tokens: int):
        calls.append(prompt)
        return {
            "available": True,
            "elapsed_seconds": 0.25,
            "generated_tokens": 8,
            "tokens_per_second_estimate": 32.0,
        }

    spec = BenchmarkSpec(target="chat", profiles=("smoke", "quality"), quality_items=2)
    result = BenchmarkSuiteRunner(benchmark, artifact_root=tmp_path).run(spec, base_url="http://service")
    assert result["status"] == "completed"
    assert result["profile_results"]["smoke"]["status"] == "completed"
    assert result["profile_results"]["quality"]["status"] == "completed"
    assert result["profile_results"]["smoke"]["observations"]
    assert len(calls) >= 18
    assert Path(result["artifact_manifest"]).is_file()
    assert Path(result["plan_file"]).is_file()
    manifest = json.loads(Path(result["artifact_manifest"]).read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "rift.benchmarks/v1"
    assert manifest["observation_file"]
    assert manifest["plan_file"] == result["plan_file"]


def test_runner_records_unavailable_as_null_measurements() -> None:
    def benchmark(**_kwargs):
        return {"available": False, "error": "timeout"}

    result = BenchmarkSuiteRunner(benchmark).run(
        BenchmarkSpec(target="chat", profiles=("smoke",)), base_url="http://service"
    )
    sample = result["profile_results"]["smoke"]["observations"][0]
    assert sample["available"] is False
    assert sample["elapsed_seconds"] is None
    assert sample["generated_tokens"] is None
    assert sample["tokens_per_second"] is None
    assert sample["first_token_seconds"] is None
    assert result["profile_results"]["smoke"]["status"] == "failed"


def test_research_statistics_are_seeded_and_clustered() -> None:
    pairs = [(1.0, 1.5), (2.0, 2.0), (3.0, 4.0)]
    effect = paired_effect(pairs)
    assert effect["estimate"] == pytest.approx(0.5)
    first = bootstrap_confidence_interval([1.0, 2.0, 3.0, 4.0], seed=7, draws=500)
    second = bootstrap_confidence_interval([1.0, 2.0, 3.0, 4.0], seed=7, draws=500)
    assert first == second
    factorial = factorial_effects(
        [
            {"a": "plain", "b": "zero", "value": 0.2},
            {"a": "plain", "b": "three", "value": 0.4},
            {"a": "structured", "b": "zero", "value": 0.6},
            {"a": "structured", "b": "three", "value": 0.8},
        ],
        factors=("a", "b"),
    )
    assert factorial["interaction"] == pytest.approx(0.0)


def test_research_protocol_validation_rejects_ambiguous_confirmatory_studies() -> None:
    with pytest.raises(ValueError, match="primary outcome"):
        compile_benchmark_plan(
            BenchmarkSpec(
                target="chat",
                profiles=("research",),
                research=ResearchProtocol(recipe="paired", items=4, primary_outcome=""),
            )
        )


def test_guided_research_profiles_have_meaningful_default_conditions() -> None:
    context = compile_benchmark_plan(
        BenchmarkSpec(
            target="chat",
            profiles=("research",),
            research=ResearchProtocol(recipe="context_position", items=2, blocks=1, repetitions=1),
        )
    )
    protocol = context["profile_plans"]["research"]["protocol"]
    assert protocol["conditions"] == ["10", "50", "90"]
    assert context["profile_plans"]["research"]["planned_requests"] == 6

    prefix = compile_benchmark_plan(
        BenchmarkSpec(
            target="chat",
            profiles=("research",),
            research=ResearchProtocol(recipe="prefix_reuse", items=2, blocks=1, repetitions=1),
        )
    )
    assert prefix["profile_plans"]["research"]["protocol"]["conditions"] == ["cold", "warm"]


def test_custom_research_cases_are_declarative_and_repeated() -> None:
    plan = compile_benchmark_plan(
        BenchmarkSpec(
            target="chat",
            profiles=("research",),
            research=ResearchProtocol(
                recipe="custom",
                items=2,
                blocks=2,
                repetitions=2,
                custom_cases=({"id": "one", "prompt": "Reply OK", "expected": "OK"},),
            ),
        )
    )
    cases = plan["profile_plans"]["research"]["cases"]
    assert len(cases) == 4
    assert {case["scorer"] for case in cases} == {"exact"}


def test_cli_paired_research_supplies_two_default_conditions() -> None:
    protocol = _research_protocol_from_mapping({"recipe": "paired"})
    assert protocol.conditions == ("baseline", "candidate")


def test_server_exposes_profile_catalog_and_plan_endpoint(tmp_path: Path) -> None:
    class FakeOrchestrator:
        rift_dir = tmp_path

        def benchmark_profiles_catalog(self):
            return {"profiles": profile_catalog()}

        def benchmark_targets(self):
            return {"targets": [{"id": "chat", "benchmarkable": True}]}

        def benchmark_plan(self, **kwargs):
            return compile_benchmark_plan(BenchmarkSpec(target=kwargs["service_name"], profiles=tuple(kwargs["profiles"])))

    runtime = RiftServerRuntime(orchestrator_factory=FakeOrchestrator)
    profiles = runtime.control_get("/api/rift/v2/benchmark-profiles", {})
    assert len(profiles["profiles"]) == 7
    plan = runtime.control_post(
        "/api/rift/v2/benchmark-plans",
        {"service": "chat", "profiles": ["smoke", "quality"]},
    )
    assert plan["execution_order"] == ["smoke", "quality"]
