# Controller Gateway Lifecycle and Group Routing Design

**Status:** Draft for review  
**Date:** 2026-09-14  
**Scope:** Controller-managed gateway lifecycle, shared service routing, and optional dedicated group listeners

## Problem

RIFT can launch a model server and contains a policy-enforcing OpenAI-compatible gateway, but deployment currently starts only the backend service. The gateway must be started manually in a foreground terminal, and the UI has no lifecycle control. As a result, gateway-derived telemetry such as `request.error_ratio` remains unavailable even when a service is healthy.

RIFT already has a persistent mesh service catalog, service groups with `gateway_path`, gateway policy/runtime code, deployment actions, and telemetry storage. This design connects those pieces without creating a separate gateway implementation for every service.

## Goals

1. Run one controller gateway for all gateway-enabled services by default.
2. Make gateway lifecycle available through both CLI and UI.
3. Route a service directly through the main gateway and expose groups as virtual paths by default.
4. Offer an optional dedicated group listener/port that the main gateway forwards to.
5. Attribute request metrics to the correct service and group instead of reporting shared totals to every service.
6. Keep the direct backend endpoint available as an explicitly documented advanced bypass.
7. Persist gateway state and make start/stop operations idempotent and observable.

## Non-goals

- Replacing the existing llama.cpp/vLLM/other backend processes.
- Building a general reverse-proxy configuration language.
- Changing mesh admission or placement policy semantics.
- Automatically exposing non-loopback listeners without explicit configuration and security checks.

## Chosen architecture

### Main controller gateway

The controller owns one gateway process and one policy/runtime instance. The process is started from the active RIFT runtime/configuration and listens on the configured controller gateway address, defaulting to `127.0.0.1:11734`. Its route table is built from the controller state, so all gateway-enabled services become routes without starting one gateway process per service.

`gateway.enabled: true` expresses the desired gateway route. `rift apply --allow-launch` starts the main gateway after the managed service routes are available. A failed gateway start must be reported separately from a successful backend start; it must not silently claim that gateway-derived metrics are available.

### Virtual service and group routes (default)

The main gateway keeps the existing service-name route behavior for OpenAI requests. A registered `ServiceGroup.gateway_path` is mounted as a virtual route on the same listener. The gateway resolves the group through the existing `ServiceCatalog` and `MeshGatewayRouter`, selects the default or requested member service, and proxies to that service's managed backend endpoint. For example, a group with `gateway_path: /v1/team-a` is served by the controller gateway at:

```text
http://127.0.0.1:11734/v1/team-a
```

The route must preserve the existing request admission, fallback, and policy checks. A group path may not collide with another group path or a reserved controller path.

### Dedicated group listener (optional)

A group may opt into an isolated listener with an explicit bind address and port. The listener uses the same gateway runtime/policy and group route, but has its own process state and metrics scope. The controller gateway can forward a configured group path to that listener; direct access to the dedicated listener remains loopback-only unless the group explicitly permits another exposure and passes the existing API-key/CORS checks.

Dedicated listeners are not started implicitly by ordinary service deployment. They are started by a group lifecycle action or an explicit deployment option, because each listener consumes a process and port and may require conflict handling.

## Gateway lifecycle

### State and ownership

The controller stores the main gateway state at `.rift-runtime/gateway/state.json` and metrics at `.rift-runtime/gateway/metrics.json`, preserving the current locations. Dedicated group listeners use `.rift-runtime/gateway/groups/<group-id>/state.json` and `metrics.json`. State includes gateway kind (`main` or `group`), group id when applicable, pid, host, port, service/group route, config fingerprint, start/stop timestamps, and status.

The controller is the owner of process lifecycle. It must verify pid liveness and listener health before reporting `running`; stale state is reported as `stale` and is safe to replace only after the old pid/listener has been checked.

### Operations

All lifecycle operations are idempotent:

- `start` on a healthy listener returns its existing state.
- `stop` on an absent listener returns a stopped/not-started result without error.
- `status` reports configured, desired, observed, and process-health state separately.
- Port conflicts and invalid group paths fail with an actionable error and leave existing listeners untouched.

Stopping a gateway must not stop model services. Stopping a model service leaves the gateway running, but removes that service from the route table; a gateway request to an unavailable route returns a policy-consistent 503 and increments the route failure counters.

## CLI surface

The existing foreground command remains compatible as `rift service gateway run`. New lifecycle commands are:

```text
rift gateway start [--config PATH]
rift gateway stop
rift gateway status
rift gateway group start GROUP [--port PORT] [--host HOST]
rift gateway group stop GROUP
rift gateway group status GROUP
```

