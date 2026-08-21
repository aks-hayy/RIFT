# RIFT Known Limitations

RIFT is useful today as a local LLM deployment control plane, but it is still a
preview. These boundaries are intentional and are surfaced in plans and
compatibility reports instead of being hidden.

## Verified Provider Coverage

- `llama.cpp` with GGUF is the only provider exercised end to end on the
  development workstation.
- vLLM and SGLang adapters implement the provider contract, but still require
  real Linux or WSL2 CUDA acceptance before they are advertised as verified.
- MLX-LM implements the adapter contract but still requires real Apple Silicon
  acceptance. Its raw development server stays on loopback unless explicitly
  protected by the RIFT gateway.
- LMCache support is an experimental overlay and has not yet demonstrated a
  measured benefit over its base provider in a real workload.
- The internal CUDA survival runtime is experimental and is not selected as a
  general production provider.

## Recommendation Evidence

Hub likes, downloads, tags, model cards, and publisher claims are useful
signals, not measured accuracy. RIFT labels those signals and prevents
popularity from overriding severe hardware incompatibility, but its curated
evaluation registry and local task-evaluation coverage are still limited.

Some repositories omit exact file sizes or quantization metadata. RIFT enriches
finalists, validates exact artifacts before download, checks real free disk
space, and reports confidence. It cannot guarantee upstream metadata quality.

## Operations Boundary

- The control API and dashboard are intended for local binding. TLS termination
  and public exposure remain operator responsibilities.
- Recovery is process-level and bounded by restart budgets. Persistent OS
  agents, alternate-artifact failover, and long-running soak acceptance remain
  release work.
- Gateway rate and concurrency counters are local-process state, not a
  distributed quota system.
- Prometheus output exists; OpenTelemetry and remote metric aggregation do not.

## Cluster Boundary

Placement, reservations, rollout planning, and recovery are deterministically
tested through a 50-node heterogeneous emulation. A mutual-TLS node agent and
SSH/PowerShell discovery paths exist, but physical three-node deployment,
benchmark, partition, failover, and teardown acceptance has not been completed.
RIFT is not yet a Kubernetes replacement.

## Packaging Boundary

The native wheel requires a C++17/CUDA build environment and compiles for the
local GPU architecture by default. The dashboard runs from the source checkout;
packaged dashboard assets, signed releases, installers, SBOMs, and a public CI
matrix remain open release gates.

See [Compatibility](compatibility.md) and
[Roadmap Verification Status](../roadmap/status.md) for exact support labels.
