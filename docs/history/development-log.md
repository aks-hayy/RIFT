# RIFT Development Log

## R0: Identity, API Surface, And Compatibility Bridge

### Status

Completed and verified.

### What Changed

- Added `spoolstream.rift`.
- Added `RiftEngine` as the RIFT-facing Python facade.
- Added public enums:
  - `RiftMode`
  - `DeploymentStrategy`
  - `UsabilityVerdict`
- Exported RIFT API objects from `spoolstream.__init__`.
- Added a `rift` console-script alias while keeping `spoolstream`.
- Added basic CLI commands:
  - `rift --help`
  - `rift build-info`
  - `rift hardware`
- Updated CMake install rules to package `rift.py`.

### Retrospective

This phase deliberately avoids renaming the native C++/CUDA backend. The safest architecture is to keep SpoolStream as the engine room and build RIFT as the user-facing planner/runtime layer above it. That lets the existing Phase 28 real-model path remain usable while the product direction changes.

### LLM User / Developer Notes

Useful additional feature idea: RIFT should eventually include `rift doctor`, a one-command diagnostic that checks CUDA visibility, package install health, model folder structure, tokenizer availability, and likely runtime blockers before the user attempts a run.

### Verification

Completed:

```text
cmake --build build --config Release
100% tests passed, 0 tests failed out of 12
RiftEngine import smoke passed
CLI help/build-info smoke passed
```

Observed smoke:

```text
RIFT R0 SURVIVAL
cuda_available: True
```

## R1: Hardware And Model Inspect Engine

### Status

Completed and verified.

### What Changed

- Added `RiftCompatibilityLevel`.
- Added RIFT inspection annotations:
  - `rift_compatibility_level`
  - `rift_recommended_initial_mode`
  - `rift_native_modes`
  - `rift_summary`
  - `rift_blockers`
- Added CLI command:

```bash
rift inspect --model <path>
```

- Standardized CLI output as JSON for automation and dashboard reuse.

### Retrospective

The raw backend inspection has a lot of useful detail, but it is too dense for a normal LLM user. RIFT needs to surface a short verdict first, then preserve the deep report underneath. The compatibility-level tiering gives us that product shape without losing engineering detail.

### LLM User / Developer Notes

Additional feature idea: add a compact `--summary` flag that prints only the mode, blockers, memory estimate, and recommendation. The full JSON is excellent for tools, but humans will want a quick readable summary.

### Verification

Completed:

```text
cmake --build build --config Release
100% tests passed, 0 tests failed out of 12
RiftEngine inspect smoke passed on LLAMA-GPT4Q
CLI inspect JSON smoke passed on LLAMA-GPT4Q
```

Observed RIFT verdict:

```text
rift_compatibility_level: NATIVE_RUN_READY
rift_recommended_initial_mode: SURVIVAL
SURVIVAL native mode: True
layers: 32
output_head_mode: DENSE_FP16_LM_HEAD_STREAMING
```

## R2: Real Benchmark Harness

### Status

Completed and verified.

### What Changed

- Added `RiftEngine.benchmark_model(...)`.
- Added CLI command:

```bash
rift bench --model <path>
```

- Added measured disk read sampling:
  - bytes read
  - elapsed seconds
  - GB/s
  - MiB/s
  - files sampled
- Added H2D transfer estimates from the native backend.
- Added backend dry-run benchmark capture when available.

### Retrospective

The important product distinction is measured versus estimated. RIFT should earn user trust by labeling benchmark data honestly. R2 measures disk read throughput directly, while H2D timing remains estimate-based until a native timed-copy benchmark lands.

### LLM User / Developer Notes

Additional feature idea: add a `--cold-cache` advisory mode later. True cold-cache disk testing is OS-specific and disruptive, but RIFT can at least warn users when a benchmark likely reflects Windows file cache rather than sustained NVMe reads.

### Verification

Completed:

```text
cmake --build build --config Release
100% tests passed, 0 tests failed out of 12
CLI bench smoke passed on LLAMA-GPT4Q
```

Observed benchmark smoke:

```text
compatibility_level: NATIVE_RUN_READY
recommended_initial_mode: SURVIVAL
bytes_read: 67108864
disk_sample_bandwidth_gbps: 1.818
h2d_estimates: max_layer_bytes, sample_read_bytes, total_model_bytes
```

## R3: `.riftplan` Schema And Planner

### Status

Completed and verified.

### What Changed

- Added `RiftEngine.plan_model(...)`.
- Added `RiftEngine.load_plan(...)`.
- Added CLI command:

