import { createFileRoute } from "@tanstack/react-router";
import { FileSearch, RefreshCw } from "lucide-react";
import { useState } from "react";

import { ErrorState, JsonPreview, LoadingState, ResultBanner } from "@/components/console/live";
import { Chip, KV, Metric, PageHeader, Panel } from "@/components/console/primitives";
import { riftKeys, useRiftMutation, useRiftQuery } from "@/hooks/use-rift";
import { statusTone } from "@/lib/rift-api";

export const Route = createFileRoute("/plan")({ component: PlanPage });

function PlanPage() {
  const [config, setConfig] = useState(".rift/generated/rift.generated.yaml");
  const latest = useRiftQuery<any>(riftKeys.plan, "/api/rift/plan");
  const generated = useRiftQuery<any>(["rift", "generated"], "/api/rift/generated-config");
  const planMutation = useRiftMutation<any>("/api/rift/plan", [riftKeys.plan]);
  const plan = planMutation.data ?? latest.data;

  if (latest.isPending && !planMutation.data)
    return <LoadingState label="Reading latest deployment plan" />;
  if (latest.error && !planMutation.data)
    return <ErrorState error={latest.error} onRetry={() => void latest.refetch()} />;

  const actions = plan?.actions ?? [];
  const services = Object.entries<any>(plan?.services ?? {});
  const errors = actions.filter((action: any) => action.kind === "error");

  return (
    <div>
      <PageHeader
        title="Plan"
        subtitle="Read-only desired-state evaluation. Downloads, installs, launches, and remote actions are never executed here."
        command={`rift plan --config ${config}`}
      />
      <div className="space-y-3 p-4">
        <Panel title="Plan source">
          <div className="flex flex-wrap items-end gap-3">
            <label className="min-w-72 flex-1 text-xs text-muted-foreground">
              Config path
              <input
                value={config}
                onChange={(event) => setConfig(event.target.value)}
                className="mt-1 h-9 w-full rounded-sm border border-input bg-background px-3 mono text-xs text-foreground"
              />
            </label>
            <button
              type="button"
              onClick={() => planMutation.mutate({ config })}
              disabled={planMutation.isPending}
              className="inline-flex h-9 items-center gap-2 rounded-sm border border-primary/50 px-4 text-xs text-primary hover:bg-primary/10 disabled:opacity-50"
            >
              <FileSearch className="h-3.5 w-3.5" />{" "}
              {planMutation.isPending ? "Planning" : "Create plan"}
            </button>
            <button
              type="button"
              onClick={() => void latest.refetch()}
              className="inline-flex h-9 items-center gap-2 rounded-sm border border-border px-3 text-xs hover:bg-surface"
            >
              <RefreshCw className="h-3.5 w-3.5" /> Refresh
            </button>
          </div>
          {generated.data?.path && (
            <p className="mt-2 text-xs text-muted-foreground">
              Generated config: <span className="mono">{generated.data.path}</span>
            </p>
          )}
        </Panel>
        {planMutation.error && <ErrorState error={planMutation.error} />}
        <ResultBanner result={planMutation.data} />

        <div className="grid gap-3 lg:grid-cols-4">
          <Panel>
            <Metric label="Services" value={services.length} />
          </Panel>
          <Panel>
            <Metric label="Actions" value={actions.length} tone="info" />
          </Panel>
          <Panel>
            <Metric
              label="Blocking errors"
              value={errors.length}
              tone={errors.length ? "err" : "ok"}
            />
          </Panel>
          <Panel>
            <Metric
              label="Drift"
              value={(plan?.drift ?? []).length}
              tone={(plan?.drift ?? []).length ? "warn" : "ok"}
            />
          </Panel>
        </div>

        <Panel title="Planned actions" padded={false}>
          {actions.length === 0 ? (
            <div className="p-6 text-sm text-muted-foreground">No actions in the latest plan.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-border bg-surface text-[10px] uppercase tracking-widest text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2">Kind</th>
                    <th>Service</th>
                    <th>Intent</th>
                    <th>Permission</th>
                  </tr>
                </thead>
                <tbody>
                  {actions.map((action: any, index: number) => (
                    <tr
                      key={`${action.kind}-${index}`}
                      className="border-b border-border/60 last:border-0"
                    >
                      <td className="px-3 py-2">
                        <Chip
                          tone={statusTone(
                            action.kind === "error"
                              ? "error"
                              : action.kind === "launch"
                                ? "info"
                                : "warning",
                          )}
                        >
                          {action.kind}
                        </Chip>
                      </td>
                      <td className="mono">{action.service}</td>
                      <td>{action.message}</td>
                      <td className="mono">{action.permission ?? "none"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <div className="grid gap-3 xl:grid-cols-2">
          {services.map(([name, service]) => (
            <Panel key={name} title={`Service / ${name}`}>
              <KV k="Backend" v={service.backend ?? "--"} />
              <KV k="Model" v={service.model?.id ?? "--"} />
              <KV k="Node" v={service.placement?.node ?? "local"} />
              <KV k="Endpoint" v={service.launch_plan?.api_base ?? "--"} />
              <KV
                k="Governance"
                v={
                  <Chip tone={service.governance?.allowed === false ? "err" : "ok"}>
                    {service.governance?.allowed === false ? "blocked" : "allowed"}
                  </Chip>
                }
              />
              {(service.decision?.reason ?? []).map((reason: string) => (
                <p key={reason} className="mt-2 text-xs text-muted-foreground">
                  {reason}
                </p>
              ))}
            </Panel>
          ))}
        </div>

        {plan && (
          <Panel title="Raw plan">
            <JsonPreview value={plan} />
          </Panel>
        )}
      </div>
    </div>
  );
}
