import { createFileRoute } from "@tanstack/react-router";
import { Layers3, Route as RouteIcon } from "lucide-react";
import { AppShell } from "@/components/rift/app-shell";
import { PageHeader, Panel, StatDot } from "@/components/rift/primitives";
import { Unavailable } from "@/components/rift/unavailable";
import { useMeshServiceGroups, useMeshServices } from "@/lib/rift/hooks";
import { useGatewayStatus } from "@/lib/rift/hooks";
import { rift } from "@/lib/rift/client";
import { useState } from "react";

export const Route = createFileRoute("/groups")({
  head: () => ({ meta: [{ title: "Groups — RIFT" }] }),
  component: GroupsPage,
});

function GroupsPage() {
  const groups = useMeshServiceGroups();
  const services = useMeshServices();
  const gateway = useGatewayStatus();
  const [ports, setPorts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const servicesById = new Map((services.data ?? []).map((service) => [service.serviceId, service]));
  return (
    <AppShell>
      <PageHeader
        eyebrow="Mesh gateway organization"
        title="Groups"
        description="Gateway groups expose a stable entry point while RIFT routes requests across their model-backed services."
      />
      <div className="max-w-[1400px] mx-auto px-4 py-6 grid gap-4">
        {groups.unavailable || services.unavailable ? (
          <Unavailable endpoint="/v2/mesh/service-groups" resource="Mesh gateway groups" />
        ) : groups.isLoading || services.isLoading ? (
          <Panel title="Gateway groups"><div className="p-4 text-[13px] text-ink-secondary">Loading groups…</div></Panel>
        ) : (groups.data ?? []).length === 0 ? (
          <Panel title="Gateway groups"><div className="p-10 text-center text-[13px] text-ink-secondary">No service groups configured yet.</div></Panel>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {(groups.data ?? []).map((group) => (
              <Panel key={group.groupId} title={group.groupId} aside={<StatDot tone="ok" />}>
                <div className="flex items-center gap-2 text-[12px] text-ink-secondary"><RouteIcon className="size-3.5" aria-hidden /> {group.gatewayPath ?? "no published path"}</div>
                <div className="mt-4 grid gap-2">
                  {group.serviceIds.map((serviceId) => {
                    const service = servicesById.get(serviceId);
                    return <div key={serviceId} className="flex items-center justify-between border-t border-border pt-2 text-[13px]"><span className="font-medium">{serviceId}</span><span className="rift-mono text-[11px] text-ink-secondary">{service ? `${service.modelId} · ${service.revision}` : "missing service"}</span></div>;
                  })}
                </div>
                <div className="mt-4 flex items-center gap-2 text-[11px] uppercase tracking-[0.12em] text-ink-secondary"><Layers3 className="size-3.5" aria-hidden /> default: {group.defaultService ?? group.serviceIds[0]}</div>
                <div className="mt-4 border-t border-border pt-3 grid gap-2">
                  <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.1em] text-ink-secondary">
                    <span>Main gateway route</span>
                    <span className="rift-mono">{gateway.data?.status ?? "unknown"}</span>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <input
                      aria-label={`Dedicated port for ${group.groupId}`}
                      value={ports[group.groupId] ?? "11736"}
                      onChange={(event) => setPorts((current) => ({ ...current, [group.groupId]: event.target.value }))}
                      className="h-8 w-24 rounded-[4px] border border-border bg-transparent px-2 rift-mono text-[12px]"
                      inputMode="numeric"
                    />
                    {(() => {
                      const listener = gateway.data?.groups?.find((item) => item.groupId === group.groupId);
                      const running = listener?.status === "running" && listener.processAlive;
                      return (
                        <button
                          type="button"
                          disabled={busy === group.groupId}
                          onClick={async () => {
                            setBusy(group.groupId);
                            try {
                              await rift.gatewayGroupAction(group.groupId, running ? "stop" : "start", running ? {} : { port: Number(ports[group.groupId] ?? 11736) });
                              gateway.refetch();
                            } finally {
                              setBusy(null);
                            }
                          }}
                          className="h-8 px-3 rounded-[4px] border border-border text-[12px] disabled:opacity-50"
                        >
                          {busy === group.groupId ? "Working…" : running ? "Stop dedicated listener" : "Start dedicated listener"}
                        </button>
                      );
                    })()}
                  </div>
                </div>
              </Panel>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
