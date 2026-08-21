# RIFT Implementation Roadmap

## Purpose

This document is the working backlog for taking RIFT from a capable local LLM
deployment tool to a trustworthy LLM-serving control plane.

RIFT's product promise is deliberately narrow and useful:

```text
Discover hardware -> choose a deployable model artifact -> choose a backend ->
generate an explainable plan -> deploy -> benchmark -> monitor -> tune ->
recover.
```

RIFT is an orchestrator. It should make backend-specific serving predictable,
observable, and reproducible; it should not pretend that every model format or
backend has equal support.

## Current Baseline

The local workstation workflow is substantially implemented:

- local hardware and backend discovery
- bounded Hugging Face, private-source, and local-folder model discovery
- artifact-aware recommendations, including GGUF quant-file selection
- disk-aware pull preflight and user-approved downloads
- generated YAML/config, read-only plan, apply, state, and reports
- verified llama.cpp local deployment path
- benchmark reports, health checks, logs, supervised restart foundations, and
  safe local tuning
- an OpenAI-compatible gateway with basic limits and fallback routing
- a deterministic/emulated cluster scheduler for control-plane testing

The important boundary is that RIFT is not yet ready to become the single
production control plane for all LLM workloads. Real remote cluster transport,
security, durable observability, hardened recovery, and evidence-based model
quality selection remain unfinished.

## Implementation Snapshot - 2026-07-12

The roadmap is now implemented far enough to operate and inspect through the
live control API and dashboard, but not every production acceptance gate can be
closed on one Windows workstation. Detailed evidence is tracked in
[`status.md`](status.md).

- Implemented and locally verified: hardware/capacity analysis, bounded disk
  calibration, evidence provenance, artifact manifests and hashes, provider
  lifecycle contracts, llama.cpp serving, fixed-suite benchmarking, bounded
  tuning with regression gates, API-key lifecycle, local gateway limits,
  supervision, incidents, redacted logs, Prometheus export, migrations,
  diagnostics, governance policy, and the live operator dashboard.
- Implemented and deterministically emulated: resource-safe cluster placement,
  replica spreading, node/process failure recovery, reservations, canary and
  blue/green rollout plans, and readiness/performance promotion gates.
- Implemented but awaiting real infrastructure acceptance: SSH and PowerShell
  remote discovery, vLLM and SGLang platform gates, and LMCache-aware launch
  overlays.
- Still required for a production cluster claim: two real enrolled nodes,
  credential/host-key operational hardening, replicated controller state,
  distributed limits, real canary traffic, Linux provider acceptance, packaged
  operator UI assets, and CI/release installers for Windows/Linux/WSL.

## Rollout Standard

RIFT can be called usable for one workstation when it can repeat this sequence
without manual backend knowledge:

```text
discover -> recommend exact artifact -> plan -> approved pull/install/launch
-> successful request -> benchmark -> tune -> status -> stop -> recover
```

RIFT can be called production-ready for a small cluster only when the same
sequence works across real nodes, survives routine failures, leaves an audit
trail, and never makes unsafe changes without explicit authorization.

## Priority 0: Trust And Correctness

These items gate wider adoption. Do them before adding broad feature surface.

### 1. Recommendation Evidence Engine

Replace metadata-heavy "quality" rankings with an evidence ladder.

- Maintain a curated, versioned benchmark registry by task, model revision,
  quantization, and license.
- Run a local smoke-evaluation suite after pull for instruction following,
  structured output, coding, and safety checks where applicable.
- Distinguish estimated quality, published evidence, and locally verified
  quality in every recommendation and report.
- Treat likes, downloads, and tags as weak popularity signals only.
- Add an explicit confidence score with the evidence used to derive it.

Acceptance: a recommendation explains why it is ranked and never labels a
metadata-only score as measured accuracy.

### 2. Measurement-Grade Hardware Analysis

Turn capacity estimates into an honest hardware profile.

- Detect CPU model, physical/logical cores, RAM total/free, GPU total/free,
  storage type/free space, OS, CUDA/driver, power source, and thermal policy
  where the platform exposes them.
- Separate total capacity, current free capacity, RIFT-managed reclaimable
  capacity, and clean-boot planning capacity.
- Measure sequential disk bandwidth on the selected model volume.
- Measure practical H2D bandwidth where CUDA is present.
- Record active RIFT services separately from unrelated resource pressure.
- Add a short calibration command and make stale calibration visible.

Acceptance: a plan reports the measurements and assumptions used for its RAM,
VRAM, disk, context, and throughput estimates.

### 3. Artifact Intelligence

Make exact model-file selection dependable across formats.

- Build format-specific selectors for GGUF, GPTQ, AWQ, and SafeTensors.
- Recognize sharded artifacts, tokenizer/config dependencies, model revisions,
  and required auxiliary files.
- Estimate final download size from exact files, not only repository metadata.
- Validate checksums, resumable downloads, incomplete snapshots, and local
  cache integrity.
- Generate clear license, gated-access, and model-card provenance warnings.

