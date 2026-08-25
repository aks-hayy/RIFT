// RIFT typed resource contracts.
// These describe the wire shape the controller API is expected to return.
// Every endpoint referenced here is documented alongside the hook that uses it.

export type NodeId = string;
export type ServiceId = string;
export type PlanId = string;
export type RevisionId = string;
export type IncidentId = string;

export type DataProvenance = "live" | "derived-live" | "preview";

export type NodeRole = "controller" | "agent" | "controller+agent";
export type NodeStatus = "ready" | "enrolling" | "draining" | "offline" | "error";

export interface Accelerator {
  index: number;
  vendor: "nvidia" | "amd" | "apple" | "intel" | "cpu";
  name: string;
  vramBytes: number;
  vramFreeBytes: number;
  computeCapability?: string;
}

export interface RiftNode {
  id: NodeId;
  hostname: string;
  role: NodeRole;
  status: NodeStatus;
  address: string; // internal address for controller <-> agent
  os: string;
  arch: string;
  ramBytes: number;
  ramFreeBytes: number;
  diskBytes: number;
  diskFreeBytes: number;
  accelerators: Accelerator[];
  backends: string[]; // installed backends, e.g. "vllm@0.6.2", "llama.cpp@b3459"
  labels: Record<string, string>;
  enrolledAt: string; // ISO-8601
  lastHeartbeatAt: string; // ISO-8601
  version: string;
  provenance?: DataProvenance;
  telemetry?: {
    cpuModel?: string;
    logicalCpuCount?: number;
    diskReadMiBs?: number;
    temperatureC?: number;
    powerDrawW?: number;
    gpuUtilizationPercent?: number;
  };
}

export type ArtifactFormat = "gguf" | "safetensors" | "gptq" | "awq" | "hf";
export type Quantization =
  | "f16"
  | "bf16"
  | "int8"
  | "q8_0"
  | "q6_k"
  | "q5_k_m"
  | "q4_k_m"
  | "q4_0"
  | "int4"
  | "awq"
  | "gptq"
  | "none";

export interface ModelArtifact {
  id: string;
  displayName: string;
  family: string; // e.g. "Llama 3.1", "Qwen 2.5"
  parameters: string; // "8B", "70B"
  source: "huggingface" | "local" | "endpoint" | "catalog";
  repo?: string; // e.g. "meta-llama/Llama-3.1-8B-Instruct"
  revision?: string;
  format: ArtifactFormat;
  quantization: Quantization;
  sizeBytes: number;
  sha256?: string;
  license: string;
  licenseUrl?: string;
  trust: "verified" | "community" | "unknown";
  provenance?: DataProvenance;
}

export type BackendKind =
  "vllm" | "llama.cpp" | "sglang" | "lmcache" | "tgi" | "mlc" | "ollama" | "external";

export interface Backend {
  kind: BackendKind;
  version: string;
  supports: {
    formats: ArtifactFormat[];
    accelerators: Accelerator["vendor"][];
  };
}

export type UseCase = "chat" | "coding" | "documents" | "agent" | "custom";
export type Priority = "recommended" | "quality" | "speed";

export interface ModelRecommendation {
  id?: string;
  recommendationRunId?: string;
  priority: Priority;
  artifact: ModelArtifact;
  backend: Backend;
  targetNode: NodeId;
  rationale: string; // plain-language why
  quality: {
    score: number; // 0-100 normalized
    confidence: "low" | "medium" | "high";
    evidence: string; // e.g. "MMLU 68.4, ArenaHard 41.2 (published)"
  };
  performance: {
    estimatedTokensPerSec?: number;
    measuredTokensPerSec?: number;
    firstTokenMs?: number;
  };
  resources: {
    vramBytes: number;
    ramBytes: number;
    diskBytes: number;
    kvCacheBytes: number;
  };
  compromises: string[]; // e.g. "4-bit quantization: ~2% quality loss"
  warnings: string[]; // license/trust/hardware warnings
  provenance?: DataProvenance;
}

