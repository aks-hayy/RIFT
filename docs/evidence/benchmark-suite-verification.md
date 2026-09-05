# RIFT benchmark suite verification evidence

Run date: 2026-09-05  
Suite schema: `rift.benchmarks/v1`  
Verification mode: deterministic offline provider plus repository/build checks

## Scope

This report verifies the benchmark suite's contracts and evidence pipeline. The
offline provider returns fixed latency and token measurements, so this run is
repeatable and does not depend on a model, GPU, network, or service state. It
is evidence that RIFT expands profiles into inspectable workloads, executes
selected profiles sequentially, persists provenance-bearing artifacts, keeps
missing measurements null, and exposes the CLI/UI build surface.

It is not a claim about model quality, physical throughput, GPU energy, or
heterogeneous-node reliability. Those claims require a live service and the
hardware-specific evidence described in the live verification section below.

## Verification matrix

| Check | Command | Observed result |
| --- | --- | --- |
| Benchmark contract tests | `python -m pytest -q tests/python/benchmark_suite_tests.py` | **11 passed** in 0.43 s |
| Full Python suite | `python -m pytest -q` | **267 passed, 8 subtests passed** in 67.27 s |
| Python compilation | `python -m compileall -q python tests` | Exit code 0 |
| Changed UI lint | `npx eslint src/lib/rift/client.ts src/lib/rift/hooks.ts src/lib/rift/types.ts src/routes/deployments.$id.tsx` | Exit code 0 |
| Production dashboard build | `npm run build` from `ui/` | Client + SSR bundles built; 8 routes exported to `python/rift/web/static` |
| Whitespace audit | `git diff --check` | Exit code 0; only expected Git LF/CRLF normalization warnings for generated static assets |

All commands above were run from the repository checkout on the date shown at
the top of this report.

## Deterministic plan expansion

The following probe compiled `smoke`, `research`, and `quality` together for an
offline target. The research protocol was a paired study with three items,
two blocks, two repetitions, and explicit `baseline`/`candidate` conditions.

```json
{
  "execution_order": ["smoke", "research", "quality"],
  "profile_requests": {
    "smoke": 18,
    "research": 24,
    "quality": 4
  },
  "planned_requests": 46,
  "plan_hash": "1a614f613c7316a3ce66cc72882318036c49b054d538441b6fa1e68892320975"
}
```

The catalog contains seven versioned profiles: `smoke`, `interactive`,
`throughput`, `context`, `reliability`, `quality`, and `research`. The plan
records the seed, limits, capabilities, execution order, workload cases, and
methodology flags (`pilot_observations_excluded`, `missing_metrics_are_null`,
and `token_counts_are_provenanced`). Compiling the same specification again
must produce the same plan hash; the research statistics tests also verify
seeded bootstrap confidence intervals and paired/factorial effects.

## Artifact pipeline probe

A deterministic provider was run against `smoke`, `research`, and `quality`
with a smaller research study. The runner completed all requested profiles in
the planned order and persisted the complete artifact set:

```json
{
  "status": "completed",
  "execution_order": ["smoke", "research", "quality"],
  "profile_status": {
    "smoke": "completed",
    "research": "completed",
    "quality": "completed"
  },
  "profile_observations": {
    "smoke": 18,
    "research": 4,
    "quality": 2
  },
  "artifacts": [
    "manifest.json",
    "observations.jsonl",
    "plan.json",
    "result.json"
  ],
  "plan_schema": "rift.benchmarks/v1",
  "manifest_schema": "rift.benchmarks/v1"
}
```

The contract suite separately forces an unavailable provider response and
verifies that the run is marked failed while latency, token, and rate fields
remain `null` rather than becoming fabricated zeros.

## CLI surface verified

The installed CLI exposes the profile-oriented command and the research
recipes used by the plan compiler:

```text
rift benchmark [plan|list|show|compare|export|replay|cancel|targets]
  --profiles smoke,quality,throughput
  --study repeatability|paired|factorial|context_position|prefix_reuse|custom
  --max-concurrency N --max-duration SECONDS --max-requests N
  --quality-items N --seed N --no-retain-responses --yes --follow
```

The CLI defaults to `smoke`, allows multiple profiles in one invocation, and
keeps plan inspection, run listing, comparison, export, replay, and cancellation
as separate explicit actions.

The exact JSON plan command was also executed against the local `chat` target
without dispatching requests. It exited 0 and returned schema
`rift.benchmarks/v1`, execution order `smoke → research → quality`, and plan
hash `15662d5ef600c49e4fa1c6ac0c01f4495fc8366b4dede370906166bfb8b8e6f8`.

## Live verification procedure

To turn this contract evidence into service evidence, run against a reachable
managed or registered OpenAI-compatible target and retain the resulting run
directory:

```powershell
rift benchmark targets
rift --json benchmark plan --service chat --profiles smoke,quality,research --study paired
rift benchmark --service chat --profiles smoke,quality,research --study paired --yes
rift benchmark list --service chat
rift benchmark show RUN_ID
rift benchmark export RUN_ID --format bundle
```

The resulting `plan.json`, `observations.jsonl`, `result.json`, and
`manifest.json` should be attached to any research claim. For a defensible
comparison, keep the target identity, model/artifact digest, prompt suite,
seed, concurrency, context length, backend version, and hardware snapshot
alongside the run. Do not treat an offline fixture or emulated measurement as
physical performance evidence.

## Machine-readable record

The summarized values in this report are also available as
[`benchmark-suite-verification.json`](benchmark-suite-verification.json) for
CI or release checklists.
