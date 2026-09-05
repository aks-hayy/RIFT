import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { z } from "zod";
import { AppShell } from "@/components/rift/app-shell";
import { PageHeader, Panel, KV, StatDot, SourceBadge } from "@/components/rift/primitives";
import { Unavailable } from "@/components/rift/unavailable";
import {
  useService,
  useRevisions,
  useBenchmarks,
  useEvaluations,
  useLogs,
  useReports,
  useTelemetryLatest,
  useResourceReports,
  useServiceTelemetryAccounting,
} from "@/lib/rift/hooks";
import { rift } from "@/lib/rift/client";
import { bytes, relativeTime } from "@/lib/rift/format";
import { cn } from "@/lib/utils";
import {
  CheckCircle2,
  Copy,
  Gauge,
  Loader2,
  RotateCcw,
  Save,
  Send,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
  XCircle,
} from "lucide-react";
import { useEffect, useState } from "react";
import type { Service } from "@/lib/rift/types";

const searchSchema = z.object({
  tab: z
    .enum(["overview", "playground", "performance", "tuning", "logs", "configuration", "revisions"])
    .catch("overview"),
});

export const Route = createFileRoute("/deployments/$id")({
  validateSearch: searchSchema,
  head: ({ params }) => ({
    meta: [
      { title: `${params.id} — Deployment` },
      { name: "description", content: `Deployment detail for ${params.id}.` },
    ],
  }),
  component: DeploymentDetail,
});

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "playground", label: "Playground" },
  { id: "performance", label: "Performance" },
  { id: "tuning", label: "Tuning" },
  { id: "logs", label: "Logs" },
  { id: "configuration", label: "Configuration" },
  { id: "revisions", label: "Revisions" },
] as const;

