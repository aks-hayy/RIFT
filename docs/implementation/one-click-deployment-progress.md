# One-click deployment implementation

Status: **in progress; easy-path execution bridge available behind explicit approval**.

The approved direction is one Simple experience alongside the existing Advanced
UI/CLI. Both must drive the same serving, tuning, monitoring and evidence system.
An approval, a healthy process, and a workload verified at its endpoint are three
different states. This implementation must never present one as another.

## Decisions carried forward

- Text chat, coding, extraction, tools and RAG generation over supplied context
  first. Ingestion, arbitrary tool execution, audio/video and training are later.
- A saved explicit compute/permission policy, then an editable interpretation
  and one approval per workload. No authority inferred from natural language.
- First verified fit, with further optimization available afterwards.
- Windows/WSL, Linux x86, Apple Silicon and ARM Linux edge are qualification
  targets, not blanket compatibility claims.
- Clusters initially place whole services/independent replicas on enrolled nodes.
  Discovery alone does not authorize installation or execution.
- Recover and advise by default. Idle optimization and canary operation are
  separately authorized modes, enabled only after qualification.
- Unmet hard requirements produce an explanation and suggested edits, not an
  unapproved best-effort service.
- Ordinary tuning locks weights, quantization, runtime and workload capacity.
  KV precision is a separate visible permission. Alternative artifacts require
  separate authorization and consume search budget.

## Landed in this working tree

### Shared-tuning recovery and corrections

The branch started clean at `edb313d`, without the shared tuner. Its earlier
implementation was found in local commit `932cd6d`. Selected source, API, UI and
test changes were recovered; old performance reports, promotional charts and the
older product overview were not copied into this branch.

- Shared coordinator and a separate tuning-adapter registry for llama.cpp/vLLM.
- Service backend identity determines the adapter; one tuning page, two profiles.
- Runtime-probed vLLM controls and explicit native/container/WSL paths.
- Durable tuning lease handling and optional parent workload references.
- Added missing WSL environment/probe locks; explicit WSL Python now takes
  precedence over a newly detected environment.
- UI usage defaults to the service rather than forcing interactive mode.
  Switching service clears speculation/preview overrides.
- Interactive measurements retain the service's configured concurrency.
- New windowed Speed intervals use deterministic window-level bootstrap and
  require at least five windows. Mean latency is no longer labelled p95.
- An explicit zero server token count is not replaced by a positive text estimate.
- Concurrent Cost is unavailable until concurrent energy-window accounting exists;
  it does not quietly test at concurrency one.

This is a recovered/evolving integration, **not fresh physical qualification**.
Remaining tuning work includes interleaved baseline/finalist remeasurement,
full effective runtime identity resolution, task-specific held-out evaluations,
latency-cell bounds, adaptive search, full energy-domain coverage and runtime
qualification. Legacy scoring readers remain for older measurements.

### Resource monitoring and graphs

- Fixed latest telemetry to read the newest observation instead of the oldest.
- Reports include all retained session samples, not only the first 20,000.
- Serialized shared SQLite access, including supervisor signal writes; sample
  sequence allocation is transactional across connections.
- Stored sequence/session/time fields cannot be overwritten by payload metadata.
- Added `GET /api/rift/v2/telemetry/history`: one session, allowlisted gauge,
  bounded range and bucket count, sample mean/min/max/count, null gaps.
- Fleet graphs provide 15-minute, 1-hour and 24-hour views, resource selection,
  peak overlays and an accessible data table.

These are **resource gauge charts**, not request-latency histograms or proof of
workload satisfaction. The current view covers one process session; restarts
create separate sessions. Host/GPU readings can include other services.
Long-term rollups, cross-session history, gateway distributions, delivery dedup,
event overlays and whole-machine energy attribution remain pending.

### Approval and execution foundations

`execution_policy.py` and `workload_store.py` implement strict structured text
contracts, explicit saved policy envelopes, immutable revisions, exact hash
approval, idempotency, pessimistic download reservations, and durable workload
run/event journals.

- Unsupported contract fields and untyped permissions fail closed.
- Quality floors require a versioned suite and mandatory cases; evaluator
  availability still must be verified by the execution controller.
- Policy envelopes constrain actions, exact targets, sources, licenses,
  exposure, autonomy mode, quantization alternatives and time/network limits.
- Editing a draft supersedes its previous approval. Review questions block approval.
- Approval records say `deployment_started: false`; they never say `VERIFIED`.
- Action reservations survive reopening the journal. Same action ID cannot bind
  different contents. Uncertain downloads remain charged; concurrent requests
  cannot over-reserve bytes. Resume/reconciliation must not blindly execute a
  replayed reservation.

The workload controller is the executor bridge: it reuses recommendation,
immutable plan/apply, health, benchmark, evaluation, and shared tuning. Cleanup
ownership, trust/license checks, local-artifact counting, tuning candidate usage,
runtime setup accounting, cancellation, recovery and full promotion conformance
remain hardening work. Offline installs are conservatively denied by this
initial envelope validator; installing from verified local packs needs a
separate offline installation action. Saved-policy edits apply to future
approvals; explicit revocation of in-flight authority still needs its own
operation.

### Workload compiler and execution bridge (new)

