export type TelemetryHistoryPoint = {
  observed_at: number;
  count: number;
  mean: number | null;
  minimum: number | null;
  maximum: number | null;
};

export type TelemetryHistorySeries = {
  id: string;
  unit: string;
  scope: string;
  points: TelemetryHistoryPoint[];
};

export type AlignedTelemetrySeries = {
  unit: string;
  scope: string;
  points: Array<Record<string, number | null> & { observed_at: number }>;
};

export function alignTelemetrySeries(series: TelemetryHistorySeries[]): AlignedTelemetrySeries {
  const units = new Set(series.map((item) => item.unit));
  const scopes = new Set(series.map((item) => item.scope));
  const ids = new Set(series.map((item) => item.id));
  if (ids.size !== series.length) throw new Error("series ids must be unique");
  if (units.size > 1) throw new Error("series units differ; overlay is not valid");
  if (scopes.size > 1) throw new Error("series scopes differ; overlay is not valid");

  const timestamps = [
    ...new Set(series.flatMap((item) => item.points.map((point) => point.observed_at))),
  ].sort((a, b) => a - b);
  const valuesBySeries = series.map((item) => {
    const values = new Map<number, number | null>();
    for (const point of item.points) {
      values.set(point.observed_at, point.count > 0 ? point.mean : null);
    }
    return { id: item.id, values };
  });

  return {
    unit: series[0]?.unit ?? "",
    scope: series[0]?.scope ?? "",
    points: timestamps.map((observed_at) => {
      const row: Record<string, number | null> & { observed_at: number } = { observed_at };
      for (const item of valuesBySeries) row[item.id] = item.values.get(observed_at) ?? null;
      return row;
    }),
  };
}
