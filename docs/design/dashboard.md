# RIFT Dashboard Replacement Prompt

Design a new RIFT dashboard from scratch.

RIFT is Terraform for LLM servers: it discovers hardware, recommends models, generates `rift.yaml`, plans deployments, applies them, launches backends, benchmarks performance, tunes settings, monitors health, and recovers failed services across local workstations and clusters.

## Visual Direction

- Technical blue, dark operator console, dense but polished.
- This is an infrastructure control surface, not a marketing site.
- Primary users: LLM developers, homelab users, ML infra engineers, and power users trying to run the best possible model on real hardware.
- Desktop is primary. Mobile can be simplified.

## Required Views

1. Overview
   - local/cluster health
   - active services
   - selected models
   - backends
   - ports
   - current status
   - warnings

2. Discovery
   - hardware inventory
   - backend detection
   - model source scan
   - Hugging Face/private/local source selector
   - scan progress
   - discovered candidates

3. YAML Generator
   - generated `rift.yaml` preview
   - decision evidence
   - rejected alternatives
   - model/backend/source choices
   - edit/export/save controls

4. Plan
   - rendered plan diff
   - planned actions
   - exact vs optimized apply choice
   - install/download/launch actions clearly marked
   - destructive actions highlighted

5. Apply / Operations
   - apply progress timeline
   - backend install status
   - model pull status
   - launch status
   - health checks
   - optimized config output

6. Services
   - running LLM services
   - backend
   - model
   - PID
   - endpoint
   - context length
   - concurrency
   - restart count
   - start/stop/restart buttons

7. Benchmarks & Tuning
   - first token latency
   - prompt eval speed
   - decode tokens/sec
   - model load time
   - usability verdict
   - benchmark history chart
   - tuning candidates and winning config

8. Monitoring
   - live health
   - logs
   - errors
   - degraded services
   - recovery actions

9. Cluster
   - node table/map
   - service placement
   - placement reasons
   - rejected node reasons
   - model distribution
   - backend availability per node

## Design Requirements

- No nested cards inside cards.
- Dense infrastructure UI, not SaaS landing page.
- Use tabs, tables, status chips, log panes, timelines, diff views, and compact metric panels.
- Use icons for actions.
- Every dangerous action must show confirmation state.
- Show command equivalents for plan/apply/benchmark actions.
- Raw JSON/YAML should be available but not primary.
- OpenAI-compatible serving endpoints must be visually separate from the RIFT control API.

## API Surface To Use

- `GET /api/rift/state`
- `GET /api/rift/discovery`
- `GET /api/rift/generated-config`
- `GET /api/rift/plan`
- `GET /api/rift/backends`
- `GET /api/rift/services`
- `GET /api/rift/metrics`
- `GET /api/rift/reports`
- `POST /api/rift/discover`
- `POST /api/rift/generate`
- `POST /api/rift/plan`
- `POST /api/rift/apply`
- `POST /api/rift/benchmark`
- `POST /api/rift/tune`
- `POST /api/rift/destroy`
