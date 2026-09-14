# RIFT implementation handoff for Luna

## Read this first

The user requested implementation of the approved one-click local/cluster
deployment roadmap. **The full roadmap is NOT implemented.** This working tree
contains a tested first increment: shared-tuning recovery, monitoring corrections
and resource graphs, plus internal workload policy/approval foundations.

Continue from the current working tree. Do not reset it, redo the recovery, or
cherry-pick the old tuning commit over these changes.

- Branch: `upgrade-again`.
- Starting HEAD: `edb313d` (Mesh-Upgrade merge).
- All work in this increment is uncommitted. No commit, push, PR or merge made.
- User preference: work directly on the branch; no superpowers or subagents.
- No real models/backends/drivers were installed or benchmarked this increment.
- The temporary browser-test server and browser were closed. No long-running
  worker or test command is intentionally left running.
- Generated static/SSR bundles were rebuilt using the existing clean-build
  script. Numerous old hashed-file deletions/new additions are expected.
  New source files are also untracked; `git diff --stat` alone omits them.

Read `one-click-deployment-progress.md` beside this file for product decisions,
the eight delivery checkpoints and explicit limitations. The full approved plan
also remains in the conversation. The source strategy was titled **RIFT — Market
Impact Product Strategy and Roadmap**; its example metrics were illustrative.

## Product decisions that must survive the handoff

1. Simple one-click and existing Advanced experiences share the same control
   plane. Do not create a second tuner or deployment lifecycle.
2. Text workloads first: chat, coding, extraction, tool capabilities and RAG
   generation over supplied context. Building retrieval/ingestion systems,
   arbitrary tool execution, chaos injection and training are separate features.
3. Saved explicit compute/permission policy; editable workload interpretation;
   one exact approval before bounded autonomous action.
4. Choose the first fully verified fit; optimize further only when requested.
5. Target Windows/WSL, Linux x86, Apple Silicon and ARM Linux edge. Qualification
   is specific to hardware/runtime/model/features, not a marketing checkbox.
6. Cluster release starts with whole services/independent replicas. Discovered
   devices must be enrolled/trusted before execution. Do not pool arbitrary VRAM.
7. Default operational mode is recover + advise. Idle tuning and canary modes
   require separate authority and qualified execution paths.
8. Preserve hard requirements. Explain failures and offer edits; never silently
   promote a service that violates an approved contract.
9. One tuning page, Speed and Cost profiles; adapter chosen from service identity.
10. Normal tuning cannot replace weights, change weight quantization/dtype,
    substitute templates or runtimes, or reduce required capacity/concurrency.
    KV precision is a separate visible permission. Alternative artifacts consume
    explicit permissions and budgets.
11. No fabricated benchmark claims or human-engineer time savings. Human savings
    need a comparable measured human baseline.

## What was implemented

### A. Recovered shared tuner

The current branch initially contained only llama.cpp-specific profiled tuning.
The previous shared implementation was found at local commit `932cd6d`, on
branch `tuning`, directly descended from `edb313d`.

Selected source/test/UI/API changes were recovered using patches, not a merge.
Old evidence reports, validation scripts, promotional README text and the old
product technical overview were deliberately not imported.

New recovered modules:

- `python/rift/tuning_adapters.py`: separate tuning registry, llama.cpp wrapper,
  runtime-probed vLLM parameter descriptors/proposals and identity validation.
- `python/rift/tuning_coordinator.py`: extracted profiled tuning transaction;
  existing serving lifecycle still belongs to the orchestrator.
- `python/rift/tuning_benchmark.py`: concurrent request windows, explicit usage,
  measured/estimated token provenance and seeded bootstrap primitives.
- `python/rift/tuning_contracts.py`: versioned shared interchange records.

Existing files changed:

- `orchestrator.py` now inherits the coordinator; legacy paths remain.
- `tuning_engine.py` includes more identity locks and durable service/device leases.
- Providers `base.py`, `openai_backend.py`, `vllm.py` include shared controls,
  streaming observations, runtime probes and native/container/WSL handling.
- CLI `commands.py`/`parser.py`, server, OpenAPI, UI client/hooks/tuning route
  expose backend capabilities and usage through the existing workflow.

Additional corrections made after recovery:

- Locked WSL distribution, Python, model path and runtime probe identity.
- Explicit saved WSL Python wins over newly detected Python.
- UI usage defaults to service inference; service changes reset incompatible
  speculation/preview state. N-gram control is llama.cpp-only.
