import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Search, Sparkles } from "lucide-react";
import { AppShell } from "@/components/rift/app-shell";
import { PageHeader, Panel, SourceBadge, StatDot } from "@/components/rift/primitives";
import { Unavailable } from "@/components/rift/unavailable";
import { useRecommendations, useServices } from "@/lib/rift/hooks";
import { bytes } from "@/lib/rift/format";
import type { ModelArtifact, ModelRecommendation, UseCase } from "@/lib/rift/types";

export const Route = createFileRoute("/models")({
  head: () => ({
    meta: [
      { title: "Models - RIFT" },
      {
        name: "description",
        content: "Active model artifacts and hardware-aware model discovery.",
      },
    ],
  }),
  component: ModelsPage,
});

function ModelsPage() {
  const services = useServices();
  const [task, setTask] = useState<UseCase>("chat");
  const [search, setSearch] = useState<UseCase | null>(null);
  const recommendations = useRecommendations(
    search ? { useCase: search, source: "huggingface" } : null,
  );
  const active = (services.data ?? []).map((service): ModelArtifact => ({
    id: service.artifactId,
    displayName:
      service.details?.modelPath?.replace(/\\/g, "/").split("/").pop() || service.artifactId,
    family: "controller-managed",
    parameters: "from artifact metadata",
    source: "local",
    format: service.artifactId.toLowerCase().endsWith(".gguf") ? "gguf" : "hf",
    quantization: service.artifactId.toLowerCase().includes("q8") ? "q8_0" : "none",
    sizeBytes: 0,
    license: "see model card",
    trust: "community",
    provenance: "derived-live",
  }));

  return (
    <AppShell>
      <PageHeader
        eyebrow="Catalog"
        title="Models"
        description="See what is deployed now, then let RIFT discover and rank Hugging Face models for this machine. No repository ID is required."
        actions={
          <div className="flex items-center gap-2">
            <select
              value={task}
              onChange={(event) => setTask(event.target.value as UseCase)}
              className="h-9 rounded-[4px] border border-border bg-raised px-3 text-[12.5px] text-ink"
              aria-label="Recommendation task"
            >
              <option value="chat">Chat</option>
              <option value="coding">Coding</option>
              <option value="documents">Documents</option>
              <option value="agent">Agent</option>
            </select>
            <button
              type="button"
              onClick={() => setSearch(task)}
              className="inline-flex h-9 items-center gap-2 rounded-[4px] bg-primary px-3.5 text-[13px] font-medium text-primary-foreground hover:bg-[color:var(--oxide-deep)]"
            >
              <Search className="size-4" aria-hidden />
              Find the best model
            </button>
          </div>
        }
      />
      <div className="max-w-[1400px] mx-auto px-4 py-6 grid gap-4">
        <Panel
          title="Active artifacts"
          aside={<SourceBadge source="derived-live" />}
          bodyClassName="p-0"
        >
          {services.unavailable ? (
            <div className="p-4">
              <Unavailable endpoint="/services" resource="Controller-managed services" />
            </div>
          ) : services.isLoading || !services.data ? (
            <div className="px-4 py-10 text-center text-[13px] text-ink-secondary">
              Loading managed artifacts...
            </div>
          ) : active.length === 0 ? (
            <div className="px-4 py-10 text-center text-[13px] text-ink-secondary">
              No model artifacts are attached to a managed service.
            </div>
          ) : (
            <ArtifactTable artifacts={active} />
          )}
        </Panel>

        {search && (
          <Panel
            title={`Hardware-aware recommendations / ${search}`}
            aside={<SourceBadge source="live" />}
            bodyClassName="p-0"
          >
            {recommendations.isLoading ? (
              <div className="px-4 py-12 text-center text-[13px] text-ink-secondary">
                Searching Hugging Face's indexed catalog, enriching finalists, and scoring hardware
                fit...
              </div>
            ) : recommendations.unavailable ? (
              <div className="p-4">
                <Unavailable
                  endpoint="/recommend"
                  method="POST"
                  resource="Hardware-aware Hugging Face recommendations"
                  reason={recommendations.unavailable.message}
                />
              </div>
            ) : recommendations.error ? (
              <div className="px-4 py-8 text-[13px] text-error">
                {recommendations.error.message}
              </div>
            ) : (
              <RecommendationTable rows={recommendations.data ?? []} />
            )}
          </Panel>
        )}

        {!search && (
          <Panel title="Model discovery" aside={<SourceBadge source="live" />}>
            <div className="px-4 py-10 text-center text-[13px] text-ink-secondary">
              Choose a task and start discovery. RIFT will show only live controller results; no
              catalog records are fabricated when the controller has no data.
            </div>
          </Panel>
        )}
      </div>
    </AppShell>
  );
}

