import { Link, useRouterState } from "@tanstack/react-router";
import {
  Activity,
  Boxes,
  Cpu,
  FileCode2,
  GaugeCircle,
  Layers,
  Network,
  PlayCircle,
  Radar,
  Server,
  Terminal,
  Bell,
  Search,
  CircleDot,
  Sun,
  Moon,
  Menu,
} from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import { useTheme } from "@/hooks/use-theme";
import { riftKeys, useRiftHealth, useRiftQuery } from "@/hooks/use-rift";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";

const NAV: Array<{ to: string; label: string; icon: typeof Activity; group: string }> = [
  { to: "/", label: "Overview", icon: Radar, group: "Control" },
  { to: "/hardware", label: "Hardware", icon: Cpu, group: "Control" },
  { to: "/models", label: "Models", icon: Boxes, group: "Control" },
  { to: "/plan", label: "Plan", icon: FileCode2, group: "Deploy" },
  { to: "/apply", label: "Apply", icon: PlayCircle, group: "Deploy" },
  { to: "/services", label: "Services", icon: Server, group: "Runtime" },
  { to: "/benchmarks", label: "Benchmarks", icon: GaugeCircle, group: "Runtime" },
  { to: "/monitoring", label: "Monitoring", icon: Activity, group: "Runtime" },
  { to: "/cluster", label: "Cluster", icon: Network, group: "Runtime" },
];

