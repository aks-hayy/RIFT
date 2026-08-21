# RIFT Post-MVP Phases

RIFT MVP R0-R8 proved the product loop:

```text
inspect -> benchmark -> plan -> run -> report -> serve/dashboard
```

The post-MVP goal is to make RIFT useful beyond a correctness-first SURVIVAL
path.

## Phase R9: Doctor And Fit-Aware Planner

Goal: explain the difference between what the hardware/model pair should be
able to do and what the current runtime can execute.

Deliverables:

- `rift doctor`.
- Hardware/model readiness checks.
- Mode analysis:
  - best hardware-fit mode
  - best executable mode
  - runtime gap
  - candidate mode details
- Plans preserve executable `recommended_mode` while also reporting
  `hardware_fit_mode`.

## Phase R10: Optimized Decode Correctness

Goal: remove repeated full-prefill decode as the default correctness path.

Deliverables:

- Write per-layer K/V tensors into paged KV cache.
- Read historical K/V during decode attention.
- Compare optimized decode logits against repeated-prefill logits on short
  prompts.
- Keep repeated-prefill as fallback.

## Phase R11: BALANCED Runtime

Goal: make the first non-survival execution mode real.

Deliverables:

- VRAM/RAM tensor cache.
- Quantized metadata cache.
- Dense `lm_head` tile/cache policy.
- Plan selection for BALANCED when model fits with cache reuse.
- Report memory hit rate and cache reuse.

## Phase R12: FAST Runtime

Goal: run mostly GPU-resident when the model and context fit comfortably.

Deliverables:

- GPU residency planner.
- Persistent layer/tensor placement.
- Avoid disk streaming for hot model paths.
- FAST plan activation when memory constraints are satisfied.

## Phase R13: Serving Hardening

Goal: make local serving practical.

Deliverables:

- Streaming responses.
- Request queue and cancellation.
- `/v1/chat/completions` compatibility polish.
- Report latest queue, latency, and backend state.

## Phase R14: Broader Model Inspection

Goal: make RIFT useful even when it cannot run a model natively.

Deliverables:

- Qwen, Mistral, Gemma, Phi adapter reports.
- GGUF inspect support.
- External backend recommendations.
- Compatibility explanations that users can act on.

## Phase R15: Benchmark Comparisons

Goal: make RIFT reports credible against common local runtimes.

Deliverables:

- Repeatable benchmark harness.
- First-token latency and decode tok/s.
- Peak VRAM/RAM tracking.
- Disk and H2D metrics.
- Exportable comparison reports.

## Seven-Phase Implementation Track: R11-R17

The remaining MVP-to-useful bridge is split into these seven implementation
phases:

### R11: Decode Readiness Contract

- Expose whether cached decode attention primitives exist.
- Keep full-generation optimized decode marked unavailable until real layer
  integration is complete.
- Report the fallback path clearly.

### R12: BALANCED Cache Budget Contract

- Estimate VRAM/host cache budgets.
- Report cacheable weight fraction.
- Keep `runtime_available=false` until tensor-cache execution lands.

### R13: Rich Benchmark And Report Metrics

- Add first-token, per-token, p50, and p95 latency fields.
- Preserve disk/H2D estimates.
- Keep metrics honest when they are derived from a single generation call.

### R14: Serving Hardening

- Add single-request busy guard.
- Expose busy state.
- Add MVP SSE streaming response support.

### R15: Report History And Dashboard APIs

- Store historical reports.
- Add report listing APIs.
- Surface compatibility and report history through dashboard routes.

### R16: Model Breadth Advice

- Add compatibility advice for LLAMA GPTQ, GGUF, Qwen, Mistral, Gemma, Phi, and
  unknown SafeTensors models.
- Recommend external backends when native RIFT support is not ready.

### R17: Release Hardening

- Update docs and tests.
- Keep build/install verification green.
- Leave unsupported runtime modes explicitly marked pending.