```bash
rift plan --model <path>
```

- Added `.riftplan` schema version 1.
- Added model fingerprinting from model file names, sizes, and mtimes.
- Added candidate-mode decisions:
  - `FAST`
  - `BALANCED`
  - `SURVIVAL`
- Added rough disk-stream floor estimate and survival tok/s ceiling.

### Retrospective

The planner must be conservative. In R3, FAST and BALANCED are intentionally marked unavailable because their execution paths are not implemented yet. SURVIVAL is selected only when the current native backend can actually run the model.

### LLM User / Developer Notes

Additional feature idea: add plan comparison. A future `rift plan --compare` could emit multiple candidate plans side by side, such as "interactive 4k context", "long-context slow mode", and "low-RAM survival".

### Verification

Completed:

```text
cmake --build build --config Release
100% tests passed, 0 tests failed out of 12
CLI plan smoke passed on LLAMA-GPT4Q
.riftplan read-back verification passed
```

Observed plan:

```text
schema_version: 1
recommended_mode: SURVIVAL
selected_backend: spoolstream_native_survival
SURVIVAL available: True
lm_head strategy: dense_fp16_tiled_streaming
```

## R4: SURVIVAL Run Mode

### Status

Completed and verified.

### What Changed

- Added `RiftEngine.run(...)`.
- Added CLI command:

```bash
rift run --model <path> --prompt "Hello" --max-tokens 1
rift run --plan <path.riftplan> --prompt "Hello" --max-tokens 1
```

- Wrapped existing Phase 28 native generation as RIFT `SURVIVAL`.
- Added structured run metrics:
  - load seconds
  - generation seconds
  - total seconds
  - generated token count
  - tokens/sec
  - backend streamed bytes
  - layers executed

### Retrospective

R4 is where RIFT stops being only advisory and becomes executable. The key is honesty: this mode is correctness-first survival execution, not optimized chat. It proves that a viable deployment can run without OOM.

### LLM User / Developer Notes

Additional feature idea: every SURVIVAL response should include an explicit slow-mode warning and suggested alternatives, such as smaller model, lower context, more RAM, or waiting for BALANCED mode.

### Verification

Completed:

```text
cmake --build build --config Release
100% tests passed, 0 tests failed out of 12
CLI run smoke from .riftplan passed on LLAMA-GPT4Q
```

Observed run:

```text
status: ok
mode: SURVIVAL
generated_tokens: 1
tokens_per_second: 0.0947
layers_executed: 32
```

## R5: Usability Report

### Status

Completed and verified.

### What Changed

- Added usability report generation after `RiftEngine.run(...)`.
- Added default report artifact:

```text
.rift/latest.riftreport.json
```

- Added CLI command:

```bash
rift report --run latest
```

- Added report fields:
  - usability verdict
  - bottleneck classification
  - load/generation/total seconds
  - generated tokens
  - tokens/sec
  - backend metrics
  - recommendations

### Retrospective

The report is the start of RIFT's trust layer. Users need more than "it ran"; they need to know whether it was usable, what bottleneck dominated, and what to try next.

### LLM User / Developer Notes

Additional feature idea: add report history with run IDs, then let users compare multiple models or modes across the same hardware. That could become one of RIFT's strongest features.

### Verification

Completed:

```text
cmake --build build --config Release
100% tests passed, 0 tests failed out of 12
CLI run wrote report
CLI report read latest report
```

Observed report:

```text
status: ok
usability_verdict: SLOW
bottleneck_classification: survival_repeated_prefill_streaming
generated_tokens: 1
recommendations: 3
```

## R6: Local API Server

### Status

Completed and verified.

### What Changed

- Added `spoolstream.server`.
- Added `RiftServerRuntime`.
- Added `create_rift_server(...)`.
- Added CLI command:

```bash
rift serve --plan <path.riftplan>
rift serve --model <path>
```

- Added local endpoints:
  - `GET /v1/models`
  - `POST /v1/completions`
  - `POST /v1/chat/completions`
  - `GET /rift/status`
  - `GET /rift/metrics`
  - `GET /rift/report`

### Retrospective

The MVP server intentionally uses the Python standard library. This is enough to prove the product loop without adding server dependencies. Later production work can replace or wrap this with a stronger async server.

### LLM User / Developer Notes

Additional feature idea: add a queue status endpoint before adding concurrency. Users should be able to see when SURVIVAL mode is busy and why another request is waiting.

### Verification

Completed:

```text
cmake --build build --config Release
100% tests passed, 0 tests failed out of 12
Server creation smoke passed
GET /rift/status smoke passed
GET /v1/models smoke passed
```

