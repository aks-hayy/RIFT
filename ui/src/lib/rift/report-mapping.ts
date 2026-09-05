import type { Benchmark } from "./types";

type JsonObject = Record<string, unknown>;

function object(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonObject) : {};
}

function numeric(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function text(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function basename(value: string): string {
  return value.split(/[\\/]/).pop() ?? value;
}

function reportSummary(report: JsonObject): JsonObject {
  const summary = object(report.summary);
  return Object.keys(summary).length ? summary : report;
}

export function mapBenchmarkReport(entry: unknown, serviceId: string): Benchmark | null {
  const item = object(entry);
  const path = text(item.path);
  if (!path.toLowerCase().includes("benchmark") || path.toLowerCase().includes("cluster")) {
    return null;
  }

  const reportPayload = reportSummary(item);
  const nestedSummary = object(reportPayload.summary);
  const summary = Object.keys(nestedSummary).length ? nestedSummary : reportPayload;
  const metrics = object(summary.metrics);
  const backendTimings = object(summary.backend_timings);
  const cases = Array.isArray(reportPayload.cases)
    ? reportPayload.cases.map(object)
    : Array.isArray(item.cases)
      ? item.cases.map(object)
      : [];
  const caseSummaries = cases.map((value) => object(value.summary));
  const tokensPerSec = numeric(
    summary.decode_tokens_per_second,
    numeric(
      summary.tokens_per_second_estimate,
      numeric(
        summary.median_tokens_per_second,
        numeric(metrics.tokens_per_second, numeric(backendTimings.predicted_per_second)),
      ),
    ),
  );
  if (tokensPerSec <= 0) return null;

  const firstTokenSeconds = numeric(
    summary.time_to_first_token_seconds_estimate,
    numeric(
      summary.median_first_token_seconds,
      numeric(metrics.first_token_seconds, numeric(caseSummaries[0]?.median_first_token_seconds)),
    ),
  );
  const metadata = object(reportPayload.metadata ?? item.metadata);
  const launchPlan = object(metadata.launch_plan);
  const created =
    numeric(item.created_unix_seconds) ||
    numeric(reportPayload.created_unix_seconds) ||
    numeric(summary.created_unix_seconds) ||
    numeric(basename(path).split("-")[0]);
  return {
    id: basename(path),
    serviceId,
    measuredAt: new Date(created * 1000).toISOString(),
    tokensPerSec,
    firstTokenMs: Math.round(firstTokenSeconds * 1000),
    concurrency: numeric(summary.concurrency, numeric(launchPlan.concurrency, 1)),
    contextTokens: numeric(
      summary.context_tokens,
      numeric(summary.prompt_tokens, numeric(launchPlan.context_length, 0)),
    ),
    outputTokens: numeric(summary.generated_tokens_estimate, numeric(metrics.generated_tokens, 0)),
    provenance: "live",
  };
}
