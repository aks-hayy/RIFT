# RIFT easy-path workload deployment evidence — 2026-09-14

This record is from a live CLI run on the local workstation. It is deliberately
limited to facts persisted by RIFT's workload journal and tuning journal; no
synthetic success values are used.

## Workload and interaction

Natural-language request submitted to the CLI:

> Deploy a private local Qwen2.5-7B coding assistant. It must sustain at least 1 token per second for one user with a 2K context window, remain offline, and favor speed.

RIFT compiled and displayed the contract, then required one explicit approval.
The approval envelope allowed local launch, restart, promotion, and cleanup;
downloads and remote execution were disabled. The model family was inferred
from the request, while the backend was selected from the local GGUF artifact
and runtime availability (llama.cpp), not supplied as a tuning argument.

| Item | Recorded value |
|---|---|
| Draft | `da9fa4a3c1e449f09893a8bf47558533` |
| Contract hash | `2bac5d7bd77dd6abcdb8f5da3f555b4c239879be45a70ba1aa95a8dc8b505c20` |
| Approval | `7c6510eb3ccc42fb92205333de20cde5` |
| Model artifact | Qwen2.5-7B-Instruct-Q4_K_M.gguf (local) |
| Backend/runtime | llama.cpp `0.3.0-dev`, build 10665 |
| Workload run | `fa2eac192bba4a4e8b7ed9f6d1f86b46` |
| Deployment outcome | `VERIFIED` |
| Run wall time | 16.34 s (journal creation to terminal verification) |
| Fresh benchmark | 15 samples; median 146.63 decode tok/s |
| Quality gate | `rift-text-core/v1`, required `response_nonempty`: PASS |
| Context/concurrency | requested 2,048 tokens; launched capacity 8,192; concurrency 1 |

The successful run reached readiness, ran fresh benchmark and quality checks,
and promoted the endpoint. The service was then stopped with RIFT's stop path.

## Tuning stability run

To exercise automatic tuning rather than merely demonstrate a baseline that
already passed, a second natural-language contract raised the hard speed gate
to 160 tok/s while keeping the same model, offline policy, 2K request context,
and Q4_K_M artifact. It used a two-configuration tuning envelope.

| Item | Recorded value |
|---|---|
| Draft | `1822bd080fc743e991130ee20f6b6e57` |
| Contract hash | `05f018d9c11c068c7b3879f974160fb8dae043529af46b2e6b50c798493f0792` |
| Approval | `c1fd20d6248548ddb9b8d10b338a3ef8` |
| Workload run | `a0f99c946b0f4ce78c282d38ca824f9d` |
| Workload outcome | `EXHAUSTED` (160 tok/s was not defensibly achieved) |
| Tuning run | `tune-a6eecbed414d47e698f5` |
| Tuning outcome | `no_improvement`; baseline restored and health rechecked |
| Baseline measurement | 149.84 tok/s |
| Candidate measurement | 150.65 tok/s |
| Improvement interval | −2.75% to +3.80%; crosses zero, so not promotable |
| Locked throughout | model SHA-256, Q4_K_M weight quantization, context 8,192, concurrency 1, K/V cache f16 |
| Candidate lifecycle | stop previous trial → launch candidate → readiness check → measure → restore baseline |

The candidate did not receive a promotion because its uncertainty interval
included no improvement. This is an intentional defensibility result, not a
claim that a 0.5% point estimate is a win. RIFT restored the healthy baseline
before the workload run terminated. The tuning report is retained in the local
runtime report directory and is referenced by the workload journal.

The first two-candidate screen deliberately materialized the existing f16 K/V
lock as its only alternative; it did not silently claim that this was a new
effective runtime optimization. A broader four-candidate screen then exercised
actual K/V alternatives:

Raw tuning report: `.rift-runtime/reports/1789337366436002400-workload-service-profiled-tuning-speed.json`

| Candidate | Decode tok/s | Result |
|---|---:|---|
| baseline | 46.185 | reference |
| f16 / f16 | 45.547 | no improvement |
| q8_0 / q8_0 | 45.531 | slower; no improvement |
| q4_0 / q4_0 | 45.118 | rejected by deterministic accuracy gate |

That run (`8ef4fb8deced4713ba78133974f10d6c`, tuning
`tune-e4bb7677db4e4ba99962`) also ended `EXHAUSTED`, restored a healthy
baseline, and retained the same model SHA-256, Q4_K_M weights, context lock,
and concurrency. The point of the screen was to demonstrate the safety path:
lower K/V precision is a measured opportunity, not an automatic accuracy or
speed win.

## Cleanup verification

After both runs, `rift stop --yes --service workload-service` terminated the
owned llama-server processes. A follow-up listener check showed no LISTENING
socket on ports 11734 or 11735 (only normal TCP `TIME_WAIT` entries remained).
No model artifacts were deleted; cleanup removed only the run-owned service
process/state.

## What this proves — and what it does not

This is end-to-end evidence for the current local easy path: natural-language
compilation, immutable approval, model/backend selection, plan/apply, readiness,
fresh quality/performance acceptance, and cleanup. It also proves that a live
tuning attempt can change runtime configuration under a maintenance lease while
keeping identity and context locks intact, and can safely roll back when the
improvement is not statistically defensible.

It does **not** claim a 160 tok/s fit, universal coding quality, or a full
near-capacity 2K-context task suite. The successful acceptance used the
versioned non-empty text gate and a short benchmark recipe; a future qualification
run should add the approved coding suite and explicit near-capacity context
requests before making stronger claims.
