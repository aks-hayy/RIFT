import { c as __toESM, i as require_react, r as require_jsx_runtime } from "./useRouter-C3Fl0Qct.js";
import { n as PageHeader, o as AppShell, r as Panel } from "./primitives-DeAXA1eZ.js";
import { L as rift } from "./hooks-BdOll_GY.js";
//#region src/lib/rift/workload-approval.ts
var import_react = /* @__PURE__ */ __toESM(require_react());
function hasValidAcquisitionApproval(input) {
	if (input.network === "offline") return true;
	return (input.allowDownload || input.allowInstall) && input.perArtifactGiB.trim().length > 0 && input.totalDownloadGiB.trim().length > 0;
}
function positiveInteger(value, label) {
	const parsed = Number(value);
	if (!Number.isSafeInteger(parsed) || parsed < 1) throw new Error(`${label} must be a positive whole number.`);
	return parsed;
}
function bytes(value, label) {
	const parsed = Number(value);
	if (!Number.isFinite(parsed) || parsed < 0) throw new Error(`${label} must be zero or more GiB.`);
	return Math.floor(parsed * 1024 ** 3);
}
function buildWorkloadEnvelope(input) {
	const explorationSeconds = positiveInteger(input.explorationSeconds, "Exploration time");
	const maxArtifacts = positiveInteger(input.maxArtifacts, "Maximum artifact count");
	const tuningCandidates = positiveInteger(input.tuningCandidates, "Tuning candidate limit");
	const perArtifactBytes = bytes(input.perArtifactGiB, "Per-artifact download budget");
	const totalDownloadBytes = bytes(input.totalDownloadGiB, "Total download budget");
	if (input.network === "offline" && (perArtifactBytes !== 0 || totalDownloadBytes !== 0)) throw new Error("Offline mode requires both download budgets to be zero GiB.");
	if (perArtifactBytes > totalDownloadBytes) throw new Error("Per-artifact download budget cannot exceed the total download budget.");
	if (input.network === "approved_sources" && !input.actions.download && totalDownloadBytes > 0) throw new Error("A non-zero download budget requires explicit download permission.");
	return {
		schema_version: 1,
		actions: {
			...input.actions,
			download: input.network === "approved_sources" && input.actions.download === true,
			install: input.network === "approved_sources" && input.actions.install === true,
			remote_execution: false
		},
		targets: ["local"],
		sources: input.network === "approved_sources" ? ["huggingface"] : [],
		licenses: input.network === "approved_sources" && input.licensePolicy === "apache-2.0" ? ["Apache-2.0"] : [],
		network: input.network,
		limits: {
			exploration_seconds: explorationSeconds,
			max_artifacts: maxArtifacts,
			tuning_candidates: tuningCandidates,
			per_artifact_bytes: perArtifactBytes,
			total_download_bytes: totalDownloadBytes
		},
		allow_quantization_alternatives: false,
		exposure: "loopback",
		operations_mode: "recover"
	};
}
//#endregion
//#region src/lib/rift/workload-result.ts
function object(value) {
	return value !== null && typeof value === "object" && !Array.isArray(value) ? value : null;
}
function number(value) {
	return typeof value === "number" && Number.isFinite(value) ? value : null;
}
function string(value) {
	return typeof value === "string" && value.trim() ? value : null;
}
function summarizeWorkloadRun(result, status) {
	const root = object(result);
	const deployment = object(root?.deployment);
	const services = object(object(deployment?.plan)?.services);
	const serviceEntry = services ? Object.entries(services)[0] : void 0;
	const serviceName = serviceEntry?.[0] ?? null;
	const service = object(serviceEntry?.[1]);
	const model = object(service?.model);
	const benchmarkSummary = object(object(root?.benchmark)?.summary);
	const evaluationSummary = object(object(root?.evaluation)?.summary);
	const acceptance = object(root?.acceptance);
	const serving = object(service?.serving);
	return {
		status,
		serviceName,
		backend: string(service?.backend),
		model: string(model?.selected_file) ?? string(model?.id) ?? string(object(model?.artifact)?.artifact_id),
		modelSource: string(model?.source),
		contextTokens: number(serving?.context_length),
		concurrency: number(serving?.concurrency),
		decodeTokensPerSecond: number(benchmarkSummary?.median_tokens_per_second),
		benchmarkSamples: number(benchmarkSummary?.sample_count),
		benchmarkCases: number(benchmarkSummary?.case_count),
		evaluationPassed: acceptance?.evaluation_passed === true,
		evaluationPasses: number(evaluationSummary?.pass),
		evaluationFailures: (number(evaluationSummary?.fail) ?? 0) + (number(evaluationSummary?.error) ?? 0),
		endpoint: string(object(service?.health)?.url),
		applied: deployment?.applied === true
	};
}
//#endregion
//#region src/routes/workloads.tsx?tsr-split=component
var import_jsx_runtime = require_jsx_runtime();
function WorkloadsPage() {
	const [input, setInput] = (0, import_react.useState)("");
	const [inputMode, setInputMode] = (0, import_react.useState)("natural");
	const [outputSchema, setOutputSchema] = (0, import_react.useState)(null);
	const [outputSchemaName, setOutputSchemaName] = (0, import_react.useState)("");
	const [outputSchemaError, setOutputSchemaError] = (0, import_react.useState)(null);
	const [result, setResult] = (0, import_react.useState)(null);
	const [busy, setBusy] = (0, import_react.useState)(false);
	const [error, setError] = (0, import_react.useState)(null);
	const [network, setNetwork] = (0, import_react.useState)("offline");
	const [licensePolicy, setLicensePolicy] = (0, import_react.useState)("apache-2.0");
	const [allowLaunch, setAllowLaunch] = (0, import_react.useState)(false);
	const [allowRestart, setAllowRestart] = (0, import_react.useState)(false);
	const [allowPromote, setAllowPromote] = (0, import_react.useState)(false);
	const [allowCleanup, setAllowCleanup] = (0, import_react.useState)(false);
	const [allowDownload, setAllowDownload] = (0, import_react.useState)(false);
	const [allowInstall, setAllowInstall] = (0, import_react.useState)(false);
	const [modelsDir, setModelsDir] = (0, import_react.useState)("");
	const [explorationHours, setExplorationHours] = (0, import_react.useState)("");
	const [maxArtifacts, setMaxArtifacts] = (0, import_react.useState)("");
	const [tuningCandidates, setTuningCandidates] = (0, import_react.useState)("");
	const [perArtifactGiB, setPerArtifactGiB] = (0, import_react.useState)("");
	const [totalDownloadGiB, setTotalDownloadGiB] = (0, import_react.useState)("");
	const [qualityConfirmed, setQualityConfirmed] = (0, import_react.useState)(false);
	const [runId, setRunId] = (0, import_react.useState)(null);
	const [runOperationId, setRunOperationId] = (0, import_react.useState)(null);
	const [runState, setRunState] = (0, import_react.useState)(null);
	const [runBusy, setRunBusy] = (0, import_react.useState)(false);
	const [workloadRuns, setWorkloadRuns] = (0, import_react.useState)([]);
	const [runsLoading, setRunsLoading] = (0, import_react.useState)(true);
	const [runsError, setRunsError] = (0, import_react.useState)(null);
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
			setResult(await rift.compileWorkload(parseInput(), true, void 0, outputSchema ?? void 0));
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
			}, true, void 0, outputSchema ?? void 0);
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
			const envelope = buildWorkloadEnvelope({
				network,
				licensePolicy,
				actions: {
					cleanup: allowCleanup,
					download: allowDownload,
					install: allowInstall,
					promote: allowPromote,
					restart: allowRestart,
					temporary_launch: allowLaunch
				},
				explorationSeconds: String(Number(explorationHours) * 3600),
				maxArtifacts,
				tuningCandidates,
				perArtifactGiB: network === "offline" ? "0" : perArtifactGiB,
				totalDownloadGiB: network === "offline" ? "0" : totalDownloadGiB
			});
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
	async function loadWorkloadRuns() {
		setRunsLoading(true);
		try {
			setRunsError(null);
			setWorkloadRuns(await rift.listWorkloadRuns());
		} catch (cause) {
			setRunsError(cause instanceof Error ? cause.message : String(cause));
		} finally {
			setRunsLoading(false);
		}
	}
	async function openSavedRun(id) {
		setRunBusy(true);
		setError(null);
		try {
			const savedRun = await rift.getWorkloadRun(id);
			setRunId(id);
			setRunState(savedRun);
			setRunOperationId(typeof savedRun.result === "object" && savedRun.result !== null ? String(savedRun.result.operation_id ?? "") || null : null);
		} catch (cause) {
			setError(cause instanceof Error ? cause.message : String(cause));
		} finally {
			setRunBusy(false);
		}
	}
	(0, import_react.useEffect)(() => {
		loadWorkloadRuns();
	}, []);
	const runStatus = String(runState?.status ?? "").toUpperCase();
	(0, import_react.useEffect)(() => {
		if (!runId || [
			"VERIFIED",
			"INFEASIBLE",
			"EXHAUSTED",
			"BLOCKED",
			"FAILED",
			"CANCELLED"
		].includes(runStatus)) return;
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
	}, [runId, runStatus]);
	const contract = result?.contract ?? {};
	const questions = Array.isArray(result?.questions) ? result.questions : [];
	const unsupported = Array.isArray(result?.unsupported_requirements) ? result.unsupported_requirements : [];
	const qualityQuestion = questions.some((question) => String(question).toLowerCase().includes("quality suite"));
	const runEvents = Array.isArray(runState?.events) ? runState.events : [];
	const outcome = runState ? summarizeWorkloadRun(runState.result, runStatus || "UNKNOWN") : null;
	(0, import_react.useEffect)(() => {
		if ([
			"VERIFIED",
			"INFEASIBLE",
			"EXHAUSTED",
			"BLOCKED",
			"FAILED",
			"CANCELLED"
		].includes(runStatus)) loadWorkloadRuns();
	}, [runStatus]);
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(AppShell, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(PageHeader, {
		eyebrow: "Workload deploy",
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
						placeholder: inputMode === "json" ? "Paste a workload JSON contract" : "Describe the service you need, its performance, quality, context, and policy requirements…",
						rows: 10,
						className: "w-full rounded border border-border bg-canvas p-3 text-[13px] leading-6 text-ink",
						"aria-label": inputMode === "json" ? "Structured JSON workload" : "Natural-language workload"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "mt-3 rounded border border-border bg-muted/30 p-3 text-[12px]",
						children: [
							/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
								className: "block font-medium",
								children: [
									"Output JSON Schema",
									" ",
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
										className: "font-normal text-ink-secondary",
										children: "(required when strict JSON is requested)"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
										type: "file",
										accept: "application/schema+json,application/json,.json",
										className: "mt-2 block w-full text-[12px]",
										onChange: async (event) => {
											const file = event.target.files?.[0];
											setOutputSchemaError(null);
											setOutputSchema(null);
											setOutputSchemaName("");
											if (!file) return;
											try {
												const parsed = JSON.parse(await file.text());
												if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Schema root must be a JSON object");
												setOutputSchema(parsed);
												setOutputSchemaName(file.name);
											} catch (cause) {
												setOutputSchemaError(cause instanceof Error ? cause.message : "Schema file could not be read");
											}
										}
									})
								]
							}),
							outputSchemaName && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", {
								className: "mt-1 text-secondary",
								children: [
									"Attached: ",
									outputSchemaName,
									". RIFT will validate and hash this schema during compilation."
								]
							}),
							outputSchemaError && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
								className: "mt-1 text-attention",
								children: outputSchemaError
							})
						]
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
						type: "button",
						onClick: compile,
						disabled: busy || !input.trim() || Boolean(outputSchemaError),
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
					Boolean(contract.output_schema) && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", {
						className: "mt-2 text-[12px] text-secondary",
						children: [
							"Output schema attached and content-hashed:",
							" ",
							String(contract.output_schema.sha256 ?? "unavailable")
						]
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
							network === "approved_sources" && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
								className: "block",
								children: ["License filter", /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("select", {
									value: licensePolicy,
									onChange: (event) => setLicensePolicy(event.target.value),
									className: "ml-2 rounded border border-border bg-canvas px-2 py-1",
									children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
										value: "apache-2.0",
										children: "Apache-2.0 only"
									}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
										value: "no-filter",
										children: "No filter; review each model"
									})]
								})]
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("fieldset", {
								className: "grid gap-2 rounded-lg border border-border/70 bg-white/35 p-3 sm:grid-cols-2",
								children: [
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("legend", {
										className: "px-1 text-[11px] font-medium",
										children: "Approved search limits (required)"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
										className: "grid gap-1",
										children: ["Exploration time (hours)", /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
											required: true,
											type: "number",
											min: "0.1",
											step: "0.1",
											value: explorationHours,
											onChange: (event) => setExplorationHours(event.target.value),
											className: "rounded border border-border bg-white/70 px-2 py-1.5"
										})]
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
										className: "grid gap-1",
										children: ["Maximum model artifacts", /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
											required: true,
											type: "number",
											min: "1",
											step: "1",
											value: maxArtifacts,
											onChange: (event) => setMaxArtifacts(event.target.value),
											className: "rounded border border-border bg-white/70 px-2 py-1.5"
										})]
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
										className: "grid gap-1",
										children: ["Tuning configurations per candidate", /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
											required: true,
											type: "number",
											min: "1",
											step: "1",
											value: tuningCandidates,
											onChange: (event) => setTuningCandidates(event.target.value),
											className: "rounded border border-border bg-white/70 px-2 py-1.5"
										})]
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
										className: "grid gap-1",
										children: ["Per-artifact download (GiB)", /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
											required: true,
											type: "number",
											min: "0",
											step: "0.1",
											value: network === "offline" ? "0" : perArtifactGiB,
											disabled: network === "offline",
											onChange: (event) => setPerArtifactGiB(event.target.value),
											className: "rounded border border-border bg-white/70 px-2 py-1.5 disabled:opacity-60"
										})]
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
										className: "grid gap-1",
										children: ["Total download (GiB)", /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
											required: true,
											type: "number",
											min: "0",
											step: "0.1",
											value: network === "offline" ? "0" : totalDownloadGiB,
											disabled: network === "offline",
											onChange: (event) => setTotalDownloadGiB(event.target.value),
											className: "rounded border border-border bg-white/70 px-2 py-1.5 disabled:opacity-60"
										})]
									})
								]
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
								className: "block",
								children: [
									"Local models directory (searched first)",
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
										value: modelsDir,
										onChange: (event) => setModelsDir(event.target.value),
										placeholder: "C:\\\\models",
										className: "ml-2 rounded border border-border bg-canvas px-2 py-1"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
										className: "ml-2 text-[11px] text-ink-secondary",
										children: "Optional with approved sources; RIFT prefers a compatible local artifact before considering downloads."
									})
								]
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
								className: "flex flex-wrap gap-3",
								children: [
									/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", { children: [
										/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
											type: "checkbox",
											checked: allowLaunch,
											onChange: (event) => setAllowLaunch(event.target.checked)
										}),
										" ",
										"temporary launch"
									] }),
									/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", { children: [
										/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
											type: "checkbox",
											checked: allowRestart,
											onChange: (event) => setAllowRestart(event.target.checked)
										}),
										" ",
										"restart for tuning"
									] }),
									/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", { children: [
										/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
											type: "checkbox",
											checked: allowPromote,
											onChange: (event) => setAllowPromote(event.target.checked)
										}),
										" ",
										"promote winner"
									] }),
									/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", { children: [
										/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
											type: "checkbox",
											checked: allowCleanup,
											onChange: (event) => setAllowCleanup(event.target.checked)
										}),
										" ",
										"cleanup run-owned trials"
									] }),
									network === "approved_sources" && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", { children: [
										/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
											type: "checkbox",
											checked: allowDownload,
											onChange: (event) => setAllowDownload(event.target.checked)
										}),
										" ",
										"download artifacts"
									] }), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", { children: [
										/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
											type: "checkbox",
											checked: allowInstall,
											onChange: (event) => setAllowInstall(event.target.checked)
										}),
										" ",
										"install backend"
									] })] })
								]
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
								type: "button",
								onClick: approveAndRun,
								disabled: busy || questions.length > 0 || !allowLaunch || !explorationHours || !maxArtifacts || !tuningCandidates || network === "offline" && !modelsDir.trim() || !hasValidAcquisitionApproval({
									network,
									allowDownload,
									allowInstall,
									perArtifactGiB,
									totalDownloadGiB
								}),
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
									"Approval recorded:",
									" ",
									String(result.approval.approval_id),
									". Run started:",
									" ",
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
					runState && Object.prototype.hasOwnProperty.call(runState, "result") && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "mt-4 space-y-3",
						children: [outcome?.status === "VERIFIED" ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "rounded-xl border border-success/30 bg-success/5 p-4",
							children: [
								/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
									className: "flex flex-wrap items-start justify-between gap-3",
									children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
										/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
											className: "text-[11px] uppercase tracking-[0.14em] text-ink-secondary",
											children: "Workload verified"
										}),
										/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("h3", {
											className: "mt-1 text-lg font-semibold",
											children: [outcome.serviceName ?? "Service", " passed acceptance"]
										}),
										/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", {
											className: "mt-1 break-all text-[12px] text-ink-secondary",
											children: [outcome.model?.replace(/^.*[\\/]/, "") ?? "Model identity unavailable", outcome.modelSource === "local" ? " · local artifact" : ""]
										})
									] }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
										className: "rounded-full border border-success/40 px-3 py-1 text-[11px] font-medium text-success",
										children: outcome.backend ?? "Backend verified"
									})]
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
									className: "mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4",
									children: [
										/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
											className: "rounded-lg bg-surface/70 p-3",
											children: [
												/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
													className: "text-[11px] text-ink-secondary",
													children: "Median decode"
												}),
												/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
													className: "mt-1 text-base font-semibold",
													children: outcome.decodeTokensPerSecond === null ? "Not measured" : `${outcome.decodeTokensPerSecond.toFixed(1)} tok/s`
												}),
												/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", {
													className: "text-[10px] text-ink-secondary",
													children: [
														outcome.benchmarkSamples ?? 0,
														" samples · ",
														outcome.benchmarkCases ?? 0,
														" cases"
													]
												})
											]
										}),
										/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
											className: "rounded-lg bg-surface/70 p-3",
											children: [
												/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
													className: "text-[11px] text-ink-secondary",
													children: "Context / concurrency"
												}),
												/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", {
													className: "mt-1 text-base font-semibold",
													children: [
														outcome.contextTokens?.toLocaleString() ?? "—",
														" / ",
														outcome.concurrency ?? "—"
													]
												}),
												/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
													className: "text-[10px] text-ink-secondary",
													children: "tokens / requests"
												})
											]
										}),
										/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
											className: "rounded-lg bg-surface/70 p-3",
											children: [
												/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
													className: "text-[11px] text-ink-secondary",
													children: "Required checks"
												}),
												/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
													className: "mt-1 text-base font-semibold",
													children: outcome.evaluationPassed ? "Passed" : "Not passed"
												}),
												/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", {
													className: "text-[10px] text-ink-secondary",
													children: [
														outcome.evaluationPasses ?? 0,
														" passed · ",
														outcome.evaluationFailures ?? 0,
														" failed"
													]
												})
											]
										}),
										/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
											className: "rounded-lg bg-surface/70 p-3",
											children: [
												/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
													className: "text-[11px] text-ink-secondary",
													children: "Artifact transfer"
												}),
												/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
													className: "mt-1 text-base font-semibold",
													children: outcome.modelSource === "local" ? "No model download" : "See evidence"
												}),
												/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
													className: "text-[10px] text-ink-secondary",
													children: "existing local weights reused"
												})
											]
										})
									]
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
									className: "mt-3 text-[11px] text-ink-secondary",
									children: "Acceptance is limited to the approved suite and recorded measurements; it is not a general accuracy guarantee."
								}),
								outcome.serviceName && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("a", {
									className: "mt-3 inline-flex h-8 items-center rounded border border-border px-3 text-[12px] font-medium hover:bg-canvas",
									href: `/deployments/${encodeURIComponent(outcome.serviceName)}`,
									children: "Open service"
								})
							]
						}) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "rounded-lg border border-border bg-canvas p-3 text-[12px]",
							children: [
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("strong", { children: "Run result" }),
								outcome?.backend && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [" · ", outcome.backend] }),
								outcome?.model && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
									className: "mt-1 break-all",
									children: outcome.model
								})
							]
						}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("details", {
							className: "rounded-lg border border-border bg-canvas p-3",
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("summary", {
								className: "cursor-pointer text-[12px] font-medium",
								children: "Raw evidence JSON"
							}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("pre", {
								className: "mt-3 max-h-[360px] overflow-auto whitespace-pre-wrap break-words text-[10px] text-ink-secondary",
								children: JSON.stringify(runState.result, null, 2)
							})]
						})]
					})
				]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Panel, {
				title: "Recent workload runs",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "flex items-center justify-between gap-3",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "text-[12px] text-ink-secondary",
						children: "Reopen a persisted run to inspect its status, measurements, and evidence."
					}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
						type: "button",
						onClick: () => void loadWorkloadRuns(),
						className: "h-8 shrink-0 rounded border border-border px-3 text-[12px]",
						children: "Refresh"
					})]
				}), runsLoading ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
					className: "mt-3 text-[12px] text-ink-secondary",
					children: "Loading saved workload runs…"
				}) : runsError ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", {
					className: "mt-3 text-[12px] text-attention",
					children: ["Could not load runs: ", runsError]
				}) : workloadRuns.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
					className: "mt-3 text-[12px] text-ink-secondary",
					children: "No persisted workload runs yet."
				}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
					className: "mt-3 divide-y divide-border",
					children: workloadRuns.map((savedRun) => {
						const id = String(savedRun.run_id ?? "");
						const status = String(savedRun.status ?? "UNKNOWN").toUpperCase();
						return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("li", { children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
							type: "button",
							onClick: () => void openSavedRun(id),
							className: "flex w-full items-center justify-between gap-3 py-3 text-left hover:bg-canvas",
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
								className: "min-w-0",
								children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
									className: "block font-medium",
									children: id || "Unknown run"
								}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
									className: "block text-[11px] text-ink-secondary",
									children: ["Approval ", String(savedRun.approval_id ?? "—")]
								})]
							}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "rift-mono shrink-0 text-[11px]",
								children: status
							})]
						}) }, id);
					})
				})]
			})
		]
	})] });
}
//#endregion
export { WorkloadsPage as component };
