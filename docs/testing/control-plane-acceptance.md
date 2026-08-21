# RIFT Control-Plane Acceptance Report

Date: 2026-07-12

## Scope

This report verifies the first Kubernetes-like RIFT control-plane foundation:
desired-state reconciliation, readiness/liveness monitoring, benchmark-driven
tuning, bounded local recovery, resource-aware placement, and emulated
cross-node recovery.

## Operational Design

The implementation follows these rules:

- desired state and observed state are stored separately;
- process liveness, HTTP readiness, and startup grace have distinct meanings;
- transient readiness failure must cross a threshold before restart;
- crashes use bounded restart attempts and exponential backoff;
- tuning is a transaction with a last-known-good rollback target;
- cluster scheduling filters infeasible nodes before scoring feasible nodes;
- node failure may reschedule only when backend and resource constraints still
  fit on a replacement node;
- fault recovery always requires an explicit authorization flag.

## Local Workstation

Hardware and service under test:

```text
GPU: NVIDIA GeForce RTX 4060 Laptop GPU, 8 GB VRAM
RAM: approximately 16 GB
Backend: llama.cpp 9957
Model: Llama 3.2 1B Instruct Q8_0 GGUF
Endpoint: http://127.0.0.1:11735/v1
```

Lifecycle exercised:

1. RIFT planned the local deployment and verified backend/model fit.
2. Two monitor samples confirmed a live PID and HTTP `200 /health`.
3. Baseline generation produced a valid 64-token response.
4. Live tuning tested batches 256, 512, and 768 with warmup and repeated runs.
5. Batch 768 won at `155.992 tok/s`, a measured `1.280%` gain over the
   `154.020 tok/s` baseline.
6. The backend process was observed dead after the controlled tuning lifecycle.
7. RIFT recorded the crash and refused non-authorized recovery.
8. Authorized recovery relaunched the last-known-good batch-768 plan as PID
   `5164`.
9. Two monitor samples confirmed readiness after restart.
10. A post-recovery request returned exactly `RIFT_RECOVERY_OK` at
    `142.019 tok/s` with estimated first-token latency of `48.789 ms`.

Final local state: healthy, process alive, restart count 1.

## Emulated Cluster

Nodes:

```text
laptop-4060:      8 GB VRAM, 16 GB RAM, llama.cpp
workstation-4090: 24 GB VRAM, 64 GB RAM, llama.cpp/vLLM/SGLang
cpu-edge:         CPU-only, 32 GB RAM, llama.cpp
```

Placements:

```text
chat-0  -> laptop-4060       llama.cpp / 7B GGUF
chat-1  -> workstation-4090  llama.cpp / 7B GGUF
coder-0 -> workstation-4090  vLLM / 14B AWQ
```

All three replicas passed feasibility and were deployed into emulated desired
state. The initial aggregate estimate was `39.190 tok/s`.

Tuning results:

```text
chat-0:  0.000% gain; baseline retained
chat-1:  9.890% gain; batch 1024 selected
coder-0: 9.896% gain; max_num_batched_tokens 1024 selected
```

Recovery tests:

- `coder-0` process crash: detected, withheld without permission, then restarted
  on the same node.
- `laptop-4060` node loss: node marked NotReady; `chat-0` was rescheduled to the
  24 GB node after backend and capacity checks.
- Final desired state: all three instances Running, two incidents persisted.

Cluster timing values are deterministic emulation and must not be presented as
physical hardware benchmarks.

## Verification

```text
CMake configure: passed
Native/Python build: passed
CTest: 19/19 passed
Installed CLI: local monitor/benchmark/tune/recover passed
Installed CLI: cluster check/plan/deploy/monitor/benchmark/tune/recover passed
```

## Remaining Boundary

RIFT now has a tested controller and scheduler contract, but is not yet a
replacement for a production Kubernetes cluster. Real remote execution needs a
secure node agent or SSH transport, durable replicated state, leader election,
artifact distribution, rolling/canary updates, graceful request draining,
distributed rate-limit state, and production metrics export.