- Interactive benchmarking still offers the deployed service's concurrency.
- New Speed confidence/improvement calculations use window objectives rather
  than reconstructing throughput from elapsed-time surrogates.
- Default tuning repeats raised to five; fewer new windows are inconclusive.
- Removed false p95 alias that previously contained mean latency.
- Explicit zero server token usage cannot be replaced by a positive estimate.
- Cost requests use fixed seed/temperature.
- Concurrent Cost returns unavailable until concurrent energy accounting exists;
  it does not quietly benchmark at concurrency one.

### B. Monitoring correctness and working resource charts

Backend:

- `telemetry_latest()` previously requested one ascending sample: the oldest.
  It now requests the newest observation, including out-of-order ingestion cases.
- `TelemetryStore.finish_session()` now reads all retained samples instead of
  truncating reports at the public series page limit of 20,000.
- Shared SQLite connection methods are serialized by an RLock. Sample sequence
  allocation uses an immediate transaction; supervisor signals use a store
  method instead of bypassing transaction ownership.
- Payload metadata cannot overwrite stored sequence/session/time identity.
- Nonfinite sample JSON is rejected without poisoning the next transaction.
- Series responses include a truncation indicator.
- Added `GET /api/rift/v2/telemetry/history`, wired in server/OpenAPI.
  It supports allowlisted numeric gauges, one session, maximum 48-hour range,
  1–1,200 buckets, mean/minimum/maximum/count and explicit null gaps.

Frontend:

- Added `ui/src/components/rift/resource-history.tsx` to Fleet.
- Added types, client method and React Query hook.
- Select observed session, metric and 15-minute/1-hour/24-hour window.
- Recharts lines show sample mean and peak; missing buckets break lines.
- Accessible selectors and expandable data table.
- Honest source/scope text: these are host/GPU observations, not exclusive
  per-service energy attribution or workload-SLO verification.

Browser QA found/fixed incorrect CSS variable names that made the chart lines
invisible. The smoke test now checks actual visible strokes, not merely axes.
The final screenshot was visually inspected with visible curves and a gap.

### C. Internal policy and approval foundations

New `python/rift/execution_policy.py`:

- Strict explicit actions/targets/sources/licenses/network/limits/exposure and
  operations-mode validation; no wildcard targets or truthy-string permissions.
- Run envelope must be within the saved policy.
- Structured text-workload contract validation with explicit throughput scope,
  reviewed p95, context, concurrency, quality suite/version/floor/mandatory cases,
  tool/structured-output booleans and model/backend constraints.
- Canonical JSON and SHA-256 hashes; unsupported fields fail closed.

New `python/rift/workload_store.py`:

- SQLite immutable policy and draft revisions, provenance and review questions.
- Exact contract/envelope hash approval and expected-revision checks.
- Idempotent approval; changed contents require a new revision.
- Edits supersede previous approval; questions prevent approval.
- Pessimistic, idempotent network/action reservations before execution.
- Per-artifact/total network accounting and downloaded-artifact limits survive
  reopening; concurrent reservations cannot overspend.
- Approval explicitly returns `deployment_started: false`.

**The approval journal is not an executor.** The old `workload_contracts.py`
from `932cd6d` remains intentionally excluded: its deterministic parser was
incomplete and could drop requirements. The bounded review-only compiler/API/
CLI added below is a new implementation and does not claim deployment.

### E. Workload compiler/API/CLI (new in this continuation)

- `python/rift/workload_compiler.py` deterministically compiles natural-language
  and structured JSON/YAML requests into the strict v1 text-workload contract.
- Quantities, units, comparators, task/objective signals, context, concurrency,
  tool/structured-output requirements, backend/model hints and offline language
  are extracted with field-level provenance. Ambiguities and unsupported input
  remain visible as questions/warnings; input text cannot grant permissions.
- `RiftServerRuntime` exposes list/compile/get/edit/approve workload routes,
  including canonical contract hashes, revision checks and normal operation
  idempotency. `PUT` editing creates a new revision and `approve` remains
  journal-only (`deployment_started: false`).
- CLI adds `rift workload compile --text/--file [--no-save]`,
  `rift workload show DRAFT_ID`, `rift workload approve`, and
  `rift workload run`.
- OpenAPI now documents the review resources and `WorkloadDraft` shape.

The compiler/API slice remains review-first: compilation and approval never
start deployment. The executor below consumes the reviewed draft and envelope,
with the explicit acceptance limitations recorded there.

### F. Easy-path executor and UI (new continuation)

