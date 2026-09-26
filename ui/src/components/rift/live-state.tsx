import type { ReactNode } from "react";
import { AlertTriangle, CircleSlash2, LoaderCircle, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { resolveLiveState, type LiveStateInput } from "@/lib/rift/live-state-state";

type LiveStateProps = LiveStateInput & {
  children: ReactNode;
  className?: string;
  title?: string;
  loadingLabel?: string;
  emptyTitle?: string;
  emptyDescription?: string;
  reason?: string;
  onRetry?: () => void;
};

export function LiveState({
  children,
  className,
  title,
  loadingLabel = "Loading live data…",
  emptyTitle = "No data returned",
  emptyDescription = "The controller returned an empty result for this view.",
  reason,
  onRetry,
  ...input
}: LiveStateProps) {
  const state = resolveLiveState(input);
  if (state === "ready") return <>{children}</>;

  const content = {
    loading: {
      icon: (
        <LoaderCircle
          className="size-4 animate-spin text-primary motion-reduce:animate-none"
          aria-hidden
        />
      ),
      heading: title ?? "Loading",
      message: loadingLabel,
    },
    empty: {
      icon: <CircleSlash2 className="size-4 text-ink-muted" aria-hidden />,
      heading: emptyTitle,
      message: emptyDescription,
    },
    unavailable: {
      icon: <AlertTriangle className="size-4 text-attention" aria-hidden />,
      heading: title ?? "Controller unavailable",
      message:
        reason ?? "RIFT did not return this resource. Check the controller connection and retry.",
    },
    error: {
      icon: <AlertTriangle className="size-4 text-error" aria-hidden />,
      heading: title ?? "Could not load data",
      message:
        reason ??
        "The controller request failed. Existing measurements have not been replaced with estimates.",
    },
    unsupported: {
      icon: <CircleSlash2 className="size-4 text-ink-muted" aria-hidden />,
      heading: title ?? "Not supported here",
      message: reason ?? "The selected service or backend does not advertise this capability.",
    },
    ready: { icon: null, heading: "", message: "" },
  }[state];

  return (
    <div
      className={cn(
        "rift-live-state flex min-h-24 items-start gap-3 rounded-xl border border-border/70 bg-white/45 p-4 text-left",
        className,
      )}
      role="status"
      aria-live="polite"
      data-live-state={state}
    >
      <span className="mt-0.5 shrink-0">{content.icon}</span>
      <div className="min-w-0 flex-1">
        <div className="text-[13px] font-medium text-ink">{content.heading}</div>
        <p className="mt-1 max-w-2xl text-[12.5px] leading-relaxed text-ink-secondary">
          {content.message}
        </p>
        {onRetry && state !== "loading" && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 inline-flex h-8 items-center gap-2 rounded-lg border border-border/80 bg-white/75 px-3 text-[12px] font-medium text-ink transition-colors hover:border-primary/35 hover:text-primary"
          >
            <RefreshCw className="size-3.5" aria-hidden />
            Retry
          </button>
        )}
      </div>
    </div>
  );
}
