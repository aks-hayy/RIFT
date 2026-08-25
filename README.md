# RIFT

> **RIFT is an experimental, research project. Please forgive the mistakes.**
> APIs, adapters, deployment workflows, and platform support can change while
> the project is being validated.

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

See the [Project Status](#project-status) section for current support levels
and unresolved production gates.

## Fresh Clone

The intended first-run workflow requires only Python 3.10+ and network access
to install the declared Python dependencies. It does not install a model,
serving backend, GPU runtime, or compiler.

Windows:

```powershell
git clone <rift-repository>
cd rift
.\bootstrap.ps1
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

### Give RIFT A Local Model

For a model already on disk, RIFT can manage the exact artifact without Hub
discovery:

```powershell
rift model inspect D:\models\my-model-Q4_K_M.gguf
rift model verify D:\models\my-model-Q4_K_M.gguf
rift model recommend --source local --models-dir D:\models --output rift.yaml
rift plan --config rift.yaml
rift apply --config rift.yaml --allow-launch
```

The equivalent explicit model section is:

```yaml
schema_version: 1
services:
  chat:
    model:
      source: local
      id: my-model
      local_path: "D:\\models\\my-model-Q4_K_M.gguf"
    policy:
      backend: llama.cpp
```

RIFT checks the exact file, backend compatibility, memory budgets, ports,
context length, and permissions before launch. It refuses incompatible model
and backend combinations instead of silently substituting a model.

### Choose A Hugging Face Repository Yourself

Automatic discovery is optional. For an exact repository, use its repository ID
such as `org/model` rather than the browser URL:

```powershell
rift model pull org/model --dry-run --max-download-gb 12
rift model pull org/model --output D:\models\org-model
rift model inspect D:\models\org-model
rift model verify D:\models\org-model --hash-mode all
rift model recommend --source local --models-dir D:\models\org-model --output rift.yaml
rift plan --config rift.yaml
rift apply --config rift.yaml --allow-launch
```

The dry run checks repository files, disk capacity, artifact size, revision,
and likely backend compatibility before any download. Private Hub-compatible
endpoints can be selected with `--endpoint` and `--token`.

### Node And Controller Enrollment

On the controller, start RIFT and open the dashboard's **Add Node** flow. The
controller opens a temporary enrollment window on port `11748`. On the new
device, run:

```powershell
rift node start --controller https://controller:11748
```

The node creates a persistent identity, displays a six-digit pairing code, and
waits for operator approval. The controller issues certificates and verifies
the node through an mTLS health check before marking it `ACTIVE`. The pairing
code is never shown in the controller UI. New nodes remain deny-by-default:

```powershell
rift node permissions show
rift node permissions set --inference allow
rift node permissions set --download allow --install allow --launch allow
```

Subsequent node starts reuse the identity and skip pairing. For Docker, the
controller must advertise its service hostname, for example
`RIFT_CONTROLLER_ADVERTISE_HOST=controller`, rather than advertising
`127.0.0.1`.

### Automatic Tuning

Normal `rift apply` uses hardware-aware backend defaults. Preview candidate
settings with:

```powershell
rift service tune --service chat
```

Run actual measured tuning with controlled restarts using:

```powershell
rift service tune --service chat --live --allow-restart
```

Live tuning measures a baseline and bounded backend candidates, waits for
health after each restart, selects the highest valid measured throughput, saves
the report, and restores the last known-good configuration if a candidate fails.
The current `rift apply --optimize` path is intended for optimization but does
not replace this explicit live tuning command yet.

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
  rift node start|status|stop|permissions

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

The UI must treat live controller API data as authoritative. It must label
measured, published, estimated, emulated, and unavailable values separately;
it must never render operational mock data as real state.

Adapter authors should use the versioned
[Adapter API V2 contract](docs/reference/rift-adapter-api-v2.openapi.yaml).

## Repository Layout

```text
ui/              canonical operator interface source
python/rift/web/  bundled dashboard assets
 docs/            machine-readable OpenAPI contracts only
deploy/          split OCI images and mesh Compose workflow
python/rift/     public Python and CLI facade
scripts/         contributor build helpers
tests/python/    control-plane and provider tests
```

The README is the canonical repository and operator guide. The OpenAPI files
under `docs/reference/` are retained as machine-readable contracts.

## Safety Model

RIFT never silently downloads a model, installs a backend, launches or stops a
service, executes remote commands, exposes a public port, or overwrites user
intent. Destructive operations require explicit confirmation, and public
network exposure remains an operator responsibility.

## Testing And Verification

Run the Python tests from an environment with the declared package
dependencies:

```powershell
python -m compileall -q python tests
Get-ChildItem tests\python -Filter '*_tests.py' | ForEach-Object {
  python $_.FullName
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

Container manifests under `deploy/containers/` and
`deploy/compose.mesh.yaml` can exercise controller/node enrollment, Docker
bridge-network discovery, mTLS activation, restart persistence, recovery, and
cleanup without modifying host model files. Tests distinguish real hardware
measurements, live backend measurements, deterministic emulation, and fake
provider contract tests. Emulation is not evidence of physical fleet
reliability.

## Compatibility And Project Status

RIFT is a pure-Python control plane suitable for local deployment workflows,
adapter-based backend management, and deterministic mesh/control-plane
emulation. Physical heterogeneous-node reliability remains
`UNVERIFIED_EXTERNAL`; this release does not claim to be a Kubernetes
replacement or to bundle serving backends.

Backend compatibility is the intersection of the exact artifact, architecture,
backend version, operating system, accelerator, memory budget, and workload.
llama.cpp with GGUF is the strongest locally verified path. vLLM, SGLang, and
MLX-LM have adapter contracts and platform-specific planning, but their broad
physical acceptance matrix is not yet complete. CPU-only fallback and remote
node plans are valid strategies when local acceleration is unavailable.

Known limits include incomplete physical heterogeneous-node evidence, limited
real-backend tuning coverage, no guarantee that every model family is
deployable, and no claim of Kubernetes-level production HA. These limits are
reported rather than hidden.

- [Controller OpenAPI](docs/reference/rift-controller.openapi.yaml)
- [Node Agent OpenAPI](docs/reference/rift-node-agent.openapi.yaml)
- [Adapter API V2 OpenAPI](docs/reference/rift-adapter-api-v2.openapi.yaml)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)
- [Changelog](CHANGELOG.md)

## License

Licensed under the [Apache License 2.0](LICENSE).
