import { AlertTriangle, ExternalLink } from "lucide-react";

/**
 * `Unavailable` — shown wherever a required RIFT controller endpoint is
 * not reachable. Per spec: never silently substitute mock data. Instead
 * we name the endpoint, method, and expected resource shape so operators
 * can wire it up (or confirm the controller is offline).
 */
export function Unavailable({
  endpoint,
  method = "GET",
  resource,
  hint,
  reason,
}: {
  endpoint: string;
  method?: "GET" | "POST" | "DELETE" | "PATCH";
  resource: string;
  hint?: string;
  reason?: string;
}) {
  return (
    <div className="rift-surface p-5" role="status" aria-live="polite">
      <div className="flex items-start gap-3">
        <AlertTriangle className="size-4 mt-0.5 text-attention shrink-0" aria-hidden />
        <div className="min-w-0">
          <div className="rift-label mb-1 text-ink">Data unavailable</div>
          <p className="text-[13px] text-ink-secondary max-w-xl">
            {reason ?? "The controller endpoint required to render this view is not reachable."}
          </p>
          <div className="mt-3 grid gap-1.5 text-[12.5px] rift-mono">
            <div className="flex gap-2">
              <span className="text-ink-secondary w-16">endpoint</span>
              <span className="text-ink">
                {method} {endpoint}
              </span>
            </div>
            <div className="flex gap-2">
              <span className="text-ink-secondary w-16">returns</span>
              <span className="text-ink">{resource}</span>
            </div>
          </div>
          {hint && <p className="mt-3 text-[12px] text-ink-secondary max-w-xl">{hint}</p>}
          <a
            href="#"
            className="mt-4 inline-flex items-center gap-1 text-[12px] text-primary hover:underline"
          >
            <ExternalLink className="size-3" aria-hidden />
            RIFT controller API reference
          </a>
        </div>
      </div>
    </div>
  );
}
