export interface OperationDisplayInput {
  status: string;
  stage?: string | null;
  percent?: number | null;
  message?: string | null;
  error?: string | null;
}

export interface OperationDisplay {
  stage: string;
  percent: number | null;
  message: string;
}

const terminalStages: Record<string, string> = {
  SUCCEEDED: "succeeded",
  FAILED: "failed",
  CANCELLED: "cancelled",
  INTERRUPTED: "interrupted",
};

export function deriveOperationDisplay(input: OperationDisplayInput): OperationDisplay {
  const status = input.status.trim().toUpperCase();
  const explicitStage = input.stage?.trim();
  const stage = explicitStage || terminalStages[status] || "running";
  const message =
    input.message?.trim() ||
    input.error?.trim() ||
    (status === "SUCCEEDED"
      ? "Operation completed successfully."
      : status === "FAILED" || status === "INTERRUPTED" || status === "CANCELLED"
        ? "Operation did not complete successfully."
        : "Operation in progress.");
  const percent =
    input.percent === null
      ? null
      : typeof input.percent === "number" && Number.isFinite(input.percent)
        ? input.percent
        : status === "SUCCEEDED"
          ? 100
          : null;

  return { stage, percent, message };
}
