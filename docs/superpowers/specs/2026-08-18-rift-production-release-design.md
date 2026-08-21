# RIFT Production Release Design

**Status:** Proposed for implementation

**Date:** 2026-08-18

## Goal

Make RIFT a production-oriented, open-source LLM deployment control plane whose model recommendations combine published benchmark evidence with exact artifact and hardware fit, while keeping expensive local verification explicit, bounded, and auditable.

## Product Boundary

RIFT owns discovery, evidence aggregation, hardware-aware planning, artifact selection, deployment orchestration, local verification, tuning, monitoring, and recovery. RIFT does not own model weights, third-party serving backends, upstream benchmark leaderboards, or the legal terms of models and backends that users choose to download.

RIFT's recommendation output must distinguish:

- `best_published_quality`: strongest supported quality evidence from external evaluations.
- `best_estimated_fit`: strongest estimated choice after hardware and artifact constraints.
- `best_verified_local`: strongest result measured on the current hardware, if verification exists.
- `fastest_verified_local`: highest measured serving throughput, if verification exists.
- `best_deployment`: a transparent weighted choice with all component scores visible.

No single score may be presented as a universal accuracy score.

## Evidence Architecture

### Evidence Sources

The evidence layer accepts records from:

1. Hugging Face model metadata, model cards, `model-index`, and `.eval_results`.
2. External benchmark providers such as Arena, LiveBench, EvalPlus, and BigCodeBench through explicit provider adapters or imported snapshots.
3. RIFT local verification runs.
4. RIFT local deployment benchmarks and tuning results.

External evidence is optional. RIFT must remain useful when a provider is unavailable, stale, rate-limited, or not configured.

### Evidence Record

Every imported or measured record uses this logical shape:

```json
{
  "source": "huggingface|arena|livebench|evalplus|bigcodebench|rift_local",
  "source_url": "https://example.invalid/result",
  "benchmark": "benchmark-name",
  "task": "chat|coding|documents|agent|custom",
  "metric": "accuracy|pass@k|elo|score",
  "value": 0.0,
  "unit": "percent|points|tokens_per_second|milliseconds",
  "observed_at": "2026-08-18T00:00:00Z",
  "model_id": "org/model",
  "model_revision": "revision-or-null",
  "artifact_id": "artifact-or-null",
  "backend": "backend-or-null",
  "hardware_fingerprint": "fingerprint-or-null",
  "relation": "direct|variant|lineage|inherited|unknown",
  "confidence": 0.0,
  "provenance": "verified|community|author|measured|estimated"
}
```

Benchmark values from different benchmarks are never directly averaged as if they measured the same capability. RIFT normalizes only within a benchmark/task family, applies recency and relationship confidence, and exposes the original records beside any derived score.

### Model Lineage Rules

- `direct` evidence applies to the exact model revision.
- `variant` evidence may transfer to a documented quantized or converted artifact with a confidence penalty.
- `lineage` evidence may transfer from a declared base model to a fine-tune with a larger penalty and an explicit warning.
- `inherited` and `unknown` evidence cannot determine `best_verified_local` and receives only a weak estimate contribution.

## Recommendation Flow

### Default Search

`rift recommend` performs no model download and no backend launch. It uses bounded Hub discovery, configured evidence providers, local cache, exact artifact inspection where available, hardware analysis, backend adapter capabilities, disk capacity, and prior local measurements.

The default search must return evidence freshness, source coverage, confidence, rejected alternatives, and whether the result is estimated or locally verified.

### Optional Local Verification

`rift recommend --verify` verifies only the top candidate unless the user explicitly requests more. It requires permission for downloads, backend installation, and launching. The default local run uses a small deterministic smoke suite and records:

- download and model load time
- first-token latency
- prompt processing rate
- decode tokens per second
- peak or sampled VRAM and RAM
- response completion and error state
- backend and configuration
- model revision and exact artifact hash where available
- task smoke-test result

`rift recommend --verify-top N` is an explicit higher-cost operation. `rift recommend --verify-budget MINUTES` limits total verification time and stops cleanly when the budget is exhausted.

Local benchmark records are reusable only when the model revision, artifact hash, backend version, relevant configuration, workload profile, and hardware fingerprint match. Mismatched records may inform estimates but cannot claim local verification.

## Scoring Contract

RIFT keeps separate dimensions:

- published quality evidence
- task relevance
- hardware fit
- deployment feasibility
- expected speed
- measured speed
- artifact integrity
- license and trust signals
- evidence freshness and confidence

The combined `best_deployment` score is explainable and must include component scores and selection reasons. A missing benchmark record lowers confidence; it must not be silently replaced by a fabricated performance or accuracy value.

## Production CLI Contract

The public release keeps a small, aligned command surface:

```text
rift inspect
rift recommend
rift recommend --verify
rift pull
rift plan
rift apply
rift status
rift benchmark
rift tune
rift logs
rift destroy
rift backend list|inspect|doctor|install-plan|install
rift cluster discover|plan|apply|status|benchmark|tune|destroy
```

Side effects remain permission-gated. Read-only commands never download, install, launch, or modify user model files.

## Repository And Release Hygiene

The canonical product tree is the Python/native RIFT package plus one selected operator console. The live `seismic-deploy-main` console is the current candidate; the older `dashboard` tree must be classified before removal or archival by checking build and documentation references.

The release tree must not contain:

- `.rift` runtime state, recommendation caches, logs, or model files
- native build outputs and compiled binaries
- `node_modules`, frontend output directories, or package-manager caches
- source ZIP snapshots
- generated test fixtures or machine-specific reports
- secrets, tokens, certificates, or private endpoint configuration

Generated runtime and development files belong in `.gitignore` and release builds must be created from a clean checkout.

## Legal And Provenance Policy

RIFT-owned source remains Apache-2.0. The release must add:

- `NOTICE` for RIFT attribution and material notices
- a generated third-party dependency attribution report
- an SBOM for Python, native, frontend, and build dependencies
- model and backend licensing documentation stating that downloaded artifacts retain their own terms
- benchmark-data provenance documentation stating source, date, transformation, and redistribution limits
- a disclaimer that the repository audit is not legal advice or a substitute for counsel

RIFT must not bundle external backend binaries or model weights by default. Leaderboard integration must use documented APIs, permitted snapshots, or user-provided evidence and must not silently redistribute restricted data.

## Security And Operations

Production defaults bind services locally unless the user explicitly exposes them. Remote execution, downloads, installs, and public serving require explicit permission. Logs must redact tokens and secrets. Health, benchmark, tuning, and recovery reports must identify whether values are simulated, estimated, or measured.

## Verification Gates

Before release:

1. Python unit and integration tests pass.
2. Native CTest passes where CUDA is available, with clear skips where it is not.
3. Frontend lint, type/build, and controller smoke tests pass.
4. Recommendation tests cover evidence ingestion, lineage penalties, stale evidence, no-provider operation, and local verification gating.
5. License/provenance audit produces a clean report with reviewed exceptions.
6. A clean-checkout wheel and operator console build succeeds without runtime caches or model artifacts.
7. The README and release notes accurately state supported backends, platforms, limitations, and the difference between estimates and measurements.

## Non-Goals For This Release

- Building a complete local copy of every public leaderboard.
- Claiming that metadata scores are objective model intelligence.
- Running full academic evaluations on every user machine.
- Bundling proprietary or third-party backend binaries.
- Including model weights in the source repository.
- Treating RIFT's native survival runtime as production-ready for every architecture.