Observed server smoke:

```text
status.ok: True
model_id: LLAMA-GPT4Q.riftplan
```

## R7: Dashboard Integration

### Status

Completed and verified.

### What Changed

- Dashboard default engine now uses `RiftEngine`.
- Dashboard health reports `rift-dashboard`.
- Added dashboard API routes:
  - `POST /api/rift/bench`
  - `POST /api/rift/plan`
  - `POST /api/rift/run`
  - `GET /api/rift/report`
- Extended dashboard tests with RIFT route coverage.

### Retrospective

R7 focuses on backend dashboard integration first. The browser UI can now call RIFT planning/running/reporting routes without needing another server-layer change. Visual polish should come after the MVP data contracts stabilize.

### LLM User / Developer Notes

Additional feature idea: add a "plan comparison" table to the dashboard once FAST/BALANCED candidates become real. For now, the dashboard should highlight SURVIVAL warnings clearly.

### Verification

Completed:

```text
cmake --build build --config Release
100% tests passed, 0 tests failed out of 12
Dashboard route tests passed with RIFT bench/plan/run/report coverage
```

## R8: MVP Hardening And Release Package

### Status

Completed and verified.

### What Changed

- Rewrote `README.md` around the RIFT product workflow.
- Added `RIFT_QUICKSTART.md`.
- Added `RIFT_KNOWN_LIMITATIONS.md`.
- Added `RIFT_COMPATIBILITY_MATRIX.md`.
- Added `examples/LLAMA-GPT4Q.example.riftplan`.
- Installed RIFT docs and example plans through CMake.
- Added `tests/rift_tests.py` for planner, report, and run wrapper smoke coverage.
- Added `spoolstream_rift_tests` to CTest.
- Updated package metadata description for RIFT.
- Updated `build_info()` to report current RIFT phase `R8`.

### Retrospective

R8 turns the work from a private engineering build into something a user can try
without guessing the sequence. The most important product decision is still
honesty: RIFT can run the validated model in SURVIVAL mode, but the report must
clearly say when it is slow and why.

### LLM User / Developer Notes

Additional feature idea: add `rift doctor` next. It should check CUDA, package
install health, model-file layout, tokenizer presence, and whether the newest
report indicates a mode upgrade path.

### Verification

Completed:

```text
cmake --build build --config Release
100% tests passed, 0 tests failed out of 13
cmake --install build --config Release --prefix phase19_install
Installed-package RIFT API smoke passed on LLAMA-GPT4Q
Installed CLI help/report smoke passed
```

Observed installed real-model smoke:

```text
product: RIFT
compatibility_level: NATIVE_RUN_READY
recommended_mode: SURVIVAL
layers: 32
plan: SURVIVAL
run_status: ok
generated_tokens: 1
tokens_per_second: 0.1431
usability_verdict: SLOW
```

### Current Capability After R8

RIFT MVP now supports the complete first product loop:

```text
inspect -> benchmark -> plan -> run -> report -> serve/dashboard
```

The executable backend remains SURVIVAL mode for the validated LLaMA GPTQ
SafeTensors target. FAST and BALANCED remain planned optimization modes.

## R9: Doctor And Fit-Aware Planner

### Status

Completed and verified.

### What Changed

- Added `RiftEngine.doctor(...)`.
- Added CLI command:

```bash
rift doctor --model <path>
```

- Added dashboard API route:
  - `POST /api/rift/doctor`
- Added RIFT mode analysis:
  - `best_hardware_fit_mode`
  - `best_executable_mode`
  - `runtime_gap`
  - per-mode `hardware_suitable`
  - per-mode `runtime_available`
- Updated plans to include:
  - `hardware_fit_mode`
  - `best_executable_mode`
  - `mode_analysis`
- Added `RIFT_POST_MVP_PHASES.md`.
- Updated quickstart and README with `rift doctor`.

### Retrospective

This phase fixes an important product truth. A model can be comfortable for the
hardware but still routed through SURVIVAL because the faster runtime is not
implemented yet. RIFT now says that directly instead of implying the hardware is
the reason for slow execution.

### LLM User / Developer Notes

Additional feature idea: the dashboard should show mode gap as a first-class
banner: "Your model should be BALANCED, but RIFT currently runs SURVIVAL."

### Verification

Completed:

```text
cmake --build build --config Release
100% tests passed, 0 tests failed out of 13
cmake --install build --config Release --prefix phase19_install
Installed CLI doctor smoke passed on LLAMA-GPT4Q
```

