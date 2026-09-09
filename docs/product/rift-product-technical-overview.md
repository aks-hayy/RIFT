# RIFT — Product and Technical Architecture

**Document status:** implementation-grounded product reference  
**Scope:** the RIFT control plane currently present in this repository  
**Audience:** product, platform, inference, SRE, security, and developer-tooling teams  
**Last reviewed:** 2026-09-07

This document describes what RIFT currently does, how the pieces fit together, and where the implementation is intentionally qualified, experimental, or only a foundation. It is a product document, not a promise that every advertised backend or hardware combination has passed physical qualification.

## 1. Product definition

RIFT is a local-first, hardware-aware control plane for deploying and operating large-language-model services on one workstation or a small, explicitly managed cluster. It combines machine profiling, model/artifact intelligence, declarative plans, permission-gated execution, service lifecycle management, observability, benchmarking, tuning, and evidence generation behind a CLI, HTTP API, and technical dashboard.

The product boundary is the control plane. RIFT can discover and reason about external serving runtimes, but the runtime itself remains an external process, container, WSL environment, or node-agent process. RIFT does not train models, change model weights during ordinary tuning, or claim universal model quality from a finite benchmark suite.

### 1.1 Core product promise

Given a target machine, model/artifact, backend, and deployment policy, RIFT can:

1. observe hardware and runtime capacity;
2. identify a compatible artifact and serving backend;
3. produce a deterministic, inspectable deployment plan;
4. require explicit approval for installation, launch, restart, promotion, and cleanup;
5. execute and monitor the service;
6. benchmark it with fixed, reproducible request recipes;
7. run bounded Speed or Cost tuning without changing locked model identity;
8. retain baseline, candidate, winner, rejection, and rollback evidence;
9. expose the result through an OpenAI-compatible gateway and the dashboard.

### 1.2 Current delivery status

| Area | Current state | Qualification / interpretation |
|---|---|---|
| Local hardware discovery | Implemented | Read-only profiling of CPU, RAM, GPU/VRAM, disk, thermal and pressure signals |
| Declarative configuration | Implemented | `rift.yaml`, normalized plans, persisted state and permission checks |
| Model/artifact intelligence | Implemented | GGUF and several SafeTensors-derived formats; exact artifact identity and integrity checks |
| llama.cpp serving | Locally verified | GGUF, OpenAI-compatible server lifecycle, Windows/Linux/macOS paths depending installed binary |
| vLLM serving | Implemented, runtime qualification pending | Native Linux, WSL2 and container launch paths; runtime/hardware support must be tested in situ |
| SGLang serving | Implemented, platform gate pending | CUDA-oriented provider; not equivalent to physical qualification |
| MLX-LM serving | Provider present | Apple/MLX capability is exposed through provider discovery; tuning adapter is not registered |
| LMCache | Experimental overlay | Augments compatible serving paths; not an independent model server |
| Shared tuning coordinator | Implemented | One lifecycle and evidence path for backend-specific tuning adapters |
| Speed profile | Implemented | Latency/throughput acceptance with bounded candidate search |
| Cost profile | Implemented when valid energy telemetry exists | Uses measured energy; unavailable is reported rather than converted to zero |
| Tuning adapter registration | llama.cpp and vLLM | SGLang/MLX-LM provider discovery exists, but no certified tuning adapter is registered |
| Cluster scheduler/emulator | Implemented | Deterministic placement and failure emulation; physical heterogeneous-node acceptance remains pending |
| Mesh onboarding | Implemented as controller and emulation flows | mDNS/USB/ADB discovery, consent-gated enrollment and mTLS identity paths exist; physical heterogenous-node qualification is pending |
| Workload-to-deployment flow | Contract/compiler foundation only | `workload_contracts.py` is intentionally not wired into setup or autonomous deployment yet |
| Natural-language autonomous deployment | Not exposed as complete | Requires compiler qualification, candidate search/evaluation adapters and end-to-end hardware acceptance |

Status labels in this document mean:

- **Implemented:** code path and tests exist; physical qualification may still be narrower.
- **Locally verified:** a real local path has been exercised for the stated scope.
- **Unqualified:** the integration is present but the exact runtime/hardware combination has not passed the required acceptance suite.
- **Experimental:** useful for development or controlled trials; do not infer production guarantees.
- **Foundation only:** data contracts or helper primitives exist, but the end-user flow is not enabled.

## 2. System architecture

### 2.1 Control-plane topology

```text
                             CLI / UI / API clients
                                      │
                                      ▼
                           HTTP controller (server.py)
                                      │
                ┌─────────────────────┼─────────────────────┐
                │                     │                     │
                ▼                     ▼                     ▼
        Configuration + plan   Operations/idempotency  Dashboard proxy
        validation/orchestr.   + event timeline         + static assets
                │                     │                     │
                └──────────────┬──────┴──────────────┬──────┘
                               ▼                     ▼
                 Hardware / artifact / backend   State and evidence stores
                 discovery and recommendation   SQLite + JSON + reports
                               │                     │
                               ▼                     │
                      Serving lifecycle              │
              (native process, WSL, container,       │
                 remote node-agent or emulator)      │
                               │                     │
                               ▼                     │
                        Running LLM service ─────────┘
                         OpenAI-compatible API
```

