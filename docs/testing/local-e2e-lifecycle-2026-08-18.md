# RIFT Local End-to-End Lifecycle Test

Date: 2026-08-18  
Node: `AksAsh`  
Execution policy: RIFT CLI only for discovery, installation, model acquisition, planning, deployment, monitoring, benchmarking, tuning, recovery, and teardown.

## Test Target

- GPU: NVIDIA GeForce RTX 4060 Laptop GPU
- VRAM: 8,585,216,000 bytes reported by RIFT
- Host RAM: 16,849,272,832 bytes reported by RIFT
- CUDA capability: 8.9
- PCIe: Gen 4 x8 observed by RIFT
- OS: Windows 11
- Model: `Qwen2.5-1.5B-Instruct-Q4_K_M.gguf`
- Model size: 986,048,768 bytes
- Backend: RIFT-managed `llama.cpp`
- Service: `chat`

This is a lifecycle smoke test. It proves the control-plane path and a real local prompt; it does not establish 30B quality, 30B memory fit, or production availability.

## RIFT Lifecycle

1. **Hardware preflight**
   - Ran `rift system hardware`.
   - RIFT observed CUDA, the RTX 4060 Laptop GPU, 16 GB host RAM, and about 33 GB free disk before acquisition.
   - The disk guard retained its configured safety reserve before the model pull.

2. **Backend detection and installation**
   - Ran `rift backend detect llama.cpp`; it was initially unavailable.
   - Ran `rift backend install llama.cpp --allow-install --variant cuda13`.
   - RIFT installed the managed backend under `.rift/backends/llama.cpp`.
   - Final detected executable: `.rift/backends/llama.cpp/llama-server.exe`.
   - Detected build: `0.1.2-dev`, build `10488`, commit `9d77fa172`.

3. **Artifact resolution, pull, and verification**
   - RIFT resolved the exact `Q4_K_M` GGUF file instead of pulling an ambiguous repository.
   - RIFT dry-run confirmed the file size and usable disk budget.
   - RIFT pulled the artifact into `models/rift-selected`.
   - RIFT verified the model successfully with SHA-256:
     `1adf0b11065d8ad2e8123ea110d1ec956dab4ab038eab665614adba04b6c3370`.

4. **Configuration and plan**
   - RIFT generated `.rift/generated/e2e.rift.yaml` from the local artifact source.
   - The generated plan selected `llama.cpp`, GPU offload, context `8192`, batch `512`, ubatch `128`, and `8` threads.
   - `rift plan` produced one launch action and no implicit install or download action.

5. **Apply and health**
   - Ran `rift apply --config .rift/generated/e2e.rift.yaml --allow-launch`.
   - RIFT launched the managed service on `http://127.0.0.1:11735`.
   - RIFT health returned HTTP `200` with `{"status":"ok"}`.
   - RIFT process monitoring returned two healthy samples.

6. **Real prompt**
   - Ran the RIFT benchmark command with the prompt requiring `RIFT_E2E_OK`.
   - HTTP `200`; the model returned the exact requested text.
   - Measured decode throughput: `94.75 tok/s` for the short prompt.

7. **Benchmark suite**
   - Ran the RIFT suite with one warmup and three repetitions across chat, structured JSON, and coding prompts.
   - All 9 measured requests were valid HTTP `200` responses.
   - Median decode throughput by case:
     - chat: `150.31 tok/s`
     - structured: `153.68 tok/s`
     - coding: `153.42 tok/s`
   - Suite summary: valid, 3 cases, p95 elapsed time `0.656184 s`.
   - Full evidence: `.rift/reports/1787062576-chat-benchmark-suite.json`.

8. **Live tuning**
   - RIFT tested three batch candidates: `512`, `256`, and `768`.
   - Every candidate passed startup, health, and generation checks.
   - Winning configuration remained the baseline: batch `512`, ubatch `128`, GPU layers `999`, threads `8`.
   - The measured winner was `138.27 tok/s` in the fixed tuning prompt; measured improvement was `0%`, so RIFT correctly kept the baseline.
   - Full evidence: `.rift/reports/1787062705-chat-live-tuning.json`.

9. **Recovery**
   - Ran RIFT's explicit service restart/recovery command with launch permission.
   - RIFT recorded one incident, terminated the old managed PID, launched a replacement, and reported `restart_count: 1`.
   - Two post-recovery monitor samples were healthy.
   - The replacement returned the exact prompt response `RIFT_RECOVERY_OK` with HTTP `200`.
   - Incident evidence: `.rift/reports/e2e-incidents-all.json`.

10. **Teardown**
    - Ran `rift destroy --service chat --yes`.
    - Final RIFT status reported service `stopped`, desired state `stopped`, and `process_alive: false`.
    - The model and managed backend files were retained; teardown stopped the service only.
    - Final observed free disk: about `28.46 GB`.

## Result

**PASS: local control-plane lifecycle smoke test.** RIFT completed the operational path of hardware inspection, gated backend installation, exact artifact acquisition, integrity verification, justified planning, deployment, health monitoring, real generation, suite benchmarking, bounded live tuning, controlled recovery, and clean teardown.

## What This Does Not Prove

- It does not prove that a 30B model fits or generates acceptably on this laptop.
- It does not benchmark model quality against an external evaluation set.
- The recovery test exercises RIFT-managed restart, not an externally killed process or machine loss.
- The RIFT gateway was not started in this run; the backend endpoint was tested directly through RIFT's benchmark command.
- The optional native-survival experiments were outside this lifecycle; the
  tested path used the managed external `llama.cpp` provider.

This report predates the platform runtime-path migration. Its `.rift/`
references identify the original evidence location; current state and reports
belong under the platform-specific `RIFT_HOME` directory.

## Evidence Files

- `.rift/reports/e2e-destroy.json`
- `.rift/reports/e2e-final-status.json`
- `.rift/reports/e2e-final-hardware.json`
- `.rift/reports/e2e-post-tune-benchmark.json`
- `.rift/reports/e2e-recovery.json`
- `.rift/reports/e2e-recovery-benchmark.json`
- `.rift/reports/e2e-recovery-monitor.json`
- `.rift/reports/1787062576-chat-benchmark-suite.json`
- `.rift/reports/1787062705-chat-live-tuning.json`
