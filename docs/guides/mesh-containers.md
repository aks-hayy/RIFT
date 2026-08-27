# RIFT Mesh Containers

The files under `deploy/` provide a dependency-light Compose topology for
controller, node, gateway, and emulator roles. They are intended for local
development and contract testing, not as a production security boundary.

## Start the local mesh

From the repository root:

```bash
docker compose -f deploy/compose.mesh.yaml --profile mesh up --build
```

The Compose file keeps state in named volumes and exposes no model weights by
default. Use the `controller` role to exercise the control API and the
`emulator` role for deterministic node behaviour. Stop and remove the test
topology with:

```bash
docker compose -f deploy/compose.mesh.yaml --profile mesh down --remove-orphans
```

The containers run as non-root users with read-only root filesystems and no
Linux capabilities. Supply credentials and model paths through an explicit
deployment configuration; do not bake them into images or commit them.

## Scope

This topology validates API contracts, persistence, health checks, routing,
and failure handling. It does not prove physical GPU throughput, mTLS
deployment on a real fleet, or model quality.
