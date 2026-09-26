export type WorkloadApprovalInput = {
  network: "offline" | "approved_sources";
  licensePolicy: "apache-2.0" | "no-filter";
  actions: Record<string, boolean>;
  explorationSeconds: string;
  maxArtifacts: string;
  tuningCandidates: string;
  perArtifactGiB: string;
  totalDownloadGiB: string;
};

export function hasValidAcquisitionApproval(input: {
  network: "offline" | "approved_sources";
  allowDownload: boolean;
  allowInstall: boolean;
  perArtifactGiB: string;
  totalDownloadGiB: string;
}): boolean {
  if (input.network === "offline") return true;
  return (
    (input.allowDownload || input.allowInstall) &&
    input.perArtifactGiB.trim().length > 0 &&
    input.totalDownloadGiB.trim().length > 0
  );
}

function positiveInteger(value: string, label: string): number {
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < 1)
    throw new Error(`${label} must be a positive whole number.`);
  return parsed;
}

function bytes(value: string, label: string): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) throw new Error(`${label} must be zero or more GiB.`);
  return Math.floor(parsed * 1024 ** 3);
}

export function buildWorkloadEnvelope(input: WorkloadApprovalInput) {
  const explorationSeconds = positiveInteger(input.explorationSeconds, "Exploration time");
  const maxArtifacts = positiveInteger(input.maxArtifacts, "Maximum artifact count");
  const tuningCandidates = positiveInteger(input.tuningCandidates, "Tuning candidate limit");
  const perArtifactBytes = bytes(input.perArtifactGiB, "Per-artifact download budget");
  const totalDownloadBytes = bytes(input.totalDownloadGiB, "Total download budget");
  if (input.network === "offline" && (perArtifactBytes !== 0 || totalDownloadBytes !== 0)) {
    throw new Error("Offline mode requires both download budgets to be zero GiB.");
  }
  if (perArtifactBytes > totalDownloadBytes) {
    throw new Error("Per-artifact download budget cannot exceed the total download budget.");
  }
  if (input.network === "approved_sources" && !input.actions.download && totalDownloadBytes > 0) {
    throw new Error("A non-zero download budget requires explicit download permission.");
  }
  const actions = {
    ...input.actions,
    download: input.network === "approved_sources" && input.actions.download === true,
    install: input.network === "approved_sources" && input.actions.install === true,
    remote_execution: false,
  };
  return {
    schema_version: 1,
    actions,
    targets: ["local"],
    sources: input.network === "approved_sources" ? ["huggingface"] : [],
    licenses:
      input.network === "approved_sources" && input.licensePolicy === "apache-2.0"
        ? ["Apache-2.0"]
        : [],
    network: input.network,
    limits: {
      exploration_seconds: explorationSeconds,
      max_artifacts: maxArtifacts,
      tuning_candidates: tuningCandidates,
      per_artifact_bytes: perArtifactBytes,
      total_download_bytes: totalDownloadBytes,
    },
    allow_quantization_alternatives: false,
    exposure: "loopback",
    operations_mode: "recover",
  };
}