The controller owns desired state, authorization, orchestration, and evidence. Providers own backend-specific commands and diagnostics. The model server owns inference. The gateway is a policy boundary in front of a service, not a second inference engine.

### 2.2 Deployment and tuning dependency direction

```text
Setup / CLI / API / UI
          │
          ├── standard recommendation → plan → apply
          │
          ├── existing-service tune ─────────────┐
          │                                       │
          └── future workload controller          │
              (compiler + approved search)        │
                                                  ▼
                                      Shared tuning coordinator
                                      ├── llama.cpp adapter
                                      └── vLLM adapter
                                                  │
                                      Serving provider lifecycle
                                                  │
                                   benchmark + evaluation + evidence
```

This direction is deliberate: a backend tuning adapter proposes valid configurations, but the coordinator controls measurement, acceptance, promotion, permissions, and rollback. A workload controller will call this same tuner rather than implementing a separate optimizer.

### 2.3 Execution environments

RIFT can target:

- the native host (Windows, Linux, or macOS where the provider supports it);
- a Linux distribution under WSL2;
- a Docker or Podman container;
- a remote node through the RIFT node-agent transport;
- a deterministic cluster/emulator mode for planning and failure tests.

Runtime probing must occur inside the selected execution environment. A Windows host with a compatible Linux/WSL environment is not automatically classified as a legacy Windows engine. RIFT records runtime mode, executable/image, framework and driver evidence where available.

## 3. Hardware and environment intelligence

`system_profile.py` and the telemetry collectors build a normalized machine profile used by recommendations, fit checks, scheduling, tuning, and reports.

### 3.1 Discovered dimensions

- operating system and architecture;
- physical and logical CPU counts;
- CPU model and feature hints;
- total/available RAM and pressure indicators;
- accelerator family (CUDA, ROCm, XPU, Metal, Vulkan, CPU);
- accelerator model, count, VRAM and device identifiers when readable;
- disk volume capacity, free space and configured reserve;
- thermal/pressure observations where platform collectors expose them;
- serving runtime and executable/container visibility;
- running services, ports, health and process ownership.

The profile distinguishes observed values from estimates. Unknown telemetry is represented as unknown; it is not treated as zero capacity or zero energy.

### 3.2 Memory-fit model

Artifact adapters estimate:

```text
resident weights
+ KV/cache state for requested context and concurrency
+ activations and temporary workspace
+ runtime/graph buffers
+ configured reserve/headroom
```

The estimate is model-architecture and runtime aware where metadata is available. Backend allocator overhead and platform-specific KV dtypes are resolved during planning or launch. Aggregate VRAM is not assumed to be poolable unless the selected topology supports it.

The workload path no longer relies on a fixed 12 GiB recommendation ceiling. Download and extraction budgets are constrained by free disk after reserve, temporary installation needs, artifact size, and memory fit. Offline mode has a zero new-download budget.

### 3.3 Resource reservations

The orchestrator and cluster controller use service/device reservations. A tuning run acquires a maintenance lease such as `service:<name>` plus a local device reservation so competing operations do not mutate the same service or device. Monitoring continues to collect telemetry while competing automatic recovery is suppressed for the leased service.

## 4. Model and artifact intelligence

### 4.1 Artifact adapter registry

`python/rift/adapters/artifacts.py` provides format-specific inspection, compatibility and resource estimation. Built-in families include:

- **GGUF** for llama.cpp;
- **SafeTensors** dense model layouts;
- **AWQ**;
- **GPTQ**;
- **FP8**;
- **EXL2**;
- **MLX**;
- generic SafeTensors fallback.

An artifact variant captures repository/source identity, files, total bytes, model family, quantization metadata, multimodal hints, tokenizer/config metadata, and compatible backend families. Specialized adapters are selected from metadata and file layout rather than a filename-only guess.

### 4.2 Hub discovery and downloads

`hf_hub.py` implements:

- cached model metadata and repository tree access;
- pattern filtering and safe remote paths;
- exact file selection;
- resumable `.part` downloads;
- size and disk-capacity preflight;
- atomic promotion after completion;
- SHA-256 verification and provenance records;
- cache status and pruning of RIFT-owned cache entries.

RIFT searches existing local/cache artifacts before asking for network downloads. Download/install permissions are explicit plan actions. A failed or slow download is recorded as infrastructure state, not mislabelled as an inference failure.

### 4.3 Recommendation contract

