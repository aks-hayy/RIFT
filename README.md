# RIFT

RIFT is a hardware-aware control plane for local and small-cluster LLM serving.
It discovers machines, recommends an exact model artifact and backend, generates
an explainable deployment configuration, applies it with explicit permissions,
then benchmarks, tunes, monitors, and recovers the resulting service.

```text
discover -> model recommend -> plan -> apply -> operate
```

RIFT orchestrates established serving backends. It does not claim that every
model, format, backend, or PC is equally supported, and it labels measured,
published, estimated, and emulated evidence separately.

## What Works Today

- Measurement-aware CPU, RAM, GPU/VRAM, disk, pressure, thermal, and RIFT-owned
  service discovery.
- Bounded Hugging Face discovery with exact-artifact ranking, disk preflight,
  resumable pulls, hashes, provenance, and evidence confidence.
- Declarative `rift.yaml` generation, read-only plans, permission-gated apply,
  persisted state, governance policy, and diagnostic exports.
- A locally verified llama.cpp provider for GGUF models on the development
  workstation.
- Dynamically discovered backend adapters for llama.cpp, vLLM, SGLang, and
  MLX-LM; LMCache remains a separate optimization overlay. Linux/Apple adapter
  paths retain honest physical-platform acceptance gates.
- Exact artifact adapters for GGUF, dense/sharded SafeTensors, AWQ, GPTQ, FP8,
  EXL2, and MLX, with dependency and integrity checks that fail closed.
- Recommendation Contract V2 with format-neutral identity discovery, exact
  artifacts, separate trust dimensions, Pareto choices, persisted runs, and an
  optional measured finalist tournament. Published benchmark snapshots are
  signed and provenance-labelled; `rift model recommend` remains download-free by
  default and `--verify` is explicitly bounded and permission-gated.
- Reproducible benchmarks, bounded tuning, regression rejection, supervision,
  incidents, recovery, gateway limits, API keys, logs, and Prometheus output.
- Deterministic cluster placement and failure emulation. Physical multi-node
  acceptance remains a documented release gate.
- An optional mTLS node agent for desired-state reconciliation and node-side
  install/download/launch permission enforcement.
- A live technical dashboard backed by the RIFT control API.
- UI-first Elastic Intelligence Mesh onboarding: passive mDNS discovery,
  consent-gated private-subnet/USB/ADB bootstrap, explicit pairing, controller
  CA-issued mTLS identities, live topology evidence, policy-aware routing, and
  short-lived route leases. Physical heterogeneous-node acceptance is pending.
- Reproducible controller, node, gateway, and emulator container definitions.
  Mobile and native runtime experiments are preserved outside the release
  branch in the archival source tag.

See the [verified roadmap status](docs/roadmap/status.md) for exact support
levels and unresolved production gates.

## Fresh Clone

The intended first-run workflow requires only Python 3.10+ and network access
to install the declared Python dependencies. It does not install a model,
serving backend, GPU runtime, or compiler.

Windows:

```powershell
git clone <rift-repository>
cd rift
.\scripts\bootstrap.ps1
.\.venv\Scripts\rift.exe start
```

Linux/macOS:

```bash
git clone <rift-repository>
cd rift
./scripts/bootstrap.sh
./.venv/bin/rift start
```

The dashboard opens to onboarding. Use `--no-browser` on headless machines.

## Install From Source

The normal RIFT package is pure Python. CUDA, CMake, Ninja, Node.js, and a
native compiler are not required for the control plane. Serving backends remain
external, permission-gated adapters.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install .
```

Start the bundled dashboard:

```powershell
rift start --no-browser
```

Runtime state uses a platform-aware data directory and never belongs in the
checkout. Set `RIFT_HOME` to override it. Model weights, backend environments,
logs, certificates, caches, and reports are operator-owned runtime data and are
not included in the source distribution.

## First Deployment

```powershell
# Inspect hardware and installed providers.
rift discover

# Find the strongest practical model for this machine.
rift model recommend --task chat --top 5

