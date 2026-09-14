# Service Objectives and Policy Monitoring

## Goal

Add a backend-agnostic, metric-agnostic objective layer to RIFT. A deployment may opt into objectives such as availability, request error rate, TTFT, throughput, thermal limits, memory pressure, power, or cost. Uptime is one objective type, not the organizing principle.

## Scope

- Preserve Stage 1 telemetry profiles and selected-metric collection.
- Define validated objectives under `service.monitoring.objectives`.
- Evaluate objectives from recorded samples with configurable aggregation, operators, windows, consecutive-breach dwell, and recovery hysteresis.
- Persist objective state/events in the existing telemetry store and include objective summaries in live status and stopped-service reports.
- Expose objective policy through plan/config CLI, service status CLI, API, and the existing Monitoring UI.
- Keep alert delivery pluggable through an adapter interface; Stage 2 ships an in-process/webhook adapter contract and does not make notifications a service dependency.
- Automatically require or enable the metrics referenced by configured objectives during plan validation.

## Non-goals

- Claiming a long-horizon SLA from a short run; reports must show observation coverage and mark unavailable windows as unproven.
- Replacing the existing resource threshold policy; objectives complement it and use the same sample stream.
- Implementing every external notification vendor in this stage.

## Design

### Objective contract

Each objective has an id, metric, operator (`>=`, `<=`, `>`, `<`, `==`), threshold, optional aggregation (`latest`, `average`, `max`, `min`, `p95`, `p99`, `ratio`), optional window seconds, optional consecutive breach count, optional warning/critical thresholds, and optional alert adapter names. The evaluator returns `pass`, `warning`, `breach`, or `unknown` with the observed value, target, sample count, window, and reason.

Metric ids are the canonical telemetry ids. Derived request metrics (`service.availability_ratio`, `request.error_ratio`, `inference.ttft_ms`, `inference.decode_tps`) may be supplied by gateways or external ingestion. If a required metric is absent, the result is `unknown`, never a false pass.

### Runtime flow

`TelemetrySupervisor` sends each filtered sample to `ObjectiveEvaluator`. Evaluations and state transitions are stored as objective events. The existing telemetry report builder summarizes objective compliance, breach duration, and unknown coverage. Node agents can forward the same evaluation/event payloads to the controller; labels include service, node, objective, and backend.

### Configuration

Service configuration stores:

```yaml
monitoring:
  resources:
    profile: default
  objectives:
    - id: ttft
      metric: inference.ttft_ms
      aggregation: p95
      operator: "<="
      threshold: 500
      window_seconds: 300
      consecutive_breaches: 3
      alerts: [webhook]
```

Plan generation accepts `--monitoring-policy PATH` (YAML/JSON) and stores the normalized objectives in the immutable generated config. The API accepts the same object as `monitoring_objectives`.

### API and CLI

- `GET /api/rift/telemetry/objectives?service=...` returns policy, current evaluations, and event history.
- `GET /api/rift/telemetry/objectives/catalog` returns supported aggregations/operators and metric availability.
- `rift service objectives --service chat` renders live objective status.
- `rift service objectives --service chat --events` renders transitions.
- `rift service objectives --service chat --report` renders the stopped-service objective summary.
- `rift plan --monitoring-policy policies/chat.yaml` validates and persists objectives.

### UI

The existing setup Monitoring step gets an Objectives editor that starts empty, supports adding/removing objectives, and warns when a referenced metric is not in the selected profile. The existing deployment Monitoring tab gets objective status cards, current value/target, coverage, breach timeline, and alert adapter state. Resource charts remain available below it. Workload rows show the count of warnings/breaches.

### Testing

- Unit tests cover normalization, validation, aggregation, unknown coverage, dwell/recovery, and report math.
- API/CLI tests cover plan persistence, objective status/events, and malformed policies.
- UI verification covers adding an objective, generated plan payload, live status rendering, and report rendering with the existing live-actions/resource-history scripts.