`python/rift/workload_controller.py` now consumes an approved journal record and
reuses the existing recommendation, immutable plan/apply, benchmark,
evaluation and shared tuning paths. It supports local offline search and
permitted online search, applies only envelope-authorized actions, records
durable workload runs/events, invokes Speed/Cost tuning when authorized, and
classifies terminal outcomes conservatively. `GET/POST /v2/workload-runs` and
`rift workload run` expose the bridge.

The dashboard has a separate Easy deploy page at `/workloads` with a natural-
language input, compiled-contract review, explicit policy/envelope controls,
and an Approve & start action. Advanced setup/tuning remains unchanged. The
page receives a stable run id, polls the durable event journal, and can cancel
through the existing operation control. Rich candidate/evidence views and
final promotion presentation remain pending.

The executor's initial acceptance bridge checks deployment health, benchmark
availability, throughput and the existing evaluation suite. It does not yet
claim full workload conformance for p95 TTFT, near-capacity context, exact tool
call cases, structured schemas, multi-candidate switching or evidence charts.

### D. Documentation/build

- README labels the upgrade in progress and links to implementation status.
- `docs/implementation/one-click-deployment-progress.md` records delivered versus
  pending functionality and release gates.
- OpenAPI describes the resource history endpoint and corrected tuning behavior.
- Packaged static and SSR output rebuilt together; obsolete generated bundles
  removed by the clean build, not hand-edited. They are reproducible from source.

## Verification and how to repeat it

Latest complete Python run: **342 passed, 8 subtests passed**, about 81 seconds.
After the final WSL-model-path lock/API wording edits, the focused tuning suite
was rerun: **31 passed**.

Use the repository virtualenv. System `python` had no pytest. Isolate runtime
state: two legacy tests otherwise write to the operator's default RIFT directory
and hit sandbox permissions. Do not escalate to write live operator state.

From repository root, PowerShell:

```powershell
$env:RIFT_HOME = Join-Path $env:TEMP ('rift-validation-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest tests/python -q
```

Relevant tests:

- `tests/python/telemetry_history_tests.py`: latest ordering, gaps/zero, session
  isolation, query limits, long reports, concurrency, API and nonfinite samples.
- `tests/python/workload_store_tests.py`: 28 policy/approval/budget regressions.
- `tests/python/tuning_adapter_tests.py`, `tuning_contract_tests.py` plus existing
  profiled/engine/API/provider/CLI/monitoring regressions.

UI checks passed from `ui`:

```powershell
.\node_modules\.bin\tsc.cmd --noEmit
npm.cmd run build
npm.cmd run verify:tuning-flow
npm.cmd run verify:setup-flow
npm.cmd run verify:benchmark-report
npm.cmd run verify:operation-state
```

New browser smoke:

```powershell
# If Playwright is not locally installed, point to an existing package index.mjs.
$env:RIFT_PLAYWRIGHT_MODULE = '<installed-playwright>/index.mjs'
node scripts/verify-resource-history.mjs
```

Bundled Playwright was located via the workspace-dependencies tool. Optional
`RIFT_UI_SCREENSHOT` writes an ignored screenshot. Current artifact:
`tmp/resource-history-smoke.png` (synthetic UI data, NOT performance evidence).
Browser assertions: visible mean/peak curves, 180-row table, range change,
missing-sensor message, no page errors. Temporary server/browser close in finally.

Other checks: OpenAPI YAML parses; `git diff --check` passes (Git emits some
LF/CRLF notices). A limited packaged-source scan found no contributor home paths;
this was not a comprehensive secret/PII audit or push-readiness certification.

## What remains, in recommended execution order

### 1. Finish shared execution and acceptance foundations

- Audit recovered coordinator thoroughly rather than treating old work as certified.
- Pin/verify complete effective model, directory artifact hashes, dtype, template,
  parser, runtime build and device identity. `auto` must resolve visibly.
- Validate flags/combinations in the exact selected runtime with actual launches.
  Recheck vLLM module/CLI argument compatibility and device allocation restrictions.
- Interleave baseline/finalist retests; reserve acceptance/recovery time; enforce
  budgets at every checkpoint; ensure cancellation during quality/final stages.
- Versioned held-out task/tool/schema/context suites; current response checks
  still include baseline similarity and are not comprehensive task accuracy.
- At least five independent windows; at least 100 completions per critical p95
  cell; seeded distribution bounds and honest inconclusive results.
- Cost: comparable request mix/arrival schedule, CPU plus accelerator domain
  coverage where required, provider uncertainty/dedup, concurrent energy windows.
