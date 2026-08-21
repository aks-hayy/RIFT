# RIFT Product Document

## Product Identity

RIFT is a control plane for LLM serving on real hardware.

It helps a user answer four practical questions:

1. What can this machine or cluster actually run?
2. Which model, quantization, and backend should I use?
3. How do I deploy it safely without hand-tuning dozens of flags?
4. How do I keep it healthy, fast, observable, and recoverable?

RIFT is not trying to replace every inference backend. Instead, it orchestrates
the best backend for the situation, then manages it like infrastructure.

The simplest product framing is:

```text
RIFT = Terraform-style planning + Kubernetes-style operations for LLM servers.
```

Terraform-style means RIFT can discover hardware, recommend a deployment,
generate a declarative config, show a plan, apply it, and destroy it.

Kubernetes-style means RIFT can supervise running LLM services, monitor health,
enforce limits, restart failures, route requests, tune parameters, and record
operational history.

## The Problem

Running local or private LLMs is still too manual.

Users must usually decide:

- which model family to use
- which model size is realistic
- which quantization is best
- which file inside a model repo to download
- which backend can serve it
- which launch flags are safe
- whether the machine has enough VRAM, RAM, disk, and bandwidth
- whether the server is healthy after launch
- why performance is poor
- what to do when the process crashes

Today, this work is spread across model cards, Discord messages, GitHub issues,
backend-specific docs, trial-and-error flags, and manual monitoring.

RIFT turns that into one infrastructure workflow.

## Product Promise

Given a workstation or cluster, RIFT should:

- inspect the hardware
- inspect installed serving backends
- search approved model sources
- choose a practical model and exact model file
- explain the decision
- generate a deployment config
- apply it only with explicit permission
- launch the backend
- expose a stable OpenAI-compatible endpoint
- benchmark actual performance
- tune backend parameters
- monitor health
- recover from failures
- produce a usability report

The user should not need to know every backend flag or quantization tradeoff in
order to get a usable LLM server.

## Target Users

### Homelab User

Has one or more consumer PCs and wants the best possible local model without
manual backend tuning.

Primary needs:

- simple model recommendation
- safe downloads
- clear performance expectations
- local chat/API endpoint
- crash recovery

### LLM Developer

Tests many models and wants reproducible deployment reports.

Primary needs:

- model comparison
- backend comparison
- benchmark history
- configuration traceability
- fast rollback

### ML Infrastructure Engineer

Runs a small private cluster and wants repeatable LLM service deployment.

Primary needs:

- declarative YAML
- hardware inventory
- placement decisions
- monitoring
- rate limits
- recovery policies
- cluster status

### Enterprise / Private Model User

Cannot rely only on public Hugging Face recommendations.

Primary needs:

- private model catalog support
- private Hub-compatible endpoints
- local folder scanning
- license/compliance warnings
- audit-friendly reports

## Product Principles

### 1. Be Honest About Confidence

RIFT must distinguish estimated recommendations from verified recommendations.

Before download:

```text
Best estimated model.
```

After local benchmark/eval:

```text
Best verified model for this hardware.
```

RIFT should never pretend metadata is the same as a real quality benchmark.

### 2. Recommend Deployments, Not Just Models

The useful answer is not only:

```text
Use Qwen2.5-7B.
```

The useful answer is:

```text
Use Qwen2.5-7B-Instruct-GGUF, Q4_K_M, served by llama.cpp, with this context
length, this GPU-layer policy, this batch size, and this expected throughput.
```

### 3. Explain Every Important Decision

Every generated config should include reasoning:

- why this model
- why this quant
- why this backend
- why this machine
- why alternatives were rejected
- what risks remain

### 4. Permission-Gated Side Effects

Discovery, recommendation, and planning are read-only.

Downloading, installing, launching, stopping, and deleting require explicit
permission or explicit CLI flags.

### 5. Backend-Agnostic Control Plane

RIFT should manage multiple backends through adapters:

- llama.cpp
- vLLM
- SGLang
- LMCache overlays
- Ollama, later
- TensorRT-LLM, later
- RIFT native survival runtime, experimental

The user should not have to care which backend exposes which flags.

### 6. Real Hardware First

RIFT is built for messy real machines:

- 8 GB laptop GPUs
- mixed CPU/GPU systems
- limited RAM
- low disk space
- Windows, WSL2, Linux
- consumer thermals
- private local model folders
- imperfect metadata