function DeploymentDetail() {
  const { id } = Route.useParams();
  const { tab } = Route.useSearch();
  const navigate = useNavigate({ from: "/deployments/$id" });
  const { data: service, unavailable, error, isLoading, refetch } = useService(id);

  return (
    <AppShell>
      <PageHeader
        eyebrow="Deployment"
        title={service?.name ?? id}
        description={service ? `${service.artifactId} on ${service.backendKind}` : undefined}
        actions={
          service && (
            <span className="inline-flex items-center gap-2 rift-mono text-[12px]">
              <StatDot
                tone={
                  service.status === "running"
                    ? "ok"
                    : service.status === "degraded"
                      ? "attention"
                      : service.status === "failed"
                        ? "error"
                        : "info"
                }
              />
              {service.status}
            </span>
          )
        }
      />
      <div className="border-b border-border bg-raised">
        <div className="max-w-[1400px] mx-auto px-4 flex gap-0 overflow-x-auto">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => navigate({ search: { tab: t.id }, replace: true })}
              className={cn(
                "h-11 px-4 text-[13px] border-b-2 -mb-px whitespace-nowrap",
                tab === t.id
                  ? "border-primary text-ink font-medium"
                  : "border-transparent text-ink-secondary hover:text-ink",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="max-w-[1400px] mx-auto min-w-0 px-4 py-6 grid gap-4">
        {unavailable && <Unavailable endpoint="/services" resource="Service" />}
        {isLoading && !service && (
          <Panel title="Live deployment state">
            <div className="flex items-center gap-2 text-[13px] text-ink-secondary" role="status">
              <Loader2 className="size-4 animate-spin" aria-hidden />
              Reading live service state...
            </div>
          </Panel>
        )}
        {error && !service && (
          <Panel title="Live deployment state">
            <div className="text-[13px] text-error" role="alert">
              The controller could not return this deployment: {error.message}
            </div>
          </Panel>
        )}
        {service && (
          <ServiceActions
            service={service}
            onChanged={() => {
              refetch();
              window.setTimeout(refetch, 3_000);
              window.setTimeout(refetch, 12_000);
            }}
            onDeleted={() => navigate({ to: "/deployments" })}
          />
        )}
        {service && tab === "overview" && <OverviewTab s={service} />}
        {service && tab === "playground" && <PlaygroundTab s={service} />}
        {service && tab === "performance" && <PerformanceTab s={service} />}
        {service && tab === "tuning" && <DeploymentTuningTab service={service} />}
        {service && tab === "logs" && <LogsTab service={service} />}
        {service && tab === "configuration" && <ConfigurationTab s={service} />}
        {tab === "revisions" && <RevisionsTab id={id} />}
      </div>
    </AppShell>
  );
}

function DeploymentTuningTab({ service }: { service: Service }) {
  return (
    <Panel title="Autonomous tuning">
      <div className="max-w-2xl">
        <div className="flex items-start gap-3">
          <SlidersHorizontal className="size-5 text-primary mt-0.5" aria-hidden />
          <div>
            <h2 className="text-[15px] text-ink font-medium">
              Tune {service.name} after deployment
            </h2>
            <p className="mt-1.5 text-[13px] text-ink-secondary">
              Choose Speed or Cost in the tuning workspace. RIFT will benchmark bounded llama.cpp
              settings, keep the model and precision contract locked, and show the evidence behind
              the winner.
            </p>
            <Link
              to="/tuning"
              className="mt-4 inline-flex items-center h-9 px-3.5 rounded-[4px] bg-primary text-primary-foreground text-[13px] font-medium hover:bg-[color:var(--oxide-deep)]"
            >
              Open tuning workspace
            </Link>
          </div>
        </div>
      </div>
    </Panel>
  );
}

function ServiceActions({
  service,
  onChanged,
  onDeleted,
}: {
  service: Service;
  onChanged: () => void;
  onDeleted: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmTune, setConfirmTune] = useState(false);
  const [confirmRestart, setConfirmRestart] = useState(false);
  const [confirmRecover, setConfirmRecover] = useState(false);

  const run = async (action: string, task: () => Promise<unknown>) => {
    setBusy(action);
    setMessage(null);
    setError(null);
    try {
      const result = await task();
      const payload =
        result && typeof result === "object" ? (result as Record<string, unknown>) : {};
      setMessage(
        typeof payload.reason === "string"
          ? payload.reason
          : ["restart", "recover"].includes(action)
            ? `${action} completed; verifying service health.`
            : `${action} completed; refresh the live service state for details.`,
      );
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
      setConfirmDelete(false);
      setConfirmTune(false);
      setConfirmRestart(false);
      setConfirmRecover(false);
    }
  };

  return (
    <section className="rift-panel px-4 py-3" aria-label="Service operations">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rift-label mr-2">Operations</span>
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => run("benchmark", () => rift.benchmarkSuite(service.name))}
          className="inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] border border-border text-[12px] hover:bg-muted disabled:opacity-50"
        >
          {busy === "benchmark" ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Gauge className="size-3.5" />
          )}
          Benchmark
        </button>
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => run("tune plan", () => rift.tuneService(service.name))}
          className="inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] border border-border text-[12px] hover:bg-muted disabled:opacity-50"
        >
          <SlidersHorizontal className="size-3.5" /> Tune plan
        </button>
        {confirmRestart ? (
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => run("restart", () => rift.restartService(service.name))}
            className="inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] bg-attention text-ink text-[12px] font-medium disabled:opacity-50"
          >
            <RotateCcw className="size-3.5" /> Confirm restart
          </button>
        ) : (
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => setConfirmRestart(true)}
            className="inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] border border-border text-[12px] hover:bg-muted disabled:opacity-50"
          >
            <RotateCcw className="size-3.5" /> Restart
          </button>
        )}
        {confirmRecover ? (
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => run("recover", () => rift.recoverService(service.name))}
            className="inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] bg-secondary text-white text-[12px] font-medium disabled:opacity-50"
          >
            <ShieldCheck className="size-3.5" /> Confirm recover
          </button>
        ) : (
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => setConfirmRecover(true)}
            className="inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] border border-border text-[12px] hover:bg-muted disabled:opacity-50"
          >
            <ShieldCheck className="size-3.5" /> Recover
          </button>
        )}
        {confirmTune ? (
          <button
            type="button"
            disabled={busy !== null}
            onClick={() =>
              run("live tune", () =>
                rift.tuneService(service.name, {
                  live: true,
                  allowRestart: true,
                  candidateLimit: 2,
                }),
              )
            }
            className="inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] bg-attention text-ink text-[12px] font-medium disabled:opacity-50"
          >
            Confirm live tune
          </button>
        ) : (
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => setConfirmTune(true)}
            className="inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] border border-border text-[12px] hover:bg-muted disabled:opacity-50"
          >
            Tune live
          </button>
        )}
        {service.status !== "running" &&
          (confirmRecover ? (
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => run("recover", () => rift.recoverService(service.name))}
              className="inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] bg-primary text-white text-[12px] font-medium disabled:opacity-50"
            >
              <RotateCcw className="size-3.5" /> Confirm recovery
            </button>
          ) : (
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => setConfirmRecover(true)}
              className="inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] border border-primary/40 text-primary text-[12px] hover:bg-primary/10 disabled:opacity-50"
            >
              <RotateCcw className="size-3.5" /> Recover service
            </button>
          ))}
        {confirmDelete ? (
          <button
            type="button"
            disabled={busy !== null}
            onClick={() =>
              run("delete", async () => {
                const result = await rift.destroyService(service.name);
                onDeleted();
                return result;
              })
            }
            className="inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] bg-error text-white text-[12px] font-medium disabled:opacity-50"
          >
            Confirm delete
          </button>
        ) : (
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => setConfirmDelete(true)}
            className="inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] border border-error/40 text-error text-[12px] hover:bg-error/10 disabled:opacity-50"
          >
            <Trash2 className="size-3.5" /> Delete service
          </button>
        )}
      </div>
      {(message || error || confirmTune || confirmDelete || confirmRestart || confirmRecover) && (
        <div
          className="mt-2 rift-mono text-[11px] text-ink-secondary"
          role={error ? "alert" : undefined}
        >
          {error ??
            message ??
            (confirmTune
              ? "Live tuning will restart the backend between candidates."
              : confirmRestart
                ? "Restart stops and relaunches the selected service using its current launch plan."
                : confirmRecover
                  ? "Recovery may relaunch the service using its last-known-good launch plan."
                  : "Deletion stops the service and removes its RIFT-managed state; model files are retained.")}
        </div>
      )}
    </section>
  );
}