Observed real-model doctor result:

```text
overall_status: WARN
recommended_mode: SURVIVAL
hardware_fit_mode: BALANCED
runtime_gap: true
BALANCED hardware_suitable: true
BALANCED runtime_available: false
```

## R10: Cached Decode Attention Primitive

### Status

Completed and verified as a native CUDA primitive.

### What Changed

- Added `launch_store_kv_cache_token(...)`.
- Added `launch_causal_attention_decode(...)`.
- Added CUDA kernels that:
  - store one token's K/V vectors into a contiguous cache
  - compute one-token decode attention over cached K/V history
- Added transformer executor coverage proving cached decode attention matches
  the last-token output of causal prefill attention for the same sequence.
- Updated native build metadata to report the R10 primitive.

### Retrospective

This is not the full optimized decoder yet, but it is the correct first native
step. Before replacing repeated full-prefill generation, RIFT needs a trusted
decode-attention primitive that can be compared against the known-good prefill
path. That now exists.

### LLM User / Developer Notes

Additional feature idea: add a debug mode that compares optimized decode logits
against repeated-prefill logits for the first few tokens, then automatically
falls back if divergence exceeds a threshold.

### Verification

Completed:

```text
cmake --build build --config Release
100% tests passed, 0 tests failed out of 13
transformer executor cached decode attention matched prefill tail
```

### Remaining Work

R10 still needs integration into full generation:

- allocate per-layer K/V cache tensors
- write real projected K/V during prefill
- use cached K/V during decode layers
- compare optimized decode logits against repeated-prefill logits
- expose optimized decode through Python `generate(...)`

## R11-R17: Seven-Phase Post-MVP Product Bridge

### Status

Completed and verified.

### Phase Breakdown

- **R11 Decode Readiness Contract**
  - Added `RiftEngine.decode_readiness()`.
  - Added CLI command `rift decode-readiness`.
  - Reports cached decode-attention primitive availability and full integration blockers.
- **R12 BALANCED Cache Budget Contract**
  - Added BALANCED cache planning inside mode analysis.
  - Plans now include `balanced_cache_plan`.
  - BALANCED remains `runtime_available=false` until tensor-cache execution is real.
- **R13 Rich Benchmark And Report Metrics**
  - Added derived first-token, per-token, p50, and p95 latency fields.
  - Reports now include `decode_path` and mode-analysis context.
- **R14 Serving Hardening**
  - Added server busy state and single-request guard.
  - Added MVP SSE streaming responses for `/v1/completions` and `/v1/chat/completions`.
- **R15 Report History And Dashboard APIs**
  - Added `.rift/reports/*.riftreport.json` history writes.
  - Added `RiftEngine.list_reports(...)`.
  - Added dashboard/API report-history routes.
- **R16 Model Breadth Advice**
  - Added `RiftEngine.compatibility_advice(...)`.
  - Added CLI command `rift compat --model <path>`.
  - Added advice for LLaMA GPTQ, GGUF, Qwen, Mistral, Gemma, Phi, and unknown SafeTensors.
- **R17 Release Hardening**
  - Added tests for RIFT product layer and server streaming routes.
  - Updated docs and command surfaces.
  - Updated build info to report RIFT phase R17.

### Retrospective

These phases do not magically make BALANCED/FAST execution real, and they should
not. They make RIFT honest and substantially more useful while the native
runtime catches up: users can see what should fit, what can run now, what mode
gap exists, what backend is recommended, and what metrics came from actual runs.

### LLM User / Developer Notes

Additional feature idea: add a "confidence" score to compatibility advice that
separates exact support, likely support, adapter-pending support, and external
backend recommendation.

### Verification

Completed:

```text
cmake --build build --config Release
100% tests passed, 0 tests failed out of 14
```

### Current Capability

RIFT now has a richer post-MVP product shell around the native runtime:

```text
doctor -> compat -> decode-readiness -> plan -> run -> report history -> serve streaming
```

The executable generation backend is still SURVIVAL. BALANCED is now planned in
detail, but its runtime remains pending.

## R18: Hugging Face Hub Pull

### Status

Completed and verified with a local Hub-compatible test server.

### What Changed

- Added a stdlib-only `HfHubClient`.
- Added `RiftEngine.pull_model_from_hub(...)`.
- Added CLI command:

```bash
rift pull <org/model> --dry-run
rift pull <org/model> --output <local-folder>
```

- Added filtered snapshot downloads:
  - default includes: SafeTensors, GGUF, JSON/tokenizer, model/text metadata
  - default ignores: `.bin`, `.pt`, `.pth`, ONNX, H5, msgpack blobs
