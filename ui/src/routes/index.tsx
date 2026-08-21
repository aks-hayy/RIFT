import { createFileRoute, Link } from "@tanstack/react-router";
import { AppShell } from "@/components/rift/app-shell";
import { PageHeader, Panel, StatDot, KV, SourceBadge } from "@/components/rift/primitives";
import { Unavailable } from "@/components/rift/unavailable";
import { useHealth, useServices, useNodes, useIncidents, useTimeline } from "@/lib/rift/hooks";
import { rift } from "@/lib/rift/client";
import { bytes, pct, relativeTime } from "@/lib/rift/format";
import { Plus, ArrowRight, Rocket } from "lucide-react";
import type { Service, Incident } from "@/lib/rift/types";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Home — RIFT" },
      {
        name: "description",
        content:
          "Fleet health, running models, node readiness, incidents, and recent changes at a glance.",
      },
      { property: "og:title", content: "Home — RIFT" },
      {
        property: "og:description",
        content: "Operational overview of your RIFT fleet.",
      },
    ],
  }),
  component: HomePage,
});

function HomePage() {
  if (!rift.isConfigured()) return <FirstRunGate />;
  return (
    <AppShell>
      <PageHeader
        eyebrow="Overview"
        title="Fleet"
        description="What's running, where, how it's performing, and what needs attention."
        actions={
          <Link
            to="/setup"
            className="inline-flex items-center gap-2 h-9 px-3.5 rounded-[4px] bg-primary text-primary-foreground text-[13px] font-medium hover:bg-[color:var(--oxide-deep)]"
          >
            <Plus className="size-4" aria-hidden />
            Deploy a model
          </Link>
        }
      />
      <div className="max-w-[1400px] mx-auto px-4 py-6 grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2 grid gap-4">
          <HealthPanel />
          <ServicesPanel />
        </div>
        <div className="grid gap-4">
          <IncidentsPanel />
          <NodesPanel />
          <RecentChangesPanel />
        </div>
      </div>
    </AppShell>
  );
}

function FirstRunGate() {
  return (
    <AppShell>
      <div className="max-w-[1400px] mx-auto px-4 py-12">
        <div className="rift-panel p-8 max-w-2xl">
          <div className="rift-label mb-3">First run</div>
          <h1 className="text-[24px] font-medium text-ink">Set up RIFT</h1>
          <p className="mt-2 text-[13px] text-ink-secondary max-w-lg">
            RIFT hasn't been connected to a controller yet. Start the guided setup to run on this
            computer or manage a cluster of nodes.
          </p>
          <div className="mt-5">
            <Link
              to="/setup"
              className="inline-flex items-center gap-2 h-10 px-4 rounded-[4px] bg-primary text-primary-foreground text-[13px] font-medium hover:bg-[color:var(--oxide-deep)]"
            >
              <Rocket className="size-4" aria-hidden />
              Start guided setup
            </Link>
          </div>
          <div className="mt-8 rift-ticks" aria-hidden />
          <p className="mt-4 text-[12px] rift-mono text-ink-secondary">
            Controller URL is configured via{" "}
            <span className="text-ink">VITE_RIFT_CONTROLLER_URL</span>. The controller binds to
            127.0.0.1 by default.
          </p>
        </div>
      </div>
    </AppShell>
  );
}

function HealthPanel() {
  const { data, unavailable, isLoading } = useHealth();
  if (unavailable)
    return (
      <Unavailable
        endpoint="/v1/health"
        resource="FleetHealth { nodesReady, servicesRunning, incidentsOpen, capacity }"
        hint="Emit `health` events on /v1/events to keep this panel live."
      />
    );
  if (isLoading || !data)
    return (
      <Panel title="Health">
        <div className="text-[13px] text-ink-secondary">Loading…</div>
      </Panel>
    );

  const nodesOk = data.nodesReady === data.nodesTotal;
  const svcsOk = data.servicesRunning === data.servicesTotal;
  const anyIncidents = data.incidentsOpen > 0;
  const overall = anyIncidents ? "error" : nodesOk && svcsOk ? "ok" : "attention";

  return (
    <Panel
      title="Fleet health"
      aside={
        <div className="flex items-center gap-2">
          <SourceBadge source={data.provenance} />
          <span className="hidden sm:inline rift-mono text-[11px] text-ink-secondary">
            controller {data.controllerVersion}
          </span>
        </div>
      }
    >
      <div className="flex items-center gap-3 mb-4">
        <StatDot tone={overall as "ok" | "attention" | "error"} />
        <span className="text-[15px] text-ink font-medium">
          {overall === "ok"
            ? "All systems nominal"
            : overall === "attention"
              ? "Attention required"
              : "Incidents open"}
        </span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-6">
        <KV label="Nodes ready" value={`${data.nodesReady} / ${data.nodesTotal}`} />
        <KV label="Services running" value={`${data.servicesRunning} / ${data.servicesTotal}`} />
        <KV label="Open incidents" value={data.incidentsOpen} />
        <KV label="Updated" value={relativeTime(data.updatedAt)} />
      </div>
      <div className="mt-6 grid sm:grid-cols-2 gap-4">
        <CapacityBar
          label="VRAM"
          used={data.capacity.vramUsedBytes}
          total={data.capacity.vramTotalBytes}
        />
        <CapacityBar
          label="RAM"
          used={data.capacity.ramUsedBytes}
          total={data.capacity.ramTotalBytes}
        />
      </div>
    </Panel>
  );
}