`recommendations.py` persists recommendation runs and candidate evidence. The recommendation contract includes exact artifact identity, backend compatibility, fit rationale, quality/performance evidence when available, Pareto information, and optional measured-finalist tournament results. Metadata is treated as discovery evidence, not proof of tool calling, quality, or runtime compatibility.

The recommendation engine can choose a backend from artifact format, hardware, runtime availability and policy. Tuning acts on the deployed service identity and therefore does not require a separate backend selector.

## 5. Backend serving adapters

All serving providers implement a compatible lifecycle surface: detect/probe, install plan/install, model fit, launch planning, health/readiness, benchmark, tuning-space enumeration, launch, stop, recovery and capabilities.

### 5.1 Capability registry

The current built-in capability records are:

| Backend | Operating systems | Accelerators | Formats | Current status |
|---|---|---|---|---|
| `llama.cpp` | Windows, Linux, macOS | CPU, CUDA, Metal, Vulkan | GGUF | `verified_local` |
| `vllm` | Linux, WSL2 | CUDA, ROCm, XPU, CPU | SafeTensors, AWQ, GPTQ, FP16, BF16 | `implemented_runtime_probe_unqualified` |
| `sglang` | Linux, WSL2 | CUDA | SafeTensors, AWQ, GPTQ, FP16, BF16 | `implemented_platform_gate_pending` |
| `mlx-lm` | Provider-specific Apple/MLX path | MLX/Metal-oriented | MLX | provider present; qualification depends on host |
| `lmcache_aware` | Linux, WSL2 | CUDA | compatible SafeTensors families | experimental overlay, not a standalone server |

### 5.2 llama.cpp provider

The provider launches an OpenAI-compatible `llama-server` using a GGUF file. The launch planner can represent:

- context length (`--ctx-size`);
- GPU layer offload (`--n-gpu-layers` / `-ngl`);
- batch and micro-batch (`--batch-size`, `--ubatch-size`);
- CPU and batch threads;
- parallel slots and continuous batching;
- Flash Attention;
- K/V cache type and K/V offload;
- unified cache, no-host, operation offload and repacking;
- mmap/mlock and load-mode controls;
- CPU priority, affinity and NUMA hints;
- split mode, tensor split, main GPU and device selection;
- polling controls;
- speculative decoding and n-gram-mod controls when the installed binary advertises them.

The provider probes `--help` and related runtime flags, preserves safe defaults, and gates optional controls to the installed binary. `--skip-chat-parsing` remains disabled during tool/capability evaluation. RIFT never enables llama.cpp built-in shell, filesystem, MCP or agent execution while evaluating a model.

### 5.3 vLLM provider

The provider detects runtimes in this order:

1. isolated RIFT-managed CLI/module;
2. native CLI/module;
3. RIFT-managed WSL installation;
4. Docker/Podman container image.

Supported launch modes include native Python/module execution, WSL2 `wsl.exe` execution, and containerized `vllm serve`. Container device wiring is backend-specific: CUDA uses GPU exposure, ROCm uses `/dev/kfd` and `/dev/dri`, and XPU uses the relevant device mapping. The provider records runtime mode, image/executable, distribution, framework and feature-probe evidence.

The current vLLM tuning descriptor families are:

- scheduler: `max_num_batched_tokens`, `max_num_seqs`, chunked prefill;
- memory/KV capacity: GPU memory utilization or explicit KV bytes;
- prefix reuse: prefix caching;
- KV precision: cache dtype and scale calculation;
- execution: eager mode, attention backend and compilation configuration;
- offload: CPU weight/KV offload controls;
- CPU runtime: `VLLM_CPU_KVCACHE_SPACE` and `VLLM_CPU_OMP_THREADS_BIND`.

Only flags confirmed by the selected runtime feature probe are surfaced to the tuner. A help-text flag is preliminary evidence; a real launch and acceptance run are required for qualification.

### 5.4 SGLang, MLX-LM and LMCache

SGLang and MLX-LM are available through the provider registry for discovery and lifecycle integration according to their capability manifests. SGLang currently exposes CUDA-oriented fit/launch metadata and a small tuning surface (`mem_fraction_static`, tensor parallel size, chunked-prefill size), but it is not registered with the shared tuning adapter registry. MLX-LM has provider discovery/lifecycle code but no shared Speed/Cost tuning adapter. LMCache is an experimental overlay that adds local CPU cache, size and remote URL settings to compatible deployments.

## 6. Declarative configuration, plans and governance

`rift_yaml.py`, `governance.py` and `orchestrator.py` turn configuration into immutable, inspectable actions.

### 6.1 Configuration model

The configuration describes:

- global node and resource settings;
- model/artifact source and local path;
- selected backend/runtime;
- service name, host/port and exposure policy;
- context, concurrency, sampling and launch settings;
- gateway limits and API-key policy;
- monitoring/telemetry policy;
- optional cluster placement and rollout settings.

The parser normalizes paths, defaults and aliases, then validates schema and policy invariants before planning.

