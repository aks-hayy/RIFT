import { createFileRoute, Link } from "@tanstack/react-router";
import { AppShell } from "@/components/rift/app-shell";
import { PageHeader, Panel, StatDot } from "@/components/rift/primitives";
import { Unavailable } from "@/components/rift/unavailable";
import { useDeploymentRecords, useServices } from "@/lib/rift/hooks";
import { rift } from "@/lib/rift/client";
import { Loader2, Plus, Play, RotateCcw, Search } from "lucide-react";
import { useState } from "react";
import type { DeploymentRecord, Service } from "@/lib/rift/types";

export const Route = createFileRoute("/deployments/")({
  component: DeploymentsListPage,
});

function DeploymentsListPage() {
  const { data, unavailable, isLoading } = useServices();
  const records = useDeploymentRecords();
  const [filter, setFilter] = useState("");
  const query = filter.trim().toLowerCase();
  const activeServices = (data ?? []).filter(
    (service) =>
      !query ||
      `${service.name} ${service.artifactId} ${service.backendKind}`.toLowerCase().includes(query),
  );
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
      <div className="max-w-[1400px] mx-auto min-w-0 px-4 py-6 grid gap-4">
        {unavailable ? (
          <Unavailable
            endpoint="/services"
            resource="Service[] { id, name, status, useCase, endpoint, assignments }"
          />
        ) : isLoading || !data ? (
          <Panel title="Services">
            <div className="text-[13px] text-ink-secondary">Loading services...</div>
          </Panel>
        ) : (
          <Panel
            bodyClassName="p-0"
            title={`${activeServices.length} service${activeServices.length === 1 ? "" : "s"}`}
            aside={
              <div className="relative">
                <Search
                  className="size-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-ink-secondary"
                  aria-hidden
                />
                <input
                  type="search"
                  placeholder="Filter"
                  value={filter}
                  onChange={(event) => setFilter(event.target.value)}
                  className="h-7 pl-7 pr-2 rounded-[4px] border border-border bg-raised text-[12px] rift-mono w-40 focus:outline-none focus:border-primary"
                />
              </div>
            }
          >
            {activeServices.length === 0 ? (
              <div className="px-4 py-14 text-center text-[13px] text-ink-secondary">
                No services deployed. Start the guided setup to deploy one.
              </div>
            ) : (
              <ul className="divide-y divide-border">
                {activeServices.map((s: Service) => (
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
        <SavedDeployments records={records.data ?? []} unavailable={records.unavailable !== null} />
      </div>
    </AppShell>
  );
}

function SavedDeployments({
  records,
  unavailable,
}: {
  records: DeploymentRecord[];
  unavailable: boolean;
}) {
  const [confirming, setConfirming] = useState<string | null>(null);
  const [launching, setLaunching] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const launchAgain = async (record: DeploymentRecord) => {
    setLaunching(record.deploymentId);
    setConfirming(null);
    setMessage(null);
    setError(null);
    try {
      const result = await rift.relaunchDeployment(record.deploymentId, { allowLaunch: true });
      if (result.applied === false) {
        setError(String(result.reason ?? "The saved deployment could not be launched."));
      } else {
        setMessage(`${record.serviceName} relaunched through the saved configuration.`);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLaunching(null);
    }
  };

  return (
    <Panel
      title="Saved deployments"
      aside={<span className="rift-mono text-[11px] text-ink-secondary">reusable history</span>}
      bodyClassName="p-0"
    >
      {unavailable ? (
        <div className="px-4 py-8 text-[13px] text-ink-secondary">
          Saved deployment history is unavailable on this controller version.
        </div>
      ) : records.length === 0 ? (
        <div className="px-4 py-8 text-[13px] text-ink-secondary">
          Successful deployments will remain here after they are stopped or deleted.
        </div>
      ) : (
        <ul className="divide-y divide-border">
          {records.map((record) => {
            const modelName = String(
              record.model.selected_file ?? record.model.local_path ?? record.model.id ?? "model",
            );
            const context = record.serving.context_length;
            const statusTone =
              record.status === "ready" ? "ok" : record.status === "failed" ? "error" : "attention";
            return (
              <li key={record.deploymentId} className="px-4 py-3">
                <div className="flex flex-wrap items-start gap-3">
                  <StatDot tone={statusTone} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[13.5px] font-medium text-ink">
                        {record.displayName}
                      </span>
                      <span className="rift-mono text-[10px] uppercase text-ink-secondary">
                        {record.status}
                      </span>
                    </div>
                    <div className="mt-1 text-[12px] text-ink-secondary break-all">
                      {modelName} · {record.backend.kind}
                      {record.backend.version ? ` ${record.backend.version}` : ""}
                    </div>
                    <div className="mt-1 rift-mono text-[10.5px] text-ink-secondary">
                      {record.endpoint.openaiBase ??
                        record.endpoint.apiBase ??
                        "endpoint not recorded"}
                      {context ? ` · context ${String(context)}` : ""}
                      {record.relaunchCount ? ` · relaunched ${record.relaunchCount}x` : ""}
                    </div>
                  </div>
                  {confirming === record.deploymentId ? (
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={() => void launchAgain(record)}
                        disabled={launching !== null}
                        className="inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] bg-primary text-primary-foreground text-[12px] font-medium disabled:opacity-50"
                      >
                        {launching === record.deploymentId ? (
                          <Loader2 className="size-3.5 animate-spin" />
                        ) : (
                          <Play className="size-3.5" />
                        )}
                        Confirm launch
                      </button>
                      <button
                        type="button"
                        onClick={() => setConfirming(null)}
                        className="h-8 px-2.5 rounded-[4px] border border-border text-[12px]"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setConfirming(record.deploymentId)}
                      disabled={launching !== null}
                      className="inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] border border-border text-[12px] hover:bg-muted disabled:opacity-50"
                    >
                      <RotateCcw className="size-3.5" /> Launch again
                    </button>
                  )}
                </div>
                {confirming === record.deploymentId && (
                  <p className="mt-2 pl-6 rift-mono text-[10.5px] text-ink-secondary">
                    RIFT will revalidate the saved artifact and backend. This authorizes launch
                    only; missing downloads or installs remain blocked.
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {(message || error) && (
        <div
          className="border-t border-border px-4 py-2 rift-mono text-[11px]"
          role={error ? "alert" : undefined}
        >
          <span className={error ? "text-error" : "text-secondary"}>{error ?? message}</span>
        </div>
      )}
    </Panel>
  );
}