function OverviewTab({ s }: { s: Service }) {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="lg:col-span-2 grid gap-4">
        <Panel title="Endpoint" aside={<SourceBadge source={s.provenance} />}>
          <div className="flex items-center gap-2">
            <code className="flex-1 rift-mono text-[13px] text-ink break-all">
              {s.endpoint.scheme}://{s.endpoint.bindAddress}:{s.endpoint.port}
              {s.endpoint.path}
            </code>
            <button
              type="button"
              onClick={() =>
                navigator.clipboard.writeText(
                  `${s.endpoint.scheme}://${s.endpoint.bindAddress}:${s.endpoint.port}${s.endpoint.path}`,
                )
              }
              className="inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] border border-border text-[12px] hover:bg-muted"
            >
              <Copy className="size-3.5" /> Copy
            </button>
          </div>
          <p className="mt-2 rift-mono text-[11px] text-ink-secondary">
            {s.endpoint.openaiCompatible ? "OpenAI-compatible" : "Custom protocol"} · binds to{" "}
            {s.endpoint.bindAddress === "127.0.0.1" ? "localhost only" : s.endpoint.bindAddress}
          </p>
        </Panel>
        <Panel title="Assignments">
          <ul className="divide-y divide-border -mx-4 -my-4">
            {s.assignments.map((a, i) => (
              <li key={i} className="px-4 py-3 flex items-center gap-4 text-[13px]">
                <span className="rift-mono text-ink">{a.nodeId}</span>
                <span className="rift-mono text-[11.5px] text-ink-secondary">
                  GPU {a.gpuIndices.join(", ") || "cpu"}
                </span>
                <span className="ml-auto rift-mono text-[11.5px] text-ink-secondary">
                  {bytes(a.reservedVramBytes)} reserved
                </span>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
      <div className="grid gap-4">
        <Panel title="Meta">
          <div className="grid gap-3">
            <KV label="Service ID" value={s.id} />
            <KV label="Artifact" value={s.artifactId} />
            <KV label="Backend" value={s.backendKind} />
            <KV label="Use case" value={s.useCase} />
            <KV label="Revision" value={s.currentRevision} />
            <KV label="Updated" value={relativeTime(s.updatedAt)} />
          </div>
        </Panel>
      </div>
    </div>
  );
}

function PlaygroundTab({ s }: { s: Service }) {
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [out, setOut] = useState<string>("");
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setErr(null);
    setOut("");
    try {
      const endpoint = `${s.endpoint.scheme}://${s.endpoint.bindAddress}:${s.endpoint.port}${s.endpoint.path}`;
      let model = s.artifactId;
      try {
        const catalog = await fetch(`${endpoint}/models`);
        if (catalog.ok) {
          const payload = (await catalog.json()) as {
            data?: { id?: string }[];
          };
          model = payload.data?.find((item) => item.id)?.id ?? model;
        }
      } catch {
        // Keep the artifact identifier as a compatibility fallback for minimal servers.
      }
      const url = `${endpoint}/chat/completions`;
      const res = await fetch(url, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          model,
          messages: [{ role: "user", content: input }],
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const j = (await res.json()) as {
        choices?: { message?: { content?: string } }[];
      };
      setOut(j.choices?.[0]?.message?.content ?? "");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panel title="Prompt">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          rows={10}
          placeholder="Ask the model something…"
          className="w-full p-3 rounded-[4px] border border-border bg-raised text-[13px] focus:outline-none focus:border-primary resize-y"
        />
        <div className="mt-3 flex items-center gap-2">
          <button
            type="button"
            onClick={submit}
            disabled={busy || !input.trim()}
            className="inline-flex items-center gap-2 h-9 px-3.5 rounded-[4px] bg-primary text-primary-foreground text-[13px] font-medium hover:bg-[color:var(--oxide-deep)] disabled:opacity-60"
          >
            <Send className="size-4" /> Send
          </button>
          <span className="rift-mono text-[11px] text-ink-secondary">
            Calls the service's own OpenAI-compatible endpoint (not the controller API).
          </span>
        </div>
      </Panel>
      <Panel title="Response">
        {err ? (
          <div className="text-[13px] text-error rift-mono">{err}</div>
        ) : (
          <pre className="whitespace-pre-wrap text-[13px] text-ink min-h-[8rem]">
            {out || <span className="text-ink-secondary">Waiting for prompt…</span>}
          </pre>
        )}
      </Panel>
    </div>
  );
}

function PerformanceTab({ s }: { s: Service }) {
  const { data, unavailable, refetch } = useBenchmarks(s.id);
  const telemetry = useTelemetryLatest(s.name);
  const resourceReports = useResourceReports(s.name);
  const accounting = useServiceTelemetryAccounting(s.name);
  const evaluations = useEvaluations(s.name);
  const reports = useReports();
  const [benchmarkPrompt, setBenchmarkPrompt] = useState(
    "Explain one practical benefit of local LLM inference in two sentences.",
  );
  const [benchmarkMaxTokens, setBenchmarkMaxTokens] = useState(48);
  const [benchmarkWarmups, setBenchmarkWarmups] = useState(1);
  const [benchmarkRepetitions, setBenchmarkRepetitions] = useState(3);
  const [benchmarkConcurrency, setBenchmarkConcurrency] = useState(1);
  const [benchmarkBusy, setBenchmarkBusy] = useState(false);
  const [benchmarkError, setBenchmarkError] = useState<string | null>(null);
  const [evaluationBusy, setEvaluationBusy] = useState(false);
  const [evaluationError, setEvaluationError] = useState<string | null>(null);
  const [electricityPrice, setElectricityPrice] = useState("");
  const [computeCost, setComputeCost] = useState("");
  const [accountingBusy, setAccountingBusy] = useState(false);
  const [accountingError, setAccountingError] = useState<string | null>(null);
  const [accountingSaved, setAccountingSaved] = useState(false);
  useEffect(() => {
    if (!accounting.data) return;
    setElectricityPrice(
      accounting.data.electricityPricePerKwh == null
        ? ""
        : String(accounting.data.electricityPricePerKwh),
    );
    setComputeCost(
      accounting.data.computeCostPerNodeHour == null
        ? ""
        : String(accounting.data.computeCostPerNodeHour),
    );
  }, [accounting.data]);
  const latestEvaluation = evaluations.data?.[0];
  const latestTuning = (Array.isArray(reports.data?.reports) ? reports.data.reports : [])
    .map((value) => {
      const entry = asRecord(value);
      return {
        created: Number(entry.created_unix_seconds ?? 0),
        report: asRecord(entry.summary),
      };
    })
    .filter(({ report }) => {
      return String(report.service ?? "") === s.name && "winning_config" in report;
    })
    .sort((left, right) => right.created - left.created)[0]?.report;
  const runEvaluation = async () => {
    setEvaluationBusy(true);
    setEvaluationError(null);
    try {
      await rift.evaluateService(s.name);
      evaluations.refetch();
    } catch (error) {
      setEvaluationError(error instanceof Error ? error.message : String(error));
    } finally {
      setEvaluationBusy(false);
    }
  };
  const runBenchmark = async () => {
    setBenchmarkBusy(true);
    setBenchmarkError(null);
    try {
      await rift.benchmarkSuite(s.name, {
        prompt: benchmarkPrompt,
        maxTokens: Math.min(128, Math.max(1, benchmarkMaxTokens)),
        warmups: Math.max(0, benchmarkWarmups),
        repetitions: Math.max(1, benchmarkRepetitions),
        concurrency: Math.max(1, benchmarkConcurrency),
      });
      refetch();
    } catch (error) {
      setBenchmarkError(error instanceof Error ? error.message : String(error));
    } finally {
      setBenchmarkBusy(false);
    }
  };
  const saveAccounting = async () => {
    const parseRate = (value: string, label: string): number | null => {
      if (!value.trim()) return null;
      const parsed = Number(value);
      if (!Number.isFinite(parsed) || parsed < 0) {
        throw new Error(`${label} must be a non-negative number or blank.`);
      }
      return parsed;
    };
    setAccountingBusy(true);
    setAccountingError(null);
    setAccountingSaved(false);
    try {
      await rift.updateServiceTelemetryAccounting(s.name, {
        electricityPricePerKwh: parseRate(electricityPrice, "Electricity price"),
        computeCostPerNodeHour: parseRate(computeCost, "Compute cost"),
      });
      await Promise.all([accounting.refetch(), resourceReports.refetch()]);
      setAccountingSaved(true);
    } catch (error) {
      setAccountingError(error instanceof Error ? error.message : String(error));
    } finally {
      setAccountingBusy(false);
    }
  };
  if (unavailable) return <Unavailable endpoint="/reports" resource="Benchmark[]" />;
  const rows = data ?? [];
  const live = telemetry.data?.[0];
  const liveSample = live?.sample;
  const value = (item: number | undefined, suffix = "") =>
    item == null || Number.isNaN(item) ? "unavailable" : `${item.toFixed(1)}${suffix}`;
  return (
    <div className="grid gap-4">
      <Panel
        title="Live resources"
        aside={
          <span className="rift-mono text-[11px] text-ink-secondary">
            {liveSample
              ? `sampled ${relativeTime(liveSample.observedAt)}`
              : "waiting for telemetry"}
          </span>
        }
      >
        {telemetry.unavailable ? (
          <div className="text-[13px] text-ink-secondary">
            Resource telemetry is not available from this controller.
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <KV label="Service CPU" value={value(liveSample?.processCpuPercent, "%")} />
            <KV
              label="Service memory"
              value={
                liveSample?.processRssBytes == null
                  ? "unavailable"
                  : bytes(liveSample.processRssBytes)
              }
            />
            <KV label="GPU utilization" value={value(liveSample?.gpuUtilizationPercent, "%")} />
            <KV label="GPU temperature" value={value(liveSample?.gpuTemperatureC, "°C")} />
            <KV label="GPU power" value={value(liveSample?.gpuPowerWatts, " W")} />
            <KV label="Host RAM pressure" value={value(liveSample?.hostRamPressurePercent, "%")} />
            <KV
              label="GPU VRAM"
              value={
                liveSample?.gpuVramUsedBytes == null
                  ? "unavailable"
                  : `${bytes(liveSample.gpuVramUsedBytes)} / ${bytes(liveSample.gpuVramTotalBytes ?? 0)}`
              }
            />
            <KV
              label="Collection"
              value={liveSample?.availability?.gpu === "measured" ? "measured" : "partial"}
            />
          </div>
        )}
      </Panel>
      <Panel title="Resource accounting" aside={<SourceBadge source="live" />}>
        {accounting.unavailable ? (
          <p className="text-[12px] text-ink-secondary">
            Service accounting settings are unavailable from this controller.
          </p>
        ) : (
          <div className="grid gap-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="grid gap-1 text-[12px]">
                <span className="rift-label">Electricity price / kWh</span>
                <input
                  type="number"
                  min={0}
                  step="0.0001"
                  value={electricityPrice}
                  onChange={(event) => setElectricityPrice(event.target.value)}
                  placeholder="Not configured"
                  className="h-8 rounded-[4px] border border-border bg-raised px-2 rift-mono"
                />
                <span className="text-[11px] text-ink-secondary">
                  {accounting.data?.electricityPriceSource === "global"
                    ? "Using the global telemetry default. Enter a value to override it for this service."
                    : "Leave blank to clear this service override."}
                </span>
              </label>
              <label className="grid gap-1 text-[12px]">
                <span className="rift-label">Compute cost / node-hour</span>
                <input
                  type="number"
                  min={0}
                  step="0.0001"
                  value={computeCost}
                  onChange={(event) => setComputeCost(event.target.value)}
                  placeholder="Not configured"
                  className="h-8 rounded-[4px] border border-border bg-raised px-2 rift-mono"
                />
                <span className="text-[11px] text-ink-secondary">
                  Applied to this service's runtime duration in future reports.
                </span>
              </label>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={saveAccounting}
                disabled={accountingBusy}
                className="inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] bg-primary text-primary-foreground text-[12px] font-medium hover:bg-[color:var(--oxide-deep)] disabled:opacity-50"
              >
                {accountingBusy ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Save className="size-3.5" />
                )}
                Save service rates
              </button>
              <span className="rift-mono text-[11px] text-ink-secondary">
                {accounting.data?.configPath
                  ? `Stored in ${accounting.data.configPath}`
                  : "Stored in the service configuration"}
              </span>
              {accountingSaved && <span className="text-[11px] text-secondary">Saved</span>}
            </div>
            {accountingError && (
              <p className="rift-mono text-[11px] text-error" role="alert">
                {accountingError}
              </p>
            )}
          </div>
        )}
      </Panel>
      {resourceReports.data && resourceReports.data.length > 0 && (
        <Panel title="Completed resource reports" bodyClassName="p-0">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-[13px] rift-mono">
              <thead className="rift-label">
                <tr className="border-b border-border">
                  <th className="text-left px-4 h-9 font-normal">Stopped</th>
                  <th className="text-left px-4 font-normal">Samples</th>
                  <th className="text-left px-4 font-normal">CPU avg</th>
                  <th className="text-left px-4 font-normal">GPU energy</th>
                  <th className="text-left px-4 font-normal">Cost</th>
                </tr>
              </thead>
              <tbody>
                {resourceReports.data.map((report) => {
                  const cpu = report.metrics.process_cpu_percent?.average;
                  const energy = report.costs?.energyJoules;
                  const electricity = report.costs?.electricityCost;
                  const compute = report.costs?.computeCost;
                  const cost =
                    report.costs?.totalCost ??
                    (electricity == null && compute == null
                      ? undefined
                      : (electricity ?? 0) + (compute ?? 0));
                  return (
                    <tr key={report.reportId} className="border-b border-border last:border-0">
                      <td className="px-4 py-2">{relativeTime(report.stoppedAt)}</td>
                      <td className="px-4">{report.sampleCount}</td>
                      <td className="px-4">{value(cpu, "%")}</td>
                      <td className="px-4">
                        {energy == null ? "unavailable" : `${energy.toFixed(1)} J`}
                      </td>
                      <td className="px-4">
                        {cost == null ? (
                          "unconfigured"
                        ) : (
                          <span
                            title={`Electricity: ${electricity ?? 0}; compute: ${compute ?? 0}`}
                          >
                            {cost.toFixed(4)}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
      <Panel title="Benchmarks" bodyClassName="p-0">
        {rows.length === 0 ? (
          <div className="px-4 py-10 text-center text-[13px] text-ink-secondary">
            No benchmarks recorded yet.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[620px] text-[13px] rift-mono">
              <thead className="rift-label">
                <tr className="border-b border-border">
                  <th className="text-left px-4 h-9 font-normal">At</th>
                  <th className="text-left px-4 font-normal">tok/s</th>
                  <th className="text-left px-4 font-normal">first token</th>
                  <th className="text-left px-4 font-normal">concurrency</th>
                  <th className="text-left px-4 font-normal">ctx</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((b) => (
                  <tr key={b.id} className="border-b border-border last:border-0">
                    <td className="px-4 py-2">{relativeTime(b.measuredAt)}</td>
                    <td className="px-4">{b.tokensPerSec.toFixed(1)}</td>
                    <td className="px-4">{b.firstTokenMs}ms</td>
                    <td className="px-4">{b.concurrency}</td>
                    <td className="px-4">{b.contextTokens}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      <Panel title="Run benchmark">
        <div className="grid gap-3">
          <label className="grid gap-1 text-[12px]">
            <span className="rift-label">Prompt</span>
            <textarea
              value={benchmarkPrompt}
              onChange={(event) => setBenchmarkPrompt(event.target.value)}
              rows={3}
              className="w-full rounded-[4px] border border-border bg-raised p-2 text-[13px] resize-y"
            />
          </label>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <label className="grid gap-1 text-[12px]">
              <span className="rift-label">Output tokens</span>
              <input
                type="number"
                min={1}
                max={128}
                value={benchmarkMaxTokens}
                onChange={(event) => setBenchmarkMaxTokens(Number(event.target.value))}
                className="h-8 rounded-[4px] border border-border bg-raised px-2 rift-mono"
              />
            </label>
            <label className="grid gap-1 text-[12px]">
              <span className="rift-label">Warmups</span>
              <input
                type="number"
                min={0}
                max={10}
                value={benchmarkWarmups}
                onChange={(event) => setBenchmarkWarmups(Number(event.target.value))}
                className="h-8 rounded-[4px] border border-border bg-raised px-2 rift-mono"
              />
            </label>
            <label className="grid gap-1 text-[12px]">
              <span className="rift-label">Repetitions</span>
              <input
                type="number"
                min={1}
                max={20}
                value={benchmarkRepetitions}
                onChange={(event) => setBenchmarkRepetitions(Number(event.target.value))}
                className="h-8 rounded-[4px] border border-border bg-raised px-2 rift-mono"
              />
            </label>
            <label className="grid gap-1 text-[12px]">
              <span className="rift-label">Concurrency</span>
              <input
                type="number"
                min={1}
                max={8}
                value={benchmarkConcurrency}
                onChange={(event) => setBenchmarkConcurrency(Number(event.target.value))}
                className="h-8 rounded-[4px] border border-border bg-raised px-2 rift-mono"
              />
            </label>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={runBenchmark}
              disabled={
                benchmarkBusy ||
                !benchmarkPrompt.trim() ||
                !["running", "healthy"].includes(s.status)
              }
              className="inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] bg-primary text-primary-foreground text-[12px] font-medium hover:bg-[color:var(--oxide-deep)] disabled:opacity-50"
            >
              {benchmarkBusy ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Gauge className="size-3.5" />
              )}
              Run measured benchmark
            </button>
            <span className="rift-mono text-[11px] text-ink-secondary">
              Defaults: 1 warmup, 3 samples, concurrency 1.
            </span>
          </div>
          {benchmarkError && (
            <p className="rift-mono text-[11px] text-error" role="alert">
              {benchmarkError}
            </p>
          )}
        </div>
      </Panel>
      <Panel title="Latest tuning result" aside={<SourceBadge source="live" />}>
        {reports.unavailable ? (
          <p className="text-[12px] text-ink-secondary">Tuning history is unavailable.</p>
        ) : !latestTuning ? (
          <p className="text-[12px] text-ink-secondary">No tuning result recorded yet.</p>
        ) : (
          <div className="grid gap-4">
            <div className="grid gap-4 sm:grid-cols-4">
              <KV
                label="Performance delta"
                value={
                  typeof latestTuning.improvement_percent === "number"
                    ? `${latestTuning.improvement_percent.toFixed(2)}%`
                    : "not measured"
                }
              />
              <KV
                label="Baseline score"
                value={
                  typeof latestTuning.baseline_score === "number"
                    ? latestTuning.baseline_score.toFixed(3)
                    : "not measured"
                }
              />
              <KV
                label="Winning score"
                value={
                  typeof latestTuning.winning_score === "number"
                    ? latestTuning.winning_score.toFixed(3)
                    : "not measured"
                }
              />
              <KV label="Mode" value={String(latestTuning.mode ?? "measured")} />
            </div>
            <div>
              <div className="rift-label">Winning parameters</div>
              <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded-[4px] border border-border bg-raised p-3 rift-mono text-[11.5px] text-ink">
                {JSON.stringify(latestTuning.winning_config, null, 2)}
              </pre>
            </div>
            <p className="text-[12px] text-ink-secondary">
              {String(
                latestTuning.decision ?? "Winner selected from the recorded tuning candidates.",
              )}
            </p>
          </div>
        )}
      </Panel>
      <Panel
        title="Answer quality"
        aside={
          <button
            type="button"
            onClick={runEvaluation}
            disabled={evaluationBusy || s.status !== "running"}
            className="inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] bg-primary text-primary-foreground text-[12px] font-medium hover:bg-[color:var(--oxide-deep)] disabled:opacity-50"
          >
            {evaluationBusy ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <ShieldCheck className="size-3.5" />
            )}
            Run smoke check
          </button>
        }
      >
        <p className="text-[12px] text-ink-secondary">
          Five bounded, deterministic checks. This measures behavior against explicit criteria; it
          is not a general accuracy certification.
        </p>
        {evaluationError && (
          <p className="mt-3 rift-mono text-[11px] text-error" role="alert">
            {evaluationError}
          </p>
        )}
        {evaluations.unavailable ? (
          <p className="mt-3 rift-mono text-[11px] text-ink-secondary">
            Answer evaluation is unavailable on this controller.
          </p>
        ) : latestEvaluation ? (
          <div className="mt-4 grid gap-2">
            <div className="flex flex-wrap items-center gap-3 rift-mono text-[11px]">
              <span className="text-ink">
                {latestEvaluation.suite.id} v{latestEvaluation.suite.version}
              </span>
              <span className="text-ink-secondary">
                {latestEvaluation.summary.pass ?? 0} passed
              </span>
              <span className="text-error">{latestEvaluation.summary.fail ?? 0} failed</span>
              <span className="text-ink-secondary">
                {latestEvaluation.summary.not_assessed ?? 0} not assessed
              </span>
              <span className="ml-auto text-ink-secondary">{latestEvaluation.status}</span>
            </div>
            <ul className="divide-y divide-border border border-border rounded-[4px]">
              {latestEvaluation.cases.map((item) => (
                <li key={item.caseId} className="flex items-start gap-2 px-3 py-2 text-[12px]">
                  {item.status === "pass" ? (
                    <CheckCircle2 className="mt-0.5 size-3.5 text-secondary shrink-0" />
                  ) : (
                    <XCircle className="mt-0.5 size-3.5 text-error shrink-0" />
                  )}
                  <span className="min-w-0">
                    <span className="font-medium text-ink">{item.caseId}</span>
                    <span className="block text-ink-secondary">{item.detail}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="mt-3 rift-mono text-[11px] text-ink-secondary">
            No evaluation run recorded yet.
          </p>
        )}
      </Panel>
    </div>
  );
}

function LogsTab({ service }: { service: Service }) {
  const { data, unavailable } = useLogs(service.name);
  if (unavailable) {
    return <Unavailable endpoint="/logs" resource={`${service.name} service logs`} />;
  }
  const lines = Array.isArray(data?.lines)
    ? data.lines
    : typeof data?.text === "string"
      ? data.text.split(/\r?\n/)
      : [];
  return (
    <Panel
      title={`${service.name} / latest logs`}
      aside={<SourceBadge source="live" />}
      bodyClassName="p-0"
    >
      <pre className="max-h-[580px] overflow-auto bg-[color:var(--ink)] px-4 py-3 rift-mono text-[11.5px] leading-5 text-[color:var(--surface)]">
        {lines.length
          ? lines.map((line) => (typeof line === "string" ? line : JSON.stringify(line))).join("\n")
          : "No log lines available."}
      </pre>
    </Panel>
  );
}

function ConfigurationTab({ s }: { s: Service }) {
  const details = s.details ?? {};
  const model = details.model ?? {};
  const serving = details.serving ?? {};
  const gateway = details.gateway ?? {};
  const launchPlan = details.launchPlan ?? {};
  const modelPath = String(details.modelPath ?? model.selected_file ?? model.id ?? s.artifactId);
  const contextLength =
    serving.context_length ?? launchPlan.context_length ?? details.contextLength;
  const concurrency = serving.concurrency ?? launchPlan.concurrency ?? details.concurrency;
  const gatewayCors = gateway.cors_origins;
  const corsOrigins = Array.isArray(gatewayCors)
    ? gatewayCors.map(String)
    : typeof gatewayCors === "string"
      ? [gatewayCors]
      : [];
  const exposed = !["127.0.0.1", "localhost", "::1"].includes(s.endpoint.bindAddress);
  const securityWarnings: string[] = [];
  if (corsOrigins.includes("*")) {
    securityWarnings.push("Unrestricted CORS is enabled for this service.");
  }
  if (exposed && gateway.api_key_protection === "not_configured") {
    securityWarnings.push(
      "The service is network-exposed but gateway API-key protection is not configured.",
    );
  }
  const effectiveLaunch = {
    service: s.name,
    backend: s.backendKind,
    backend_version: details.backendVersion ?? launchPlan.version ?? "unknown",
    artifact: s.artifactId,
    model: modelPath,
    serving,
    endpoint: s.endpoint,
    placement: s.assignments,
    launch_plan: launchPlan,
    gateway,
    process: { pid: details.pid ?? null, restart_count: details.restartCount ?? null },
  };
  const yaml = `service:
  name: ${s.name}
  artifact: ${s.artifactId}
  backend: ${s.backendKind}
  endpoint:
    scheme: ${s.endpoint.scheme}
    bind: ${s.endpoint.bindAddress}
    port: ${s.endpoint.port}
    path: ${s.endpoint.path}
assignments:
${s.assignments.map((a) => `  - node: ${a.nodeId}\n    gpus: [${a.gpuIndices.join(", ")}]`).join("\n")}
`;
  return (
    <div className="grid gap-4">
      <Panel title="Effective launch settings" aside={<SourceBadge source="live" />}>
        {securityWarnings.length > 0 && (
          <div
            className="mb-4 border border-error/50 bg-error/5 px-3 py-3 text-[12px] text-error"
            role="alert"
          >
            <div className="rift-label text-error">Security attention required</div>
            <ul className="mt-2 grid gap-1 list-disc pl-4">
              {securityWarnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </div>
        )}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <KV
            label="Backend"
            value={`${s.backendKind} · ${String(details.backendVersion ?? launchPlan.version ?? "version unknown")}`}
          />
          <KV label="Model" value={modelPath} />
          <KV
            label="Endpoint"
            value={`${s.endpoint.scheme}://${s.endpoint.bindAddress}:${s.endpoint.port}${s.endpoint.path}`}
          />
          <KV
            label="Exposure"
            value={`${String(details.exposure ?? "local")} · ${s.endpoint.bindAddress}`}
          />
          <KV
            label="Context length"
            value={contextLength == null ? "unknown" : String(contextLength)}
          />
          <KV label="Concurrency" value={concurrency == null ? "unknown" : String(concurrency)} />
          <KV label="Process" value={details.pid == null ? "not running" : `PID ${details.pid}`} />
          <KV
            label="Gateway"
            value={gateway.status == null ? "not configured" : String(gateway.status)}
          />
        </div>
        <details className="mt-4 border-t border-border pt-3">
          <summary className="cursor-pointer rift-label">Full effective launch payload</summary>
          <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap rift-mono text-[11.5px] text-ink">
            {JSON.stringify(effectiveLaunch, null, 2)}
          </pre>
        </details>
      </Panel>
      <Panel
        title="Normalized configuration"
        aside={
          <button
            type="button"
            onClick={() => navigator.clipboard.writeText(yaml)}
            className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-[4px] border border-border text-[11.5px] hover:bg-muted"
          >
            <Copy className="size-3" /> Copy YAML
          </button>
        }
      >
        <pre className="rift-mono text-[12.5px] text-ink whitespace-pre">{yaml}</pre>
        <p className="mt-3 rift-mono text-[11px] text-ink-secondary">
          Advanced users can export this via GET /services or apply changes by generating a new
          plan.
        </p>
      </Panel>
    </div>
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function RevisionsTab({ id }: { id: string }) {
  const { data, unavailable } = useRevisions(id);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  if (unavailable) return <Unavailable endpoint="/state" resource="DeploymentRevision[]" />;
  const rows = data ?? [];
  const rollback = async () => {
    setBusy(true);
    setMessage(null);
    setError(null);
    try {
      await rift.rollback(id);
      setMessage("Rollback completed; refresh the live service state for details.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
      setConfirm(false);
    }
  };
  return (
    <Panel
      title="Revisions"
      bodyClassName="p-0"
      aside={
        rows.length > 0 && (
          <button
            type="button"
            disabled={busy}
            onClick={() => setConfirm(true)}
            className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-[4px] border border-border text-[11.5px] hover:bg-muted disabled:opacity-50"
          >
            <RotateCcw className="size-3" /> Roll back last known-good
          </button>
        )
      }
    >
      {(message || error) && (
        <div
          className="px-4 py-2 border-b border-border rift-mono text-[11px]"
          role={error ? "alert" : undefined}
        >
          <span className={error ? "text-error" : "text-ink-secondary"}>{error ?? message}</span>
        </div>
      )}
      {confirm && !busy && (
        <div className="px-4 py-2 border-b border-border flex flex-wrap items-center gap-2 rift-mono text-[11px]">
          <span className="text-ink-secondary">
            This relaunches the last known-good service configuration.
          </span>
          <button
            type="button"
            onClick={rollback}
            className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-[4px] bg-attention text-ink font-medium"
          >
            Confirm rollback
          </button>
          <button
            type="button"
            onClick={() => setConfirm(false)}
            className="inline-flex items-center h-7 px-2.5 rounded-[4px] border border-border"
          >
            Cancel
          </button>
        </div>
      )}
      {rows.length === 0 ? (
        <div className="px-4 py-10 text-center text-[13px] text-ink-secondary">
          No revisions yet.
        </div>
      ) : (
        <ul className="divide-y divide-border">
          {rows.map((r) => (
            <li key={r.id} className="px-4 py-3 flex items-center gap-3 text-[13px]">
              <span className="rift-mono text-ink">{r.id}</span>
              <span className="rift-mono text-[11.5px] text-ink-secondary truncate">
                plan {r.planHash.slice(0, 12)}… · by {r.appliedBy}
              </span>
              <span className="rift-mono text-[11.5px] text-ink-secondary ml-auto">
                {relativeTime(r.createdAt)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