export function ConsoleShell({ children }: { children: ReactNode }) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const groups = Array.from(new Set(NAV.map((n) => n.group)));
  const { theme, toggle } = useTheme();
  const health = useRiftHealth();
  const incidents = useRiftQuery<any>(riftKeys.incidents, "/api/rift/incidents", {
    refetchInterval: 10_000,
  });
  const connected = health.isSuccess;
  const incidentCount = Number(incidents.data?.incident_count ?? 0);
  const requestCount = Number(health.data?.request_count ?? 0);

  return (
    <div className="min-h-screen w-full bg-background text-foreground">
      <div className="flex min-h-screen">
        {/* Sidebar */}
        <aside className="hidden md:flex w-56 shrink-0 flex-col border-r border-border bg-sidebar">
          <div className="flex items-center gap-2 px-4 h-12 border-b border-border">
            <div className="relative">
              <Layers className="h-5 w-5 text-primary" strokeWidth={2.25} />
              <span className="absolute -right-1 -bottom-1 h-1.5 w-1.5 rounded-full bg-ok shadow-[0_0_6px_var(--color-ok)]" />
            </div>
            <div className="flex flex-col leading-none">
              <span className="mono text-sm font-semibold tracking-widest">RIFT</span>
              <span className="mono text-[10px] text-muted-foreground">control plane / local</span>
            </div>
          </div>

          <nav className="flex-1 overflow-y-auto py-3">
            {groups.map((g) => (
              <div key={g} className="mb-4">
                <div className="px-4 mb-1 mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  {g}
                </div>
                <ul>
                  {NAV.filter((n) => n.group === g).map((n) => {
                    const Icon = n.icon;
                    const active = n.to === "/" ? pathname === "/" : pathname.startsWith(n.to);
                    return (
                      <li key={n.to}>
                        <Link
                          to={n.to}
                          className={cn(
                            "group flex items-center gap-2.5 px-4 py-1.5 text-sm border-l-2 border-transparent transition-colors",
                            active
                              ? "border-primary bg-sidebar-accent text-foreground"
                              : "text-sidebar-foreground/80 hover:text-foreground hover:bg-sidebar-accent/50",
                          )}
                        >
                          <Icon
                            className={cn(
                              "h-3.5 w-3.5",
                              active ? "text-primary" : "text-muted-foreground",
                            )}
                          />
                          <span>{n.label}</span>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </nav>

          <div className="border-t border-border px-4 py-2.5 text-[11px] mono text-muted-foreground space-y-1">
            <div className="flex justify-between">
              <span>context</span>
              <span className="text-foreground">local / rift-host</span>
            </div>
            <div className="flex justify-between">
              <span>api</span>
              <span className={connected ? "text-ok" : "text-err"}>
                {connected ? "connected" : "offline"}
              </span>
            </div>
          </div>
        </aside>

        {/* Main column */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Top bar */}
          <header className="h-12 border-b border-border bg-surface flex items-center gap-3 px-4">
            <MobileNavigation pathname={pathname} groups={groups} />
            <div className="md:hidden mono text-sm font-semibold tracking-widest">RIFT</div>
            <div className="hidden md:flex items-center gap-2 mono text-xs text-muted-foreground">
              <span>rift-host</span>
              <span className="text-border">/</span>
              <span className="text-foreground">
                {NAV.find((n) => (n.to === "/" ? pathname === "/" : pathname.startsWith(n.to)))
                  ?.label ?? "Overview"}
              </span>
            </div>

            <div className="flex-1" />

            <div className="hidden lg:flex items-center gap-2 rounded border border-border bg-panel px-2.5 py-1 w-72 text-xs text-muted-foreground">
              <Search className="h-3.5 w-3.5" />
              <span className="mono">services / nodes / models</span>
              <span className="ml-auto mono text-[10px] rounded border border-border px-1 py-0.5">
                Ctrl K
              </span>
            </div>

            <StatusPill
              tone={connected ? "ok" : "err"}
              label={connected ? "control API ready" : "control API offline"}
            />
            {incidentCount > 0 && <StatusPill tone="warn" label={`${incidentCount} incidents`} />}

            <button
              onClick={toggle}
              className="h-8 w-8 rounded border border-border bg-panel grid place-items-center text-muted-foreground hover:text-foreground"
              aria-label="Toggle theme"
              title={theme === "dark" ? "Switch to light" : "Switch to dark"}
            >
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
            <button
              className="h-8 w-8 rounded border border-border bg-panel grid place-items-center text-muted-foreground hover:text-foreground"
              aria-label="Alerts"
            >
              <Bell className="h-4 w-4" />
            </button>
            <button
              className="h-8 w-8 rounded border border-border bg-panel grid place-items-center text-muted-foreground hover:text-foreground"
              aria-label="Terminal"
            >
              <Terminal className="h-4 w-4" />
            </button>
          </header>

          <main className="flex-1 overflow-y-auto">{children}</main>

          {/* Status bar */}
          <footer className="h-7 border-t border-border bg-sidebar flex items-center gap-4 px-4 mono text-[11px] text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <CircleDot className={cn("h-3 w-3", connected ? "text-ok" : "text-err")} />
              {connected ? "daemon connected" : "daemon unavailable"}
            </span>
            <span className="hidden sm:inline">requests {requestCount}</span>
            <span className="hidden sm:inline">incidents {incidentCount}</span>
            <span className="ml-auto hidden lg:inline">rift apply queue: idle</span>
            <span className="ml-auto lg:ml-0">live API</span>
          </footer>
        </div>
      </div>
    </div>
  );
}

function MobileNavigation({ pathname, groups }: { pathname: string; groups: Array<string> }) {
  return (
    <Sheet>
      <SheetTrigger asChild>
        <button
          className="md:hidden h-8 w-8 rounded border border-border bg-panel grid place-items-center text-muted-foreground hover:text-foreground"
          aria-label="Open navigation"
          title="Open navigation"
        >
          <Menu className="h-4 w-4" />
        </button>
      </SheetTrigger>
      <SheetContent side="left" className="w-[19rem] max-w-[85vw] bg-sidebar p-0">
        <SheetHeader className="border-b border-border px-4 py-4 text-left">
          <SheetTitle className="mono text-sm tracking-widest">RIFT</SheetTitle>
          <SheetDescription className="mono text-[11px]">control plane / local</SheetDescription>
        </SheetHeader>
        <nav className="overflow-y-auto py-4">
          {groups.map((group) => (
            <div key={group} className="mb-4">
              <div className="px-4 mb-1 mono text-[10px] uppercase tracking-widest text-muted-foreground">
                {group}
              </div>
              <ul>
                {NAV.filter((item) => item.group === group).map((item) => {
                  const Icon = item.icon;
                  const active = item.to === "/" ? pathname === "/" : pathname.startsWith(item.to);
                  return (
                    <li key={item.to}>
                      <SheetClose asChild>
                        <Link
                          to={item.to}
                          className={cn(
                            "flex items-center gap-2.5 border-l-2 border-transparent px-4 py-2 text-sm",
                            active
                              ? "border-primary bg-sidebar-accent text-foreground"
                              : "text-sidebar-foreground/80 hover:bg-sidebar-accent/50 hover:text-foreground",
                          )}
                        >
                          <Icon
                            className={cn(
                              "h-4 w-4",
                              active ? "text-primary" : "text-muted-foreground",
                            )}
                          />
                          <span>{item.label}</span>
                        </Link>
                      </SheetClose>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>
      </SheetContent>
    </Sheet>
  );
}

function StatusPill({ tone, label }: { tone: "ok" | "warn" | "err" | "info"; label: string }) {
  const map = {
    ok: "text-ok border-ok/40 bg-ok/10",
    warn: "text-warn border-warn/40 bg-warn/10",
    err: "text-err border-err/40 bg-err/10",
    info: "text-info border-info/40 bg-info/10",
  } as const;
  return (
    <span
      className={cn(
        "hidden md:inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 mono text-[11px]",
        map[tone],
      )}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {label}
    </span>
  );
}