### 6.2 Plan generation

`rift plan` produces a plan containing:

- resolved hardware and node target;
- selected exact artifact and source;
- backend/runtime launch specification;
- download/install/temporary-launch/restart/promote actions;
- port and endpoint details;
- predicted fit and warnings;
- configuration fingerprint and provenance;
- required permissions.

The plan is the review boundary. `--json` returns machine-readable output. Simulation/hardware simulation is read-only and cannot pull, install, launch or verify a service.

### 6.3 Apply and action permissions

`apply` executes only approved plan actions. Permissions are explicit and checked before side effects. Typical action categories are:

- download or use an existing cache entry;
- install a provider/runtime;
- launch a temporary or production process;
- stop/restart an existing service;
- promote a verified candidate;
- remove only RIFT-owned rejected temporary artifacts.

An approval envelope can be hashed and associated with an operation. Conformance checks ensure a later operation does not silently add actions outside the reviewed plan.

### 6.4 Supply-chain and provenance controls

Artifact manifests, hashes, source/license metadata and runtime identity are retained in state and evidence. Download sources and gated credentials are policy inputs. RIFT does not infer permission to use a private registry, execute remote code, expose a service publicly or remove shared cache entries from natural-language text.

## 7. Deployment lifecycle and state machine

The standard lifecycle is:

```text
DISCOVER → RECOMMEND → PLAN → APPROVE → APPLY
    → INSTALL/PULL → LAUNCH → HEALTH CHECK
    → READY → MONITOR → BENCHMARK/TUNE
    → PROMOTE or ROLLBACK → STOP/REMOVE
```

The operation store provides idempotency keys, operation links and status transitions. The state store persists desired configuration, services, model identity, runtime identity, launch plans, endpoints, gateway settings and monitoring sessions.

### 7.1 Process ownership and recovery

RIFT tracks more than a PID where the runtime allows it: process creation identity, container ID or WSL process group, deployment revision and operation/run ownership. Recovery stops only owned processes.

On cancellation or controller restart:

1. reconcile actual processes with persisted ownership;
2. stop only owned temporary trials;
3. restore the baseline if promotion was incomplete;
4. verify health and endpoint identity;
5. resume only from a stable checkpoint with valid identity, permission and budget.

A rollback failure has an explicit failure status and cannot be reported as a successful cancellation.

### 7.2 Immutable deployment revisions

Promotions produce an immutable deployment revision/fingerprint. The final launch specification, artifact hash, backend build, runtime mode, template/handler fields, precision and target devices are retained so a rollback can reconstruct the prior service.

## 8. Monitoring, telemetry and operational accounting

`observability.py`, telemetry collectors and the node supervisor provide continuous operational state.

### 8.1 Observed metrics

- service health/readiness and endpoint latency;
- process identity, exit code and restart/recovery events;
- CPU utilization and process seconds;
- RAM and accelerator memory utilization;
- GPU/accelerator power when a collector supports it;
- thermal and pressure signals;
- gateway requests, successes, failures and observed token counts;
- deployment, benchmark, tuning and rollout timelines.

Each measurement carries source, scope, timestamp and coverage where available. Aggregate GPU power is labelled as aggregate device power and may include other workloads sharing the device.

### 8.2 Energy and cost

The Cost profile uses a short-lived sampler isolated from the normal monitoring supervisor. On NVIDIA-capable systems it integrates `nvidia-smi power.draw` samples using trapezoidal integration and records sample count, covered seconds and coverage ratio. GPU-only coverage is labelled GPU energy; CPU-only or partial coverage is not silently promoted to total system energy.

If a valid energy provider is unavailable, Cost is unavailable with an actionable explanation. Memory usage or utilization is not substituted for joules.

### 8.3 Prometheus and retention

The telemetry surface can expose Prometheus-compatible metrics and JSON reports. Retention and report paths are configurable through the runtime root. The gateway maintains request counters and token-usage coverage; unknown token accounting is retained as unknown.

## 9. Shared tuning engine

The shared tuner consists of versioned contracts, a backend tuning-adapter registry, a durable SQLite journal and the `TuningCoordinatorMixin`.

### 9.1 Tuning contract and identity locks

The contract records service, profile, usage mode, model path, context, concurrency, candidate limit, budget, KV-search permission, optional parent workload ID and contract hash.

`DeploymentIdentity` pins:

- model revision and artifact hash;
- tokenizer and chat template;
- backend/build/runtime;
- resolved precision and devices;
- tool/reasoning parser fields where present;
- tensor/pipeline parallel settings and container image where applicable.

Ordinary tuning cannot change model weights, revision, weight quantization, resolved compute dtype, tokenizer/template, sampling policy, required context, offered concurrency, endpoint security or authorized device allocation. KV precision is a separate visible permission and can be disabled. Speculation is permitted only within the existing resource envelope and certified launch mechanism.