function ArtifactTable({ artifacts }: { artifacts: ModelArtifact[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] text-[13px]">
        <thead className="rift-label">
          <tr className="border-b border-border">
            <th className="h-9 px-4 text-left font-normal">Artifact</th>
            <th className="px-4 text-left font-normal">Format</th>
            <th className="px-4 text-left font-normal">Parameters</th>
            <th className="px-4 text-left font-normal">Size</th>
            <th className="px-4 text-left font-normal">Trust</th>
            <th className="px-4 text-left font-normal">Source</th>
          </tr>
        </thead>
        <tbody>
          {artifacts.map((artifact) => (
            <tr key={artifact.id} className="border-b border-border last:border-0">
              <td className="px-4 py-3">
                <div className="font-medium text-ink">{artifact.displayName}</div>
                <div className="rift-mono text-[10.5px] text-ink-secondary">{artifact.id}</div>
              </td>
              <td className="px-4 rift-mono text-[12px]">
                {artifact.format} / {artifact.quantization}
              </td>
              <td className="px-4 rift-mono text-[12px]">{artifact.parameters}</td>
              <td className="px-4 rift-mono text-[12px]">
                {artifact.sizeBytes ? bytes(artifact.sizeBytes) : "controller metadata pending"}
              </td>
              <td className="px-4">
                <span className="inline-flex items-center gap-2">
                  <StatDot tone={artifact.trust === "verified" ? "ok" : "attention"} />
                  {artifact.trust}
                </span>
              </td>
              <td className="px-4">
                <SourceBadge source={artifact.provenance} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RecommendationTable({ rows }: { rows: ModelRecommendation[] }) {
  if (rows.length === 0) {
    return (
      <div className="px-4 py-10 text-center text-[13px] text-ink-secondary">
        No compatible candidates survived the current hardware and storage filters.
      </div>
    );
  }
  return (
    <ul className="divide-y divide-border">
      {rows.map((row, index) => (
        <li
          key={row.id ?? row.artifact.id}
          className="px-4 py-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto]"
        >
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              {index === 0 && <Sparkles className="size-4 text-primary" aria-hidden />}
              <span className="font-medium text-ink">{row.artifact.displayName}</span>
              <SourceBadge source={row.provenance} />
            </div>
            <div className="mt-1 rift-mono text-[11px] text-ink-secondary">
              {row.artifact.id} · {row.artifact.format} · {row.backend.kind}
            </div>
            <p className="mt-2 max-w-3xl text-[12.5px] text-ink-secondary">{row.rationale}</p>
            {row.warnings.length > 0 && (
              <p className="mt-2 text-[11.5px] text-attention">{row.warnings.join(" · ")}</p>
            )}
          </div>
          <div className="grid grid-cols-3 gap-5 lg:min-w-[340px]">
            <Metric label="Quality proxy" value={`${row.quality.score}/100`} />
            <Metric label="Download" value={bytes(row.resources.diskBytes)} />
            <Metric label="Target" value={row.targetNode} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="rift-label">{label}</div>
      <div className="mt-1 rift-mono text-[12px] text-ink">{value}</div>
    </div>
  );
}
