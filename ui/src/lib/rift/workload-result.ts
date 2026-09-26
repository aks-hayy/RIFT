type ObjectValue = Record<string, unknown>;

function object(value: unknown): ObjectValue | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as ObjectValue)
    : null;
}

function number(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function string(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

export function summarizeWorkloadRun(result: unknown, status: string) {
  const root = object(result);
  const deployment = object(root?.deployment);
  const plan = object(deployment?.plan);
  const services = object(plan?.services);
  const serviceEntry = services ? Object.entries(services)[0] : undefined;
  const serviceName = serviceEntry?.[0] ?? null;
  const service = object(serviceEntry?.[1]);
  const model = object(service?.model);
  const benchmark = object(root?.benchmark);
  const benchmarkSummary = object(benchmark?.summary);
  const evaluation = object(root?.evaluation);
  const evaluationSummary = object(evaluation?.summary);
  const acceptance = object(root?.acceptance);
  const serving = object(service?.serving);

  return {
    status,
    serviceName,
    backend: string(service?.backend),
    model:
      string(model?.selected_file) ??
      string(model?.id) ??
      string(object(model?.artifact)?.artifact_id),
    modelSource: string(model?.source),
    contextTokens: number(serving?.context_length),
    concurrency: number(serving?.concurrency),
    decodeTokensPerSecond: number(benchmarkSummary?.median_tokens_per_second),
    benchmarkSamples: number(benchmarkSummary?.sample_count),
    benchmarkCases: number(benchmarkSummary?.case_count),
    evaluationPassed: acceptance?.evaluation_passed === true,
    evaluationPasses: number(evaluationSummary?.pass),
    evaluationFailures:
      (number(evaluationSummary?.fail) ?? 0) + (number(evaluationSummary?.error) ?? 0),
    endpoint: string(object(service?.health)?.url),
    applied: deployment?.applied === true,
  };
}
