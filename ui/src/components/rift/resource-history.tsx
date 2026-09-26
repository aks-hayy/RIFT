import { useMemo, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Panel } from "./primitives";
import { LiveState } from "./live-state";
import { useTelemetryLatest } from "@/lib/rift/hooks";
import { rift, RiftUnavailable } from "@/lib/rift/client";
import { alignTelemetrySeries } from "@/lib/rift/telemetry-series";
import type { ResourceHistory } from "@/lib/rift/types";

const metrics = {
  cpu_percent: { label: "Host CPU", unit: "%" },
  process_cpu_percent: { label: "Service CPU", unit: "%" },
  process_rss_bytes: { label: "Service memory", unit: "bytes" },
  host_ram_pressure_percent: { label: "Host RAM pressure", unit: "%" },
  gpu_utilization_percent: { label: "GPU utilization", unit: "%" },
  gpu_temperature_c: { label: "GPU temperature", unit: "°C" },
  gpu_vram_pressure_percent: { label: "GPU VRAM pressure", unit: "%" },
  gpu_power_watts: { label: "GPU power", unit: "W" },
};
type Metric = keyof typeof metrics;
type ViewMode = "overlay" | "compare";
const COLORS = ["var(--oxide)", "var(--verdigris)", "#7267b8", "#2f7ea0", "#c18b18", "#aa5267"];
const timeLabel = (seconds: number) =>
  new Date(seconds * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

export function ResourceHistoryPanel({
  serviceName,
  allowedMetrics,
}: {
  serviceName?: string;
  allowedMetrics?: string[];
}) {
  const sessions = useTelemetryLatest(serviceName);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [metric, setMetric] = useState<Metric>("cpu_percent");
  const [seconds, setSeconds] = useState(900);
  const [viewMode, setViewMode] = useState<ViewMode>("overlay");
  const selectableMetrics = (Object.keys(metrics) as Metric[]).filter(
    (key) => !allowedMetrics || allowedMetrics.includes(key),
  );
  const activeMetric = selectableMetrics.includes(metric)
    ? metric
    : (selectableMetrics[0] ?? "cpu_percent");
  const entries = sessions.data ?? [];
  const chosenIds = selectedIds.length
    ? selectedIds
    : entries.slice(0, 1).map(({ session }) => session.sessionId);
  const selectedSessions = selectableMetrics.length
    ? entries.filter(({ session }) => chosenIds.includes(session.sessionId))
    : [];
  const historyQueries = useQueries({
    queries: selectedSessions.map(({ session }) => ({
      queryKey: ["rift", "telemetry", "history", session.sessionId, activeMetric, seconds],
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        rift.resourceHistory(session.sessionId, activeMetric, seconds, signal),
      staleTime: 5_000,
      refetchInterval: 10_000,
      retry: false,
    })),
  });
  const loadingHistory = historyQueries.some((query) => query.isPending);
  const queryError = historyQueries.find((query) => query.error)?.error ?? null;
  const historyRows = selectedSessions.flatMap((entry, index) => {
    const history = historyQueries[index]?.data as ResourceHistory | undefined;
    if (!history) return [];
    return [
      {
        id: entry.session.sessionId,
        label: `${entry.session.serviceName} · ${entry.session.nodeId}`,
        unit: metrics[activeMetric].unit,
        scope: history.scope,
        points: history.points,
      },
    ];
  });
  const { aligned, alignmentError } = useMemo(() => {
    if (!historyRows.length) return { aligned: null, alignmentError: null };
    try {
      return { aligned: alignTelemetrySeries(historyRows), alignmentError: null };
    } catch (error) {
      return {
        aligned: null,
        alignmentError: error instanceof Error ? error.message : String(error),
      };
    }
  }, [historyRows]);
  const measured =
    aligned?.points.filter((point) => Object.values(point).some((value) => value !== null)) ?? [];
  const fieldClass =
    "h-9 rounded-xl border border-border/70 bg-white/75 px-3 text-[12px] shadow-sm outline-none transition focus:border-primary/40 focus:ring-2 focus:ring-primary/15";
  const sessionStateUnavailable = Boolean(sessions.unavailable);
  const sessionStateError = Boolean(sessions.error);

  return (
    <Panel
      title="Resource history"
      aside={
        <span className="rift-mono text-[11px] text-ink-secondary">
          {historyRows.length > 1 ? `${historyRows.length} selected` : "recorded · refresh 10s"}
        </span>
      }
    >
      <LiveState
        isLoading={sessions.isLoading}
        hasData={sessions.data !== undefined}
        empty={entries.length === 0}
        unavailable={sessionStateUnavailable}
        error={sessionStateError}
        reason={sessions.unavailable?.message ?? sessions.error?.message}
        emptyTitle="No active telemetry sessions"
        emptyDescription="History appears when RIFT has an active monitored service. No sample values are generated."
        onRetry={sessions.refetch}
      >
        <div className="grid gap-4">
          <div className="grid gap-3 rounded-xl border border-border/70 bg-white/40 p-3 sm:grid-cols-2 xl:grid-cols-[minmax(220px,1.4fr)_minmax(150px,0.8fr)_minmax(130px,0.7fr)_minmax(180px,0.9fr)]">
            <fieldset className="min-w-0">
              <legend className="mb-1.5 text-[11px] font-medium text-ink-secondary">
                Services / nodes
              </legend>
              <div className="grid max-h-24 gap-1 overflow-auto rounded-lg border border-border/70 bg-white/65 p-2">
                {entries.map(({ session }) => {
                  const checked = chosenIds.includes(session.sessionId);
                  return (
                    <label
                      key={session.sessionId}
                      className="flex min-w-0 cursor-pointer items-center gap-2 rounded-md px-1.5 py-1 text-[11.5px] hover:bg-primary/5"
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(event) => {
                          setSelectedIds((current) => {
                            const prior = current.length
                              ? current
                              : entries.slice(0, 1).map((item) => item.session.sessionId);
                            if (event.target.checked)
                              return [...new Set([...prior, session.sessionId])];
                            const next = prior.filter((id) => id !== session.sessionId);
                            return next.length ? next : [];
                          });
                        }}
                        aria-label={`Monitor ${session.serviceName} on ${session.nodeId}`}
                        className="accent-primary"
                      />
                      <span className="truncate">{session.serviceName}</span>
                      <span className="ml-auto shrink-0 rift-mono text-[10px] text-ink-muted">
                        {session.nodeId}
                      </span>
                    </label>
                  );
                })}
              </div>
            </fieldset>
            <label className="grid content-start gap-1.5 text-[11px] font-medium text-ink-secondary">
              Resource
              <select
                aria-label="Resource"
                className={fieldClass}
                value={activeMetric}
                onChange={(event) => setMetric(event.target.value as Metric)}
                disabled={!selectableMetrics.length}
              >
                {selectableMetrics.map((key) => (
                  <option key={key} value={key}>
                    {metrics[key].label} ({metrics[key].unit})
                  </option>
                ))}
              </select>
            </label>
            <label className="grid content-start gap-1.5 text-[11px] font-medium text-ink-secondary">
              Time range
              <select
                aria-label="Time range"
                className={fieldClass}
                value={seconds}
                onChange={(event) => setSeconds(Number(event.target.value))}
              >
                <option value={900}>15 minutes</option>
                <option value={3600}>1 hour</option>
                <option value={86400}>24 hours</option>
              </select>
            </label>
            <fieldset className="grid content-start gap-1.5">
              <legend className="text-[11px] font-medium text-ink-secondary">View</legend>
              <div className="flex h-9 rounded-xl border border-border/70 bg-white/65 p-0.5">
                {(["overlay", "compare"] as const).map((mode) => (
                  <button
                    type="button"
                    key={mode}
                    aria-pressed={viewMode === mode}
                    onClick={() => setViewMode(mode)}
                    className={`flex-1 rounded-[10px] px-2 text-[11px] capitalize transition-colors ${viewMode === mode ? "bg-primary text-white shadow-sm" : "text-ink-secondary hover:text-ink"}`}
                  >
                    {mode}
                  </button>
                ))}
              </div>
            </fieldset>
          </div>

          {queryError ? (
            <LiveState
              isLoading={false}
              hasData={false}
              unavailable={queryError instanceof RiftUnavailable}
              error={!(queryError instanceof RiftUnavailable)}
              reason={queryError.message}
              onRetry={() => void Promise.all(historyQueries.map((query) => query.refetch()))}
            >
              {null}
            </LiveState>
          ) : loadingHistory ? (
            <LiveState
              isLoading
              hasData={false}
              loadingLabel="Loading measured samples from the controller…"
            >
              {null}
            </LiveState>
          ) : !selectableMetrics.length ? (
            <LiveState
              isLoading={false}
              hasData={false}
              unsupported
              reason="This service has no compatible resource metrics available to chart."
            >
              {null}
            </LiveState>
          ) : !selectedSessions.length ? (
            <LiveState
              isLoading={false}
              hasData={false}
              emptyTitle="No selected session is active"
              emptyDescription="Choose an active monitored service or node above."
            >
              {null}
            </LiveState>
          ) : alignmentError ? (
            <LiveState
              isLoading={false}
              hasData={false}
              unsupported
              reason={`${alignmentError}. Choose a compatible scope before overlaying measurements.`}
            >
              {null}
            </LiveState>
          ) : !measured.length ? (
            <LiveState
              isLoading={false}
              hasData={Boolean(aligned)}
              empty
              emptyTitle="No measurements in this range"
              emptyDescription="RIFT returned no populated buckets. Missing sensors and samples remain gaps, not zeros."
            >
              {null}
            </LiveState>
          ) : viewMode === "overlay" ? (
            <HistoryChart
              data={aligned!.points}
              series={historyRows.map((item) => ({ id: item.id, label: item.label }))}
              unit={metrics[activeMetric].unit}
              seconds={seconds}
              scope={aligned!.scope}
            />
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              {historyRows.map((series, index) => (
                <HistoryChart
                  key={series.id}
                  data={aligned!.points}
                  series={[{ id: series.id, label: series.label }]}
                  unit={metrics[activeMetric].unit}
                  seconds={seconds}
                  scope={aligned!.scope}
                  color={COLORS[index % COLORS.length]}
                />
              ))}
            </div>
          )}
          <p className="text-[11px] leading-relaxed text-ink-secondary">
            Measured sample means by bucket · {metrics[activeMetric].unit} · scope:{" "}
            {aligned?.scope ?? "from controller"}. Host/GPU readings may include other services;
            missing buckets are not interpolated.
          </p>
        </div>
      </LiveState>
    </Panel>
  );
}

