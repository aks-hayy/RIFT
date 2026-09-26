export type RecommendationPriority = "recommended" | "quality" | "speed";

export interface ApplyPermissionInput {
  allowDownload: boolean;
  allowInstall: boolean;
  allowLaunch: boolean;
  allowRemote?: boolean;
  optimize?: boolean;
  writeBack?: boolean;
}

export function isDeployableRecommendation(value: unknown): boolean {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const candidate = value as Record<string, unknown>;
  const support = String(candidate.support_level ?? "").toUpperCase();
  const backend = String(candidate.backend ?? "").toLowerCase();
  return (
    support !== "UNSUPPORTED" && backend !== "" && backend !== "none" && backend !== "external"
  );
}

export function recommendationSelector(priority: RecommendationPriority): string {
  if (priority === "quality") return "highest_quality";
  if (priority === "speed") return "fastest";
  return "best_estimated";
}

export function planRequest(
  recommendationRunId: string,
  selector: string,
  intent: {
    artifactId?: string;
    backendKind?: string;
    targetNodeId?: string;
    serviceName?: string;
    exposure?: "local" | "lan" | "public";
    monitoringProfile?: string;
    monitoringMetrics?: string[];
    monitoringObjectives?: MonitoringObjective[];
  } = {},
): Record<string, unknown> {
  if (!recommendationRunId.trim()) throw new Error("recommendation run id is required");
  const request: Record<string, string> = { recommendation_run_id: recommendationRunId, selector };
  if (intent.artifactId) request.artifact_id = intent.artifactId;
  if (intent.backendKind) request.backend_kind = intent.backendKind;
  if (intent.targetNodeId) request.target_node_id = intent.targetNodeId;
  if (intent.serviceName) request.service_name = intent.serviceName;
  if (intent.exposure) request.exposure = intent.exposure;
  if (intent.monitoringProfile) request.monitoring_profile = intent.monitoringProfile;
  if (intent.monitoringMetrics?.length) request.monitoring_metrics = intent.monitoringMetrics.join(",");
  if (intent.monitoringObjectives?.length) {
    request.monitoring_objectives = JSON.stringify(intent.monitoringObjectives);
  }
  return request;
}

export function applyRequest(
  configPath: string,
  permissions: ApplyPermissionInput,
  plan?: { id?: string; hash?: string },
): Record<string, string | boolean> {
  if (!configPath.trim()) throw new Error("materialized config path is required");
  const request: Record<string, string | boolean> = {
    config: configPath,
    allow_download: permissions.allowDownload,
    allow_install: permissions.allowInstall,
    allow_launch: permissions.allowLaunch,
    allow_remote: permissions.allowRemote ?? false,
    optimize: permissions.optimize ?? false,
    write_back: permissions.writeBack ?? false,
  };
  if (plan?.id) request.plan_id = plan.id;
  if (plan?.hash) request.plan_hash = plan.hash;
  return request;
}
import type { MonitoringObjective } from "./types";
