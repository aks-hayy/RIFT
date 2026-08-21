# RIFT Production Recommendation And Release Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an evidence-aware, hardware-aware RIFT recommendation flow with bounded opt-in local verification, documented provenance/legal boundaries, and a clean reproducible open-source release tree.

**Architecture:** Extend the existing `EvidenceEngine` and signed intelligence-feed path with typed benchmark records and confidence-aware aggregation. Keep `RiftEngine.recommend_models()` download-free by default; add external evidence to its separate quality dimension, while the existing permission-gated orchestrator verifies only explicitly selected finalists and records hardware-specific measurements. Harden the repository with generated provenance checks, release documentation, and removal of generated artifacts without bundling models or backend binaries.

**Tech Stack:** Python 3.9+, existing RIFT control-plane modules, JSON/JSONL evidence records, Ed25519 feed verification, argparse CLI, CMake/CTest, PEP 517 packaging, TanStack/Vite operator console.

**Spec:** `docs/superpowers/specs/2026-08-18-rift-production-release-design.md`

## Global Constraints

- `rift recommend` performs no model download, backend installation, or backend launch.
- `rift recommend --verify` verifies one finalist by default and requires explicit side-effect permissions.
- Benchmark values from different benchmark families are never averaged as if they were one metric.
- `best_verified_local` requires matching model revision, artifact, backend, configuration, workload, and hardware evidence.
- RIFT-owned code remains Apache-2.0; model and backend licenses remain external obligations.
- Runtime state, model files, build output, node modules, caches, secrets, and source ZIP snapshots are not release content.
- Every estimate, emulation, published result, and local measurement is labelled in persisted output and human-readable output.

---

### Task 1: Evidence Record V2 And Benchmark Provider Boundary

**Files:**
- Modify: `python/spoolstream/evidence.py`
- Create: `python/spoolstream/evidence_sources.py`
- Test: `tests/python/recommend_tests.py`
- Test: `tests/python/evidence_tests.py`

**Interfaces:**
- `EvidenceRecord` gains typed provenance fields: `benchmark`, `task`, `metric`, `normalized_value`, `observed_unix_seconds`, `model_revision`, `artifact_id`, `backend`, `hardware_fingerprint`, `relation`, `confidence`, and `provenance`.
- Add `BenchmarkEvidenceSource` with `source_id`, `load()`, and `diagnostics()` methods.
- Add `JsonEvidenceSource(path_or_url, source_id)` that accepts an already-permitted JSON snapshot and returns validated records; remote loading is opt-in and remains fail-closed when signature verification is absent.
- Add `aggregate_quality_evidence(records, task)` returning `score`, `coverage`, `freshness`, `confidence`, `published_records`, `local_records`, and `claim_boundary`.

- [ ] **Step 1: Write failing evidence tests**

Add tests for a signed snapshot containing Arena-style preference, EvalPlus-style pass rate, and a local measured record. Assert that source, metric, timestamp, model relation, and normalized values survive serialization; assert that malformed values and unsigned external snapshots are rejected as trusted evidence.

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run:

```powershell
python tests/python/evidence_tests.py
```

Expected: failure because the V2 record fields and provider module do not exist.

- [ ] **Step 3: Implement the typed record and provider boundary**

Preserve the existing signed Ed25519 feed format for compatibility. Accept external records only when their envelope has a trusted key, source identifier, observation time, model identity, benchmark, metric, and numeric value. Keep raw source records in the evidence result so downstream reports remain auditable.

- [ ] **Step 4: Implement benchmark-family aggregation**

Aggregate only records with a declared `normalized_value` within the same task and benchmark family. Apply relation and confidence multipliers, apply a bounded age decay, keep publisher/community/verified/measured provenance separate, and return `None` for quality score when no comparable normalized record exists.

- [ ] **Step 5: Run the focused tests and the existing recommendation suite**

Run:

```powershell
python tests/python/evidence_tests.py
python tests/python/recommend_tests.py
```

Expected: all tests pass, including legacy recommendation fields.

- [ ] **Step 6: Commit the evidence boundary**

```powershell
git add python/spoolstream/evidence.py python/spoolstream/evidence_sources.py tests/python/evidence_tests.py tests/python/recommend_tests.py
git commit -m "feat: add provenance-aware benchmark evidence records"
```

### Task 2: Integrate Published Evidence Into Recommendation Scoring

**Files:**
- Modify: `python/spoolstream/rift.py`
- Modify: `python/spoolstream/recommendations.py`
- Modify: `tests/python/recommend_tests.py`

**Interfaces:**
- `RiftEngine` owns one `EvidenceEngine` rooted at the active RIFT directory.
- `_score_hub_candidate()` consumes the evidence aggregate without replacing hardware, artifact, or deployment scores.
- Public candidate output includes `quality_evidence`, `evidence_freshness`, `evidence_coverage`, and `claim_boundary`.

- [ ] **Step 1: Add failing scoring tests**

Create two synthetic candidates with identical hardware/artifact fit. Give one a recent direct EvalPlus record and the other only model-card metadata. Assert that the benchmark-backed candidate wins the quality dimension, while a severe hardware incompatibility still prevents a benchmark-rich candidate from becoming deployable.

- [ ] **Step 2: Run the focused tests and confirm the new assertions fail**

Run:

```powershell
python tests/python/recommend_tests.py
```

- [ ] **Step 3: Wire the evidence engine into candidate scoring**

Use the selected revision, artifact identity, backend candidate, task, and hardware fingerprint when assessing records. Add a bounded benchmark evidence contribution to `quality_proxy`; do not add benchmark values to expected speed or hardware fit.

- [ ] **Step 4: Add explicit recommendation categories**

Persist `best_published_quality`, `best_estimated_fit`, `best_verified_local`, `fastest_verified_local`, and `best_deployment`. Do not populate local categories from a repository-only match when exact artifact/backend/hardware evidence is missing.

- [ ] **Step 5: Add stale and no-provider diagnostics**

Return provider status, source age, missing coverage, and the reason a candidate is estimated. A provider outage must not erase Hub-based recommendations or fabricate a score.

- [ ] **Step 6: Run all recommendation and orchestrator tests**

Run:

```powershell
python tests/python/recommend_tests.py
python tests/python/orchestrator_tests.py
```

- [ ] **Step 7: Commit scoring integration**

```powershell
git add python/spoolstream/rift.py python/spoolstream/recommendations.py tests/python/recommend_tests.py
git commit -m "feat: combine published benchmark evidence with deployment fit"
```

### Task 3: Bounded Local Verification And CLI Reports

**Files:**
- Modify: `python/rift/cli/parser.py`
- Modify: `python/rift/cli/commands.py`
- Modify: `python/rift/cli/console.py`
- Modify: `python/spoolstream/orchestrator.py`
- Test: `tests/python/recommend_tests.py`
- Test: `tests/python/orchestrator_tests.py`

**Interfaces:**
- Add `--verify-top` and `--verify-budget` to `rift recommend` while retaining `--verify-finalists` as a compatibility alias for one release.
- `verify_recommendation_run()` accepts an optional monotonic wall-clock budget and stops between candidates without killing an active backend process.
- Human output labels every result as `PUBLISHED`, `ESTIMATED`, `MEASURED_LOCAL`, or `BLOCKED`.

- [ ] **Step 1: Add failing CLI and budget tests**

Assert that default recommendation performs no side effects, `--verify` defaults to one finalist, `--verify-top 3` requests three, and a zero or exhausted budget produces a persisted blocked report without a launch.

- [ ] **Step 2: Run the focused tests and confirm failure**

Run:

```powershell
python tests/python/recommend_tests.py
python tests/python/orchestrator_tests.py
```

- [ ] **Step 3: Implement verification budget enforcement**