function CapacityBar({ label, used, total }: { label: string; used: number; total: number }) {
  const p = pct(used, total);
  const tone = p > 90 ? "var(--error)" : p > 75 ? "var(--saffron)" : "var(--verdigris)";
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="rift-label">{label}</span>
        <span className="rift-mono text-[12px] text-ink">
          {bytes(used)} / {bytes(total)}
        </span>
      </div>
      <div className="h-1.5 bg-muted rounded-[2px] overflow-hidden">
        <div className="h-full" style={{ width: `${p}%`, background: tone }} />
      </div>
    </div>
  );
}

function ServicesPanel() {
  const { data, unavailable, isLoading } = useServices();
  if (unavailable)
    return (
      <Unavailable
        endpoint="/v1/services"
        resource="Service[] { id, name, status, artifactId, endpoint, assignments }"
      />
    );
  if (isLoading || !data) {
    return (
      <Panel title="Running models">
        <div className="text-[13px] text-ink-secondary">Loading services...</div>
      </Panel>
    );
  }
  const services = data;
  return (
    <Panel
      title="Running models"
      aside={
        <Link
          to="/deployments"
          className="text-[12px] text-primary inline-flex items-center gap-1 hover:underline"
        >
          All deployments <ArrowRight className="size-3" aria-hidden />
        </Link>
      }
      bodyClassName="p-0"
    >
      {services.length === 0 ? (
        <div className="px-4 py-10 text-center">
          <p className="text-[13px] text-ink-secondary">No services deployed yet.</p>
          <Link
            to="/setup"
            className="mt-3 inline-flex items-center gap-2 h-9 px-3.5 rounded-[4px] bg-primary text-primary-foreground text-[13px] font-medium hover:bg-[color:var(--oxide-deep)]"
          >
            <Plus className="size-4" aria-hidden /> Deploy a model
          </Link>
        </div>
      ) : (
        <table className="w-full text-[13px]">
          <thead className="rift-label">
            <tr className="border-b border-border">
              <th className="text-left px-4 h-9 font-normal">Service</th>
              <th className="text-left px-4 font-normal">Status</th>
              <th className="text-left px-4 font-normal">Nodes</th>
              <th className="text-left px-4 font-normal">Endpoint</th>
            </tr>
          </thead>
          <tbody>
            {services.map((s) => (
              <ServiceRow key={s.id} s={s} />
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}

function ServiceRow({ s }: { s: Service }) {
  const tone: Parameters<typeof StatDot>[0]["tone"] =
    s.status === "running"
      ? "ok"
      : s.status === "degraded"
        ? "attention"
        : s.status === "failed"
          ? "error"
          : "info";
  return (
    <tr className="border-b border-border last:border-0 hover:bg-muted/50">
      <td className="px-4 py-2.5">
        <Link
          to="/deployments/$id"
          params={{ id: s.id }}
          className="text-ink hover:underline font-medium"
        >
          {s.name}
        </Link>
      </td>
      <td className="px-4">
        <span className="inline-flex items-center gap-2">
          <StatDot tone={tone} /> <span className="rift-mono text-[12px]">{s.status}</span>
        </span>
      </td>
      <td className="px-4 rift-mono text-[12px]">{s.assignments.length}</td>
      <td className="px-4 rift-mono text-[12px] text-ink-secondary">
        {s.endpoint.scheme}://{s.endpoint.bindAddress}:{s.endpoint.port}
        {s.endpoint.path}
      </td>
    </tr>
  );
}

function IncidentsPanel() {
  const { data, unavailable, isLoading } = useIncidents();
  if (unavailable)
    return (
      <Unavailable
        endpoint="/v1/incidents"
        resource="Incident[] { severity, status, title, nodeId?, serviceId? }"
      />
    );
  if (isLoading || !data) {
    return (
      <Panel title="Active incidents">
        <div className="text-[13px] text-ink-secondary">Loading incidents...</div>
      </Panel>
    );
  }
  const open = data.filter((i: Incident) => i.status !== "resolved");
  return (
    <Panel title="Active incidents">
      {open.length === 0 ? (
        <div className="text-[13px] text-ink-secondary flex items-center gap-2">
          <StatDot tone="ok" /> No open incidents.
        </div>
      ) : (
        <ul className="grid gap-2">
          {open.slice(0, 5).map((i) => (
            <li key={i.id} className="flex items-start gap-2">
              <StatDot
                tone={
                  i.severity === "critical"
                    ? "error"
                    : i.severity === "warning"
                      ? "attention"
                      : "info"
                }
              />
              <div className="min-w-0">
                <div className="text-[13px] text-ink truncate">{i.title}</div>
                <div className="text-[11.5px] rift-mono text-ink-secondary">
                  {relativeTime(i.openedAt)}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function NodesPanel() {
  const { data, unavailable, isLoading } = useNodes();
  if (unavailable)
    return (
      <Unavailable
        endpoint="/v1/nodes"
        resource="RiftNode[] { hostname, status, accelerators[] }"
      />
    );
  if (isLoading || !data) {
    return (
      <Panel title="Nodes">
        <div className="text-[13px] text-ink-secondary">Loading nodes...</div>
      </Panel>
    );
  }
  const nodes = data;
  return (
    <Panel
      title="Nodes"
      aside={
        <Link
          to="/nodes"
          className="text-[12px] text-primary hover:underline inline-flex items-center gap-1"
        >
          All <ArrowRight className="size-3" aria-hidden />
        </Link>
      }
    >
      {nodes.length === 0 ? (
        <div className="text-[13px] text-ink-secondary">No nodes enrolled.</div>
      ) : (
        <ul className="grid gap-1.5 text-[13px]">
          {nodes.slice(0, 6).map((n) => (
            <li key={n.id} className="flex items-center gap-2">
              <StatDot
                tone={
                  n.status === "ready"
                    ? "ok"
                    : n.status === "offline" || n.status === "error"
                      ? "error"
                      : "attention"
                }
              />
              <Link to="/nodes/$id" params={{ id: n.id }} className="hover:underline">
                {n.hostname}
              </Link>
              <span className="ml-auto rift-mono text-[11.5px] text-ink-secondary">
                {n.accelerators.length} GPU · {bytes(n.ramBytes)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function RecentChangesPanel() {
  const { data, unavailable, isLoading } = useTimeline();
  if (unavailable) {
    return (
      <Panel title="Recent changes">
        <Unavailable
          endpoint="/timeline"
          resource="Controller timeline events"
          reason="The controller timeline is unavailable."
        />
      </Panel>
    );
  }
  const events = Array.isArray(data?.events) ? data.events : [];
  return (
    <Panel title="Recent changes" aside={<SourceBadge source="live" />}>
      {isLoading ? (
        <p className="text-[13px] text-ink-secondary">Loading timeline...</p>
      ) : events.length === 0 ? (
        <p className="text-[13px] text-ink-secondary">No controller events recorded.</p>
      ) : (
        <ol className="grid gap-3">
          {events.slice(0, 6).map((value, index) => {
            const event =
              value && typeof value === "object" ? (value as Record<string, unknown>) : {};
            const created = Number(event.created_unix_seconds ?? 0);
            return (
              <li
                key={`${String(event.event)}-${created}-${index}`}
                className="flex items-start gap-2"
              >
                <StatDot tone={String(event.status) === "error" ? "error" : "info"} />
                <div className="min-w-0">
                  <div className="text-[12.5px] text-ink truncate">
                    {String(event.event ?? "controller event").replaceAll("_", " ")}
                  </div>
                  <div className="rift-mono text-[10.5px] text-ink-secondary">
                    {event.service ? `${String(event.service)} · ` : ""}
                    {created
                      ? relativeTime(new Date(created * 1000).toISOString())
                      : "time unavailable"}
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </Panel>
  );
}