- Added revision pinning, alternate endpoint support, token support through
  argument or `HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN`, and `--max-bytes`.
- Added dashboard API route `POST /api/rift/pull`.
- Added a small dashboard Hub Pull panel.

### Retrospective

This makes RIFT less awkward to use. Users no longer need to manually download
a checkpoint before asking RIFT whether it fits their PC. The important product
guardrail is `--dry-run`: RIFT can show the exact selected files and byte count
before pulling a multi-gigabyte repository.

### LLM User / Developer Notes

Additional feature idea: add a model-card compatibility preflight that reads
Hub metadata before download and labels likely adapter support, license notes,
and expected disk/VRAM/RAM fit.

### Verification

Completed:

```text
python tests/hf_hub_tests.py
python tests/dashboard_tests.py
python tests/rift_tests.py
cmake --build build --config Release
100% tests passed, 0 tests failed out of 15
```

### Current Capability

RIFT can now run:

```text
pull -> inspect -> doctor -> compat -> plan -> run -> report -> serve
```

`pull` downloads a filtered Hugging Face Hub snapshot into a local directory and
then optionally runs RIFT inspection/advice on the downloaded model folder.

## R19: Optimized Hub Scout And Hardware-Aware Recommender

### Status

Completed and verified.

### What Changed

- Extended `HfHubClient` with bounded model search, selective metadata
  expansion, and a 24-hour local metadata cache under `.rift/hub_cache/`.
- Added `RiftEngine.recommend_models(...)`.
- Added CLI command:

```bash
rift recommend --task chat
rift recommend --task coding --mode balanced --top 10
rift recommend --formats gptq,gguf,safetensors
rift recommend --max-download-gb 12
rift recommend --pull-best --output .\models\best
rift recommend --refresh
rift recommend --write-report recommendations.json
```

- Added dashboard route `POST /api/rift/recommend`.
- Added dashboard model cards with score breakdowns, evidence, warnings,
  backend advice, and pull commands.
- Added a mode-free `best_for_hardware` summary with `best_performance`,
  `best_accuracy_proxy`, and `best_overall`.
- Added `absolute_best` and a simplified `answer` block for users who just want
  to know which model to run on the laptop.
- Changed recommendation ranking to be laptop-first instead of
  RIFT-runtime-first. Native runtime readiness is still reported, but does not
  determine the top recommendation.
- Added parameter/format-based size estimation for Hub repositories that do not
  expose complete file sizes.
- Added `rift reccommend` as a forgiving alias for `rift recommend`.
- Moved CUDA survival-runtime implementation units to `src/Survival/`.
- Added fake-Hub tests for caching, filtering, enrichment caps, scoring,
  dashboard route coverage, CLI report writing, and optional pull-best wiring.

### Retrospective

This is a useful product step because it changes the user journey from
"browse the model zoo and hope" to "ask RIFT what is realistic on this PC."
The recommender is intentionally bounded: it does not crawl the whole Hub, and
it does not pretend that likes/downloads equal model quality. It surfaces
confidence and evidence so recommendations remain explainable.

### LLM User / Developer Notes

Additional feature idea: add a local "model fit notebook" export that compares
the top recommendations side by side with expected download size, backend,
native-readiness, and a one-click `rift pull` command.

### Verification

Verification completed:

```text
python tests/recommend_tests.py
python tests/dashboard_tests.py
python tests/hf_hub_tests.py
python tests/rift_tests.py
python tests/server_tests.py
cmake --build build --config Release
100% tests passed, 0 tests failed out of 16
```

Focused Python tests and the full native CTest suite passed.

### Current Capability

RIFT can now run:

```text
recommend -> pull -> inspect -> doctor -> compat -> plan -> run -> report -> serve
```

`recommend` returns ranked Hugging Face candidates with hardware fit, expected
speed, quality proxy, safety/trust, popularity/community, confidence, warnings,
backend advice, and pull commands.

Latest live hardware report:

```text
.rift\reports\hardware-model-recommendations-r19.json
.rift\reports\laptop-best-model-r19.json
```

The latest report was generated against the RTX 4060 Laptop GPU / 16 GB RAM
workstation profile using 9 bounded Hub query arms and 50 enriched finalists.

```text
Best model for this laptop: Qwen/Qwen2.5-7B-Instruct-GGUF
Best speed: Qwen/Qwen1.5-0.5B-Chat-GPTQ-Int4
Best quality proxy: Qwen/Qwen2.5-7B-Instruct-GGUF
```
