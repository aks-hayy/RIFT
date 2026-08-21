import { createFileRoute } from "@tanstack/react-router";
import { Activity, RefreshCw, ScanSearch } from "lucide-react";

import { ErrorState, LoadingState } from "@/components/console/live";
import { Chip, Metric, PageHeader, Panel } from "@/components/console/primitives";
import { riftKeys, useRiftMutation, useRiftQuery } from "@/hooks/use-rift";
import { dateTime, statusTone } from "@/lib/rift-api";

export const Route = createFileRoute("/")({ component: OverviewPage });

function OverviewPage() {
  const status = useRiftQuery<any>(riftKeys.status, "/api/rift/status", { refetchInterval: 5_000 });
  const services = useRiftQuery<any>(riftKeys.services, "/api/rift/services", {
    refetchInterval: 5_000,
  });
  const operations = useRiftQuery<any>(riftKeys.observability, "/api/rift/observability", {
    refetchInterval: 10_000,
  });
  const discover = useRiftMutation("/api/rift/discover", [riftKeys.discovery, riftKeys.hardware]);
  const monitor = useRiftMutation("/api/rift/monitor", [riftKeys.services, riftKeys.observability]);

  if (status.isPending || services.isPending || operations.isPending) return <LoadingState />;
  const error = status.error || services.error || operations.error;
  if (error) return <ErrorState error={error} onRetry={() => void status.refetch()} />;

  const serviceEntries = Object.entries<any>(services.data ?? {});
  const snapshot = operations.data?.snapshot ?? {};
  const timeline = operations.data?.timeline?.events ?? [];
  const healthy = serviceEntries.filter(([, service]) => {
    const observation = service.observation ?? {};
    return observation.healthy === true || observation.phase === "healthy";
  }).length;
  const incidentCount = Number(snapshot.incident_count ?? 0);

  return (
    <div>
      <PageHeader
        title="Overview"
        subtitle="Desired state, observed health, gateway load, and recent control-plane activity."
        command="rift status"
        actions={
          <>
            <button
              type="button"
              onClick={() => discover.mutate({ local: true })}
              disabled={discover.isPending}
              className="inline-flex h-8 items-center gap-2 rounded-sm border border-border px-3 text-xs hover:bg-surface disabled:opacity-50"
            >
              <ScanSearch className="h-3.5 w-3.5" /> Discover
            </button>
            <button
              type="button"
              onClick={() => monitor.mutate({ iterations: 1, allow_recovery: false })}
              disabled={monitor.isPending}
              className="inline-flex h-8 items-center gap-2 rounded-sm border border-primary/50 px-3 text-xs text-primary hover:bg-primary/10 disabled:opacity-50"
            >
              <RefreshCw className="h-3.5 w-3.5" /> Reconcile
            </button>
          </>
        }
      />

      <div className="grid gap-3 p-4 lg:grid-cols-4">
        <Panel>
          <Metric label="Managed services" value={serviceEntries.length} tone="info" />
        </Panel>
        <Panel>
          <Metric
            label="Healthy"
            value={healthy}
            tone={healthy === serviceEntries.length ? "ok" : "warn"}
          />
        </Panel>
        <Panel>
          <Metric label="Incidents" value={incidentCount} tone={incidentCount ? "warn" : "ok"} />
        </Panel>
        <Panel>
          <Metric
            label="Gateway requests"
            value={snapshot.gateway?.requests_total ?? 0}
            hint={`${snapshot.gateway?.requests_failed ?? 0} failed`}
          />
        </Panel>
      </div>

      <div className="grid gap-3 px-4 pb-4 xl:grid-cols-[1.4fr_1fr]">
        <Panel title="Services" padded={false}>
          {serviceEntries.length === 0 ? (
            <div className="p-6 text-center text-sm text-muted-foreground">
              No services are managed yet. Generate and apply a plan to begin.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-border bg-surface text-[10px] uppercase tracking-widest text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2">Service</th>
                    <th>Backend</th>
                    <th>Model</th>
                    <th>Endpoint</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {serviceEntries.map(([name, service]) => {
                    const observation = service.observation ?? {};
                    return (
                      <tr key={name} className="border-b border-border/60 last:border-0">
                        <td className="px-3 py-2 mono text-foreground">{name}</td>
                        <td>{service.backend ?? "--"}</td>
                        <td className="max-w-56 truncate" title={service.model?.id}>
                          {service.model?.id ?? "--"}
                        </td>
                        <td className="mono">
                          {observation.api_base ?? service.runtime?.api_base ?? "--"}
                        </td>
                        <td>
                          <Chip tone={statusTone(observation.phase ?? service.status)}>
                            {observation.phase ?? service.status ?? "unknown"}
                          </Chip>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title="Operation timeline" scroll className="min-h-72">
          {timeline.length === 0 ? (
            <div className="text-sm text-muted-foreground">No operation events recorded yet.</div>
          ) : (
            <div className="space-y-3">
              {[...timeline]
                .reverse()
                .slice(0, 12)
                .map((event: any, index: number) => (
                  <div
                    key={`${event.created_unix_seconds}-${index}`}
                    className="flex gap-2 border-b border-border/50 pb-2 last:border-0"
                  >
                    <Activity className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
                    <div className="min-w-0">
                      <div className="mono text-xs text-foreground">{event.event}</div>
                      <div className="text-[11px] text-muted-foreground">
                        {dateTime(event.created_unix_seconds)}
                        {event.service ? ` / ${event.service}` : ""}
                      </div>
                    </div>
                  </div>
                ))}
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
