import { AlertTriangle, Check, LoaderCircle, Play, RefreshCw, X } from "lucide-react";
import type { ReactNode } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { cn } from "@/lib/utils";

export function LoadingState({ label = "Loading RIFT data" }: { label?: string }) {
  return (
    <div className="flex min-h-32 items-center justify-center gap-2 text-sm text-muted-foreground">
      <LoaderCircle className="h-4 w-4 animate-spin text-primary" />
      <span className="mono">{label}</span>
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : "RIFT API request failed";
  return (
    <div className="border border-err/40 bg-err/10 p-4 text-sm">
      <div className="flex items-center gap-2 text-err">
        <AlertTriangle className="h-4 w-4" />
        <strong>Control API unavailable</strong>
      </div>
      <p className="mt-2 text-muted-foreground">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 inline-flex h-8 items-center gap-2 rounded-sm border border-border px-3 text-xs hover:bg-surface"
        >
          <RefreshCw className="h-3.5 w-3.5" /> Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="flex min-h-32 flex-col items-center justify-center px-6 text-center">
      <div className="mono text-xs uppercase tracking-widest text-muted-foreground">{title}</div>
      {detail && <p className="mt-2 max-w-lg text-sm text-muted-foreground">{detail}</p>}
    </div>
  );
}

export function JsonPreview({ value, className }: { value: unknown; className?: string }) {
  return (
    <pre
      className={cn(
        "max-h-[32rem] overflow-auto whitespace-pre-wrap break-words bg-background p-3 mono text-[11px] leading-5 text-muted-foreground",
        className,
      )}
    >
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

export function ResultBanner({ result }: { result: unknown }) {
  if (!result) return null;
  return (
    <div className="border border-ok/30 bg-ok/10 px-3 py-2 text-xs text-ok">
      <span className="inline-flex items-center gap-2">
        <Check className="h-3.5 w-3.5" /> Operation completed. Review the returned state below.
      </span>
    </div>
  );
}

export function ConfirmAction({
  label,
  title,
  description,
  onConfirm,
  pending,
  destructive = false,
  icon,
}: {
  label: string;
  title: string;
  description: string;
  onConfirm: () => void;
  pending?: boolean;
  destructive?: boolean;
  icon?: ReactNode;
}) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <button
          type="button"
          disabled={pending}
          className={cn(
            "inline-flex h-8 items-center gap-2 rounded-sm border px-3 text-xs font-medium disabled:opacity-50",
            destructive
              ? "border-err/50 text-err hover:bg-err/10"
              : "border-primary/50 text-primary hover:bg-primary/10",
          )}
        >
          {pending ? (
            <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
          ) : (
            (icon ?? <Play className="h-3.5 w-3.5" />)
          )}
          {label}
        </button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>
            <X className="mr-2 h-3.5 w-3.5" /> Cancel
          </AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>Confirm</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