Use `time.monotonic()` around finalist boundaries, persist partial results, stop and clean up through the existing provider lifecycle, and mark untested finalists as `BUDGET_EXHAUSTED` rather than failed.

- [ ] **Step 4: Implement concise evidence-aware console output**

Show the best published result, best estimated fit, and best verified local result separately. JSON output retains complete evidence records and claim boundaries.

- [ ] **Step 5: Run CLI smoke tests and regression tests**

Run:

```powershell
python -m rift --help
python -m rift recommend --help
python tests/python/recommend_tests.py
python tests/python/orchestrator_tests.py
```

- [ ] **Step 6: Commit the bounded verification surface**

```powershell
git add python/rift/cli/parser.py python/rift/cli/commands.py python/rift/cli/console.py python/spoolstream/orchestrator.py tests/python/recommend_tests.py tests/python/orchestrator_tests.py
git commit -m "feat: add budgeted opt-in recommendation verification"
```

### Task 4: Legal, Dependency, And Release Provenance

**Files:**
- Create: `NOTICE`
- Create: `THIRD_PARTY_NOTICES.md`
- Create: `docs/legal/model-and-backend-policy.md`
- Create: `docs/legal/benchmark-data-policy.md`
- Create: `docs/legal/release-audit.md`
- Create: `scripts/audit_release.py`
- Modify: `pyproject.toml`
- Modify: `.gitignore`
- Modify: `.github/workflows/ci.yml`
- Test: `tests/python/release_audit_tests.py`

**Interfaces:**
- `python scripts/audit_release.py --root . --json` emits `status`, `tracked_violations`, `dependency_inventory`, `unresolved_licenses`, and `runtime_artifact_violations`.
- The audit rejects model weights, secrets, runtime `.rift` state, build outputs, node modules, source ZIPs, and unknown direct dependency licensing in release mode.
- The audit does not claim legal advice or verify model licenses beyond recorded metadata.

- [ ] **Step 1: Add failing release-audit tests**

Create a temporary release fixture containing a `.gguf`, `.rift/state.json`, a ZIP snapshot, and an unknown dependency. Assert that the audit reports each violation and passes a clean fixture.

- [ ] **Step 2: Run the focused test and confirm failure**

Run:

```powershell
python tests/python/release_audit_tests.py
```

- [ ] **Step 3: Implement the audit script**

Scan tracked files when Git metadata is available and the filesystem tree otherwise. Parse Python direct dependencies, frontend lockfiles, and native build requirements. Record known direct dependency license URLs and mark transitive packages as requiring generated lockfile/SBOM review rather than silently declaring them cleared.

- [ ] **Step 4: Add release policy documents and notices**

Document Apache-2.0 ownership, external model/backend terms, benchmark-source redistribution limits, feed signing, and user obligations. Add attribution for direct runtime and build dependencies with their upstream license references.

- [ ] **Step 5: Add CI release gates**

Run the release audit, Python suites, and frontend gates in CI. Keep CUDA acceptance separate and labelled as a hardware job.

- [ ] **Step 6: Run audit tests and generate the current report**

Run:

```powershell
python tests/python/release_audit_tests.py
python scripts/audit_release.py --root . --json
```

- [ ] **Step 7: Commit release provenance changes**

```powershell
git add NOTICE THIRD_PARTY_NOTICES.md docs/legal scripts/audit_release.py tests/python/release_audit_tests.py pyproject.toml .gitignore .github/workflows/ci.yml
git commit -m "chore: add release provenance and legal audit gates"
```

### Task 5: Repository Cleanup And Canonical Operator Console

**Files:**
- Modify: `README.md`
- Modify: `CONTRIBUTING.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/roadmap/status.md`
- Modify: `docs/architecture/repository-layout.md`
- Modify: `.gitignore`
- Inspect/remove only after reference checks: `seismic-deploy-main.zip`, generated build/output/cache directories, duplicate dashboard source if confirmed unused

