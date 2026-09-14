import { c as __toESM, i as require_react, r as require_jsx_runtime } from "./useRouter-C3Fl0Qct.js";
import { n as PageHeader, o as AppShell, r as Panel } from "./primitives-CK9JOCwG.js";
import { I as rift } from "./hooks-DK2temI-.js";
//#region src/routes/workloads.tsx?tsr-split=component
var import_react = /* @__PURE__ */ __toESM(require_react());
var import_jsx_runtime = require_jsx_runtime();
function WorkloadsPage() {
	const [input, setInput] = (0, import_react.useState)("Private coding assistant; at least 30 tok/s; 8K context; offline");
	const [inputMode, setInputMode] = (0, import_react.useState)("natural");
	const [result, setResult] = (0, import_react.useState)(null);
	const [busy, setBusy] = (0, import_react.useState)(false);
	const [error, setError] = (0, import_react.useState)(null);
	const [network, setNetwork] = (0, import_react.useState)("offline");
	const [allowLaunch, setAllowLaunch] = (0, import_react.useState)(false);
	const [allowRestart, setAllowRestart] = (0, import_react.useState)(false);
	const [allowPromote, setAllowPromote] = (0, import_react.useState)(false);
	const [allowCleanup, setAllowCleanup] = (0, import_react.useState)(false);
	const [allowDownload, setAllowDownload] = (0, import_react.useState)(false);
	const [allowInstall, setAllowInstall] = (0, import_react.useState)(false);
	const [modelsDir, setModelsDir] = (0, import_react.useState)("");
	const [qualityConfirmed, setQualityConfirmed] = (0, import_react.useState)(false);
	const [runId, setRunId] = (0, import_react.useState)(null);
	const [runOperationId, setRunOperationId] = (0, import_react.useState)(null);
	const [runState, setRunState] = (0, import_react.useState)(null);
	const [runBusy, setRunBusy] = (0, import_react.useState)(false);
	function parseInput() {
		if (inputMode === "natural") return input;
		const parsed = JSON.parse(input);
		if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("JSON workload must be an object");
		return parsed;
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
			const compiled = await rift.compileWorkload({
				...workload,
				quality: {
					suite_id: "rift-text-core",
					suite_version: "v1",
					minimum_score: .9,
					required_cases: ["response_nonempty"]
				}
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
			const actions = {
				cleanup: allowCleanup,
				download: network === "approved_sources" && allowDownload,
				install: network === "approved_sources" && allowInstall,
				promote: allowPromote,
				remote_execution: false,
				restart: allowRestart,
				temporary_launch: allowLaunch
			};
			const bytes = network === "offline" ? 0 : 36 * 1024 ** 3;
			const envelope = {
				schema_version: 1,
				actions,
				targets: ["local"],
				sources: ["huggingface"],
				licenses: ["Apache-2.0"],
				network,
				limits: {
					exploration_seconds: 3600,
					max_artifacts: 3,
					tuning_candidates: 24,
					per_artifact_bytes: bytes,
					total_download_bytes: bytes
				},
				allow_quantization_alternatives: false,
				exposure: "loopback",
				operations_mode: "recover"
			};
			const policyId = `easy-${String(result.draft_id).slice(0, 12)}`;
			const policy = await rift.saveWorkloadPolicy(envelope, policyId, 0);
			const approval = await rift.approveWorkload(String(result.draft_id), {
				revision: result.revision,
				contract_hash: result.contract_hash,
				policy_id: policy.policy_id,
				policy_revision: policy.revision,
				envelope,
				envelope_hash: policy.policy_hash
			});
			const run = await rift.startWorkloadRun(String(approval.approval_id), { modelsDir: modelsDir || void 0 });
			setResult({
				...result,
				approval,
				run
			});
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
		const operationId = runOperationId || (typeof runState?.result === "object" && runState.result !== null ? String(runState.result.operation_id ?? "") : "");
		if (!operationId) return;
		setError(null);
		try {
			await rift.cancelOperation(operationId, "Cancelled easy-path workload deployment");
			setRunState((current) => current ? {
				...current,
				status: "CANCEL_REQUESTED"
			} : current);
		} catch (cause) {
			setError(cause instanceof Error ? cause.message : String(cause));
		}
	}
	(0, import_react.useEffect)(() => {
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
		poll();
		const timer = window.setInterval(() => void poll(), 3e3);
		return () => {
			cancelled = true;
			window.clearInterval(timer);
		};
	}, [runId]);
	const contract = result?.contract ?? {};
	const questions = Array.isArray(result?.questions) ? result.questions : [];
	const unsupported = Array.isArray(result?.unsupported_requirements) ? result.unsupported_requirements : [];
	const qualityQuestion = questions.some((question) => String(question).toLowerCase().includes("quality suite"));
	const runStatus = String(runState?.status ?? "").toUpperCase();
	const runEvents = Array.isArray(runState?.events) ? runState.events : [];
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(AppShell, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(PageHeader, {
		eyebrow: "Easy deployment",
		title: "Describe a workload",
		description: "RIFT interprets the request, shows its assumptions, and asks for approval before any deployment action."
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "max-w-[1100px] mx-auto px-4 py-6 grid gap-4 lg:grid-cols-2",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Panel, {
				title: "Workload request",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "mb-2 flex items-center gap-2 text-[12px]",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "rift-label",
							children: "Input format"
						}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("select", {
							value: inputMode,
							onChange: (event) => {
								setInputMode(event.target.value);
								setResult(null);
								setQualityConfirmed(false);
							},
							className: "rounded border border-border bg-canvas px-2 py-1",
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
								value: "natural",
								children: "Natural language"
							}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
								value: "json",
								children: "Structured JSON"
							})]
						})]
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("textarea", {
						value: input,
						onChange: (event) => {
							setInput(event.target.value);
							setQualityConfirmed(false);
						},
						rows: 10,
						className: "w-full rounded border border-border bg-canvas p-3 text-[13px] leading-6 text-ink",
						"aria-label": inputMode === "json" ? "Structured JSON workload" : "Natural-language workload"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
						type: "button",
						onClick: compile,
						disabled: busy || !input.trim(),
						className: "mt-3 h-9 px-4 rounded bg-primary text-primary-foreground text-[13px] disabled:opacity-50",
						children: busy ? "Compiling…" : "Compile for review"
					}),
					error && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "mt-3 text-[12px] text-attention",
						children: error
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "mt-4 text-[11px] text-ink-secondary",
						children: "Compilation is local. Deployment starts only after you review and explicitly approve the permission envelope."
					})
				]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
				title: "Compiled contract",
				children: !result ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
					className: "text-[13px] text-ink-secondary",
					children: "Your interpreted requirements will appear here."
				}) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("pre", {
						className: "max-h-[360px] overflow-auto rounded bg-canvas p-3 text-[11px] text-ink",
						children: JSON.stringify(contract, null, 2)
					}),
					questions.length > 0 && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "mt-3 rounded border border-attention/40 bg-attention/5 p-3 text-[12px]",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("strong", { children: "Review questions" }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
							className: "mt-1 list-disc pl-4",
							children: questions.map((question) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("li", { children: String(question) }, String(question)))
						})]
					}),
					qualityQuestion && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "mt-3 rounded border border-border bg-muted/40 p-3 text-[12px]",
						children: [
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("strong", { children: "Quality acceptance" }),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
								className: "mt-1 text-ink-secondary",
								children: "RIFT needs a versioned suite before it can make a defensible pass/fail claim."
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
								type: "button",
								onClick: confirmDefaultQuality,
								disabled: busy,
								className: "mt-2 h-8 rounded border border-border bg-raised px-3 text-[12px] disabled:opacity-50",
								children: busy ? "Confirming…" : "Use rift-text-core/v1 (0.90)"
							})
						]
					}),
					unsupported.length > 0 && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "mt-3 rounded border border-border p-3 text-[12px]",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("strong", { children: "Captured but not executable in v1" }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
							className: "mt-1 list-disc pl-4",
							children: unsupported.map((item, index) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("li", { children: String(item.value) }, index))
						})]
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", {
						className: "mt-3 rift-mono text-[10px] text-ink-secondary",
						children: ["contract hash: ", String(result.contract_hash ?? "unavailable")]
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "mt-4 border-t border-border pt-4 space-y-3 text-[12px]",
						children: [
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
								className: "font-medium",
								children: "Execution approval"
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
								className: "block",
								children: ["Network policy", /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("select", {
									value: network,
									onChange: (event) => setNetwork(event.target.value),
									className: "ml-2 rounded border border-border bg-canvas px-2 py-1",
									children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
										value: "offline",
										children: "Offline (no downloads)"
									}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
										value: "approved_sources",
										children: "Approved sources"
									})]
								})]
							}),
							network === "offline" && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
								className: "block",
								children: ["Local models directory", /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
									value: modelsDir,
									onChange: (event) => setModelsDir(event.target.value),
									placeholder: "C:\\\\models",
									className: "ml-2 rounded border border-border bg-canvas px-2 py-1"
								})]
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
								className: "flex flex-wrap gap-3",
								children: [
									/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
										type: "checkbox",
										checked: allowLaunch,
										onChange: (event) => setAllowLaunch(event.target.checked)
									}), " temporary launch"] }),
									/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
										type: "checkbox",
										checked: allowRestart,
										onChange: (event) => setAllowRestart(event.target.checked)
									}), " restart for tuning"] }),
									/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
										type: "checkbox",
										checked: allowPromote,
										onChange: (event) => setAllowPromote(event.target.checked)
									}), " promote winner"] }),
									/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
										type: "checkbox",
										checked: allowCleanup,
										onChange: (event) => setAllowCleanup(event.target.checked)
									}), " cleanup run-owned trials"] }),
									network === "approved_sources" && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
										type: "checkbox",
										checked: allowDownload,
										onChange: (event) => setAllowDownload(event.target.checked)
									}), " download artifacts"] }), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
										type: "checkbox",
										checked: allowInstall,
										onChange: (event) => setAllowInstall(event.target.checked)
									}), " install backend"] })] })
								]
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
								type: "button",
								onClick: approveAndRun,
								disabled: busy || questions.length > 0 || !allowLaunch || network === "offline" && !modelsDir.trim() || network === "approved_sources" && !allowDownload,
								className: "h-9 px-4 rounded bg-primary text-primary-foreground disabled:opacity-50",
								children: busy ? "Approving…" : "Approve & start deployment"
							}),
							questions.length > 0 && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
								className: "text-attention",
								children: "Resolve the review questions before approval."
							}),
							Boolean(result.approval) && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", {
								className: "text-secondary",
								children: [
									"Approval recorded: ",
									String(result.approval.approval_id),
									". Run started: ",
									String(result.run?.operation_id ?? "pending")
								]
							}),
							qualityConfirmed && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
								className: "text-ink-secondary",
								children: "Quality suite confirmed: rift-text-core/v1, minimum score 0.90."
							})
						]
					})
				] })
			}),
			runId && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Panel, {
				title: "Autonomous run",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "flex items-center justify-between text-[12px]",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "font-medium",
							children: runStatus || "QUEUED"
						}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "text-ink-secondary",
							children: runBusy ? "Refreshing…" : "Live journal"
						})]
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("ol", {
						className: "mt-3 space-y-2 text-[12px]",
						children: runEvents.map((event) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("li", {
							className: "flex gap-2",
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "rift-mono text-ink-secondary",
								children: String(event.stage)
							}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: String(event.message) })]
						}, String(event.sequence)))
					}),
					runStatus && [
						"QUEUED",
						"RUNNING",
						"CANCEL_REQUESTED"
					].includes(runStatus) && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
						type: "button",
						onClick: cancelRun,
						className: "mt-3 h-8 rounded border border-border px-3 text-[12px]",
						children: "Cancel and recover"
					}),
					runState && Object.prototype.hasOwnProperty.call(runState, "result") && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("pre", {
						className: "mt-3 max-h-[280px] overflow-auto rounded bg-canvas p-3 text-[11px] text-ink",
						children: JSON.stringify(runState.result, null, 2)
					})
				]
			})
		]
	})] });
}
//#endregion
export { WorkloadsPage as component };
