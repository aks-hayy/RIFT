import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export type Tone = "ok" | "warn" | "err" | "info" | "neutral";

const toneClasses: Record<Tone, string> = {
  ok: "text-ok border-ok/40 bg-ok/10",
  warn: "text-warn border-warn/40 bg-warn/10",
  err: "text-err border-err/40 bg-err/10",
  info: "text-info border-info/40 bg-info/10",
  neutral: "text-neutral border-border bg-panel",
};

export function Chip({
  tone = "neutral",
  children,
  dot = true,
  className,
}: {
  tone?: Tone;
  children: ReactNode;
  dot?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm border px-1.5 py-0.5 mono text-[11px] leading-none",
        toneClasses[tone],
        className,
      )}
    >
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
  command,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  command?: string;
}) {
  return (
    <div className="border-b border-border bg-surface px-6 py-4 flex flex-wrap items-end gap-4">
      <div className="min-w-0">
        <div className="mono text-[10px] uppercase tracking-widest text-muted-foreground">
          Console
        </div>
        <h1 className="mt-0.5 text-lg font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="text-sm text-muted-foreground max-w-2xl">{subtitle}</p>}
      </div>
      <div className="flex-1" />
      {command && (
        <div className="hidden md:flex items-center gap-2 rounded border border-border bg-panel px-2.5 py-1.5 mono text-xs">
          <span className="text-muted-foreground">$</span>
          <span className="text-primary">{command}</span>
        </div>
      )}
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Panel({
  title,
  actions,
  children,
  className,
  padded = true,
  scroll = false,
}: {
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  padded?: boolean;
  scroll?: boolean;
}) {
  return (
    <section className={cn("border border-border bg-panel flex flex-col min-w-0", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between px-3 h-9 border-b border-border bg-surface">
          <div className="mono text-[11px] uppercase tracking-widest text-muted-foreground">
            {title}
          </div>
          {actions && <div className="flex items-center gap-1">{actions}</div>}
        </header>
      )}
      <div className={cn(padded && "p-3", scroll && "overflow-auto", "flex-1 min-h-0")}>
        {children}
      </div>
    </section>
  );
}

export function Metric({
  label,
  value,
  unit,
  hint,
  tone,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  hint?: string;
  tone?: Tone;
}) {
  return (
    <div>
      <div className="mono text-[10px] uppercase tracking-widest text-muted-foreground">
        {label}
      </div>
      <div className="mt-0.5 flex items-baseline gap-1">
        <span
          className={cn(
            "mono text-xl font-semibold tabular-nums",
            tone === "ok" && "text-ok",
            tone === "warn" && "text-warn",
            tone === "err" && "text-err",
            tone === "info" && "text-primary",
          )}
        >
          {value}
        </span>
        {unit && <span className="mono text-xs text-muted-foreground">{unit}</span>}
      </div>
      {hint && <div className="text-[11px] text-muted-foreground mt-0.5">{hint}</div>}
    </div>
  );
}

export function IconButton({
  label,
  children,
  onClick,
  tone = "neutral",
  disabled,
}: {
  label: string;
  children: ReactNode;
  onClick?: () => void;
  tone?: Tone;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      title={label}
      disabled={disabled}
      className={cn(
        "h-7 w-7 grid place-items-center rounded-sm border transition-colors disabled:opacity-40",
        tone === "err"
          ? "border-err/40 text-err hover:bg-err/10"
          : tone === "ok"
            ? "border-ok/40 text-ok hover:bg-ok/10"
            : tone === "warn"
              ? "border-warn/40 text-warn hover:bg-warn/10"
              : "border-border text-muted-foreground hover:text-foreground hover:bg-surface",
      )}
    >
      {children}
    </button>
  );
}

export function Bar({
  value,
  max = 100,
  tone = "info",
  className,
}: {
  value: number;
  max?: number;
  tone?: Tone;
  className?: string;
}) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const barTone =
    tone === "ok"
      ? "bg-ok"
      : tone === "warn"
        ? "bg-warn"
        : tone === "err"
          ? "bg-err"
          : tone === "neutral"
            ? "bg-neutral"
            : "bg-primary";
  return (
    <div className={cn("h-1.5 w-full bg-surface rounded-sm overflow-hidden", className)}>
      <div className={cn("h-full", barTone)} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function KV({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 text-xs py-1 border-b border-border/50 last:border-0">
      <span className="mono uppercase tracking-widest text-[10px] text-muted-foreground">{k}</span>
      <span className="mono text-foreground text-right">{v}</span>
    </div>
  );
}
