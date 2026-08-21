# RIFT Adapter Authoring Guide

RIFT adapters translate normalized deployment intent into operations against an
unmodified external backend or artifact family. An adapter must not import or
patch backend internals. It may use documented executables, containers,
configuration files, and HTTP endpoints.

## Package Entry Points

Third-party packages register adapters through standard Python entry points:

```toml
[project.entry-points."rift.backend_adapters"]
my-backend = "my_rift_adapter:MyBackendAdapter"

[project.entry-points."rift.artifact_adapters"]
my-format = "my_rift_adapter:MyArtifactAdapter"

[project.entry-points."rift.converter_adapters"]
my-converter = "my_rift_adapter:MyConverterAdapter"
```

After the package is installed into the RIFT controller environment, it appears
in discovery, recommendation, planning, apply, and the API without a central
registry change. `RIFT_DISABLED_ADAPTERS=id-one,id-two` disables adapters by ID.
Duplicate IDs fail closed: the first registration stays active and the conflict
is reported by `rift backend doctor` and API V2.

## Backend Contract

An adapter exposes an `AdapterManifest(kind="backend")` and implements:

```text
probe, capabilities, install_plan, install, evaluate_fit,
build_launch_spec, launch, health, benchmark, tuning_space,
stop, recover
```

The manifest declares tasks, artifact formats, quantizations, architectures,
platforms, accelerators, installation methods, endpoints, features, security
boundaries, and evidence status. Runtime detection returns the actual upstream
version and feature probe. Static capabilities are never interpreted as proof
that a particular installed version supports a feature.

Installation must target an isolated RIFT-managed environment or an approved
container. `install_plan()` must return `requires_permission: true`; controller
permission gates remain authoritative. Launch specifications must be data, not
shell strings, and must preserve the exact model revision and artifact.

## Artifact Contract

An artifact adapter exposes `AdapterManifest(kind="artifact")` and implements:

```text
detect, inspect, resolve_files, validate,
estimate_resources, compatible_backends
```

`inspect()` returns one or more `ArtifactVariant` values. Each variant records
the exact revision, architecture, quantization, required files, dependency
roles, byte counts, hashes, validation result, and resource estimate. Artifact
adapters describe artifacts; backend compatibility is decided by backend
manifests. `compatible_backends()` is only an adapter-local hint and is not the
planner's source of truth.

Serving readiness must fail closed for missing shards, config/tokenizer files,
required processors, multimodal projections, or invalid zero-byte files. A safe
serialization format does not substitute for hash evidence.

Converters use `AdapterManifest(kind="converter")` and implement
`can_convert`, `plan_conversion`, and `convert`. RIFT will not execute a plan
without explicit `allow_conversion` permission. Conversion never happens as an
implicit side effect of recommendation.

## API Versioning

The current adapter API is `1.0`. Hosts accept compatible minor revisions but
reject a different major version. Manifests and diagnostics are available at:

```text
GET /api/rift/v2/adapters
GET /api/rift/v2/artifact-adapters
GET /api/rift/v2/capabilities
```

## Conformance

Run the shared suites before publishing an adapter:

```python
from spoolstream.adapters.conformance import (
    ArtifactConformanceSuite,
    BackendConformanceSuite,
)
```

Backend conformance checks the complete side-effect-free contract and can run a
fake lifecycle. Artifact conformance checks detection, exact variants,
dependencies, validation, resource estimates, and resolution. Passing the
suite means contract-complete, not physically verified. Production evidence
requires a real install, artifact, prompt, health check, benchmark, tuning run,
crash recovery, stop, and teardown on every advertised platform class.

## Security Rules

- Never install, download, convert, launch, expose, or run remotely without the
  corresponding controller permission.
- Never mutate the user's global Python environment.
- Bind raw development servers to loopback and route managed access through the
  RIFT gateway.
- Treat credentials as secrets and keep them out of commands, state, and logs.
- Return actionable diagnostics for unsupported systems instead of claiming a
  fallback succeeded.
