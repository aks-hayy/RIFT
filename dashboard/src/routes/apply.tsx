import { createFileRoute } from "@tanstack/react-router";
import { Download, PackagePlus, Play, SlidersHorizontal } from "lucide-react";
import { useState } from "react";
import type { ReactNode } from "react";

import { ConfirmAction, ErrorState, JsonPreview, ResultBanner } from "@/components/console/live";
import { Chip, PageHeader, Panel } from "@/components/console/primitives";
import { riftKeys, useRiftMutation } from "@/hooks/use-rift";

export const Route = createFileRoute("/apply")({ component: ApplyPage });

function ApplyPage() {
  const [config, setConfig] = useState(".rift/generated/rift.generated.yaml");
  const [allowDownload, setAllowDownload] = useState(false);
  const [allowInstall, setAllowInstall] = useState(false);
  const [allowLaunch, setAllowLaunch] = useState(false);
  const [allowRemote, setAllowRemote] = useState(false);
  const [optimize, setOptimize] = useState(false);
  const apply = useRiftMutation<any>("/api/rift/apply", [
    riftKeys.state,
    riftKeys.services,
    riftKeys.plan,
  ]);

  const payload = {
    config,
    allow_download: allowDownload,
    allow_install: allowInstall,
    allow_launch: allowLaunch,
    allow_remote: allowRemote,
    optimize,
    write_back: false,
  };

  return (
    <div>
      <PageHeader
        title="Apply"
        subtitle="Apply declared intent with explicit permission for every side effect. The original YAML is never overwritten."
        command={`rift apply --config ${config}${optimize ? " --optimize" : ""}`}
      />
      <div className="space-y-3 p-4">
        <Panel title="Execution permissions">
          <label className="block text-xs text-muted-foreground">
            Config path
            <input
              value={config}
              onChange={(event) => setConfig(event.target.value)}
              className="mt-1 h-9 w-full rounded-sm border border-input bg-background px-3 mono text-xs text-foreground"
            />
          </label>
          <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-5">
            <Permission
              label="Download model artifacts"
              checked={allowDownload}
              onChange={setAllowDownload}
              icon={<Download className="h-4 w-4" />}
            />
            <Permission
              label="Install backend"
              checked={allowInstall}
              onChange={setAllowInstall}
              icon={<PackagePlus className="h-4 w-4" />}
            />
            <Permission
              label="Launch services"
              checked={allowLaunch}
              onChange={setAllowLaunch}
              icon={<Play className="h-4 w-4" />}
            />
            <Permission
              label="Execute remotely"
              checked={allowRemote}
              onChange={setAllowRemote}
              icon={<Play className="h-4 w-4" />}
            />
            <Permission
              label="Benchmark and tune"
              checked={optimize}
              onChange={setOptimize}
              icon={<SlidersHorizontal className="h-4 w-4" />}
            />
          </div>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
            <div className="flex flex-wrap gap-2">
              <Chip tone={allowDownload ? "warn" : "neutral"}>
                download {allowDownload ? "allowed" : "blocked"}
              </Chip>
              <Chip tone={allowInstall ? "warn" : "neutral"}>
                install {allowInstall ? "allowed" : "blocked"}
              </Chip>
              <Chip tone={allowLaunch ? "warn" : "neutral"}>
                launch {allowLaunch ? "allowed" : "blocked"}
              </Chip>
              <Chip tone={allowRemote ? "err" : "neutral"}>
                remote {allowRemote ? "allowed" : "blocked"}
              </Chip>
            </div>
            <ConfirmAction
              label={optimize ? "Apply and optimize" : "Apply exact config"}
              title="Apply this RIFT deployment?"
              description="RIFT will perform only the side effects enabled above. Download, install, launch, and remote execution remain independently gated."
              pending={apply.isPending}
              onConfirm={() => apply.mutate(payload)}
            />
          </div>
        </Panel>

        {apply.error && <ErrorState error={apply.error} />}
        <ResultBanner result={apply.data} />
        {apply.data && (
          <>
            <Panel title="Apply outcome">
              <div className="flex flex-wrap items-center gap-3">
                <Chip tone={apply.data.applied ? "ok" : "warn"}>
                  {apply.data.applied ? "applied" : "not applied"}
                </Chip>
                <span className="text-sm text-muted-foreground">
                  {apply.data.reason ??
                    (apply.data.applied
                      ? "Desired state was written."
                      : "Review required permissions and plan errors.")}
                </span>
              </div>
              {(apply.data.required_permissions ?? []).length > 0 && (
                <div className="mt-3 text-xs text-warn">
                  Required: {apply.data.required_permissions.join(", ")}
                </div>
              )}
            </Panel>
            <Panel title="Raw operation result">
              <JsonPreview value={apply.data} />
            </Panel>
          </>
        )}
      </div>
    </div>
  );
}

function Permission({
  label,
  checked,
  onChange,
  icon,
}: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  icon: ReactNode;
}) {
  return (
    <label
      className={`flex cursor-pointer items-center gap-3 border p-3 text-sm ${checked ? "border-primary/50 bg-primary/10" : "border-border bg-background"}`}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="h-4 w-4 accent-[var(--color-primary)]"
      />
      <span className={checked ? "text-primary" : "text-muted-foreground"}>{icon}</span>
      <span>{label}</span>
    </label>
  );
}