`workload_compiler.py` now provides a deterministic first-pass compiler for
natural-language and structured JSON/YAML inputs. It extracts quantities and
units (throughput, TTFT, context, concurrency and request rate), task/objective
signals, tool and structured-output requirements, backend/model hints and
offline policy language. Each field carries source evidence and confidence.
Ambiguous scope, percentile interpretation, missing quality suites, conflicts
and unsupported fields remain visible as questions or warnings. Instruction-like
input cannot create permissions. The compiler emits a canonical SHA-256 contract
and deliberately does not grant deployment permissions.

The controller now exposes review resources at `/api/rift/v2/workloads` and
`/api/rift/v2/workloads/compile`, immutable draft reads/edits, and exact-hash
approval. CLI equivalents are `rift workload compile --text/--file`,
`rift workload show`, `rift workload approve`, and `rift workload run`.
Approval still returns `deployment_started: false`; the separate run command
consumes that exact approval and executes only within its saved envelope.

### Easy-path execution slice (new)

`workload_controller.py` now bridges approved runs to the existing
recommendation, immutable plan/apply, benchmark, evaluation and shared tuning
primitives. It can search local artifacts for offline requests or permitted
sources for online requests, apply one reviewed plan, run endpoint checks,
invoke Speed/Cost tuning when authorized, and persist `VERIFIED`, `BLOCKED`,
`INFEASIBLE`, `EXHAUSTED` or `FAILED` outcomes. The corresponding
`/api/rift/v2/workload-runs` resources and `rift workload run` command are
available.

The UI now includes an **Easy deploy** page with Natural language and
Structured JSON input modes, compiled-contract review, and explicit network,
launch/restart/promote/cleanup/download/install envelope controls. When all
review questions are resolved, **Approve & start deployment** creates the
policy, approval ID, and workload run automatically. The page shows the stable
run ID, polls its durable event journal, and offers cancel/recover through the
existing operation control. Candidate history, rich evidence rendering and
final promotion presentation remain to be connected.

The acceptance bridge is intentionally conservative but not yet the full
release gate: percentile TTFT, context-capacity, exact tool-call and structured
schema cases, multi-candidate switching, and complete evidence charts still
need dedicated evaluators before this path is production-complete.

## Delivery checkpoints

| Stage | Implementation and exit gate | State |
|---|---|---|
| A | Reconcile branch; recover useful shared work without transplanting old evidence | Source recovered and regression-tested |
| B | Shared tuning, request/energy measurements, safe runtime installation, monitoring history | Partial: recovered tuner and resource charts; qualification pending |
| C | Local compiler, provenance review, policy approval, candidate search, provisional deploy, shared tuning, acceptance, promotion | Easy-path bridge partial; full conformance/evidence gate pending |
| D | Enrolled pools, replica placement, reservations, partition recovery, ARM/heterogeneous physical tests | Pending |
| E | Adaptive bounded search, local performance history, tournaments and Pareto explanations | Pending |
| F | Drift detection, idle optimization, shadow/canary routing, rollback and regression guard | Pending |
| G | Additional workload packs, imports, semantic/API compatibility, wider qualified backends | Pending |
| H | Qualified distributed fabric/KV sharing, enterprise governance, K8s target, opt-in evidence sharing | Pending |

The first public Simple release requires C **and** D acceptance. Standard setup,
plan/apply, tuning, monitoring and the Advanced UI remain available throughout.

## Next implementation slice

1. Resolve effective deployment identity and upgrade shared benchmark/quality
   gates before using the tuner as a workload acceptance engine.
2. Add versioned deterministic compilation and field-level evidence. Unsupported
   requirements stay visible. Qualify the smallest local semantic pack against a
   held-out corpus; no prompt leaves the machine.
3. Connect approved envelopes to existing recommendation, immutable plan/apply,
   provisional service lifecycle and the shared tuner. Persist ownership and
   consumed budgets at every transition.
4. Verify the final gateway endpoint using fresh acceptance, then publish exact
   requirement verdicts and promote the first passing candidate. Distinguish
   BLOCKED, EXHAUSTED, scoped INFEASIBLE and rollback failure.
5. Only then expose Simple setup and workload CLI, followed by enrolled pools and
   physical platform qualification. Refactor setup to stable step IDs before
   adding branches.

## Verification

This tranche uses synthetic fixtures to verify software behavior, not model speed
or quality. No models, drivers or serving runtimes were installed or benchmarked.

Run Python tests with `RIFT_HOME` set to a fresh temporary directory; two legacy
tests otherwise attempt to write the operator's platform-default runtime state.
The isolated full suite passed **342 tests plus 8 subtests** during development.
Focused tests cover history gaps, >20,000 samples, concurrent writers, stale
approvals, type confusion, prompt-text authority injection and budget races.

UI checks: TypeScript, production static/SSR build and existing tuning/setup/
benchmark/operation scripts. `ui/scripts/verify-resource-history.mjs` exercises
the packaged dashboard in Playwright using explicitly synthetic API responses.
It checks visible chart strokes, range control, the 180-row data table and the
unavailable-sensor state, with no browser errors. The resulting synthetic
screenshot was visually inspected; it is not published as performance evidence.

Fresh llama.cpp/vLLM Speed/Cost measurements, hardware-family certification and
the designated 10% improvement gates remain **not run**. Human-engineer time
savings require a comparable measured human baseline; no such claim is made.