### 9.2 Profiles

RIFT currently exposes exactly two optimization profiles:

**Speed** maximizes useful inference performance while retaining quality, TTFT/latency and concurrency gates. Usage is either:

- **interactive:** per-request decode rate and first-response latency;
- **shared:** aggregate useful throughput/goodput under the configured offered concurrency or request rate.

Usage is inferred from deployed service concurrency when not explicitly supplied and displayed for confirmation.

**Cost** minimizes measured joules per successful request for an identical request mix and arrival schedule. Joules per 1,000 output tokens is a secondary view. All performance and quality gates remain active; a lower-energy but slower or less correct candidate is rejected.

### 9.3 Adapter interface

```text
probe(deployment) → capabilities
resolve_configuration(deployment) → effective settings
validate(configuration, identity, requirements, resources) → findings
propose(baseline, observations, search_state, budget) → candidates
build_launch_spec(configuration) → serving launch specification
collect_diagnostics(runtime) → normalized observations
explain(candidate, evidence) → structured explanation
```

The coordinator owns baseline measurement, warmups, candidate scheduling, benchmark requests, correctness gates, acceptance, promotion and rollback. Parameter descriptors carry type, allowed values, dependencies, restart requirement, applicability and explanation; UI controls are rendered from these descriptors.

### 9.4 Search and acceptance algorithm

```text
resolve healthy service and expected deployment revision
resolve tuning adapter and effective baseline
compile immutable tuning request and acceptance policy
validate identity locks, permissions, telemetry and budgets
acquire maintenance lease and device reservation
measure baseline and run baseline correctness gates
generate diverse, validated candidates
for each candidate within candidate/time budget:
    persist intended launch and ownership
    stop previous trial and verify resource release
    launch and verify effective configuration
    warm up, smoke test and measure fixed request recipe
    reject quality, latency, throughput or resource violations
    update feasible set and bottleneck observations
retest baseline and finalists in interleaved order
run held-out acceptance
promote winner through immutable plan/apply path
verify endpoint, or restore baseline
write evidence and release lease
```

The default standalone envelope is up to 24 candidates and approximately 60 minutes, with warmup/repeat/request-count settings supplied by the caller. Candidate identity and measurements are journaled before side effects so a restart can reconcile ownership.

### 9.5 llama.cpp search space

The llama.cpp adapter preserves existing families for GPU layers, device placement, batch/micro-batch, CPU threads, parallel slots, Flash Attention, K/V precision/offload, mmap/mlock, CPU affinity/priority/NUMA, repacking, operation offload, split/tensor placement, polling and safe speculation. Candidate generation is capability-gated against the installed binary and keeps locked identity values intact.

### 9.6 vLLM search space

The vLLM adapter proposes only runtime-confirmed controls across scheduler, memory/KV capacity, prefix caching, KV precision, execution/compilation, attention backend, CPU resources, offload and certified speculation. GPU-only controls cannot leak into CPU launches. KV precision changes require exact runtime support, scaling provenance where needed, long-context checks and capability regression tests.

### 9.7 Correctness gates

`AccuracySuite` is a bounded acceptance floor, not a universal quality proof. New runs use versioned deterministic cases covering required terms, status/finish behavior, structured output, refusal/no-call behavior and baseline-relative response similarity. Candidate quality must remain within configured tolerances. Historical reports with only legacy similarity scores remain readable but are not silently reclassified as measured task accuracy.

Tool capability is an exact deployment property. A declared model or backend feature is not sufficient. Verification must pin artifact, template, parser/handler, backend build, launch flags, runtime and results. Tool tests cover selection, arguments, no-call cases and a multi-turn tool-result continuation where required.

### 9.8 Outcomes

| Outcome | Meaning |
|---|---|
| `VERIFIED` | Fresh acceptance passed and the winner was promoted and endpoint-verified |
| `NO_IMPROVEMENT` | Search completed but no candidate defensibly beat the baseline |
| `BASELINE_INVALID` | Baseline correctness/health gate failed before optimization |
| `INFEASIBLE` | A lower bound or complete admissible search proves the requirement cannot be met in scope |
| `EXHAUSTED` | Budget ended while plausible candidates remain untested |
| `BLOCKED` | Permission, telemetry, credential, runtime or policy prevented progress |
| `FAILED` | Infrastructure failure prevented completion |
| `CANCELLED` | User cancellation completed with cleanup/recovery |

The implementation also returns compatibility statuses such as `permission_required`, `unavailable`, `preview`, and `blocked` in API/CLI envelopes.

## 10. Benchmarking, evaluation and evidence

### 10.1 Common benchmark runner

The benchmark runner fixes prompt text, sampling parameters, output limits, cache condition and offered load across comparisons. It supports sequential interactive requests, fixed-concurrency tests, request-rate tests, short/mixed/near-capacity prompts, warm-prefix and unique-prefix conditions, and separate warm-start versus cold-start reporting.

