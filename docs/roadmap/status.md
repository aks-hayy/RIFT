# RIFT Roadmap Verification Status

## Current Release-Hardening Increment: 1.3.0

This increment moves the public product boundary to a pure-Python,
cross-platform RIFT control plane. The active package is `rift`; the old
SpoolStream native namespace is historical and is not a runtime dependency.

Verified in the current checkout:

- PEP 517 wheel builds without CUDA, CMake, Ninja, MSVC, or Node.js.
- The wheel contains the `rift` package and bundled dashboard assets, with no
  `spoolstream` package entries.
- `rift init`, `rift discover`, `rift model recommend`, `rift plan`, `rift
  apply`, `rift status`, `rift doctor`, `rift start`, and `rift stop` are the
  canonical operator workflow.
- Runtime state has a platform-aware `RIFT_HOME`; legacy checkout state and
  models have a previewed, backup-first migration path.
- State-changing control API requests persist request/operation IDs and replay
  completed results on retry.
- The bundled dashboard is served from an installed wheel and consumes live
  controller routes with explicit unavailable/empty states.
- A bounded reconciliation loop is available to the controller dashboard;
  automatic recovery remains opt-in through `RIFT_AUTO_RECOVER=1`.
- All active Python contract tests pass in isolated temporary `RIFT_HOME`
  directories.

Not yet claimed by this increment: physical multi-node reliability, controller
HA, mTLS rotation in production, real vLLM/SGLang/MLX acceptance, or a native
RIFT inference engine. Those remain separately labelled below.

Updated: 2026-08-18

This ledger distinguishes source-code completeness from real acceptance. A
feature is not called production-ready because its interface exists or because
an emulated test passes.

## Status Vocabulary

- `VERIFIED_LOCAL`: exercised end to end on this RTX 4060 Windows workstation.
- `VERIFIED_TEST`: covered by deterministic unit or fake-backend integration
  tests.
- `EMULATED`: cluster behavior is deterministic, but no remote process ran.
- `VERIFIED_STATIC`: build or manifest checks passed, but the target runtime or
  device was not available for physical execution.
- `IMPLEMENTED_UNVERIFIED`: code and permission gates exist; target hardware or
  platform acceptance is still required.
- `PENDING`: material product work remains.

## Roadmap Matrix