function HistoryChart({
  data,
  series,
  unit,
  seconds,
  scope,
  color,
}: {
  data: Array<Record<string, number | null> & { observed_at: number }>;
  series: Array<{ id: string; label: string }>;
  unit: string;
  seconds: number;
  scope: string;
  color?: string;
}) {
  const domain = [data[0]?.observed_at ?? 0, data.at(-1)?.observed_at ?? 0] as [number, number];
  return (
    <div
      className="h-64 min-w-0 rounded-xl border border-border/60 bg-white/55 p-2 pt-3 shadow-[inset_0_1px_0_rgba(255,255,255,.9)] sm:h-72 sm:p-3"
      role="img"
      aria-label={`${series.map((item) => item.label).join(", ")} ${unit} measurements over ${seconds / 60} minutes; scope ${scope}. Missing measurements are gaps. Data table follows.`}
    >
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={data}
          margin={{ top: 10, right: 12, bottom: 0, left: 0 }}
          accessibilityLayer
        >
          <CartesianGrid stroke="rgba(104, 106, 115, .16)" strokeDasharray="4 5" vertical={false} />
          <XAxis
            dataKey="observed_at"
            type="number"
            domain={domain}
            tickFormatter={timeLabel}
            tick={{ fontSize: 10, fill: "var(--ink-secondary)" }}
            axisLine={{ stroke: "var(--border-strong)" }}
            tickLine={false}
            minTickGap={28}
          />
          <YAxis
            unit={unit}
            tick={{ fontSize: 10, fill: "var(--ink-secondary)" }}
            axisLine={false}
            tickLine={false}
            width={56}
          />
          <Tooltip
            labelFormatter={(value) => timeLabel(Number(value))}
            formatter={(value, name) => [
              value == null ? "no sample" : `${Number(value).toFixed(1)} ${unit}`,
              name,
            ]}
            contentStyle={{
              borderRadius: 12,
              borderColor: "var(--border)",
              background: "rgba(255,255,255,.96)",
              boxShadow: "0 10px 30px rgba(30,20,22,.12)",
            }}
          />
          {series.map((item, index) => (
            <Line
              key={item.id}
              type="monotone"
              dataKey={item.id}
              name={item.label}
              stroke={color ?? COLORS[index % COLORS.length]}
              strokeWidth={2.5}
              activeDot={{ r: 4, strokeWidth: 2, fill: "white" }}
              dot={false}
              connectNulls={false}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
      <details className="mt-1 text-[11px] text-ink-secondary">
        <summary className="cursor-pointer px-1">View measured values</summary>
        <div className="mt-2 max-h-48 overflow-auto rounded-lg border border-border/60 bg-white/80">
          <table className="w-full text-left text-[11px]">
            <caption className="sr-only">Measured sample means and gaps in {unit}</caption>
            <thead className="sticky top-0 bg-surface/95">
              <tr>
                <th className="px-2 py-1.5 font-medium">Time</th>
                {series.map((item) => (
                  <th key={item.id} className="px-2 py-1.5 font-medium">
                    {item.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((point) => (
                <tr key={point.observed_at} className="border-t border-border/50">
                  <td className="px-2 py-1.5 rift-mono">{timeLabel(point.observed_at)}</td>
                  {series.map((item) => (
                    <td key={item.id} className="px-2 py-1.5 rift-mono">
                      {point[item.id] == null ? "—" : Number(point[item.id]).toFixed(1)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
