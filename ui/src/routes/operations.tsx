import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { z } from "zod";
import { AppShell } from "@/components/rift/app-shell";
import { PageHeader, Panel, StatDot, SourceBadge } from "@/components/rift/primitives";
import { Unavailable } from "@/components/rift/unavailable";
import { useIncidents, useLatestPlan, useLogs, useReports, useTimeline } from "@/lib/rift/hooks";
import { relativeTime } from "@/lib/rift/format";
import { cn } from "@/lib/utils";

const searchSchema = z.object({
  tab: z.enum(["incidents", "rollouts", "audit", "logs", "metrics"]).catch("incidents"),
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

      <div className="max-w-[1400px] mx-auto px-4 py-6 grid gap-4">
        {tab === "incidents" && <IncidentsTab />}
        {tab === "rollouts" && <RolloutsTab />}
        {tab === "audit" && <AuditTab />}
        {tab === "logs" && <LogsTab />}
        {tab === "metrics" && <MetricsTab />}
      </div>
    </AppShell>
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
        endpoint="/v1/incidents"
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
