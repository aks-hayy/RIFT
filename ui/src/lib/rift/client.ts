// Typed facade over the current RIFT controller API.
//
// RIFT's shipped controller exposes legacy `/api/rift` resources alongside
// versioned V2 operations. This adapter normalizes those live responses into
// the UI resource model without coupling route components to wire details.

import type {
  ApplyProgress,
  Backend,
  Benchmark,
  DeploymentRecord,
  DeploymentRevision,
  EvaluationRun,
  EnrollmentToken,
  FleetHealth,
  Incident,
  ModelArtifact,
  ModelRecommendation,
  RecommendationSearchResult,
  EnrollmentApproval,
  EnrollmentChallenge,
  MeshLink,
  MeshNode,
  MeshSighting,
  MeshTopology,
  ManagedEnrollment,
  ManagedEnrollmentWindow,
  OperationRecord,
  PlanAction,
  Plan,
  SettingsSnapshot,
  RiftEvent,
  RiftNode,
  Service,
  UseCase,
} from "./types";
import {
  applyRequest,
  isDeployableRecommendation,
  planRequest,
  recommendationSelector,
} from "./action-contract";
import { mapBenchmarkReport } from "./report-mapping";
import { deriveOperationDisplay } from "./operation-state";

export class RiftUnavailable extends Error {
  constructor(
    public readonly endpoint: string,
    public readonly method: HttpMethod,
    public readonly reason:
      "controller-unconfigured" | "controller-offline" | "timeout" | "not-implemented",
    public readonly detail?: string,
  ) {
    super(`RIFT ${method} ${endpoint} unavailable: ${reason}${detail ? ` - ${detail}` : ""}`);
    this.name = "RiftUnavailable";
  }
}

export class RiftApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly endpoint: string,
    public readonly body: unknown,
  ) {
    const detail =
      typeof body === "string"
        ? body
        : body && typeof body === "object"
          ? String(
              (body as Record<string, unknown>).detail ??
                (body as Record<string, unknown>).error ??
                (body as Record<string, unknown>).message ??
                "",
            )
          : "";
    super(`RIFT ${endpoint} failed: ${status}${detail ? ` - ${detail}` : ""}`);
    this.name = "RiftApiError";
  }
}

type HttpMethod = "GET" | "POST" | "DELETE" | "PATCH";
type JsonObject = Record<string, unknown>;

const DEFAULT_TIMEOUT_MS = 120_000;

function configuredRoot(): string {
  const env = (
    import.meta as ImportMeta & {
      env: Record<string, string | undefined>;
    }
  ).env;
  const runtimeConfigured =
    typeof window !== "undefined"
      ? (window as Window & { RIFT_CONTROL_API?: string }).RIFT_CONTROL_API?.trim()
      : undefined;
  const configured = runtimeConfigured || env.VITE_RIFT_CONTROLLER_URL?.trim();
  if (!configured) return "/api/rift";
  const root = configured.replace(/\/+$/, "");
  if (root.endsWith("/api/rift")) return root;
  if (root.endsWith("/api/rift/v1")) return root.slice(0, -3);
  return `${root}/api/rift`;
}

function previewEnabled(): boolean {
  const env = (
    import.meta as ImportMeta & {
      env: Record<string, string | boolean | undefined>;
    }
  ).env;
  const configured = env.VITE_RIFT_PREVIEW_DATA;
  if (typeof configured === "string") return configured.toLowerCase() === "true";
  return env.DEV === true;
}

