export type RecommendationViewState = "ready" | "stale" | "empty";

export interface RecommendationStateLike {
  recommendations: readonly unknown[];
  stale: boolean;
  queryArmErrors: readonly string[];
}

export function recommendationViewState(result: RecommendationStateLike): RecommendationViewState {
  if (result.recommendations.length === 0) return "empty";
  return result.stale ? "stale" : "ready";
}

export function recommendationFailureSummary(result: RecommendationStateLike): string {
  if (result.stale) {
    return "Live Hub search is unavailable. RIFT is showing the last successful shortlist from its local cache.";
  }
  if (result.queryArmErrors.length > 0) {
    return "Hub search failed before RIFT could build a shortlist. Check controller network access and retry.";
  }
  return "RIFT did not find a compatible model in the current search window.";
}