Acceptance: `rift plan` identifies the exact artifact set, download bytes,
disk reserve, backend compatibility, and validation result before pulling.

## Priority 1: Reliable Local Serving

### 4. Provider Contract Hardening

Formalize a single adapter contract for every backend.

- Required adapter lifecycle: detect, install-plan, install, model-fit,
  plan-launch, launch, readiness, health, benchmark, tune, stop, recover.
- Add capability declarations for OS, GPU/CUDA, formats, multi-GPU, API shape,
  streaming, and tuning knobs.
- Require a fake-backend integration suite before an adapter is advertised as
  supported.
- Keep unsupported combinations visible as external-backend advice, never as
  fake readiness.

Acceptance: every provider has a tested capability matrix and produces
actionable errors for unsupported models or machines.

### 5. llama.cpp Production Gate

Finish the first provider to a high standard before relying on more providers.

- Verify official install paths on Windows, Linux, and WSL where supported.
- Test GGUF selection, download, launch, OpenAI endpoint health, streaming,
  stop, crash recovery, and log capture against a real backend binary.
- Benchmark cold start, prompt evaluation, decoding, memory use, and long
  context behavior.
- Tune only bounded, safe flags and preserve the last-known-good configuration.
- Add port collision, corrupted model, missing runtime, out-of-memory, and
  hung-server recovery tests.

Acceptance: RIFT can reliably operate a real llama.cpp service on the target
workstation over repeated deploy/stop/recover cycles.

### 6. Benchmark And Tuning Integrity

Make optimization useful rather than ceremonial.

- Use a fixed prompt suite, warmups, repetitions, median/p95 reporting, and a
  clear cold-versus-warm cache label.
- Record backend/model revision, artifact, context, concurrency, host state,
  temperature/power evidence where available, and exact launch settings.
- Add regression thresholds and rollback if the selected candidate is worse.
- Keep tuning transactions isolated from user configurations and require an
  explicit write-back decision.

Acceptance: two runs can be compared fairly, and a tuning result is
reproducible from its stored report.

## Priority 2: Secure Operations

### 7. Gateway And Tenant Controls

Harden the user-facing endpoint before multi-user use.

- Add API-key management, secret-safe storage, key rotation, per-key quotas,
  request/token/concurrency limits, request size limits, and timeouts.
- Add request IDs, structured access logs, redaction policy, and audit events.
- Add configurable local-only binding by default, TLS termination guidance,
  CORS policy, and explicit public-exposure warnings.
- Implement queueing/backpressure and overload responses rather than allowing
  uncontrolled backend saturation.

Acceptance: an operator can safely expose one RIFT-managed service to a small
trusted team and explain who used it and when.

### 8. Service Supervision And Disaster Recovery

Extend the current restart foundation into a tested policy engine.

- Persist desired state, observed state, health history, incidents, and
  last-known-good launch plans durably.
- Support readiness versus liveness checks, startup grace, exponential backoff,
  bounded restart budgets, degraded state, and operator acknowledgement.
- Add repair/retry for incomplete model pulls and disk-space failures.
- Add configurable fallback: alternate port, smaller artifact, alternate
  backend, or rollback to a known-good configuration.
- Produce incident reports containing timeline, log tail, resource snapshots,
  attempted recovery, and final status.

Acceptance: intentional process kill, backend health failure, port conflict,
and incomplete download each result in predictable state and a readable
incident report.

### 9. Observability And Data Retention

- Export structured metrics in a documented format (Prometheus/OpenTelemetry
  are the likely interoperability targets).
- Capture service status, resource usage, queue depth, request latency,
  throughput, error rate, restart count, and model/backend/version labels.
- Add retention controls and privacy-aware log redaction.
- Provide report history and a machine-readable operation timeline.

Acceptance: an operator can answer "what changed, when did it degrade, and
why?" without manually reconstructing logs.

## Priority 3: Real Cluster Control Plane

### 10. Remote Node Transport

Replace emulated nodes with real, permissioned remote execution.

- Begin with agentless SSH and Windows PowerShell remoting.
- Add node authentication, host-key/credential handling, remote capability
  discovery, and explicit remote-action confirmation.
- Design an optional RIFT node agent only when agentless transport becomes too
  limiting.
- Keep controller state separate from node-local state and survive controller
  restart.

Acceptance: RIFT can discover, plan, apply, benchmark, and destroy one service
on two real heterogeneous nodes without manual remote shell work.

### 11. Scheduler And Placement Correctness

- Use actual node capacity, current reservations, model cache locality,
  backend capability, disk space, network reachability, and policy constraints.
- Add anti-affinity, replica spreading, placement locks, and clear rejected
  node explanations.
- Introduce resource reservations and release them only after observed stop.
- Support deliberate model replication and artifact distribution planning.

Acceptance: placement is deterministic, explainable, resource-safe, and
reconciles drift between desired and observed state.

### 12. Cluster Recovery And Rollout Safety

- Add node-loss detection, replica rescheduling, disruption budgets, and
  capacity-aware failover.
