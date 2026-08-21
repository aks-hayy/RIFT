import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { z } from "zod";
import { AppShell } from "@/components/rift/app-shell";
import { PageHeader, Panel, KV, SourceBadge, StatDot } from "@/components/rift/primitives";
import { Unavailable } from "@/components/rift/unavailable";
import { cn } from "@/lib/utils";
import { rift } from "@/lib/rift/client";
import { useBackends } from "@/lib/rift/hooks";

const searchSchema = z.object({
  tab: z
    .enum(["controller", "sources", "security", "policies", "users", "integrations"])
    .catch("controller"),
});

export const Route = createFileRoute("/settings")({
  validateSearch: searchSchema,
  head: () => ({
    meta: [
      { title: "Settings — RIFT" },
      {
        name: "description",
        content: "Controller, sources, security, policies, users, integrations.",
      },
      { property: "og:title", content: "Settings — RIFT" },
      {
        property: "og:description",
        content: "Controller, sources, security, policies, users, integrations.",
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
  { id: "users", label: "Users" },
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
        {tab === "sources" && <SourcesPreview />}
        {tab === "security" && <SecurityTab />}
        {tab === "policies" && (
          <Unavailable
            endpoint="/v1/settings/policies"
            resource="Policy[] { id, scope, requiresConfirmation, allowedActions }"
            hint="Policies replace multi-checkbox permission prompts with reusable rules."
          />
        )}
        {tab === "users" && (
          <Unavailable
            endpoint="/v1/settings/users"
            resource="User[] { email, role, lastActiveAt }"
          />
        )}
        {tab === "integrations" && <BackendIntegrations />}
      </div>
    </AppShell>
  );
}

function ControllerTab() {
  const connection = rift.connectionInfo();
  return (
    <Panel title="Controller" aside={<SourceBadge source="live" />}>
      <div className="grid sm:grid-cols-3 gap-4">
        <KV label="URL" value={connection.root} />
        <KV label="Adapter" value={connection.mode} />
        <KV label="Preview surfaces" value={connection.previewEnabled ? "enabled" : "disabled"} />
      </div>
      <p className="mt-4 text-[12.5px] text-ink-secondary max-w-2xl">
        The console uses the live legacy controller through a typed compatibility adapter. Set{" "}
        <span className="rift-mono text-ink">VITE_RIFT_CONTROLLER_URL</span> only when the
        controller is not available through the same-origin proxy.
      </p>
    </Panel>
  );
}

function SourcesPreview() {
  return (
    <Panel
      title="Model sources / contract preview"
      aside={<SourceBadge source="preview" />}
      bodyClassName="p-0"
    >
      <div className="border-b border-border bg-attention/5 px-4 py-2 text-[11.5px] text-ink-secondary">
        These rows demonstrate the future source registry. Credentials and verification are not
        wired yet.
      </div>
      <ul className="divide-y divide-border text-[13px]">
        <li className="flex items-center gap-3 px-4 py-3">
          <StatDot tone="info" />
          <span className="font-medium text-ink">Hugging Face Hub</span>
          <span className="rift-mono text-[11px] text-ink-secondary">https://huggingface.co</span>
          <span className="ml-auto rift-mono text-[11px] text-attention">preview</span>
        </li>
        <li className="flex items-center gap-3 px-4 py-3">
          <StatDot tone="info" />
          <span className="font-medium text-ink">Local model directory</span>
          <span className="rift-mono text-[11px] text-ink-secondary">.rift/models</span>
          <span className="ml-auto rift-mono text-[11px] text-attention">preview</span>
        </li>
      </ul>
    </Panel>
  );
}

function BackendIntegrations() {
  const { data, unavailable } = useBackends();
  if (unavailable)
    return <Unavailable endpoint="/backends" resource="Backend provider detection" />;
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
            {providers.map(([name, value]) => {
              const provider = asRecord(value);
              const detection = asRecord(provider.detection);
              const gate = asRecord(provider.lifecycle_gate);
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
                    {String(detection.version ?? "--")}
                  </td>
                  <td className="px-4 rift-mono text-[11px]">
                    {String(detection.license ?? "unknown")}
                  </td>
                  <td className="px-4 rift-mono text-[11px] text-ink-secondary">
                    {String(gate.advertised_status ?? "unknown")}
                  </td>
                </tr>
              );
            })}
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
  return (
    <div className="grid gap-4">
      <Panel title="Enrollment tokens">
        <Unavailable
          endpoint="/v1/settings/tokens"
          resource="EnrollmentToken[] { token (redacted), expiresAt, createdBy, usedAt? }"
          hint="Tokens are one-time and expire. Never revealed after creation."
        />
      </Panel>
      <Panel title="Service API keys">
        <Unavailable
          endpoint="/v1/settings/api-keys"
          resource="ApiKey[] { id, label, prefix, createdAt, lastUsedAt }"
          hint="Only the key prefix is stored; the full value is shown once at creation and never again."
        />
      </Panel>
    </div>
  );
}
