# llama.cpp profile re-verification

Run date: 2026-09-05
Backend: llama.cpp `0.3.0-dev` (build 10665, commit `ca3d5a3e1`)
Host: local workstation GPU; host and device capacity were measured locally
Workload: natural-language coding-assistant prompt, one request stream, 8,192-token context, 64-token completion, one warmup, five measured repetitions.
Quality gate: RIFT's six-case deterministic suite; every accepted run scored `1.0` with all six cases passing.

## What was tested

To make the value of tuning visible, each model was first deployed with a deliberately conservative, ordinary llama.cpp-style configuration. The model artifact and `Q4_K_M` weight quantization were kept fixed throughout. RIFT then restarted the service for a bounded set of 24 candidate configurations, measured each candidate, ran the quality gate on the shortlist, and only promoted a statistically reliable improvement.

The baseline for the 3B and 7B speed runs and the selected 7B cost run was:

```text
batch=64, ubatch=32, threads=1, threads_batch=1, gpu_layers=999
flash_attn=on, cache_type_k=q8_0, cache_type_v=q8_0
kv_offload=false, kv_unified=false, op_offload=false, repack=false
ngram_speculation=false, context=8192, concurrency=1
```

The 3B cost run used the same baseline. `flash_attn=on` is required by this llama.cpp build when a quantized V cache is selected.

Artifacts were local and already cached; no download occurred during tuning:

| Model artifact | Weight quantization | SHA-256 |
| --- | --- | --- |
| `qwen2.5-3b-instruct-q4_k_m.gguf` | `Q4_K_M` | `626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d` |
| `Qwen2.5-7B-Instruct-Q4_K_M.gguf` | `Q4_K_M` | `65b8fcd92af6b4fefa935c625d1ac27ea29dcb6ee14589c55a8f115ceaaa1423` |

## Results

| Model/profile | Baseline | Promoted/final result | Change | Quality | Outcome |
| --- | ---: | ---: | ---: | ---: | --- |
| Qwen2.5 3B · Speed | 72.6386 tok/s | 81.5624 tok/s (final retest) | **+12.29%** | 1.00 | Promoted |
| Qwen2.5 3B · Cost | 44.6906 GPU J/req | 31.4054 GPU J/req (final retest) | **−29.73%** | 1.00 | Promoted |
| Qwen2.5 7B · Speed | 32.3785 tok/s | 44.4110 tok/s (final retest) | **+37.16%** | 1.00 | Promoted |
| Qwen2.5 7B · Cost | 79.4569 GPU J/req | 78.4110 GPU J/req (best passing point estimate) | −1.32%* | 1.00 | Baseline retained |

\* The 7B cost point estimate did not pass RIFT's confidence gate: its 95% improvement interval crossed zero. RIFT therefore did not apply it. This is an intentional safety result, not a missing measurement. The lower-energy Q4 K/V candidates were also rejected by the quality gate, so changing cache precision would not have been a valid “cost win.”

## How the Cost profile works

Cost profiling is an energy experiment, not a guess based on one llama.cpp
flag. RIFT warms the service, sends the same workload repeatedly, and runs an
isolated GPU power sampler around each measured request. The sampler integrates
`nvidia-smi power.draw` over time, then RIFT divides the accumulated GPU joules
by the number of completed requests. It records latency, failures, and process
CPU time alongside the energy result.

The sampler measures aggregate power for the GPU device, so unrelated work
sharing that GPU can contribute to the reading. RIFT exposes that attribution
limit instead of presenting it as per-process electrical precision.

Candidates are generated deterministically from the backend capabilities and
tested one at a time. The bounded search used for this verification covered:

- K/V cache precision pairs: `f16`, `q8_0`, `q4_0`, `q4_1`, `iq4_nl`, plus selected mixed pairs and precision-plus-batch combinations.
- Batch and micro-batch sizes: baseline `64/32`, then batch sizes `128`, `256`, `512`, `1024`, and `2048` with a micro-batch no larger than `128`.
- CPU execution: `threads` and `threads_batch` values spanning 1, half the physical cores, all physical cores, and logical processors.
- Attention and scheduling: Flash Attention `on/off/auto`, polling `0/25/50`, batch polling `0/1/25`, continuous batching, and parallel-slot values derived from the requested concurrency.
- Runtime memory and execution controls: unified KV cache, KV offload, operation offload, repacking, host-memory use, and load mode (`auto`, `mmap`, `mlock`, `mmap+mlock`).
- Host placement controls when advertised by the binary: priority, CPU affinity, and NUMA (NUMA is platform-gated and was not enabled on Windows).

The installed llama-server is probed first; a family is included only when the
binary advertises the corresponding flag. Unsupported controls are omitted
before launch, and startup failures are recorded as candidate rejections rather
than being treated as tuning wins.

Model identity, the `Q4_K_M` weight quantization, context length, concurrency, and
GPU layer placement were held constant. N-gram speculation was explicitly off
for these runs, so speculative-decoding controls were not part of this result.

For a candidate to remain eligible, it must start cleanly, complete without
request failures, pass the deterministic quality suite, avoid more than a 10%
latency regression or CPU-work increase, and show a positive 95% improvement
interval for energy per request. RIFT then restarts the selected configuration
and performs a fresh final retest. If that retest is not repeatable, the
baseline is restored. That is why the 7B cost run retains its baseline even
though one point estimate looked slightly lower.

The final retest is the number used for promotion. For example, the 3B speed
candidate briefly measured 85.4928 tok/s, but RIFT re-tested the applied
configuration and recorded 81.5624 tok/s with a 95% lower bound of 79.3516
tok/s. The 7B speed final lower bound was 43.1938 tok/s.

## Audit trail

The complete candidate journals (including launch commands, measurements, confidence intervals, quality responses/hashes, startup failures, and rejected candidates) are retained in the runtime report directory:

```text
.rift-runtime/reports/1788612008244875300-chat-profiled-tuning-speed.json
.rift-runtime/reports/1788612283637981000-chat-profiled-tuning-cost.json
.rift-runtime/reports/1788613459651192900-chat-profiled-tuning-speed.json
.rift-runtime/reports/1788615307328553100-chat-profiled-tuning-cost.json
```

The 7B speed journal records one HTTP-500 candidate measurement and one startup failure as candidate-local rejections; the remaining candidates were still evaluated. The 7B cost journal records five quality-safe candidates, but none had a confidence interval proving a lower energy/request, so the baseline was restored. These behaviours demonstrate bounded search, quality protection, and rollback rather than cherry-picking a noisy point estimate.

Raw run IDs:

```text
3B speed  tune-2cb864a8abd244f7a1d3
3B cost   tune-5bd0e843ea364fef8254
7B speed  tune-9cfbf3739e62429aa8ff
7B cost   tune-e068b464a4844546a1d7
```

The profile invocations were equivalent to:

```powershell
rift tune --service chat --profile speed --allow-restart --yes --candidate-limit 24 --warmups 1 --repeats 5 --budget 12m --max-tokens 64 --target-tokens-per-second 1 --no-ngram-speculation
rift tune --service chat --profile cost  --allow-restart --yes --candidate-limit 24 --warmups 1 --repeats 5 --budget 12m --max-tokens 64 --target-tokens-per-second 1 --no-ngram-speculation
```

The 7B cost confirmation was repeated with ten measurements before the final
baseline-retained decision; the evidence table reports that statistically
defensible run rather than an earlier noisy point estimate.
