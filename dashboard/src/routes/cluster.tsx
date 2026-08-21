import { createFileRoute } from "@tanstack/react-router";
import { Network, Play, RefreshCw, ShieldAlert } from "lucide-react";
import { useState } from "react";

import {
  ConfirmAction,
  ErrorState,
  JsonPreview,
  LoadingState,
  ResultBanner,
} from "@/components/console/live";
import { Chip, Metric, PageHeader, Panel } from "@/components/console/primitives";
import { riftKeys, useRiftMutation, useRiftQuery } from "@/hooks/use-rift";
import { bytes, statusTone } from "@/lib/rift-api";

export const Route = createFileRoute("/cluster")({ component: ClusterPage });

function ClusterPage() {
  const [config, setConfig] = useState("cluster.yaml");
  const cluster = useRiftQuery<any>(riftKeys.cluster, "/api/rift/cluster/status", {
    refetchInterval: 5_000,
  });
  const discover = useRiftMutation<any>("/api/rift/cluster/discover", [riftKeys.cluster]);
  const plan = useRiftMutation<any>("/api/rift/cluster/plan", [riftKeys.cluster]);
  const apply = useRiftMutation<any>("/api/rift/cluster/apply", [riftKeys.cluster]);
  const recover = useRiftMutation<any>("/api/rift/cluster/recover", [
    riftKeys.cluster,
    riftKeys.incidents,
  ]);
  const fault = useRiftMutation<any>("/api/rift/cluster/fault", [riftKeys.cluster]);
  const rollout = useRiftMutation<any>("/api/rift/cluster/rollout/plan", [riftKeys.cluster]);

  if (cluster.isPending) return <LoadingState label="Reading cluster state" />;
  if (cluster.error)
    return <ErrorState error={cluster.error} onRetry={() => void cluster.refetch()} />;
  const data = cluster.data ?? {};
  const nodes = data.nodes ?? [];
  const instances = data.instances ?? [];
  const summary = data.summary ?? {};
  const operation =
    discover.data ?? plan.data ?? apply.data ?? recover.data ?? fault.data ?? rollout.data;
  const mutationError =
    discover.error || plan.error || apply.error || recover.error || fault.error || rollout.error;

  return (
    <div>
      <PageHeader
        title="Cluster"
        subtitle="Explainable placement, hard reservations, permissioned remote discovery, failover, and safe rollout planning."
        command={`rift cluster status --cluster ${config}`}
      />
      <div className="space-y-3 p-4">
        <Panel title="Cluster controls">
          <div className="flex flex-wrap items-end gap-3">
            <label className="min-w-64 flex-1 text-xs text-muted-foreground">
              Cluster config
              <input
                value={config}
                onChange={(event) => setConfig(event.target.value)}
                className="mt-1 h-9 w-full rounded-sm border border-input bg-background px-3 mono text-xs text-foreground"
              />
            </label>
            <button
              type="button"
              onClick={() => discover.mutate({ cluster: config, allow_remote: false })}
              className="inline-flex h-9 items-center gap-2 rounded-sm border border-border px-3 text-xs hover:bg-surface"
            >
              <Network className="h-3.5 w-3.5" /> Discover
            </button>
            <button
              type="button"
              onClick={() => plan.mutate({ cluster: config })}
              className="inline-flex h-9 items-center gap-2 rounded-sm border border-primary/50 px-3 text-xs text-primary hover:bg-primary/10"
            >
              <Play className="h-3.5 w-3.5" /> Plan
            </button>
            <ConfirmAction
              label="Apply cluster"
              title="Apply cluster deployment?"
              description="This authorizes deployment actions in the configured cluster. Remote execution still requires its explicit permission and configured transport."
              onConfirm={() => apply.mutate({ cluster: config, allow_launch: true })}
              pending={apply.isPending}
            />
            <ConfirmAction
              label="Recover"
              title="Recover failed cluster instances?"
              description="RIFT will restart or reschedule only when capacity and recovery policy permit it."
              onConfirm={() => recover.mutate({ cluster: config, allow_recovery: true })}
              pending={recover.isPending}
              icon={<RefreshCw className="h-3.5 w-3.5" />}
            />
          </div>
        </Panel>
        {mutationError && <ErrorState error={mutationError} />}
        <ResultBanner result={operation} />

        <div className="grid gap-3 lg:grid-cols-4">
          <Panel>
            <Metric label="Nodes" value={summary.node_count ?? nodes.length} />
          </Panel>
          <Panel>
            <Metric label="Instances" value={summary.instance_count ?? instances.length} />
          </Panel>
          <Panel>
            <Metric
              label="Incidents"
              value={summary.incident_count ?? 0}
              tone={summary.incident_count ? "warn" : "ok"}
            />
          </Panel>
          <Panel>
            <Metric
              label="Mode"
              value={data.mode ?? "not applied"}
              tone={data.mode === "emulated" ? "warn" : "info"}
              hint={data.mode === "emulated" ? "not a physical benchmark" : "remote state"}
            />
          </Panel>
        </div>

        <Panel title="Nodes" padded={false}>
          {nodes.length === 0 ? (
            <div className="p-6 text-sm text-muted-foreground">
              No cluster state. Discover or apply a cluster configuration.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-border bg-surface text-[10px] uppercase tracking-widest text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2">Node</th>
                    <th>Transport</th>
                    <th>VRAM</th>
                    <th>RAM</th>
                    <th>Backends</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {nodes.map((node: any) => (
                    <tr key={node.name} className="border-b border-border/60 last:border-0">
                      <td className="px-3 py-2 mono">{node.name}</td>
                      <td>{node.transport ?? data.mode}</td>
                      <td>{bytes(node.hardware?.total_vram_bytes)}</td>
                      <td>{bytes(node.hardware?.total_host_ram_bytes)}</td>
                      <td>{(node.backends ?? []).join(", ") || "--"}</td>
                      <td>
                        <Chip
                          tone={statusTone(node.status ?? (node.ready ? "ready" : "unhealthy"))}
                        >
                          {node.status ?? (node.ready ? "ready" : "not ready")}
                        </Chip>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title="Instances and recovery" padded={false}>
          {instances.length === 0 ? (
            <div className="p-6 text-sm text-muted-foreground">No instances deployed.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-border bg-surface text-[10px] uppercase tracking-widest text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2">Instance</th>
                    <th>Node</th>
                    <th>Backend</th>
                    <th>Generation</th>
                    <th>Phase</th>
                    <th className="text-right pr-3">Fault test</th>
                  </tr>
                </thead>
                <tbody>
                  {instances.map((instance: any) => (
                    <tr
                      key={instance.instance_id}
                      className="border-b border-border/60 last:border-0"
                    >
                      <td className="px-3 py-2 mono">{instance.instance_id}</td>
                      <td>{instance.node}</td>
                      <td>{instance.backend}</td>
                      <td className="mono">{instance.generation ?? 1}</td>
                      <td>
                        <Chip tone={statusTone(instance.phase)}>{instance.phase}</Chip>
                      </td>
                      <td className="pr-3 text-right">
                        <ConfirmAction
                          label="Inject crash"
                          title={`Inject a test crash into ${instance.instance_id}?`}
                          description="This changes only RIFT cluster state in emulated mode. On real nodes, fault injection must be separately implemented and authorized."
                          onConfirm={() =>
                            fault.mutate({
                              cluster: config,
                              instance: instance.instance_id,
                              kind: "process_crash",
                            })
                          }
                          pending={fault.isPending}
                          destructive
                          icon={<ShieldAlert className="h-3.5 w-3.5" />}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title="Rollout safety">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-sm font-medium">Canary plan for the chat service</div>
              <div className="text-xs text-muted-foreground">
                Produces a read-only readiness and benchmark-gated rollout sequence.
              </div>
            </div>
            <button
              type="button"
              onClick={() =>
                rollout.mutate({
                  service: "chat",
                  strategy: "canary",
                  max_unavailable: 0,
                  desired: { revision: "next" },
                })
              }
              className="inline-flex h-8 items-center gap-2 rounded-sm border border-border px-3 text-xs hover:bg-surface"
            >
              <Play className="h-3.5 w-3.5" /> Plan canary
            </button>
          </div>
        </Panel>
        {operation && (
          <Panel title="Latest cluster operation">
            <JsonPreview value={operation} />
          </Panel>
        )}
      </div>
    </div>
  );
}