- Add blue/green and canary rollout with benchmark/readiness promotion gates.
- Add rollback on health or performance regression.
- Keep distributed rate limits and service state correct under partial failure.

Acceptance: simulated node loss or bad rollout preserves an available endpoint
when capacity exists and produces a complete incident/rollback record.

## Priority 4: Backend Breadth

Add providers sequentially. Do not advertise a provider as production-ready
until it passes the same lifecycle gate as llama.cpp.

### 13. vLLM Adapter

- Target CUDA SafeTensors, AWQ, and GPTQ paths where vLLM actually supports the
  model and platform.
- Make Windows/WSL/Linux limitations explicit.
- Support model fit, launch planning, health, benchmark, tuning, stop, and
  recovery.

### 14. SGLang Adapter

- Target structured generation, prefix-heavy workloads, and supported CUDA
  deployments.
- Measure when it beats vLLM/llama.cpp rather than assuming it does.

### 15. Cache and Specialized Overlays

- Add LMCache or equivalent only when the workload needs prefix reuse, long
  context, or multi-node cache coordination.
- Treat TensorRT-LLM, Ollama, and other providers as future adapters with the
  same verification contract.

Acceptance for each: detection, install plan, launch, health, benchmark,
tuning, recovery, documentation, and genuine end-to-end verification.

## Priority 5: Product Experience And Governance

### 16. Clean Operator Interface

The old UI should remain superseded until a purpose-built operator interface is
ready. The UI must consume the control API rather than reimplement logic.

Required operator views:

- overview and service health
- discovery and recommendation evidence
- YAML generation and plan diff
- apply progress and approval states
- services, endpoints, logs, and recovery controls
- benchmarks, tuning history, and configuration comparison
- cluster inventory, placement decisions, and incidents

Acceptance: raw YAML/JSON remains available, but the normal workflow is
understandable without reading backend command lines.

### 17. Governance, Supply Chain, And Compliance

- Record artifact origin, revision, hashes, license, and gated-access status.
- Add optional allow/deny policies for model sources and backend versions.
- Generate an exportable deployment manifest and audit trail.
- Document security boundaries, data handling, telemetry, and third-party
  backend licenses.

Acceptance: an enterprise can review what was deployed, from where, with which
permissions and versions.

### 18. Packaging And Release Engineering

- Produce repeatable Windows, Linux, and WSL installation paths.
- Add versioned migration for state/config schemas.
- Publish a compatibility matrix and supported-backend policy.
- Add CI for unit, fake-backend, integration, regression, and packaging tests.
- Create a reproducible demo environment and troubleshooting bundle.

Acceptance: a new user can install RIFT, run the local workflow, and submit a
useful diagnostic bundle if it fails.

## Recommended Delivery Sequence

1. Measurement-grade hardware analysis and artifact intelligence.
2. llama.cpp production gate and benchmark/tuning integrity.
3. Gateway security, service supervision, incidents, and observability.
4. Real remote-node transport and two-node cluster verification.
5. Scheduler, failover, and safe rollout policies.
6. vLLM adapter, then SGLang, each through the provider gate.
7. Operator UI, governance, packaging, and a public release candidate.

This ordering makes the first open-source release valuable early while avoiding
the trap of presenting an unverified multi-backend cluster manager as finished.

## Release Gates

### Community Preview

- Verified one-machine llama.cpp workflow.
- Clear recommendation confidence and exact artifact plan.
- Explicit permissions for install, download, launch, stop, and deletion.
- Stable benchmark/report format and honest limitations.

### Local Production Candidate

- Hardened supervisor, incident reports, rate limits, authenticated gateway,
  regression-safe tuning, and reproducible packaging.
- Repeated real-workstation recovery testing passes.

### Cluster Beta

- Real two-node remote transport, placement, reconciliation, node-loss
  recovery, and observability pass end-to-end tests.
- Remote credential and network exposure guidance is documented.

### General Availability

- At least two providers meet the full adapter gate on their supported
  platforms.
- Security, support, upgrade/migration, compatibility, and runbook standards
  are documented and tested.
- Recommendations clearly distinguish verified results from estimates.

## Non-Negotiable Product Rules

- Never silently download, install, expose a port, kill a process, or modify a
  user's YAML.
- Never convert weak metadata into a claim of benchmarked quality or safety.
- Never claim a backend/model/platform is supported without an adapter gate.
- Keep RIFT's own runtime experimental until it has independent performance and
  correctness validation.
- Prefer a small number of complete, reliable workflows over a large list of
  half-working commands.

## Definition Of "Ready To Roll Out"

RIFT is ready for a meaningful open-source rollout when a user with a normal
workstation can install it, receive an explainable exact-artifact
recommendation, approve a plan, launch a real backend, make an OpenAI-compatible
request, benchmark and tune the result, inspect health/logs, and recover from a
controlled failure without learning backend internals.

RIFT is ready to be trusted as Terraform/Kubernetes for LLM servers only after
the equivalent lifecycle has been demonstrated on real multi-node deployments
with secure remote access, durable state, observability, and tested recovery.
