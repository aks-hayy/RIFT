import { createFileRoute, Link } from "@tanstack/react-router";
import { AppShell } from "@/components/rift/app-shell";
import { PageHeader, Panel, StatDot } from "@/components/rift/primitives";
import { Unavailable } from "@/components/rift/unavailable";
import { useServices } from "@/lib/rift/hooks";
import { Plus, Search } from "lucide-react";
import type { Service } from "@/lib/rift/types";

export const Route = createFileRoute("/deployments/")({
  component: DeploymentsListPage,
});

function DeploymentsListPage() {
  const { data, unavailable, isLoading } = useServices();
  return (
    <AppShell>
      <PageHeader
        eyebrow="Deployments"
        title="Model services"
        description="Every LLM service RIFT is running, across every node."
        actions={
          <Link
            to="/setup"
            className="inline-flex items-center gap-2 h-9 px-3.5 rounded-[4px] bg-primary text-primary-foreground text-[13px] font-medium hover:bg-[color:var(--oxide-deep)]"
          >
            <Plus className="size-4" aria-hidden /> Deploy a model
          </Link>
        }
      />
      <div className="max-w-[1400px] mx-auto px-4 py-6 grid gap-4">
        {unavailable ? (
          <Unavailable
            endpoint="/v1/services"
            resource="Service[] { id, name, status, useCase, endpoint, assignments }"
          />
        ) : isLoading || !data ? (
          <Panel title="Services">
            <div className="text-[13px] text-ink-secondary">Loading services...</div>
          </Panel>
        ) : (
          <Panel
            bodyClassName="p-0"
            title={`${data.length} service${data.length === 1 ? "" : "s"}`}
            aside={
              <div className="relative">
                <Search
                  className="size-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-ink-secondary"
                  aria-hidden
                />
                <input
                  type="search"
                  placeholder="Filter"
                  className="h-7 pl-7 pr-2 rounded-[4px] border border-border bg-raised text-[12px] rift-mono w-40 focus:outline-none focus:border-primary"
                />
              </div>
            }
          >
            {data.length === 0 ? (
              <div className="px-4 py-14 text-center text-[13px] text-ink-secondary">
                No services deployed. Start the guided setup to deploy one.
              </div>
            ) : (
              <ul className="divide-y divide-border">
                {data.map((s: Service) => (
                  <li key={s.id}>
                    <Link
                      to="/deployments/$id"
                      params={{ id: s.id }}
                      className="flex items-center gap-4 px-4 py-3 hover:bg-muted/50"
                    >
                      <StatDot
                        tone={
                          s.status === "running"
                            ? "ok"
                            : s.status === "degraded"
                              ? "attention"
                              : s.status === "failed"
                                ? "error"
                                : "info"
                        }
                      />
                      <div className="min-w-0 flex-1">
                        <div className="text-[14px] text-ink font-medium">{s.name}</div>
                        <div className="rift-mono text-[11.5px] text-ink-secondary truncate">
                          {s.artifactId} · {s.backendKind} · {s.useCase}
                        </div>
                      </div>
                      <div className="hidden sm:block rift-mono text-[11.5px] text-ink-secondary text-right">
                        {s.endpoint.scheme}://{s.endpoint.bindAddress}:{s.endpoint.port}
                      </div>
                      <div className="rift-mono text-[11.5px] text-ink-secondary w-20 text-right">
                        {s.assignments.length} node{s.assignments.length === 1 ? "" : "s"}
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        )}
      </div>
    </AppShell>
  );
}