| Roadmap item | Status | Current evidence | Remaining gate |
| --- | --- | --- | --- |
| 1. Recommendation evidence | `VERIFIED_TEST` | Typed signed benchmark records preserve source, task, benchmark family, metric, normalization, revision, artifact relation, confidence, freshness, and claim boundary. R20 adds Arena, EvalPlus, LiveBench, BigCodeBench provenance, diversified live Hub search, separate VRAM residency scoring, and a 51-profile calibration harness. Published evidence contributes only to quality; local verification remains separate. | Ship and maintain a substantial curated evaluation registry; broaden local task evaluations and run a permissioned finalist tournament. |
| 2. Hardware analysis | `VERIFIED_LOCAL` | CPU, RAM, GPU/VRAM, disk capacity, pressure, thermal/power telemetry, RIFT-managed services, fingerprint, disk calibration, and timed pinned-memory CUDA H2D calibration are live. The latest local H2D sample measured 11.43 GB/s. | Improve storage media detection and collect comparable calibration evidence across supported platforms. |
| 3. Artifact intelligence | `VERIFIED_TEST` | GGUF, dense/sharded SafeTensors, AWQ, GPTQ, FP8, EXL2, and MLX adapters resolve exact dependencies, shard completeness, multimodal files, byte counts, revisions, hashes, and resource estimates. | Expand physical-repository fixtures and signed publisher manifests. |
| 4. Provider contract | `VERIFIED_TEST` | Dynamic entry points, API negotiation, conflicts, disable policy, diagnostics, runtime feature probes, and shared backend/artifact conformance gates pass. | Each provider still needs its own real physical-platform acceptance. |
| 5. llama.cpp gate | `VERIFIED_LOCAL` | Official local binary detected; GGUF launch, health, generation, benchmark, tuning, stop, and controlled recovery have run on this workstation. | Repeat release-cycle tests on Linux, macOS, WSL, port conflict, corrupt model, and long-context/OOM cases. |
| 6. Benchmark/tuning integrity | `VERIFIED_LOCAL` | Fixed prompt suite, warmups, repetitions, median/p95, cache labels, reproducibility metadata, regression gate, rollback target, and isolated optimized config exist. | Multi-objective SLO tuning and canary traffic on a multi-replica real service. |
| 7. Gateway/tenant controls | `VERIFIED_TEST` | Hash-only API-key persistence, create/revoke/rotate, request IDs, structured redacted logs, CORS, local bind, bounded request/token/concurrency/rate limits, and overload responses exist. | Shared/distributed counters, exact backend tokenizer accounting, TLS automation, and external security review. |
| 8. Supervision/recovery | `VERIFIED_LOCAL` | Desired/observed state, liveness/readiness, startup grace, bounded restarts, exponential backoff, incidents, last-known-good rollback, and operator-gated recovery exist. Authoritative controller state now uses SQLite WAL with a JSON compatibility mirror; cluster state uses the same store. | Persistent OS service/agent, incomplete-pull repair acceptance, alternate-artifact failover, and repeated soak testing. |
| 9. Observability | `VERIFIED_TEST` | Structured timeline, redaction, retention pruning, logs, snapshots, reports, and Prometheus text export exist. | OpenTelemetry export, continuous per-process RAM/VRAM attribution, and remote metrics aggregation. |
| 10. Remote transport | `IMPLEMENTED_UNVERIFIED` | SSH and PowerShell remoting discovery paths validate hosts, require explicit remote permission, execute bounded probes, and parse structured results. | Real credentials, host-key operations, and two heterogeneous nodes must pass discover/apply/benchmark/destroy. |
| 11. Scheduler/placement | `EMULATED` | A 50-node heterogeneous test covers manifest-driven backends, capacity, reservations, disk, reachability, cache locality, replica spread, and rejected-node explanations. | Reconcile the same decisions against real remote node state and artifact distribution. |
| 12. Recovery/rollouts | `EMULATED` | Process/node/partition recovery, reservation movement, recreate/canary/blue-green plans, and readiness/performance gates exist. | Real traffic drain, disruption budgets, failover endpoint continuity, and rollback under a physical network partition. |
| 13. vLLM | `IMPLEMENTED_UNVERIFIED` | Full provider contract, Linux/WSL platform advice, install/launch/health/benchmark/tuning plans, and fake-backend coverage exist. | Real Linux/WSL CUDA acceptance with SafeTensors, AWQ, and GPTQ artifacts. |
| 14. SGLang | `IMPLEMENTED_UNVERIFIED` | Full provider contract and explicit platform gate exist. | Real Linux CUDA structured/prefix workload comparison and lifecycle acceptance. |
| 14a. MLX-LM | `IMPLEMENTED_UNVERIFIED` | Full provider contract, isolated install, Apple hardware gate, OpenAI health/benchmark, tuning, and loopback security gate exist. | Real Apple Silicon lifecycle and performance acceptance. |
| 15. LMCache overlay | `IMPLEMENTED_UNVERIFIED` | Overlay detection, config planning, launch, health, benchmark, and tuning contract exist. | Demonstrate measurable benefit over baseline vLLM for a prefix/long-context workload. |
| 16. Operator interface | `VERIFIED_LOCAL` | The TanStack dashboard consumes the live control API across all operator views. Nitro proxies the API in development and production. Recursive source discovery, explicit root override, readiness checks, detached launch with persisted logs, desktop layout, and 390 px no-overflow layout are verified. | Package production UI assets into release artifacts and add browser E2E CI. |
| 17. Governance/supply chain | `VERIFIED_TEST` | Source/license/backend/gated/hash policies, artifact provenance, deployment export, audit timeline, diagnostics redaction, signed evidence policy, direct dependency inventory, and release audit exist. | Enterprise policy bundles, generated SBOM, and legal review for each distributed model/backend combination. |
| 18. Packaging/release | `VERIFIED_TEST` | State/config migrations, compatibility gates, diagnostic ZIP, PEP 517 native wheel, canonical frontend source, direct dependency notices, and release audit work locally. | Repeatable public installers, packaged dashboard assets, CI matrix, upgrade tests, and signed releases remain. |
| 19. Adapter API V2 | `VERIFIED_TEST` | Backend/artifact/converter entry points, persisted recommendation/verification runs, compatibility APIs, and permission-gated conversion host are documented and tested. | Publish an external sample adapter package and run compatibility CI against it. |
| 20. mTLS node agent | `VERIFIED_TEST` | TLS 1.2+, client-certificate verification, monotonic desired state, idempotency, reconciliation, and node-side permissions are tested. | Provision real PKI and complete three-node physical acceptance. |
| 21. Mesh discovery | `VERIFIED_TEST` | Transport-neutral sightings, TTL expiry, deduplication, provider diagnostics, passive mDNS, consented private subnet, USB-network, ADB, mass-storage, and TLS-fingerprint binding have deterministic coverage. mDNS and ADB are registered by default. | Wire consent/configuration for every provider into the controller UI and pass real LAN, USB-network, ADB, and removable-media acceptance. |
| 22. Mesh enrollment and PKI | `VERIFIED_TEST` | UI-first pairing, scrypt challenge validation, explicit ENROLLED/ACTIVE states, CSR identity validation, ECDSA controller CA issuance, activation, and capability sequence gates are tested. | Terminate authenticated controller TLS, bind publishing requests to node certificates, add rotation/revocation distribution, and complete physical pairing. |
| 23. Mesh topology, routing, and leases | `EMULATED` | Sparse and consented intensive measurement plans, evidence-labelled links, local-first/privacy-aware routing, fallbacks, overload rerouting, and persisted policy-bound leases pass deterministic tests. | Measure heterogeneous physical links and carry real inference traffic directly between nodes under validated leases. |
| 24. Mesh UI onboarding | `VERIFIED_LOCAL` | The TanStack setup flow consumes live mesh APIs, separates untrusted sightings from trusted nodes, exposes fingerprints, requires explicit approval, and production-builds locally. | Add browser E2E against physical discovery/pairing and recovery from expired or interrupted enrollment. |
| 25. Controller recovery | `VERIFIED_TEST` | Recovery-key manual promotion and odd-quorum majority election primitives reject invalid keys, even/small quorums, and double votes. | Replicate state, fence stale controllers, transfer PKI custody, and verify manual and three-voter promotion under real partitions. |
| 26. Android mesh client/node | `VERIFIED_STATIC` | Manifest/security tests cover HTTPS-only networking, non-exported telemetry, Keystore lease storage, local-first policy, explicit pairing UI, and an honest llama.cpp JNI boundary. | Install JDK/Android SDK, build and sign the APK, run physical enrollment/telemetry/remote inference, and integrate a real multi-ABI llama.cpp runtime. |
| 27. Mesh containers | `VERIFIED_STATIC` | Controller, node, gateway, and emulator OCI definitions plus Compose profiles pass static role, non-root, read-only, capability, health, volume, and secret checks. | Build/start images on an OCI host, verify Linux wheel compilation, mTLS, Compose networking, and NVIDIA passthrough. |
| 28. Direct inference data plane | `IMPLEMENTED_UNVERIFIED` | The mTLS node agent now exposes a policy-gated `/v1/inference` proxy that derives upstream routes only from RIFT-managed service state, rejects arbitrary targets and streaming until raw-response forwarding is complete, and has deterministic upstream proxy coverage. | Bind inference requests to route leases, add direct streaming/backpressure, controller-side retry/fallback, request metrics, and physical saturation/failure tests. |