Metrics are kept distinct:

- decode throughput (tokens/s over the measurable decode interval);
- total response throughput;
- aggregate/shared goodput;
- TTFT and total latency distributions;
- completion/failure counts;
- resource and energy observations.

An SSE chunk is not counted as a token. If exact token timing is unavailable, the report names the measurable interval and marks token-level ITL unavailable.

### 10.2 Acceptance discipline

Final acceptance uses repeated independent measurement windows, warmups, held-out confirmation, and confidence bounds where sufficient samples exist. Critical percentile claims require enough completed requests; otherwise the report is `inconclusive`. The baseline and finalists are remeasured in interleaved order to reduce drift.

### 10.3 Evidence report model

`EvidenceReport` and related evidence sources retain:

- original request/contract and interpretation;
- exact model/artifact/backend/runtime identity;
- baseline and candidate effective settings, including unchanged settings;
- every requirement with measured result, unit, uncertainty and verdict;
- candidate history and rejection reasons;
- quality/tool-case outcomes;
- compile/download/start/tune/acceptance time;
- endpoint, promotion and rollback state;
- measurement scope, exclusions and limitations;
- report hash and artifact links.

Reports can be rendered as JSON, Markdown summaries and portable HTML/SVG visualizations. Quantitative prose is generated from validated measurements; any optional narrative layer is constrained to those facts and cannot invent causal attribution. Unless ablation tests exist, wording should be “configuration improved throughput,” not “parameter X caused the improvement.”

Current repository evidence includes real llama.cpp 3B/7B Speed/Cost runs and a focused 3B promotion where Flash Attention changed from `off` to `auto`; the reported improvement was approximately 4.6% with quality score 1.0. The broader matrix correctly recorded no improvement under its reliability gate. vLLM physical qualification remains blocked when a compatible runtime/model is not locally available or downloads cannot complete.

## 11. Gateway, security and governance

### 11.1 OpenAI-compatible gateway

`gateway.py` provides a policy boundary for local services:

- OpenAI-compatible request/response forwarding;
- API-key creation, rotation and revocation;
- per-service request timeout;
- concurrent-request and burst controls;
- requests-per-minute limits;
- prompt, completion and total-token ceilings;
- exposure host policy (local versus broader binding);
- request success/failure/token counters;
- gateway metrics persistence.

The gateway is intentionally separate from backend launch flags and does not grant model-level tool execution.

### 11.2 Node identity and mTLS

Node enrollment supports pairing and certificate issuance/rotation. The mesh controller maintains a local CA/bootstrap material, node fingerprints, participation state, capability records and revocation. Remote node operations use explicit grants and transport identity; discovery does not imply authorization.

### 11.3 Data handling

RIFT keeps control-plane state and evidence on the local runtime root. Public exports should omit sensitive prompts and device identifiers by default. Hashes prove bundle integrity, not independent external verification. Natural-language workload compiler foundations are intended to remain offline; model-generated text cannot grant permissions.

## 12. Cluster, rollout and Elastic Intelligence Mesh

### 12.1 Cluster controller

`cluster.py` plans replicas against node hardware, backend compatibility, memory fit and requested resources. It supports deterministic emulation, placement summaries, unscheduled-replica reporting, apply gates, service status, benchmark/tune simulation, failure injection, node drain/restore, rollout planning and rollout gates.

Remote apply requires the supported RIFT agent transport; SSH/PowerShell are discovery/bootstrap transports rather than an implicit remote-serving authority.

### 12.2 Rollouts and failure handling

`rollout.py`, `reconciliation.py` and cluster recovery preserve desired state, deployment revisions and capacity constraints. Existing healthy services are not replaced until a new revision passes its gates where coexistence is possible. Rollback is explicit and verified.

### 12.3 Mesh

The `mesh/` package provides controller-side primitives for:

- passive mDNS discovery;
- consent-gated private-subnet, USB and ADB bootstrap;
- enrollment and CA-issued mTLS identities;
- topology and link evidence;
- model/service catalogs;
- policy-aware routing and short-lived route leases;
- service groups, scaling and failover;
- gateway admission and operation authority;
- node telemetry, capability updates and revocation;
- deterministic mesh emulation.

Physical heterogeneous-node acceptance is a separate qualification boundary; emulated topology results must not be presented as physical proof.

## 13. Workload-driven deployment foundation

The future workload flow is architecturally planned but not exposed as a complete user feature.

`workload_contracts.py` provides offline deterministic primitives for a versioned workload contract, field provenance, compilation, validation and hashing. The intended flow is:

```text
describe/import workload
  → normalize and extract explicit quantities/policies
  → semantic classification with a pinned local compiler pack
  → deterministic merge and conflict detection
  → editable review with field-level provenance
  → explicit budgets and permissions
  → approval of contract/envelope hashes
  → candidate search and provisional deployment
  → shared Speed/Cost tuning where needed
  → held-out acceptance and promotion
  → evidence report
```

