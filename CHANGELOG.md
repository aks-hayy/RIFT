# Changelog

## 1.3.0 - 2026-08-22

### Release Hardening

- Converted the public distribution to a pure-Python, cross-platform control
  plane with no CUDA, CMake, compiler, or Node.js requirement for users.
- Added platform-aware `RiftPaths`, backup-first checkout migration, durable
  operation IDs, request-id idempotency, and a bounded reconciliation loop.
- Reduced the CLI to the canonical workflow and grouped expert operations under
  `model`, `backend`, `service`, `cluster`, `node`, and `system`.
- Bundled the live dashboard into the wheel and added clean-clone bootstrap
  scripts for Windows, Linux, and macOS.
- Rebuilt controller, node, gateway, and emulator images on `python:3.12-slim`;
  external serving backends remain adapter-managed and are never bundled.
- Preserved native-survival and Android experiments in the archival Git tag
  `archive/native-android-2026-08-22`; they are excluded from the release tree.

### Verification Boundary

The release has deterministic control-plane, packaging, dashboard,
state, recommendation, adapter, gateway, mesh, and container-manifest tests.
Physical multi-node reliability, controller HA with PostgreSQL/Redis, mTLS
rotation, and provider acceptance on Linux/Apple hardware remain explicitly
`UNVERIFIED_EXTERNAL` until field evidence exists.

## 1.3.0-rc - 2026-08-18

### Recommendation Evidence And Release Hygiene

- Added typed, provenance-aware benchmark records with signed JSON snapshot
  loading and benchmark-family-safe aggregation.
- Added explicit recommendation categories for published quality, estimated
  fit, local verification, verified speed, and deployment feasibility.
- Added bounded recommendation verification controls: `--verify-top`,
  `--verify-budget`, one-finalist default, and persisted `BUDGET_EXHAUSTED`
  results.
- Added human-readable evidence labels: `PUBLISHED`, `ESTIMATED`,
  `MEASURED_LOCAL`, and `BLOCKED`.
- Added `NOTICE`, direct dependency attribution, model/backend policy,
  benchmark provenance policy, and a release audit command.
- Added read-only hypothetical hardware simulation for recommendations, with
  compact key/value or JSON profiles, simulated disk feasibility, explicit
  assumptions, and side-effect rejection.
- Consolidated the source checkout around `seismic-deploy-main/` as the
  canonical operator console and removed generated outputs and the redundant
  source ZIP from the working tree.

This release covers the verified local control-plane scope. It is
not a claim of universal model quality, production Kubernetes equivalence, or
physical multi-node/provider acceptance.

### R20 Recommendation Calibration Addendum

- Added benchmark provenance catalog entries for Chatbot Arena, EvalPlus,
  LiveBench, and BigCodeBench, plus signed snapshot ingestion through
  `--benchmark-snapshot`.
- Replaced the recommendation funnel's single small-model parameter arm with
  small, medium, and large parameter arms alongside task, format, and family
  discovery arms.
- Added separate practical VRAM residency scoring and offload penalties so
  weak hardware is not told that an oversized model is equally usable.
- Added a deterministic 51-profile calibration harness covering the measured
  workstation, 50 weaker/stronger/mobile simulations, exact artifact choices,
  backend recommendations, and no-side-effect live Hub searches.
- Cached backend probes within a recommendation run to reduce repeated
  external-tool detection overhead.

All notable RIFT changes are recorded here. The detailed engineering history is
preserved in [`docs/history/versions.md`](docs/history/versions.md).

## 1.2.0 - 2026-08-14

### Added

- Added the transport-neutral Elastic Intelligence Mesh contracts, deterministic
  fleet laboratory, policy-aware route planner, capability snapshots, measured
  links, and short-lived cached route leases.
- Added passive mDNS discovery plus consent-gated private-subnet, USB-network,
  ADB, and removable-media bootstrap adapters. Discovery never grants trust.
- Added explicit pairing, persistent enrollment/revocation state, controller
  CA-issued client certificates from node-generated CSRs, and routability only
  after mTLS activation.
