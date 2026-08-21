# One-Off 30-Node RIFT Acceptance Test

Date: 2026-08-18  
Host: Windows 11, NVIDIA GeForce RTX 4060 Laptop GPU, 8 GB VRAM, 16 GB RAM  
Purpose: disposable development validation only; no new `rift lab` product command was added.

## Execution Boundaries

- RIFT CLI/API was used for discovery, backend diagnostics, install plans, cluster planning, deployment state, monitoring, benchmarking, tuning, failure injection, recovery, service launch, gateway routing, and teardown.
- Docker Desktop was started only for the disposable container layer and stopped again after cleanup.
- No additional backend was installed.
- No additional model was downloaded. The already verified local `Qwen2.5-1.5B-Instruct-Q4_K_M.gguf` artifact was reused for the real service tests.
- The 30 Docker containers were low-resource node shells from an image already present locally. They were not GPU workers and did not claim to be physical RIFT nodes.

## 1. Control-Plane Simulation

### Discovery gate

The RIFT emulated controller inspected 30 declared node profiles:

- 3 strong CUDA workstations
- 2 workstation CUDA nodes
- 12 consumer CUDA nodes
- 4 weak CUDA nodes
- 4 CPU edge nodes
- 3 mobile-like nodes
- 2 Apple/MLX nodes

Result: **30/30 ready** with `deterministic_emulation` evidence.

### Format and backend planning

The scenario included GGUF, AWQ, GPTQ, dense SafeTensors, and MLX artifacts. RIFT generated read-only install plans for llama.cpp, vLLM, SGLang, and MLX-LM. All plans required explicit permission; no installation ran.

The placement plan scheduled all 26 requested replicas across 16 nodes:

- llama.cpp: 14 replicas
- vLLM: 6 replicas
- SGLang: 4 replicas
- MLX-LM: 2 replicas

No replica was unscheduled.

### Controller lifecycle

- Applied 26 emulated instances.
- Monitored all instances as running.
- Produced deterministic benchmark results for all 26 instances.
- Aggregate simulated throughput: `931.757 tok/s`.
- Tuned all 26 instances with deterministic candidate settings.
- Injected a laptop node loss; RIFT rescheduled `chat-5`.
- Injected a process crash; RIFT restarted `chat-0`.
- Injected a network partition; RIFT rescheduled two affected instances.
- Final emulated state: 26/26 running, 4 incidents recorded.
- Placement rejected 437 infeasible node/replica combinations based on capacity, backend, labels, or reachability rather than overcommitting.

**Control-plane result: PASS for local deterministic emulation.**

This does not prove physical 30-node behavior, distributed consensus, or real remote transport.

## 2. Service Simulation

Two real RIFT-managed llama.cpp services were launched on separate local ports using the verified 986 MB GGUF artifact:

- `gpu-primary`: port `11735`
- `gpu-secondary`: port `11736`

Results:

- Both services passed health monitoring.
- Direct RIFT benchmarks returned HTTP `200`.
- Initial measured decode throughput: approximately `81.99 tok/s` and `78.93 tok/s`.
- Live tuning ran on both services and applied winning configurations.
- Fixed tuning measurements selected approximately `136.51 tok/s` and `135.64 tok/s` winners.
- The RIFT gateway forwarded `RIFT_GATEWAY_OK` with HTTP `200`.
- Eight concurrent gateway requests produced `2 x 200` and `6 x 429`, demonstrating concurrency/rate rejection.
- After RIFT stopped `gpu-primary`, the gateway returned `RIFT_FALLBACK_OK` from `gpu-secondary` with HTTP `200`.
- RIFT restored both services and observed three healthy monitor samples before teardown.

**Service result: PASS for local real-process serving, tuning, gateway forwarding, rate limiting, and fallback.**

## 3. Hardware Calibration

RIFT measured the actual workstation after the service test:

- Sequential disk read: `678.668 MiB/s`
- Sequential disk write: `843.233 MiB/s`
- Pinned CUDA H2D bandwidth: `13.404 GB/s`
- Free VRAM after teardown: `6.93 GB`
- Free host RAM after teardown: `5.11 GB`
- GPU temperature: `50 C`
- GPU utilization: `5%`
- PCIe: `Gen 4 x8`
- Free disk: `37.45 GB`

The real service benchmarks measured throughput and latency under local execution. The run also exercised contention between two live services during tuning. RIFT did not emit a separate model-load-time breakdown or a long thermal-throttling curve in this run, so those remain measurement gaps.

**Hardware result: PASS for bounded storage/H2D/telemetry calibration; incomplete for long-run thermal and model-load characterization.**

## Cleanup Verification

- Docker test containers remaining: `0`
- Test Docker networks remaining: `0`
- Docker Desktop returned to stopped state
- Temporary root config removed
- RIFT service records: `3`, all stopped
- Managed `llama-server` processes remaining: `0`
- Evidence reports retained under `.rift/reports/`

During cleanup, RIFT changed all service records to stopped but three detached `llama-server` child processes remained. They were terminated by matching the executable path to RIFT's managed backend directory. This is a real lifecycle defect: RIFT needs stronger child-process ownership and reaping before claiming production-grade teardown.

## Overall Assessment

The one-off test proves that RIFT's local control plane, model/backend planning, real llama.cpp serving, gateway protections, tuning, fallback, and deterministic heterogeneous placement all work together.

It does **not** yet prove:

- real 30-node RIFT-agent networking;
- physical multi-GPU scheduling;
- distributed state consistency;
- long-duration thermal stability;
- exact model-load accounting;
- production-safe child-process teardown without an external cleanup guard.

Overall acceptance: **PASS with a process-lifecycle defect and physical-cluster validation still outstanding.**

## Evidence

- `.rift/reports/cluster30-discovery.json`
- `.rift/reports/cluster30-plan.json`
- `.rift/reports/cluster30-apply.json`
- `.rift/reports/cluster30-benchmark.json`
- `.rift/reports/cluster30-tune.json`
- `.rift/reports/cluster30-node-recovery.json`
- `.rift/reports/cluster30-process-recovery.json`
- `.rift/reports/cluster30-network-recovery.json`
- `.rift/reports/e2e-gateway-routing-rate.json`
- `.rift/reports/e2e-gateway-fallback.json`
- `.rift/reports/1787077276-gpu-primary-live-tuning.json`
- `.rift/reports/1787077285-gpu-secondary-live-tuning.json`
- `.rift/reports/e2e-hardware-calibration.json`
- `.rift/reports/e2e-final-clean-status.json`