# Ask what RIFT would recommend for a different workstation without touching this one.
rift model recommend --task chat --top 5 `
  --simulate-hardware "gpu=RTX 5090,vram_gb=32,ram_gb=64,disk_free_gb=500,os=linux"

# Optional: compare finalists by actually pulling/launching/benchmarking them.
# Every side effect remains explicit.
rift model recommend --task chat --verify --allow-download --allow-install --allow-launch
# Verify more finalists only when the extra download/launch cost is intentional.
rift model recommend --task chat --verify-top 3 --verify-budget 900 --allow-download --allow-install --allow-launch

# Let RIFT find the repo and exact artifact; this first command downloads nothing.
rift model pull --task chat --dry-run

# Remove --dry-run when the selection looks right.
rift model pull --task chat --output models/best

# Generate explainable intent and review every action.
rift model recommend --task chat --write-report recommendations.json
rift plan --config rift.yaml

# Nothing downloads, installs, or launches without these explicit permissions.
rift apply --config rift.yaml --allow-download --allow-install --allow-launch

# Operate the deployed service.
rift status
rift service benchmark --service chat --suite
rift service tune --service chat
rift stop --service chat --yes
```

Use `rift --json COMMAND ...` for automation. Human-readable tables are the
default. `--simulate-hardware` accepts a JSON object or a JSON file path as
well as comma-separated `key=value` pairs. Required simulation inputs are GPU,
VRAM, host RAM, and free disk; free VRAM/RAM default to total capacity unless
specified. Simulation is explicitly labelled and is read-only: it cannot pull,
install, launch, or verify a model.

## Focused Commands

```text
Core workflow
  init, start, discover, plan, apply, status, dashboard, stop, doctor

Model operations
  rift model recommend|pull|inspect|verify

Provider operations
  rift backend list|inspect|doctor|detect|install-plan|install|health

Service operations
  rift service benchmark|tune|logs|restart|rollback|gateway

Cluster operations
  rift cluster discover|plan|apply|status|drain|destroy

Node agent
  rift node enroll|serve|status

System and support
  rift system backup|restore|diagnostics|migrate
```

Run `rift COMMAND --help` for permission requirements and examples.

## Dashboard

```powershell
rift dashboard --port 8765 --control-port 8777
rift dashboard --detach
```

The canonical contributor UI source is `ui/`. The installed package serves
`python/rift/web/static` directly, so users do not need npm. From an installed
wheel, `rift start` and `rift dashboard` work outside the source checkout.

The current console starts with discovery and trust onboarding, then provides
live mesh nodes, certificate/routability state, measured links, hardware,
services, models, benchmarks, incidents, logs, timeline, backends, and read-only
plans. Values derived from live state and preview-only future surfaces are
labeled in the UI. Mutating operations remain guarded by the same permissions
enforced by the CLI.

See the [operator console data guide](docs/guides/operator-console.md) for the
live/derived/preview boundary.

See [benchmark data policy](docs/legal/benchmark-data-policy.md) for the
published-evidence boundary and [release audit](docs/legal/release-audit.md)
for the source-tree checks required before publishing.

Adapter authors should start with the
[versioned adapter guide](docs/guides/adapter-authoring.md) and the
[Adapter API V2 contract](docs/reference/rift-adapter-api-v2.openapi.yaml).

## Repository Layout

```text
ui/              canonical operator interface source
python/rift/web/  bundled dashboard assets
docs/            guides, architecture, roadmap, reference, and history
deploy/          split OCI images and mesh Compose workflow
python/rift/     public Python and CLI facade
scripts/         contributor build helpers
tests/python/    control-plane and provider tests
```

More detail is available in the [repository layout](docs/architecture/repository-layout.md).

## Safety Model

RIFT never silently downloads a model, installs a backend, launches or stops a
service, executes remote commands, exposes a public port, or overwrites user
intent. Destructive operations require explicit confirmation, and public
network exposure remains an operator responsibility.

## Project Status

RIFT is a pure-Python control plane suitable for local deployment workflows,
adapter-based backend management, and deterministic mesh/control-plane
emulation. Physical heterogeneous-node reliability remains
`UNVERIFIED_EXTERNAL`; this release does not claim to be a Kubernetes
replacement or to bundle serving backends.

- [Quickstart](docs/guides/quickstart.md)
- [Compatibility](docs/reference/compatibility.md)
- [Known limitations](docs/reference/known-limitations.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)
- [Changelog](CHANGELOG.md)

## License

Licensed under the [Apache License 2.0](LICENSE).
