import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import {
  Monitor,
  Network,
  Copy,
  Check,
  ArrowRight,
  ArrowLeft,
  Loader2,
  ShieldCheck,
  Cpu,
  HardDrive,
  MemoryStick,
  MessageSquare,
  Code2,
  FileText,
  Bot,
  Sliders,
  Sparkles,
  Zap,
  Gauge,
  AlertTriangle,
  ExternalLink,
  Terminal,
  Search,
  Fingerprint,
  LockKeyhole,
  RadioTower,
  RefreshCw,
  Wifi,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { rift } from "@/lib/rift/client";
import { bytes } from "@/lib/rift/format";
import type {
  UseCase,
  ModelArtifact,
  ModelRecommendation,
  RecommendationSearchResult,
  Plan,
  ApplyProgress,
  EnrollmentChallenge,
  MeshNode,
  MeshSighting,
  ManagedEnrollment,
} from "@/lib/rift/types";
import { Unavailable } from "@/components/rift/unavailable";
import { getNextSetupStep, getPreviousSetupStep } from "@/lib/rift/setup-flow";
import {
  recommendationFailureSummary,
  recommendationViewState,
} from "@/lib/rift/recommendation-state";

export const Route = createFileRoute("/setup")({
  head: () => ({
    meta: [
      { title: "Guided setup — RIFT" },
      {
        name: "description",
        content: "Discover hardware, choose a model, review the plan, and deploy in one flow.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: SetupPage,
});

type Mode = "standalone" | "cluster";

interface SetupState {
  step: number;
  mode: Mode | null;
  useCase: UseCase | null;
  source: ModelArtifact["source"] | null;
  chosenRecommendation: ModelRecommendation | null;
  serviceName: string;
  exposure: "local" | "lan" | "public";
  plan: Plan | null;
  applyStarted: boolean;
  applyProgress: ApplyProgress | null;
}

const STEPS = [
  "Mode",
  "Discover",
  "Enroll",
  "Nodes",
  "Use case",
  "Source",
  "Recommendation",
  "Service",
  "Plan",
  "Apply",
  "Progress",
  "Finish",
] as const;

function SetupPage() {
  const navigate = useNavigate();
  const [s, setS] = useState<SetupState>({
    step: 0,
    mode: null,
    useCase: null,
    source: "huggingface",
    chosenRecommendation: null,
    serviceName: "",
    exposure: "local",
    plan: null,
    applyStarted: false,
    applyProgress: null,
  });

  const set = <K extends keyof SetupState>(k: K, v: SetupState[K]) =>
    setS((prev) => ({ ...prev, [k]: v }));
  // If cluster path is skipped, skip Enroll+Nodes when standalone.
  const visible = (i: number) => {
    if (s.mode === "standalone" && (i === 2 || i === 3)) return false;
    return true;
  };
  const next = () =>
    setS((p) => ({
      ...p,
      step: getNextSetupStep(
        p.step,
        (index) => {
          if (p.mode === "standalone" && (index === 2 || index === 3)) return false;
          return true;
        },
        STEPS.length - 1,
      ),
    }));
  const prev = () =>
    setS((p) => ({
      ...p,
      step: getPreviousSetupStep(
        p.step,
        (index) => {
          if (p.mode === "standalone" && (index === 2 || index === 3)) return false;
          return true;
        },
        0,
      ),
    }));
  const visibleSteps = STEPS.map((label, i) => ({ label, i })).filter((x) => visible(x.i));

  return (
    <div className="min-h-dvh bg-canvas flex flex-col">
      <header className="border-b border-border bg-raised">
        <div className="max-w-[1200px] mx-auto px-4 h-14 flex items-center gap-4">
          <div className="font-mono text-[13px] tracking-[0.14em] font-medium text-ink">
            RIFT · guided setup
          </div>
          <button
            type="button"
            onClick={() => navigate({ to: "/" })}
            className="ml-auto text-[12px] text-ink-secondary hover:text-ink"
          >
            Cancel
          </button>
        </div>
        <ProgressRail current={s.step} visible={visibleSteps} />
      </header>

      <div className="flex-1">
        <div className="max-w-[900px] mx-auto px-4 py-10">
          {s.step === 0 && (
            <StepMode value={s.mode} onChange={(v) => set("mode", v)} onNext={next} />
          )}
          {s.step === 1 && <StepDiscover mode={s.mode!} onNext={next} />}
          {s.step === 2 && <StepManagedEnroll onNext={next} />}
          {s.step === 3 && <StepNodesLive onNext={next} />}
          {s.step === 4 && (
            <StepUseCase value={s.useCase} onChange={(v) => set("useCase", v)} onNext={next} />
          )}
          {s.step === 5 && (
            <StepSource
              source={s.source}
              onChange={(source) => set("source", source)}
              onNext={next}
            />
          )}
          {s.step === 6 && (
            <StepRecommendation
              useCase={s.useCase!}
              source={s.source!}
              chosen={s.chosenRecommendation}
              onChoose={(r) => set("chosenRecommendation", r)}
              onNext={next}
            />
          )}
          {s.step === 7 && (
            <StepService
              serviceName={s.serviceName}
              exposure={s.exposure}
              onChange={(name, exp) => setS((p) => ({ ...p, serviceName: name, exposure: exp }))}
              onNext={next}
            />
          )}
          {s.step === 8 && (
            <StepPlan
              recommendation={s.chosenRecommendation}
              serviceName={s.serviceName}
              exposure={s.exposure}
              plan={s.plan}
              onPlan={(p) => set("plan", p)}
              onNext={next}
            />
          )}
          {s.step === 9 && (
            <StepApply
              plan={s.plan}
              onApplied={(progress) => {
                set("applyProgress", progress);
                set("applyStarted", true);
                next();
              }}
            />
          )}
          {s.step === 10 && (
            <StepProgress plan={s.plan!} initialProgress={s.applyProgress} onNext={next} />
          )}
          {s.step === 11 && <StepFinish state={s} />}
        </div>
      </div>

      <footer className="border-t border-border bg-raised">
        <div className="max-w-[1200px] mx-auto px-4 h-14 flex items-center justify-between">
          <button
            type="button"
            onClick={prev}
            disabled={s.step === 0}
            className="inline-flex items-center gap-1.5 text-[13px] text-ink-secondary hover:text-ink disabled:opacity-40"
          >
            <ArrowLeft className="size-4" aria-hidden /> Back
          </button>
          <span className="rift-mono text-[11px] text-ink-secondary">
            Step {s.step + 1} of {STEPS.length}
          </span>
        </div>
      </footer>
    </div>
  );
}

function ProgressRail({
  current,
  visible,
}: {
  current: number;
  visible: { label: string; i: number }[];
}) {
  return (
    <div className="max-w-[1200px] mx-auto px-4 py-2">
      <ol className="flex items-center gap-1 overflow-x-auto">
        {visible.map((v, idx) => {
          const done = current > v.i;
          const active = current === v.i;
          return (
            <li key={v.label} className="flex items-center gap-1 shrink-0">
              <span
                className={cn(
                  "inline-flex items-center gap-1.5 h-6 px-2 rounded-[3px] text-[11px] rift-mono tracking-wider",
                  active
                    ? "bg-primary text-primary-foreground"
                    : done
                      ? "text-secondary"
                      : "text-ink-secondary",
                )}
              >
                <span className="tabular-nums">{String(idx + 1).padStart(2, "0")}</span>
                <span className="uppercase">{v.label}</span>
              </span>
              {idx < visible.length - 1 && <span className="w-4 h-px bg-border" aria-hidden />}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/* ============= steps ============= */

function StepMode({
  value,
  onChange,
  onNext,
}: {
  value: Mode | null;
  onChange: (m: Mode) => void;
  onNext: () => void;
}) {
  return (
    <div>
      <StepTitle
        eyebrow="Step 01 · Mode"
        title="How will RIFT run?"
        description="You can change this later. Cluster mode uses one controller and one lightweight agent per node."
      />
      <div className="grid sm:grid-cols-2 gap-3 mt-6">
        <ModeCard
          icon={Monitor}
          title="Use this computer"
          desc="Controller and agent run on the same machine. Best for local development and single-workstation deployments."
          selected={value === "standalone"}
          onClick={() => onChange("standalone")}
        />
        <ModeCard
          icon={Network}
          title="Manage multiple computers"
          desc="One controller manages agents on every node. Each identity is reviewed, paired, and activated with mTLS."
          selected={value === "cluster"}
          onClick={() => onChange("cluster")}
        />
      </div>
      <PrimaryNext disabled={!value} onClick={onNext} />
    </div>
  );
}

function ModeCard({
  icon: Icon,
  title,
  desc,
  selected,
  onClick,
}: {
  icon: typeof Monitor;
  title: string;
  desc: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "text-left rift-panel p-5 transition-colors focus:outline-none",
        selected ? "border-primary ring-1 ring-primary" : "hover:border-border-strong",
      )}
      aria-pressed={selected}
    >
      <Icon className="size-5 text-primary mb-3" aria-hidden />
      <div className="text-[15px] font-medium text-ink">{title}</div>
      <p className="mt-1.5 text-[13px] text-ink-secondary">{desc}</p>
    </button>
  );
}

function StepDiscover({ mode, onNext }: { mode: Mode; onNext: () => void }) {
  return (
    <div>
      <StepTitle
        eyebrow="Step 02 · Discover"
        title={mode === "standalone" ? "Discovering this computer" : "Initializing the controller"}
        description={
          mode === "standalone"
            ? "RIFT is inspecting hardware, drivers, and available backends."
            : "RIFT is starting the controller and preparing to receive node enrollments."
        }
      />
      {!rift.isConfigured() ? (
        <div className="mt-6">
          <Unavailable
            endpoint={mode === "standalone" ? "/v1/nodes/self" : "/v1/controller/init"}
            method="POST"
            resource="RiftNode (self) / Controller status"
            hint="Configure VITE_RIFT_CONTROLLER_URL, or start the controller with `rift controller start`."
          />
          <p className="mt-4 rift-mono text-[12px] text-ink-secondary">
            Once the controller is reachable, this step performs hardware discovery and returns a
            `RiftNode` describing accelerators, RAM, disk, and supported backends.
          </p>
        </div>
      ) : (
        <DiscoverProgress onDone={onNext} />
      )}
      <PrimaryNext onClick={onNext} />
    </div>
  );
}

function DiscoverProgress({ onDone }: { onDone: () => void }) {
  const [i, setI] = useState(0);
  const steps = ["Probing accelerators", "Reading system memory", "Detecting backends", "Ready"];
  useEffect(() => {
    if (i >= steps.length - 1) return;
    const t = setTimeout(() => setI(i + 1), 700);
    return () => clearTimeout(t);
  }, [i, steps.length]);
  useEffect(() => {
    if (i === steps.length - 1) onDone();
  }, [i, steps.length, onDone]);
  return (
    <ul className="mt-6 grid gap-1.5">
      {steps.map((s, idx) => (
        <li key={s} className="flex items-center gap-2 text-[13px]">
          {idx < i ? (
            <Check className="size-4 text-success" aria-hidden />
          ) : idx === i ? (
            <Loader2 className="size-4 text-primary animate-spin" aria-hidden />
          ) : (
            <span className="size-4 inline-block" aria-hidden />
          )}
          <span className={idx <= i ? "text-ink" : "text-ink-secondary"}>{s}</span>
        </li>
      ))}
    </ul>
  );
}

function StepManagedEnroll({ onNext }: { onNext: () => void }) {
  const [windowState, setWindowState] = useState<Awaited<
    ReturnType<typeof rift.openManagedEnrollmentWindow>
  > | null>(null);
  const [enrollments, setEnrollments] = useState<ManagedEnrollment[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [pairingCode, setPairingCode] = useState("");
  const [phase, setPhase] = useState<"idle" | "opening" | "approving">("idle");
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    try {
      const [currentWindow, currentEnrollments] = await Promise.all([
        rift.getManagedEnrollmentWindow(),
        rift.listManagedEnrollments(),
      ]);
      setWindowState(currentWindow);
      setEnrollments(currentEnrollments);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  };

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 1500);
    return () => window.clearInterval(timer);
  }, []);

  const openWindow = async () => {
    setPhase("opening");
    setError(null);
    try {
      setWindowState(await rift.openManagedEnrollmentWindow(600));
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setPhase("idle");
    }
  };

  const approve = async () => {
    if (!selected || !/^\d{6}$/.test(pairingCode)) return;
    setPhase("approving");
    setError(null);
    try {
      await rift.approveManagedEnrollment(selected, pairingCode);
      setPairingCode("");
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setPhase("idle");
    }
  };

  const active = enrollments.some((item) => item.state === "ACTIVE");
  return (
    <div>
      <StepTitle
        eyebrow="Step 03 · Add node"
        title="Enroll a RIFT node"
        description="Open a short enrollment window, start the node command, then approve the code shown in that node's terminal. The controller never displays the expected code."
      />
      <div className="mt-6 rift-panel p-4 grid gap-4">
        <div className="flex items-start gap-3">
          <LockKeyhole className="size-4 text-primary mt-0.5 shrink-0" aria-hidden />
          <div>
            <div className="text-[13px] font-medium text-ink">
              Identity first, permissions later
            </div>
            <p className="mt-1 text-[12.5px] text-ink-secondary">
              New nodes receive no download, install, launch, or inference permission during
              enrollment.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={openWindow}
          disabled={phase !== "idle"}
          className="inline-flex items-center gap-2 h-10 px-4 rounded-[4px] bg-primary text-primary-foreground text-[13px] font-medium disabled:opacity-50 w-fit"
        >
          {phase === "opening" ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <RadioTower className="size-4" />
          )}
          {windowState?.open ? "Refresh enrollment window" : "Open enrollment window"}
        </button>
        {windowState?.open && (
          <div className="grid gap-2 text-[12.5px] text-ink-secondary">
            <div>
              Window closes{" "}
              {windowState.expiresAt
                ? new Date(windowState.expiresAt).toLocaleTimeString()
                : "soon"}
              .
            </div>
            <code className="rift-mono bg-muted px-3 py-2 text-ink rounded-[4px]">
              rift node start
            </code>
            <div>
              For another network:{" "}
              <code className="rift-mono">
                rift node start --controller https://CONTROLLER:11748
              </code>
            </div>
          </div>
        )}
      </div>
      {error && (
        <div className="mt-4 rift-surface p-4 text-[13px] text-error" role="alert">
          {error}
        </div>
      )}
      {enrollments.length > 0 && (
        <div className="mt-4 rift-panel">
          <header className="h-10 px-4 border-b border-border flex items-center justify-between">
            <span className="rift-label">Enrollment requests</span>
            <span className="rift-mono text-[11px] text-attention">untrusted until approved</span>
          </header>
          <ul className="divide-y divide-border">
            {enrollments.map((item) => (
              <li key={item.enrollmentId} className="px-4 py-3 flex items-center gap-3">
                <Fingerprint className="size-4 text-primary shrink-0" aria-hidden />
                <button
                  type="button"
                  className="text-left min-w-0 flex-1"
                  onClick={() => setSelected(item.enrollmentId)}
                >
                  <span className="block text-[13px] font-medium text-ink">
                    {item.displayName || item.nodeId || "Unnamed node"}
                  </span>
                  <span className="block rift-mono text-[11px] text-ink-secondary truncate">
                    {item.nodeId} · {item.endpoint}
                  </span>
                </button>
                <span className="rift-mono text-[10.5px] uppercase text-attention">
                  {item.state.replaceAll("_", " ")}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {selected && !active && (
        <div className="mt-4 rift-panel p-4 grid gap-3">
          <label className="grid gap-1.5 max-w-sm">
            <span className="rift-label">Six-digit code shown by the node</span>
            <input
              value={pairingCode}
              onChange={(event) =>
                setPairingCode(event.target.value.replace(/\D/g, "").slice(0, 6))
              }
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              className="h-10 px-3 rounded-[4px] border border-border bg-raised rift-mono"
              placeholder="000000"
            />
          </label>
          <button
            type="button"
            onClick={approve}
            disabled={phase !== "idle" || !/^\d{6}$/.test(pairingCode)}
            className="inline-flex items-center gap-2 h-10 px-4 rounded-[4px] bg-primary text-primary-foreground text-[13px] font-medium disabled:opacity-50 w-fit"
          >
            {phase === "approving" ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <ShieldCheck className="size-4" />
            )}
            Approve and issue certificate
          </button>
        </div>
      )}
      {active && (
        <div className="mt-4 rift-panel p-4 text-[13px] text-ink">
          Node is <strong>ACTIVE</strong> and passed authenticated health verification.
        </div>
      )}
      <PrimaryNext disabled={!active} onClick={onNext} label="Review trusted nodes" />
    </div>
  );
}

function StepEnroll({ onNext }: { onNext: () => void }) {
  const [sightings, setSightings] = useState<MeshSighting[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [challenge, setChallenge] = useState<EnrollmentChallenge | null>(null);
  const [pairingCode, setPairingCode] = useState("");
  const [approvedNode, setApprovedNode] = useState<MeshNode | null>(null);
  const [hasScanned, setHasScanned] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [phase, setPhase] = useState<"idle" | "scanning" | "pairing" | "approving">("idle");

  const scan = async () => {
    setPhase("scanning");
    setErr(null);
    setChallenge(null);
    setApprovedNode(null);
    try {
      const found = await rift.discoverMesh();
      const untrusted = found.filter((item) => item.trustState === "DISCOVERED_UNTRUSTED");
      setSightings(untrusted);
      setSelectedId((current) =>
        untrusted.some((item) => item.sightingId === current) ? current : null,
      );
      setHasScanned(true);
    } catch (error) {
      setErr(error instanceof Error ? error.message : String(error));
    } finally {
      setPhase("idle");
    }
  };

  useEffect(() => {
    let alive = true;
    rift
      .listMeshSightings()
      .then((found) => {
        if (alive) {
          setSightings(found.filter((item) => item.trustState === "DISCOVERED_UNTRUSTED"));
        }
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  const beginPairing = async () => {
    if (!selectedId) return;
    setPhase("pairing");
    setErr(null);
    try {
      setChallenge(await rift.beginMeshEnrollment(selectedId, 120));
      setPairingCode("");
    } catch (error) {
      setErr(error instanceof Error ? error.message : String(error));
    } finally {
      setPhase("idle");
    }
  };

  const approve = async () => {
    if (!challenge || !/^\d{6}$/.test(pairingCode)) return;
    setPhase("approving");
    setErr(null);
    try {
      const result = await rift.approveMeshEnrollment(challenge.enrollmentId, pairingCode.trim());
      setApprovedNode(result.node);
      setSightings((current) => current.filter((item) => item.sightingId !== challenge.sightingId));
    } catch (error) {
      setErr(error instanceof Error ? error.message : String(error));
    } finally {
      setPhase("idle");
    }
  };

  const selected = sightings.find((item) => item.sightingId === selectedId) ?? null;

  return (
    <div>
      <StepTitle
        eyebrow="Step 03 · Discover & trust"
        title="Find a RIFT node on your network"
        description="Discovery only reports nearby agents. Select a sighting, then enter the six-digit code shown on that node to approve pairing."
      />

      <div className="mt-6 rift-surface border border-attention/40 p-4 flex items-start gap-3">
        <LockKeyhole className="size-4 text-attention mt-0.5 shrink-0" aria-hidden />
        <div>
          <div className="text-[13px] font-medium text-ink">Discovery is not trust</div>
          <p className="mt-1 text-[12.5px] text-ink-secondary">
            A visible device remains untrusted until you enter the code displayed locally by that
            device. The controller never receives or displays that code before you submit it.
          </p>
        </div>
      </div>

      <div className="mt-4 flex items-center gap-3">
        <button
          type="button"
          onClick={scan}
          disabled={phase !== "idle"}
          className="inline-flex items-center gap-2 h-10 px-4 rounded-[4px] bg-primary text-primary-foreground text-[13px] font-medium hover:bg-[color:var(--oxide-deep)] disabled:opacity-60"
        >
          {phase === "scanning" ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <RadioTower className="size-4" />
          )}
          {sightings.length ? "Scan again" : "Scan for RIFT nodes"}
        </button>
        {sightings.length > 0 && (
          <span className="rift-mono text-[11.5px] text-ink-secondary">
            {sightings.length} untrusted sighting{sightings.length === 1 ? "" : "s"}
          </span>
        )}
      </div>

      {err && (
        <div className="mt-4 rift-surface p-4 text-[13px] text-error" role="alert">
          {err}
        </div>
      )}

      {hasScanned && !err && sightings.length === 0 && (
        <div className="mt-4 rift-panel p-4">
          <div className="text-[13px] font-medium text-ink">No untrusted RIFT nodes found</div>
          <p className="mt-1 text-[12.5px] text-ink-secondary">
            Passive mDNS and attached ADB devices were checked. Start a RIFT node on the same
            network, or enable an explicit subnet, USB-network, or removable-media scan.
          </p>
        </div>
      )}

      {sightings.length > 0 && !approvedNode && (
        <div className="mt-4 rift-panel">
          <header className="h-10 px-4 border-b border-border flex items-center justify-between">
            <span className="rift-label">Untrusted sightings</span>
            <span className="rift-mono text-[11px] text-attention">approval required</span>
          </header>
          <ul className="divide-y divide-border">
            {sightings.map((item) => {
              const active = selectedId === item.sightingId;
              return (
                <li key={item.sightingId}>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedId(item.sightingId);
                      setChallenge(null);
                      setPairingCode("");
                    }}
                    className={cn(
                      "w-full px-4 py-3 text-left flex items-start gap-3 transition-colors",
                      active ? "bg-muted" : "hover:bg-muted/60",
                    )}
                    aria-pressed={active}
                  >
                    {item.provider.toLowerCase().includes("mdns") ? (
                      <Wifi className="size-4 text-primary mt-0.5 shrink-0" aria-hidden />
                    ) : (
                      <Network className="size-4 text-primary mt-0.5 shrink-0" aria-hidden />
                    )}
                    <span className="min-w-0 flex-1">
                      <span className="block text-[13px] font-medium text-ink">
                        {item.nodeHint}
                      </span>
                      <span className="block rift-mono text-[11.5px] text-ink-secondary mt-1 truncate">
                        {item.endpoint}
                      </span>
                    </span>
                    <span className="text-right shrink-0">
                      <span className="block rift-mono text-[10.5px] uppercase text-attention">
                        untrusted
                      </span>
                      <span className="block rift-mono text-[10.5px] text-ink-secondary mt-1">
                        {item.provider}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {selected && !challenge && !approvedNode && (
        <div className="mt-4 rift-panel p-4 flex items-start gap-3">
          <Fingerprint className="size-4 text-primary mt-0.5 shrink-0" aria-hidden />
          <div className="min-w-0 flex-1">
            <div className="rift-label">Bootstrap fingerprint</div>
            <div className="mt-1 rift-mono text-[12px] text-ink break-all">
              {selected.bootstrapFingerprint}
            </div>
            <p className="mt-2 text-[12px] text-ink-secondary">
              Pairing starts a short-lived challenge. It does not approve the node by itself.
            </p>
          </div>
          <button
            type="button"
            onClick={beginPairing}
            disabled={phase !== "idle"}
            className="inline-flex items-center gap-2 h-9 px-3 rounded-[4px] border border-primary text-[12px] font-medium text-primary hover:bg-muted disabled:opacity-60 shrink-0"
          >
            {phase === "pairing" ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <LockKeyhole className="size-3.5" />
            )}
            Pair node
          </button>
        </div>
      )}

      {challenge && !approvedNode && (
        <div className="mt-4 rift-panel">
          <header className="h-10 px-4 border-b border-border flex items-center justify-between">
            <span className="rift-label">Verify pairing challenge</span>
            <span className="rift-mono text-[11px] text-ink-secondary">
              expires {new Date(challenge.expiresAt).toLocaleTimeString()}
            </span>
          </header>
          <div className="p-4 grid gap-4">
            <div>
              <p className="text-[13px] text-ink">
                Read the six-digit code displayed by {selected?.nodeHint ?? "the node"}, then enter
                it below. RIFT will not reveal the code in the controller UI.
              </p>
            </div>
            <label className="grid gap-1.5 max-w-sm">
              <span className="rift-label">Code shown on the node</span>
              <input
                type="text"
                value={pairingCode}
                onChange={(event) =>
                  setPairingCode(event.target.value.replace(/\D/g, "").slice(0, 6))
                }
                autoComplete="one-time-code"
                inputMode="numeric"
                pattern="[0-9]{6}"
                maxLength={6}
                aria-label="Six-digit code shown on the node"
                placeholder="000000"
                className="h-10 px-3 rounded-[4px] border border-border bg-raised text-[13px] rift-mono focus:outline-none focus:border-primary"
              />
            </label>
            <button
              type="button"
              onClick={approve}
              disabled={!/^\d{6}$/.test(pairingCode) || phase !== "idle"}
              className="justify-self-start inline-flex items-center gap-2 h-10 px-4 rounded-[4px] bg-primary text-primary-foreground text-[13px] font-medium hover:bg-[color:var(--oxide-deep)] disabled:opacity-40"
            >
              {phase === "approving" ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <ShieldCheck className="size-4" />
              )}
              Approve pairing
            </button>
          </div>
        </div>
      )}

      {approvedNode && (
        <div className="mt-4 rift-panel p-4 flex items-start gap-3">
          <ShieldCheck className="size-5 text-attention shrink-0" aria-hidden />
          <div>
            <div className="text-[13px] font-medium text-ink">Pairing approved</div>
            <p className="mt-1 text-[12.5px] text-ink-secondary">
              {approvedNode.hostname} is enrolled as {approvedNode.nodeId}, but it is not routable
              yet. Certificate activation is pending.
            </p>
          </div>
        </div>
      )}

      <PrimaryNext disabled={!approvedNode} onClick={onNext} label="Review trusted nodes" />
    </div>
  );
}

function StepNodesLive({ onNext }: { onNext: () => void }) {
  const [nodes, setNodes] = useState<MeshNode[] | null>(null);
  const [err, setErr] = useState<Error | null>(null);
  useEffect(() => {
    let alive = true;
    const load = () =>
      rift
        .listMeshNodes()
        .then((result) => {
          if (alive) {
            setNodes(result);
            setErr(null);
          }
        })
        .catch((error) => alive && setErr(error));
    load();
    const timer = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  const routableNodes = (nodes ?? []).filter(
    (node) => node.routable && node.trustState === "ACTIVE",
  );
  const pendingNodes = (nodes ?? []).filter((node) => !node.routable);

  return (
    <div>
      <StepTitle
        eyebrow="Step 04 · Enrollment"
        title="Wait for certificate activation"
        description="Pairing approval enrolls an identity, but only an ACTIVE node with a certificate can receive routed work."
      />
      {err ? (
        <div className="mt-6">
          <Unavailable
            endpoint="/api/rift/v2/mesh/nodes"
            resource="MeshNode[]"
            hint="Return to the previous step to discover and approve a node."
          />
        </div>
      ) : (
        <div className="mt-6 rift-panel">
          <header className="h-10 px-4 border-b border-border flex items-center justify-between">
            <span className="rift-label">Controller enrollment registry</span>
            <span className="rift-mono text-[11px] text-ink-secondary">
              {routableNodes.length} routable · {pendingNodes.length} pending
            </span>
          </header>
          <ul className="divide-y divide-border">
            {nodes === null && (
              <li className="px-4 py-6 text-[13px] text-ink-secondary flex items-center gap-2">
                <Loader2 className="size-4 animate-spin text-primary" /> Loading trusted nodes…
              </li>
            )}
            {nodes?.length === 0 && (
              <li className="px-4 py-6 text-[13px] text-ink-secondary">
                No approved nodes. Return to discovery and complete pairing before continuing.
              </li>
            )}
            {(nodes ?? []).map((node) => (
              <li key={node.nodeId} className="px-4 py-3 flex items-center gap-3 text-[13px]">
                <span
                  className={cn(
                    "rift-dot",
                    node.routable && node.healthy ? "text-success" : "text-attention",
                  )}
                  aria-hidden
                />
                <div className="min-w-0">
                  <div className="font-medium text-ink">{node.hostname}</div>
                  <div className="rift-mono text-[11px] text-ink-secondary mt-0.5 truncate">
                    {node.nodeId}
                    {node.endpoint ? ` · ${node.endpoint}` : ""}
                  </div>
                </div>
                <div className="ml-auto text-right shrink-0">
                  <div
                    className={cn(
                      "rift-mono text-[10.5px] uppercase",
                      node.routable ? "text-success" : "text-attention",
                    )}
                  >
                    {node.routable ? node.trustState : "certificate pending"}
                  </div>
                  <div className="rift-mono text-[10.5px] text-ink-secondary mt-0.5">
                    queue {node.queueDepth}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="mt-3 flex items-center gap-2 text-[12px] text-ink-secondary">
        <RefreshCw className="size-3.5" aria-hidden /> Trust registry refreshes every five seconds.
      </div>
      <PrimaryNext
        disabled={routableNodes.length === 0}
        onClick={onNext}
        label="Use active nodes"
      />
    </div>
  );
}

function StepUseCase({
  value,
  onChange,
  onNext,
}: {
  value: UseCase | null;
  onChange: (v: UseCase) => void;
  onNext: () => void;
}) {
  const opts: { id: UseCase; icon: typeof MessageSquare; label: string; desc: string }[] = [
    {
      id: "chat",
      icon: MessageSquare,
      label: "Chat",
      desc: "General assistant, Q&A, casual conversation.",
    },
    {
      id: "coding",
      icon: Code2,
      label: "Coding",
      desc: "Code completion, refactoring, code review.",
    },
    {
      id: "documents",
      icon: FileText,
      label: "Documents / RAG",
      desc: "Summarize and answer over your own documents.",
    },
    {
      id: "agent",
      icon: Bot,
      label: "Agent",
      desc: "Tool use, structured output, multi-step tasks.",
    },
    {
      id: "custom",
      icon: Sliders,
      label: "Custom",
      desc: "Pick your own model or configure manually.",
    },
  ];
  return (
    <div>
      <StepTitle
        eyebrow="Step 05 · Use case"
        title="What do you want to run?"
        description="RIFT uses this to shortlist models and pick sensible defaults."
      />
      <div className="mt-6 grid sm:grid-cols-2 gap-3">
        {opts.map(({ id, icon: Icon, label, desc }) => (
          <button
            key={id}
            type="button"
            onClick={() => onChange(id)}
            aria-pressed={value === id}
            className={cn(
              "text-left rift-panel p-4 focus:outline-none transition-colors",
              value === id ? "border-primary ring-1 ring-primary" : "hover:border-border-strong",
            )}
          >
            <Icon className="size-4 text-primary mb-2" aria-hidden />
            <div className="text-[14px] font-medium text-ink">{label}</div>
            <p className="mt-1 text-[12.5px] text-ink-secondary">{desc}</p>
          </button>
        ))}
      </div>
      <PrimaryNext disabled={!value} onClick={onNext} />
    </div>
  );
}

function StepSource({
  source,
  onChange,
  onNext,
}: {
  source: ModelArtifact["source"] | null;
  onChange: (source: ModelArtifact["source"]) => void;
  onNext: () => void;
}) {
  return (
    <div>
      <StepTitle
        eyebrow="Step 06 / Discovery"
        title="Let RIFT find the model"
        description="No Hugging Face repository ID is required. RIFT searches the Hub index, ranks viable artifacts against the discovered hardware, and returns the strongest practical choices."
      />
      <div className="mt-6 rift-panel overflow-hidden">
        <div className="flex items-start gap-3 border-b border-border bg-primary/5 p-4">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-[4px] border border-primary/30 bg-raised text-primary">
            <Search className="size-4" aria-hidden />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[14px] font-medium text-ink">
                Automatic Hugging Face discovery
              </span>
              <span className="rift-label text-primary">Default</span>
            </div>
            <p className="mt-1 text-[12.5px] leading-5 text-ink-secondary">
              RIFT searches task, format, popularity, recency, and parameter-size query arms,
              removes artifacts that do not fit, then enriches and scores the finalists.
            </p>
          </div>
        </div>
        <div className="grid gap-px bg-border sm:grid-cols-3">
          <DiscoveryStage
            index="01"
            title="Measure"
            detail="GPU, RAM, disk, platform, and installed backends"
          />
          <DiscoveryStage
            index="02"
            title="Search"
            detail="Broad indexed Hub queries without downloading candidates"
          />
          <DiscoveryStage
            index="03"
            title="Rank"
            detail="Exact artifact, backend, fit, quality evidence, and warnings"
          />
        </div>
        <div className="border-t border-border p-4 text-[12px] leading-5 text-ink-secondary">
          This is a broad indexed search, not a literal download or page-by-page crawl of every Hub
          repository. Exact repository pulls remain available for expert workflows through
          <span className="rift-mono text-ink"> rift model pull org/repository</span>.
        </div>
      </div>
      <PrimaryNext
        disabled={!source}
        onClick={() => {
          onChange("huggingface");
          onNext();
        }}
      />
    </div>
  );
}

function DiscoveryStage({
  index,
  title,
  detail,
}: {
  index: string;
  title: string;
  detail: string;
}) {
  return (
    <div className="bg-raised p-4">
      <div className="rift-mono text-[10px] text-primary">{index}</div>
      <div className="mt-1 text-[13px] font-medium text-ink">{title}</div>
      <p className="mt-1 text-[11.5px] leading-5 text-ink-secondary">{detail}</p>
    </div>
  );
}

function StepRecommendation({
  useCase,
  source,
  chosen,
  onChoose,
  onNext,
}: {
  useCase: UseCase;
  source: ModelArtifact["source"];
  chosen: ModelRecommendation | null;
  onChoose: (r: ModelRecommendation) => void;
  onNext: () => void;
}) {
  const [result, setResult] = useState<RecommendationSearchResult | null>(null);
  const [err, setErr] = useState<Error | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let alive = true;
    setResult(null);
    setErr(null);
    rift
      .recommendDetailed({ useCase, source })
      .then((r) => alive && setResult(r))
      .catch((e) => alive && setErr(e));
    return () => {
      alive = false;
    };
  }, [attempt, useCase, source]);

  const [advanced, setAdvanced] = useState(false);

  return (
    <div>
      <StepTitle
        eyebrow="Step 07 · Recommendation"
        title="Choose from RIFT's shortlist"
        description="RIFT found these repositories and exact artifacts automatically. They are ranked for your hardware and use case; no repository ID was supplied."
      />
      {err ? (
        <div className="mt-6">
          <Unavailable
            endpoint="/v1/recommendations"
            method="POST"
            resource="ModelRecommendation[] { priority, artifact, backend, rationale, quality, performance, resources, compromises, warnings }"
          />
        </div>
      ) : !result ? (
        <div className="mt-6 text-[13px] text-ink-secondary inline-flex items-center gap-2">
          <Loader2 className="size-4 animate-spin text-primary" /> Searching the Hub index and
          ranking models for your hardware...
        </div>
      ) : recommendationViewState(result) === "empty" ? (
        <div className="mt-6 border border-attention/30 bg-attention/5 p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-attention" aria-hidden />
            <div className="min-w-0">
              <div className="text-[13px] font-medium text-ink">No shortlist is available</div>
              <p className="mt-1 text-[12px] leading-5 text-ink-secondary">
                {recommendationFailureSummary(result)}
              </p>
              {result.queryArmErrors.length > 0 && (
                <div className="mt-3 space-y-1 text-[10.5px] leading-4 text-ink-muted rift-mono">
                  {result.queryArmErrors.slice(0, 3).map((reason) => (
                    <div key={reason}>{reason}</div>
                  ))}
                </div>
              )}
              <button
                type="button"
                onClick={() => setAttempt((value) => value + 1)}
                className="mt-4 inline-flex items-center gap-1.5 text-[12px] font-medium text-primary hover:text-ink"
              >
                <RefreshCw className="size-3.5" aria-hidden />
                Retry Hub search
              </button>
            </div>
          </div>
        </div>
      ) : (
        <>
          {recommendationViewState(result) === "stale" && (
            <div className="mt-6 flex items-start gap-2 border border-attention/30 bg-attention/5 p-3 text-[12px] text-ink-secondary">
              <RefreshCw className="mt-0.5 size-3.5 shrink-0 text-attention" aria-hidden />
              <span>
                {result.headline ?? "Cached shortlist"}. Live Hub search is unavailable, so verify
                the selected artifact before downloading.
              </span>
              <button
                type="button"
                onClick={() => setAttempt((value) => value + 1)}
                className="ml-auto shrink-0 text-primary hover:text-ink"
              >
                Retry
              </button>
            </div>
          )}
          <div className="mt-6 grid gap-3">
            {result.recommendations.map((r) => (
              <RecommendationCard
                key={r.artifact.id + r.priority}
                rec={r}
                selected={chosen?.artifact.id === r.artifact.id && chosen?.priority === r.priority}
                onSelect={() => onChoose(r)}
              />
            ))}
          </div>
        </>
      )}
      <div className="mt-6">
        <button
          type="button"
          onClick={() => setAdvanced((v) => !v)}
          className="text-[12px] text-ink-secondary hover:text-ink inline-flex items-center gap-1"
        >
          <Sliders className="size-3.5" aria-hidden />
          {advanced ? "Hide advanced" : "Show advanced (formats, quantization, backend flags)"}
        </button>
        {advanced && (
          <div className="mt-3 rift-surface p-4 text-[12.5px] text-ink-secondary rift-mono">
            Advanced knobs (quantization override, backend selection, tensor parallelism, scoring
            internals) live here. Provided per-artifact by{" "}
            <span className="text-ink">/v1/recommendations</span> under
            <span className="text-ink"> advanced</span>.
          </div>
        )}
      </div>
      <PrimaryNext disabled={!chosen} onClick={onNext} />
    </div>
  );
}

function RecommendationCard({
  rec,
  selected,
  onSelect,
}: {
  rec: ModelRecommendation;
  selected: boolean;
  onSelect: () => void;
}) {
  const badge =
    rec.priority === "recommended"
      ? { icon: Sparkles, label: "Recommended", tone: "text-primary" }
      : rec.priority === "quality"
        ? { icon: Gauge, label: "Higher quality", tone: "text-secondary" }
        : { icon: Zap, label: "Higher speed", tone: "text-attention" };
  const B = badge.icon;
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={cn(
        "text-left rift-panel p-5 focus:outline-none transition-colors",
        selected ? "border-primary ring-1 ring-primary" : "hover:border-border-strong",
      )}
    >
      <div className="flex items-center gap-2">
        <B className={cn("size-4", badge.tone)} aria-hidden />
        <span className="rift-label">{badge.label}</span>
        <span className="ml-auto rift-mono text-[11px] text-ink-secondary">
          {rec.artifact.family} · {rec.artifact.parameters}
        </span>
      </div>
      <div className="mt-2 text-[15px] font-medium text-ink">{rec.artifact.displayName}</div>
      <p className="mt-1.5 text-[13px] text-ink-secondary">{rec.rationale}</p>

      <div className="mt-4 grid sm:grid-cols-4 gap-4">
        <RCell
          label="Quality"
          value={`${rec.quality.score} / 100`}
          sub={`${rec.quality.confidence} confidence`}
        />
        <RCell
          label="Speed"
          value={
            rec.performance.measuredTokensPerSec
              ? `${rec.performance.measuredTokensPerSec.toFixed(1)} tok/s measured`
              : rec.performance.estimatedTokensPerSec
                ? `~${rec.performance.estimatedTokensPerSec.toFixed(1)} tok/s`
                : "—"
          }
          sub={
            rec.performance.firstTokenMs
              ? `${rec.performance.firstTokenMs}ms first token`
              : undefined
          }
        />
        <RCell
          label="VRAM"
          value={bytes(rec.resources.vramBytes)}
          sub={`+ KV ${bytes(rec.resources.kvCacheBytes)}`}
        />
        <RCell
          label="Disk"
          value={bytes(rec.resources.diskBytes)}
          sub={`${rec.backend.kind}@${rec.backend.version}`}
        />
      </div>
      {(rec.compromises.length > 0 || rec.warnings.length > 0) && (
        <div className="mt-4 grid gap-1.5">
          {rec.warnings.map((w) => (
            <div key={w} className="flex items-start gap-2 text-[12.5px] text-error">
              <AlertTriangle className="size-3.5 mt-0.5" aria-hidden />
              <span>{w}</span>
            </div>
          ))}
          {rec.compromises.map((c) => (
            <div key={c} className="flex items-start gap-2 text-[12.5px] text-ink-secondary">
              <span className="rift-dot text-attention mt-1.5" aria-hidden />
              <span>{c}</span>
            </div>
          ))}
        </div>
      )}
      <div className="mt-3 rift-mono text-[11px] text-ink-secondary">
        license: {rec.artifact.license} · trust: {rec.artifact.trust}
      </div>
    </button>
  );
}

function RCell({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div>
      <div className="rift-label">{label}</div>
      <div className="rift-mono text-[13px] text-ink mt-1">{value}</div>
      {sub && <div className="rift-mono text-[11px] text-ink-secondary">{sub}</div>}
    </div>
  );
}

function StepService({
  serviceName,
  exposure,
  onChange,
  onNext,
}: {
  serviceName: string;
  exposure: "local" | "lan" | "public";
  onChange: (name: string, exp: "local" | "lan" | "public") => void;
  onNext: () => void;
}) {
  return (
    <div>
      <StepTitle
        eyebrow="Step 08 · Service"
        title="Review service settings"
        description="These control how the model is exposed to clients."
      />
      <div className="mt-6 grid gap-4">
        <label className="grid gap-1.5">
          <span className="rift-label">Service name</span>
          <input
            type="text"
            value={serviceName}
            onChange={(e) => onChange(e.target.value, exposure)}
            placeholder="chat-8b"
            className="h-10 px-3 rounded-[4px] border border-border bg-raised text-[13px] rift-mono focus:outline-none focus:border-primary"
          />
        </label>
        <fieldset className="grid gap-2">
          <legend className="rift-label mb-1">Exposure</legend>
          {[
            {
              id: "local",
              label: "Local only (127.0.0.1)",
              hint: "Default. Only this machine can reach the endpoint.",
            },
            { id: "lan", label: "LAN", hint: "Bind to your local network. Requires an API key." },
            {
              id: "public",
              label: "Public",
              hint: "Reachable beyond LAN. Requires an API key + policy confirmation.",
            },
          ].map((o) => (
            <label
              key={o.id}
              className={cn(
                "flex items-start gap-3 p-3 rift-panel cursor-pointer",
                exposure === o.id && "border-primary ring-1 ring-primary",
              )}
            >
              <input
                type="radio"
                name="exposure"
                className="mt-1"
                checked={exposure === o.id}
                onChange={() => onChange(serviceName, o.id as "local" | "lan" | "public")}
              />
              <span>
                <span className="block text-[13px] font-medium text-ink">{o.label}</span>
                <span className="block text-[12px] text-ink-secondary mt-0.5">{o.hint}</span>
              </span>
            </label>
          ))}
        </fieldset>
      </div>
      <PrimaryNext disabled={!serviceName.trim()} onClick={onNext} label="Review plan" />
    </div>
  );
}

function StepPlan({
  recommendation,
  serviceName,
  exposure,
  plan,
  onPlan,
  onNext,
}: {
  recommendation: ModelRecommendation | null;
  serviceName: string;
  exposure: "local" | "lan" | "public";
  plan: Plan | null;
  onPlan: (p: Plan) => void;
  onNext: () => void;
}) {
  const [err, setErr] = useState<Error | null>(null);
  useEffect(() => {
    if (!recommendation || plan) return;
    let alive = true;
    rift
      .createPlan({
        recommendationRunId: recommendation.recommendationRunId,
        selector:
          recommendation.artifact.repo ??
          (recommendation.priority === "quality"
            ? "highest_quality"
            : recommendation.priority === "speed"
              ? "fastest"
              : "best_estimated"),
        artifactId: recommendation.artifact.id,
        backendKind: recommendation.backend.kind,
        targetNodeId: recommendation.targetNode,
        serviceName,
        exposure,
      })
      .then((p) => alive && onPlan(p))
      .catch((e) => alive && setErr(e));
    return () => {
      alive = false;
    };
  }, [recommendation, serviceName, exposure, plan, onPlan]);

  return (
    <div>
      <StepTitle
        eyebrow="Step 09 · Plan"
        title="Review the deployment plan"
        description="This is an immutable plan. Applying executes exactly what you see here — nothing more."
      />
      {err ? (
        <div className="mt-6">
          <Unavailable
            endpoint="/v1/plans"
            method="POST"
            resource="Plan { id, hash, actions[], affectedNodes, expectedDowntimeMs, rollback }"
          />
        </div>
      ) : !plan ? (
        <div className="mt-6 text-[13px] text-ink-secondary inline-flex items-center gap-2">
          <Loader2 className="size-4 animate-spin text-primary" /> Building plan…
        </div>
      ) : (
        <PlanReview plan={plan} />
      )}
      <PrimaryNext disabled={!plan} onClick={onNext} label="Apply plan" />
    </div>
  );
}

export function PlanReview({ plan }: { plan: Plan }) {
  const groups: Plan["actions"][number]["group"][] = [
    "install",
    "download",
    "configure",
    "place",
    "launch",
    "expose",
    "benchmark",
    "recover",
  ];
  const byGroup = Object.fromEntries(
    groups.map((g) => [g, plan.actions.filter((a) => a.group === g)]),
  ) as Record<Plan["actions"][number]["group"], Plan["actions"]>;

  return (
    <div className="mt-6 grid gap-4">
      <div className="rift-panel p-4">
        <div className="grid sm:grid-cols-4 gap-4">
          <div>
            <div className="rift-label">Plan hash</div>
            <div className="rift-mono text-[12.5px] mt-1 text-ink truncate" title={plan.hash}>
              {plan.hash.slice(0, 16)}…
            </div>
          </div>
          <div>
            <div className="rift-label">Affected nodes</div>
            <div className="rift-mono text-[13px] mt-1 text-ink">{plan.affectedNodes.length}</div>
          </div>
          <div>
            <div className="rift-label">Expected downtime</div>
            <div className="rift-mono text-[13px] mt-1 text-ink">
              {plan.expectedDowntimeMs ? `${Math.round(plan.expectedDowntimeMs / 1000)}s` : "none"}
            </div>
          </div>
          <div>
            <div className="rift-label">Rollback</div>
            <div className="rift-mono text-[13px] mt-1 text-ink">
              {plan.rollback.supported ? "supported" : "manual"}
            </div>
          </div>
        </div>
      </div>
      {groups
        .filter((g) => byGroup[g].length > 0)
        .map((g) => (
          <div key={g} className="rift-panel">
            <header className="h-10 px-4 border-b border-border flex items-center justify-between">
              <span className="rift-label">{g}</span>
              <span className="rift-mono text-[11px] text-ink-secondary">
                {byGroup[g].length} action{byGroup[g].length === 1 ? "" : "s"}
              </span>
            </header>
            <ul>
              {byGroup[g].map((a) => (
                <li
                  key={a.id}
                  className="px-4 py-3 border-b border-border last:border-0 flex items-start gap-3"
                >
                  <span
                    className={cn(
                      "rift-dot mt-1.5",
                      a.risk === "high"
                        ? "text-error"
                        : a.risk === "medium"
                          ? "text-attention"
                          : "text-secondary",
                    )}
                    aria-hidden
                  />
                  <div className="min-w-0 flex-1">
                    <div className="text-[13px] text-ink">{a.summary}</div>
                    <div className="rift-mono text-[11.5px] text-ink-secondary mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5">
                      {a.nodeId && <span>node: {a.nodeId}</span>}
                      {a.artifact?.sizeBytes != null && (
                        <span>size: {bytes(a.artifact.sizeBytes)}</span>
                      )}
                      {a.artifact?.sha256 && <span>sha256: {a.artifact.sha256.slice(0, 12)}…</span>}
                      {a.reserves?.vramBytes != null && (
                        <span>vram: {bytes(a.reserves.vramBytes)}</span>
                      )}
                      {a.ports && a.ports.length > 0 && <span>ports: {a.ports.join(", ")}</span>}
                      <span>risk: {a.risk}</span>
                      {!a.reversible && <span className="text-error">non-reversible</span>}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ))}
    </div>
  );
}

function StepApply({
  plan,
  onApplied,
}: {
  plan: Plan | null;
  onApplied: (progress: ApplyProgress) => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [err, setErr] = useState<Error | null>(null);
  const [allowDownload, setAllowDownload] = useState(false);
  const [allowInstall, setAllowInstall] = useState(false);
  const [allowLaunch, setAllowLaunch] = useState(false);

  const needs = (group: Plan["actions"][number]["group"]) =>
    Boolean(plan?.actions.some((action) => action.group === group));
  const permissionsReady =
    (!needs("download") || allowDownload) &&
    (!needs("install") || allowInstall) &&
    (!needs("launch") || allowLaunch);

  const apply = async () => {
    if (!plan) return;
    setConfirming(true);
    try {
      const progress = await rift.applyPlan(plan.id, plan.hash, {
        configPath: plan.configPath ?? "",
        allowDownload,
        allowInstall,
        allowLaunch,
      });
      onApplied(progress);
    } catch (e) {
      setErr(e as Error);
      setConfirming(false);
    }
  };

  return (
    <div>
      <StepTitle
        eyebrow="Step 10 · Apply"
        title="Confirm and apply"
        description="One confirmation applies the exact plan you just reviewed."
      />
      <div className="mt-6 rift-panel p-5">
        <div className="grid gap-3 text-[13px]">
          <div className="flex items-center gap-2">
            <ShieldCheck className="size-4 text-secondary" aria-hidden />
            <span className="text-ink">Reviewed plan will execute by hash</span>
            <span className="rift-mono text-[11.5px] text-ink-secondary ml-auto">
              {plan?.hash.slice(0, 16)}…
            </span>
          </div>
          <p className="text-ink-secondary">
            Apply installs, downloads, configures, and launches only what this plan specifies. Any
            drift aborts the operation.
          </p>
        </div>
        {err && (
          <div className="mt-4 rift-surface p-3 text-[13px] text-error" role="alert">
            {err.message}
          </div>
        )}
        <div className="mt-5 grid gap-2 border-t border-border pt-4">
          {(
            [
              ["download", "Download the selected model artifact", allowDownload, setAllowDownload],
              ["install", "Install the selected backend", allowInstall, setAllowInstall],
              ["launch", "Launch the local inference service", allowLaunch, setAllowLaunch],
            ] as const
          ).map(([group, label, checked, setChecked]) =>
            needs(group) ? (
              <label key={group} className="flex items-start gap-2 text-[13px] text-ink">
                <input
                  type="checkbox"
                  className="mt-0.5 accent-[var(--oxide)]"
                  checked={checked}
                  onChange={(event) => setChecked(event.target.checked)}
                />
                <span>
                  <span className="block">{label}</span>
                  <span className="rift-mono text-[11px] text-ink-secondary">
                    Explicit permission for this apply only.
                  </span>
                </span>
              </label>
            ) : null,
          )}
        </div>
        <div className="mt-5 flex items-center gap-3">
          <button
            type="button"
            onClick={apply}
            disabled={!plan || confirming || !permissionsReady}
            className="inline-flex items-center gap-2 h-10 px-4 rounded-[4px] bg-primary text-primary-foreground text-[13px] font-medium hover:bg-[color:var(--oxide-deep)] disabled:opacity-60"
          >
            {confirming ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Check className="size-4" />
            )}
            Apply plan
          </button>
          <span className="rift-mono text-[11.5px] text-ink-secondary">
            You can restrict future applies with a policy in Settings → Policies.
          </span>
        </div>
      </div>
    </div>
  );
}

function StepProgress({
  plan,
  initialProgress,
  onNext,
}: {
  plan: Plan;
  initialProgress: ApplyProgress | null;
  onNext: () => void;
}) {
  const [percent, setPercent] = useState(initialProgress?.percent ?? 5);
  const [phase, setPhase] = useState<string>(initialProgress?.phase ?? "queued");
  const [message, setMessage] = useState<string>(initialProgress?.message ?? "Waiting to start…");
  const [done, setDone] = useState(initialProgress?.phase === "succeeded");

  useEffect(() => {
    if (initialProgress?.phase === "succeeded") return undefined;
    let alive = true;
    const poll = async () => {
      try {
        const service = await rift.getService(plan.serviceId);
        if (!alive) return;
        setPhase(service.status === "running" ? "succeeded" : service.status);
        setPercent(service.status === "running" ? 100 : 65);
        setMessage(
          service.status === "running"
            ? "The service is healthy and ready."
            : `Service status: ${service.status}`,
        );
        if (service.status === "running") setDone(true);
      } catch {
        // The controller may not publish the service until launch completes.
      }
    };
    void poll();
    const timer = window.setInterval(poll, 2_000);
    const timeout = window.setTimeout(() => {
      if (alive && !done) {
        setPhase("failed");
        setMessage("The controller did not report a ready service within 60 seconds.");
      }
    }, 60_000);
    return () => {
      alive = false;
      window.clearInterval(timer);
      window.clearTimeout(timeout);
    };
  }, [plan.id, plan.serviceId, initialProgress, done]);

  return (
    <div>
      <StepTitle
        eyebrow="Step 11 · Progress"
        title="Applying"
        description={`Executing plan ${plan.hash.slice(0, 12)}…`}
      />
      <div className="mt-6 rift-panel p-5">
        <div className="flex items-center justify-between mb-2">
          <span className="rift-label">{phase}</span>
          <span className="rift-mono text-[12px] text-ink">{Math.round(percent)}%</span>
        </div>
        <div className="h-1.5 bg-muted rounded-[2px] overflow-hidden">
          <div className="h-full bg-primary transition-all" style={{ width: `${percent}%` }} />
        </div>
        <div className="mt-3 rift-mono text-[12.5px] text-ink">{message}</div>
      </div>
      <PrimaryNext disabled={!done} onClick={onNext} label="Finish" />
    </div>
  );
}

function StepFinish({ state }: { state: SetupState }) {
  const endpoint =
    state.plan?.endpointUrl ??
    (state.exposure === "local"
      ? "http://127.0.0.1:11735/v1"
      : "http://<controller-host>:11735/v1");
  return (
    <div>
      <StepTitle
        eyebrow="Step 12 · Finish"
        title="Deployment complete"
        description="Your service is running. Try it below or copy an endpoint for your app."
      />
      <div className="mt-6 grid gap-4">
        <div className="rift-panel p-5">
          <div className="rift-label mb-2">Endpoint</div>
          <div className="flex items-center gap-2">
            <code className="flex-1 rift-mono text-[13px] text-ink break-all">{endpoint}</code>
            <button
              type="button"
              onClick={() => navigator.clipboard.writeText(endpoint)}
              className="inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] border border-border text-[12px] hover:bg-muted"
            >
              <Copy className="size-3.5" /> Copy
            </button>
          </div>
          <p className="mt-3 rift-mono text-[11px] text-ink-secondary">
            OpenAI-compatible · use with the OpenAI SDK by overriding{" "}
            <span className="text-ink">baseURL</span>
          </p>
        </div>

        <div className="rift-panel p-5">
          <div className="rift-label mb-2">Client example</div>
          <pre className="rift-mono text-[12.5px] text-ink whitespace-pre-wrap">
            {`from openai import OpenAI

client = OpenAI(base_url="${endpoint}", api_key="rift-key")
r = client.chat.completions.create(
  model="${state.chosenRecommendation?.artifact.displayName ?? "your-model"}",
  messages=[{"role": "user", "content": "Say hi"}],
)
print(r.choices[0].message.content)`}
          </pre>
        </div>

        <div className="rift-panel p-5">
          <div className="flex items-center gap-2">
            <div className="rift-label">Measured benchmark</div>
            <span className="ml-auto rift-mono text-[11px] text-ink-secondary">just now</span>
          </div>
          <div className="mt-2 grid grid-cols-3 gap-4">
            <div>
              <div className="rift-mono text-[18px] text-ink">
                {state.chosenRecommendation?.performance.measuredTokensPerSec?.toFixed(1) ?? "—"}
              </div>
              <div className="rift-label">tok/s</div>
            </div>
            <div>
              <div className="rift-mono text-[18px] text-ink">
                {state.chosenRecommendation?.performance.firstTokenMs ?? "—"}
              </div>
              <div className="rift-label">first token ms</div>
            </div>
            <div>
              <div className="rift-mono text-[18px] text-ink">
                {state.chosenRecommendation?.quality.score ?? "—"}
              </div>
              <div className="rift-label">quality</div>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <a
            href="/deployments"
            className="inline-flex items-center gap-2 h-10 px-4 rounded-[4px] bg-primary text-primary-foreground text-[13px] font-medium hover:bg-[color:var(--oxide-deep)]"
          >
            <ArrowRight className="size-4" /> Open deployment
          </a>
          <a
            href="/deployments"
            className="inline-flex items-center gap-2 h-10 px-4 rounded-[4px] border border-border text-[13px] font-medium hover:bg-muted"
          >
            <MessageSquare className="size-4" /> Test in playground
          </a>
          <a
            href="#"
            className="inline-flex items-center gap-2 h-10 px-4 rounded-[4px] border border-border text-[13px] font-medium hover:bg-muted text-ink-secondary"
          >
            <Terminal className="size-4" /> Show CLI equivalent
          </a>
        </div>

        <div className="mt-2 flex items-center gap-3 rift-mono text-[11px] text-ink-secondary">
          <span className="inline-flex items-center gap-1">
            <Cpu className="size-3" /> hardware discovered
          </span>
          <span className="inline-flex items-center gap-1">
            <MemoryStick className="size-3" /> resources reserved
          </span>
          <span className="inline-flex items-center gap-1">
            <HardDrive className="size-3" /> artifact verified
          </span>
          <a href="#" className="ml-auto inline-flex items-center gap-1 hover:text-ink">
            <ExternalLink className="size-3" /> API reference
          </a>
        </div>
      </div>
    </div>
  );
}

function StepTitle({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description?: string;
}) {
  return (
    <div>
      <div className="rift-label mb-2">{eyebrow}</div>
      <h1 className="text-[24px] leading-tight font-medium text-ink">{title}</h1>
      {description && (
        <p className="mt-2 text-[13.5px] text-ink-secondary max-w-2xl">{description}</p>
      )}
      <div className="rift-ticks mt-5" aria-hidden />
    </div>
  );
}

function PrimaryNext({
  onClick,
  disabled,
  label = "Continue",
}: {
  onClick: () => void;
  disabled?: boolean;
  label?: string;
}) {
  return (
    <div className="mt-8">
      <button
        type="button"
        onClick={onClick}
        disabled={disabled}
        className="inline-flex items-center gap-2 h-10 px-4 rounded-[4px] bg-primary text-primary-foreground text-[13px] font-medium hover:bg-[color:var(--oxide-deep)] disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {label} <ArrowRight className="size-4" aria-hidden />
      </button>
    </div>
  );
}
