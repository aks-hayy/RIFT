import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { ChevronDown, Loader2, Settings2, ShieldCheck, SlidersHorizontal, Zap } from "lucide-react";
import { AppShell } from "@/components/rift/app-shell";
import { PageHeader, Panel, KV, StatDot } from "@/components/rift/primitives";
import { Unavailable } from "@/components/rift/unavailable";
import { rift } from "@/lib/rift/client";
import { useActiveTuningRun, useServices, useTuningRuns } from "@/lib/rift/hooks";
import { tuningOutcomeTone, tuningProfileLabel } from "@/lib/rift/tuning-contract";
import type { TuningProfile, TuningRun } from "@/lib/rift/types";

type TuningPreview = {
  mode: string;
  candidates?: number;
  locks?: Record<string, unknown>;
};

export const Route = createFileRoute("/tuning")({
  head: () => ({
    meta: [
      { title: "Tuning — RIFT" },
      {
        name: "description",
        content: "Autonomously tune llama.cpp deployments for speed or GPU energy cost.",
      },
    ],
  }),
  component: TuningPage,
});

function TuningPage() {
  const services = useServices();
  const [selectedServiceName, setSelectedServiceName] = useState<string | undefined>();
  const service =
    services.data?.find((item) => item.name === selectedServiceName) ?? services.data?.[0];
  const [profile, setProfile] = useState<TuningProfile>("speed");
  const [allowRestart, setAllowRestart] = useState(false);
  const [noApply, setNoApply] = useState(false);
  const [targetTokensPerSecond, setTargetTokensPerSecond] = useState(100);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [candidateLimit, setCandidateLimit] = useState(24);
  const [budgetMinutes, setBudgetMinutes] = useState(60);
  const [warmupRuns, setWarmupRuns] = useState(1);
  const [repeats, setRepeats] = useState(3);
  const [startupTimeoutSeconds, setStartupTimeoutSeconds] = useState(180);
  const [prompt, setPrompt] = useState("Reply briefly: what is one benefit of local inference?");
  const [maxTokens, setMaxTokens] = useState(32);
  const [accuracyTolerance, setAccuracyTolerance] = useState(0.05);
  const [accuracyCaseTolerance, setAccuracyCaseTolerance] = useState(0.15);
  const [kvPrecisionSearch, setKvPrecisionSearch] = useState(true);
  const [retainAccuracyResponses, setRetainAccuracyResponses] = useState(false);
  const [ngramSpeculation, setNgramSpeculation] = useState<"default" | "on" | "off">("default");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<TuningPreview | null>(null);
  const [operationId, setOperationId] = useState<string | null>(null);
  const runs = useTuningRuns({ service: service?.name });
  const activeRun = useActiveTuningRun(runs.data);
  useEffect(() => {
    const status = activeRun.data?.status?.toUpperCase();
    if (status && !["QUEUED", "RUNNING"].includes(status)) setOperationId(null);
  }, [activeRun.data?.status]);

  const validateSettings = () => {
    if (!Number.isFinite(targetTokensPerSecond) || targetTokensPerSecond <= 0) {
      return "Target throughput must be greater than zero.";
    }
    if (!Number.isInteger(candidateLimit) || candidateLimit < 1 || candidateLimit > 24) {
      return "Candidate limit must be an integer from 1 to 24.";
    }
    if (!Number.isFinite(budgetMinutes) || budgetMinutes <= 0) {
      return "Experiment budget must be greater than zero minutes.";
    }
    if (!Number.isInteger(warmupRuns) || warmupRuns < 0 || warmupRuns > 10) {
      return "Warmup runs must be an integer from 0 to 10.";
    }
    if (!Number.isInteger(repeats) || repeats < 1 || repeats > 20) {
      return "Measurement repeats must be an integer from 1 to 20.";
    }
    if (!Number.isFinite(startupTimeoutSeconds) || startupTimeoutSeconds < 30) {
      return "Startup timeout must be at least 30 seconds.";
    }
    if (!prompt.trim()) return "Benchmark prompt cannot be empty.";
    if (!Number.isInteger(maxTokens) || maxTokens < 1 || maxTokens > 128) {
      return "Maximum tokens must be an integer from 1 to 128.";
    }
    if (!Number.isFinite(accuracyTolerance) || accuracyTolerance < 0) {
      return "Accuracy tolerance cannot be negative.";
    }
    if (!Number.isFinite(accuracyCaseTolerance) || accuracyCaseTolerance < 0) {
      return "Accuracy case tolerance cannot be negative.";
    }
    return null;
  };

  const tuningOptions = () => ({
    allowRestart,
    noApply,
    candidateLimit,
    warmupRuns,
    repeats,
    budgetSeconds: Math.round(budgetMinutes * 60),
    startupTimeoutSeconds,
    prompt: prompt.trim(),
    maxTokens,
    targetTokensPerSecond,
    accuracyTolerance,
    accuracyCaseTolerance,
    retainAccuracyResponses,
    kvPrecisionSearch,
    ngramSpeculation: ngramSpeculation === "default" ? undefined : ngramSpeculation === "on",
  });

  const start = async () => {
    if (!service) return;
    const validationError = validateSettings();
    if (validationError) {
      setError(validationError);
      setAdvancedOpen(true);
      return;
    }
    setBusy(true);
    setMessage(null);
    setError(null);
    setPreview(null);
    try {
      const result = await rift.startTuning(service.name, profile, tuningOptions());
      setOperationId(typeof result.operation_id === "string" ? result.operation_id : null);
      setMessage(
        typeof result.operation_id === "string"
          ? `Run accepted (${result.operation_id}). This page will refresh history while it executes.`
          : "Run accepted. This page will refresh history while it executes.",
      );
      void runs.refetch();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const previewScope = async () => {
    if (!service) return;
    const validationError = validateSettings();
    if (validationError) {
      setError(validationError);
      setAdvancedOpen(true);
      return;
    }
    setBusy(true);
    setMessage(null);
    setError(null);
    try {
      const result = await rift.startTuning(service.name, profile, {
        ...tuningOptions(),
        allowRestart: false,
        noApply: true,
        dryRun: true,
      });
      setPreview({
        mode: String(result.mode ?? "profiled_preview"),
        candidates: Array.isArray(result.candidates) ? result.candidates.length : undefined,
        locks:
          result.precision_locks && typeof result.precision_locks === "object"
            ? (result.precision_locks as Record<string, unknown>)
            : undefined,
      });
      setMessage("Preview ready. No service restart or benchmark was performed.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    const id = operationId ?? activeRun.data?.operationId;
    if (!id) return;
    setError(null);
    try {
      await rift.cancelTuning(id);
      setMessage(
        `Cancellation requested for ${id}. The baseline will be restored at the next safe checkpoint.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <AppShell>
      <PageHeader
        eyebrow="Optimization"
        title="Tuning"
        description="RIFT measures bounded llama.cpp candidates, explains the winner, and preserves your model and precision contract."
      />
      <div className="max-w-[1400px] mx-auto px-4 py-6 grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2 grid gap-4">
          <Panel title="Start a profiled run">
            {services.unavailable ? (
              <Unavailable endpoint="/services" resource="Service[]" />
            ) : !service ? (
              <p className="text-[13px] text-ink-secondary">Deploy a service before tuning it.</p>
            ) : (
              <div className="grid gap-5">
                {services.data && services.data.length > 1 && (
                  <label className="grid gap-1 text-[12px]">
                    <span className="rift-label">Deployment</span>
                    <select
                      value={service.name}
                      onChange={(event) => setSelectedServiceName(event.target.value)}
                      className="h-9 rounded-[4px] border border-border bg-raised px-2 text-[13px]"
                    >
                      {services.data.map((item) => (
                        <option key={item.id} value={item.name}>
                          {item.name} · {item.backendKind}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                <label className="grid gap-1 text-[12px] sm:max-w-xs">
                  <span className="rift-label">Target throughput</span>
                  <input
                    type="number"
                    min="0.01"
                    step="0.01"
                    value={targetTokensPerSecond}
                    onChange={(event) => setTargetTokensPerSecond(Number(event.target.value))}
                    className="h-9 rounded-[4px] border border-border bg-raised px-2"
                  />
                  <span className="text-[11px] text-ink-secondary">
                    Used as a goal and report metric; it does not override the accuracy gate.
                  </span>
                </label>
                <div className="grid gap-3 sm:grid-cols-2">
                  <button
                    type="button"
                    onClick={() => setProfile("speed")}
                    className={`text-left border rounded-[4px] p-4 ${profile === "speed" ? "border-primary bg-primary/5" : "border-border"}`}
                  >
                    <div className="flex items-center gap-2 text-[14px] font-medium">
                      <Zap className="size-4 text-primary" /> Speed
                    </div>
                    <p className="mt-2 text-[12px] text-ink-secondary">
                      Maximize generated tokens per second with a latency guard. Uses fixed prompts,
                      warmups, and repeated measurements.
                    </p>
                  </button>
                  <button
                    type="button"
                    onClick={() => setProfile("cost")}
                    className={`text-left border rounded-[4px] p-4 ${profile === "cost" ? "border-primary bg-primary/5" : "border-border"}`}
                  >
                    <div className="flex items-center gap-2 text-[14px] font-medium">
                      <SlidersHorizontal className="size-4 text-primary" /> Cost
                    </div>
                    <p className="mt-2 text-[12px] text-ink-secondary">
                      Minimize GPU joules per request. Requires usable GPU power telemetry on every
                      candidate.
                    </p>
                  </button>
                </div>
                <div className="rounded-[4px] border border-border bg-muted">
                  <button
                    type="button"
                    className="flex w-full items-center justify-between gap-3 px-3.5 py-3 text-left"
                    aria-expanded={advancedOpen}
                    aria-controls="tuning-advanced-controls"
                    onClick={() => setAdvancedOpen((open) => !open)}
                  >
                    <span className="flex items-center gap-2 text-[13px] font-medium text-ink">
                      <Settings2 className="size-4 text-primary" />
                      Advanced controls
                    </span>
                    <span className="flex items-center gap-2 text-[11px] text-ink-secondary">
                      {advancedOpen ? "Hide" : "Show"}
                      <ChevronDown
                        className={`size-4 transition-transform ${advancedOpen ? "rotate-180" : ""}`}
                      />
                    </span>
                  </button>
                  {!advancedOpen && (
                    <p className="border-t border-border px-3.5 py-2.5 text-[11px] text-ink-secondary">
                      {candidateLimit} candidates · {budgetMinutes} min · {repeats} measurements ·{" "}
                      {ngramSpeculation === "default"
                        ? "backend speculation default"
                        : `n-gram ${ngramSpeculation}`}
                    </p>
                  )}
                  {advancedOpen && (
                    <div
                      id="tuning-advanced-controls"
                      className="grid gap-4 border-t border-border p-3.5"
                    >
                      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                        <label className="grid gap-1 text-[12px]">
                          <span className="rift-label">Candidate limit</span>
                          <input
                            type="number"
                            min="1"
                            max="24"
                            step="1"
                            value={candidateLimit}
                            onChange={(event) => setCandidateLimit(Number(event.target.value))}
                            className="h-9 rounded-[4px] border border-border bg-raised px-2"
                          />
                          <span className="text-[11px] text-ink-secondary">
                            Maximum configurations to test.
                          </span>
                        </label>
                        <label className="grid gap-1 text-[12px]">
                          <span className="rift-label">Experiment budget (minutes)</span>
                          <input
                            type="number"
                            min="1"
                            step="1"
                            value={budgetMinutes}
                            onChange={(event) => setBudgetMinutes(Number(event.target.value))}
                            className="h-9 rounded-[4px] border border-border bg-raised px-2"
                          />
                          <span className="text-[11px] text-ink-secondary">
                            Stops before the time budget is exceeded.
                          </span>
                        </label>
                        <label className="grid gap-1 text-[12px]">
                          <span className="rift-label">Startup timeout (seconds)</span>
                          <input
                            type="number"
                            min="30"
                            step="1"
                            value={startupTimeoutSeconds}
                            onChange={(event) =>
                              setStartupTimeoutSeconds(Number(event.target.value))
                            }
                            className="h-9 rounded-[4px] border border-border bg-raised px-2"
                          />
                          <span className="text-[11px] text-ink-secondary">
                            Readiness deadline for each restart.
                          </span>
                        </label>
                      </div>
                      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                        <label className="grid gap-1 text-[12px]">
                          <span className="rift-label">Warmup runs</span>
                          <input
                            type="number"
                            min="0"
                            max="10"
                            step="1"
                            value={warmupRuns}
                            onChange={(event) => setWarmupRuns(Number(event.target.value))}
                            className="h-9 rounded-[4px] border border-border bg-raised px-2"
                          />
                        </label>
                        <label className="grid gap-1 text-[12px]">
                          <span className="rift-label">Measurement repeats</span>
                          <input
                            type="number"
                            min="1"
                            max="20"
                            step="1"
                            value={repeats}
                            onChange={(event) => setRepeats(Number(event.target.value))}
                            className="h-9 rounded-[4px] border border-border bg-raised px-2"
                          />
                        </label>
                        <label className="grid gap-1 text-[12px]">
                          <span className="rift-label">Maximum tokens</span>
                          <input
                            type="number"
                            min="1"
                            max="128"
                            step="1"
                            value={maxTokens}
                            onChange={(event) => setMaxTokens(Number(event.target.value))}
                            className="h-9 rounded-[4px] border border-border bg-raised px-2"
                          />
                        </label>
                      </div>
                      <label className="grid gap-1 text-[12px]">
                        <span className="rift-label">Benchmark prompt</span>
                        <textarea
                          rows={2}
                          value={prompt}
                          onChange={(event) => setPrompt(event.target.value)}
                          className="rounded-[4px] border border-border bg-raised px-2 py-2 text-[12px]"
                        />
                        <span className="text-[11px] text-ink-secondary">
                          The same prompt is used for each candidate so comparisons remain
                          reproducible.
                        </span>
                      </label>
                      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                        <label className="grid gap-1 text-[12px]">
                          <span className="rift-label">Accuracy tolerance</span>
                          <input
                            type="number"
                            min="0"
                            step="0.01"
                            value={accuracyTolerance}
                            onChange={(event) => setAccuracyTolerance(Number(event.target.value))}
                            className="h-9 rounded-[4px] border border-border bg-raised px-2"
                          />
                        </label>
                        <label className="grid gap-1 text-[12px]">
                          <span className="rift-label">Accuracy case tolerance</span>
                          <input
                            type="number"
                            min="0"
                            step="0.01"
                            value={accuracyCaseTolerance}
                            onChange={(event) =>
                              setAccuracyCaseTolerance(Number(event.target.value))
                            }
                            className="h-9 rounded-[4px] border border-border bg-raised px-2"
                          />
                        </label>
                        <label className="flex items-center gap-2 text-[12px] text-ink-secondary">
                          <input
                            type="checkbox"
                            checked={kvPrecisionSearch}
                            onChange={(event) => setKvPrecisionSearch(event.target.checked)}
                          />
                          <span>
                            <span className="text-ink font-medium">K/V precision search</span>
                            <br />
                            Allow safe K/V cache candidates.
                          </span>
                        </label>
                        <label className="flex items-center gap-2 text-[12px] text-ink-secondary">
                          <input
                            type="checkbox"
                            checked={retainAccuracyResponses}
                            onChange={(event) => setRetainAccuracyResponses(event.target.checked)}
                          />
                          <span>
                            <span className="text-ink font-medium">Retain accuracy responses</span>
                            <br />
                            Include response evidence in the report.
                          </span>
                        </label>
                      </div>
                      <div className="grid gap-1 text-[12px] sm:max-w-sm">
                        <label className="grid gap-1">
                          <span className="rift-label">N-gram speculation</span>
                          <select
                            value={ngramSpeculation}
                            onChange={(event) =>
                              setNgramSpeculation(event.target.value as "default" | "on" | "off")
                            }
                            className="h-9 rounded-[4px] border border-border bg-raised px-2"
                          >
                            <option value="default">Backend default</option>
                            <option value="off">Explicitly off</option>
                            <option value="on">Explicitly on</option>
                          </select>
                        </label>
                        <span className="text-[11px] text-ink-secondary">
                          Keep it off for creative tasks; enable it only when predictable text makes
                          speculation worthwhile.
                        </span>
                      </div>
                      <div className="flex flex-wrap items-center gap-3">
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void previewScope()}
                          className="inline-flex h-8 items-center gap-2 rounded-[4px] border border-border bg-raised px-3 text-[12px] font-medium text-ink disabled:opacity-50"
                        >
                          <Settings2 className="size-3.5" /> Preview scope
                        </button>
                        <span className="text-[11px] text-ink-secondary">
                          Preview validates locks and candidate scope without restarting the
                          service.
                        </span>
                      </div>
                      {preview && (
                        <div
                          className="rounded-[4px] border border-border bg-raised p-3 text-[11px]"
                          role="status"
                        >
                          <div className="rift-label mb-1">Preview ready</div>
                          <div className="grid gap-1 text-ink-secondary sm:grid-cols-2">
                            <span>
                              Mode: <span className="rift-mono text-ink">{preview.mode}</span>
                            </span>
                            <span>
                              Candidates:{" "}
                              <span className="rift-mono text-ink">
                                {preview.candidates ?? "—"}
                              </span>
                            </span>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="flex items-start gap-2 text-[12px] text-ink-secondary">
                    <input
                      type="checkbox"
                      checked={allowRestart}
                      onChange={(event) => setAllowRestart(event.target.checked)}
                      className="mt-0.5"
                    />
                    <span>
                      <span className="text-ink font-medium">Allow maintenance restarts</span>
                      <br />
                      Candidate settings are tested one at a time; monitoring recovery is paused for
                      this run.
                    </span>
                  </label>
                  <label className="flex items-start gap-2 text-[12px] text-ink-secondary">
                    <input
                      type="checkbox"
                      checked={noApply}
                      onChange={(event) => setNoApply(event.target.checked)}
                      className="mt-0.5"
                    />
                    <span>
                      <span className="text-ink font-medium">Report only</span>
                      <br />
                      Measure and explain the winner, then restore the baseline instead of applying
                      it.
                    </span>
                  </label>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    disabled={busy || !allowRestart}
                    onClick={() => void start()}
                    className="inline-flex items-center gap-2 h-9 px-3.5 rounded-[4px] bg-primary text-primary-foreground text-[13px] font-medium disabled:opacity-50"
                  >
                    {busy ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <ShieldCheck className="size-4" />
                    )}{" "}
                    Start {tuningProfileLabel(profile)} tuning
                  </button>
                  <Link
                    to={service ? "/deployments/$id" : "/deployments"}
                    params={service ? { id: service.id } : undefined}
                    className="text-[12px] text-primary hover:underline"
                  >
                    View deployment state
                  </Link>
                </div>
                {message && (
                  <p className="rift-mono text-[11px] text-secondary" role="status">
                    {message}
                  </p>
                )}
                {error && (
                  <p className="rift-mono text-[11px] text-error" role="alert">
                    {error}
                  </p>
                )}
                {(activeRun.data || operationId) && (
                  <div className="rounded-[4px] border border-border bg-muted p-3" role="status">
                    <div className="flex flex-wrap items-center gap-2 text-[12px]">
                      <span className="font-medium text-ink">Live tuning run</span>
                      <span className="rift-mono text-[11px] text-ink-secondary">
                        {activeRun.data?.runId ?? operationId}
                      </span>
                      {activeRun.data && (
                        <span className="rift-mono text-[11px] text-ink-secondary">
                          {activeRun.data.status}
                        </span>
                      )}
                      {(operationId || activeRun.data?.operationId) && (
                        <button
                          type="button"
                          onClick={() => void cancel()}
                          className="ml-auto text-[11px] text-error hover:underline"
                        >
                          Cancel safely
                        </button>
                      )}
                    </div>
                    {activeRun.data?.events?.length ? (
                      <div className="mt-2 grid gap-1">
                        <div className="flex items-center justify-between rift-mono text-[11px] text-ink-secondary">
                          <span>
                            {activeRun.data.events[activeRun.data.events.length - 1].message}
                          </span>
                          <span>
                            {activeRun.data.events[activeRun.data.events.length - 1].percent == null
                              ? ""
                              : `${activeRun.data.events[activeRun.data.events.length - 1].percent}%`}
                          </span>
                        </div>
                        <div className="h-1.5 overflow-hidden rounded-full bg-raised">
                          <div
                            className="h-full bg-primary transition-all"
                            style={{
                              width: `${Math.max(0, Math.min(100, activeRun.data.events[activeRun.data.events.length - 1].percent ?? 0))}%`,
                            }}
                          />
                        </div>
                      </div>
                    ) : (
                      <p className="mt-2 rift-mono text-[11px] text-ink-secondary">
                        Waiting for the controller to create the durable run journal…
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}
          </Panel>
          <RunHistory runs={runs.data ?? []} loading={runs.isLoading} />
        </div>
        <ContractPanel run={runs.data?.[0]} />
      </div>
    </AppShell>
  );
}

function RunHistory({ runs, loading }: { runs: TuningRun[]; loading: boolean }) {
  return (
    <Panel
      title="Run history"
      aside={<span className="rift-mono text-[11px] text-ink-secondary">persistent</span>}
    >
      {loading && !runs.length ? (
        <p className="text-[13px] text-ink-secondary">Loading tuning history…</p>
      ) : !runs.length ? (
        <p className="text-[13px] text-ink-secondary">No profiled runs yet.</p>
      ) : (
        <div className="divide-y divide-border">
          {runs.map((run) => {
            const tone = tuningOutcomeTone(run.outcome ?? run.status);
            return (
              <div
                key={run.runId}
                className="py-3 first:pt-0 last:pb-0 flex flex-wrap items-center gap-3"
              >
                <StatDot
                  tone={tone === "success" ? "ok" : tone === "error" ? "error" : "attention"}
                />
                <div className="min-w-0 flex-1">
                  <div className="text-[13px] text-ink font-medium">
                    {tuningProfileLabel(run.profile)} · {run.service}
                  </div>
                  <div className="rift-mono text-[10px] text-ink-secondary">
                    {run.runId} · {run.outcome ?? run.status}
                  </div>
                </div>
                <div className="rift-mono text-[11px] text-ink-secondary">
                  {run.applied ? "applied" : "baseline kept"}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Panel>
  );
}

function ContractPanel({ run }: { run?: TuningRun }) {
  const locks = run?.precisionLocks ?? {};
  const winnerConfig = (run?.winner?.config ?? run?.winner ?? {}) as Record<string, unknown>;
  return (
    <Panel title="Precision contract">
      {run && (
        <div className="mb-5 border-b border-border pb-4">
          <div className="rift-label mb-2">Latest result</div>
          <div className="grid grid-cols-2 gap-4">
            <KV label="Profile" value={tuningProfileLabel(run.profile)} />
            <KV label="Outcome" value={run.outcome ?? run.status} />
            <KV label="Deployment" value={run.applied ? "winner applied" : "baseline kept"} />
            <KV label="Candidates" value={run.candidates?.length ?? "—"} />
          </div>
          {run.decision && <p className="mt-3 text-[12px] text-ink-secondary">{run.decision}</p>}
          {run.winner && (
            <div className="mt-3">
              <div className="rift-label mb-1">Winning configuration</div>
              <code className="block max-h-32 overflow-auto whitespace-pre-wrap break-all rounded-[3px] bg-muted p-2 rift-mono text-[10px] text-ink">
                {JSON.stringify(run.winner.config ?? run.winner, null, 2)}
              </code>
            </div>
          )}
          <div
            className="mt-4 rounded-[4px] border border-border bg-muted p-3"
            aria-label="tuning result"
          >
            <div className="rift-label mb-2">Target / Accuracy / KV</div>
            <div className="grid grid-cols-2 gap-3 text-[12px]">
              <KV
                label="Target"
                value={
                  run.target
                    ? `${run.target.value ?? "—"} tok/s · ${run.target.reached ? "reached" : "not reached"}`
                    : "—"
                }
              />
              <KV
                label="Accuracy"
                value={
                  run.accuracy
                    ? `${run.accuracy.passed ? "PASS" : "FAIL"} · ${run.accuracy.aggregateScore ?? "—"}`
                    : "—"
                }
              />
              <KV
                label="K/V search"
                value={
                  run.kvPrecisionSearch == null
                    ? "—"
                    : run.kvPrecisionSearch
                      ? "enabled"
                      : "disabled"
                }
              />
              <KV label="Selected K cache" value={String(winnerConfig.cache_type_k ?? "—")} />
              <KV label="Selected V cache" value={String(winnerConfig.cache_type_v ?? "—")} />
              <KV
                label="Apply / rollback"
                value={run.applyState?.state ?? (run.applied ? "applied" : "baseline kept")}
              />
            </div>
            {!!run.rejected?.length && (
              <div className="mt-3 text-[11px] text-ink-secondary">
                Rejected candidates:{" "}
                {run.rejected
                  .map((item) => item.rejectionReason ?? item.reason ?? "unspecified")
                  .join("; ")}
              </div>
            )}
          </div>
        </div>
      )}
      <p className="text-[12px] text-ink-secondary">
        Tuning never changes the model artifact, weight quantization, context, or concurrency. K/V
        cache precision is searched only when the explicit K/V precision search control is enabled;
        candidates remain accuracy-screened and any quality trade-off is reported.
      </p>
      <div className="mt-4 grid grid-cols-2 gap-4">
        <KV label="Model" value={String(locks.model_path ?? "locked at run start")} />
        <KV label="Quantization" value={String(locks.weight_quantization ?? "locked")} />
        <KV label="K cache" value={String(locks.cache_type_k ?? "locked")} />
        <KV label="V cache" value={String(locks.cache_type_v ?? "locked")} />
        <KV label="Context" value={String(locks.context_length ?? "locked")} />
        <KV label="Concurrency" value={String(locks.concurrency ?? "locked")} />
      </div>
      {run?.opportunities?.length ? (
        <div className="mt-5 border-t border-border pt-4">
          <div className="rift-label mb-2">Further improvement · recommendation only</div>
          {run.opportunities.map((opportunity) => (
            <div key={opportunity.id} className="mb-3 last:mb-0">
              <div className="text-[12px] text-ink font-medium">{opportunity.title}</div>
              <div className="text-[11px] text-ink-secondary mt-0.5">{opportunity.warning}</div>
            </div>
          ))}
        </div>
      ) : null}
    </Panel>
  );
}
