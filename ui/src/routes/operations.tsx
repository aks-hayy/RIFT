import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { z } from "zod";
import { AppShell } from "@/components/rift/app-shell";
import { PageHeader, Panel, StatDot, SourceBadge } from "@/components/rift/primitives";
import { Unavailable } from "@/components/rift/unavailable";
import {
  useIncidents,
  useLatestPlan,
  useLogs,
  useOperations,
  useReports,
  useTimeline,
} from "@/lib/rift/hooks";
import { relativeTime } from "@/lib/rift/format";
import { cn } from "@/lib/utils";
import { rift } from "@/lib/rift/client";
import { Fragment, useState } from "react";
import type { OperationRecord } from "@/lib/rift/types";

const searchSchema = z.object({
  tab: z
    .enum(["operations", "incidents", "rollouts", "audit", "logs", "metrics"])
    .catch("operations"),
});

export const Route = createFileRoute("/operations")({
  validateSearch: searchSchema,
  head: () => ({
    meta: [
      { title: "Operations — RIFT" },
      { name: "description", content: "Incidents, rollouts, audit log, fleet logs, and metrics." },
      { property: "og:title", content: "Operations — RIFT" },
      {
        property: "og:description",
        content: "Incidents, rollouts, audit log, fleet logs, and metrics.",
      },
    ],
  }),
  component: OperationsPage,
});

const TABS = [
  { id: "operations", label: "Operations" },
  { id: "incidents", label: "Incidents" },
  { id: "rollouts", label: "Rollouts" },
  { id: "audit", label: "Audit log" },
  { id: "logs", label: "Fleet logs" },
  { id: "metrics", label: "Metrics" },
] as const;

function OperationsPage() {
  const { tab } = Route.useSearch();
  const navigate = useNavigate({ from: "/operations" });
  return (
    <AppShell>
      <PageHeader
        eyebrow="Operations"
        title="Fleet operations"
        description="Incidents, rollouts, and everything that has happened."
      />
      <div className="border-b border-border bg-raised">
        <div className="max-w-[1400px] mx-auto px-4 flex overflow-x-auto">
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
        {tab === "operations" && <OperationsTab />}
        {tab === "incidents" && <IncidentsTab />}
        {tab === "rollouts" && <RolloutsTab />}
        {tab === "audit" && <AuditTab />}
        {tab === "logs" && <LogsTab />}
        {tab === "metrics" && <MetricsTab />}
      </div>
    </AppShell>
  );
}

