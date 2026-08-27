import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { z } from "zod";
import { AppShell } from "@/components/rift/app-shell";
import { PageHeader, Panel, KV, StatDot, SourceBadge } from "@/components/rift/primitives";
import { Unavailable } from "@/components/rift/unavailable";
import { useNode } from "@/lib/rift/hooks";
import { bytes, pct, relativeTime } from "@/lib/rift/format";
import { cn } from "@/lib/utils";
import type { RiftNode } from "@/lib/rift/types";

const searchSchema = z.object({
  tab: z
    .enum(["hardware", "assignments", "backends", "cache", "health", "diagnostics"])
    .catch("hardware"),
});

export const Route = createFileRoute("/nodes/$id")({
  validateSearch: searchSchema,
  head: ({ params }) => ({
    meta: [{ title: `${params.id} — Node` }],
  }),
  component: NodeDetail,
});

const TABS = [
  { id: "hardware", label: "Hardware" },
  { id: "assignments", label: "Assignments" },
  { id: "backends", label: "Backends" },
  { id: "cache", label: "Model cache" },
  { id: "health", label: "Health" },
  { id: "diagnostics", label: "Diagnostics" },
] as const;

function NodeDetail() {
  const { id } = Route.useParams();
  const { tab } = Route.useSearch();
  const navigate = useNavigate({ from: "/nodes/$id" });
  const { data: node, unavailable } = useNode(id);

  return (
    <AppShell>
      <PageHeader
        eyebrow="Node"
        title={node?.hostname ?? id}
        description={
          node ? `${node.role} · ${node.os} ${node.arch} · agent ${node.version}` : undefined
        }
        actions={
          node && (
            <span className="inline-flex items-center gap-2 rift-mono text-[12px]">
              <StatDot
                tone={
                  node.status === "ready"
                    ? "ok"
                    : node.status === "offline" || node.status === "error"
                      ? "error"
                      : "attention"
                }
              />
              {node.status}
            </span>
          )
        }
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
        {unavailable && <Unavailable endpoint="/hardware" resource="RIFT node hardware" />}
        {node && tab === "hardware" && <HardwareTab n={node} />}
        {tab === "assignments" && (
          <Unavailable
            endpoint="/services"
            resource="Assignment[] { serviceId, gpuIndices, reservedVramBytes }"
          />
        )}
        {node && tab === "backends" && <BackendsTab n={node} />}
        {tab === "cache" && (
          <Unavailable
            endpoint="/artifacts"
            resource="CachedArtifact[] { artifactId, sizeBytes, sha256, lastUsedAt }"
          />
        )}
        {node && tab === "health" && <HealthTab n={node} />}
        {tab === "diagnostics" && (
          <Unavailable
            endpoint="/diagnostics"
            method="POST"
            resource="DiagnosticsBundle { url, expiresAt }"
            hint="Bundle should include driver info, kernel, dmesg tail, backend logs."
          />
        )}
      </div>
    </AppShell>
  );
}

function HardwareTab({ n }: { n: RiftNode }) {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="lg:col-span-2 grid gap-4">
        <Panel
          title="Accelerators"
          aside={<SourceBadge source={n.provenance} />}
          bodyClassName="p-0"
        >
          {n.accelerators.length === 0 ? (
            <div className="px-4 py-8 text-[13px] text-ink-secondary text-center">
              No accelerators detected — CPU inference only.
            </div>
          ) : (
            <table className="w-full text-[13px]">
              <thead className="rift-label">
                <tr className="border-b border-border">
                  <th className="text-left px-4 h-9 font-normal">#</th>
                  <th className="text-left px-4 font-normal">Vendor</th>
                  <th className="text-left px-4 font-normal">Model</th>
                  <th className="text-left px-4 font-normal">VRAM used</th>
                </tr>
              </thead>
              <tbody>
                {n.accelerators.map((a) => {
                  const used = a.vramBytes - a.vramFreeBytes;
                  return (
                    <tr key={a.index} className="border-b border-border last:border-0">
                      <td className="px-4 py-2.5 rift-mono">{a.index}</td>
                      <td className="px-4 rift-mono text-[12px] uppercase">{a.vendor}</td>
                      <td className="px-4">{a.name}</td>
                      <td className="px-4">
                        <div className="flex items-center gap-2">
                          <div className="w-24 h-1.5 bg-muted rounded-[2px] overflow-hidden">
                            <div
                              className="h-full bg-secondary"
                              style={{ width: `${pct(used, a.vramBytes)}%` }}
                            />
                          </div>
                          <span className="rift-mono text-[11.5px] text-ink-secondary">
                            {bytes(used)} / {bytes(a.vramBytes)}
                          </span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </Panel>
      </div>
      <div className="grid gap-4">
        <Panel title="System">
          <div className="grid gap-3">
            <KV label="OS" value={`${n.os} ${n.arch}`} />
            <KV
              label="RAM"
              value={`${bytes(n.ramBytes - n.ramFreeBytes)} / ${bytes(n.ramBytes)}`}
            />
            <KV
              label="Disk"
              value={`${bytes(n.diskBytes - n.diskFreeBytes)} / ${bytes(n.diskBytes)}`}
            />
            <KV label="Enrolled" value={relativeTime(n.enrolledAt)} />
            <KV label="Address" value={n.address} />
          </div>
        </Panel>
      </div>
    </div>
  );
}

function HealthTab({ n }: { n: RiftNode }) {
  const telemetry = n.telemetry;
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Panel
        title="Observed telemetry"
        aside={<SourceBadge source={n.provenance} />}
        className="lg:col-span-2"
      >
        <div className="grid grid-cols-2 gap-5 sm:grid-cols-4">
          <KV
            label="GPU utilization"
            value={
              telemetry?.gpuUtilizationPercent != null
                ? `${telemetry.gpuUtilizationPercent}%`
                : "not reported"
            }
          />
          <KV
            label="Temperature"
            value={telemetry?.temperatureC != null ? `${telemetry.temperatureC} C` : "not reported"}
          />
          <KV
            label="Power draw"
            value={telemetry?.powerDrawW != null ? `${telemetry.powerDrawW} W` : "not reported"}
          />
          <KV
            label="Disk read sample"
            value={
              telemetry?.diskReadMiBs
                ? `${telemetry.diskReadMiBs.toFixed(1)} MiB/s`
                : "not calibrated"
            }
          />
        </div>
      </Panel>
      <Panel title="Processor">
        <div className="grid gap-3">
          <KV label="CPU" value={telemetry?.cpuModel ?? "not reported"} mono={false} />
          <KV label="Logical processors" value={telemetry?.logicalCpuCount ?? "--"} />
          <KV label="Last heartbeat" value={relativeTime(n.lastHeartbeatAt)} />
        </div>
      </Panel>
    </div>
  );
}

function BackendsTab({ n }: { n: RiftNode }) {
  return (
    <Panel title="Installed backends">
      {n.backends.length === 0 ? (
        <p className="text-[13px] text-ink-secondary">No backends installed on this node.</p>
      ) : (
        <ul className="grid gap-1.5">
          {n.backends.map((b) => (
            <li key={b} className="rift-mono text-[13px] text-ink">
              {b}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
