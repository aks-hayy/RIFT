import { createFileRoute, Link } from "@tanstack/react-router";
import { Activity, Network, ShieldCheck, UserPlus } from "lucide-react";
import { AppShell } from "@/components/rift/app-shell";
import { PageHeader, Panel, StatDot } from "@/components/rift/primitives";
import { Unavailable } from "@/components/rift/unavailable";
import { relativeTime } from "@/lib/rift/format";
import { useMeshNodes, useMeshTopology } from "@/lib/rift/hooks";
import type { MeshNode } from "@/lib/rift/types";

export const Route = createFileRoute("/nodes/")({
  component: NodesListPage,
});

function nodeTone(node: MeshNode): "ok" | "attention" | "error" {
  if (node.trustState === "REVOKED" || !node.healthy) return "error";
  if (node.trustState === "ACTIVE" && node.routable) return "ok";
  return "attention";
}

function nodeStatus(node: MeshNode): string {
  if (node.trustState === "ACTIVE" && node.routable) return "active";
  if (node.trustState === "ENROLLED") return "enrolled";
  return node.trustState.toLowerCase().replaceAll("_", " ");
}

function certificateStatus(node: MeshNode): string {
  if (node.certificateRequired) return "activation pending";
  if (node.trustState === "ACTIVE") return "active";
  return "not active";
}

