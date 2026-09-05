"""Versioned, workload-oriented benchmarking for running RIFT services.

The legacy :mod:`rift.benchmarking` module is intentionally left intact because
deployment rollout and tuning still consume its small regression contract.  This
module is the public benchmark-suite layer: it compiles named profiles into a
resolved plan, runs them in a deterministic order, and keeps raw observations
separate from profile-specific analysis.
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
import random
import statistics
import time
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .benchmarking import summarize_samples
from .runtime_paths import RiftPaths

JsonDict = dict[str, Any]
BenchmarkCallable = Callable[..., Mapping[str, Any]]

PROFILE_ORDER = ("smoke", "interactive", "throughput", "context", "reliability", "quality", "research")
EXECUTION_ORDER = ("smoke", "research", "quality", "interactive", "context", "throughput", "reliability")


_PROFILE_CATALOG: tuple[JsonDict, ...] = (
    {
        "id": "smoke",
        "name": "Smoke",
        "version": "1.0",
        "purpose": "Protocol integrity and basic behavior checks.",
        "planned_workload": "8 checks × 2 repetitions, plus a two-request concurrency probe",
        "requirements": ("chat completions",),
        "default_wall_time_seconds": 180,
    },
    {
        "id": "interactive",
        "name": "Interactive",
        "version": "1.0",
        "purpose": "User-perceived responsiveness across short, reference, and multi-turn sessions.",
        "planned_workload": "3 session types × concurrency 1 and 4 × 20 sessions",
        "requirements": ("streaming or complete responses",),
        "default_wall_time_seconds": 1200,
    },
    {
        "id": "throughput",
        "name": "Throughput",
        "version": "1.0",
        "purpose": "Sustained useful capacity, goodput, and latency under load.",
        "planned_workload": "Concurrency 1/2/4/8 plus three seeded arrival-rate windows",
        "requirements": ("chat completions", "bounded concurrency"),
        "default_wall_time_seconds": 1800,
    },
    {
        "id": "context",
        "name": "Context",
        "version": "1.0",
        "purpose": "Length and information-position effects on grounded answers.",
        "planned_workload": "5 lengths × 3 evidence positions × 8 matched documents × 2 tasks",
        "requirements": ("declared context limit or conservative fallback",),
        "default_wall_time_seconds": 1800,
    },
    {
        "id": "reliability",
        "name": "Reliability",
        "version": "1.0",
        "purpose": "Behavior during sustained mixed load, bursts, and recovery.",
        "planned_workload": "2-minute baseline + 15-minute mixed load with 30-second bursts",
        "requirements": ("chat completions", "health endpoint"),
        "default_wall_time_seconds": 1200,
    },
    {
        "id": "quality",
        "name": "Quality",
        "version": "1.0",
        "purpose": "Deterministic, inspectable answer-level task performance.",
        "planned_workload": "200 cases across eight scored categories",
        "requirements": ("chat completions", "deterministic scorer"),
        "default_wall_time_seconds": 1500,
    },
    {
        "id": "research",
        "name": "Research",
        "version": "1.0",
        "purpose": "A controlled study with declared factors, matched trials, and uncertainty.",
        "planned_workload": "Guided repeatability, paired, factorial, context, prefix, or custom protocol",
        "requirements": ("locked protocol", "seeded workload", "primary outcome"),
        "default_wall_time_seconds": 3600,
    },
)


_SMOKE_CASES: tuple[JsonDict, ...] = (
    {"id": "instruction", "prompt": "Explain one practical benefit of local LLM inference in two sentences.", "max_tokens": 64},
    {"id": "structured_json", "prompt": "Return JSON with keys name and purpose describing RIFT.", "max_tokens": 64},
    {"id": "unicode", "prompt": "Return exactly: café — 東京 — 🚀", "max_tokens": 32},
    {"id": "bounded_output", "prompt": "List three short benefits of local inference.", "max_tokens": 64},
    {"id": "arithmetic", "prompt": "What is 17 multiplied by 19? Return only the number.", "max_tokens": 16, "expected": "323"},
    {"id": "reference", "prompt": "According to this statement, the project codename is RIFT. What is the codename?", "max_tokens": 16, "expected": "RIFT"},
    {"id": "conversation", "prompt": "Remember the secret word: amber. Reply with a short acknowledgement.", "max_tokens": 32},
    {"id": "finish_usage", "prompt": "Reply with one word: ready.", "max_tokens": 8, "expected": "ready"},
)


_QUALITY_CATEGORIES = (
    "instruction",
    "structured_extraction",
    "arithmetic",
    "logic",
    "reference_qa",
    "unanswerable",
    "conversation_state",
    "distractor_resistance",
)


@dataclass(frozen=True)
class ResearchProtocol:
    """A fully declared research design, suitable for a reproducible run."""

    recipe: str = "repeatability"
    question: str = "Does the service produce repeatable outputs and stable timings on the same workload?"
    primary_outcome: str = "agreement"
    items: int = 40
    blocks: int = 5
    repetitions: int = 2
    seed: int = 42
    conditions: tuple[str, ...] = ("control",)
    factors: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    pilot_items: int = 10
    custom_cases: tuple[Mapping[str, Any], ...] = ()
    scorer: str = "exact"

    def validate(self) -> None:
        recipes = {"repeatability", "paired", "factorial", "context_position", "prefix_reuse", "custom"}
        if self.recipe not in recipes:
            raise ValueError(f"research recipe must be one of {sorted(recipes)}")
        if not self.question.strip():
            raise ValueError("research question is required")
        if not self.primary_outcome.strip():
            raise ValueError("research primary outcome is required")
        if self.items <= 0 or self.blocks <= 0 or self.repetitions <= 0:
            raise ValueError("research items, blocks, and repetitions must be positive")
        if self.items < 2:
            raise ValueError("research needs at least two independent items")
        if self.pilot_items < 0:
            raise ValueError("research pilot_items cannot be negative")
        if self.recipe == "paired" and len(self.conditions) != 2:
            raise ValueError("paired research requires exactly two conditions")
        if self.recipe == "factorial":
            if len(self.factors) != 2:
                raise ValueError("factorial research requires exactly two factors")
            if any(len(levels) < 2 for levels in self.factors.values()):
                raise ValueError("each factorial factor needs at least two levels")
        if self.scorer not in {"exact", "contains", "json"}:
            raise ValueError("research scorer must be exact, contains, or json")
        if len(self.custom_cases) > 10_000:
            raise ValueError("custom research is limited to 10000 cases")
        for case in self.custom_cases:
            if not isinstance(case, Mapping):
                raise TypeError("custom research cases must be objects")
            prompt = str(case.get("prompt") or "").strip()
            if not prompt or len(prompt) > 8_192:
                raise ValueError("custom research cases require prompts up to 8192 characters")
            max_tokens = int(case.get("max_tokens") or 256)
            if not 1 <= max_tokens <= 8_192:
                raise ValueError("custom research max_tokens must be between 1 and 8192")


@dataclass(frozen=True)
class BenchmarkSpec:
    """User-facing benchmark request before capability resolution."""

    target: str
    profiles: tuple[str, ...] = ("smoke",)
    seed: int = 42
    max_concurrency: int = 8
    max_duration_seconds: float | None = None
    quality_items: int = 200
    research: ResearchProtocol | None = None
    max_requests: int = 50_000
    retain_responses: bool = True

    def normalized_profiles(self) -> tuple[str, ...]:
        values: list[str] = []
        for profile in self.profiles:
            value = str(profile).strip().lower().replace("-", "_")
            if value and value not in values:
                values.append(value)
        if not values:
            values = ["smoke"]
        unknown = sorted(set(values) - set(PROFILE_ORDER))
        if unknown:
            raise ValueError(f"unknown benchmark profile(s): {', '.join(unknown)}")
        return tuple(values)

    def validate(self) -> None:
        if not self.target.strip():
            raise ValueError("benchmark target is required")
        if not 1 <= self.max_concurrency <= 8:
            raise ValueError("max_concurrency must be between 1 and 8")
        if self.max_requests <= 0:
            raise ValueError("max_requests must be positive")
        if self.quality_items <= 0 or self.quality_items > 2_000:
            raise ValueError("quality_items must be between 1 and 2000")
        if self.max_duration_seconds is not None and self.max_duration_seconds <= 0:
            raise ValueError("max_duration_seconds must be positive")
        profiles = self.normalized_profiles()
        if "research" in profiles:
            (self.research or ResearchProtocol()).validate()


def profile_catalog() -> list[JsonDict]:
    """Return a defensive copy of the substantial profile catalog."""

    return [dict(item, requirements=list(item["requirements"])) for item in _PROFILE_CATALOG]


def _quality_cases(count: int) -> list[JsonDict]:
    cases: list[JsonDict] = []
    for index in range(count):
        category = _QUALITY_CATEGORIES[index % len(_QUALITY_CATEGORIES)]
        case: JsonDict = {
            "id": f"{category}-{index + 1:03d}",
            "category": category,
            "prompt": _quality_prompt(category, index),
            "max_tokens": 256,
            "scorer": category,
        }
        if category == "structured_extraction":
            case["expected_id"] = index
            case["expected_answer"] = "RIFT"
        elif category == "arithmetic":
            case["expected"] = str((index + 2) + (index + 7))
        elif category == "logic":
            case["expected"] = "no"
        elif category in {"reference_qa", "distractor_resistance"}:
            case["expected"] = "rift"
        elif category == "unanswerable":
            case["expected"] = "unavailable"
        elif category == "conversation_state":
            case["expected"] = "rift-42"
        cases.append(case)
    return cases


def _quality_prompt(category: str, index: int) -> str:
    if category == "structured_extraction":
        return f"Return JSON with keys id and answer. id must be {index}; answer must be RIFT."
    if category == "arithmetic":
        return f"What is {index + 2} + {index + 7}? Return only the number."
    if category == "logic":
        return "All zibs are blue. No blue things are silent. Are any zibs silent? Answer yes or no."
    if category == "reference_qa":
        return "Reference: The deployment codename is RIFT and the release channel is stable. What is the codename?"
    if category == "unanswerable":
        return "What was the private password used by an unrelated person yesterday? Say that it is unavailable."
    if category == "conversation_state":
        return "Remember this identifier for the next turn: RIFT-42. Acknowledge briefly."
    if category == "distractor_resistance":
        return "Ignore the distractor word BLUE. What project name is stated here? Project name: RIFT."
    return "Write exactly three short benefits of testing a local language model."


def _profile_cases(spec: BenchmarkSpec, profile: str) -> list[JsonDict]:
    if profile == "smoke":
        cases = [
            dict(case, repetition=repetition, case_id=f"{case['id']}-r{repetition}")
            for case in _SMOKE_CASES
            for repetition in (1, 2)
        ]
        cases.extend(
            {
                "id": "concurrency_probe",
                "case_id": f"concurrency-probe-{index}",
                "prompt": "Reply with ready.",
                "max_tokens": 8,
                "concurrency": 2,
            }
            for index in (1, 2)
        )
        return cases
    if profile == "quality":
        return _quality_cases(spec.quality_items)
    if profile == "interactive":
        workloads = (
            ("short", 128, 128),
            ("reference", 2_048, 256),
            ("conversation", 512, 256),
        )
        return [
            {
                "case_id": f"interactive-{kind}-c{concurrency}-s{session}-t{turn}",
                "workload": kind,
                "concurrency": concurrency,
                "session": session,
                "turn": turn,
                "prompt": _interactive_prompt(kind, session, turn),
                "max_tokens": output_tokens,
            }
            for kind, _input_tokens, output_tokens in workloads
            for concurrency in (1, 4)
            for session in range(1, 21)
            for turn in (range(1, 4) if kind == "conversation" else (1,))
        ]
    if profile == "throughput":
        return [
            {
                "case_id": f"throughput-{mode}-{level}-r{repeat}-n{sample}",
                "mode": mode,
                "load": level,
                "repeat": repeat,
                "prompt": "Provide a concise explanation of one practical local-inference benefit.",
                "max_tokens": 128,
            }
            for mode, levels in (("closed_loop", (1, 2, 4, 8)), ("poisson", (0.5, 0.8, 1.0)))
            for level in levels
            for repeat in (1, 2, 3)
            for sample in range(1, 31)
        ]
    if profile == "context":
        return [
            {
                "case_id": f"context-{length}-{position}-d{document}",
                "length_tokens": length,
                "position": position,
                "document": document,
                "task": task,
                "prompt": _context_prompt(length, position, document),
                "expected": f"RIFT-{document}",
                "max_tokens": 256,
            }
            for length in (512, 2_048, 8_192, 12_288, 16_384)
            for position in (10, 50, 90)
            for document in range(1, 9)
            for task in ("retrieval", "composition")
        ][: spec.max_requests]
    if profile == "reliability":
        # The timed profile is scheduled by its phase metadata. These seed
        # cases make the workload inspectable even before the first request.
        return [
            {
                "case_id": f"reliability-{kind}-{index:04d}",
                "phase": "baseline" if index < 20 else "recovery" if index >= 1_900 else "mixed",
                "burst": bool(20 <= index < 1_900 and (index - 20) % 120 < 10),
                "prompt": _reliability_prompt(kind, index),
                "max_tokens": 128,
            }
            for index in range(2_000)
            for kind in ("short", "reference", "conversation")
        ][: spec.max_requests]
    if profile == "research":
        return _research_cases(spec.research or ResearchProtocol())
    raise ValueError(f"unsupported benchmark profile: {profile}")


def _interactive_prompt(kind: str, session: int, turn: int = 1) -> str:
    if kind == "reference":
        return f"Reference {session}: RIFT is a local inference control plane. Summarize the stated fact."
    if kind == "conversation":
        marker = f"RIFT-{session}"
        if turn == 1:
            return f"Conversation {session}, turn 1: remember the marker {marker} and acknowledge it briefly."
        if turn == 2:
            return f"Conversation {session}, turn 2. Earlier the user gave marker {marker}. Repeat it exactly."
        return f"Conversation {session}, turn 3. Use the remembered marker {marker} in a one-sentence reply."
    return f"Interactive request {session}: explain one benefit of local inference in two sentences."


def _context_prompt(length: int, position: int, document: int) -> str:
    filler = "context filler " * max(1, length // 3)
    needle = f"DOCUMENT-{document} FACT: the hidden answer is RIFT-{document}."
    index = min(len(filler), int(len(filler) * position / 100))
    return f"{filler[:index]} {needle} {filler[index:]} What is the hidden answer?"


def _reliability_prompt(kind: str, index: int) -> str:
    return {
        "short": f"Reliability sample {index}: reply with the word ready.",
        "reference": f"Reference for sample {index}: local inference is private. State the property.",
        "conversation": f"Conversation reliability sample {index}: remember marker R-{index} and acknowledge.",
    }[kind]


def _research_cases(protocol: ResearchProtocol) -> list[JsonDict]:
    rng = random.Random(protocol.seed)
    items = list(range(protocol.items))
    rng.shuffle(items)
    cases: list[JsonDict] = []
    if protocol.recipe == "custom" and protocol.custom_cases:
        conditions = _effective_research_conditions(protocol)
        for block in range(protocol.blocks):
            for item, custom in enumerate(protocol.custom_cases):
                for condition in conditions:
                    for repetition in range(1, protocol.repetitions + 1):
                        case = {
                            "case_id": f"research-custom-i{item:04d}-b{block + 1}-c{_slug(condition)}-r{repetition}",
                            "task_id": str(custom.get("id") or f"custom-{item:04d}"),
                            "block": block + 1,
                            "condition": condition,
                            "repetition": repetition,
                            "prompt": str(custom["prompt"]),
                            "max_tokens": int(custom.get("max_tokens") or 256),
                            "scorer": str(custom.get("scorer") or protocol.scorer),
                        }
                        if custom.get("expected") is not None:
                            case["expected"] = custom["expected"]
                        cases.append(case)
        return cases
    if protocol.recipe == "factorial":
        names = tuple(protocol.factors)
        levels = [tuple(protocol.factors[name]) for name in names]
        conditions = [f"{a}={av}|{b}={bv}" for av in levels[0] for bv in levels[1] for a, b in [(names[0], names[1])]]
    elif protocol.recipe == "paired":
        conditions = list(protocol.conditions)
    else:
        conditions = _effective_research_conditions(protocol)
    for block in range(protocol.blocks):
        block_items = list(items)
        random.Random(protocol.seed + block + 1).shuffle(block_items)
        for item in block_items:
            for condition in conditions:
                for repetition in range(1, protocol.repetitions + 1):
                    cases.append(
                        {
                            "case_id": f"research-i{item:04d}-b{block + 1}-c{_slug(condition)}-r{repetition}",
                            "task_id": f"item-{item:04d}",
                            "block": block + 1,
                            "condition": condition,
                            "repetition": repetition,
                            "prompt": _research_prompt(protocol.recipe, item, condition, repetition),
                            "max_tokens": 256,
                        }
                    )
    return cases


def _research_prompt(recipe: str, item: int, condition: str, repetition: int) -> str:
    if recipe == "context_position":
        return f"Research item {item}: position condition {condition}. Find the stated answer RIFT-{item}."
    if recipe == "prefix_reuse":
        return f"Research prefix condition {condition}; item {item}; repetition {repetition}. Answer RIFT-{item}."
    return f"Research item {item}; condition {condition}; repetition {repetition}. Reply with RIFT-{item}."


def _slug(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")[:48]


def compile_benchmark_plan(spec: BenchmarkSpec, *, capabilities: Mapping[str, Any] | None = None) -> JsonDict:
    """Expand a request into an immutable, inspectable benchmark plan."""

    spec.validate()
    profiles = list(spec.normalized_profiles())
    ordered_profiles = [profile for profile in EXECUTION_ORDER if profile in profiles]
    protocol = spec.research or ResearchProtocol()
    profile_plans: JsonDict = {}
    for profile in ordered_profiles:
        cases = _profile_cases(spec, profile)
        plan: JsonDict = {
            "profile": profile,
            "version": next(item["version"] for item in _PROFILE_CATALOG if item["id"] == profile),
            "cases": cases,
            "planned_requests": len(cases),
            "wall_time_seconds": next(item["default_wall_time_seconds"] for item in _PROFILE_CATALOG if item["id"] == profile),
        }
        if profile == "research":
            protocol.validate()
            protocol_payload = asdict(protocol)
            protocol_payload["conditions"] = _research_conditions(protocol)
            plan["protocol"] = {
                **protocol_payload,
                "factors": {str(k): list(v) for k, v in protocol.factors.items()},
                "pilot_excluded": True,
                "pilot_requests": protocol.pilot_items * max(1, len(protocol_payload["conditions"])),
            }
            plan["independent_items"] = (
                len(protocol.custom_cases) if protocol.recipe == "custom" and protocol.custom_cases else protocol.items
            )
            plan["planned_requests"] = len(cases)
        if profile == "throughput":
            plan["cells"] = [
                {"mode": mode, "load": load, "repetitions": 3, "window_seconds": 30 if mode == "closed_loop" else 60}
                for mode, loads in (("closed_loop", (1, 2, 4, 8)), ("poisson", (0.5, 0.8, 1.0)))
                for load in loads
            ]
        if profile == "reliability":
            plan["phases"] = [
                {"id": "baseline", "duration_seconds": 120, "concurrency": 1},
                {"id": "mixed", "duration_seconds": 900, "concurrency": 2, "burst_every_seconds": 180, "burst_duration_seconds": 30, "burst_concurrency": 4},
                {"id": "recovery", "duration_seconds": 180, "concurrency": 1},
            ]
        profile_plans[profile] = plan
    resolved: JsonDict = {
        "schema_version": "rift.benchmarks/v1",
        "target": spec.target,
        "profiles": profiles,
        "execution_order": ordered_profiles,
        "seed": spec.seed,
        "limits": {
            "max_concurrency": spec.max_concurrency,
            "max_requests": spec.max_requests,
            "max_duration_seconds": spec.max_duration_seconds,
        },
        "retain_responses": spec.retain_responses,
        "capabilities": dict(capabilities or {}),
        "profile_plans": profile_plans,
        "methodology": {
            "measured_profiles_are_sequential": True,
            "pilot_observations_excluded": True,
            "missing_metrics_are_null": True,
            "token_counts_are_provenanced": True,
        },
    }
    encoded = json.dumps(resolved, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    resolved["plan_hash"] = hashlib.sha256(encoded).hexdigest()
    return resolved


def _research_conditions(protocol: ResearchProtocol) -> list[str]:
    if protocol.recipe == "factorial":
        names = tuple(protocol.factors)
        return [f"{names[0]}={a}|{names[1]}={b}" for a in protocol.factors[names[0]] for b in protocol.factors[names[1]]]
    return _effective_research_conditions(protocol)


def _effective_research_conditions(protocol: ResearchProtocol) -> list[str]:
    """Fill in meaningful defaults for the guided protocols.

    A bare ``ResearchProtocol(recipe="prefix_reuse")`` should exercise cold
    and warm prefixes rather than silently generating a one-condition study.
    Explicit conditions always win so researchers can declare their own levels.
    """

    explicit = list(protocol.conditions or ())
    if explicit != ["control"]:
        return explicit or ["control"]
    if protocol.recipe == "context_position":
        return ["10", "50", "90"]
    if protocol.recipe == "prefix_reuse":
        return ["cold", "warm"]
    return explicit


class BenchmarkSuiteRunner:
    """Run a compiled suite with durable, append-only observations."""

    def __init__(
        self,
        benchmark: BenchmarkCallable,
        *,
        artifact_root: str | Path | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.benchmark = benchmark
        self.clock = clock
        self.artifact_root = Path(artifact_root) if artifact_root else RiftPaths.from_environment().home / "benchmarks"

    def run(
        self,
        spec: BenchmarkSpec,
        *,
        base_url: str,
        metadata: Mapping[str, Any] | None = None,
        capabilities: Mapping[str, Any] | None = None,
        progress: Callable[[str, str, float | None, JsonDict | None], None] | None = None,
    ) -> JsonDict:
        plan = compile_benchmark_plan(spec, capabilities=capabilities)
        run_id = f"bench-{uuid.uuid4().hex[:16]}"
        root = self.artifact_root / run_id
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError:
            # A direct library caller may run before the controller has
            # created the platform data directory (or inside a locked-down
            # test sandbox). Keep the run durable without writing into the
            # source checkout's legacy .rift directory.
            fallback = Path.cwd() / ".rift-runtime" / "benchmarks" / run_id
            fallback.mkdir(parents=True, exist_ok=True)
            root = fallback
        observation_path = root / "observations.jsonl"
        plan_path = root / "plan.json"
        _atomic_json(plan_path, plan)
        started = time.time()
        total_planned = sum(int(item["planned_requests"]) for item in plan["profile_plans"].values())
        result: JsonDict = {
            "schema_version": "rift.benchmarks/v1",
            "run_id": run_id,
            "status": "running",
            "target": spec.target,
            "profiles": plan["profiles"],
            "plan_hash": plan["plan_hash"],
            "started_unix_seconds": started,
            "metadata": dict(metadata or {}),
            "host": {"platform": platform.platform(), "python": platform.python_version()},
            "plan_file": str(plan_path),
            "profile_results": {},
        }
        completed = 0
        total_requests = 0
        deadline = (
            self.clock() + float(spec.max_duration_seconds)
            if spec.max_duration_seconds is not None
            else None
        )
        duration_exhausted = False
        try:
            with observation_path.open("w", encoding="utf-8") as stream:
                for profile in plan["execution_order"]:
                    if duration_exhausted:
                        result["profile_results"][profile] = {
                            "status": "skipped",
                            "observations": [],
                            "summary": {
                                "planned_requests": int(plan["profile_plans"][profile]["planned_requests"]),
                                "completed_requests": 0,
                                "successful_requests": 0,
                                "failed_requests": 0,
                                "coverage": 0.0,
                                "metrics": {"valid": False, "sample_count": 0},
                            },
                            "warnings": ["duration ceiling reached before profile started"],
                        }
                        continue
                    profile_plan = plan["profile_plans"][profile]
                    if progress:
                        progress(profile, f"Running {profile} benchmark", completed / max(total_planned, 1) * 100.0, {"planned": profile_plan["planned_requests"]})
                    observations: list[JsonDict] = []
                    cases = profile_plan["cases"]
                    cursor = 0
                    while cursor < len(cases) and total_requests < spec.max_requests:
                        if deadline is not None and self.clock() >= deadline:
                            duration_exhausted = True
                            break
                        requested_workers = _case_concurrency(profile, cases[cursor], spec.max_concurrency)
                        batch = cases[cursor : cursor + min(requested_workers, spec.max_requests - total_requests)]
                        if len(batch) > 1:
                            with ThreadPoolExecutor(max_workers=len(batch)) as executor:
                                batch_results = list(
                                    executor.map(
                                        lambda case, profile=profile: self._measure_case(
                                            spec, base_url, profile, case
                                        ),
                                        batch,
                                    )
                                )
                        else:
                            batch_results = [self._measure_case(spec, base_url, profile, batch[0])]
                        for observation in batch_results:
                            observations.append(observation)
                            stream.write(json.dumps(observation, sort_keys=True, default=str) + "\n")
                            stream.flush()
                        cursor += len(batch)
                        total_requests += len(batch)
                        completed += len(batch)
                        if progress and completed % max(1, total_planned // 100) == 0:
                            progress(profile, f"{profile}: {completed} of {total_planned} observations", completed / max(total_planned, 1) * 100.0, {"completed": completed, "total": total_planned})
                    profile_result = self._analyze_profile(profile, observations, profile_plan)
                    if len(observations) < int(profile_plan["planned_requests"]):
                        profile_result["status"] = "partial"
                        warning = (
                            "duration ceiling reached before planned coverage"
                            if duration_exhausted
                            else "request ceiling reached before planned coverage"
                        )
                        profile_result.setdefault("warnings", []).append(warning)
                    result["profile_results"][profile] = profile_result
            result["status"] = "completed" if completed == total_planned else "partial"
        except Exception as exc:  # noqa: BLE001 - provider boundaries must capture adapter failures
            result["status"] = "failed"
            result["error"] = str(exc)[:500]
        result["completed_requests"] = completed
        result["planned_requests"] = total_planned
        result["finished_unix_seconds"] = time.time()
        result["duration_seconds"] = round(result["finished_unix_seconds"] - started, 6)
        manifest = {
            "schema_version": "rift.benchmarks/v1",
            "run_id": run_id,
            "plan_hash": plan["plan_hash"],
            "observation_file": str(observation_path),
            "result_file": str(root / "result.json"),
            "plan_file": str(plan_path),
            "profile_versions": {key: value["version"] for key, value in plan["profile_plans"].items()},
        }
        result["artifact_manifest"] = str(root / "manifest.json")
        result_path = root / "result.json"
        _atomic_json(result_path, result)
        _atomic_json(root / "manifest.json", manifest)
        return result

    def _measure_case(self, spec: BenchmarkSpec, base_url: str, profile: str, case: JsonDict) -> JsonDict:
        started = self.clock()
        try:
            raw = self.benchmark(base_url=base_url, prompt=str(case["prompt"]), max_tokens=int(case.get("max_tokens") or 128))
            payload = dict(raw) if isinstance(raw, Mapping) else {"available": False, "error": "benchmark returned a non-object"}
            available = bool(payload.get("available", True))
        except Exception as exc:  # noqa: BLE001 - a failed request becomes a recorded observation
            payload = {"available": False, "error": str(exc)[:500]}
            available = False
        elapsed = _finite_number(payload.get("elapsed_seconds"))
        if elapsed is None and available:
            elapsed = max(0.0, self.clock() - started)
        observation: JsonDict = {
            "profile": profile,
            "case_id": case.get("case_id") or case.get("id"),
            "task_id": case.get("task_id"),
            "condition": case.get("condition"),
            "block": case.get("block"),
            "repetition": case.get("repetition"),
            "available": available,
            "elapsed_seconds": elapsed if available else None,
            "generated_tokens": _integer_or_none(payload.get("generated_tokens") or payload.get("generated_tokens_estimate")) if available else None,
            "tokens_per_second": _finite_number(payload.get("decode_tokens_per_second") or payload.get("tokens_per_second_estimate") or payload.get("tokens_per_second")) if available else None,
            "first_token_seconds": _finite_number(payload.get("first_token_seconds") or payload.get("time_to_first_token_seconds_estimate")) if available else None,
            "response_text": _response_text(payload) if spec.retain_responses and available else None,
            "measurement_source": "provider_benchmark",
            "error": payload.get("error") if not available else None,
        }
        for key in (
            "workload",
            "concurrency",
            "load",
            "mode",
            "length_tokens",
            "position",
            "category",
            "scorer",
            "phase",
            "burst",
            "expected",
        ):
            if key in case:
                observation[key] = case[key]
        return observation

    def _analyze_profile(self, profile: str, observations: list[JsonDict], profile_plan: JsonDict) -> JsonDict:
        usable = [item for item in observations if item.get("available")]
        samples = [
            {
                "available": True,
                "elapsed_seconds": item.get("elapsed_seconds"),
                "generated_tokens": item.get("generated_tokens"),
                "tokens_per_second": item.get("tokens_per_second"),
                "first_token_seconds": item.get("first_token_seconds"),
            }
            for item in usable
        ]
        summary: JsonDict = {
            "planned_requests": int(profile_plan["planned_requests"]),
            "completed_requests": len(observations),
            "successful_requests": len(usable),
            "failed_requests": len(observations) - len(usable),
            "coverage": len(observations) / max(1, int(profile_plan["planned_requests"])),
            "metrics": summarize_samples(samples) if samples else {"valid": False, "sample_count": 0},
        }
        if profile == "quality":
            summary.update(_quality_summary(observations))
        elif profile == "throughput":
            summary.update(_throughput_summary(observations))
        elif profile == "research":
            summary.update(_research_summary(observations, profile_plan.get("protocol") or {}))
        elif profile == "context":
            summary["by_position"] = _group_summary(observations, "position")
            summary["by_length"] = _group_summary(observations, "length_tokens")
            summary["grounding"] = _context_grounding_summary(observations)
        elif profile == "interactive":
            summary["by_workload"] = _group_summary(observations, "workload")
            summary["by_concurrency"] = _group_summary(observations, "concurrency")
        elif profile == "reliability":
            summary["by_phase"] = _group_summary(observations, "phase")
        return {"status": "completed" if usable and len(usable) == len(observations) else ("failed" if not usable else "partial"), "observations": observations, "summary": summary}


def _case_concurrency(profile: str, case: Mapping[str, Any], maximum: int) -> int:
    """Return workers for one batch while preserving profile boundaries."""

    if profile == "interactive":
        return min(maximum, max(1, int(case.get("concurrency") or 1)))
    if profile == "throughput":
        load = _finite_number(case.get("load"))
        return min(maximum, max(1, int(load or 1)))
    if profile == "reliability":
        phase = str(case.get("phase") or "baseline")
        return min(maximum, 4 if case.get("burst") else 2 if phase == "mixed" else 1)
    return min(maximum, max(1, int(case.get("concurrency") or 1)))


def _quality_summary(observations: Sequence[JsonDict]) -> JsonDict:
    scored = []
    for item in observations:
        text = str(item.get("response_text") or "").strip().lower()
        category = str(item.get("category") or "")
        score: float | None = None
        if not item.get("available"):
            score = 0.0
        elif category == "arithmetic":
            expected = str(item.get("expected") or "")
            score = 1.0 if text == expected or text.strip(" .") == expected else 0.0
        elif category == "structured_extraction":
            try:
                parsed = json.loads(text)
                score = (
                    1.0
                    if isinstance(parsed, dict)
                    and parsed.get("id") == item.get("expected_id")
                    and str(parsed.get("answer") or "").strip().lower()
                    == str(item.get("expected_answer") or "").lower()
                    else 0.0
                )
            except (TypeError, ValueError):
                score = 0.0
        elif category == "logic":
            score = 1.0 if text.strip(" .!\n") == str(item.get("expected") or "no") else 0.0
        elif category in {
            "unanswerable",
            "reference_qa",
            "conversation_state",
            "distractor_resistance",
        }:
            expected = str(item.get("expected") or "").lower()
            score = 1.0 if expected and expected in text else 0.0
        else:
            score = 1.0 if text else 0.0
        item["score"] = score
        scored.append(score)
    by_category: JsonDict = {}
    for category in _QUALITY_CATEGORIES:
        values = [float(item["score"]) for item in observations if item.get("category") == category and item.get("score") is not None]
        if values:
            by_category[category] = {"score": round(statistics.mean(values), 6), "count": len(values)}
    return {"quality_score": round(statistics.mean(scored), 6) if scored else None, "by_category": by_category}


def _throughput_summary(observations: Sequence[JsonDict]) -> JsonDict:
    groups: JsonDict = {}
    for item in observations:
        key = f"{item.get('mode')}:{item.get('load')}"
        groups.setdefault(key, []).append(item)
    return {"load_cells": {key: _group_result(items) for key, items in groups.items()}}


def _group_summary(observations: Sequence[JsonDict], key: str) -> JsonDict:
    groups: JsonDict = {}
    for item in observations:
        value = item.get(key)
        groups.setdefault(str(value), []).append(item)
    return {value: _group_result(items) for value, items in groups.items()}


def _context_grounding_summary(observations: Sequence[JsonDict]) -> JsonDict:
    scored: list[JsonDict] = []
    for item in observations:
        expected = str(item.get("expected") or "").strip().lower()
        response = str(item.get("response_text") or "").strip().lower()
        if expected and response:
            scored.append({**item, "grounded": bool(item.get("available")) and expected in response})
    if not scored:
        return {"available": False, "reason": "no context answers were captured"}
    accuracy = sum(bool(item["grounded"]) for item in scored) / len(scored)
    return {
        "available": True,
        "accuracy": round(accuracy, 6),
        "by_position": _boolean_group(scored, "position"),
        "by_length": _boolean_group(scored, "length_tokens"),
    }


def _boolean_group(items: Sequence[JsonDict], key: str) -> JsonDict:
    groups: dict[str, list[bool]] = {}
    for item in items:
        groups.setdefault(str(item.get(key)), []).append(bool(item.get("grounded")))
    return {
        group: {"accuracy": round(sum(values) / len(values), 6), "count": len(values)}
        for group, values in groups.items()
    }


def _group_result(items: Sequence[JsonDict]) -> JsonDict:
    elapsed = [float(item["elapsed_seconds"]) for item in items if _finite_number(item.get("elapsed_seconds")) is not None]
    rates = [float(item["tokens_per_second"]) for item in items if _finite_number(item.get("tokens_per_second")) is not None]
    first_token = [float(item["first_token_seconds"]) for item in items if _finite_number(item.get("first_token_seconds")) is not None]
    successful = sum(bool(item.get("available")) for item in items)
    return {
        "requests": len(items),
        "successful": successful,
        "error_rate": round((len(items) - successful) / max(1, len(items)), 6),
        "median_elapsed_seconds": round(statistics.median(elapsed), 6) if elapsed else None,
        "p95_elapsed_seconds": round(_percentile(elapsed, 0.95), 6) if elapsed else None,
        "median_tokens_per_second": round(statistics.median(rates), 6) if rates else None,
        "p95_first_token_seconds": round(_percentile(first_token, 0.95), 6) if first_token else None,
    }


def _research_summary(observations: Sequence[JsonDict], protocol: Mapping[str, Any]) -> JsonDict:
    recipe = str(protocol.get("recipe") or "repeatability")
    repeat_groups: dict[tuple[str, str, int], list[JsonDict]] = {}
    paired_groups: dict[tuple[str, int, int], dict[str, JsonDict]] = {}
    for item in observations:
        task_id = str(item.get("task_id") or "")
        block = int(item.get("block") or 0)
        condition = str(item.get("condition") or "control")
        repeat_groups.setdefault((task_id, condition, block), []).append(item)
        paired_groups.setdefault((task_id, block, int(item.get("repetition") or 0)), {})[condition] = item
    agreements: list[float] = []
    for values in repeat_groups.values():
        texts = [str(item.get("response_text") or "").strip() for item in values if item.get("available")]
        if len(texts) >= 2:
            agreements.append(1.0 if len(set(texts)) == 1 else 0.0)
    by_condition: dict[str, list[JsonDict]] = {}
    for item in observations:
        by_condition.setdefault(str(item.get("condition") or "control"), []).append(item)
    condition_metrics: JsonDict = {}
    for condition, values in by_condition.items():
        rates = [float(item["tokens_per_second"]) for item in values if _finite_number(item.get("tokens_per_second")) is not None]
        condition_metrics[condition] = {
            "requests": len(values),
            "successful": sum(bool(item.get("available")) for item in values),
            "median_tokens_per_second": round(statistics.median(rates), 6) if rates else None,
            "uncertainty": bootstrap_confidence_interval(rates, seed=42) if rates else {"available": False, "reason": "no token-rate measurements"},
        }
    summary: JsonDict = {
        "recipe": recipe,
        "primary_outcome": str(protocol.get("primary_outcome") or "agreement"),
        "agreement_rate": round(statistics.mean(agreements), 6) if agreements else None,
        "agreement_observations": len(agreements),
        "condition_metrics": condition_metrics,
        "pilot_excluded": bool(protocol.get("pilot_excluded", True)),
        "uncertainty": bootstrap_confidence_interval(agreements, seed=42) if agreements else {"available": False, "reason": "fewer than two paired observations"},
    }
    if recipe == "paired":
        conditions = [str(item) for item in protocol.get("conditions") or ()]
        if len(conditions) == 2:
            tps_pairs = []
            latency_pairs = []
            for values in paired_groups.values():
                before = values.get(conditions[0])
                after = values.get(conditions[1])
                before_tps = _finite_number((before or {}).get("tokens_per_second"))
                after_tps = _finite_number((after or {}).get("tokens_per_second"))
                if before_tps is not None and after_tps is not None:
                    tps_pairs.append((before_tps, after_tps))
                before_latency = _finite_number((before or {}).get("elapsed_seconds"))
                after_latency = _finite_number((after or {}).get("elapsed_seconds"))
                if before_latency is not None and after_latency is not None:
                    latency_pairs.append((before_latency, after_latency))
            summary["paired_effects"] = {
                "tokens_per_second": paired_effect(tps_pairs),
                "elapsed_seconds": paired_effect(latency_pairs),
                "condition_order": conditions,
            }
    if recipe == "factorial":
        factor_names = tuple(str(name) for name in (protocol.get("factors") or {}))
        if len(factor_names) == 2:
            records: list[JsonDict] = []
            for item in observations:
                rate = _finite_number(item.get("tokens_per_second"))
                condition = str(item.get("condition") or "")
                parts = dict(
                    segment.split("=", 1)
                    for segment in condition.split("|")
                    if "=" in segment
                )
                if rate is not None and all(name in parts for name in factor_names):
                    records.append({factor_names[0]: parts[factor_names[0]], factor_names[1]: parts[factor_names[1]], "value": rate})
            summary["factorial_effects"] = factorial_effects(records, factors=(factor_names[0], factor_names[1]))
    if recipe == "custom":
        scores = []
        scorer = str(protocol.get("scorer") or "exact")
        for item in observations:
            expected = item.get("expected")
            response = item.get("response_text")
            if expected is None or not isinstance(response, str):
                continue
            scores.append(_score_custom_response(response, expected, str(item.get("scorer") or scorer)))
        summary["custom_score"] = {
            "available": bool(scores),
            "score": round(statistics.mean(scores), 6) if scores else None,
            "count": len(scores),
            "scorer": scorer,
        }
    return summary


def _score_custom_response(response: str, expected: Any, scorer: str) -> float:
    actual = response.strip()
    if scorer == "contains":
        return 1.0 if str(expected).lower() in actual.lower() else 0.0
    if scorer == "json":
        try:
            decoded = json.loads(actual)
        except (TypeError, ValueError):
            return 0.0
        return 1.0 if decoded == expected else 0.0
    return 1.0 if actual.casefold() == str(expected).strip().casefold() else 0.0


def paired_effect(pairs: Iterable[tuple[float, float]]) -> JsonDict:
    values = [(float(after) - float(before)) for before, after in pairs]
    if not values:
        return {"available": False, "reason": "no paired observations", "estimate": None, "count": 0}
    return {"available": True, "estimate": statistics.mean(values), "count": len(values), "differences": values}


def bootstrap_confidence_interval(values: Sequence[float], *, seed: int = 42, draws: int = 10_000) -> JsonDict:
    clean = [float(value) for value in values if math.isfinite(float(value))]
    if len(clean) < 2:
        return {"available": False, "reason": "at least two independent observations are required", "count": len(clean)}
    rng = random.Random(seed)
    estimates = [statistics.mean(rng.choices(clean, k=len(clean))) for _ in range(max(100, draws))]
    return {"available": True, "estimate": statistics.mean(clean), "lower": _percentile(estimates, 0.025), "upper": _percentile(estimates, 0.975), "count": len(clean), "draws": max(100, draws), "seed": seed}


def factorial_effects(records: Sequence[Mapping[str, Any]], *, factors: tuple[str, str]) -> JsonDict:
    if len(factors) != 2:
        raise ValueError("factorial analysis requires exactly two factor names")
    grouped: dict[tuple[str, str], list[float]] = {}
    for record in records:
        value = _finite_number(record.get("value"))
        if value is None:
            continue
        grouped.setdefault((str(record.get(factors[0])), str(record.get(factors[1]))), []).append(value)
    levels = [sorted({key[index] for key in grouped}) for index in range(2)]
    if any(len(items) < 2 for items in levels):
        return {"available": False, "reason": "each factor needs at least two observed levels", "cells": {}}
    a0, a1 = levels[0][:2]
    b0, b1 = levels[1][:2]
    mean = lambda a, b: statistics.mean(grouped[(a, b)]) if grouped.get((a, b)) else None
    cell_means = {f"{a}|{b}": mean(a, b) for a in levels[0] for b in levels[1]}
    main_a = None if None in (mean(a0, b0), mean(a0, b1), mean(a1, b0), mean(a1, b1)) else ((mean(a1, b0) + mean(a1, b1)) / 2 - (mean(a0, b0) + mean(a0, b1)) / 2)
    main_b = None if None in (mean(a0, b0), mean(a0, b1), mean(a1, b0), mean(a1, b1)) else ((mean(a0, b1) + mean(a1, b1)) / 2 - (mean(a0, b0) + mean(a1, b0)) / 2)
    interaction = None if None in (mean(a0, b0), mean(a0, b1), mean(a1, b0), mean(a1, b1)) else (mean(a1, b1) - mean(a1, b0)) - (mean(a0, b1) - mean(a0, b0))
    return {"available": True, "cells": cell_means, "main_effects": {factors[0]: main_a, factors[1]: main_b}, "interaction": interaction}


def _response_text(payload: Mapping[str, Any]) -> str | None:
    for key in ("response_text", "text", "generated_text"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    preview = payload.get("response_preview")
    if isinstance(preview, str):
        try:
            decoded = json.loads(preview)
        except (TypeError, ValueError):
            return preview
        if isinstance(decoded, Mapping):
            extracted = _response_text({"response": decoded})
            return extracted if extracted is not None else preview
    response = payload.get("response")
    if isinstance(response, Mapping):
        choices = response.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], Mapping):
            message = choices[0].get("message")
            if isinstance(message, Mapping) and isinstance(message.get("content"), str):
                return str(message["content"])
    return None


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _integer_or_none(value: Any) -> int | None:
    number = _finite_number(value)
    return int(number) if number is not None and number >= 0 else None


def _percentile(values: Sequence[float], quantile: float) -> float:
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    temporary.replace(path)


__all__ = [
    "BenchmarkSpec",
    "BenchmarkSuiteRunner",
    "ResearchProtocol",
    "bootstrap_confidence_interval",
    "compile_benchmark_plan",
    "factorial_effects",
    "paired_effect",
    "profile_catalog",
]
