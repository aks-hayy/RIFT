import { createFileRoute } from "@tanstack/react-router";
import { Gauge, SlidersHorizontal } from "lucide-react";
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
import { dateTime, number } from "@/lib/rift-api";

export const Route = createFileRoute("/benchmarks")({ component: BenchmarksPage });

function BenchmarksPage() {
  const [service, setService] = useState("chat");
  const reports = useRiftQuery<any>(riftKeys.reports, "/api/rift/reports");
  const benchmark = useRiftMutation<any>("/api/rift/benchmark", [riftKeys.reports]);
  const suite = useRiftMutation<any>("/api/rift/benchmark-suite", [riftKeys.reports]);
  const tune = useRiftMutation<any>("/api/rift/tune", [riftKeys.reports, riftKeys.services]);

  if (reports.isPending) return <LoadingState label="Loading benchmark history" />;
  if (reports.error)
    return <ErrorState error={reports.error} onRetry={() => void reports.refetch()} />;
  const result = suite.data ?? benchmark.data ?? tune.data;
  const summary = result?.summary ?? result?.measurement ?? result ?? {};
  const history = reports.data?.reports ?? [];

  return (
    <div>
      <PageHeader
        title="Benchmarks and tuning"
        subtitle="Fixed prompt suites, warmups, repeated measurements, median/p95 reporting, and last-known-good rollback."
        command={`rift benchmark --service ${service}`}
      />
      <div className="space-y-3 p-4">
        <Panel title="Measurement controls">
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-xs text-muted-foreground">
              Service
              <input
                value={service}
                onChange={(event) => setService(event.target.value)}
                className="mt-1 h-9 w-40 rounded-sm border border-input bg-background px-3 mono text-xs text-foreground"
              />
            </label>
            <button
              type="button"
              onClick={() => benchmark.mutate({ service, max_tokens: 64 })}
              disabled={benchmark.isPending}
              className="inline-flex h-9 items-center gap-2 rounded-sm border border-border px-3 text-xs hover:bg-surface disabled:opacity-50"
            >
              <Gauge className="h-3.5 w-3.5" /> Quick benchmark
            </button>
            <button
              type="button"
              onClick={() => suite.mutate({ service, warmups: 1, repetitions: 3 })}
              disabled={suite.isPending}
              className="inline-flex h-9 items-center gap-2 rounded-sm border border-primary/50 px-3 text-xs text-primary hover:bg-primary/10 disabled:opacity-50"
            >
              <Gauge className="h-3.5 w-3.5" /> Reproducible suite
            </button>
            <ConfirmAction
              label="Live tune"
              title={`Tune ${service}?`}
              description="RIFT will restart the backend for bounded candidate measurements and restore the baseline if a candidate fails or regresses."
              onConfirm={() =>
                tune.mutate({
                  service,
                  config: "rift.yaml",
                  live: true,
                  allow_restart: true,
                  candidate_limit: 4,
                  warmup_runs: 1,
                  repeats: 3,
                })
              }
              pending={tune.isPending}
              icon={<SlidersHorizontal className="h-3.5 w-3.5" />}
            />
          </div>
        </Panel>
        {(benchmark.error || suite.error || tune.error) && (
          <ErrorState error={benchmark.error || suite.error || tune.error} />
        )}
        <ResultBanner result={result} />

        {result && (
          <div className="grid gap-3 lg:grid-cols-4">
            <Panel>
              <Metric
                label="Median decode"
                value={number(
                  summary.median_tokens_per_second ??
                    summary.tokens_per_second_estimate ??
                    result.winning_score,
                )}
                unit="tok/s"
                tone="info"
              />
            </Panel>
            <Panel>
              <Metric label="P95 latency" value={number(summary.p95_elapsed_seconds)} unit="s" />
            </Panel>
            <Panel>
              <Metric label="Samples" value={summary.sample_count ?? result.repetitions ?? "--"} />
            </Panel>
            <Panel>
              <Metric
                label="Validity"
                value={summary.valid === false ? "failed" : "passed"}
                tone={summary.valid === false ? "err" : "ok"}
                hint={result.cache_state ?? result.mode}
              />
            </Panel>
          </div>
        )}

        <Panel title="Report history" padded={false}>
          {history.length === 0 ? (
            <div className="p-6 text-sm text-muted-foreground">
              No benchmark or tuning reports have been recorded.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-border bg-surface text-[10px] uppercase tracking-widest text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2">Created</th>
                    <th>Service</th>
                    <th>Mode</th>
                    <th>Outcome</th>
                    <th>Report</th>
                  </tr>
                </thead>
                <tbody>
                  {history.slice(0, 30).map((entry: any) => {
                    const item = entry.summary ?? {};
                    return (
                      <tr key={entry.path} className="border-b border-border/60 last:border-0">
                        <td className="px-3 py-2">{dateTime(item.created_unix_seconds)}</td>
                        <td className="mono">{item.service ?? item.metadata?.service ?? "--"}</td>
                        <td>
                          {item.mode ?? item.suite_id ?? item.measurement_mode ?? "benchmark"}
                        </td>
                        <td>
                          <Chip
                            tone={
                              item.applied === false || item.available === false ? "warn" : "ok"
                            }
                          >
                            {item.applied === false
                              ? "not applied"
                              : item.summary?.valid === false
                                ? "invalid"
                                : "recorded"}
                          </Chip>
                        </td>
                        <td
                          className="max-w-80 truncate mono text-muted-foreground"
                          title={entry.path}
                        >
                          {entry.path}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        {result && (
          <Panel title="Latest result">
            <JsonPreview value={result} />
          </Panel>
        )}
      </div>
    </div>
  );
}