## Current Increment

The operator lifecycle now has concise aliases: `rift up` is the explicit,
permission-gated deployment path and `rift down --yes` is the explicit managed
service stop path. These aliases share the existing plan/apply/destroy logic;
they do not bypass download, install, remote, or launch permissions.

The controller state migration is complete for this increment. A fresh local
or cluster controller creates a SQLite database in WAL mode and keeps the
existing JSON file as a human-readable compatibility mirror. The diagnostic
bundle records the database revision without copying the database contents or
secrets. Operators can create a SQLite backup and restore only a validated
backup through `rift system backup` and `rift system restore --yes`; restore
automatically creates a pre-restore backup.

The node data plane now has a first authenticated inference boundary. A node
agent may proxy a bounded non-streaming OpenAI-compatible request only when
`allow_inference: true` is explicitly enabled and only to a URL recorded in
managed service state. This is a verified test contract, not a claim of
physical multi-node serving.

## Latest Acceptance Run

```text
Native build:                    39/39 compile and link steps passed
Native and Python CTest suites:  24/24 passed
CUDA execution target:          RTX 4060 Laptop GPU / sm_89
CUDA runtime tests:             kernels, pipeline, speculation, KV, transformer, GPTQ passed
Backend adapter conformance:    llama.cpp, vLLM, SGLang, MLX-LM passed
Artifact adapter conformance:   GGUF, SafeTensors, AWQ, GPTQ, FP8, EXL2, MLX passed
Third-party adapter loading:     backend and artifact entry-point fixtures passed
Cluster control:                50-node placement, partition, recovery, rollout passed (emulated)
PEP 517 native wheel:           rift-llm 1.1.0 built and installed
Installed CLI smoke:            version, list, inspect, install-plan passed
Pinned CUDA H2D calibration:    11.43 GB/s (8 MiB x 4 timed iterations)
```

## Release Position

## 1.3.0 RC Verification

```text
Python control-plane suites:    19/19 passed after release changes
Dashboard launcher suite:       passed with canonical frontend dependencies
Frontend lint:                   passed, 6 existing Fast Refresh warnings
Frontend typecheck:              passed
Frontend production build:      passed
Frontend setup smoke:            passed
Frontend recommendation smoke:  passed
Release audit:                  PASS, 0 runtime/tracked violations, 0 unresolved licenses
Native CMake/CTest:              blocked before compile; VS BuildTools has no cl.exe in the active C++ workload
```

The native blocker is an environment/toolchain prerequisite, not a passing
native acceptance result. A Windows developer shell with the MSVC C++ workload
must be installed before recreating the CUDA build and running CTest for this
release candidate.

RIFT is useful today as a local-workstation preview, llama.cpp operator, and
testable Elastic Intelligence Mesh control-plane foundation. The UI can guide
discovery and enrollment, while deterministic tests prove trust, topology,
routing, lease, and recovery contracts. It is not yet honestly a production
mesh or Kubernetes replacement. The next mesh release gate is authenticated
controller ingress and direct inference across at least three heterogeneous
physical nodes, including LAN/USB/Android discovery and failover; those gates
cannot be substituted with more emulation on this machine.
