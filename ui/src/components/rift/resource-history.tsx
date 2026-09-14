import { useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Panel } from "./primitives";
import { useResourceHistory, useTelemetryLatest } from "@/lib/rift/hooks";

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
const timeLabel = (seconds: number) => new Date(seconds * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

export function ResourceHistoryPanel({ serviceName, allowedMetrics }: { serviceName?: string; allowedMetrics?: string[] }) {
  const sessions = useTelemetryLatest(serviceName);
  const [selected, setSelected] = useState("");
  const selectableMetrics = Object.keys(metrics).filter((key) => !allowedMetrics || allowedMetrics.includes(key)) as Metric[];
  const [metric, setMetric] = useState<Metric>(selectableMetrics[0] ?? "cpu_percent");
  const [seconds, setSeconds] = useState(900);
  const activeMetric = selectableMetrics.includes(metric) ? metric : selectableMetrics[0] ?? "cpu_percent";
  const entries = sessions.data ?? [];
  const session = entries.find((entry) => entry.session.sessionId === selected)?.session ?? entries[0]?.session;
  const history = useResourceHistory(session?.sessionId, activeMetric, seconds);
  const points = history.data?.points ?? [];
  const measured = points.filter((point) => point.count > 0 && point.mean !== null);
  const fieldClass = "h-9 rounded-[4px] border border-border bg-raised px-2 text-[12px]";

  return <Panel title="Resource history" aside={<span className="rift-mono text-[11px] text-ink-secondary">recorded · refresh 10s</span>}>
    {!session ? <p className="text-[13px] text-ink-secondary">{sessions.isLoading ? "Loading telemetry sessions…" : "No active telemetry session. History appears when a monitored service is running."}</p> : <>
      <div className="flex flex-wrap gap-2 mb-3">
        <label className="grid gap-1 text-[11px]">Observed session
          <select aria-label="Observed session" className={fieldClass} value={session.sessionId} onChange={(event) => setSelected(event.target.value)}>
            {entries.map(({ session: item }) => <option key={item.sessionId} value={item.sessionId}>{item.serviceName} · {item.nodeId}</option>)}
          </select>
        </label>
        <label className="grid gap-1 text-[11px]">Resource
          <select aria-label="Resource" className={fieldClass} value={activeMetric} onChange={(event) => setMetric(event.target.value as Metric)} disabled={!selectableMetrics.length}>
            {selectableMetrics.map((key) => <option key={key} value={key}>{metrics[key].label} ({metrics[key].unit})</option>)}
          </select>
        </label>
        <label className="grid gap-1 text-[11px]">Time range
          <select aria-label="Time range" className={fieldClass} value={seconds} onChange={(event) => setSeconds(Number(event.target.value))}>
            <option value={900}>15 minutes</option><option value={3600}>1 hour</option><option value={86400}>24 hours</option>
          </select>
        </label>
      </div>
      {history.unavailable ? <p role="status" className="text-[13px] text-ink-secondary">Resource history is unavailable from this controller.</p>
        : history.isLoading ? <p role="status" className="text-[13px]">Loading recorded history…</p>
        : !measured.length ? <p role="status" className="text-[13px] text-ink-secondary">No measurements for this resource in the selected range. Missing sensors are not recorded as zero.</p>
        : <>
          <div className="h-56 w-full" role="img" aria-label={`${metrics[activeMetric].label} over the last ${seconds / 60} minutes. Mean and peak per bucket. Missing measurements are gaps. Data table follows.`}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={points} margin={{ top: 10, right: 12, bottom: 0, left: 0 }} accessibilityLayer>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis dataKey="observed_at" type="number" domain={[history.data!.since, history.data!.until]} tickFormatter={timeLabel} tick={{ fontSize: 10 }} />
                <YAxis unit={metrics[activeMetric].unit} tick={{ fontSize: 10 }} width={55} />
                <Tooltip labelFormatter={(value) => timeLabel(Number(value))} formatter={(value) => `${Number(value).toFixed(1)} ${metrics[activeMetric].unit}`} />
                <Line type="linear" dataKey="mean" name="Sample mean" stroke="var(--oxide, #d94f3d)" strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} />
                <Line type="linear" dataKey="maximum" name="Bucket peak" stroke="var(--ink-secondary, #65716d)" strokeDasharray="4 3" dot={false} connectNulls={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <details className="mt-2 text-[12px]">
            <summary className="cursor-pointer">View recorded values ({measured.length} populated buckets)</summary>
            <div className="max-h-56 overflow-auto mt-2"><table className="w-full text-left">
            <caption className="text-left">{metrics[activeMetric].label} ({metrics[activeMetric].unit})</caption>
              <thead><tr><th>Time</th><th>Mean</th><th>Minimum</th><th>Peak</th><th>Samples</th></tr></thead>
              <tbody>{points.map((point) => <tr key={point.observed_at}>
                <td>{timeLabel(point.observed_at)}</td><td>{point.mean?.toFixed(1) ?? "—"}</td><td>{point.minimum?.toFixed(1) ?? "—"}</td><td>{point.maximum?.toFixed(1) ?? "—"}</td><td>{point.count}</td>
              </tr>)}</tbody>
            </table></div>
          </details>
        </>}
      <p className="mt-3 text-[11px] text-ink-secondary">Current process session only. Host/GPU readings can include other services; they are not exclusive service usage. Lines show sample means and peaks, not percentiles. Gaps mean no retained measurement.</p>
    </>}
  </Panel>;
}