## Core Product Flow

RIFT has one primary lifecycle.

```text
Discover -> Recommend -> Generate -> Plan -> Apply -> Serve -> Monitor -> Tune -> Recover
```

### Discover

RIFT inspects the local machine or cluster.

It should collect:

- GPU model
- VRAM total and free
- RAM total and free
- CPU model and threads
- disk free space
- model cache path
- OS
- CUDA availability
- installed backends
- active RIFT-managed services
- current resource pressure

Important distinction:

```text
total capacity
current free capacity
RIFT-managed reclaimable capacity
clean-boot planning capacity
```

This prevents an already-running model from making the machine look weaker than
it really is.

### Recommend

RIFT searches configured model sources and ranks practical deployment options.

Supported sources:

- Hugging Face public Hub
- private Hub-compatible endpoint
- local model folder
- local model catalog
- future enterprise registry

Current core model formats:

- GGUF
- GPTQ
- AWQ
- SafeTensors

Recommendation output should include:

- best balanced deployment
- best quality deployment
- best speed deployment
- smallest usable deployment
- rejected alternatives
- evidence
- confidence

A recommendation must include a backend and exact model artifact, not just a
repo name.

Example:

```text
Best balanced:
  model: Qwen2.5-7B-Instruct
  file: qwen2.5-7b-instruct-q4_k_m.gguf
  backend: llama.cpp
  confidence: medium
```

### Generate

RIFT converts the recommendation into a declarative config.

The config should describe intent:

- service name
- model source
- selected file
- backend
- hardware target
- context length
- concurrency
- resource policy
- rate limits
- recovery policy
- monitoring policy
- decision evidence

This is the infrastructure contract.

### Plan

RIFT shows exactly what it would do.

Plan output should answer:

- what model would be downloaded
- how much disk is needed
- what backend would be installed or used
- what process would be launched
- what ports would be opened
- what existing service would be changed
- whether the action is safe
- whether the config differs from current state

Plan is always read-only.

### Apply

RIFT applies the config.

There are two modes:

Exact apply:

```text
Apply the config as written.
```

Optimized apply:

```text
Use the config as intent, but tune safe backend parameters and write an
optimized derived config.
```

RIFT must record every change it makes during optimization.

### Serve

RIFT launches a backend and exposes a stable service endpoint.

The user should get:

- OpenAI-compatible URL
- backend process PID
- model loaded status
- health status
- logs path
- benchmark/report path

RIFT should hide backend-specific launch complexity behind one service model.

### Monitor

RIFT continuously observes the service.

Metrics should include:

- process alive/dead
- HTTP health
- request count
- error count
- first-token latency
- prompt eval speed
- decode tokens/sec
- queue time
- active requests
- RAM usage
- VRAM usage
- disk pressure
- restart count
- last crash reason

### Tune

RIFT tries safe parameter variations.

Examples:

- context length
- GPU layers
- batch size
- microbatch size
- CPU threads
- mmap/mlock policy
- backend-specific memory fraction

Tuning should become benchmark-driven:

```text
baseline -> candidate A -> candidate B -> candidate C -> winner
```

The winning config is saved separately from the user's original config.

### Recover

RIFT applies recovery policy when things fail.

Recovery options:

- restart failed process
- exponential backoff
- mark degraded after repeated failures
- roll back to last known-good config
- fail over to a smaller model
- switch to backup backend
- repair incomplete model download
- choose alternate port after collision

Recovery must generate an incident report.

## Product Modules

### Hardware Analyzer

Responsible for answering:

```text
What can this machine realistically run?
```

Required capabilities:

- GPU/VRAM detection
- RAM detection
- disk detection
- backend compatibility detection
- active service accounting
- measured disk read speed
- measured host-to-device transfer speed where CUDA exists
- clean-capacity vs live-capacity modeling

### Model Scout

Responsible for answering:

```text
Which models are worth considering?
```

Required capabilities:

- bounded Hub search
- private endpoint search
- local folder scanning
- local catalog scanning
- candidate de-duplication
- metadata cache
- gated/private model handling
- license warning

### Artifact Selector

Responsible for answering:

```text
Which exact file should be used?
```

This is especially important for GGUF repos.

Example ranking for an 8 GB VRAM laptop:

- balanced: Q4_K_M
- speed: Q4_K_S
- quality: Q5_K_M if memory margin is healthy
- avoid: Q8_0 for larger models unless explicitly requested
- survival: Q3/Q2 only when necessary

### Backend Planner

Responsible for answering:

```text
Which backend should run this artifact?
```

Current mapping:

- GGUF -> llama.cpp
- GPTQ/AWQ -> vLLM or SGLang where supported
- SafeTensors -> vLLM/SGLang or inspect-only depending on architecture
- RIFT native -> experimental survival path

### Deployment Planner

Responsible for turning decisions into a config and a plan.

It should check:

- disk feasibility
- memory feasibility
- backend availability
- port availability
- model file availability
- install requirements
- download requirements
- launch requirements

### Service Supervisor

Responsible for process lifecycle.

Required capabilities:

- start
- stop
- restart
- health probe
- crash detection
- restart backoff
- log capture
- state persistence

### Gateway

Responsible for stable user-facing API access.

Required capabilities:

- OpenAI-compatible proxy
- request IDs
- request logging
- timeout policy
- backend routing
- rate limiting
- concurrency limits
- fallback routing

### Monitor

Responsible for observability.

Required capabilities:

- metrics collection
- status reporting
- benchmark history
- health timelines
- degraded-state detection
- incident reports

### Optimizer

Responsible for safe performance improvement.

Required capabilities:

- candidate generation
- benchmark execution
- winner selection
- regression detection
- optimized config output
- rollback if optimized config performs worse

## Config Model

RIFT should have one primary declarative config: `rift.yaml`.

Conceptual structure:

```yaml
project:
nodes:
model_sources:
services:
policies:
```

The config should be readable by humans and generated by RIFT.

Generated configs must include decision evidence, but the evidence should not
make the main config unreadable. Full reports can live under `.rift/reports`.

## Service Model

A RIFT service represents one LLM endpoint.

A service includes:

- model
- artifact
- backend
- node placement
- serving options
- limits
- recovery policy
- monitoring policy
- tuning policy

The user should think in terms of services, not backend processes.

## Recommendation Categories

RIFT should always separate recommendations by user intent.

### Best Balanced

Best default choice for this hardware.

Optimizes:

- useful quality
- stable serving
- reasonable speed
- safe memory use

### Best Quality

Largest or strongest model that still appears deployable.

May be slower.

### Best Speed

Fastest acceptable model.

May be lower quality.

### Best Survival

Smallest or most conservative choice.

Used when memory, disk, or backend support is constrained.

### Best Verified

Only available after local benchmark/eval.

This should become the most trusted category.

## Quality Model

RIFT should use a quality evidence ladder.

Highest confidence:

- local eval run
- local benchmark prompt suite
- verified instruction-following checks

Medium confidence:

- curated benchmark registry
- known model family reputation
- public benchmark metadata

Low confidence:

- downloads
- likes
- tags
- model-card claims

RIFT should display quality confidence separately from quality score.

## Operational Features

### Health

Every service has one of these states:

- pending
- starting
- healthy
- degraded
- unhealthy
- failed
- stopped

### Rate Limiting

RIFT should support:

- requests per minute
- tokens per minute
- max concurrent requests
- per-key limits
- global limits

### Disaster Recovery

RIFT should support:

- restart on crash
- restart backoff
- max restart count
- fallback model
- fallback backend
- rollback config
- degraded mode
- incident report

### Deployment Strategies

Future rollout strategies:

- exact apply
- optimized apply
- blue/green
- canary
- benchmark-gated promotion
- rollback

## MVP Scope

The MVP should prove this loop:

```text
discover -> recommend exact artifact -> generate config -> plan -> apply ->
serve -> benchmark -> monitor -> stop
```

MVP backend:

- llama.cpp

MVP model path:

- GGUF

MVP machine target:

- one local workstation

MVP must include:

- hardware discovery
- disk-aware model recommendation
- exact GGUF file selection
- backend detection
- user-approved backend install
- user-approved model pull
- config generation
- read-only plan
- launch
- health status
- benchmark
- logs
- stop
- report

## Post-MVP Scope

After MVP:

- vLLM adapter
- SGLang adapter
- local gateway
- rate limiting
- recovery policies
- live benchmark-driven tuning
- cluster discovery
- cluster placement
- private model catalogs
- richer hardware probes
- dashboard

