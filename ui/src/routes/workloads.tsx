import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/rift/app-shell";
import { PageHeader, Panel } from "@/components/rift/primitives";
import { rift } from "@/lib/rift/client";

export const Route = createFileRoute("/workloads")({
  head: () => ({ meta: [{ title: "Easy deployment — RIFT" }] }),
  component: WorkloadsPage,
});

function WorkloadsPage() {
  const [input, setInput] = useState("Private coding assistant; at least 30 tok/s; 8K context; offline");
  const [inputMode, setInputMode] = useState<"natural" | "json">("natural");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [network, setNetwork] = useState<"offline" | "approved_sources">("offline");
  const [allowLaunch, setAllowLaunch] = useState(false);
  const [allowRestart, setAllowRestart] = useState(false);
  const [allowPromote, setAllowPromote] = useState(false);
  const [allowCleanup, setAllowCleanup] = useState(false);
  const [allowDownload, setAllowDownload] = useState(false);
  const [allowInstall, setAllowInstall] = useState(false);
  const [modelsDir, setModelsDir] = useState("");
  const [qualityConfirmed, setQualityConfirmed] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const [runOperationId, setRunOperationId] = useState<string | null>(null);
  const [runState, setRunState] = useState<Record<string, unknown> | null>(null);
  const [runBusy, setRunBusy] = useState(false);
  function parseInput(): string | Record<string, unknown> {
    if (inputMode === "natural") return input;
    const parsed: unknown = JSON.parse(input);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("JSON workload must be an object");
    return parsed as Record<string, unknown>;
  }
  async function compile() {
    setBusy(true);
    setError(null);
    setQualityConfirmed(false);
    setRunId(null);
    setRunOperationId(null);
    setRunState(null);
    try {
      setResult(await rift.compileWorkload(parseInput(), true));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }
  async function confirmDefaultQuality() {
    setBusy(true);
    setError(null);
    try {
      const parsed = parseInput();
      const workload = typeof parsed === "string" ? { workload_text: parsed } : parsed;
      const compiled = await rift.compileWorkload({ ...workload,
        quality: { suite_id: "rift-text-core", suite_version: "v1", minimum_score: 0.9, required_cases: ["response_nonempty"] },
      }, true);
      setResult(compiled);
      setQualityConfirmed(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }
  async function approveAndRun() {
    if (!result?.draft_id || questions.length > 0) return;
    setBusy(true);
    setError(null);
    try {
      const actions = { cleanup: allowCleanup, download: network === "approved_sources" && allowDownload, install: network === "approved_sources" && allowInstall, promote: allowPromote, remote_execution: false, restart: allowRestart, temporary_launch: allowLaunch };
      const bytes = network === "offline" ? 0 : 36 * 1024 ** 3;
      const envelope = { schema_version: 1, actions, targets: ["local"], sources: ["huggingface"], licenses: ["Apache-2.0"], network, limits: { exploration_seconds: 3600, max_artifacts: 3, tuning_candidates: 24, per_artifact_bytes: bytes, total_download_bytes: bytes }, allow_quantization_alternatives: false, exposure: "loopback", operations_mode: "recover" };
      const policyId = `easy-${String(result.draft_id).slice(0, 12)}`;
      const policy = await rift.saveWorkloadPolicy(envelope, policyId, 0);
      const approval = await rift.approveWorkload(String(result.draft_id), { revision: result.revision, contract_hash: result.contract_hash, policy_id: policy.policy_id, policy_revision: policy.revision, envelope, envelope_hash: policy.policy_hash });
      const run = await rift.startWorkloadRun(String(approval.approval_id), { modelsDir: modelsDir || undefined });
      setResult({ ...result, approval, run });
      const startedRunId = typeof run.run_id === "string" ? run.run_id : null;
      setRunId(startedRunId);
      setRunOperationId(typeof run.operation_id === "string" ? run.operation_id : null);
      setRunState(startedRunId ? run : null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }
  async function cancelRun() {
    const operationId = runOperationId || (typeof runState?.result === "object" && runState.result !== null
      ? String((runState.result as Record<string, unknown>).operation_id ?? "")
      : "");
    if (!operationId) return;
    setError(null);
    try {
      await rift.cancelOperation(operationId, "Cancelled easy-path workload deployment");
      setRunState((current) => current ? { ...current, status: "CANCEL_REQUESTED" } : current);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }
  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    const poll = async () => {
      setRunBusy(true);
      try {
        const next = await rift.getWorkloadRun(runId);
        if (!cancelled) setRunState(next);
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : String(cause));
      } finally {
        if (!cancelled) setRunBusy(false);
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 3000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [runId]);
  const contract = (result?.contract ?? {}) as Record<string, unknown>;
  const questions = Array.isArray(result?.questions) ? result.questions : [];
  const unsupported = Array.isArray(result?.unsupported_requirements) ? result.unsupported_requirements : [];
  const qualityQuestion = questions.some((question) => String(question).toLowerCase().includes("quality suite"));
  const runStatus = String(runState?.status ?? "").toUpperCase();
  const runEvents = Array.isArray(runState?.events) ? runState.events as Array<Record<string, unknown>> : [];
  return (
    <AppShell>
      <PageHeader eyebrow="Easy deployment" title="Describe a workload" description="RIFT interprets the request, shows its assumptions, and asks for approval before any deployment action." />
      <div className="max-w-[1100px] mx-auto px-4 py-6 grid gap-4 lg:grid-cols-2">
        <Panel title="Workload request">
          <div className="mb-2 flex items-center gap-2 text-[12px]"><span className="rift-label">Input format</span><select value={inputMode} onChange={(event) => { setInputMode(event.target.value as "natural" | "json"); setResult(null); setQualityConfirmed(false); }} className="rounded border border-border bg-canvas px-2 py-1"><option value="natural">Natural language</option><option value="json">Structured JSON</option></select></div>
          <textarea value={input} onChange={(event) => { setInput(event.target.value); setQualityConfirmed(false); }} rows={10} className="w-full rounded border border-border bg-canvas p-3 text-[13px] leading-6 text-ink" aria-label={inputMode === "json" ? "Structured JSON workload" : "Natural-language workload"} />
          <button type="button" onClick={compile} disabled={busy || !input.trim()} className="mt-3 h-9 px-4 rounded bg-primary text-primary-foreground text-[13px] disabled:opacity-50">{busy ? "Compiling…" : "Compile for review"}</button>
          {error && <p className="mt-3 text-[12px] text-attention">{error}</p>}
          <p className="mt-4 text-[11px] text-ink-secondary">Compilation is local. Deployment starts only after you review and explicitly approve the permission envelope.</p>
        </Panel>
        <Panel title="Compiled contract">
          {!result ? <p className="text-[13px] text-ink-secondary">Your interpreted requirements will appear here.</p> : <>
            <pre className="max-h-[360px] overflow-auto rounded bg-canvas p-3 text-[11px] text-ink">{JSON.stringify(contract, null, 2)}</pre>
            {questions.length > 0 && <div className="mt-3 rounded border border-attention/40 bg-attention/5 p-3 text-[12px]"><strong>Review questions</strong><ul className="mt-1 list-disc pl-4">{questions.map((question) => <li key={String(question)}>{String(question)}</li>)}</ul></div>}
            {qualityQuestion && <div className="mt-3 rounded border border-border bg-muted/40 p-3 text-[12px]"><strong>Quality acceptance</strong><p className="mt-1 text-ink-secondary">RIFT needs a versioned suite before it can make a defensible pass/fail claim.</p><button type="button" onClick={confirmDefaultQuality} disabled={busy} className="mt-2 h-8 rounded border border-border bg-raised px-3 text-[12px] disabled:opacity-50">{busy ? "Confirming…" : "Use rift-text-core/v1 (0.90)"}</button></div>}
            {unsupported.length > 0 && <div className="mt-3 rounded border border-border p-3 text-[12px]"><strong>Captured but not executable in v1</strong><ul className="mt-1 list-disc pl-4">{unsupported.map((item, index) => <li key={index}>{String((item as Record<string, unknown>).value)}</li>)}</ul></div>}
            <p className="mt-3 rift-mono text-[10px] text-ink-secondary">contract hash: {String(result.contract_hash ?? "unavailable")}</p>
            <div className="mt-4 border-t border-border pt-4 space-y-3 text-[12px]">
              <div className="font-medium">Execution approval</div>
              <label className="block">Network policy<select value={network} onChange={(event) => setNetwork(event.target.value as "offline" | "approved_sources")} className="ml-2 rounded border border-border bg-canvas px-2 py-1"><option value="offline">Offline (no downloads)</option><option value="approved_sources">Approved sources</option></select></label>
              {network === "offline" && <label className="block">Local models directory<input value={modelsDir} onChange={(event) => setModelsDir(event.target.value)} placeholder="C:\\models" className="ml-2 rounded border border-border bg-canvas px-2 py-1" /></label>}
              <div className="flex flex-wrap gap-3">
                <label><input type="checkbox" checked={allowLaunch} onChange={(event) => setAllowLaunch(event.target.checked)} /> temporary launch</label>
                <label><input type="checkbox" checked={allowRestart} onChange={(event) => setAllowRestart(event.target.checked)} /> restart for tuning</label>
                <label><input type="checkbox" checked={allowPromote} onChange={(event) => setAllowPromote(event.target.checked)} /> promote winner</label>
                <label><input type="checkbox" checked={allowCleanup} onChange={(event) => setAllowCleanup(event.target.checked)} /> cleanup run-owned trials</label>
                {network === "approved_sources" && <><label><input type="checkbox" checked={allowDownload} onChange={(event) => setAllowDownload(event.target.checked)} /> download artifacts</label><label><input type="checkbox" checked={allowInstall} onChange={(event) => setAllowInstall(event.target.checked)} /> install backend</label></>}
              </div>
              <button type="button" onClick={approveAndRun} disabled={busy || questions.length > 0 || !allowLaunch || (network === "offline" && !modelsDir.trim()) || (network === "approved_sources" && !allowDownload)} className="h-9 px-4 rounded bg-primary text-primary-foreground disabled:opacity-50">{busy ? "Approving…" : "Approve & start deployment"}</button>
              {questions.length > 0 && <p className="text-attention">Resolve the review questions before approval.</p>}
              {Boolean(result.approval) && <p className="text-secondary">Approval recorded: {String((result.approval as Record<string, unknown>).approval_id)}. Run started: {String((result.run as Record<string, unknown> | undefined)?.operation_id ?? "pending")}</p>}
              {qualityConfirmed && <p className="text-ink-secondary">Quality suite confirmed: rift-text-core/v1, minimum score 0.90.</p>}
            </div>
          </>}
        </Panel>
        {runId && <Panel title="Autonomous run">
          <div className="flex items-center justify-between text-[12px]"><span className="font-medium">{runStatus || "QUEUED"}</span><span className="text-ink-secondary">{runBusy ? "Refreshing…" : "Live journal"}</span></div>
          <ol className="mt-3 space-y-2 text-[12px]">{runEvents.map((event) => <li key={String(event.sequence)} className="flex gap-2"><span className="rift-mono text-ink-secondary">{String(event.stage)}</span><span>{String(event.message)}</span></li>)}</ol>
          {runStatus && ["QUEUED", "RUNNING", "CANCEL_REQUESTED"].includes(runStatus) && <button type="button" onClick={cancelRun} className="mt-3 h-8 rounded border border-border px-3 text-[12px]">Cancel and recover</button>}
          {runState && Object.prototype.hasOwnProperty.call(runState, "result") && <pre className="mt-3 max-h-[280px] overflow-auto rounded bg-canvas p-3 text-[11px] text-ink">{JSON.stringify(runState.result, null, 2)}</pre>}
        </Panel>}
      </div>
    </AppShell>
  );
}
