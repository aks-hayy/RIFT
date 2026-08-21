import { createFileRoute } from "@tanstack/react-router";
import { Search, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { ErrorState, JsonPreview, ResultBanner } from "@/components/console/live";
import { Chip, KV, Metric, PageHeader, Panel } from "@/components/console/primitives";
import { useRiftMutation } from "@/hooks/use-rift";
import { bytes, number, statusTone } from "@/lib/rift-api";

export const Route = createFileRoute("/models")({ component: ModelsPage });

function ModelsPage() {
  const [task, setTask] = useState("chat");
  const [formats, setFormats] = useState("gguf,gptq,awq,safetensors");
  const [maxGb, setMaxGb] = useState(12);
  const recommend = useRiftMutation<any>("/api/rift/recommend", []);
  const result = recommend.data;
  const best = result?.best_for_hardware?.absolute_best;
  const picks = result?.recommendations ?? [];

  return (
    <div>
      <PageHeader
        title="Model discovery"
        subtitle="Bounded Hub search with exact artifact selection, disk feasibility, provider fit, and evidence provenance."
        command={`rift recommend --task ${task}`}
      />
      <div className="space-y-3 p-4">
        <Panel title="Search policy">
          <div className="grid gap-3 md:grid-cols-[1fr_2fr_1fr_auto]">
            <label className="text-xs text-muted-foreground">
              Task
              <select
                value={task}
                onChange={(event) => setTask(event.target.value)}
                className="mt-1 h-9 w-full rounded-sm border border-input bg-background px-2 text-foreground"
              >
                <option value="chat">Chat</option>
                <option value="coding">Coding</option>
                <option value="structured">Structured</option>
              </select>
            </label>
            <label className="text-xs text-muted-foreground">
              Formats
              <input
                value={formats}
                onChange={(event) => setFormats(event.target.value)}
                className="mt-1 h-9 w-full rounded-sm border border-input bg-background px-2 mono text-xs text-foreground"
              />
            </label>
            <label className="text-xs text-muted-foreground">
              Max download GiB
              <input
                type="number"
                min={1}
                max={200}
                value={maxGb}
                onChange={(event) => setMaxGb(Number(event.target.value))}
                className="mt-1 h-9 w-full rounded-sm border border-input bg-background px-2 mono text-foreground"
              />
            </label>
            <button
              type="button"
              onClick={() =>
                recommend.mutate({
                  task,
                  formats,
                  max_download_gb: maxGb,
                  top: 10,
                  candidate_limit: 200,
                })
              }
              disabled={recommend.isPending}
              className="mt-auto inline-flex h-9 items-center justify-center gap-2 rounded-sm border border-primary/50 px-4 text-xs font-medium text-primary hover:bg-primary/10 disabled:opacity-50"
            >
              <Search className="h-3.5 w-3.5" />{" "}
              {recommend.isPending ? "Searching Hub" : "Recommend"}
            </button>
          </div>
        </Panel>

        {recommend.error && <ErrorState error={recommend.error} />}
        <ResultBanner result={result} />

        {!result && !recommend.isPending && (
          <Panel>
            <div className="py-10 text-center text-sm text-muted-foreground">
              Run recommendation to compare candidates for the live hardware profile.
            </div>
          </Panel>
        )}
        {recommend.isPending && (
          <Panel>
            <div className="py-10 text-center mono text-sm text-muted-foreground">
              Querying bounded Hub candidate arms and enriching finalists...
            </div>
          </Panel>
        )}

        {best && (
          <>
            <div className="grid gap-3 lg:grid-cols-4">
              <Panel>
                <Metric label="Best model" value={best.repo_id} tone="info" />
              </Panel>
              <Panel>
                <Metric
                  label="Selected artifact"
                  value={best.quantization ?? best.format}
                  hint={best.selected_file ?? "provisional"}
                />
              </Panel>
              <Panel>
                <Metric
                  label="Download"
                  value={best.selected_download_gb ?? "--"}
                  unit="GiB"
                  hint={best.download_size_source}
                />
              </Panel>
              <Panel>
                <Metric
                  label="Confidence"
                  value={number((best.confidence ?? 0) * 100, 1)}
                  unit="%"
                  hint={best.evidence_provenance?.highest_level ?? "metadata only"}
                />
              </Panel>
            </div>
            <div className="grid gap-3 xl:grid-cols-[1.2fr_1fr]">
              <Panel title="Decision evidence">
                <div className="mb-3 flex flex-wrap gap-2">
                  <Chip tone={statusTone(best.disk_feasibility?.status)}>
                    {best.disk_feasibility?.status ?? "disk unknown"}
                  </Chip>
                  <Chip tone={best.support_level === "UNSUPPORTED" ? "err" : "ok"}>
                    {best.support_level}
                  </Chip>
                  <Chip tone="info">{best.backend}</Chip>
                </div>
                <ul className="space-y-2 text-sm text-muted-foreground">
                  {(best.evidence ?? []).map((item: string) => (
                    <li key={item} className="flex gap-2">
                      <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
                      {item}
                    </li>
                  ))}
                </ul>
                {(best.warnings ?? []).length > 0 && (
                  <div className="mt-4 border-l-2 border-warn pl-3 text-xs text-warn">
                    {best.warnings.join(" / ")}
                  </div>
                )}
              </Panel>
              <Panel title="Artifact and fit">
                <KV k="Repository" v={best.repo_id} />
                <KV k="File" v={best.selected_file ?? "provisional"} />
                <KV k="Required disk" v={bytes(best.disk_feasibility?.required_bytes)} />
                <KV k="Usable disk" v={bytes(best.disk_feasibility?.usable_bytes)} />
                <KV
                  k="Parameters"
                  v={best.parameters_b != null ? `${best.parameters_b}B` : "unknown"}
                />
                <KV k="License" v={best.license ?? "unknown"} />
                <KV k="Evidence" v={best.evidence_provenance?.highest_level ?? "unknown"} />
              </Panel>
            </div>
          </>
        )}

        {picks.length > 0 && (
          <Panel title="Ranked candidates" padded={false}>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-border bg-surface text-[10px] uppercase tracking-widest text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2">Rank</th>
                    <th>Model</th>
                    <th>Artifact</th>
                    <th>Backend</th>
                    <th>Score</th>
                    <th>Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {picks.map((pick: any, index: number) => (
                    <tr key={pick.repo_id} className="border-b border-border/60 last:border-0">
                      <td className="px-3 py-2 mono">{index + 1}</td>
                      <td className="font-medium">{pick.repo_id}</td>
                      <td className="mono">{pick.quantization ?? pick.format}</td>
                      <td>{pick.backend}</td>
                      <td className="mono">{number(pick.final_score, 3)}</td>
                      <td>
                        <Chip
                          tone={
                            pick.evidence_provenance?.highest_level === "VERIFIED_LOCAL"
                              ? "ok"
                              : "warn"
                          }
                        >
                          {pick.evidence_provenance?.highest_level ?? "metadata"}
                        </Chip>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        )}

        {result && (
          <Panel title="Raw recommendation report">
            <JsonPreview value={result} />
          </Panel>
        )}
      </div>
    </div>
  );
}
