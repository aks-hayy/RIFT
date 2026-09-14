# RIFT easy-path medical summarizer workload — 2026-09-14

## Result

The natural-language request was compiled locally, but RIFT correctly stopped
before deployment. This workload is not currently executable as written because
the EHR JSON Schema/evaluator was not supplied and a short run cannot prove a
99.9% long-horizon uptime SLO. RIFT did not claim a deployment, acceptance, or
medical-quality result.

Request:

> Deploy an offline medical summarizer on an air-gapped server. It needs a 32K context window to handle long patient histories, 99.9% uptime, strict JSON output matching our EHR schema, and no external network access ever.

## Compiler evidence

| Field | Compiled result | Provenance |
|---|---|---|
| Task | `documents` | inferred from summarizer/history language |
| Objective | `balanced` | default |
| Context | 32,768 tokens | explicit “32K context window” |
| Structured output | required | inferred from strict JSON/schema language |
| Network | `offline` | explicit air-gapped/no external access |
| Uptime | 99.9% | explicit; recorded as unsupported hard requirement |
| Quality suite | `rift-text-core/v1`, 0.90 floor | operator-confirmed default |

Draft `c9ec3ff1dbba47788fc122554e8728f8` produced contract hash
`3078fb17a8aa268e326a38aa81caeb3121a2b5f80de3ce34b38c925ffe804ba4`.
The compiler emitted two approval-blocking review questions:

1. Provide a versioned EHR JSON Schema or registered evaluator; JSON syntax
   alone cannot prove EHR conformance.
2. Define the uptime observation window and monitoring evidence for 99.9%.

The earlier false offline/network conflict was fixed: “no external network
access ever” is now recognized as a prohibition, not a request for networking.

## Read-only model/backend preflight

Because approval was blocked, no artifact was launched. A separate read-only
recommendation inspection found the best local fit to be:

| Identity | Value |
|---|---|
| Candidate artifact | Qwen2.5-1.5B-Instruct-Q4_K_M.gguf |
| Weight quantization | Q4_K_M |
| Candidate backend | llama.cpp |
| Backend build | 0.3.0-dev, build 10665 |
| Fit evidence | GGUF accepted; llama.cpp executable detected locally |
| Selection status | preview only; not deployed |

Before the fix, the generated standard plan preview used an 8,192-token serving
context. That was below the requested 32,768 tokens. The controller now
propagates the contract context into the plan and rejects any remaining
undersized plan as `INFEASIBLE` before launch rather than silently accepting a
smaller context.

## Approval and cleanup

Approval was not created because unresolved hard questions remain. No workload
run, model process, endpoint, benchmark, tuning run, or promotion was started.
The final RIFT status showed zero managed services and no listeners on ports
11734/11735; therefore there was nothing to tear down.

## What is required to run this workload

- Supply the exact versioned EHR JSON Schema and register an evaluator that
  checks required fields, types, constraints, and representative summaries.
- Define an uptime observation policy (window, probe interval, error budget, and
  monitoring source). A short deployment smoke test can establish readiness,
  not 99.9% availability.
- Add an EHR-specific model/backend evaluator that genuinely certifies at least
  32K context for the target model, then run the approved near-capacity test.

## 32K context validation after the fix

To validate the propagation fix independently of the unavailable EHR
evaluator/uptime evidence, I ran a closely scoped offline document workload
with the same explicit 32K context requirement but without the two
unverifiable medical claims.

| Item | Recorded value |
|---|---|
| Draft / approval | `8b3a9087ab414325972ed487dc4d6255` / `d12b952bfa754f8e95a83fcd5e07b186` |
| Workload run | `583dd8cd9163487fb515d434a2ec948a` (`VERIFIED`) |
| Model | Qwen2.5-1.5B-Instruct-Q4_K_M.gguf |
| Backend | llama.cpp 0.3.0-dev, build 10665 |
| Planned/effective context | 32,768 tokens (both plan and deployment record) |
| Fresh acceptance | 15 benchmark samples; median 154.02 decode tok/s; quality PASS |
| Near-capacity synthetic request | 30,642 prompt tokens, HTTP 200, 3.28 s, 8-token response |

This proves that the compiled context now reaches the launch plan and that a
roughly 30K-token synthetic request is accepted by the running service. It is
not proof of EHR schema conformance, clinical quality, or 99.9% availability.
The service was stopped after the test and no RIFT listeners remained.
