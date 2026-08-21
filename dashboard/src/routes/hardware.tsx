import { createFileRoute } from "@tanstack/react-router";
import { Gauge, RefreshCw } from "lucide-react";

import { ErrorState, JsonPreview, LoadingState, ResultBanner } from "@/components/console/live";
import { Bar, Chip, KV, Metric, PageHeader, Panel } from "@/components/console/primitives";
import { riftKeys, useRiftMutation, useRiftQuery } from "@/hooks/use-rift";
import { bytes, number, statusTone } from "@/lib/rift-api";

export const Route = createFileRoute("/hardware")({ component: HardwarePage });

function HardwarePage() {
  const hardware = useRiftQuery<any>(riftKeys.hardware, "/api/rift/hardware", {
    refetchInterval: 15_000,
  });
  const discovery = useRiftQuery<any>(riftKeys.discovery, "/api/rift/discovery");
  const calibrate = useRiftMutation<any>("/api/rift/calibrate", [riftKeys.hardware]);

  if (hardware.isPending) return <LoadingState label="Reading hardware profile" />;
  if (hardware.error)
    return <ErrorState error={hardware.error} onRetry={() => void hardware.refetch()} />;

  const data = hardware.data ?? {};
  const capacity = data.capacity ?? {};
  const pressure = data.pressure ?? {};
  const calibration = data.calibration ?? {};
  const disk = calibration.result?.disk ?? {};
  const nodes = discovery.data?.nodes ?? [];

  return (
    <div>
      <PageHeader
        title="Hardware"
        subtitle="Stable capacity, current pressure, thermal state, and freshness-labeled calibration evidence."
        command="rift hardware"
        actions={
          <button
            type="button"
            onClick={() => calibrate.mutate({ sample_bytes: 32 * 1024 ** 2, force: true })}
            disabled={calibrate.isPending}
            className="inline-flex h-8 items-center gap-2 rounded-sm border border-primary/50 px-3 text-xs text-primary hover:bg-primary/10 disabled:opacity-50"
          >
            <Gauge className="h-3.5 w-3.5" />{" "}
            {calibrate.isPending ? "Calibrating" : "Calibrate disk"}
          </button>
        }
      />
      <div className="space-y-3 p-4">
        <ResultBanner result={calibrate.data} />
        {calibrate.error && <ErrorState error={calibrate.error} />}

        <div className="grid gap-3 lg:grid-cols-4">
          <Panel>
            <Metric
              label="GPU"
              value={data.device_name ?? "Unknown"}
              hint={`CUDA ${data.compute_capability_major ?? "-"}.${data.compute_capability_minor ?? "-"}`}
              tone="info"
            />
          </Panel>
          <Panel>
            <Metric
              label="VRAM capacity"
              value={bytes(capacity.vram_bytes ?? data.total_vram_bytes)}
              hint={`${number(pressure.vram_used_percent, 1)}% currently used`}
            />
          </Panel>
          <Panel>
            <Metric
              label="Host RAM"
              value={bytes(capacity.host_ram_bytes ?? data.total_host_ram_bytes)}
              hint={`${number(pressure.host_ram_used_percent, 1)}% currently used`}
            />
          </Panel>
          <Panel>
            <Metric
              label="Disk free"
              value={bytes(pressure.disk_free_bytes)}
              hint={`${number(pressure.disk_used_percent, 1)}% used`}
            />
          </Panel>
        </div>

        <div className="grid gap-3 xl:grid-cols-[1.2fr_1fr]">
          <Panel title="Resource pressure">
            <div className="space-y-5">
              <Resource
                label="VRAM"
                used={Number(pressure.vram_used_percent ?? 0)}
                free={bytes(pressure.vram_free_bytes)}
              />
              <Resource
                label="Host RAM"
                used={Number(pressure.host_ram_used_percent ?? 0)}
                free={bytes(pressure.host_ram_free_bytes)}
              />
              <Resource
                label="Disk"
                used={Number(pressure.disk_used_percent ?? 0)}
                free={bytes(pressure.disk_free_bytes)}
              />
            </div>
            <p className="mt-4 text-xs text-muted-foreground">{pressure.observation_note}</p>
          </Panel>

          <Panel title="Identity and telemetry">
            <KV k="Host" v={data.identity?.hostname ?? "--"} />
            <KV k="CPU" v={data.identity?.cpu_model ?? "--"} />
            <KV k="Logical CPUs" v={data.identity?.logical_cpu_count ?? "--"} />
            <KV k="OS" v={`${data.identity?.os ?? "--"} ${data.identity?.os_release ?? ""}`} />
            <KV
              k="GPU temperature"
              v={
                data.power_thermal?.temperature_c != null
                  ? `${data.power_thermal.temperature_c} C`
                  : "unavailable"
              }
            />
            <KV
              k="GPU power"
              v={
                data.power_thermal?.power_draw_w != null
                  ? `${data.power_thermal.power_draw_w} W`
                  : "unavailable"
              }
            />
            <KV
              k="Profile fingerprint"
              v={<span className="break-all">{data.fingerprint?.slice(0, 20) ?? "--"}</span>}
            />
          </Panel>
        </div>

        <div className="grid gap-3 xl:grid-cols-2">
          <Panel title="Calibration evidence">
            <div className="mb-3 flex items-center gap-2">
              <Chip tone={calibration.available && !calibration.stale ? "ok" : "warn"}>
                {calibration.available ? (calibration.stale ? "stale" : "fresh") : "not measured"}
              </Chip>
              <span className="text-xs text-muted-foreground">
                H2D: {data.measurement_labels?.h2d_bandwidth ?? "unknown"}
              </span>
            </div>
            <KV
              k="Disk read"
              v={disk.read_mib_s != null ? `${disk.read_mib_s} MiB/s` : "not measured"}
            />
            <KV
              k="Disk write"
              v={disk.write_mib_s != null ? `${disk.write_mib_s} MiB/s` : "not measured"}
            />
            <KV k="Sample" v={bytes(calibration.result?.sample_bytes)} />
            <p className="mt-3 text-xs text-muted-foreground">
              {disk.cache_caveat ?? "Run calibration to measure a bounded local sample."}
            </p>
          </Panel>

          <Panel title="Discovered nodes" padded={false}>
            {nodes.length === 0 ? (
              <div className="p-5 text-sm text-muted-foreground">
                Run discovery to persist local or cluster nodes.
              </div>
            ) : (
              <div className="overflow-auto">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-border bg-surface text-[10px] uppercase tracking-widest text-muted-foreground">
                    <tr>
                      <th className="px-3 py-2">Node</th>
                      <th>GPU</th>
                      <th>VRAM</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {nodes.map((node: any) => (
                      <tr key={node.name} className="border-b border-border/60 last:border-0">
                        <td className="px-3 py-2 mono">{node.name}</td>
                        <td>
                          {node.hardware?.device_name ?? node.hardware?.identity?.gpu ?? "--"}
                        </td>
                        <td>{bytes(node.hardware?.total_vram_bytes)}</td>
                        <td>
                          <Chip tone={statusTone(node.status ?? "ready")}>
                            {node.status ?? "ready"}
                          </Chip>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </div>

        {calibrate.data && (
          <Panel title="Calibration result">
            <JsonPreview value={calibrate.data} />
          </Panel>
        )}
      </div>
    </div>
  );
}

function Resource({ label, used, free }: { label: string; used: number; free: string }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span>{label}</span>
        <span className="mono text-muted-foreground">
          {used.toFixed(1)}% / {free} free
        </span>
      </div>
      <Bar value={used} tone={used > 90 ? "err" : used > 75 ? "warn" : "info"} />
    </div>
  );
}
