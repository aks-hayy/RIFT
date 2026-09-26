import { createFileRoute } from "@tanstack/react-router";
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { RefreshCw, Search, Sparkles } from "lucide-react";
import { AppShell } from "@/components/rift/app-shell";
import { PageHeader, Panel, SourceBadge } from "@/components/rift/primitives";
import { Unavailable } from "@/components/rift/unavailable";
import { useRecommendations } from "@/lib/rift/hooks";
import { bytes } from "@/lib/rift/format";
import type { ModelRecommendation, UseCase } from "@/lib/rift/types";

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
  const [task, setTask] = useState<UseCase>("chat");
  const [search, setSearch] = useState<UseCase | null>(null);
  const [attempt, setAttempt] = useState(0);
  const recommendations = useRecommendations(
    search ? { useCase: search, source: "huggingface", refresh: attempt > 0 } : null,
  );
  return (
    <AppShell>
      <PageHeader
        eyebrow="Model discovery"
        title="Find a model for this machine"
        description="Run RIFT’s live hardware-aware discovery. Results come from the controller and retain their measured, estimated, and repository provenance."
        actions={
          <div className="flex items-center gap-2">
            <Link
              to="/models/catalog"
              className="inline-flex h-9 items-center rounded-xl border border-border bg-white/70 px-3 text-[12px] font-medium text-ink hover:border-primary/35 hover:text-primary"
            >
              Local artifact catalog
            </Link>
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
              onClick={() => {
                setAttempt(0);
                setSearch(task);
              }}
              className="inline-flex h-9 items-center gap-2 rounded-[4px] bg-primary px-3.5 text-[13px] font-medium text-primary-foreground hover:bg-[color:var(--oxide-deep)]"
            >
              <Search className="size-4" aria-hidden />
              Find the best model
            </button>
          </div>
        }
      />
      <div className="max-w-[1400px] mx-auto px-4 py-6 grid gap-4">
        {search && (
          <Panel
            title={`Hardware-aware recommendations / ${search}`}
            aside={
              <div className="flex items-center gap-3">
                <SourceBadge source="live" />
                <button
                  type="button"
                  onClick={() => setAttempt((value) => value + 1)}
                  className="inline-flex items-center gap-1 text-[11px] text-primary hover:text-ink"
                >
                  <RefreshCw className="size-3" aria-hidden /> Refresh search
                </button>
              </div>
            }
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
          <Panel title="Ready to discover" aside={<SourceBadge source="live" />}>
            <div className="px-4 py-10 text-center text-[13px] text-ink-secondary">
              Select a workload category and start a fresh controller-backed discovery run.
            </div>
          </Panel>
        )}
      </div>
    </AppShell>
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
