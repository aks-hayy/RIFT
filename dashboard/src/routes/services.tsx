import { createFileRoute } from "@tanstack/react-router";
import { HeartPulse, RotateCcw, Square } from "lucide-react";

import { ConfirmAction, ErrorState, JsonPreview, LoadingState } from "@/components/console/live";
import { Chip, KV, PageHeader, Panel } from "@/components/console/primitives";
import { riftKeys, useRiftMutation, useRiftQuery } from "@/hooks/use-rift";
import { dateTime, statusTone } from "@/lib/rift-api";

export const Route = createFileRoute("/services")({ component: ServicesPage });

function ServicesPage() {
  const services = useRiftQuery<any>(riftKeys.services, "/api/rift/services", {
    refetchInterval: 5_000,
  });
  const backends = useRiftQuery<any>(riftKeys.backends, "/api/rift/backends", {
    refetchInterval: 30_000,
  });
  const monitor = useRiftMutation<any>("/api/rift/monitor", [
    riftKeys.services,
    riftKeys.observability,
  ]);
  const recover = useRiftMutation<any>("/api/rift/recover", [
    riftKeys.services,
    riftKeys.incidents,
  ]);
  const destroy = useRiftMutation<any>("/api/rift/destroy", [riftKeys.services, riftKeys.state]);

  if (services.isPending || backends.isPending)
    return <LoadingState label="Reading managed services" />;
  const error = services.error || backends.error;
  if (error) return <ErrorState error={error} onRetry={() => void services.refetch()} />;
  const entries = Object.entries<any>(services.data ?? {});

  return (
    <div>
      <PageHeader
        title="Services"
        subtitle="Desired and observed runtime state, endpoint health, provider gates, and bounded recovery controls."
        command="rift status"
        actions={
          <button
            type="button"
            onClick={() => monitor.mutate({ iterations: 1, allow_recovery: false })}
            className="inline-flex h-8 items-center gap-2 rounded-sm border border-border px-3 text-xs hover:bg-surface"
          >
            <HeartPulse className="h-3.5 w-3.5" /> Probe all
          </button>
        }
      />
      <div className="space-y-3 p-4">
        {(monitor.error || recover.error || destroy.error) && (
          <ErrorState error={monitor.error || recover.error || destroy.error} />
        )}
        <Panel title="Managed services" padded={false}>
          {entries.length === 0 ? (
            <div className="p-8 text-center text-sm text-muted-foreground">
              No service state exists. Apply a deployment first.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-border bg-surface text-[10px] uppercase tracking-widest text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2">Service</th>
                    <th>Model / backend</th>
                    <th>PID</th>
                    <th>Endpoint</th>
                    <th>Observed</th>
                    <th className="text-right pr-3">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map(([name, service]) => {
                    const observation = service.observation ?? {};
                    return (
                      <tr key={name} className="border-b border-border/60 align-top last:border-0">
                        <td className="px-3 py-3 mono font-semibold">{name}</td>
                        <td className="py-3">
                          <div>{service.model?.id ?? "--"}</div>
                          <div className="text-muted-foreground">{service.backend}</div>
                        </td>
                        <td className="py-3 mono">{service.runtime?.pid ?? "--"}</td>
                        <td className="py-3 mono">
                          {observation.api_base ?? service.runtime?.api_base ?? "--"}
                        </td>
                        <td className="py-3">
                          <Chip tone={statusTone(observation.phase ?? service.status)}>
                            {observation.phase ?? service.status ?? "unknown"}
                          </Chip>
                          <div className="mt-1 text-[10px] text-muted-foreground">
                            {dateTime(observation.observed_unix_seconds)}
                          </div>
                        </td>
                        <td className="py-3 pr-3">
                          <div className="flex justify-end gap-2">
                            <ConfirmAction
                              label="Recover"
                              title={`Recover ${name}?`}
                              description="RIFT will use the last-known-good launch plan and the configured restart budget."
                              onConfirm={() =>
                                recover.mutate({ service: name, allow_launch: true, force: true })
                              }
                              pending={recover.isPending}
                              icon={<RotateCcw className="h-3.5 w-3.5" />}
                            />
                            <ConfirmAction
                              label="Stop"
                              title={`Stop ${name}?`}
                              description="The backend process will stop. Model files remain intact."
                              onConfirm={() => destroy.mutate({ service: name })}
                              pending={destroy.isPending}
                              destructive
                              icon={<Square className="h-3.5 w-3.5" />}
                            />
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title="Provider lifecycle gates" padded={false}>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-border bg-surface text-[10px] uppercase tracking-widest text-muted-foreground">
                <tr>
                  <th className="px-3 py-2">Backend</th>
                  <th>Detected</th>
                  <th>Contract</th>
                  <th>Advertised status</th>
                  <th>Formats</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries<any>(backends.data?.providers ?? {}).map(([name, provider]) => {
                  const gate = provider.lifecycle_gate ?? {};
                  return (
                    <tr key={name} className="border-b border-border/60 last:border-0">
                      <td className="px-3 py-2 mono">{name}</td>
                      <td>
                        <Chip tone={provider.detection?.available ? "ok" : "warn"}>
                          {provider.detection?.available ? "available" : "not detected"}
                        </Chip>
                      </td>
                      <td>
                        <Chip tone={gate.gate_passed ? "ok" : "err"}>
                          {gate.gate_passed ? "complete" : "incomplete"}
                        </Chip>
                      </td>
                      <td>{gate.advertised_status ?? "experimental"}</td>
                      <td className="mono">{(gate.capabilities?.formats ?? []).join(", ")}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>

        {entries.map(([name, service]) => (
          <Panel key={name} title={`Runtime detail / ${name}`}>
            <div className="grid gap-x-8 md:grid-cols-2">
              <div>
                <KV k="Desired state" v={service.desired_state ?? "unknown"} />
                <KV
                  k="Context"
                  v={service.serving?.context_length ?? service.launch_plan?.context_length ?? "--"}
                />
                <KV k="Concurrency" v={service.serving?.concurrency ?? "--"} />
              </div>
              <div>
                <KV k="Restarts" v={service.supervisor?.restart_count ?? 0} />
                <KV k="Last healthy" v={dateTime(service.supervisor?.last_healthy_unix_seconds)} />
                <KV
                  k="Last known good"
                  v={service.last_known_good_launch_plan ? "recorded" : "not recorded"}
                />
              </div>
            </div>
            <details className="mt-3">
              <summary className="cursor-pointer mono text-xs text-muted-foreground">
                Raw service state
              </summary>
              <JsonPreview value={service} className="mt-2" />
            </details>
          </Panel>
        ))}
      </div>
    </div>
  );
}
