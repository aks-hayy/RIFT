import { createFileRoute } from "@tanstack/react-router";
import { KeyRound, RotateCcw, Trash2 } from "lucide-react";
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
import { dateTime, number, statusTone } from "@/lib/rift-api";

export const Route = createFileRoute("/monitoring")({ component: MonitoringPage });

function MonitoringPage() {
  const [keyLabel, setKeyLabel] = useState("operator");
  const observability = useRiftQuery<any>(riftKeys.observability, "/api/rift/observability", {
    refetchInterval: 5_000,
  });
  const incidents = useRiftQuery<any>(riftKeys.incidents, "/api/rift/incidents", {
    refetchInterval: 5_000,
  });
  const gateway = useRiftQuery<any>(riftKeys.gateway, "/api/rift/gateway", {
    refetchInterval: 5_000,
  });
  const logs = useRiftQuery<any>(["rift", "logs"], "/api/rift/logs", { refetchInterval: 5_000 });
  const createKey = useRiftMutation<any>("/api/rift/gateway/keys/create", [riftKeys.gateway]);
  const rotateKey = useRiftMutation<any>("/api/rift/gateway/keys/rotate", [riftKeys.gateway]);
  const revokeKey = useRiftMutation<any>("/api/rift/gateway/keys/revoke", [riftKeys.gateway]);
  const prune = useRiftMutation<any>("/api/rift/observability/prune", [riftKeys.observability]);

  if (observability.isPending || incidents.isPending || gateway.isPending || logs.isPending)
    return <LoadingState label="Reading operational telemetry" />;
  const error = observability.error || incidents.error || gateway.error || logs.error;
  if (error) return <ErrorState error={error} onRetry={() => void observability.refetch()} />;
  const snapshot = observability.data?.snapshot ?? {};
  const events = observability.data?.timeline?.events ?? [];
  const incidentRows = incidents.data?.incidents ?? [];
  const keys = gateway.data?.api_keys?.keys ?? [];

  return (
    <div>
      <PageHeader
        title="Monitoring and security"
        subtitle="Health, incidents, gateway load, redacted logs, operation timeline, and hash-only API key management."
        command="rift monitor --iterations 0"
      />
      <div className="space-y-3 p-4">
        <div className="grid gap-3 lg:grid-cols-4">
          <Panel>
            <Metric label="Services" value={snapshot.services_total ?? 0} />
          </Panel>
          <Panel>
            <Metric
              label="Restarts"
              value={snapshot.restart_count ?? 0}
              tone={snapshot.restart_count ? "warn" : "ok"}
            />
          </Panel>
          <Panel>
            <Metric label="Gateway requests" value={snapshot.gateway?.requests_total ?? 0} />
          </Panel>
          <Panel>
            <Metric
              label="Average latency"
              value={number(snapshot.gateway?.average_latency_seconds)}
              unit="s"
            />
          </Panel>
        </div>

        <div className="grid gap-3 xl:grid-cols-[1.2fr_1fr]">
          <Panel title="Operation timeline" scroll className="min-h-80">
            {events.length === 0 ? (
              <div className="text-sm text-muted-foreground">No events recorded.</div>
            ) : (
              <div className="space-y-2">
                {[...events].reverse().map((event: any, index: number) => (
                  <div
                    key={`${event.created_unix_seconds}-${index}`}
                    className="grid grid-cols-[9rem_1fr_auto] gap-3 border-b border-border/50 py-1.5 text-xs last:border-0"
                  >
                    <span className="mono text-muted-foreground">
                      {dateTime(event.created_unix_seconds)}
                    </span>
                    <span>
                      {event.event}
                      {event.service ? ` / ${event.service}` : ""}
                    </span>
                    <Chip tone={statusTone(event.status)}>{event.status}</Chip>
                  </div>
                ))}
              </div>
            )}
          </Panel>
          <Panel title="Incident ledger" scroll className="min-h-80">
            {incidentRows.length === 0 ? (
              <div className="text-sm text-muted-foreground">No persisted incidents.</div>
            ) : (
              <div className="space-y-3">
                {incidentRows.map((incident: any, index: number) => (
                  <div
                    key={incident.path ?? index}
                    className="border-b border-border/60 pb-3 last:border-0"
                  >
                    <div className="flex items-center justify-between">
                      <span className="mono text-xs">
                        {incident.summary?.service ?? incident.service ?? "service"}
                      </span>
                      <Chip tone="warn">incident</Chip>
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {incident.summary?.reason ?? incident.reason ?? incident.path}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>

        <Panel title="Gateway API keys">
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-xs text-muted-foreground">
              Key label
              <input
                value={keyLabel}
                onChange={(event) => setKeyLabel(event.target.value)}
                className="mt-1 h-9 w-52 rounded-sm border border-input bg-background px-3 text-foreground"
              />
            </label>
            <ConfirmAction
              label="Create key"
              title="Create a gateway API key?"
              description="The plaintext secret will be shown once. RIFT stores only its SHA-256 digest."
              onConfirm={() => createKey.mutate({ label: keyLabel })}
              pending={createKey.isPending}
              icon={<KeyRound className="h-3.5 w-3.5" />}
            />
          </div>
          {createKey.data?.secret && (
            <div className="mt-3 border border-warn/40 bg-warn/10 p-3">
              <div className="text-xs font-medium text-warn">
                Store this secret now. It cannot be recovered later.
              </div>
              <code className="mt-2 block break-all mono text-xs">{createKey.data.secret}</code>
            </div>
          )}
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-border text-[10px] uppercase tracking-widest text-muted-foreground">
                <tr>
                  <th className="py-2">Label</th>
                  <th>Fingerprint</th>
                  <th>Created</th>
                  <th>Status</th>
                  <th className="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {keys.map((key: any) => (
                  <tr key={key.id} className="border-b border-border/60 last:border-0">
                    <td className="py-2">{key.label}</td>
                    <td className="mono">{key.fingerprint}</td>
                    <td>{dateTime(key.created_unix_seconds)}</td>
                    <td>
                      <Chip tone={key.revoked_unix_seconds ? "err" : "ok"}>
                        {key.revoked_unix_seconds ? "revoked" : "active"}
                      </Chip>
                    </td>
                    <td>
                      <div className="flex justify-end gap-2">
                        {!key.revoked_unix_seconds && (
                          <>
                            <ConfirmAction
                              label="Rotate"
                              title={`Rotate ${key.label}?`}
                              description="The old key is revoked and a new plaintext secret is returned once."
                              onConfirm={() => rotateKey.mutate({ key_id: key.id })}
                              pending={rotateKey.isPending}
                              icon={<RotateCcw className="h-3.5 w-3.5" />}
                            />
                            <ConfirmAction
                              label="Revoke"
                              title={`Revoke ${key.label}?`}
                              description="Clients using this key will immediately lose access."
                              onConfirm={() => revokeKey.mutate({ key_id: key.id })}
                              pending={revokeKey.isPending}
                              destructive
                              icon={<Trash2 className="h-3.5 w-3.5" />}
                            />
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {rotateKey.data?.new?.secret && (
            <div className="mt-3 border border-warn/40 bg-warn/10 p-3">
              <div className="text-xs text-warn">Rotated secret, shown once:</div>
              <code className="mt-1 block break-all mono text-xs">{rotateKey.data.new.secret}</code>
            </div>
          )}
        </Panel>

        <Panel title="Redacted service log" scroll className="min-h-64">
          <pre className="whitespace-pre-wrap mono text-[11px] leading-5 text-muted-foreground">
            {logs.data?.available
              ? (logs.data.lines ?? []).join("\n")
              : "No chat service log is available."}
          </pre>
        </Panel>

        <div className="flex justify-end">
          <ConfirmAction
            label="Prune old telemetry"
            title="Prune telemetry outside retention?"
            description="Events outside the configured retention window are removed from the local timeline."
            onConfirm={() => prune.mutate({})}
            pending={prune.isPending}
            destructive
          />
        </div>
        <ResultBanner result={prune.data || createKey.data || rotateKey.data || revokeKey.data} />
        {(createKey.error || rotateKey.error || revokeKey.error || prune.error) && (
          <ErrorState
            error={createKey.error || rotateKey.error || revokeKey.error || prune.error}
          />
        )}
        <Panel title="Gateway state">
          <JsonPreview value={gateway.data} />
        </Panel>
      </div>
    </div>
  );
}