This flow must not be described as available merely because its contracts exist. Before release it needs candidate-search/evaluation adapters, permission-envelope conformance, durable workload journaling, compiler corpus qualification, setup/UI/CLI integration, and real hardware acceptance. Unsupported requirements must remain visible rather than being silently dropped.

## 14. CLI product surface

The CLI is designed for both guided use and automation. Common commands include:

```text
rift discover
rift status
rift model recommend [options]
rift model pull [options]
rift model inspect [options]
rift model verify [options]
rift plan [options]
rift apply [options]
rift stop [options]
rift service benchmark --service NAME
rift service tune --service NAME --profile speed|cost
rift tune status RUN_ID
rift tune watch RUN_ID
rift tune report RUN_ID
rift tune cancel RUN_ID
rift tune apply RUN_ID
rift tune rollback RUN_ID
rift cluster discover|check|plan|apply|monitor|benchmark|tune|fault|recover|destroy
```

Tuning supports shared usage selection (`interactive` or `shared`), candidate/time limits, warmups/repeats, request recipe, acceptance tolerances, KV precision permission, speculation control, restart permission, preview/report-only mode and JSON output. Arbitrary backend flags are not appended unchecked; descriptors validate them before launch.

Non-interactive workflows must supply exact approvals/permissions where required. Exit codes distinguish verified, failed, approval-required, infeasible, exhausted and cancelled outcomes.

## 15. UI and dashboard product surface

The dashboard is served by `dashboard.py` and the bundled static/Rich assets. It provides live technical views for:

- setup and discovery;
- nodes and hardware;
- models and artifacts;
- deployments and endpoints;
- operations and event timelines;
- settings and gateway policy;
- tuning, run history, preview, live progress, apply/rollback and evidence.

The tuning page is backend-neutral. It shows the selected service and backend identity, Speed/Cost profiles, usage mode, locked model/precision notice, acceptance requirements, advanced backend-generated controls, candidate/time limits, maintenance behavior and current run state. Selecting another service refreshes the capability descriptor and clears incompatible overrides.

The workload branch, once enabled, should be a branch in the existing guided setup rather than a separate product: describe/import, compile, review, limits/permissions, approve, autonomous search, evidence and endpoint.

## 16. HTTP API surface

`server.py` exposes the controller API and proxies dashboard requests. The versioned API includes resources for:

- discovery, hardware, nodes and services;
- models, artifacts, recommendations and plans;
- deployments, operations, apply, stop, rollback and reconciliation;
- benchmarks, evaluation suites, evidence and reports;
- telemetry, sessions, reports and Prometheus output;
- gateway status, API-key lifecycle and metrics;
- cluster planning, apply, monitoring, rollout and fault recovery;
- mesh enrollment, nodes, topology, catalogs, services, routing, gateway admission and operation authorities;
- tuning profiles, capabilities, runs, events and reports.

The tuning routes are:

```text
GET  /api/rift/v2/tuning/profiles
GET  /api/rift/v2/tuning/capabilities?service=NAME
GET  /api/rift/v2/tuning/runs
POST /api/rift/v2/tuning/runs
GET  /api/rift/v2/tuning/runs/{id}
GET  /api/rift/v2/tuning/runs/{id}/events
GET  /api/rift/v2/tuning/runs/{id}/report
```

Legacy routes and aliases remain for compatibility. OpenAPI is maintained in `docs/reference/rift-controller.openapi.yaml`. Future workload routes are a planned additive surface and should not be assumed enabled until the controller state machine is connected.

## 17. Persistence and runtime layout

The runtime root is configured. Repository-local runs commonly use `.rift` or `.rift-runtime`; installed deployments can use the platform-specific `RIFT_HOME` default or an explicit `RIFT_HOME`. Important state includes:

```text
.rift-runtime/
  state.json                       desired state and deployed services
  operations.db / operations/       idempotent operation journal and events
  tuning.db                         tuning runs, events and maintenance leases
  telemetry/                        sessions, samples and reports
  recommendations/                 durable recommendation runs/evidence
  reports/                          benchmark, tuning and deployment reports
  artifacts/ / cache/              RIFT-owned downloaded/verified artifacts
  gateway/                          API keys and gateway metrics
  mesh/                             controller identity, topology and enrollments
  cluster/                          cluster plan, allocations and rollout state
```

Exact filenames can vary by release/configuration. State writers use crash-safe patterns and preserve provenance. Shared caches and artifacts used by active services are not deleted by rejected-trial cleanup.

## 18. Failure semantics and operator safety

RIFT distinguishes:

- structural incompatibility (format/backend/OS/accelerator);
- missing runtime/install/credential;
- disk or memory fit failure;
- startup timeout or health failure;
- benchmark/correctness regression;
- insufficient telemetry or confidence;
- budget exhaustion;
- missing permission/policy authorization;
- infrastructure failure and cancellation;
- rollback failure.