**Interfaces:**
- The release uses one canonical operator console and one documented development command.
- `rift dashboard` resolves the canonical console without depending on generated output directories.
- Documentation names the distinction between source, generated runtime state, local model storage, and release artifacts.

- [ ] **Step 1: Write a reference inventory test**

Assert that documentation, dashboard launcher code, and packaging configuration agree on the canonical console path and that no release manifest includes runtime state or model directories.

- [ ] **Step 2: Run the inventory test before cleanup**

Run:

```powershell
python tests/python/repository_layout_tests.py
```

Expected: failure identifying stale duplicate or contradictory references.

- [ ] **Step 3: Resolve references and classify duplicate sources**

Use `rg` across source, docs, scripts, CMake, and package manifests. Keep the current live console as canonical only if all launcher and build paths agree; otherwise migrate the launcher references first. Do not delete source merely because it is not currently open in the browser.

- [ ] **Step 4: Remove clearly generated artifacts**

Remove only verified generated outputs and the redundant source ZIP. Keep source, tests, manifests, docs, and user model placeholders. Update `.gitignore` for every removed runtime class.

- [ ] **Step 5: Update public documentation**

Document the evidence-aware recommendation flow, `--verify` cost, production limitations, supported backend/platform matrix, legal boundaries, and clean source build commands.

- [ ] **Step 6: Run layout and frontend checks**

Run:

```powershell
python tests/python/repository_layout_tests.py
cd seismic-deploy-main
npm run lint
npx tsc --noEmit
npm run build
cd ..
```

- [ ] **Step 7: Commit repository cleanup**

```powershell
git add README.md CONTRIBUTING.md CHANGELOG.md docs .gitignore tests/python/repository_layout_tests.py
git commit -m "chore: consolidate the open-source release tree"
```

### Task 6: Full Verification And Release Candidate Report

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/roadmap/status.md`
- Create: `docs/releases/1.3.0-rc.md`

- [ ] **Step 1: Run all Python control-plane suites**

```powershell
for ($file in Get-ChildItem tests/python/*_tests.py) { python $file.FullName }
```

- [ ] **Step 2: Run native CTest where the configured build is available**

```powershell
ctest --test-dir build --output-on-failure
```

Record CUDA availability and skipped/failed hardware tests explicitly.

- [ ] **Step 3: Run frontend lint, typecheck, build, and smoke scripts**

```powershell
cd seismic-deploy-main
npm run lint
npx tsc --noEmit
npm run build
npm run verify:setup-flow
npm run verify:recommendation-state
cd ..
```

- [ ] **Step 4: Run clean-wheel and installed-CLI checks**

Build the PEP 517 wheel from a clean staging directory, install it into a fresh environment, run `rift --help`, `rift recommend --help`, and the read-only `rift inspect`/`rift system info` smoke commands.

- [ ] **Step 5: Generate the release-candidate report**

Record test counts, platform, CUDA/toolchain availability, evidence-provider status, legal-audit status, known limitations, and explicit blockers. Mark RIFT production-ready only for the verified scope; keep unsupported providers and physical cluster gates visible.

- [ ] **Step 6: Commit release documentation**

```powershell
git add CHANGELOG.md docs/roadmap/status.md docs/releases/1.3.0-rc.md
git commit -m "docs: publish RIFT production release candidate status"
```

## Plan Self-Review

- Evidence ingestion, scoring, local verification, release/legal audit, cleanup, and final verification each have separate tasks and tests.
- The plan preserves the existing signed feed and permission gates instead of adding an untrusted leaderboard scraper.
- No task bundles model weights or backend binaries.
- No task treats metadata, published benchmarks, or a tiny local smoke suite as universal accuracy.
- The current frontend duplicate is classified through reference tests before any deletion.
- No placeholder implementation steps remain; each task names files, interfaces, failing tests, commands, and commit boundaries.