export interface RecommendationSearchResult {
  recommendations: ModelRecommendation[];
  stale: boolean;
  staleCreatedAt?: string;
  headline?: string;
  detail?: string;
  queryArmErrors: string[];
  candidateCounts?: {
    raw: number;
    afterFilters: number;
    enriched: number;
    returned: number;
  };
}

export interface ServiceEndpoint {
  path: string; // e.g. "/v1"
  scheme: "http" | "https";
  port: number;
  bindAddress: string; // e.g. "127.0.0.1" (local by default) or "0.0.0.0"
  openaiCompatible: boolean;
}

export type ServiceStatus = "planning" | "applying" | "running" | "degraded" | "stopped" | "failed";

export interface Service {
  id: ServiceId;
  name: string;
  useCase: UseCase;
  status: ServiceStatus;
  artifactId: string;
  backendKind: BackendKind;
  assignments: Assignment[];
  endpoint: ServiceEndpoint;
  createdAt: string;
  updatedAt: string;
  currentRevision: RevisionId;
  provenance?: DataProvenance;
  details?: {
    modelPath?: string;
    desiredState?: string;
    contextLength?: number;
    concurrency?: number;
    pid?: number;
    restartCount?: number;
    command?: string;
  };
}

export interface Assignment {
  nodeId: NodeId;
  gpuIndices: number[];
  reservedVramBytes: number;
}

export type PlanActionGroup =
  "install" | "download" | "configure" | "place" | "launch" | "expose" | "benchmark" | "recover";

export interface PlanAction {
  id: string;
  group: PlanActionGroup;
  summary: string; // plain-language
  nodeId?: NodeId;
  artifact?: { sizeBytes?: number; sha256?: string; source?: string };
  reserves?: { vramBytes?: number; ramBytes?: number; diskBytes?: number };
  ports?: number[];
  expectedDurationMs?: number;
  risk: "low" | "medium" | "high";
  reversible: boolean;
}

export interface Plan {
  id: PlanId;
  hash: string; // immutable content hash
  serviceId: ServiceId;
  actions: PlanAction[];
  affectedNodes: NodeId[];
  expectedDowntimeMs: number;
  rollback: {
    supported: boolean;
    description: string;
  };
  createdAt: string;
  expiresAt: string;
  configPath?: string;
  endpointUrl?: string;
  provenance?: DataProvenance;
  previewOnly?: boolean;
}

export type ApplyPhase =
  | "queued"
  | "installing"
  | "downloading"
  | "configuring"
  | "placing"
  | "launching"
  | "exposing"
  | "benchmarking"
  | "succeeded"
  | "failed"
  | "rolled_back";

export interface ApplyProgress {
  planId: PlanId;
  planHash: string;
  phase: ApplyPhase;
  actionId?: string;
  nodeId?: NodeId;
  percent: number; // 0-100
  message: string;
  startedAt: string;
  updatedAt: string;
  failure?: {
    actionId: string;
    nodeId?: NodeId;
    reason: string;
    recoverable: boolean;
  };
}

export interface DeploymentRevision {
  id: RevisionId;
  serviceId: ServiceId;
  planHash: string;
  createdAt: string;
  appliedBy: string;
  notes?: string;
  provenance?: DataProvenance;
}

export interface Benchmark {
  id: string;
  serviceId: ServiceId;
  measuredAt: string;
  tokensPerSec: number;
  firstTokenMs: number;
  concurrency: number;
  contextTokens: number;
  outputTokens: number;
  provenance?: DataProvenance;
}

export type IncidentSeverity = "info" | "warning" | "critical";
export type IncidentStatus = "open" | "acknowledged" | "resolved";