function OperationsTab() {
  const { data, unavailable, error, isLoading, refetch } = useOperations();
  const [cancelling, setCancelling] = useState<string | null>(null);
  if (unavailable || error)
    return (
      <Unavailable
        endpoint="/v2/operations"
        resource="Durable operations"
        reason={unavailable?.detail ?? error?.message}
      />
    );
  const operations = data ?? [];
  return (
    <Panel
      title={`${operations.length} durable operation${operations.length === 1 ? "" : "s"}`}
      aside={<SourceBadge source="live" />}
      bodyClassName="p-0"
    >
      {isLoading ? (
        <div className="px-4 py-12 text-center text-[13px] text-ink-secondary">
          Loading operations...
        </div>
      ) : operations.length === 0 ? (
        <div className="px-4 py-12 text-center text-[13px] text-ink-secondary">
          No controller operations have been recorded.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] text-[12.5px]">
            <thead className="rift-label">
              <tr className="border-b border-border">
                <th className="h-9 px-4 text-left font-normal">Operation</th>
                <th className="px-4 text-left font-normal">Action</th>
                <th className="px-4 text-left font-normal">Stage</th>
                <th className="px-4 text-left font-normal">Progress</th>
                <th className="px-4 text-left font-normal">Updated</th>
                <th className="px-4 text-right font-normal">Control</th>
              </tr>
            </thead>
            <tbody>
              {operations.map((operation) => (
                <OperationRow
                  key={operation.operationId}
                  operation={operation}
                  cancelling={cancelling === operation.operationId}
                  onCancel={async () => {
                    setCancelling(operation.operationId);
                    try {
                      await rift.cancelOperation(operation.operationId);
                      refetch();
                    } finally {
                      setCancelling(null);
                    }
                  }}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function OperationRow({
  operation,
  cancelling,
  onCancel,
}: {
  operation: OperationRecord;
  cancelling: boolean;
  onCancel: () => Promise<void>;
}) {
  const active = operation.status === "RUNNING";
  const [expanded, setExpanded] = useState(false);
  const hasDetails = Boolean(operation.error || operation.details || operation.result);
  const tone =
    operation.status === "FAILED" || operation.status === "INTERRUPTED"
      ? "error"
      : active
        ? "attention"
        : "ok";
  return (
    <Fragment>
      <tr className="border-b border-border last:border-0">
        <td className="px-4 py-3 rift-mono text-[11px] text-ink break-all">
          {operation.operationId}
        </td>
        <td className="px-4 py-3 rift-mono text-[11px] text-ink-secondary break-all">
          <div>{operation.action}</div>
          <div className="mt-1 text-[10px] text-ink-secondary">request {operation.requestId}</div>
        </td>
        <td className="px-4 py-3">
          <span className="inline-flex items-center gap-2">
            <StatDot tone={tone} />
            {operation.stage}
          </span>
          <span className="block mt-1 text-[11px] text-ink-secondary max-w-[280px]">
            {operation.message}
          </span>
        </td>
        <td className="px-4 py-3 rift-mono text-[11px]">
          {operation.percent == null ? "indeterminate" : `${Math.round(operation.percent)}%`}
        </td>
        <td className="px-4 py-3 rift-mono text-[11px] text-ink-secondary">
          {relativeTime(operation.updatedAt)}
        </td>
        <td className="px-4 py-3 text-right">
          <div className="flex items-center justify-end gap-2">
            {hasDetails && (
              <button
                type="button"
                aria-expanded={expanded}
                onClick={() => setExpanded((value) => !value)}
                className="h-7 px-2.5 rounded-[4px] border border-border text-[11px] hover:bg-muted"
              >
                {expanded ? "Hide details" : "Details"}
              </button>
            )}
            {active ? (
              <button
                type="button"
                onClick={() => void onCancel()}
                disabled={cancelling}
                className="h-7 px-2.5 rounded-[4px] border border-error/40 text-error text-[11px] hover:bg-error/10 disabled:opacity-50"
              >
                {cancelling ? "Cancelling..." : "Cancel"}
              </button>
            ) : (
              <span className="rift-mono text-[11px] text-ink-secondary">
                {operation.status.toLowerCase()}
              </span>
            )}
          </div>
        </td>
      </tr>
      {expanded && (
        <tr className="border-b border-border bg-muted/20">
          <td colSpan={6} className="px-4 py-3">
            <div className="grid gap-2 text-[11px]">
              {operation.error && (
                <div className="border-l-2 border-error pl-3" role="alert">
                  <div className="rift-label text-error">Failure</div>
                  <p className="mt-1 text-error break-words">{operation.error}</p>
                </div>
              )}
              {operation.details && (
                <div>
                  <div className="rift-label">Stage details</div>
                  <pre className="mt-1 overflow-x-auto whitespace-pre-wrap rift-mono text-ink-secondary">
                    {JSON.stringify(operation.details, null, 2)}
                  </pre>
                </div>
              )}
              {operation.result && (
                <div>
                  <div className="rift-label">Result</div>
                  <pre className="mt-1 max-h-52 overflow-auto whitespace-pre-wrap rift-mono text-ink-secondary">
                    {JSON.stringify(operation.result, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </Fragment>
  );
}

function RolloutsTab() {
  const { data, unavailable, isLoading } = useLatestPlan();
  if (unavailable) {
    return <Unavailable endpoint="/plan" resource="Latest read-only RIFT plan" />;
  }
  if (isLoading || !data) {
    return (
      <Panel title="Latest rollout">
        <p className="text-[13px] text-ink-secondary">Loading plan...</p>
      </Panel>
    );
  }
  return (
    <Panel
      title="Latest rollout plan"
      aside={<SourceBadge source={data.provenance} />}
      bodyClassName="p-0"
    >
      <div className="grid grid-cols-2 gap-4 border-b border-border px-4 py-3 sm:grid-cols-4">
        <Metric label="Plan" value={data.hash.slice(0, 12)} />
        <Metric label="Service" value={data.serviceId} />
        <Metric label="Actions" value={String(data.actions.length)} />
        <Metric label="Apply" value={data.previewOnly ? "CLI guarded" : "available"} />
      </div>
      <ul className="divide-y divide-border">
        {data.actions.map((action) => (
          <li key={action.id} className="flex items-start gap-3 px-4 py-3">
            <StatDot
              tone={
                action.risk === "high" ? "error" : action.risk === "medium" ? "attention" : "info"
              }
            />
            <div className="min-w-0">
              <div className="text-[13px] text-ink">{action.summary}</div>
              <div className="rift-mono text-[10.5px] text-ink-secondary">
                {action.group} · {action.nodeId ?? "controller"} ·{" "}
                {action.reversible ? "reversible" : "not reversible"}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function AuditTab() {
  const { data, unavailable } = useTimeline();
  if (unavailable) return <Unavailable endpoint="/timeline" resource="Controller audit timeline" />;
  const events = Array.isArray(data?.events) ? data.events : [];
  return (
    <Panel
      title={`${events.length} recent controller events`}
      aside={<SourceBadge source="live" />}
      bodyClassName="p-0"
    >
      {events.length === 0 ? (
        <div className="px-4 py-12 text-center text-[13px] text-ink-secondary">
          No events recorded.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[680px] text-[12.5px]">
            <thead className="rift-label">
              <tr className="border-b border-border">
                <th className="h-9 px-4 text-left font-normal">Time</th>
                <th className="px-4 text-left font-normal">Event</th>
                <th className="px-4 text-left font-normal">Service</th>
                <th className="px-4 text-left font-normal">Node</th>
                <th className="px-4 text-left font-normal">Status</th>
              </tr>
            </thead>
            <tbody>
              {events.map((value, index) => {
                const event = asRecord(value);
                const created = Number(event.created_unix_seconds ?? 0);
                return (
                  <tr
                    key={`${String(event.event)}-${created}-${index}`}
                    className="border-b border-border last:border-0"
                  >
                    <td className="px-4 py-2 rift-mono text-[11px] text-ink-secondary">
                      {created ? relativeTime(new Date(created * 1000).toISOString()) : "--"}
                    </td>
                    <td className="px-4 rift-mono">
                      {String(event.event ?? "event").replaceAll("_", " ")}
                    </td>
                    <td className="px-4 rift-mono text-ink-secondary">
                      {String(event.service ?? "--")}
                    </td>
                    <td className="px-4 rift-mono text-ink-secondary">
                      {String(event.node ?? "--")}
                    </td>
                    <td className="px-4">
                      <StatDot tone={String(event.status) === "error" ? "error" : "info"} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function LogsTab() {
  const { data, unavailable } = useLogs();
  if (unavailable)
    return <Unavailable endpoint="/logs" resource="Bounded controller service logs" />;
  const lines = Array.isArray(data?.lines)
    ? data.lines
    : typeof data?.text === "string"
      ? data.text.split(/\r?\n/)
      : [];
  return (
    <Panel
      title="chat / latest log lines"
      aside={<SourceBadge source="live" />}
      bodyClassName="p-0"
    >
      <pre className="max-h-[560px] overflow-auto bg-[color:var(--ink)] px-4 py-3 rift-mono text-[11.5px] leading-5 text-[color:var(--surface)]">
        {lines.length
          ? lines.map((line) => (typeof line === "string" ? line : JSON.stringify(line))).join("\n")
          : "No log lines available."}
      </pre>
    </Panel>
  );
}

function MetricsTab() {
  const { data, unavailable } = useReports();
  if (unavailable)
    return <Unavailable endpoint="/reports" resource="Benchmark and tuning reports" />;
  const reports = Array.isArray(data?.reports) ? data.reports : [];
  const benchmarkCount = reports.filter((value) =>
    String(asRecord(value).path ?? "").includes("benchmark"),
  ).length;
  const tuningCount = reports.filter((value) =>
    String(asRecord(value).path ?? "").includes("tuning"),
  ).length;
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      <Panel title="Reports" aside={<SourceBadge source="live" />}>
        <Metric label="Total retained" value={String(reports.length)} />
      </Panel>
      <Panel title="Benchmarks">
        <Metric label="Runs" value={String(benchmarkCount)} />
      </Panel>
      <Panel title="Tuning">
        <Metric label="Runs" value={String(tuningCount)} />
      </Panel>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="rift-label">{label}</div>
      <div className="mt-1 rift-mono text-[13px] text-ink">{value}</div>
    </div>
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function IncidentsTab() {
  const { data, unavailable } = useIncidents();
  if (unavailable)
    return (
      <Unavailable
        endpoint="/incidents"
        resource="Incident[] { severity, status, title, detail, recovery }"
      />
    );
  const rows = data ?? [];
  return (
    <Panel title={`${rows.length} incident${rows.length === 1 ? "" : "s"}`} bodyClassName="p-0">
      {rows.length === 0 ? (
        <div className="px-4 py-14 text-center text-[13px] text-ink-secondary">
          No incidents recorded.
        </div>
      ) : (
        <ul className="divide-y divide-border">
          {rows.map((i) => (
            <li key={i.id} className="px-4 py-3 flex items-start gap-3">
              <StatDot
                tone={
                  i.severity === "critical"
                    ? "error"
                    : i.severity === "warning"
                      ? "attention"
                      : "info"
                }
              />
              <div className="min-w-0 flex-1">
                <div className="text-[13.5px] text-ink font-medium">{i.title}</div>
                <div className="text-[12.5px] text-ink-secondary mt-0.5">{i.detail}</div>
                {i.recovery && (
                  <div className="rift-mono text-[11.5px] mt-1.5 text-secondary">
                    recovery: {i.recovery.automatic ? "auto — " : ""}
                    {i.recovery.action}
                  </div>
                )}
              </div>
              <div className="rift-mono text-[11px] text-ink-secondary shrink-0 text-right">
                <div>{i.status}</div>
                <div>{relativeTime(i.openedAt)}</div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