The product must not call a bounded search globally impossible. `INFEASIBLE` is evidence-backed within the declared scope; `EXHAUSTED` means the search ended before a conclusion; `BLOCKED` means authorization or prerequisite state prevented progress.

## 19. Current limitations and non-goals

1. vLLM is not yet physically qualified for every advertised CUDA, ROCm, XPU or CPU combination.
2. SGLang and MLX-LM provider presence does not imply shared tuning support.
3. Physical multi-node heterogeneous deployment is not established by the emulator.
4. Workload natural-language deployment is a foundation, not an exposed autonomous flow.
5. Ordinary tuning does not change model quantization, prune weights, sparsify a dense model, convert artifacts or train a model.
6. Cost claims require valid, appropriately scoped energy telemetry.
7. A bounded correctness suite cannot prove universal model quality.
8. Tool calling is certified per exact artifact/template/parser/backend/runtime configuration, not by model name alone.
9. Runtime upgrades, topology changes and new draft artifacts are separately reviewed deployment operations.
10. A healthy baseline may legitimately remain the winner when no candidate passes the improvement/reliability gate.

## 20. Verification map for maintainers

The principal implementation modules are:

| Concern | Source area |
|---|---|
| Product facade and public orchestration | `python/rift/rift.py`, `python/rift/orchestrator.py` |
| HTTP controller | `python/rift/server.py` |
| CLI | `python/rift/cli/` |
| Hardware profile | `python/rift/system_profile.py`, telemetry collectors |
| State and operations | `python/rift/state_store.py`, `python/rift/operations.py` |
| Artifacts and Hub | `python/rift/adapters/artifacts.py`, `python/rift/artifacts.py`, `python/rift/hf_hub.py` |
| Providers | `python/rift/providers/` |
| Shared tuning | `python/rift/tuning_contracts.py`, `tuning_adapters.py`, `tuning_coordinator.py`, `tuning_engine.py` |
| Benchmark/evaluation | `python/rift/benchmarking.py`, `benchmark_suite.py`, `benchmark_catalog.py`, `evaluation.py`, `tuning_benchmark.py`, `tuning_accuracy.py` |
| Evidence | `python/rift/evidence.py`, `evidence_sources.py` |
| Monitoring/accounting | `python/rift/observability.py`, telemetry packages |
| Gateway | `python/rift/gateway.py` |
| Cluster/rollout | `python/rift/cluster.py`, `rollout.py`, `reconciliation.py` |
| Node enrollment/transport | `node_agent.py`, `node_bootstrap.py`, `node_enrollment.py`, `transport.py` |
| Elastic Intelligence Mesh | `python/rift/mesh/` |
| Workload foundation | `python/rift/workload_contracts.py` |
| UI | `ui/src/`, `python/rift/web/static/`, `python/rift/dashboard.py` |
| API contract | `docs/reference/rift-controller.openapi.yaml` |

### Recommended verification commands

```text
python -m pytest tests/python
python -m pytest tests/python/tuning_adapter_tests.py tests/python/profiled_tuning_tests.py
rift discover --json
rift plan --json
rift service tune --service NAME --profile speed --dry-run --json
rift service tune --service NAME --profile cost --dry-run --json
```

Use a real installed backend/runtime and a non-toy model for physical qualification. A simulation, help probe, or mocked benchmark is evidence of control-plane behavior only.

## 21. Product roadmap boundaries

The architecture intentionally leaves room for:

- certified shared tuning adapters for SGLang and MLX-LM;
- broader vLLM runtime/hardware qualification;
- workload compiler pack qualification and setup integration;
- workload candidate search, provisional deployments and parent/child tuning runs;
- structured output, tool and domain-specific acceptance suites;
- multi-device tensor/pipeline/data/expert parallelism optimization;
- physical heterogeneous-node mesh acceptance;
- richer report exports and measured human-baseline comparisons.

These are additive capabilities. They should continue to use the existing service identity, operation journal, monitoring, gateway, tuning coordinator and evidence model rather than introducing backend- or workflow-specific parallel systems.

## 22. Executive summary

RIFT is currently a local-first inference operations platform with a strong control-plane core: hardware-aware planning, exact artifact handling, permission-gated deployment, backend-specific serving lifecycle, monitoring, gateway policy, cluster/mesh primitives, and a shared Speed/Cost tuning engine. llama.cpp is the most mature locally verified path. vLLM has a real multi-environment provider and tuning descriptor path but still requires runtime/hardware qualification for a definitive production claim. The workload compiler and autonomous deployment concept is represented in contracts and architecture, not yet as an enabled end-user flow.

That distinction is central to RIFT’s evidence model: every result should identify what was measured, where, with which exact model/runtime/configuration, under which permissions and budgets, and what remains unknown.