async function req<T>(
  method: HttpMethod,
  path: string,
  body?: unknown,
  signal?: AbortSignal,
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  const ac = new AbortController();
  const timeoutId = setTimeout(() => ac.abort(), timeoutMs);
  const combined = signal ? new AbortController() : ac;
  if (signal) {
    signal.addEventListener("abort", () => combined.abort(), { once: true });
    ac.signal.addEventListener("abort", () => combined.abort(), { once: true });
  }
  try {
    const response = await fetch(`${configuredRoot()}${path}`, {
      method,
      headers: {
        Accept: "application/json",
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: combined.signal,
      credentials: "include",
    });
    const contentType = response.headers.get("content-type") ?? "";
    const payload = contentType.includes("application/json")
      ? await response.json()
      : await response.text();
    if (!response.ok) {
      if (response.status === 404 || response.status === 501) {
        throw new RiftUnavailable(path, method, "not-implemented");
      }
      throw new RiftApiError(response.status, path, payload);
    }
    return payload as T;
  } catch (error) {
    if (error instanceof RiftApiError || error instanceof RiftUnavailable) throw error;
    if ((error as { name?: string }).name === "AbortError") {
      throw new RiftUnavailable(path, method, "timeout");
    }
    throw new RiftUnavailable(
      path,
      method,
      "controller-offline",
      error instanceof Error ? error.message : String(error),
    );
  } finally {
    clearTimeout(timeoutId);
  }
}

function object(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonObject) : {};
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function text(value: unknown, fallback = ""): string {
  return typeof value === "string" && value ? value : fallback;
}

function numeric(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function bool(value: unknown, fallback = false): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function isoFromUnix(value: unknown, fallback = Date.now()): string {
  const seconds = numeric(value, fallback / 1000);
  return new Date(seconds * 1000).toISOString();
}

function iso(value: unknown, fallback = Date.now()): string {
  if (typeof value === "string" && value) {
    const parsed = Date.parse(value);
    if (Number.isFinite(parsed)) return new Date(parsed).toISOString();
  }
  return isoFromUnix(value, fallback);
}

function trustState(value: unknown): MeshSighting["trustState"] {
  const state = text(value, "DISCOVERED_UNTRUSTED").toUpperCase();
  if (
    state === "PAIRING_PENDING" ||
    state === "ENROLLED" ||
    state === "ACTIVE" ||
    state === "REVOKED"
  ) {
    return state;
  }
  return "DISCOVERED_UNTRUSTED";
}

function mapMeshSighting(value: unknown): MeshSighting {
  const raw = object(value);
  return {
    sightingId: text(raw.sighting_id, text(raw.sightingId)),
    provider: text(raw.provider, "unknown"),
    endpoint: text(raw.endpoint),
    nodeHint: text(raw.node_hint, text(raw.nodeHint, "Unnamed node")),
    apiVersion: text(raw.api_version, text(raw.apiVersion, "unknown")),
    bootstrapFingerprint: text(raw.bootstrap_fingerprint, text(raw.bootstrapFingerprint)),
    observedAt: iso(raw.observed_at ?? raw.observedAt),
    expiresAt: iso(raw.expires_at ?? raw.expiresAt),
    interfaceId: text(raw.interface_id, text(raw.interfaceId)) || undefined,
    trustState: trustState(raw.trust_state ?? raw.trustState),
    metadata: object(raw.metadata),
  };
}

function mapMeshNode(value: unknown): MeshNode {
  const raw = object(value);
  const state = trustState(raw.trust_state ?? raw.trustState ?? "ENROLLED");
  const routable = bool(raw.routable, state === "ACTIVE");
  return {
    nodeId: text(raw.node_id, text(raw.nodeId, text(raw.id))),
    hostname: text(raw.hostname, text(raw.node_hint, text(raw.nodeHint, "Unnamed node"))),
    endpoint: text(raw.endpoint) || undefined,
    trustState: state,
    routable,
    certificateRequired: bool(raw.certificate_required ?? raw.certificateRequired, !routable),
    healthy: bool(raw.healthy, true),
    queueDepth: numeric(raw.queue_depth, numeric(raw.queueDepth)),
    labels: Object.fromEntries(
      Object.entries(object(raw.labels)).map(([key, entry]) => [key, text(entry)]),
    ),
    enrolledAt:
      raw.enrolled_at || raw.enrolledAt ? iso(raw.enrolled_at ?? raw.enrolledAt) : undefined,
    lastSeenAt:
      raw.last_seen_at || raw.lastSeenAt ? iso(raw.last_seen_at ?? raw.lastSeenAt) : undefined,
    capabilities: Object.keys(object(raw.capabilities)).length
      ? object(raw.capabilities)
      : undefined,
  };
}

function mapMeshLink(value: unknown): MeshLink {
  const raw = object(value);
  return {
    sourceNodeId: text(raw.source_node_id, text(raw.sourceNodeId)),
    targetNodeId: text(raw.target_node_id, text(raw.targetNodeId)),
    rttP50Ms: numeric(raw.rtt_p50_ms, numeric(raw.rttP50Ms)),
    rttP95Ms: numeric(raw.rtt_p95_ms, numeric(raw.rttP95Ms)),
    jitterMs: numeric(raw.jitter_ms, numeric(raw.jitterMs)),
    lossRatio: numeric(raw.loss_ratio, numeric(raw.lossRatio)),
    uploadMbps: numeric(raw.upload_mbps, numeric(raw.uploadMbps)),
    downloadMbps: numeric(raw.download_mbps, numeric(raw.downloadMbps)),
    evidence: text(raw.evidence, "UNKNOWN"),
  };
}

function mapEnrollmentChallenge(value: unknown): EnrollmentChallenge {
  const raw = object(value);
  const state = text(raw.state, "PAIRING_PENDING").toUpperCase();
  return {
    enrollmentId: text(raw.enrollment_id, text(raw.enrollmentId, text(raw.id))),
    sightingId: text(raw.sighting_id, text(raw.sightingId)),
    expiresAt: iso(raw.expires_at ?? raw.expiresAt),
    state:
      state === "APPROVED" || state === "EXPIRED" || state === "REJECTED"
        ? state
        : "PAIRING_PENDING",
    nodeHint: text(raw.node_hint, text(raw.nodeHint)) || undefined,
  };
}

function mapManagedEnrollment(value: unknown): ManagedEnrollment {
  const raw = object(value);
  const state = text(raw.state, "PAIRING_PENDING").toUpperCase() as ManagedEnrollment["state"];
  return {
    enrollmentId: text(raw.enrollment_id, text(raw.enrollmentId, text(raw.id))),
    nodeId: text(raw.node_id, text(raw.nodeId)) || undefined,
    displayName: text(raw.display_name, text(raw.displayName)) || undefined,
    endpoint: text(raw.endpoint) || undefined,
    state,
    expiresAt: raw.expires_at || raw.expiresAt ? iso(raw.expires_at ?? raw.expiresAt) : undefined,
    attempts: raw.attempts === undefined ? undefined : numeric(raw.attempts),
  };
}

function basename(value: string): string {
  const normalized = value.replace(/\\/g, "/").replace(/\/+$/, "");
  return normalized.split("/").pop() || normalized;
}

function backendKind(value: unknown): Backend["kind"] {
  const kind = text(value, "external").toLowerCase();
  if (kind === "llama.cpp" || kind === "llama_cpp") return "llama.cpp";
  if (kind === "vllm") return "vllm";
  if (kind === "sglang") return "sglang";
  if (kind === "lmcache_aware") return "lmcache";
  if (kind === "tgi") return "tgi";
  if (kind === "mlc") return "mlc";
  if (kind === "ollama") return "ollama";
  return "external";
}

function serviceStatus(value: unknown, raw: JsonObject): Service["status"] {
  const observation = object(raw.observation);
  const health = object(raw.health);
  const state = text(observation.phase, text(value, "unknown")).toLowerCase();
  if (state === "healthy" || state === "ready" || state === "running") return "running";
  if (state === "starting" || state === "backoff" || state === "recovering") {
    return "degraded";
  }
  if (state === "stopped" || state === "not_started") return "stopped";
  if (state === "crashed" || state === "unhealthy" || health.healthy === false) {
    return "failed";
  }
  if (state === "planning") return "planning";
  if (state === "applying") return "applying";
  return "degraded";
}

function mapService(name: string, value: unknown): Service {
  const raw = object(value);
  const runtime = object(raw.runtime);
  const launch = object(raw.launch_plan);
  const providerDetection = object(raw.provider_detection);
  const backend = object(raw.backend);
  const serving = object(raw.serving);
  const model = object(raw.model);
  const placement = object(raw.placement);
  const endpointText = text(runtime.openai_base, text(launch.openai_base));
  let scheme: "http" | "https" = "http";
  let host = text(serving.host, text(launch.host, "127.0.0.1"));
  let port = numeric(serving.port, numeric(launch.port, 0));
  let path = "/v1";
  try {
    if (endpointText) {
      const endpoint = new URL(endpointText);
      scheme = endpoint.protocol === "https:" ? "https" : "http";
      host = endpoint.hostname;
      port = numeric(endpoint.port, scheme === "https" ? 443 : 80);
      path = endpoint.pathname || "/v1";
    }
  } catch {
    // The separately supplied launch fields remain authoritative.
  }
  const modelId = text(model.id, text(model.selected_file, "unconfigured-model"));
  const nodeId = text(placement.node, "local");
  const updated = numeric(raw.updated_unix_seconds, numeric(runtime.started_unix_seconds));
  return {
    id: name,
    name,
    useCase: name.toLowerCase().includes("code") ? "coding" : "chat",
    status: serviceStatus(raw.status, raw),
    artifactId: modelId,
    backendKind: backendKind(raw.backend),
    assignments: [
      {
        nodeId,
        gpuIndices: [0],
        reservedVramBytes: numeric(object(raw.requirements).vram_bytes),
      },
    ],
    endpoint: {
      path,
      scheme,
      port,
      bindAddress: host,
      openaiCompatible: text(serving.api, "openai") === "openai",
    },
    createdAt: isoFromUnix(runtime.started_unix_seconds, updated * 1000 || Date.now()),
    updatedAt: isoFromUnix(updated),
    currentRevision: text(raw.config_fingerprint, `${name}-${Math.round(updated)}`),
    provenance: "live",
    details: {
      modelPath: text(model.selected_file, modelId),
      desiredState: text(raw.desired_state, "running"),
      contextLength: numeric(serving.context_length, numeric(launch.context_length)),
      concurrency: numeric(serving.concurrency, numeric(launch.concurrency, 1)),
      pid: numeric(runtime.pid) || undefined,
      restartCount: numeric(object(raw.supervisor).restart_count),
      command: text(launch.display),
      backendVersion:
        text(
          runtime.version,
          text(launch.version, text(providerDetection.version, text(backend.version))),
        ) || undefined,
      exposure: text(raw.exposure, "local"),
      model,
      serving,
      gateway: object(raw.gateway),
      launchPlan: launch,
    },
  };
}

function mapDeploymentRecord(value: unknown): DeploymentRecord {
  const raw = object(value);
  const status = text(raw.status, "deleted").toLowerCase();
  return {
    deploymentId: text(raw.deployment_id, text(raw.deploymentId, "unknown")),
    serviceName: text(raw.service_name, text(raw.serviceName, "unknown")),
    displayName: text(raw.display_name, text(raw.service_name, "Saved deployment")),
    status: status === "ready" || status === "stopped" || status === "failed" ? status : "deleted",
    model: object(raw.model),
    backend: {
      kind: backendKind(object(raw.backend).kind),
      version: text(object(raw.backend).version) || undefined,
      executable: text(object(raw.backend).executable) || undefined,
    },
    node: Object.keys(object(raw.node)).length ? object(raw.node) : undefined,
    endpoint: {
      apiBase: text(object(raw.endpoint).api_base, text(object(raw.endpoint).apiBase)) || undefined,
      openaiBase:
        text(object(raw.endpoint).openai_base, text(object(raw.endpoint).openaiBase)) || undefined,
      host: text(object(raw.endpoint).host) || undefined,
      port: numeric(object(raw.endpoint).port) || undefined,
      path: text(object(raw.endpoint).path, "/v1"),
    },
    serving: object(raw.serving),
    gateway: object(raw.gateway),
    launch: object(raw.launch),
    lastKnownGood: object(raw.last_known_good),
    plan: {
      id: text(object(raw.plan).id) || undefined,
      hash: text(object(raw.plan).hash) || undefined,
      configPath:
        text(object(raw.plan).config_path, text(object(raw.plan).configPath)) || undefined,
    },
    configSnapshotPath: text(raw.config_snapshot_path) || undefined,
    relaunchCount: numeric(raw.relaunch_count),
    createdAt: iso(raw.created_unix_seconds),
    updatedAt: iso(
      raw.updated_unix_seconds,
      numeric(raw.created_unix_seconds, Date.now() / 1000) * 1000,
    ),
    lastStartedAt: raw.last_started_unix_seconds ? iso(raw.last_started_unix_seconds) : undefined,
    stoppedAt: raw.stopped_unix_seconds ? iso(raw.stopped_unix_seconds) : undefined,
    deletedAt: raw.deleted_unix_seconds ? iso(raw.deleted_unix_seconds) : undefined,
    provenance: "live",
  };
}

async function listDeploymentRecords(signal?: AbortSignal): Promise<DeploymentRecord[]> {
  const payload = await req<JsonObject>("GET", "/v2/deployment-records", undefined, signal);
  return list(payload.records).map(mapDeploymentRecord);
}

function mapServices(payload: unknown): Service[] {
  return Object.entries(object(payload)).map(([name, service]) => mapService(name, service));
}

async function listServices(signal?: AbortSignal): Promise<Service[]> {
  return mapServices(await req<JsonObject>("GET", "/services", undefined, signal));
}

async function listNodes(signal?: AbortSignal): Promise<RiftNode[]> {
  const [hardwarePayload, backendsPayload] = await Promise.all([
    req<JsonObject>("GET", "/hardware", undefined, signal),
    req<JsonObject>("GET", "/backends", undefined, signal),
  ]);
  const hardware = object(hardwarePayload);
  const identity = object(hardware.identity);
  const capacity = object(hardware.capacity);
  const pressure = object(hardware.pressure);
  const storage = object(hardware.storage);
  const providers = object(backendsPayload.providers);
  const installed = Object.entries(providers)
    .filter(([, provider]) => bool(object(object(provider).detection).available))
    .map(([name, provider]) => {
      const detection = object(object(provider).detection);
      return `${name}@${text(detection.version, "detected")}`;
    });
  const totalVram = numeric(hardware.total_vram_bytes, numeric(capacity.vram_bytes));
  const freeVram = numeric(hardware.free_vram_bytes, numeric(pressure.vram_free_bytes, totalVram));
  const totalRam = numeric(hardware.total_host_ram_bytes, numeric(capacity.host_ram_bytes));
  const freeRam = numeric(
    hardware.free_host_ram_bytes,
    numeric(pressure.host_ram_free_bytes, totalRam),
  );
  const diskTotal = numeric(storage.total_bytes, numeric(capacity.disk_total_bytes));
  const diskFree = numeric(storage.free_bytes, numeric(pressure.disk_free_bytes));
  const hasCuda = bool(hardware.cuda_available);
  return [
    {
      id: "local",
      hostname: text(identity.hostname, "local"),
      role: "controller+agent",
      status: "ready",
      address: "127.0.0.1",
      os: text(identity.os, "unknown"),
      arch: text(identity.architecture, "unknown"),
      ramBytes: totalRam,
      ramFreeBytes: freeRam,
      diskBytes: diskTotal,
      diskFreeBytes: diskFree,
      accelerators: hasCuda
        ? [
            {
              index: numeric(hardware.cuda_device_id),
              vendor: "nvidia",
              name: text(hardware.device_name, text(identity.gpu, "CUDA GPU")),
              vramBytes: totalVram,
              vramFreeBytes: freeVram,
              computeCapability: `${numeric(hardware.compute_capability_major)}.${numeric(
                hardware.compute_capability_minor,
              )}`,
            },
          ]
        : [],
      backends: installed,
      labels: { source: "local-controller", profile: text(hardware.profile_kind, "observed") },
      enrolledAt: isoFromUnix(hardware.created_unix_seconds),
      lastHeartbeatAt: new Date().toISOString(),
      version: "legacy-control-api",
      provenance: "live",
      telemetry: {
        cpuModel: text(identity.cpu_model, "unknown"),
        logicalCpuCount: numeric(identity.logical_cpu_count, numeric(capacity.logical_cpu_count)),
        diskReadMiBs: numeric(
          object(object(hardware.calibration).result).disk
            ? object(object(object(hardware.calibration).result).disk).read_mib_s
            : undefined,
        ),
        temperatureC: numeric(object(hardware.power_thermal).temperature_c) || undefined,
        powerDrawW: numeric(object(hardware.power_thermal).power_draw_w) || undefined,
        gpuUtilizationPercent:
          numeric(object(hardware.power_thermal).gpu_utilization_percent) || undefined,
      },
    },
  ];
}

async function listIncidents(signal?: AbortSignal): Promise<Incident[]> {
  const [incidentPayload, services] = await Promise.all([
    req<JsonObject>("GET", "/incidents", undefined, signal),
    listServices(signal),
  ]);
  const history = list(object(incidentPayload).incidents).map((entry): Incident => {
    const raw = object(entry);
    const action = text(raw.action, "detected");
    const service = text(raw.service, "unknown");
    return {
      id: text(raw.incident_id, `${service}-${numeric(raw.created_unix_seconds)}`),
      severity: action === "detected" ? "warning" : "info",
      status: "resolved",
      title:
        action === "restarted"
          ? `${service} automatically restarted`
          : `${service} failure detected`,
      detail: text(raw.reason, `RIFT recorded a ${action} event for ${service}.`),
      serviceId: service,
      openedAt: isoFromUnix(raw.created_unix_seconds),
      resolvedAt: isoFromUnix(raw.created_unix_seconds),
      recovery: {
        action: action === "restarted" ? "service restarted by supervisor" : action,
        automatic: action === "restarted",
      },
      provenance: "live",
    };
  });
  const active = services
    .filter((service) => service.status === "failed" || service.status === "degraded")
    .map((service): Incident => ({
      id: `active-${service.id}`,
      severity: service.status === "failed" ? "critical" : "warning",
      status: "open",
      title: `${service.name} is ${service.status}`,
      detail: `The latest controller observation reports the ${service.backendKind} service as ${service.status}.`,
      serviceId: service.id,
      openedAt: service.updatedAt,
      recovery: { action: "Run RIFT monitor or recover after reviewing logs.", automatic: false },
      provenance: "derived-live",
    }));
  return [...active, ...history];
}

async function listBenchmarks(serviceId: string, signal?: AbortSignal): Promise<Benchmark[]> {
  const payload = await req<JsonObject>("GET", "/reports", undefined, signal);
  return list(payload.reports)
    .map((entry) => mapBenchmarkReport(entry, serviceId))
    .filter((item): item is Benchmark => item !== null)
    .sort((a, b) => b.measuredAt.localeCompare(a.measuredAt));
}

async function listRevisions(
  serviceId: string,
  signal?: AbortSignal,
): Promise<DeploymentRevision[]> {
  const state = await req<JsonObject>("GET", "/state", undefined, signal);
  const service = object(object(state.services)[serviceId]);
  if (!Object.keys(service).length) return [];
  const updated = numeric(
    service.updated_unix_seconds,
    numeric(object(service.runtime).started_unix_seconds),
  );
  const fingerprint = text(state.config_fingerprint, `${serviceId}-${Math.round(updated)}`);
  const revisions: DeploymentRevision[] = [
    {
      id: `current-${fingerprint.slice(0, 12)}`,
      serviceId,
      planHash: fingerprint,
      createdAt: isoFromUnix(updated),
      appliedBy: "RIFT controller",
      notes: "Current live controller state",
      provenance: "derived-live",
    },
  ];
  for (const [index, tuning] of list(service.tuning_history).entries()) {
    const item = object(tuning);
    revisions.push({
      id: `tuning-${index + 1}`,
      serviceId,
      planHash: `tuning-${numeric(item.created_unix_seconds)}`,
      createdAt: isoFromUnix(item.created_unix_seconds),
      appliedBy: "RIFT auto-tuner",
      notes: `Winning configuration score ${numeric(item.selection_score).toFixed(2)}`,
      provenance: "derived-live",
    });
  }
  return revisions;
}

function mapRecommendation(value: unknown, index: number, runId?: string): ModelRecommendation {
  const raw = object(value);
  const scores = object(raw.scores);
  const repo = text(raw.repo_id, `candidate-${index + 1}`);
  const format = text(raw.format, "gguf") as ModelArtifact["format"];
  const artifactSelection = object(raw.artifact_selection);
  const artifactMetadata = object(artifactSelection.metadata);
  const artifactId = text(
    artifactSelection.artifact_id,
    text(raw.artifact_id, text(raw.selected_artifact_id, repo)),
  );
  const selectedBytes = numeric(raw.selected_download_bytes);
  const estimatedBytes =
    selectedBytes > 0
      ? selectedBytes
      : Math.max(
          numeric(raw.estimated_download_bytes),
          numeric(artifactSelection.total_bytes),
          numeric(artifactMetadata.total_download_bytes),
        );
  const source = text(raw.source, "huggingface") as ModelArtifact["source"];
  const backend = backendKind(raw.backend);
  return {
    id: `recommendation-${index + 1}-${repo.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}`,
    recommendationRunId: runId || text(raw.recommendation_run_id) || undefined,
    priority: index === 0 ? "recommended" : index === 1 ? "quality" : "speed",
    artifact: {
      id: artifactId,
      displayName: basename(repo),
      family: text(raw.model_type, basename(repo)),
      parameters: numeric(raw.parameters_b)
        ? `${numeric(raw.parameters_b).toFixed(1)}B`
        : "unknown",
      source,
      repo,
      format,
      quantization:
        format === "gguf"
          ? "q4_k_m"
          : format === "awq"
            ? "awq"
            : format === "gptq"
              ? "gptq"
              : "none",
      sizeBytes: estimatedBytes,
      license: text(raw.license, "unknown"),
      trust: bool(raw.gated) ? "unknown" : "community",
      provenance: "live",
    },
    backend: {
      kind: backend,
      version: "controller-selected",
      supports: {
        formats: [format],
        accelerators: ["nvidia", "cpu"],
      },
    },
    targetNode: "local",
    rationale:
      list(raw.evidence).map(String).join(" ") || "Selected by RIFT hardware-aware ranking.",
    quality: {
      score: Math.round(100 * numeric(scores.quality_proxy, numeric(raw.final_score))),
      confidence:
        numeric(raw.confidence) >= 0.75
          ? "high"
          : numeric(raw.confidence) >= 0.5
            ? "medium"
            : "low",
      evidence: `RIFT quality proxy ${numeric(scores.quality_proxy).toFixed(2)}; hardware fit ${numeric(scores.hardware_fit).toFixed(2)}.`,
    },
    performance: {},
    resources: {
      vramBytes: Math.min(estimatedBytes, 8 * 1024 ** 3),
      ramBytes: Math.round(estimatedBytes * 0.2),
      diskBytes: estimatedBytes,
      kvCacheBytes: Math.min(1024 ** 3, Math.round(estimatedBytes * 0.1)),
    },
    compromises: list(raw.warnings).map(String),
    warnings: list(raw.warnings).map(String),
    provenance: "live",
  };
}

async function recommend(input: {
  useCase: UseCase;
  source: ModelArtifact["source"];
  localPath?: string;
  endpointUrl?: string;
}): Promise<ModelRecommendation[]> {
  return (await recommendDetailed(input)).recommendations;
}

async function latestCachedRecommendation(task: string): Promise<JsonObject | null> {
  try {
    const index = await req<JsonObject>("GET", "/v2/recommendation-runs");
    for (const entry of list(index.runs)) {
      const summary = object(entry);
      if (text(summary.task, task) !== task) continue;
      const runId = text(summary.run_id);
      if (!runId) continue;
      try {
        const run = await req<JsonObject>(
          "GET",
          `/v2/recommendation-runs/${encodeURIComponent(runId)}`,
        );
        if (list(run.recommendations).some(isDeployableRecommendation)) return run;
      } catch {
        // A corrupt or concurrently removed historical run is not a reason to
        // hide the current Hub diagnostic. Continue to the next cached run.
      }
    }
  } catch {
    // The recommendation endpoint remains the source of truth for live errors.
  }
  return null;
}

async function recommendDetailed(input: {
  useCase: UseCase;
  source: ModelArtifact["source"];
  localPath?: string;
  endpointUrl?: string;
  modelRef?: string;
}): Promise<RecommendationSearchResult> {
  if (input.source === "local") {
    const payload = await req<JsonObject>("POST", "/recommend", {
      task: input.useCase === "coding" ? "coding" : "chat",
      source: "local",
      local_path: input.localPath,
      models_dir: input.localPath,
      top: 10,
    });
    return mapRecommendationSearchResult(payload, input.useCase === "coding" ? "coding" : "chat");
  }
  if (input.source !== "huggingface" && input.source !== "catalog") {
    throw new RiftUnavailable(
      "/recommend",
      "POST",
      "not-implemented",
      "The current controller recommendation endpoint searches Hugging Face and its cache.",
    );
  }
  const payload = await req<JsonObject>("POST", "/recommend", {
    task: input.useCase === "coding" ? "coding" : "chat",
    top: 10,
    candidate_limit: 200,
    max_download_gb: 12,
    formats: ["gguf", "gptq", "awq", "safetensors"],
    include_gated: false,
    model_ref: input.modelRef,
    endpoint: input.endpointUrl,
  });
  return mapRecommendationSearchResult(payload, input.useCase === "coding" ? "coding" : "chat");
}

async function mapRecommendationSearchResult(
  payload: JsonObject,
  task: string,
): Promise<RecommendationSearchResult> {
  const runId = text(payload.recommendation_run_id, text(payload.run_id));
  const deployableRaw = list(payload.recommendations).filter(isDeployableRecommendation);
  const liveRecommendations = deployableRaw.map((value, index) =>
    mapRecommendation(value, index, runId),
  );
  const queryArmErrors = list(payload.query_arms)
    .map((value) => object(value))
    .filter((arm) => text(arm.status).toLowerCase() === "error")
    .map((arm) => `${text(arm.name, "Hub query")}: ${text(arm.error, "request failed")}`);
  const answer = object(payload.answer);
  const counts = object(payload.candidate_counts);
  const base = {
    headline: text(answer.headline),
    detail: text(answer.detail, text(answer.summary)),
    queryArmErrors,
    candidateCounts: {
      raw: numeric(counts.raw),
      afterFilters: numeric(counts.after_filters),
      enriched: numeric(counts.enriched),
      returned: numeric(counts.returned),
    },
  };
  if (liveRecommendations.length > 0) {
    return { recommendations: liveRecommendations, stale: false, ...base };
  }

  const cached = await latestCachedRecommendation(task);
  if (cached) {
    return {
      recommendations: list(cached.recommendations)
        .filter(isDeployableRecommendation)
        .map((value, index) =>
          mapRecommendation(value, index, text(cached.recommendation_run_id, text(cached.run_id))),
        ),
      stale: true,
      staleCreatedAt: isoFromUnix(cached.created_unix_seconds),
      headline: "Showing the last successful shortlist",
      detail: "Live Hub search is unavailable; cached candidates are labelled for review.",
      queryArmErrors,
      candidateCounts: base.candidateCounts,
    };
  }
  return {
    recommendations: [],
    stale: false,
    ...base,
    detail:
      queryArmErrors.length > 0
        ? text(
            base.detail,
            "Live model search failed and no deployable cached shortlist is available.",
          )
        : "Live search returned no deployable model/backend pair for this hardware.",
  };
}

async function fleetHealth(signal?: AbortSignal): Promise<FleetHealth> {
  const [services, hardware, incidents] = await Promise.all([
    listServices(signal),
    req<JsonObject>("GET", "/hardware", undefined, signal),
    listIncidents(signal),
  ]);
  const capacity = object(hardware.capacity);
  const pressure = object(hardware.pressure);
  const vramTotal = numeric(hardware.total_vram_bytes, numeric(capacity.vram_bytes));
  const vramFree = numeric(hardware.free_vram_bytes, numeric(pressure.vram_free_bytes));
  const ramTotal = numeric(hardware.total_host_ram_bytes, numeric(capacity.host_ram_bytes));
  const ramFree = numeric(hardware.free_host_ram_bytes, numeric(pressure.host_ram_free_bytes));
  return {
    nodesTotal: 1,
    nodesReady: 1,
    servicesTotal: services.length,
    servicesRunning: services.filter((service) => service.status === "running").length,
    incidentsOpen: incidents.filter((incident) => incident.status !== "resolved").length,
    capacity: {
      vramUsedBytes: Math.max(0, vramTotal - vramFree),
      vramTotalBytes: vramTotal,
      ramUsedBytes: Math.max(0, ramTotal - ramFree),
      ramTotalBytes: ramTotal,
    },
    controllerVersion: "legacy compatibility API",
    controllerBind: configuredRoot(),
    updatedAt: new Date().toISOString(),
    provenance: "live",
  };
}

function mapControllerPlan(raw: JsonObject): Plan {
  const created = numeric(raw.created_unix_seconds);
  const services = object(raw.services);
  const serviceId = Object.keys(services)[0] ?? "chat";
  const service = object(services[serviceId]);
  const launch = object(service.launch_plan);
  const endpointUrl = text(
    launch.openai_base,
    text(launch.api_base, text(object(service.runtime).api_base)),
  );
  const actions = list(raw.actions).map((entry, index) => {
    const item = object(entry);
    const kind = text(item.kind, "configure");
    const group = [
      "install",
      "download",
      "configure",
      "place",
      "launch",
      "expose",
      "benchmark",
      "recover",
    ].includes(kind)
      ? (kind as Plan["actions"][number]["group"])
      : "configure";
    const actionLaunch = object(item.launch_plan);
    const requiredBytes = numeric(item.required_bytes, numeric(item.size_bytes));
    return {
      id: `${group}-${index + 1}`,
      group,
      summary: text(item.message, `${group} ${text(item.service, serviceId)}`),
      nodeId: text(item.node, text(object(service.placement).node, "local")),
      artifact:
        requiredBytes > 0 || text(item.selected_file)
          ? {
              sizeBytes: requiredBytes || undefined,
              source: text(item.selected_file) || undefined,
            }
          : undefined,
      reserves:
        numeric(item.required_vram_bytes) || numeric(item.required_ram_bytes)
          ? {
              vramBytes: numeric(item.required_vram_bytes) || undefined,
              ramBytes: numeric(item.required_ram_bytes) || undefined,
            }
          : undefined,
      ports: numeric(actionLaunch.port) ? [numeric(actionLaunch.port)] : undefined,
      risk: (kind === "error" || group === "launch" || group === "install"
        ? "medium"
        : "low") as PlanAction["risk"],
      reversible: group !== "download",
    };
  });
  const hash = text(
    raw.fingerprint,
    text(raw.config_fingerprint, text(raw.plan_hash, `legacy-${created}`)),
  );
  const affectedNodes = list(raw.nodes)
    .map((node) => text(object(node).name, text(object(node).host)))
    .filter(Boolean);
  return {
    id: text(raw.plan_id, `plan-${text(raw.recommendation_run_id, "latest")}`),
    hash: text(raw.plan_hash, hash),
    serviceId,
    actions,
    affectedNodes: affectedNodes.length
      ? affectedNodes
      : [text(object(service.placement).node, "local")],
    expectedDowntimeMs: actions.some((action) => action.group === "launch") ? 30_000 : 0,
    rollback: {
      supported: true,
      description: "RIFT retains the last known good launch plan for supervised recovery.",
    },
    createdAt: isoFromUnix(created),
    expiresAt: new Date((created || Date.now() / 1000) * 1000 + 24 * 3600 * 1000).toISOString(),
    configPath: text(raw.materialized_config, text(raw.config_path)) || undefined,
    endpointUrl: endpointUrl || undefined,
    provenance: "derived-live",
    previewOnly: false,
  };
}

function mapOperation(raw: JsonObject, planId: string, planHash: string): ApplyProgress {
  const result = object(raw.result);
  const resultPlan = object(result.plan);
  const status = text(raw.status, "RUNNING").toUpperCase() as ApplyProgress["status"];
  const stage = text(raw.stage, "queued");
  const phase = [
    "queued",
    "preparing",
    "executing",
    "installing",
    "downloading",
    "configuring",
    "placing",
    "launching",
    "exposing",
    "benchmarking",
    "succeeded",
    "failed",
    "cancelled",
    "interrupted",
    "rolled_back",
  ].includes(stage)
    ? (stage as ApplyProgress["phase"])
    : status === "SUCCEEDED"
      ? "succeeded"
      : status === "FAILED"
        ? "failed"
        : status === "CANCELLED"
          ? "cancelled"
          : status === "INTERRUPTED"
            ? "interrupted"
            : "executing";
  return {
    planId: text(resultPlan.plan_id, planId),
    planHash: text(resultPlan.plan_hash, planHash),
    operationId: text(raw.operation_id),
    status,
    phase,
    percent: raw.percent === null ? null : numeric(raw.percent, 0),
    message: text(raw.message, text(raw.error, "Operation in progress")),
    startedAt: iso(raw.created_unix_seconds),
    updatedAt: iso(
      raw.updated_unix_seconds,
      numeric(raw.created_unix_seconds, Date.now() / 1000) * 1000,
    ),
    error: text(raw.error) || undefined,
    result: Object.keys(result).length ? result : undefined,
  };
}

function mapEvaluationCase(value: unknown): EvaluationRun["cases"][number] {
  const raw = object(value);
  const status = text(raw.status, "error").toLowerCase();
  return {
    caseId: text(raw.case_id, "unknown"),
    status:
      status === "pass" || status === "fail" || status === "not_assessed" || status === "error"
        ? status
        : "error",
    criteria: text(raw.criteria, "explicit deterministic criterion"),
    detail: text(raw.detail, "No detail was provided."),
    elapsedSeconds:
      raw.elapsed_seconds === null || raw.elapsed_seconds === undefined
        ? undefined
        : numeric(raw.elapsed_seconds),
    response: typeof raw.response === "string" ? raw.response : undefined,
    judge: Object.keys(object(raw.judge)).length
      ? {
          status:
            text(object(raw.judge).status, "not_assessed") === "assessed" ||
            text(object(raw.judge).status) === "error"
              ? (text(object(raw.judge).status) as "assessed" | "error")
              : "not_assessed",
          score:
            object(raw.judge).score === null || object(raw.judge).score === undefined
              ? null
              : numeric(object(raw.judge).score),
          detail: text(object(raw.judge).detail) || null,
        }
      : undefined,
  };
}

function mapEvaluation(value: unknown): EvaluationRun {
  const raw = object(value);
  const suite = object(raw.suite);
  const status = text(raw.status, "not_run").toLowerCase();
  return {
    runId: text(raw.run_id, "unknown"),
    service: text(raw.service, "unknown"),
    status:
      status === "running" ||
      status === "completed" ||
      status === "deadline" ||
      status === "not_run"
        ? status
        : "not_run",
    suite: {
      id: text(suite.id, "unknown"),
      version: text(suite.version, "unknown"),
      cases: list(suite.cases),
    },
    summary: Object.fromEntries(
      Object.entries(object(raw.summary)).map(([key, entry]) => [key, numeric(entry)]),
    ),
    cases: list(raw.cases).map(mapEvaluationCase),
    available: bool(raw.available, true),
    required: bool(raw.required, false),
    reportPath: text(raw.report_path) || undefined,
    modelRevision: object(raw.model_revision),
    configuration: object(raw.configuration),
    assessment: text(raw.assessment) || undefined,
    provenance: "live",
  };
}

function mapOperationRecord(value: unknown): OperationRecord {
  const raw = object(value);
  const rawStatus = text(raw.status, "RUNNING").toUpperCase();
  const status = ["RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", "INTERRUPTED"].includes(rawStatus)
    ? (rawStatus as OperationRecord["status"])
    : "FAILED";
  const result = object(raw.result);
  const display = deriveOperationDisplay({
    status,
    stage: text(raw.stage) || undefined,
    percent:
      raw.percent === null
        ? null
        : raw.percent === undefined
          ? undefined
          : numeric(raw.percent, Number.NaN),
    message: text(raw.message) || undefined,
    error: text(raw.error) || undefined,
  });
  return {
    operationId: text(raw.operation_id, "unknown"),
    requestId: text(raw.request_id, "unknown"),
    action: text(raw.action, "unknown"),
    status,
    stage: display.stage,
    message: display.message,
    percent: display.percent,
    createdAt: iso(raw.created_unix_seconds),
    updatedAt: iso(
      raw.updated_unix_seconds,
      numeric(raw.created_unix_seconds, Date.now() / 1000) * 1000,
    ),
    completedAt: raw.completed_unix_seconds ? iso(raw.completed_unix_seconds) : undefined,
    error: text(raw.error) || undefined,
    details: Object.keys(object(raw.details)).length ? object(raw.details) : undefined,
    result: Object.keys(result).length ? result : undefined,
  };
}

async function waitForOperation(operationId: string): Promise<JsonObject> {
  const deadline = Date.now() + 15 * 60_000;
  while (Date.now() < deadline) {
    const payload = await req<JsonObject>(
      "GET",
      `/v2/operations/${encodeURIComponent(operationId)}`,
    );
    const status = text(payload.status, "RUNNING").toUpperCase();
    if (status !== "RUNNING") {
      if (status !== "SUCCEEDED") {
        throw new RiftApiError(409, `/v2/operations/${encodeURIComponent(operationId)}`, payload);
      }
      return object(payload.result);
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1_000));
  }
  throw new RiftUnavailable(
    `/v2/operations/${encodeURIComponent(operationId)}`,
    "GET",
    "timeout",
    "operation did not finish within 15 minutes",
  );
}

async function resolveOperation(payload: JsonObject): Promise<JsonObject> {
  const operationId = text(payload.operation_id);
  return operationId ? waitForOperation(operationId) : payload;
}

async function resolveDeploymentAction(
  payload: JsonObject,
  service: string,
): Promise<ApplyProgress> {
  const resolved = await resolveOperation(payload);
  return mapOperation(
    {
      status: "SUCCEEDED",
      stage: "succeeded",
      percent: 100,
      message: text(resolved.reason, "Deployment action completed."),
      result: resolved,
    },
    service,
    text(payload.plan_hash, "unknown"),
  );
}

async function currentPlan(signal?: AbortSignal): Promise<Plan> {
  const raw = await req<JsonObject>("GET", "/plan", undefined, signal);
  if (raw.available === false) {
    throw new RiftUnavailable("/plan", "GET", "not-implemented", text(raw.reason));
  }
  return mapControllerPlan(raw);
}

export const rift = {
  isConfigured: () => true,
  connectionInfo: () => ({
    root: configuredRoot(),
    mode: "legacy-live" as const,
    previewEnabled: previewEnabled(),
  }),

  health: fleetHealth,
  listNodes,
  getNode: async (id: string, signal?: AbortSignal) => {
    const nodes = await listNodes(signal);
    const node = nodes.find((item) => item.id === id);
    if (!node) throw new RiftApiError(404, `/nodes/${id}`, { error: "node not found" });
    return node;
  },
  createEnrollmentToken: async (_ttlSeconds = 900): Promise<EnrollmentToken> => {
    throw new RiftUnavailable(
      "/enrollment-tokens",
      "POST",
      "not-implemented",
      "Agent enrollment is part of the target controller-agent protocol.",
    );
  },
  drainNode: async (): Promise<void> => {
    throw new RiftUnavailable("/nodes/actions", "POST", "not-implemented");
  },

  listMeshSightings: async (signal?: AbortSignal): Promise<MeshSighting[]> => {
    const payload = await req<JsonObject>("GET", "/v2/mesh/sightings", undefined, signal);
    return list(payload.sightings).map(mapMeshSighting);
  },
  discoverMesh: async (providers?: string[], signal?: AbortSignal): Promise<MeshSighting[]> => {
    const payload = await req<JsonObject>(
      "POST",
      "/v2/mesh/discover",
      providers?.length ? { providers } : {},
      signal,
    );
    return list(payload.sightings).map(mapMeshSighting);
  },
  listMeshNodes: async (signal?: AbortSignal): Promise<MeshNode[]> => {
    const payload = await req<JsonObject>("GET", "/v2/mesh/nodes", undefined, signal);
    return list(payload.nodes).map(mapMeshNode);
  },
  getMeshTopology: async (signal?: AbortSignal): Promise<MeshTopology> => {
    const payload = await req<JsonObject>("GET", "/v2/mesh/topology", undefined, signal);
    return {
      nodes: list(payload.nodes).map(mapMeshNode),
      links: list(payload.links).map(mapMeshLink),
      evidence: text(payload.evidence, "UNKNOWN"),
    };
  },
  beginMeshEnrollment: async (
    sightingId: string,
    ttlSeconds = 120,
    signal?: AbortSignal,
  ): Promise<EnrollmentChallenge> =>
    mapEnrollmentChallenge(
      await req<JsonObject>(
        "POST",
        "/v2/mesh/enrollments",
        { sighting_id: sightingId, ttl_seconds: ttlSeconds },
        signal,
      ),
    ),
  approveMeshEnrollment: async (
    enrollmentId: string,
    pairingCode: string,
    signal?: AbortSignal,
  ): Promise<EnrollmentApproval> => {
    const payload = await req<JsonObject>(
      "POST",
      `/v2/mesh/enrollments/${encodeURIComponent(enrollmentId)}/approve`,
      { pairing_code: pairingCode },
      signal,
    );
    const enrollment = object(payload.enrollment);
    const state = text(enrollment.state, "APPROVED").toUpperCase();
    return {
      node: mapMeshNode(payload.node),
      enrollment: {
        enrollmentId: text(enrollment.enrollment_id, text(enrollment.enrollmentId, enrollmentId)),
        sightingId: text(enrollment.sighting_id, text(enrollment.sightingId)),
        state:
          state === "PAIRING_PENDING" || state === "EXPIRED" || state === "REJECTED"
            ? state
            : "APPROVED",
        approvedAt:
          enrollment.approved_at || enrollment.approvedAt
            ? iso(enrollment.approved_at ?? enrollment.approvedAt)
            : undefined,
      },
    };
  },
  openManagedEnrollmentWindow: async (ttlSeconds = 600): Promise<ManagedEnrollmentWindow> => {
    const payload = await req<JsonObject>("POST", "/v2/mesh/enrollment-window", {
      ttl_seconds: ttlSeconds,
    });
    return {
      controllerId: text(payload.controller_id, "unknown"),
      open: bool(payload.open),
      expiresAt: payload.expires_at ? iso(payload.expires_at) : undefined,
      pendingCount: numeric(payload.pending_count),
      bootstrap: object(payload.bootstrap) as ManagedEnrollmentWindow["bootstrap"],
    };
  },
  getManagedEnrollmentWindow: async (): Promise<ManagedEnrollmentWindow> => {
    const payload = await req<JsonObject>("GET", "/v2/mesh/enrollment-window");
    return {
      controllerId: text(payload.controller_id, "unknown"),
      open: bool(payload.open),
      expiresAt: payload.expires_at ? iso(payload.expires_at) : undefined,
      pendingCount: numeric(payload.pending_count),
    };
  },
  listManagedEnrollments: async (): Promise<ManagedEnrollment[]> => {
    const payload = await req<JsonObject>("GET", "/v2/mesh/enrollments");
    return list(payload.enrollments).map(mapManagedEnrollment);
  },
  approveManagedEnrollment: async (
    enrollmentId: string,
    pairingCode: string,
  ): Promise<ManagedEnrollment> =>
    mapManagedEnrollment(
      object(
        await req<JsonObject>(
          "POST",
          `/v2/mesh/enrollments/${encodeURIComponent(enrollmentId)}/approve`,
          { pairing_code: pairingCode },
        ),
      ).enrollment,
    ),
  cancelManagedEnrollment: async (enrollmentId: string): Promise<ManagedEnrollment> =>
    mapManagedEnrollment(
      await req<JsonObject>(
        "POST",
        `/v2/mesh/enrollments/${encodeURIComponent(enrollmentId)}/cancel`,
        {},
      ),
    ),

  listServices,
  listDeploymentRecords,
  getService: async (id: string, signal?: AbortSignal) => {
    const services = await listServices(signal);
    const service = services.find((item) => item.id === id);
    if (!service) throw new RiftApiError(404, `/services/${id}`, { error: "service not found" });
    return service;
  },
  listRevisions,
  listBenchmarks,
  recommend,
  recommendDetailed,
  createPlan: async (input: {
    recommendationId?: string;
    recommendationRunId?: string;
    selector?: string;
    artifactId: string;
    backendKind: string;
    targetNodeId: string;
    serviceName: string;
    exposure: "local" | "lan" | "public";
  }): Promise<Plan> => {
    if (!input.recommendationRunId) {
      throw new RiftUnavailable(
        "/v2/plans",
        "POST",
        "not-implemented",
        "The live recommendation run is missing; run model discovery again.",
      );
    }
    return mapControllerPlan(
      await req<JsonObject>(
        "POST",
        "/v2/plans",
        planRequest(
          input.recommendationRunId,
          input.selector ?? recommendationSelector("recommended"),
          {
            artifactId: input.artifactId,
            backendKind: input.backendKind,
            targetNodeId: input.targetNodeId,
            serviceName: input.serviceName,
            exposure: input.exposure,
          },
        ),
      ),
    );
  },
  getPlan: async (id: string, signal?: AbortSignal) => {
    const raw = await req<JsonObject>(
      "GET",
      `/v2/plans/${encodeURIComponent(id)}`,
      undefined,
      signal,
    );
    return mapControllerPlan(raw);
  },
  applyPlan: async (
    id: string,
    planHash: string,
    options: {
      configPath: string;
      allowDownload: boolean;
      allowInstall: boolean;
      allowLaunch: boolean;
      allowRemote?: boolean;
      optimize?: boolean;
      writeBack?: boolean;
    },
  ): Promise<ApplyProgress> => {
    const payload = await req<JsonObject>(
      "POST",
      `/v2/plans/${encodeURIComponent(id)}/apply`,
      applyRequest(options.configPath, options, { id, hash: planHash }),
      undefined,
      30_000,
    );
    if (payload.applied === false && !payload.operation_id) {
      throw new RiftApiError(409, `/v2/plans/${encodeURIComponent(id)}/apply`, payload);
    }
    return mapOperation(payload, id, planHash);
  },
  getOperation: async (
    operationId: string,
    planId: string,
    planHash: string,
    signal?: AbortSignal,
  ): Promise<ApplyProgress> => {
    const payload = await req<JsonObject>(
      "GET",
      `/v2/operations/${encodeURIComponent(operationId)}`,
      undefined,
      signal,
    );
    return mapOperation(payload, planId, planHash);
  },
  listOperations: async (signal?: AbortSignal): Promise<OperationRecord[]> => {
    const payload = await req<JsonObject>("GET", "/v2/operations", undefined, signal);
    return list(payload.operations).map(mapOperationRecord);
  },
  listEvaluations: async (service?: string, signal?: AbortSignal): Promise<EvaluationRun[]> => {
    const query = service ? `?service=${encodeURIComponent(service)}` : "";
    const payload = await req<JsonObject>("GET", `/v2/evaluations${query}`, undefined, signal);
    return list(payload.evaluations).map(mapEvaluation);
  },
  getEvaluation: async (runId: string, signal?: AbortSignal): Promise<EvaluationRun> =>
    mapEvaluation(
      await req<JsonObject>(
        "GET",
        `/v2/evaluations/${encodeURIComponent(runId)}`,
        undefined,
        signal,
      ),
    ),
  evaluateService: async (
    service: string,
    options: {
      suite?: Record<string, unknown>;
      maxTokens?: number;
      deadlineSeconds?: number;
      retainResponses?: boolean;
      required?: boolean;
      judge?: {
        endpoint: string;
        model: string;
        allowed_hosts: string[];
        credential_ref: "none" | `env:${string}`;
        external_data_consent: boolean;
        timeout_seconds?: number;
        max_tokens?: number;
      };
    } = {},
  ): Promise<EvaluationRun> => {
    const payload = await req<JsonObject>("POST", "/v2/evaluations", {
      service,
      suite: options.suite,
      max_tokens: options.maxTokens ?? 128,
      deadline_seconds: options.deadlineSeconds ?? 60,
      retain_responses: options.retainResponses ?? false,
      required: options.required ?? false,
      judge: options.judge,
    });
    return mapEvaluation(await resolveOperation(payload));
  },
  cancelOperation: async (operationId: string, reason = "Cancelled from dashboard") =>
    mapOperation(
      await req<JsonObject>("POST", `/v2/operations/${encodeURIComponent(operationId)}/cancel`, {
        reason,
      }),
      "unknown",
      "unknown",
    ),
  restartService: async (service: string): Promise<ApplyProgress> => {
    const payload = await req<JsonObject>(
      "POST",
      `/v2/deployments/${encodeURIComponent(service)}/actions`,
      { service, action: "restart", allow_launch: true },
    );
    return resolveDeploymentAction(payload, service);
  },
  recoverService: async (service: string): Promise<ApplyProgress> => {
    const payload = await req<JsonObject>(
      "POST",
      `/v2/deployments/${encodeURIComponent(service)}/actions`,
      { service, action: "recover", allow_launch: true },
    );
    return resolveDeploymentAction(payload, service);
  },
  rollback: async (service: string): Promise<ApplyProgress> => {
    const payload = await req<JsonObject>(
      "POST",
      `/v2/deployments/${encodeURIComponent(service)}/actions`,
      {
        service,
        action: "rollback",
        allow_launch: true,
      },
    );
    return resolveDeploymentAction(payload, service);
  },
  listIncidents,
  acknowledgeIncident: async (): Promise<void> => {
    throw new RiftUnavailable("/incidents/actions", "POST", "not-implemented");
  },
  resolveIncident: async (): Promise<void> => {
    throw new RiftUnavailable("/incidents/actions", "POST", "not-implemented");
  },
  planYaml: async (planId?: string): Promise<string> => {
    const generated = planId
      ? await req<JsonObject>("GET", `/v2/plans/${encodeURIComponent(planId)}`)
      : await req<JsonObject>("GET", "/generated-config");
    return JSON.stringify(generated, null, 2);
  },
  timeline: (signal?: AbortSignal) => req<JsonObject>("GET", "/timeline", undefined, signal),
  logs: (signal?: AbortSignal, service?: string) =>
    req<JsonObject>(
      "GET",
      `/logs?service=${encodeURIComponent(service || "chat")}`,
      undefined,
      signal,
    ),
  backends: (signal?: AbortSignal) => req<JsonObject>("GET", "/backends", undefined, signal),
  reports: (signal?: AbortSignal) => req<JsonObject>("GET", "/reports", undefined, signal),
  settings: async (signal?: AbortSignal): Promise<SettingsSnapshot> => {
    const payload = await req<JsonObject>("GET", "/v2/settings", undefined, signal);
    return {
      apiVersion: text(payload.api_version, "2"),
      available: bool(payload.available, true),
      configPath: text(payload.config_path) || undefined,
      configError: text(payload.config_error) || undefined,
      modelSources: object(payload.model_sources),
      gateway: object(payload.gateway),
      services: Object.fromEntries(
        Object.entries(object(payload.services)).map(([key, value]) => [key, object(value)]),
      ),
      policies: object(payload.policies),
      mesh: object(payload.mesh),
    };
  },
  currentPlan,
  benchmarkService: async (
    service: string,
    prompt = "Explain what RIFT does in one sentence.",
    maxTokens = 32,
  ) =>
    resolveOperation(
      await req<JsonObject>("POST", "/benchmark", { service, prompt, max_tokens: maxTokens }),
    ),
  benchmarkSuite: async (
    service: string,
    options: {
      prompt?: string;
      maxTokens?: number;
      warmups?: number;
      repetitions?: number;
      concurrency?: number;
    } = {},
  ) =>
    resolveOperation(
      await req<JsonObject>("POST", "/benchmark-suite", {
        service,
        prompt: options.prompt,
        max_tokens: options.maxTokens ?? 48,
        warmups: options.warmups ?? 1,
        repetitions: options.repetitions ?? 3,
        concurrency: options.concurrency ?? 1,
      }),
    ),
  tuneService: async (
    service: string,
    options: { live?: boolean; allowRestart?: boolean; candidateLimit?: number } = {},
  ) =>
    resolveOperation(
      await req<JsonObject>("POST", "/tune", {
        service,
        live: options.live ?? false,
        allow_restart: options.allowRestart ?? false,
        candidate_limit: options.candidateLimit ?? 4,
      }),
    ),
  destroyService: async (service: string) => req<JsonObject>("POST", "/destroy", { service }),
  relaunchDeployment: async (
    deploymentId: string,
    options: {
      allowDownload?: boolean;
      allowInstall?: boolean;
      allowLaunch?: boolean;
      allowRemote?: boolean;
      optimize?: boolean;
    } = {},
  ): Promise<JsonObject> =>
    resolveOperation(
      await req<JsonObject>(
        "POST",
        `/v2/deployment-records/${encodeURIComponent(deploymentId)}/launch`,
        {
          allow_download: options.allowDownload ?? false,
          allow_install: options.allowInstall ?? false,
          allow_launch: options.allowLaunch ?? false,
          allow_remote: options.allowRemote ?? false,
          optimize: options.optimize ?? false,
        },
      ),
    ),

  subscribe(onEvent: (event: RiftEvent) => void, onStale: (stale: boolean) => void): () => void {
    let closed = false;
    const poll = async () => {
      try {
        const health = await fleetHealth();
        if (!closed) {
          onStale(false);
          onEvent({ kind: "health", health });
        }
      } catch {
        if (!closed) onStale(true);
      }
    };
    void poll();
    const timer = setInterval(poll, 10_000);
    return () => {
      closed = true;
      clearInterval(timer);
    };
  },
};

export type RiftClient = typeof rift;
