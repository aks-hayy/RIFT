import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/rift/app-shell";
import { PageHeader, Panel } from "@/components/rift/primitives";
import { rift } from "@/lib/rift/client";
import {
  buildWorkloadEnvelope,
  hasValidAcquisitionApproval,
} from "@/lib/rift/workload-approval";
import { summarizeWorkloadRun } from "@/lib/rift/workload-result";

export const Route = createFileRoute("/workloads")({
  head: () => ({ meta: [{ title: "Workload Deploy — RIFT" }] }),
  component: WorkloadsPage,
});

function WorkloadsPage() {
  const [input, setInput] = useState("");
  const [inputMode, setInputMode] = useState<"natural" | "json">("natural");
  const [outputSchema, setOutputSchema] = useState<Record<string, unknown> | null>(null);
  const [outputSchemaName, setOutputSchemaName] = useState("");
  const [outputSchemaError, setOutputSchemaError] = useState<string | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [network, setNetwork] = useState<"offline" | "approved_sources">("offline");
  const [licensePolicy, setLicensePolicy] = useState<"apache-2.0" | "no-filter">("apache-2.0");
  const [allowLaunch, setAllowLaunch] = useState(false);
  const [allowRestart, setAllowRestart] = useState(false);
  const [allowPromote, setAllowPromote] = useState(false);
  const [allowCleanup, setAllowCleanup] = useState(false);
  const [allowDownload, setAllowDownload] = useState(false);
  const [allowInstall, setAllowInstall] = useState(false);
  const [modelsDir, setModelsDir] = useState("");
  const [explorationHours, setExplorationHours] = useState("");
  const [maxArtifacts, setMaxArtifacts] = useState("");
  const [tuningCandidates, setTuningCandidates] = useState("");
  const [perArtifactGiB, setPerArtifactGiB] = useState("");
  const [totalDownloadGiB, setTotalDownloadGiB] = useState("");
  const [qualityConfirmed, setQualityConfirmed] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const [runOperationId, setRunOperationId] = useState<string | null>(null);
  const [runState, setRunState] = useState<Record<string, unknown> | null>(null);
  const [runBusy, setRunBusy] = useState(false);
  const [workloadRuns, setWorkloadRuns] = useState<Array<Record<string, unknown>>>([]);
  const [runsLoading, setRunsLoading] = useState(true);
  const [runsError, setRunsError] = useState<string | null>(null);
  function parseInput(): string | Record<string, unknown> {
    if (inputMode === "natural") return input;
    const parsed: unknown = JSON.parse(input);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
      throw new Error("JSON workload must be an object");
    return parsed as Record<string, unknown>;
  }
  async function compile() {
    setBusy(true);
    setError(null);
    setQualityConfirmed(false);
    setRunId(null);
    setRunOperationId(null);
    setRunState(null);
    try {
      setResult(
        await rift.compileWorkload(parseInput(), true, undefined, outputSchema ?? undefined),
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }
  async function confirmDefaultQuality() {
    setBusy(true);
    setError(null);
    try {
      const parsed = parseInput();
      const workload = typeof parsed === "string" ? { workload_text: parsed } : parsed;
      const compiled = await rift.compileWorkload(
        {
          ...workload,
          quality: {
            suite_id: "rift-text-core",
            suite_version: "v1",
            minimum_score: 0.9,
            required_cases: ["response_nonempty"],
          },
        },
        true,
        undefined,
        outputSchema ?? undefined,
      );
      setResult(compiled);
      setQualityConfirmed(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }
  async function approveAndRun() {
    if (!result?.draft_id || questions.length > 0) return;
    setBusy(true);
    setError(null);
    try {
      const envelope = buildWorkloadEnvelope({
        network,
        licensePolicy,
        actions: {
          cleanup: allowCleanup,
          download: allowDownload,
          install: allowInstall,
          promote: allowPromote,
          restart: allowRestart,
          temporary_launch: allowLaunch,
        },
        explorationSeconds: String(Number(explorationHours) * 3600),
        maxArtifacts,
        tuningCandidates,
        perArtifactGiB: network === "offline" ? "0" : perArtifactGiB,
        totalDownloadGiB: network === "offline" ? "0" : totalDownloadGiB,
      });
      const policyId = `easy-${String(result.draft_id).slice(0, 12)}`;
      const policy = await rift.saveWorkloadPolicy(envelope, policyId, 0);
      const approval = await rift.approveWorkload(String(result.draft_id), {
        revision: result.revision,
        contract_hash: result.contract_hash,
        policy_id: policy.policy_id,
        policy_revision: policy.revision,
        envelope,
        envelope_hash: policy.policy_hash,
      });
      const run = await rift.startWorkloadRun(String(approval.approval_id), {
        modelsDir: modelsDir || undefined,
      });
      setResult({ ...result, approval, run });
      const startedRunId = typeof run.run_id === "string" ? run.run_id : null;
      setRunId(startedRunId);
      setRunOperationId(typeof run.operation_id === "string" ? run.operation_id : null);
      setRunState(startedRunId ? run : null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }
  async function cancelRun() {
    const operationId =
      runOperationId ||
      (typeof runState?.result === "object" && runState.result !== null
        ? String((runState.result as Record<string, unknown>).operation_id ?? "")
        : "");
    if (!operationId) return;
    setError(null);
    try {
      await rift.cancelOperation(operationId, "Cancelled easy-path workload deployment");
      setRunState((current) => (current ? { ...current, status: "CANCEL_REQUESTED" } : current));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }
  async function loadWorkloadRuns() {
    setRunsLoading(true);
    try {
      setRunsError(null);
      setWorkloadRuns(await rift.listWorkloadRuns());
    } catch (cause) {
      setRunsError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setRunsLoading(false);
    }
  }
  async function openSavedRun(id: string) {
    setRunBusy(true);
    setError(null);
    try {
      const savedRun = await rift.getWorkloadRun(id);
      setRunId(id);
      setRunState(savedRun);
      setRunOperationId(
        typeof savedRun.result === "object" && savedRun.result !== null
          ? String((savedRun.result as Record<string, unknown>).operation_id ?? "") || null
          : null,
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setRunBusy(false);
    }
  }
  useEffect(() => {
    void loadWorkloadRuns();
  }, []);
  const runStatus = String(runState?.status ?? "").toUpperCase();
  useEffect(() => {
    if (
      !runId ||
      ["VERIFIED", "INFEASIBLE", "EXHAUSTED", "BLOCKED", "FAILED", "CANCELLED"].includes(
        runStatus,
      )
    )
      return;
    let cancelled = false;
    const poll = async () => {
      setRunBusy(true);
      try {
        const next = await rift.getWorkloadRun(runId);
        if (!cancelled) setRunState(next);
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : String(cause));
      } finally {
        if (!cancelled) setRunBusy(false);
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 3000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [runId, runStatus]);
  const contract = (result?.contract ?? {}) as Record<string, unknown>;
  const questions = Array.isArray(result?.questions) ? result.questions : [];
  const unsupported = Array.isArray(result?.unsupported_requirements)
    ? result.unsupported_requirements
    : [];
  const qualityQuestion = questions.some((question) =>
    String(question).toLowerCase().includes("quality suite"),
  );
  const runEvents = Array.isArray(runState?.events)
    ? (runState.events as Array<Record<string, unknown>>)
    : [];
  const outcome = runState
    ? summarizeWorkloadRun(runState.result, runStatus || "UNKNOWN")
    : null;
  useEffect(() => {
    if (["VERIFIED", "INFEASIBLE", "EXHAUSTED", "BLOCKED", "FAILED", "CANCELLED"].includes(runStatus))
      void loadWorkloadRuns();
  }, [runStatus]);
  return (
    <AppShell>
      <PageHeader
        eyebrow="Workload deploy"
        title="Describe a workload"
        description="RIFT interprets the request, shows its assumptions, and asks for approval before any deployment action."
      />
      <div className="max-w-[1100px] mx-auto px-4 py-6 grid gap-4 lg:grid-cols-2">
        <Panel title="Workload request">
          <div className="mb-2 flex items-center gap-2 text-[12px]">
            <span className="rift-label">Input format</span>
            <select
              value={inputMode}
              onChange={(event) => {
                setInputMode(event.target.value as "natural" | "json");
                setResult(null);
                setQualityConfirmed(false);
              }}
              className="rounded border border-border bg-canvas px-2 py-1"
            >
              <option value="natural">Natural language</option>
              <option value="json">Structured JSON</option>
            </select>
          </div>
          <textarea
            value={input}
            onChange={(event) => {
              setInput(event.target.value);
              setQualityConfirmed(false);
            }}
            placeholder={
              inputMode === "json"
                ? "Paste a workload JSON contract"
                : "Describe the service you need, its performance, quality, context, and policy requirements…"
            }
            rows={10}
            className="w-full rounded border border-border bg-canvas p-3 text-[13px] leading-6 text-ink"
            aria-label={
              inputMode === "json" ? "Structured JSON workload" : "Natural-language workload"
            }
          />
          <div className="mt-3 rounded border border-border bg-muted/30 p-3 text-[12px]">
            <label className="block font-medium">
              Output JSON Schema{" "}
              <span className="font-normal text-ink-secondary">
                (required when strict JSON is requested)
              </span>
              <input
                type="file"
                accept="application/schema+json,application/json,.json"
                className="mt-2 block w-full text-[12px]"
                onChange={async (event) => {
                  const file = event.target.files?.[0];
                  setOutputSchemaError(null);
                  setOutputSchema(null);
                  setOutputSchemaName("");
                  if (!file) return;
                  try {
                    const parsed: unknown = JSON.parse(await file.text());
                    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
                      throw new Error("Schema root must be a JSON object");
                    setOutputSchema(parsed as Record<string, unknown>);
                    setOutputSchemaName(file.name);
                  } catch (cause) {
                    setOutputSchemaError(
                      cause instanceof Error ? cause.message : "Schema file could not be read",
                    );
                  }
                }}
              />
            </label>
            {outputSchemaName && (
              <p className="mt-1 text-secondary">
                Attached: {outputSchemaName}. RIFT will validate and hash this schema during
                compilation.
              </p>
            )}
            {outputSchemaError && <p className="mt-1 text-attention">{outputSchemaError}</p>}
          </div>
          <button
            type="button"
            onClick={compile}
            disabled={busy || !input.trim() || Boolean(outputSchemaError)}
            className="mt-3 h-9 px-4 rounded bg-primary text-primary-foreground text-[13px] disabled:opacity-50"
          >
            {busy ? "Compiling…" : "Compile for review"}
          </button>
          {error && <p className="mt-3 text-[12px] text-attention">{error}</p>}
          <p className="mt-4 text-[11px] text-ink-secondary">
            Compilation is local. Deployment starts only after you review and explicitly approve the
            permission envelope.
          </p>
        </Panel>
        <Panel title="Compiled contract">
          {!result ? (
            <p className="text-[13px] text-ink-secondary">
              Your interpreted requirements will appear here.
            </p>
          ) : (
            <>
              <pre className="max-h-[360px] overflow-auto rounded bg-canvas p-3 text-[11px] text-ink">
                {JSON.stringify(contract, null, 2)}
              </pre>
              {Boolean(contract.output_schema) && (
                <p className="mt-2 text-[12px] text-secondary">
                  Output schema attached and content-hashed:{" "}
                  {String(
                    (contract.output_schema as Record<string, unknown>).sha256 ?? "unavailable",
                  )}
                </p>
              )}
              {questions.length > 0 && (
                <div className="mt-3 rounded border border-attention/40 bg-attention/5 p-3 text-[12px]">
                  <strong>Review questions</strong>
                  <ul className="mt-1 list-disc pl-4">
                    {questions.map((question) => (
                      <li key={String(question)}>{String(question)}</li>
                    ))}
                  </ul>
                </div>
              )}
              {qualityQuestion && (
                <div className="mt-3 rounded border border-border bg-muted/40 p-3 text-[12px]">
                  <strong>Quality acceptance</strong>
                  <p className="mt-1 text-ink-secondary">
                    RIFT needs a versioned suite before it can make a defensible pass/fail claim.
                  </p>
                  <button
                    type="button"
                    onClick={confirmDefaultQuality}
                    disabled={busy}
                    className="mt-2 h-8 rounded border border-border bg-raised px-3 text-[12px] disabled:opacity-50"
                  >
                    {busy ? "Confirming…" : "Use rift-text-core/v1 (0.90)"}
                  </button>
                </div>
              )}
              {unsupported.length > 0 && (
                <div className="mt-3 rounded border border-border p-3 text-[12px]">
                  <strong>Captured but not executable in v1</strong>
                  <ul className="mt-1 list-disc pl-4">
                    {unsupported.map((item, index) => (
                      <li key={index}>{String((item as Record<string, unknown>).value)}</li>
                    ))}
                  </ul>
                </div>
              )}
              <p className="mt-3 rift-mono text-[10px] text-ink-secondary">
                contract hash: {String(result.contract_hash ?? "unavailable")}
              </p>
              <div className="mt-4 border-t border-border pt-4 space-y-3 text-[12px]">
                <div className="font-medium">Execution approval</div>
                <label className="block">
                  Network policy
                  <select
                    value={network}
                    onChange={(event) =>
                      setNetwork(event.target.value as "offline" | "approved_sources")
                    }
                    className="ml-2 rounded border border-border bg-canvas px-2 py-1"
                  >
                    <option value="offline">Offline (no downloads)</option>
                    <option value="approved_sources">Approved sources</option>
                  </select>
                </label>
                {network === "approved_sources" && (
                  <label className="block">
                    License filter
                    <select
                      value={licensePolicy}
                      onChange={(event) =>
                        setLicensePolicy(event.target.value as "apache-2.0" | "no-filter")
                      }
                      className="ml-2 rounded border border-border bg-canvas px-2 py-1"
                    >
                      <option value="apache-2.0">Apache-2.0 only</option>
                      <option value="no-filter">No filter; review each model</option>
                    </select>
                  </label>
                )}
                <fieldset className="grid gap-2 rounded-lg border border-border/70 bg-white/35 p-3 sm:grid-cols-2">
                  <legend className="px-1 text-[11px] font-medium">
                    Approved search limits (required)
                  </legend>
                  <label className="grid gap-1">
                    Exploration time (hours)
                    <input
                      required
                      type="number"
                      min="0.1"
                      step="0.1"
                      value={explorationHours}
                      onChange={(event) => setExplorationHours(event.target.value)}
                      className="rounded border border-border bg-white/70 px-2 py-1.5"
                    />
                  </label>
                  <label className="grid gap-1">
                    Maximum model artifacts
                    <input
                      required
                      type="number"
                      min="1"
                      step="1"
                      value={maxArtifacts}
                      onChange={(event) => setMaxArtifacts(event.target.value)}
                      className="rounded border border-border bg-white/70 px-2 py-1.5"
                    />
                  </label>
                  <label className="grid gap-1">
                    Tuning configurations per candidate
                    <input
                      required
                      type="number"
                      min="1"
                      step="1"
                      value={tuningCandidates}
                      onChange={(event) => setTuningCandidates(event.target.value)}
                      className="rounded border border-border bg-white/70 px-2 py-1.5"
                    />
                  </label>
                  <label className="grid gap-1">
                    Per-artifact download (GiB)
                    <input
                      required
                      type="number"
                      min="0"
                      step="0.1"
                      value={network === "offline" ? "0" : perArtifactGiB}
                      disabled={network === "offline"}
                      onChange={(event) => setPerArtifactGiB(event.target.value)}
                      className="rounded border border-border bg-white/70 px-2 py-1.5 disabled:opacity-60"
                    />
                  </label>
                  <label className="grid gap-1">
                    Total download (GiB)
                    <input
                      required
                      type="number"
                      min="0"
                      step="0.1"
                      value={network === "offline" ? "0" : totalDownloadGiB}
                      disabled={network === "offline"}
                      onChange={(event) => setTotalDownloadGiB(event.target.value)}
                      className="rounded border border-border bg-white/70 px-2 py-1.5 disabled:opacity-60"
                    />
                  </label>
                </fieldset>
                <label className="block">
                  Local models directory (searched first)
                  <input
                    value={modelsDir}
                    onChange={(event) => setModelsDir(event.target.value)}
                    placeholder="C:\\models"
                    className="ml-2 rounded border border-border bg-canvas px-2 py-1"
                  />
                  <span className="ml-2 text-[11px] text-ink-secondary">
                    Optional with approved sources; RIFT prefers a compatible local artifact before considering downloads.
                  </span>
                </label>
                <div className="flex flex-wrap gap-3">
                  <label>
                    <input
                      type="checkbox"
                      checked={allowLaunch}
                      onChange={(event) => setAllowLaunch(event.target.checked)}
                    />{" "}
                    temporary launch
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={allowRestart}
                      onChange={(event) => setAllowRestart(event.target.checked)}
                    />{" "}
                    restart for tuning
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={allowPromote}
                      onChange={(event) => setAllowPromote(event.target.checked)}
                    />{" "}
                    promote winner
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={allowCleanup}
                      onChange={(event) => setAllowCleanup(event.target.checked)}
                    />{" "}
                    cleanup run-owned trials
                  </label>
                  {network === "approved_sources" && (
                    <>
                      <label>
                        <input
                          type="checkbox"
                          checked={allowDownload}
                          onChange={(event) => setAllowDownload(event.target.checked)}
                        />{" "}
                        download artifacts
                      </label>
                      <label>
                        <input
                          type="checkbox"
                          checked={allowInstall}
                          onChange={(event) => setAllowInstall(event.target.checked)}
                        />{" "}
                        install backend
                      </label>
                    </>
                  )}
                </div>
                <button
                  type="button"
                  onClick={approveAndRun}
                  disabled={
                    busy ||
                    questions.length > 0 ||
                    !allowLaunch ||
                    !explorationHours ||
                    !maxArtifacts ||
                    !tuningCandidates ||
                    (network === "offline" && !modelsDir.trim()) ||
                    !hasValidAcquisitionApproval({
                      network,
                      allowDownload,
                      allowInstall,
                      perArtifactGiB,
                      totalDownloadGiB,
                    })
                  }
                  className="h-9 px-4 rounded bg-primary text-primary-foreground disabled:opacity-50"
                >
                  {busy ? "Approving…" : "Approve & start deployment"}
                </button>
                {questions.length > 0 && (
                  <p className="text-attention">Resolve the review questions before approval.</p>
                )}
                {Boolean(result.approval) && (
                  <p className="text-secondary">
                    Approval recorded:{" "}
                    {String((result.approval as Record<string, unknown>).approval_id)}. Run started:{" "}
                    {String(
                      (result.run as Record<string, unknown> | undefined)?.operation_id ??
                        "pending",
                    )}
                  </p>
                )}
                {qualityConfirmed && (
                  <p className="text-ink-secondary">
                    Quality suite confirmed: rift-text-core/v1, minimum score 0.90.
                  </p>
                )}
              </div>
            </>
          )}
        </Panel>
        {runId && (
          <Panel title="Autonomous run">
            <div className="flex items-center justify-between text-[12px]">
              <span className="font-medium">{runStatus || "QUEUED"}</span>
              <span className="text-ink-secondary">{runBusy ? "Refreshing…" : "Live journal"}</span>
            </div>
            <ol className="mt-3 space-y-2 text-[12px]">
              {runEvents.map((event) => (
                <li key={String(event.sequence)} className="flex gap-2">
                  <span className="rift-mono text-ink-secondary">{String(event.stage)}</span>
                  <span>{String(event.message)}</span>
                </li>
              ))}
            </ol>
            {runStatus && ["QUEUED", "RUNNING", "CANCEL_REQUESTED"].includes(runStatus) && (
              <button
                type="button"
                onClick={cancelRun}
                className="mt-3 h-8 rounded border border-border px-3 text-[12px]"
              >
                Cancel and recover
              </button>
            )}
            {runState && Object.prototype.hasOwnProperty.call(runState, "result") && (
              <div className="mt-4 space-y-3">
                {outcome?.status === "VERIFIED" ? (
                  <div className="rounded-xl border border-success/30 bg-success/5 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-[11px] uppercase tracking-[0.14em] text-ink-secondary">
                          Workload verified
                        </p>
                        <h3 className="mt-1 text-lg font-semibold">
                          {outcome.serviceName ?? "Service"} passed acceptance
                        </h3>
                        <p className="mt-1 break-all text-[12px] text-ink-secondary">
                          {outcome.model?.replace(/^.*[\\/]/, "") ?? "Model identity unavailable"}
                          {outcome.modelSource === "local" ? " · local artifact" : ""}
                        </p>
                      </div>
                      <span className="rounded-full border border-success/40 px-3 py-1 text-[11px] font-medium text-success">
                        {outcome.backend ?? "Backend verified"}
                      </span>
                    </div>
                    <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                      <div className="rounded-lg bg-surface/70 p-3">
                        <p className="text-[11px] text-ink-secondary">Median decode</p>
                        <p className="mt-1 text-base font-semibold">
                          {outcome.decodeTokensPerSecond === null
                            ? "Not measured"
                            : `${outcome.decodeTokensPerSecond.toFixed(1)} tok/s`}
                        </p>
                        <p className="text-[10px] text-ink-secondary">
                          {outcome.benchmarkSamples ?? 0} samples · {outcome.benchmarkCases ?? 0} cases
                        </p>
                      </div>
                      <div className="rounded-lg bg-surface/70 p-3">
                        <p className="text-[11px] text-ink-secondary">Context / concurrency</p>
                        <p className="mt-1 text-base font-semibold">
                          {outcome.contextTokens?.toLocaleString() ?? "—"} / {outcome.concurrency ?? "—"}
                        </p>
                        <p className="text-[10px] text-ink-secondary">tokens / requests</p>
                      </div>
                      <div className="rounded-lg bg-surface/70 p-3">
                        <p className="text-[11px] text-ink-secondary">Required checks</p>
                        <p className="mt-1 text-base font-semibold">
                          {outcome.evaluationPassed ? "Passed" : "Not passed"}
                        </p>
                        <p className="text-[10px] text-ink-secondary">
                          {outcome.evaluationPasses ?? 0} passed · {outcome.evaluationFailures ?? 0} failed
                        </p>
                      </div>
                      <div className="rounded-lg bg-surface/70 p-3">
                        <p className="text-[11px] text-ink-secondary">Artifact transfer</p>
                        <p className="mt-1 text-base font-semibold">
                          {outcome.modelSource === "local" ? "No model download" : "See evidence"}
                        </p>
                        <p className="text-[10px] text-ink-secondary">existing local weights reused</p>
                      </div>
                    </div>
                    <p className="mt-3 text-[11px] text-ink-secondary">
                      Acceptance is limited to the approved suite and recorded measurements; it is not a general accuracy guarantee.
                    </p>
                    {outcome.serviceName && (
                      <a
                        className="mt-3 inline-flex h-8 items-center rounded border border-border px-3 text-[12px] font-medium hover:bg-canvas"
                        href={`/deployments/${encodeURIComponent(outcome.serviceName)}`}
                      >
                        Open service
                      </a>
                    )}
                  </div>
                ) : (
                  <div className="rounded-lg border border-border bg-canvas p-3 text-[12px]">
                    <strong>Run result</strong>
                    {outcome?.backend && <span> · {outcome.backend}</span>}
                    {outcome?.model && <p className="mt-1 break-all">{outcome.model}</p>}
                  </div>
                )}
                <details className="rounded-lg border border-border bg-canvas p-3">
                  <summary className="cursor-pointer text-[12px] font-medium">
                    Raw evidence JSON
                  </summary>
                  <pre className="mt-3 max-h-[360px] overflow-auto whitespace-pre-wrap break-words text-[10px] text-ink-secondary">
                    {JSON.stringify(runState.result, null, 2)}
                  </pre>
                </details>
              </div>
            )}
          </Panel>
        )}
        <Panel title="Recent workload runs">
          <div className="flex items-center justify-between gap-3">
            <p className="text-[12px] text-ink-secondary">
              Reopen a persisted run to inspect its status, measurements, and evidence.
            </p>
            <button
              type="button"
              onClick={() => void loadWorkloadRuns()}
              className="h-8 shrink-0 rounded border border-border px-3 text-[12px]"
            >
              Refresh
            </button>
          </div>
          {runsLoading ? (
            <p className="mt-3 text-[12px] text-ink-secondary">Loading saved workload runs…</p>
          ) : runsError ? (
            <p className="mt-3 text-[12px] text-attention">Could not load runs: {runsError}</p>
          ) : workloadRuns.length === 0 ? (
            <p className="mt-3 text-[12px] text-ink-secondary">No persisted workload runs yet.</p>
          ) : (
            <ul className="mt-3 divide-y divide-border">
              {workloadRuns.map((savedRun) => {
                const id = String(savedRun.run_id ?? "");
                const status = String(savedRun.status ?? "UNKNOWN").toUpperCase();
                return (
                  <li key={id}>
                    <button
                      type="button"
                      onClick={() => void openSavedRun(id)}
                      className="flex w-full items-center justify-between gap-3 py-3 text-left hover:bg-canvas"
                    >
                      <span className="min-w-0">
                        <span className="block font-medium">{id || "Unknown run"}</span>
                        <span className="block text-[11px] text-ink-secondary">
                          Approval {String(savedRun.approval_id ?? "—")}
                        </span>
                      </span>
                      <span className="rift-mono shrink-0 text-[11px]">{status}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </Panel>
      </div>
    </AppShell>
  );
}
