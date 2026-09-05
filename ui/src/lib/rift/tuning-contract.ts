import type { TuningOutcome, TuningProfile } from "./types";

export function tuningProfileLabel(profile: TuningProfile | string): string {
  return String(profile).toLowerCase() === "cost" ? "Cost" : "Speed";
}

export function tuningOutcomeTone(
  outcome: TuningOutcome | string,
): "success" | "attention" | "error" {
  const value = String(outcome).toLowerCase();
  if (value === "improved") return "success";
  if (value === "failed" || value === "unavailable") return "error";
  return "attention";
}
