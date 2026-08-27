import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import type { DataProvenance } from "@/lib/rift/types";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="border-b border-border bg-surface">
      <div className="max-w-[1400px] mx-auto px-4 py-6 flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          {eyebrow && <div className="rift-label mb-2">{eyebrow}</div>}
          <h1 className="text-[22px] leading-tight font-medium text-ink">{title}</h1>
          {description && (
            <p className="mt-1.5 text-[13px] text-ink-secondary max-w-2xl">{description}</p>
          )}
        </div>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
    </div>
  );
}

export function Panel({
  title,
  aside,
  className,
  bodyClassName,
  children,
}: {
  title?: string;
  aside?: ReactNode;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
}) {
  return (
    <section className={cn("rift-panel min-w-0 max-w-full", className)}>
      {title && (
        <header className="flex items-center justify-between px-4 h-10 border-b border-border">
          <h2 className="rift-label">{title}</h2>
          {aside}
        </header>
      )}
      <div className={cn("p-4", bodyClassName)}>{children}</div>
    </section>
  );
}

export function StatDot({ tone }: { tone: "ok" | "attention" | "error" | "muted" | "info" }) {
  const color =
    tone === "ok"
      ? "text-success"
      : tone === "attention"
        ? "text-attention"
        : tone === "error"
          ? "text-error"
          : tone === "info"
            ? "text-secondary"
            : "text-ink-muted";
  return <span className={cn("rift-dot", color)} aria-hidden />;
}

export function KV({
  label,
  value,
  mono = true,
}: {
  label: string;
  value: ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="rift-label">{label}</span>
      <span className={cn("text-[13px] text-ink", mono && "rift-mono")}>{value}</span>
    </div>
  );
}

export function SourceBadge({ source }: { source?: DataProvenance }) {
  if (!source) return null;
  const label = source === "derived-live" ? "live / normalized" : source;
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center rounded-[3px] border px-1.5 rift-mono text-[10px] uppercase",
        source === "preview"
          ? "border-attention/50 bg-attention/10 text-ink"
          : "border-secondary/40 bg-secondary/10 text-secondary",
      )}
    >
      {label}
    </span>
  );
}