function NodesListPage() {
  const nodesQuery = useMeshNodes();
  const topologyQuery = useMeshTopology();
  const nodes = nodesQuery.data ?? [];
  const topology = topologyQuery.data;
  const routable = nodes.filter((node) => node.routable && node.trustState === "ACTIVE").length;
  const certificatePending = nodes.filter((node) => node.certificateRequired).length;
  const unhealthy = nodes.filter((node) => !node.healthy).length;
  const nodeNames = new Map(
    [...nodes, ...(topology?.nodes ?? [])].map((node) => [node.nodeId, node.hostname]),
  );

  return (
    <AppShell>
      <PageHeader
        eyebrow="Mesh operations"
        title="Nodes"
        description="Live enrollment, activation, routing, and measured-link state from the RIFT controller."
        actions={
          <Link
            to="/setup"
            className="inline-flex items-center gap-2 h-9 px-3.5 rounded-[4px] border border-border text-[13px] font-medium hover:bg-muted"
          >
            <UserPlus className="size-4" aria-hidden /> Discover node
          </Link>
        }
      />

      <div className="max-w-[1400px] mx-auto px-4 py-6 grid gap-6">
        {!nodesQuery.unavailable && !nodesQuery.isLoading && (
          <section
            className="grid grid-cols-2 lg:grid-cols-4 border-y border-border bg-raised"
            aria-label="Mesh node summary"
          >
            <MeshStat label="Enrolled" value={nodes.length} icon={Network} />
            <MeshStat label="Active / routable" value={routable} icon={Activity} />
            <MeshStat label="Certificate pending" value={certificatePending} icon={ShieldCheck} />
            <MeshStat
              label="Unhealthy"
              value={unhealthy}
              icon={Activity}
              tone={unhealthy ? "error" : "default"}
            />
          </section>
        )}

        <section aria-labelledby="mesh-node-registry">
          {nodesQuery.unavailable ? (
            <Unavailable
              endpoint="/api/rift/v2/mesh/nodes"
              resource="{ api_version, nodes: MeshNode[] }"
              hint="Start the RIFT controller or complete controller configuration before managing mesh enrollment."
            />
          ) : nodesQuery.isLoading ? (
            <Panel title="Enrollment registry">
              <div className="text-[13px] text-ink-secondary">Loading enrolled identities…</div>
            </Panel>
          ) : (
            <Panel
              bodyClassName="p-0 overflow-x-auto"
              title={`${nodes.length} enrolled node${nodes.length === 1 ? "" : "s"}`}
            >
              {nodes.length === 0 ? (
                <div className="px-4 py-14 text-center">
                  <ShieldCheck className="size-5 text-ink-secondary mx-auto" aria-hidden />
                  <div className="mt-3 text-[13px] font-medium text-ink">No enrolled nodes</div>
                  <p className="mt-1 text-[12.5px] text-ink-secondary">
                    Discovery sightings do not appear here until an operator approves pairing.
                  </p>
                  <Link
                    to="/setup"
                    className="mt-4 inline-flex items-center gap-2 h-9 px-3 rounded-[4px] border border-border text-[12px] font-medium hover:bg-muted"
                  >
                    <UserPlus className="size-3.5" aria-hidden /> Open discovery
                  </Link>
                </div>
              ) : (
                <table className="w-full min-w-[960px] text-[13px]">
                  <thead className="rift-label">
                    <tr className="border-b border-border">
                      <th id="mesh-node-registry" className="text-left px-4 h-9 font-normal">
                        Node
                      </th>
                      <th className="text-left px-4 font-normal">Enrollment</th>
                      <th className="text-left px-4 font-normal">Routable</th>
                      <th className="text-left px-4 font-normal">Certificate</th>
                      <th className="text-left px-4 font-normal">Health</th>
                      <th className="text-right px-4 font-normal">Queue</th>
                      <th className="text-left px-4 font-normal">Last seen</th>
                    </tr>
                  </thead>
                  <tbody>
                    {nodes.map((node) => (
                      <tr
                        key={node.nodeId}
                        className="border-b border-border last:border-0 hover:bg-muted/50"
                      >
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <StatDot tone={nodeTone(node)} />
                            <div className="min-w-0">
                              <div className="font-medium text-ink">{node.hostname}</div>
                              <div className="rift-mono text-[10.5px] text-ink-secondary truncate max-w-[260px]">
                                {node.nodeId}
                                {node.endpoint ? ` · ${node.endpoint}` : ""}
                              </div>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 rift-mono text-[11.5px] uppercase text-ink-secondary">
                          {nodeStatus(node)}
                        </td>
                        <td className="px-4">
                          <StateLabel active={node.routable} yes="yes" no="no" />
                        </td>
                        <td className="px-4 rift-mono text-[11.5px] text-ink-secondary">
                          {certificateStatus(node)}
                        </td>
                        <td className="px-4">
                          <StateLabel active={node.healthy} yes="healthy" no="unhealthy" />
                        </td>
                        <td className="px-4 text-right rift-mono text-[12px]">{node.queueDepth}</td>
                        <td className="px-4 rift-mono text-[11.5px] text-ink-secondary whitespace-nowrap">
                          {node.lastSeenAt ? relativeTime(node.lastSeenAt) : "not reported"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Panel>
          )}
        </section>

        <section aria-labelledby="mesh-link-table">
          {topologyQuery.unavailable ? (
            <Unavailable
              endpoint="/api/rift/v2/mesh/topology"
              resource="{ api_version, nodes: MeshNode[], links: MeshLink[], evidence }"
              reason="Link measurements are unavailable. Enrolled-node state above may still be current."
              hint="RIFT does not infer latency or draw synthetic connections when topology telemetry is absent."
            />
          ) : topologyQuery.isLoading || !topology ? (
            <Panel title="Measured links">
              <div className="text-[13px] text-ink-secondary">Loading link measurements…</div>
            </Panel>
          ) : (
            <Panel
              bodyClassName="p-0 overflow-x-auto"
              title={`Measured links · ${topology.evidence}`}
            >
              {topology.links.length === 0 ? (
                <div className="px-4 py-10 text-[13px] text-ink-secondary">
                  No measured links reported. RIFT will show routes here after the controller
                  records real link telemetry.
                </div>
              ) : (
                <table className="w-full min-w-[980px] text-[13px]">
                  <thead className="rift-label">
                    <tr className="border-b border-border">
                      <th id="mesh-link-table" className="text-left px-4 h-9 font-normal">
                        Source
                      </th>
                      <th className="text-left px-4 font-normal">Target</th>
                      <th className="text-right px-4 font-normal">RTT p50</th>
                      <th className="text-right px-4 font-normal">RTT p95</th>
                      <th className="text-right px-4 font-normal">Jitter</th>
                      <th className="text-right px-4 font-normal">Loss</th>
                      <th className="text-right px-4 font-normal">Up</th>
                      <th className="text-right px-4 font-normal">Down</th>
                      <th className="text-left px-4 font-normal">Evidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topology.links.map((link) => (
                      <tr
                        key={`${link.sourceNodeId}-${link.targetNodeId}`}
                        className="border-b border-border last:border-0 hover:bg-muted/50"
                      >
                        <td className="px-4 py-3">
                          <div className="font-medium text-ink">
                            {nodeNames.get(link.sourceNodeId) ?? link.sourceNodeId}
                          </div>
                          <div className="rift-mono text-[10.5px] text-ink-secondary">
                            {link.sourceNodeId}
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="font-medium text-ink">
                            {nodeNames.get(link.targetNodeId) ?? link.targetNodeId}
                          </div>
                          <div className="rift-mono text-[10.5px] text-ink-secondary">
                            {link.targetNodeId}
                          </div>
                        </td>
                        <Metric value={link.rttP50Ms} unit="ms" />
                        <Metric value={link.rttP95Ms} unit="ms" />
                        <Metric value={link.jitterMs} unit="ms" />
                        <Metric value={link.lossRatio * 100} unit="%" />
                        <Metric value={link.uploadMbps} unit="Mbps" />
                        <Metric value={link.downloadMbps} unit="Mbps" />
                        <td className="px-4 rift-mono text-[10.5px] uppercase text-ink-secondary">
                          {link.evidence}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Panel>
          )}
        </section>
      </div>
    </AppShell>
  );
}

function MeshStat({
  label,
  value,
  icon: Icon,
  tone = "default",
}: {
  label: string;
  value: number;
  icon: typeof Network;
  tone?: "default" | "error";
}) {
  return (
    <div className="min-h-20 px-4 py-3 border-r border-b lg:border-b-0 border-border last:border-r-0">
      <div className="flex items-center gap-2 rift-label">
        <Icon className={tone === "error" ? "size-3.5 text-error" : "size-3.5 text-primary"} />
        {label}
      </div>
      <div
        className={
          tone === "error"
            ? "mt-2 rift-mono text-[20px] text-error"
            : "mt-2 rift-mono text-[20px] text-ink"
        }
      >
        {value}
      </div>
    </div>
  );
}

function StateLabel({ active, yes, no }: { active: boolean; yes: string; no: string }) {
  return (
    <span
      className={
        active
          ? "rift-mono text-[10.5px] uppercase text-success"
          : "rift-mono text-[10.5px] uppercase text-attention"
      }
    >
      {active ? yes : no}
    </span>
  );
}

function Metric({ value, unit }: { value: number; unit: string }) {
  return (
    <td className="px-4 text-right rift-mono text-[11.5px] whitespace-nowrap">
      {Number.isFinite(value) ? value.toFixed(value < 10 ? 2 : 1) : "—"} {unit}
    </td>
  );
}
