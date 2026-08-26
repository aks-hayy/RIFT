import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { z } from "zod";
import { AppShell } from "@/components/rift/app-shell";
import { PageHeader, Panel, KV, StatDot, SourceBadge } from "@/components/rift/primitives";
import { Unavailable } from "@/components/rift/unavailable";
import { useService, useRevisions, useBenchmarks, useLogs } from "@/lib/rift/hooks";
import { rift } from "@/lib/rift/client";
import { bytes, relativeTime } from "@/lib/rift/format";
import { cn } from "@/lib/utils";
import { Copy, Gauge, Loader2, RotateCcw, Send, SlidersHorizontal, Trash2 } from "lucide-react";
import { useState } from "react";
import type { Service } from "@/lib/rift/types";

const searchSchema = z.object({
  tab: z
    .enum(["overview", "playground", "performance", "logs", "configuration", "revisions"])
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
  { id: "logs", label: "Logs" },
  { id: "configuration", label: "Configuration" },
  { id: "revisions", label: "Revisions" },
] as const;

function DeploymentDetail() {
  const { id } = Route.useParams();
  const { tab } = Route.useSearch();
  const navigate = useNavigate({ from: "/deployments/$id" });
  const { data: service, unavailable } = useService(id);

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

      <div className="max-w-[1400px] mx-auto px-4 py-6 grid gap-4">
        {unavailable && <Unavailable endpoint={`/v1/services/${id}`} resource="Service" />}
        {service && (
          <ServiceActions service={service} onDeleted={() => navigate({ to: "/deployments" })} />
        )}
        {service && tab === "overview" && <OverviewTab s={service} />}
        {service && tab === "playground" && <PlaygroundTab s={service} />}
        {service && tab === "performance" && <PerformanceTab s={service} />}
        {service && tab === "logs" && <LogsTab service={service} />}
        {service && tab === "configuration" && <ConfigurationTab s={service} />}
        {tab === "revisions" && <RevisionsTab id={id} />}
      </div>
    </AppShell>
  );
}

function ServiceActions({ service, onDeleted }: { service: Service; onDeleted: () => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmTune, setConfirmTune] = useState(false);
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
          : `${action} completed; refresh the live service state for details.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
      setConfirmDelete(false);
      setConfirmTune(false);
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
      {(message || error || confirmTune || confirmRecover || confirmDelete) && (
        <div
          className="mt-2 rift-mono text-[11px] text-ink-secondary"
          role={error ? "alert" : undefined}
        >
          {error ??
            message ??
            (confirmTune
              ? "Live tuning will restart the backend between candidates."
              : confirmRecover
                ? "Recovery will relaunch the last-known-good backend plan."
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
  const { data, unavailable } = useBenchmarks(s.id);
  if (unavailable)
    return <Unavailable endpoint={`/v1/services/${s.id}/benchmarks`} resource="Benchmark[]" />;
  const rows = data ?? [];
  return (
    <Panel title="Benchmarks" bodyClassName="p-0">
      {rows.length === 0 ? (
        <div className="px-4 py-10 text-center text-[13px] text-ink-secondary">
          No benchmarks recorded yet.
        </div>
      ) : (
        <table className="w-full text-[13px] rift-mono">
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
      )}
    </Panel>
  );
}

function LogsTab({ service }: { service: Service }) {
  const { data, unavailable } = useLogs();
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
        Advanced users can export this via GET /v1/services/{s.id}/yaml or apply changes by
        generating a new plan.
      </p>
    </Panel>
  );
}

function RevisionsTab({ id }: { id: string }) {
  const { data, unavailable } = useRevisions(id);
  if (unavailable)
    return (
      <Unavailable endpoint={`/v1/services/${id}/revisions`} resource="DeploymentRevision[]" />
    );
  const rows = data ?? [];
  return (
    <Panel title="Revisions" bodyClassName="p-0">
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
              <button
                type="button"
                className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-[4px] border border-border text-[11.5px] hover:bg-muted"
              >
                <RotateCcw className="size-3" /> Roll back
              </button>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
