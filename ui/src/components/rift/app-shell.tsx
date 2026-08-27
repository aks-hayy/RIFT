import { Link, useRouterState } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import {
  Home,
  Boxes,
  Server,
  Package,
  Activity,
  Settings2,
  CircleDot,
  Terminal,
  Menu,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { rift } from "@/lib/rift/client";
import type { RiftEvent } from "@/lib/rift/types";
import { useQueryClient } from "@tanstack/react-query";
import { keys } from "@/lib/rift/hooks";

type NavItem = {
  to: "/" | "/deployments" | "/nodes" | "/models" | "/operations" | "/settings";
  label: string;
  icon: typeof Home;
  exact?: boolean;
};
const NAV: readonly NavItem[] = [
  { to: "/", label: "Home", icon: Home, exact: true },
  { to: "/deployments", label: "Deployments", icon: Boxes },
  { to: "/nodes", label: "Nodes", icon: Server },
  { to: "/models", label: "Models", icon: Package },
  { to: "/operations", label: "Operations", icon: Activity },
  { to: "/settings", label: "Settings", icon: Settings2 },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const [stale, setStale] = useState<boolean | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const qc = useQueryClient();
  const connection = rift.connectionInfo();

  useEffect(() => {
    if (!rift.isConfigured()) {
      setStale(true);
      return;
    }
    const off = rift.subscribe((e: RiftEvent) => {
      // Coarse invalidations per event kind — cheap for the small resource
      // set the controller exposes and keeps the UI honest with server state.
      switch (e.kind) {
        case "health":
          qc.setQueryData(keys.health, e.health);
          break;
        case "node.enrolled":
        case "node.status":
          qc.invalidateQueries({ queryKey: keys.nodes });
          break;
        case "service.status":
          qc.invalidateQueries({ queryKey: keys.services });
          break;
        case "incident.opened":
        case "incident.resolved":
          qc.invalidateQueries({ queryKey: keys.incidents });
          break;
        case "plan.progress":
          // consumer subscribes directly; nothing to do here
          break;
      }
    }, setStale);
    return off;
  }, [qc]);

  return (
    <div className="min-h-dvh flex flex-col bg-canvas">
      <header className="border-b border-border bg-raised" role="banner">
        <div className="max-w-[1400px] mx-auto flex items-center gap-6 px-4 h-14">
          <Link
            to="/"
            className="flex items-center gap-2 font-mono text-[13px] tracking-[0.14em] font-medium text-ink"
            aria-label="RIFT home"
          >
            <RiftMark />
            <span>RIFT</span>
            <span className="text-ink-secondary font-normal">controller</span>
          </Link>

          <nav className="hidden lg:flex items-center gap-0.5 ml-4" aria-label="Primary">
            {NAV.map((item) => {
              const Icon = item.icon;
              const active = item.exact
                ? pathname === item.to
                : pathname === item.to || pathname.startsWith(item.to + "/");
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={cn(
                    "px-3 h-9 inline-flex items-center gap-2 text-[13px] rounded-[4px] transition-colors",
                    active
                      ? "bg-muted text-ink font-medium"
                      : "text-ink-secondary hover:text-ink hover:bg-muted",
                  )}
                >
                  <Icon className="size-3.5" aria-hidden />
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="ml-auto flex items-center gap-3 text-[12px] rift-mono">
            <ControllerStatus stale={stale} />
            <button
              type="button"
              className="hidden lg:inline-flex items-center gap-1.5 text-ink-secondary hover:text-ink"
              aria-label="Open CLI reference"
            >
              <Terminal className="size-3.5" aria-hidden /> CLI
            </button>
            <button
              type="button"
              className="lg:hidden inline-flex size-9 items-center justify-center rounded-[4px] border border-border text-ink-secondary hover:bg-muted hover:text-ink"
              aria-label={mobileOpen ? "Close navigation" : "Open navigation"}
              aria-expanded={mobileOpen}
              onClick={() => setMobileOpen((open) => !open)}
            >
              {mobileOpen ? <X className="size-4" /> : <Menu className="size-4" />}
            </button>
          </div>
        </div>
        {mobileOpen && (
          <nav
            className="lg:hidden border-t border-border px-3 py-2 grid grid-cols-2 gap-1"
            aria-label="Mobile primary"
          >
            {NAV.map((item) => {
              const Icon = item.icon;
              const active = item.exact
                ? pathname === item.to
                : pathname === item.to || pathname.startsWith(item.to + "/");
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  onClick={() => setMobileOpen(false)}
                  className={cn(
                    "h-9 px-3 inline-flex items-center gap-2 rounded-[4px] text-[13px]",
                    active ? "bg-muted text-ink font-medium" : "text-ink-secondary hover:bg-muted",
                  )}
                >
                  <Icon className="size-3.5" aria-hidden />
                  {item.label}
                </Link>
              );
            })}
          </nav>
        )}
      </header>

      <div className="border-b border-border bg-surface">
        <div className="max-w-[1400px] mx-auto min-h-7 px-4 py-1 flex flex-wrap items-center gap-x-3 gap-y-1 rift-mono text-[10.5px] text-ink-secondary">
          <span className="inline-flex items-center gap-1.5 text-secondary">
            <span className="rift-dot !size-1.5" aria-hidden />
            live controller data
          </span>
          <span>{connection.root}</span>
          <span className="hidden sm:inline">compatibility adapter</span>
          {connection.previewEnabled && (
            <span className="ml-auto text-attention">
              preview-only surfaces are explicitly labeled
            </span>
          )}
        </div>
      </div>

      <main className="flex-1 min-w-0" role="main">
        {children}
      </main>

      <footer className="border-t border-border bg-raised">
        <div className="max-w-[1400px] mx-auto px-4 h-9 flex items-center justify-between text-[11px] rift-mono text-ink-secondary">
          <span>RIFT · operator console</span>
          <span>Controller binds locally by default</span>
        </div>
      </footer>
    </div>
  );
}

function ControllerStatus({ stale }: { stale: boolean | null }) {
  const state = stale === null ? "connecting" : stale ? "offline" : "live";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5",
        stale === true
          ? "text-attention"
          : stale === null
            ? "text-ink-secondary"
            : "text-secondary",
      )}
      title={
        stale === null
          ? "Connecting to the controller"
          : stale
            ? "Controller poll failed; retrying"
            : "Live controller polling"
      }
    >
      <CircleDot className="size-3.5" aria-hidden />
      {state}
    </span>
  );
}

function RiftMark() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden className="text-primary">
      <path
        d="M1 10 L4 10 L5.5 5 L7 15 L8.5 7 L10 13 L11.5 6 L13 14 L14.5 9 L16 11 L19 10"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.25"
        strokeLinecap="square"
        strokeLinejoin="miter"
      />
    </svg>
  );
}
