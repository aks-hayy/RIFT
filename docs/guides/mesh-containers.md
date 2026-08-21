# RIFT Mesh Containers

RIFT ships four separate OCI roles for the Elastic Intelligence Mesh:

| Role | Purpose | Default port | Profile |
|---|---|---:|---|
| `controller` | Desired-state and operator control API | `8777` | `mesh`, `emulation` |
| `node` | Mutual-TLS worker control API | `11750` | `mesh` |
| `gateway` | Policy-enforcing OpenAI-compatible request gateway | `11734` | `mesh` |
| `emulator` | Deterministic fleet planning lab | `8788` | `emulation` |

The roles share code but not processes, state volumes, ports, or container
identities. The emulator labels every result `EMULATED`; it never presents a
synthetic benchmark as physical evidence.

## Security Defaults

- Containers run as UID/GID `10001`, not root.
- Root filesystems are read-only. Writable state lives in named volumes under
  `/var/lib/rift`; `/tmp` is a bounded `noexec,nosuid` tmpfs.
- Linux capabilities are dropped and `no-new-privileges` is enabled.
- The controller and emulator are published on host loopback only.
- The node agent requires a client certificate. No certificate, key, Hub token,
  gateway key, or other credential is copied into an image.
- The gateway API key list is supplied with `RIFT_GATEWAY_API_KEYS` at runtime.
- Downloads, backend installs, launches, and remote actions remain disabled in
  the supplied node policy. Change those permissions only after reviewing the
  desired-state boundary.

The controller API does not yet terminate TLS or authenticate operators. Keep
its loopback binding, or place it behind an authenticated TLS reverse proxy.

## Build Model

The current `rift-llm` wheel includes the native CUDA extension even when a role
only uses the Python control plane. Consequently, these image definitions use
CUDA development and runtime bases and build a Linux wheel inside the builder
stage. This is larger than the intended long-term control-plane image. Splitting
the native survival runtime into an optional wheel is tracked architectural work;
the images do not hide the present dependency.

Requirements:

- Docker Engine with Compose v2 and BuildKit
- Internet access to the configured base-image and Python package registries
- NVIDIA Container Toolkit only when using `deploy/compose.gpu.yaml`
- Sufficient build disk for CUDA build layers

Build one role:

```bash
docker build -f deploy/containers/Controller.Dockerfile -t rift/controller:local .
```

Build and run the deterministic lab:

```bash
docker compose -f deploy/compose.mesh.yaml --profile emulation up --build
curl http://127.0.0.1:8777/health
curl http://127.0.0.1:8788/v1/state
docker compose -f deploy/compose.mesh.yaml --profile emulation down
```

The Dockerfile-specific ignore manifests exclude model checkpoints, frontend
dependencies, build trees, and repository metadata from each build context.

## Physical Mesh Profile

Create a host directory outside the repository containing only runtime-issued
TLS material:

```text
secrets/
  controller-ca.crt
  node.crt
  node.key
  health-client.crt
  health-client.key
```

The node certificate and health-client certificate must chain to
`controller-ca.crt`. Protect the private keys with host filesystem permissions.
Then set runtime values without committing them:

```bash
export RIFT_SECRETS_DIR=/secure/path/rift-node-01
export RIFT_GATEWAY_API_KEYS='operator-key-1,application-key-1'
docker compose -f deploy/compose.mesh.yaml --profile mesh up --build
```

For an NVIDIA worker, apply the optional GPU override:

```bash
docker compose \
  -f deploy/compose.mesh.yaml \
  -f deploy/compose.gpu.yaml \
  --profile mesh up --build
```

The default node config is deliberately unable to install, download, or launch
software. Mount a reviewed replacement at `/etc/rift/node-agent.yaml` when the
node is ready to accept those actions. Persistent named volumes are:

- `controller_state`
- `node_state`
- `gateway_state`
- `emulator_state`

Removing containers does not remove those volumes. Deliberate volume deletion is
a separate operator action.

## Configuration Boundaries

`deploy/config/rift.yaml` is a minimal gateway policy, not a complete production
model deployment. The gateway routes to backend state managed in its RIFT state
volume. Supply the actual desired model/backend configuration through normal
RIFT planning and apply workflows.

`deploy/config/node-agent.yaml` contains paths and deny-by-default permissions,
not credentials. Secrets are mounted under `/run/secrets/rift` at runtime.

## Verification Status

Verified in this development slice:

- Compose parses as dependency-free JSON-compatible YAML.
- Exactly four role services are declared.
- Every service has an explicit profile, health check, persistent state volume,
  read-only root filesystem, dropped capabilities, and no-new-privileges policy.
- Dockerfiles use multi-stage wheel builds and non-root runtime users.
- Static checks reject baked secret/key material and literal secret environment
  values.
- Deploy-scoped Python entrypoints compile under the local Python interpreter.

Not physically verified by the manifest test:

- pulling the CUDA base images or compiling the Linux wheel
- starting these images with Docker/Compose
- NVIDIA runtime passthrough
- a real CA-signed mutual-TLS node handshake
- physical LAN/USB discovery, backend launch, model inference, or failover
- throughput, latency, RAM, VRAM, thermal, or network measurements

Those items require an OCI-capable Linux host (and real certificates/hardware
where applicable). Reports from the emulator remain configuration and emulation
evidence, never physical acceptance evidence.
