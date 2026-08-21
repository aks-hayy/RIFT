# Operator Console Data

The bundled RIFT operator console consumes the live local controller at
`/api/rift` through the versioned API adapter. The contributor UI source lives
under `ui/`; its development server may proxy to `RIFT_CONTROL_API`, which
defaults to `http://127.0.0.1:8777`, but users run the packaged dashboard.

The guided setup uses automatic Hugging Face discovery. Users select a task;
RIFT supplies the repository and exact artifact after measuring the target
hardware. Exact repo IDs are reserved for the advanced `rift model pull`
workflow and are not required by the normal dashboard path.

## Data Provenance

Every panel belongs to one of four evidence classes.

| Class | Meaning | Current examples |
|---|---|---|
| `live` | Returned directly by the running RIFT controller | Hardware capacity and pressure, services, incidents, logs, timeline, backend detection, reports, latest plan, Hub recommendations |
| `derived-live` | Computed only from current or retained controller records | Fleet health totals, active service incident, active model artifact, current revision summary |
| `preview` | Illustrative layout data, never presented as observed truth | Catalog examples and the future model-source registry |
| `unavailable` | A future controller mutation or resource does not exist yet | Enrollment tokens, immutable plan apply/rollback from the new UI, policy and user administration |

The controller status indicator reports `connecting`, `live`, or `offline`.
Preview surfaces can be disabled with `VITE_RIFT_PREVIEW_DATA=false`.

## Live Views

- Home: fleet health, managed services, active incidents, hardware node, and
  controller timeline.
- Deployments: service state, endpoint, model path, runtime settings, retained
  benchmark results, revisions, and bounded service logs.
- Nodes: observed CPU/GPU/RAM/disk capacity and pressure plus available power,
  thermal, utilization, and calibration measurements.
- Models: artifacts attached to managed services and an explicit, user-started
  hardware-aware Hugging Face recommendation search.
- Operations: incidents, latest read-only rollout plan, audit timeline, logs,
  and retained benchmark/tuning report counts.
- Settings: controller connection and detected backend providers.

## Verification

Start the controller and console:

```powershell
rift start --no-browser
```

In another terminal, verify the typed adapter against the live controller:

```powershell
cd ui
npm run verify:controller
```

The check fails if hardware is absent or fleet service counts disagree with the
service resource. Its summary includes the observed node, GPU, available disk,
service/backend state, incidents, benchmark history, plan actions, and provider
count.

## Known Boundary

The release console is bundled into the Python wheel and runs outside the
source checkout. The current controller implementation exposes the legacy
`/api/rift` paths alongside the documented versioned contract; unavailable
routes render an explicit unavailable state rather than mock data.