- Real llama.cpp and vLLM qualification; SGLang/MLX tuning adapters later.
- Review durable unavailable/failure status semantics and lease/recovery paths,
  including exceptions before the main protected transaction block.

### 2. Actual workload deployment connection

- Extend the deterministic compiler with the pinned local semantic pack,
  richer negation/conflict handling and held-out corpus qualification. The
  current parser is intentionally bounded and labels its limitations.
- Local pinned/hash-verified semantic compiler pack, evaluated on a held-out
  corpus; labelled deterministic fallback; no network in offline mode.
- Bind resolved enrolled hardware and policy to reviewed requirements.
- Connect recommendation, artifacts, runtime install/download, provisional
  deployment, shared tuner, fresh acceptance and immutable promotion.
- Maintain exact per-device memory estimates (weights/KV/workspace/graphs/reserve),
  source/license/trust checks and sequential artifact accounting.
- Count local artifacts and tuning trials too, not just downloaded artifacts.
- Implement complete run journal, events, ownership/process identity, recovery,
  cancel/resume, cleanup, budget reservations and conformance before every action.
- Stop at first verified fit; switch structural failures; tune tunable ones.
- Distinguish scoped INFEASIBLE, EXHAUSTED, BLOCKED, FAILED, CANCELLED and
  ROLLBACK_FAILED. Verify actual production endpoint before VERIFIED.

Current policy/executor limitations: no trust/process/cleanup-ownership checks;
no local-artifact or tuning-count consumption; incomplete cancellation/recovery
and promotion conformance; offline installation conservatively disallowed; no
in-flight policy revocation; and acceptance does not yet cover every workload
capability. These must not be mistaken for finished authorization of every
deployment action.

### 3. Simple UI/CLI and evidence

- Refactor setup's numeric steps to stable branch-aware IDs.
- Add Simple/Advanced mode sharing existing records and navigation.
- Describe/preset/import JSON → hardware/pool → interpretation/questions → limits
  and permissions → approval → autonomous progress → verified evidence/endpoint.
- One tuning page remains. Build backend Advanced controls from descriptors.
- CLI workload compile/show/edit and deploy/status/watch/report/cancel/resume;
  noninteractive exact hashes/policy revision, explicit confirmation, no JSON prompts.
- One validated report model drives prose, timelines, charts, candidate decisions,
  JSON/portable HTML/SVG exports and requirement confidence/verdicts.
- Keep workload deployment unavailable until the execution path passes end to end.

### 4. Cluster and ARM first-public-release acceptance

- Trusted enrolled pools, whole-service replica placement, resource/device
  reservations, priorities, stable gateway routing and drain/promotion.
- Measured queue/network/runtime conditions, node partitions/fencing and ownership.
- Preserve existing service where capacity permits; approved maintenance otherwise.
- Physical Windows/WSL/Linux/Apple Silicon/ARM Linux and heterogeneous-cluster tests.
- No default cross-node tensor splitting or unsecured llama.cpp RPC.

### 5. Better operations/monitoring

- Gateway request/latency histograms, backend queue/cache metrics and SLO goodput.
- Cross-session/service history, real minute/hour rollups, byte-bounded retention.
- Ingestion delivery dedup, clock skew, resets, stale/gap marking, OTLP validation.
- Graph event overlays, latency distributions, energy boundaries and incident detail.
- Private workload fingerprints without prompt collection.
- Recover/advise first; optional idle optimization then shadow/canary with explicit
  traffic consent, statistical gates, resource headroom and rollback.
- Drift detection, regression guard, laptop battery/thermal policy, broker/residency.

### 6. Later roadmap

- Adaptive TPE/Bayesian search, local performance history, Pareto/tournaments.
- More workload packs and backend qualifications, imports, compatible APIs/SDK.
- Qualified topology/model splitting/KV cache federation and semantic routing.
- Enterprise identity/RBAC/secrets/audit/airgap/HA and Kubernetes execution target.
- Opt-in signed global evidence network with privacy/poisoning controls.

## Evidence gates still not run

- Fresh actual 3B/7B-class llama.cpp/vLLM Speed and Cost runs.
- Designated >=10% objective improvement with positive confidence and no quality
  regression; a genuinely optimized baseline retaining itself is a valid no-op.
- Complete natural-language/JSON workload deployment through production verification.
- All target accelerator/runtime families and real heterogeneous clusters.
- Human manual-tuning baseline/time comparison.

Do not update public evidence to imply these passed. The current passing tests
are software regression evidence only.
