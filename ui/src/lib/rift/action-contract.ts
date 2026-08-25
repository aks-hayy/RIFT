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

export function planRequest(recommendationRunId: string, selector: string): Record<string, string> {
  if (!recommendationRunId.trim()) throw new Error("recommendation run id is required");
  return { recommendation_run_id: recommendationRunId, selector };
}

export function applyRequest(
  configPath: string,
  permissions: ApplyPermissionInput,
): Record<string, string | boolean> {
  if (!configPath.trim()) throw new Error("materialized config path is required");
  return {
    config: configPath,
    allow_download: permissions.allowDownload,
    allow_install: permissions.allowInstall,
    allow_launch: permissions.allowLaunch,
    allow_remote: permissions.allowRemote ?? false,
    optimize: permissions.optimize ?? false,
    write_back: permissions.writeBack ?? false,
  };
}