- Added UI-first mesh onboarding and a live node/topology operations view with
  honest trust, certificate, route, and evidence states.
- Added manual recovery-key controller promotion and optional odd-voter quorum
  election primitives.
- Added Android node/client scaffolding and split controller, node, gateway, and
  emulator OCI/Compose packaging with deny-by-default settings.

### Verification

- Passed all 27 registered CTest targets and the dashboard lint and production
  client/SSR/Nitro build.
- Built and installed the Windows CUDA wheel as `rift-llm 1.2.0` through the
  documented Visual Studio environment wrapper.
- Android device execution, real LAN/USB enrollment, heterogeneous physical
  routing, and OCI image startup remain physical acceptance gates.

## 1.1.0 - 2026-07-18

### Added

- Added Recommendation Contract V2 with model identities, exact artifact
  variants, backend deployment candidates, persisted runs, Pareto categories,
  and permission-gated local finalist verification.
- Added a versioned dynamic adapter host with Python entry points for serving,
  artifact, and converter adapters. Third-party packages require no RIFT core
  registry edits.
- Added built-in artifact adapters for GGUF, dense/sharded SafeTensors, AWQ,
  GPTQ, FP8, EXL2, and MLX, including dependency, shard, hash, multimodal, disk,
  RAM, VRAM, and KV-cache validation.
- Added complete external-process adapters for vLLM, SGLang, and MLX-LM with
  isolated/container/WSL installation plans where applicable, launch, health,
  benchmark, tuning, stop, recovery, platform gates, and runtime flag probes.
- Added API V2 resources for adapters, capabilities, artifacts,
  compatibility, recommendation runs, plans, and verification runs.
- Added an optional mutual-TLS node agent with monotonic desired state,
  idempotent reconciliation, node-side permission gates, and cluster dispatch.
- Added shared backend and artifact conformance suites, plus heterogeneous
  50-node placement, partition, rescheduling, rollout, and benchmark emulation.
- Added PyYAML as a declared runtime dependency so human-authored `rift.yaml`
  files are supported by installed packages.

### Changed

- Restructured the repository into `dashboard`, `docs`, `models`, `native`,
  `python`, and language-specific test directories.
- Replaced the flat legacy CLI with a focused, grouped RIFT command surface.
- Added human-readable tables and summaries; `--json` remains available for
  scripts and control-plane integrations.
- Added a Windows-capable ANSI console palette, command-context banners,
  state/action colors, and worked examples throughout grouped help pages.
- Removed native survival-development commands from the public product CLI.
- Renamed the Python distribution to `rift-llm` and made `rift` the only
  installed console command.
- Removed the superseded static dashboard implementation.
- Replaced the dashboard's vendor-specific build wrapper with the standard
  TanStack Start, Vite, Tailwind, and Nitro plugin stack.
- Reduced the dashboard to its three used UI primitives and removed 110 unused
  packages from its dependency graph.
- Moved dashboard API forwarding to Nitro so `/api/rift/*` works in both the
  development server and the production bundle.
- Added recursive checkout discovery, an explicit `rift dashboard --root`
  override, and startup readiness checks for the operator interface.
- Added `rift dashboard --detach` with normalized process environment,
  readiness confirmation, PID/URL output, and persisted dashboard logs.
- Made native CUDA architecture selection default to the contributor's local
  GPU while preserving explicit CMake overrides.
- Separated LMCache into an optimization overlay and conversions into their own
  permission-gated adapter class.
- Replaced recommendation/orchestration format maps with manifest-driven
  compatibility and detected-version capability negotiation.
- Split recommendation trust into behavioral safety, license trust, artifact
  integrity, and deployment feasibility; retained the legacy aggregate for one
  compatibility release.

### Fixed

- Packaged cluster and gateway modules with the native wheel.
- Kept local models, runtime state, generated builds, virtual environments, and
  dashboard dependencies out of source control.

## 1.0.0 - 2026-07-12

- First integrated RIFT control-plane preview with hardware discovery, model
  recommendation, declarative planning/apply, llama.cpp operation, benchmarking,
  tuning, supervision, gateway controls, cluster emulation, and live dashboard.
