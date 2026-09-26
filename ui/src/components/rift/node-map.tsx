import { useMemo, useState } from "react";
import { Link } from "@tanstack/react-router";
import { ArrowUpRight, Network } from "lucide-react";
import { Panel, StatDot } from "@/components/rift/primitives";
import { assignedServices } from "@/lib/rift/node-services";
import { buildNodeMapLayout } from "@/lib/rift/topology-layout";
import type { MeshLink, MeshNode, Service } from "@/lib/rift/types";

export function NodeMap({
  nodes,
  links,
  services,
}: {
  nodes: MeshNode[];
  links: MeshLink[];
  services: Service[];
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const layout = useMemo(() => buildNodeMapLayout(nodes, links), [nodes, links]);
  const selectedIdNow = nodes.some((node) => node.nodeId === selectedId)
    ? selectedId
    : (nodes[0]?.nodeId ?? null);
  const selectedNode = nodes.find((node) => node.nodeId === selectedIdNow) ?? null;
  const nodeServices = assignedServices(services, selectedNode?.nodeId ?? null);
  const nodePositions = new Map(layout.nodes.map((node) => [node.id, node]));

  return (
    <Panel
      title="Node map"
      aside={
        <span className="inline-flex items-center gap-1.5 rift-mono text-[10.5px] text-ink-secondary">
          <Network className="size-3.5 text-primary" aria-hidden />
          {nodes.length} nodes · {layout.links.length} measured links
        </span>
      }
    >
      {!nodes.length ? (
        <div className="rounded-xl border border-dashed border-border-strong bg-white/35 px-5 py-10 text-center">
          <Network className="mx-auto size-5 text-ink-muted" aria-hidden />
          <p className="mt-2 text-[13px] font-medium text-ink">No enrolled nodes to map</p>
          <p className="mt-1 text-[12px] text-ink-secondary">
            Discovery sightings remain separate until an operator approves node pairing.
          </p>
        </div>
      ) : (
        <>
          <div className="relative min-h-[310px] overflow-hidden rounded-2xl border border-border/70 bg-[radial-gradient(ellipse_at_center,rgba(255,255,255,.93),rgba(245,242,244,.72))] p-3 sm:min-h-[370px]">
            <div
              className="pointer-events-none absolute inset-0 opacity-40 [background-image:linear-gradient(rgba(105,56,64,.08)_1px,transparent_1px),linear-gradient(90deg,rgba(105,56,64,.08)_1px,transparent_1px)] [background-size:32px_32px]"
              aria-hidden
            />
            <svg
              className="pointer-events-none absolute inset-0 size-full"
              viewBox="0 0 1000 440"
              preserveAspectRatio="none"
              aria-hidden="true"
            >
              {layout.links.map((link) => {
                const source = nodePositions.get(link.sourceNodeId);
                const target = nodePositions.get(link.targetNodeId);
                if (!source || !target) return null;
                return (
                  <line
                    key={`${link.sourceNodeId}-${link.targetNodeId}`}
                    x1={source.x * 10}
                    y1={source.y * 4.4}
                    x2={target.x * 10}
                    y2={target.y * 4.4}
                    stroke="var(--oxide)"
                    strokeWidth="1.5"
                    strokeDasharray="6 7"
                    strokeOpacity=".56"
                  >
                    <title>
                      Measured link · {link.rttP50Ms.toFixed(1)} ms p50 · {link.evidence}
                    </title>
                  </line>
                );
              })}
            </svg>
            {layout.nodes.map((position) => {
              const node = nodes.find((item) => item.nodeId === position.id);
              if (!node) return null;
              const active = node.nodeId === selectedIdNow;
              return (
                <button
                  key={node.nodeId}
                  type="button"
                  onClick={() => setSelectedId(node.nodeId)}
                  aria-pressed={active}
                  aria-label={`Select node ${node.hostname}, ${node.healthy ? "healthy" : "unhealthy"}, ${node.routable ? "routable" : "not routable"}`}
                  className={`absolute z-10 flex w-[min(40vw,190px)] -translate-x-1/2 -translate-y-1/2 flex-col rounded-xl border px-3 py-2.5 text-left shadow-lg backdrop-blur-lg transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${active ? "border-primary/60 bg-white/95 ring-2 ring-primary/15" : "border-white/80 bg-white/75 hover:border-primary/35 hover:bg-white/95"}`}
                  style={{ left: `${position.x}%`, top: `${position.y}%` }}
                >
                  <span className="flex min-w-0 items-center gap-2">
                    <StatDot
                      tone={
                        !node.healthy || node.trustState === "REVOKED"
                          ? "error"
                          : node.routable
                            ? "ok"
                            : "attention"
                      }
                    />
                    <span className="truncate text-[12px] font-semibold text-ink">
                      {node.hostname}
                    </span>
                  </span>
                  <span className="mt-1 truncate pl-4 rift-mono text-[9.5px] text-ink-muted">
                    {node.nodeId}
                  </span>
                  <span className="mt-1 flex items-center justify-between pl-4 text-[10px] text-ink-secondary">
                    <span>{node.trustState.toLowerCase().replaceAll("_", " ")}</span>
                    <span>{node.queueDepth} queued</span>
                  </span>
                </button>
              );
            })}
            <div className="absolute bottom-3 left-3 rounded-lg border border-border/60 bg-white/80 px-2.5 py-1.5 rift-mono text-[9.5px] text-ink-secondary backdrop-blur">
              schematic layout · only measured links are drawn
            </div>
          </div>
          {selectedNode && (
            <div className="mt-4 grid gap-4 rounded-xl border border-border/70 bg-white/45 p-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
              <div>
                <div className="rift-label">Selected node</div>
                <div className="mt-1 flex items-center gap-2 text-[14px] font-semibold text-ink">
                  <StatDot
                    tone={
                      !selectedNode.healthy ? "error" : selectedNode.routable ? "ok" : "attention"
                    }
                  />
                  {selectedNode.hostname}
                </div>
                <div className="mt-1 rift-mono text-[10.5px] text-ink-secondary">
                  {selectedNode.nodeId}
                </div>
                <Link
                  to="/nodes/$id"
                  params={{ id: selectedNode.nodeId }}
                  className="mt-3 inline-flex h-8 items-center gap-1.5 rounded-lg border border-border bg-white/80 px-3 text-[11.5px] font-medium text-primary hover:bg-primary/5"
                >
                  Inspect node <ArrowUpRight className="size-3.5" aria-hidden />
                </Link>
              </div>
              <div>
                <div className="rift-label">Services assigned to this node</div>
                {nodeServices.length ? (
                  <ul className="mt-2 flex flex-wrap gap-2">
                    {nodeServices.map((service) => (
                      <li key={service.id}>
                        <Link
                          to="/deployments/$id"
                          params={{ id: service.id }}
                          className="inline-flex items-center gap-2 rounded-lg border border-border bg-white/80 px-3 py-2 text-[11.5px] text-ink hover:border-primary/35 hover:text-primary"
                        >
                          <StatDot
                            tone={
                              service.status === "running"
                                ? "ok"
                                : service.status === "failed"
                                  ? "error"
                                  : "attention"
                            }
                          />
                          {service.name}
                        </Link>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-2 text-[12px] text-ink-secondary">
                    No service assignment is reported for this node.
                  </p>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </Panel>
  );
}
