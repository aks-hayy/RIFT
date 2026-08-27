import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { z } from "zod";
import { AppShell } from "@/components/rift/app-shell";
import { PageHeader, Panel, KV, SourceBadge, StatDot } from "@/components/rift/primitives";
import { Unavailable } from "@/components/rift/unavailable";
import { cn } from "@/lib/utils";
import { rift } from "@/lib/rift/client";
import { useBackends, useHealth, useSettings } from "@/lib/rift/hooks";

const searchSchema = z.object({
  tab: z
    .enum(["controller", "sources", "security", "policies", "integrations"])
    .catch("controller"),
});

export const Route = createFileRoute("/settings")({
  validateSearch: searchSchema,
  head: () => ({
    meta: [
      { title: "Settings — RIFT" },
      {
        name: "description",
        content: "Controller, sources, security, policies, and integrations.",
      },
      { property: "og:title", content: "Settings — RIFT" },
      {
        property: "og:description",
        content: "Controller, sources, security, policies, and integrations.",
      },
    ],
  }),
  component: SettingsPage,
});

const TABS = [
  { id: "controller", label: "Controller" },
  { id: "sources", label: "Model sources" },
  { id: "security", label: "Security" },
  { id: "policies", label: "Policies" },
  { id: "integrations", label: "Integrations" },
] as const;

function SettingsPage() {
  const { tab } = Route.useSearch();
  const navigate = useNavigate({ from: "/settings" });
  return (
    <AppShell>
      <PageHeader eyebrow="Settings" title="Configuration" />
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
        {tab === "controller" && <ControllerTab />}
        {tab === "sources" && <SourcesTab />}
        {tab === "security" && <SecurityTab />}
        {tab === "policies" && <PoliciesTab />}
        {tab === "integrations" && <BackendIntegrations />}
      </div>
    </AppShell>
  );
}

function ControllerTab() {
  const connection = rift.connectionInfo();
  const { data: health, unavailable, error, isLoading } = useHealth();
  const controllerStatus =
    unavailable || error ? "unavailable" : isLoading ? "checking" : health ? "live" : "unknown";
  return (
    <Panel title="Controller" aside={<SourceBadge source="live" />}>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KV label="Status" value={controllerStatus} />
        <KV label="URL" value={connection.root} />
        <KV label="Compatibility" value="live compatibility adapter" />
        <KV label="Preview surfaces" value={connection.previewEnabled ? "enabled" : "disabled"} />
      </div>
      <p className="mt-4 max-w-2xl text-[12.5px] text-ink-secondary">
        This dashboard is connected to the live controller. The compatibility adapter translates the
        current controller API into the dashboard contract; preview surfaces are disabled. Set{" "}
        <span className="rift-mono text-ink">VITE_RIFT_CONTROLLER_URL</span> only when the
        controller is not available through the same-origin proxy.
      </p>
    </Panel>
  );
}