## Non-Goals

RIFT should not initially:

- train models
- fine-tune models
- become a full replacement for llama.cpp/vLLM/SGLang
- claim benchmark quality without evidence
- hide license or safety uncertainty
- silently download or install large artifacts
- silently expose public network endpoints

## Product Milestones

### Milestone 1: Local Planner

Status: complete and verified.

RIFT can inspect local hardware, inspect local model folders, and produce a
deployment recommendation.

### Milestone 2: Local Deployer

Status: complete for the verified local llama.cpp path.

RIFT can install or locate llama.cpp, pull a selected GGUF file, generate config,
launch the service, and benchmark it.

### Milestone 3: Exact Artifact Recommendation

Status: complete and verified on 2026-07-12.

RIFT chooses exact quant files such as Q4_K_M or Q5_K_M, checks disk capacity,
and explains tradeoffs.

The verified implementation handles multi-quant repositories, sharded GGUF
artifacts, exact finalist file sizes, disk reserve policy, artifact-scoped pull
commands, and propagation of the selected file from recommendation through
generate, plan, download, and backend launch.

### Milestone 4: Service Supervisor

Status: complete at the local control-plane level and verified on 2026-07-12.

RIFT keeps services healthy with process supervision, logs, restart policies,
and degraded-state reporting.

The supervisor combines process liveness with backend HTTP health, persists a
bounded health timeline, records incident files with log tails, applies
exponential restart backoff, stops at a configurable restart ceiling, and
requires explicit recovery authorization. Continuous supervision is provided by
`rift monitor --iterations 0`; installing that loop as an operating-system
service remains production hardening work.

### Milestone 5: Gateway And Limits

Status: complete at the local data-plane level and verified on 2026-07-12.

RIFT exposes a stable OpenAI-compatible gateway with concurrency limits, request
limits, token limits, and timeout policy.

The gateway routes to RIFT-managed services from persistent state, preserves
JSON and SSE streaming behavior, assigns request IDs, supports ordered fallback
services, enforces per-identity sliding-window rate and concurrency limits,
checks conservative prompt/completion/total token budgets, optionally validates
Bearer keys from an environment variable, and persists request logs and metrics.

### Milestone 6: Benchmark-Driven Optimizer

Status: complete for the verified local llama.cpp path on 2026-07-12.

RIFT runs tuning candidates, compares real metrics, selects a winner, and writes
an optimized config.

Live tuning is explicitly authorized because it restarts the service. RIFT runs
warmups and repeated measurements, ranks only candidates that become Ready and
return valid generations, applies the median-throughput winner, persists the
last-known-good launch plan, and restores the baseline if the transaction fails.

### Milestone 7: Cluster Control Plane

Status: scheduler and desired-state emulator complete on 2026-07-12; remote
transport remains pending.

RIFT discovers multiple nodes, places services, generates cluster configs, and
manages remote services.

The current cluster controller filters infeasible nodes before scoring viable
ones, reserves VRAM and host RAM, accounts for backend compatibility and model
cache locality, prefers replica spreading, reconciles desired state, benchmarks
and tunes each placement, restarts process faults, and reschedules instances
after node loss. The deterministic emulator is a control-plane verification
tool, not a claim of physical multi-node performance.

### Milestone 8: Production Operations

Status: resilience foundation in progress.

RIFT supports canary rollout, rollback, fallback models, incident reports,
long-running monitoring, and dashboard/API control.

Implemented foundations include separate process liveness and HTTP readiness,
startup grace, failure thresholds, exponential restart backoff,
last-known-good rollback, bounded incident history, gateway fallback, cluster
process restart, and node-loss rescheduling. Remaining production work includes
remote node agents/transports, HA controller state, disruption budgets across
real replicas, canary rollout, distributed rate-limit state, TLS, and durable
metrics export.

## Success Criteria

RIFT is successful when a user can say:

```text
I pointed RIFT at my hardware and model sources. It told me what to run, why,
downloaded only what was needed, launched the server, benchmarked it, tuned it,
monitored it, and recovered it when it failed.
```

For the current workstation, a strong near-term target is:

```text
Qwen2.5-7B-Instruct GGUF, exact Q4_K_M or Q5_K_M artifact, served through
llama.cpp, with measured tokens/sec, stable health, logs, and a report.
```

That is the practical line between a prototype and a useful product.
