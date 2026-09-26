import { createFileRoute, Link } from "@tanstack/react-router";
import { PackageSearch, RefreshCw } from "lucide-react";
import { AppShell } from "@/components/rift/app-shell";
import { LiveState } from "@/components/rift/live-state";
import { PageHeader, Panel, SourceBadge, StatDot } from "@/components/rift/primitives";
import { bytes } from "@/lib/rift/format";
import { useLocalArtifacts } from "@/lib/rift/hooks";

export const Route = createFileRoute("/models/catalog")({
  head: () => ({ meta: [{ title: "Local Artifact Catalog — RIFT" }] }),
  component: LocalArtifactCatalogPage,
});

function LocalArtifactCatalogPage() {
  const artifacts = useLocalArtifacts();
  const rows = artifacts.data ?? [];
  return (
    <AppShell>
      <PageHeader
        eyebrow="Models / local inventory"
        title="Local artifact catalog"
        description="Artifacts registered in RIFT’s local manifest store. This view does not scan arbitrary folders or invent metadata."
        actions={
          <div className="flex gap-2">
            <button
              type="button"
              onClick={artifacts.refetch}
              className="inline-flex h-9 items-center gap-2 rounded-xl border border-border bg-white/70 px-3 text-[12px] font-medium hover:border-primary/35"
            >
              <RefreshCw className="size-3.5" aria-hidden /> Refresh
            </button>
            <Link
              to="/models"
              className="inline-flex h-9 items-center rounded-xl bg-primary px-3.5 text-[12px] font-medium text-primary-foreground"
            >
              Discover models
            </Link>
          </div>
        }
      />
      <div className="mx-auto grid max-w-[1400px] gap-4 px-4 py-6">
        <Panel
          title="Registered artifacts"
          aside={<SourceBadge source="live" />}
          bodyClassName="p-0"
        >
          <div className="p-4">
            <LiveState
              isLoading={artifacts.isLoading}
              hasData={artifacts.data !== undefined}
              unavailable={!!artifacts.unavailable}
              error={!!artifacts.error}
              empty={rows.length === 0}
              title="Local artifact inventory unavailable"
              loadingLabel="Reading RIFT’s artifact manifests…"
              emptyTitle="No registered artifacts"
              emptyDescription="No persisted artifact manifests were returned by the controller. Deployments and cached files are not inferred as catalog records."
              reason={artifacts.unavailable?.message ?? artifacts.error?.message}
              onRetry={artifacts.refetch}
            >
              <p className="text-[12px] text-ink-secondary">
                {rows.length} manifest{rows.length === 1 ? "" : "s"} returned by the local
                controller.
              </p>
            </LiveState>
          </div>
          {rows.length > 0 && (
            <div className="overflow-x-auto border-t border-border/70">
              <table className="w-full min-w-[780px] text-[12.5px]">
                <thead className="rift-label">
                  <tr className="border-b border-border">
                    <th className="h-10 px-4 text-left font-normal">Artifact</th>
                    <th className="px-4 text-left font-normal">Format / quantization</th>
                    <th className="px-4 text-right font-normal">Model size</th>
                    <th className="px-4 text-left font-normal">Integrity evidence</th>
                    <th className="px-4 text-left font-normal">License</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((artifact) => (
                    <tr
                      key={artifact.id}
                      className="border-b border-border/70 last:border-0 hover:bg-white/35"
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2 font-medium text-ink">
                          <PackageSearch className="size-4 text-primary" aria-hidden />
                          {artifact.displayName}
                        </div>
                        <div className="mt-1 rift-mono text-[10px] text-ink-muted">
                          manifest {artifact.id}
                        </div>
                      </td>
                      <td className="px-4 rift-mono text-[11px] text-ink-secondary">
                        {artifact.format} · {artifact.quantization || "quantization not reported"}
                      </td>
                      <td className="px-4 text-right rift-mono text-[11px]">
                        {artifact.sizeBytes ? bytes(artifact.sizeBytes) : "not reported"}
                      </td>
                      <td className="px-4">
                        <span className="inline-flex items-center gap-2">
                          <StatDot tone={artifact.trust === "verified" ? "ok" : "attention"} />
                          {artifact.trust === "verified"
                            ? "model file hashes verified"
                            : "hash verification not established"}
                        </span>
                      </td>
                      <td className="px-4 text-[11px] text-ink-secondary">{artifact.license}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>
    </AppShell>
  );
}