function SourcesTab() {
  const { data, unavailable, error } = useSettings();
  if (unavailable || error) {
    return (
      <Unavailable
        endpoint="/v2/settings"
        resource="SettingsSnapshot { modelSources, gateway, services, policies, mesh }"
        reason={unavailable?.detail ?? error?.message}
      />
    );
  }
  const sources = Array.isArray(data?.modelSources.sources) ? data.modelSources.sources : [];
  return (
    <Panel title="Model sources" aside={<SourceBadge source="live" />} bodyClassName="p-0">
      {sources.length === 0 ? (
        <div className="p-4 text-[13px] text-ink-secondary">No model sources are configured.</div>
      ) : (
        <ul className="divide-y divide-border text-[13px]">
          {sources.map((entry, index) => {
            const source = asRecord(entry);
            const ready = String(source.status ?? "unknown") === "ready";
            return (
              <li
                key={String(source.id ?? index)}
                className="flex flex-wrap items-center gap-3 px-4 py-3"
              >
                <StatDot tone={ready ? "ok" : "muted"} />
                <span className="font-medium text-ink">{String(source.id ?? "source")}</span>
                <span className="rift-mono text-[11px] text-ink-secondary break-all">
                  {String(source.endpoint ?? source.path ?? "not specified")}
                </span>
                <span className="ml-auto rift-mono text-[11px] text-ink-secondary">
                  {String(source.status ?? "unknown")}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}

function BackendIntegrations() {
  const { data, unavailable, error, isLoading } = useBackends();
  if (unavailable || error)
    return (
      <Unavailable
        endpoint="/backends"
        resource="Backend provider detection"
        reason={unavailable?.detail ?? error?.message}
      />
    );
  if (isLoading)
    return (
      <Panel title="Backend integrations" aside={<SourceBadge source="live" />}>
        <p className="text-[13px] text-ink-secondary">Loading backend providers...</p>
      </Panel>
    );
  const providers =
    data?.providers && typeof data.providers === "object"
      ? Object.entries(data.providers as Record<string, unknown>)
      : [];
  return (
    <Panel title="Backend integrations" aside={<SourceBadge source="live" />} bodyClassName="p-0">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[680px] text-[12.5px]">
          <thead className="rift-label">
            <tr className="border-b border-border">
              <th className="h-9 px-4 text-left font-normal">Provider</th>
              <th className="px-4 text-left font-normal">Detected</th>
              <th className="px-4 text-left font-normal">Version</th>
              <th className="px-4 text-left font-normal">License</th>
              <th className="px-4 text-left font-normal">Lifecycle gate</th>
            </tr>
          </thead>
          <tbody>
            {providers.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-[13px] text-ink-secondary">
                  The live controller returned no backend providers.
                </td>
              </tr>
            ) : (
              providers.map(([name, value]) => {
                const provider = asRecord(value);
                const detection = asRecord(provider.detection);
                const gate = asRecord(provider.lifecycle_gate);
                const manifest = asRecord(provider.manifest);
                const available = detection.available === true;
                return (
                  <tr key={name} className="border-b border-border last:border-0">
                    <td className="px-4 py-3 font-medium text-ink">{name}</td>
                    <td className="px-4">
                      <span className="inline-flex items-center gap-2">
                        <StatDot tone={available ? "ok" : "muted"} />
                        {available ? "yes" : "no"}
                      </span>
                    </td>
                    <td className="px-4 rift-mono text-[11px] text-ink-secondary">
                      {String(detection.version ?? "not detected")}
                    </td>
                    <td className="px-4 rift-mono text-[11px]">
                      {String(detection.license ?? manifest.license ?? "unknown")}
                    </td>
                    <td className="px-4 rift-mono text-[11px] text-ink-secondary">
                      {String(gate.advertised_status ?? "unknown")}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function SecurityTab() {
  const { data, unavailable, error } = useSettings();
  if (unavailable || error) {
    return (
      <Unavailable
        endpoint="/v2/settings"
        resource="SettingsSnapshot { gateway, mesh, policies }"
        reason={unavailable?.detail ?? error?.message}
      />
    );
  }
  const gateway = data?.gateway ?? {};
  const mesh = data?.mesh ?? {};
  const securityWarnings = Array.isArray(gateway.security_warnings)
    ? gateway.security_warnings.map(String)
    : [];
  const corsOrigins = Array.isArray(gateway.cors_origins) ? gateway.cors_origins.map(String) : [];
  return (
    <div className="grid gap-4">
      {securityWarnings.length === 0 && (
        <div className="border border-ok/40 bg-ok/5 px-4 py-3 text-[12.5px] text-ink-secondary">
          No active exposure warnings. The gateway is not running, is loopback-bound, and has no
          configured CORS origins.
        </div>
      )}
      {securityWarnings.length > 0 && (
        <div
          className="border-2 border-error/60 bg-error/10 px-4 py-4 text-[13px] text-error"
          role="alert"
        >
          <div className="rift-label text-error">Security warnings require operator attention</div>
          <ul className="mt-2 grid gap-1 list-disc pl-4">
            {securityWarnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
          <p className="mt-3 text-[12px] text-error/90">
            Restrict the gateway to loopback or configure trusted origins and API keys before
            exposing it to a network.
          </p>
        </div>
      )}
      <Panel title="Gateway and credentials" aside={<SourceBadge source="live" />}>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <KV label="Gateway" value={String(gateway.status ?? "not_started")} />
          <KV label="Process" value={gateway.process_alive === true ? "alive" : "not running"} />
          <KV label="Stored key records" value={String(gateway.key_count ?? 0)} />
          <KV
            label="API-key protection"
            value={String(gateway.api_key_protection ?? "not reported")}
          />
          <KV label="Bound host" value={String(gateway.bound_host ?? "not reported")} />
          <KV
            label="CORS origins"
            value={corsOrigins.length ? corsOrigins.join(", ") : "none configured"}
          />
        </div>
        <p className="mt-4 text-[12px] text-ink-secondary">
          Secret values are never returned to the dashboard. Create or rotate keys through an
          explicit operator action.
        </p>
      </Panel>
      <Panel title="Mesh trust" aside={<SourceBadge source="live" />}>
        <div className="grid gap-4 sm:grid-cols-3">
          <KV label="Controller" value={String(mesh.controller_id ?? "not initialized")} />
          <KV label="Managed nodes" value={String(mesh.managed_nodes ?? 0)} />
          <KV
            label="Enrollment"
            value={String(asRecord(mesh.enrollment_window).open === true ? "open" : "closed")}
          />
        </div>
      </Panel>
    </div>
  );
}

function PoliciesTab() {
  const { data, unavailable, error } = useSettings();
  if (unavailable || error) {
    return (
      <Unavailable
        endpoint="/v2/settings"
        resource="SettingsSnapshot { policies, services }"
        reason={unavailable?.detail ?? error?.message}
      />
    );
  }
  const policies = data?.policies ?? {};
  return (
    <Panel title="Effective policy" aside={<SourceBadge source="live" />}>
      {Object.keys(policies).length === 0 ? (
        <p className="text-[13px] text-ink-secondary">
          The live controller returned no effective policies.
        </p>
      ) : (
        <div className="grid gap-3 text-[13px]">
          {Object.entries(policies).map(([key, value]) => (
            <div
              key={key}
              className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-2 last:border-0"
            >
              <span className="text-ink-secondary">{key.replaceAll("_", " ")}</span>
              <span className="rift-mono text-ink">{String(value)}</span>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}
