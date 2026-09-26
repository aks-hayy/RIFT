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
  Menu,
  X,
  SlidersHorizontal,
  Layers3,
  ChevronDown,
  Workflow,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { DEFAULT_ROUTE, NAVIGATION } from "@/lib/rift/navigation";
import { rift } from "@/lib/rift/client";
import type { RiftEvent } from "@/lib/rift/types";
import { useQueryClient } from "@tanstack/react-query";
import { keys } from "@/lib/rift/hooks";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const NAV_ICONS = {
  Overview: Home,
  Services: Boxes,
  Nodes: Server,
  Models: Package,
  Groups: Layers3,
  Operations: Activity,
  Tuning: SlidersHorizontal,
  Settings: Settings2,
} as const;

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
        case "controller.connected":
          qc.invalidateQueries({ queryKey: keys.health });
          qc.invalidateQueries({ queryKey: keys.services });
          break;
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
    <div className="rift-shell min-h-dvh flex flex-col bg-canvas">
      <header
        className="rift-topbar border-b border-border bg-raised/90 backdrop-blur-xl"
        role="banner"
      >
        <div className="max-w-[1560px] mx-auto flex items-center gap-4 px-4 h-[68px]">
          <Link
            to={DEFAULT_ROUTE}
            className="flex shrink-0 items-center gap-2.5 font-mono text-[13px] tracking-[0.14em] font-medium text-ink"
            aria-label="RIFT Workload Deploy"
          >
            <img src="/rift-logo-concept-v9.png" alt="" className="size-9 object-contain" />
            <span>RIFT</span>
            <span className="hidden 2xl:inline text-ink-secondary font-normal">control plane</span>
          </Link>

          <nav className="hidden xl:flex min-w-0 items-center gap-0.5 ml-3" aria-label="Primary">
            {NAVIGATION.primary.map((item) => {
              const Icon = (NAV_ICONS as Record<string, typeof Home>)[item.label];
              const active = pathname === item.to || pathname.startsWith(item.to + "/");
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={cn(
                    "px-2.5 h-9 inline-flex items-center gap-2 text-[12.5px] rounded-lg transition-colors",
                    active
                      ? "bg-primary/10 text-primary font-semibold"
                      : "text-ink-secondary hover:text-ink hover:bg-muted/75",
                  )}
                >
                  <Icon className="size-3.5" aria-hidden />
                  {item.label}
                </Link>
              );
            })}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  className={cn(
                    "inline-flex h-9 items-center gap-2 rounded-lg px-2.5 text-[12.5px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    pathname.startsWith("/workloads") || pathname.startsWith("/setup")
                      ? "bg-primary/10 font-semibold text-primary"
                      : "text-ink-secondary hover:bg-muted/75 hover:text-ink",
                  )}
                  aria-label="Deployment paths"
                >
                  <Workflow className="size-3.5" aria-hidden />
                  Deployment
                  <ChevronDown className="size-3.5 opacity-70" aria-hidden />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="start"
                className="min-w-52 rounded-xl border-white/70 bg-surface/95 p-1.5 shadow-xl backdrop-blur-xl"
              >
                {NAVIGATION.deployment.map((item) => (
                  <DropdownMenuItem key={item.to} asChild>
                    <Link
                      to={item.to}
                      className={cn(
                        "cursor-pointer rounded-lg px-3 py-2.5 text-[13px]",
                        pathname === item.to ? "bg-primary/10 font-medium text-primary" : "",
                      )}
                    >
                      {item.label}
                    </Link>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </nav>

          <div className="ml-auto flex items-center gap-3 text-[12px] rift-mono">
            <ControllerStatus stale={stale} />
            <button
              type="button"
              className="xl:hidden inline-flex size-10 items-center justify-center rounded-xl border border-border/70 bg-surface/80 text-ink-secondary shadow-sm hover:bg-muted hover:text-ink"
              aria-label={mobileOpen ? "Close navigation" : "Open navigation"}
              aria-expanded={mobileOpen}
              aria-controls="rift-mobile-navigation"
              onClick={() => setMobileOpen((open) => !open)}
            >
              {mobileOpen ? <X className="size-4" /> : <Menu className="size-4" />}
            </button>
          </div>
        </div>
        {mobileOpen && (
          <nav
            id="rift-mobile-navigation"
            className="xl:hidden border-t border-border/70 bg-surface/90 px-4 py-3 grid grid-cols-2 gap-1.5 backdrop-blur-xl"
            aria-label="Mobile primary"
          >
            {NAVIGATION.primary.map((item) => {
              const Icon = (NAV_ICONS as Record<string, typeof Home>)[item.label];
              const active = pathname === item.to || pathname.startsWith(item.to + "/");
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  onClick={() => setMobileOpen(false)}
                  className={cn(
                    "h-10 px-3 inline-flex items-center gap-2 rounded-xl text-[13px] transition-colors",
                    active
                      ? "bg-primary/10 text-primary font-semibold"
                      : "text-ink-secondary hover:bg-muted",
                  )}
                >
                  <Icon className="size-3.5" aria-hidden />
                  {item.label}
                </Link>
              );
            })}
            {NAVIGATION.deployment.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                onClick={() => setMobileOpen(false)}
                className={cn(
                  "h-10 px-3 inline-flex items-center gap-2 rounded-xl text-[13px] transition-colors",
                  pathname === item.to
                    ? "bg-primary/10 text-primary font-semibold"
                    : "text-ink-secondary hover:bg-muted",
                )}
              >
                <Workflow className="size-3.5" aria-hidden />
                {item.label}
              </Link>
            ))}
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
        </div>
      </div>

      <main className="flex-1 min-w-0" role="main">
        {children}
      </main>

      <footer className="border-t border-border/70 bg-raised/75 backdrop-blur-xl">
        <div className="max-w-[1560px] mx-auto px-4 h-10 flex items-center justify-between text-[11px] rift-mono text-ink-secondary">
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