The CLI defaults to the active RIFT runtime/configuration, so users do not need to copy a generated deployment snapshot. `--detach` is the default for `start`; `run` is the explicit foreground/debug form. `--json` returns stable state, endpoint, route, and counter fields. `rift service gateway ...` remains an alias during the compatibility window.

`rift apply --allow-launch` starts the main gateway when the effective configuration has an enabled gateway. A future `--no-gateway` escape hatch may suppress this for development, but it is not required for the first implementation if the existing explicit launch permission remains the gate.

## Controller API

Add a controller-level gateway status/action contract:

- `GET /api/rift/gateway` returns main state, endpoint, route summary, and aggregate counters.
- `POST /api/rift/gateway/actions` accepts `{ "action": "start" | "stop" }` and optional host/port overrides.
- `GET /api/rift/gateway/groups` returns group listener state and route configuration.
- `POST /api/rift/gateway/groups/{group}/actions` accepts `{ "action": "start" | "stop" }` and optional dedicated-listener settings.

The action response includes an operation id when a process is being started/stopped, the eventual state, and any warning that a backend route is unavailable. Existing key-management and mesh admission endpoints remain unchanged.

## UI behavior

### Controller gateway card

Add a Gateway card to the controller-facing Operations or Settings surface. It displays:

- main gateway status (`running`, `stopped`, `stale`, `error`);
- endpoint and number of active routes;
- request totals, failures, error ratio, and average latency when counters exist;
- Start/Stop controls with confirmation for stop;
- a clear distinction between “configured but not running” and “running with no requests.”

### Deployment view

The service Monitoring/Configuration view displays whether the service is routed through the main gateway, its gateway URL, and the route-scoped request metrics. It links to the controller gateway card rather than starting a separate gateway per service.

### Groups view

Each group card displays its members, virtual path, main-gateway route state, and an optional “Dedicated listener” section. The user can choose the default virtual route or enable a dedicated listener with host/port, then start/stop that listener. Port/path validation and security warnings are shown before submission.

## Metrics and telemetry attribution

The gateway metrics document remains backward-compatible for aggregate fields and gains route-scoped counters:

```json
{
  "requests_total": 12,
  "requests_succeeded": 11,
  "requests_failed": 1,
  "average_latency_seconds": 0.42,
  "routes": {
    "service:chat": {
      "requests_total": 8,
      "requests_succeeded": 8,
      "requests_failed": 0,
      "average_latency_seconds": 0.31
    },
    "group:team-a": {
      "requests_total": 4,
      "requests_succeeded": 3,
      "requests_failed": 1,
      "average_latency_seconds": 0.64
    }
  }
}
```

The telemetry supervisor selects the route key for a service session and computes `request.error_ratio`, `service.availability_ratio`, and latency metrics from that scope. If no gateway has run or no completed request exists, the metric remains `unknown`; it must not be synthesized from backend health checks. Prometheus output exposes both aggregate and route-labelled series where the exporter supports labels.

## Failure handling and security

- Backend healthy + gateway stopped is a partial state visible in CLI/UI; request metrics are `unknown` with a reason.
- Gateway start fails because of a port conflict, invalid configuration, or missing route: preserve backend state and return the concrete cause.
- A stale pid/state file is never treated as healthy.
- Main and dedicated listeners default to loopback.
- Non-loopback exposure requires the existing API-key and CORS policy checks.
- Dedicated listeners use an internal controller-to-group route and do not bypass authorization.
- Gateway shutdown is independent of model shutdown and must release only its own process/listener resources.

## Testing and acceptance

### Backend/CLI

- Unit-test gateway state transitions, idempotent start/stop, stale pid detection, port conflict handling, and config discovery.
- Test CLI parsing for main and group lifecycle commands, JSON output, compatibility alias, and foreground `run` behavior.
- Start two managed test services behind one gateway; send requests to each route and assert route-scoped counters and error ratios.
- Register a group and verify virtual routing through the main gateway.
- Enable a dedicated group listener and verify main-gateway forwarding, independent state, and independent counters.
- Apply a gateway-enabled service and assert the controller starts the main gateway after the backend route becomes healthy.

### API/UI

- Test controller GET/POST gateway endpoints and error responses.
- Test UI actions against the live-action verification harness, including loading, success, stale, and failure states.
- Build the UI and manually exercise: start main gateway, send a request through it, observe measured error ratio, create/use a virtual group route, and start/stop a dedicated listener.

### Acceptance criteria

1. One CLI command starts a single controller gateway for all enabled services.
2. The UI exposes the same lifecycle without requiring a terminal.
3. Two services do not see each other’s request error ratios.
4. A group is reachable through the main gateway by default.
5. A dedicated group listener can be independently enabled and controlled.
6. Gateway and service stop operations do not leak processes or memory.
7. Direct backend ports remain available only as documented advanced endpoints.