export interface Incident {
  id: IncidentId;
  severity: IncidentSeverity;
  status: IncidentStatus;
  title: string;
  detail: string;
  nodeId?: NodeId;
  serviceId?: ServiceId;
  openedAt: string;
  resolvedAt?: string;
  recovery?: {
    action: string;
    automatic: boolean;
  };
  provenance?: DataProvenance;
}

export interface FleetHealth {
  nodesTotal: number;
  nodesReady: number;
  servicesTotal: number;
  servicesRunning: number;
  incidentsOpen: number;
  capacity: {
    vramUsedBytes: number;
    vramTotalBytes: number;
    ramUsedBytes: number;
    ramTotalBytes: number;
  };
  controllerVersion: string;
  controllerBind: string;
  updatedAt: string;
  provenance?: DataProvenance;
}

export interface EnrollmentToken {
  token: string;
  command: string; // full one-liner to run on the new node
  expiresAt: string;
  createdBy: string;
}

export type MeshTrustState =
  "DISCOVERED_UNTRUSTED" | "PAIRING_PENDING" | "ENROLLED" | "ACTIVE" | "REVOKED";

/** A transport observation. A sighting is never proof of identity or enrollment. */
export interface MeshSighting {
  sightingId: string;
  provider: string;
  endpoint: string;
  nodeHint: string;
  apiVersion: string;
  bootstrapFingerprint: string;
  observedAt: string;
  expiresAt: string;
  interfaceId?: string;
  trustState: MeshTrustState;
  metadata: Record<string, unknown>;
}

/** A controller-approved mesh identity. Only enrolled nodes appear in this resource. */
export interface MeshNode {
  nodeId: NodeId;
  hostname: string;
  endpoint?: string;
  trustState: MeshTrustState;
  routable: boolean;
  certificateRequired: boolean;
  healthy: boolean;
  queueDepth: number;
  labels: Record<string, string>;
  enrolledAt?: string;
  lastSeenAt?: string;
  capabilities?: Record<string, unknown>;
}

export interface MeshLink {
  sourceNodeId: NodeId;
  targetNodeId: NodeId;
  rttP50Ms: number;
  rttP95Ms: number;
  jitterMs: number;
  lossRatio: number;
  uploadMbps: number;
  downloadMbps: number;
  evidence: string;
}

export interface MeshTopology {
  nodes: MeshNode[];
  links: MeshLink[];
  evidence: string;
}

export type EnrollmentState =
  | "PAIRING_PENDING"
  | "ENROLLED"
  | "CERTIFICATE_ISSUED"
  | "VERIFYING"
  | "ACTIVE"
  | "APPROVED"
  | "EXPIRED"
  | "REJECTED"
  | "CANCELLED";

export interface ManagedEnrollmentWindow {
  controllerId: string;
  open: boolean;
  expiresAt?: string;
  pendingCount: number;
  bootstrap?: { started: boolean; host?: string; port?: number; controller_id?: string };
}

export interface ManagedEnrollment {
  enrollmentId: string;
  nodeId?: string;
  displayName?: string;
  endpoint?: string;
  state: EnrollmentState;
  expiresAt?: string;
  attempts?: number;
}

export interface EnrollmentChallenge {
  enrollmentId: string;
  sightingId: string;
  expiresAt: string;
  state: EnrollmentState;
  nodeHint?: string;
}

export interface EnrollmentApproval {
  node: MeshNode;
  enrollment: {
    enrollmentId: string;
    sightingId: string;
    state: EnrollmentState;
    approvedAt?: string;
  };
}

/** Union of every server-sent event on /events. */
export type RiftEvent =
  | { kind: "node.enrolled"; node: RiftNode }
  | { kind: "node.status"; nodeId: NodeId; status: NodeStatus }
  | { kind: "plan.progress"; progress: ApplyProgress }
  | { kind: "service.status"; serviceId: ServiceId; status: ServiceStatus }
  | { kind: "incident.opened"; incident: Incident }
  | { kind: "incident.resolved"; incidentId: IncidentId }
  | { kind: "health"; health: FleetHealth };
