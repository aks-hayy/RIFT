import { i as require_react, r as require_jsx_runtime, s as __toESM } from "./useRouter-C_cgokP9.js";
import { t as Link } from "./link-DZw2_uJJ.js";
import { D as useServices, M as SlidersHorizontal, N as Settings2, a as StatDot, j as useTuningRuns, n as PageHeader, o as AppShell, r as Panel, s as useActiveTuningRun, t as KV } from "./primitives-D--W_sxj.js";
import { r as rift, s as createLucideIcon, t as Unavailable } from "./unavailable-vAsxbBwJ.js";
import { t as LoaderCircle } from "./loader-circle-DFyVsy-h.js";
import { t as ShieldCheck } from "./shield-check-Ck-kEyQf.js";
import { t as Zap } from "./zap-BXq8-C3O.js";
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var ChevronDown = createLucideIcon("chevron-down", [["path", {
	d: "m6 9 6 6 6-6",
	key: "qrunsl"
}]]);
//#endregion
//#region src/lib/rift/tuning-contract.ts
var import_react = /* @__PURE__ */ __toESM(require_react());
function tuningProfileLabel(profile) {
	return String(profile).toLowerCase() === "cost" ? "Cost" : "Speed";
}
function tuningOutcomeTone(outcome) {
	const value = String(outcome).toLowerCase();
	if (value === "improved") return "success";
	if (value === "failed" || value === "unavailable") return "error";
	return "attention";
}
//#endregion
//#region src/routes/tuning.tsx?tsr-split=component
var import_jsx_runtime = require_jsx_runtime();
function TuningPage() {
	const services = useServices();
	const [selectedServiceName, setSelectedServiceName] = (0, import_react.useState)();
	const service = services.data?.find((item) => item.name === selectedServiceName) ?? services.data?.[0];
	const [profile, setProfile] = (0, import_react.useState)("speed");
	const [allowRestart, setAllowRestart] = (0, import_react.useState)(false);
	const [noApply, setNoApply] = (0, import_react.useState)(false);
	const [targetTokensPerSecond, setTargetTokensPerSecond] = (0, import_react.useState)(100);
	const [advancedOpen, setAdvancedOpen] = (0, import_react.useState)(false);
	const [candidateLimit, setCandidateLimit] = (0, import_react.useState)(24);
	const [budgetMinutes, setBudgetMinutes] = (0, import_react.useState)(60);
	const [warmupRuns, setWarmupRuns] = (0, import_react.useState)(1);
	const [repeats, setRepeats] = (0, import_react.useState)(3);
	const [startupTimeoutSeconds, setStartupTimeoutSeconds] = (0, import_react.useState)(180);
	const [prompt, setPrompt] = (0, import_react.useState)("Reply briefly: what is one benefit of local inference?");
	const [maxTokens, setMaxTokens] = (0, import_react.useState)(32);
	const [accuracyTolerance, setAccuracyTolerance] = (0, import_react.useState)(.05);
	const [accuracyCaseTolerance, setAccuracyCaseTolerance] = (0, import_react.useState)(.15);
	const [kvPrecisionSearch, setKvPrecisionSearch] = (0, import_react.useState)(true);
	const [retainAccuracyResponses, setRetainAccuracyResponses] = (0, import_react.useState)(false);
	const [ngramSpeculation, setNgramSpeculation] = (0, import_react.useState)("default");
	const [busy, setBusy] = (0, import_react.useState)(false);
	const [message, setMessage] = (0, import_react.useState)(null);
	const [error, setError] = (0, import_react.useState)(null);
	const [preview, setPreview] = (0, import_react.useState)(null);
	const [operationId, setOperationId] = (0, import_react.useState)(null);
	const runs = useTuningRuns({ service: service?.name });
	const activeRun = useActiveTuningRun(runs.data);
	(0, import_react.useEffect)(() => {
		const status = activeRun.data?.status?.toUpperCase();
		if (status && !["QUEUED", "RUNNING"].includes(status)) setOperationId(null);
	}, [activeRun.data?.status]);
	const validateSettings = () => {
		if (!Number.isFinite(targetTokensPerSecond) || targetTokensPerSecond <= 0) return "Target throughput must be greater than zero.";
		if (!Number.isInteger(candidateLimit) || candidateLimit < 1 || candidateLimit > 24) return "Candidate limit must be an integer from 1 to 24.";
		if (!Number.isFinite(budgetMinutes) || budgetMinutes <= 0) return "Experiment budget must be greater than zero minutes.";
		if (!Number.isInteger(warmupRuns) || warmupRuns < 0 || warmupRuns > 10) return "Warmup runs must be an integer from 0 to 10.";
		if (!Number.isInteger(repeats) || repeats < 1 || repeats > 20) return "Measurement repeats must be an integer from 1 to 20.";
		if (!Number.isFinite(startupTimeoutSeconds) || startupTimeoutSeconds < 30) return "Startup timeout must be at least 30 seconds.";
		if (!prompt.trim()) return "Benchmark prompt cannot be empty.";
		if (!Number.isInteger(maxTokens) || maxTokens < 1 || maxTokens > 128) return "Maximum tokens must be an integer from 1 to 128.";
		if (!Number.isFinite(accuracyTolerance) || accuracyTolerance < 0) return "Accuracy tolerance cannot be negative.";
		if (!Number.isFinite(accuracyCaseTolerance) || accuracyCaseTolerance < 0) return "Accuracy case tolerance cannot be negative.";
		return null;
	};
	const tuningOptions = () => ({
		allowRestart,
		noApply,
		candidateLimit,
		warmupRuns,
		repeats,
		budgetSeconds: Math.round(budgetMinutes * 60),
		startupTimeoutSeconds,
		prompt: prompt.trim(),
		maxTokens,
		targetTokensPerSecond,
		accuracyTolerance,
		accuracyCaseTolerance,
		retainAccuracyResponses,
		kvPrecisionSearch,
		ngramSpeculation: ngramSpeculation === "default" ? void 0 : ngramSpeculation === "on"
	});
	const start = async () => {
		if (!service) return;
		const validationError = validateSettings();
		if (validationError) {
			setError(validationError);
			setAdvancedOpen(true);
			return;
		}
		setBusy(true);
		setMessage(null);
		setError(null);
		setPreview(null);
		try {
			const result = await rift.startTuning(service.name, profile, tuningOptions());
			setOperationId(typeof result.operation_id === "string" ? result.operation_id : null);
			setMessage(typeof result.operation_id === "string" ? `Run accepted (${result.operation_id}). This page will refresh history while it executes.` : "Run accepted. This page will refresh history while it executes.");
			runs.refetch();
		} catch (err) {
			setError(err instanceof Error ? err.message : String(err));
		} finally {
			setBusy(false);
		}
	};
	const previewScope = async () => {
		if (!service) return;
		const validationError = validateSettings();
		if (validationError) {
			setError(validationError);
			setAdvancedOpen(true);
			return;
		}
		setBusy(true);
		setMessage(null);
		setError(null);
		try {
			const result = await rift.startTuning(service.name, profile, {
				...tuningOptions(),
				allowRestart: false,
				noApply: true,
				dryRun: true
			});
			setPreview({
				mode: String(result.mode ?? "profiled_preview"),
				candidates: Array.isArray(result.candidates) ? result.candidates.length : void 0,
				locks: result.precision_locks && typeof result.precision_locks === "object" ? result.precision_locks : void 0
			});
			setMessage("Preview ready. No service restart or benchmark was performed.");
		} catch (err) {
			setError(err instanceof Error ? err.message : String(err));
		} finally {
			setBusy(false);
		}
	};
	const cancel = async () => {
		const id = operationId ?? activeRun.data?.operationId;
		if (!id) return;
		setError(null);
		try {
			await rift.cancelTuning(id);
			setMessage(`Cancellation requested for ${id}. The baseline will be restored at the next safe checkpoint.`);
		} catch (err) {
			setError(err instanceof Error ? err.message : String(err));
		}
	};
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(AppShell, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(PageHeader, {
		eyebrow: "Optimization",
		title: "Tuning",
		description: "RIFT measures bounded llama.cpp candidates, explains the winner, and preserves your model and precision contract."
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "max-w-[1400px] mx-auto px-4 py-6 grid gap-4 lg:grid-cols-3",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "lg:col-span-2 grid gap-4",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
				title: "Start a profiled run",
				children: services.unavailable ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
					endpoint: "/services",
					resource: "Service[]"
				}) : !service ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
					className: "text-[13px] text-ink-secondary",
					children: "Deploy a service before tuning it."
				}) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "grid gap-5",
					children: [
						services.data && services.data.length > 1 && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
							className: "grid gap-1 text-[12px]",
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "rift-label",
								children: "Deployment"
							}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("select", {
								value: service.name,
								onChange: (event) => setSelectedServiceName(event.target.value),
								className: "h-9 rounded-[4px] border border-border bg-raised px-2 text-[13px]",
								children: services.data.map((item) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("option", {
									value: item.name,
									children: [
										item.name,
										" · ",
										item.backendKind
									]
								}, item.id))
							})]
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
							className: "grid gap-1 text-[12px] sm:max-w-xs",
							children: [
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
									className: "rift-label",
									children: "Target throughput"
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
									type: "number",
									min: "0.01",
									step: "0.01",
									value: targetTokensPerSecond,
									onChange: (event) => setTargetTokensPerSecond(Number(event.target.value)),
									className: "h-9 rounded-[4px] border border-border bg-raised px-2"
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
									className: "text-[11px] text-ink-secondary",
									children: "Used as a goal and report metric; it does not override the accuracy gate."
								})
							]
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "grid gap-3 sm:grid-cols-2",
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
								type: "button",
								onClick: () => setProfile("speed"),
								className: `text-left border rounded-[4px] p-4 ${profile === "speed" ? "border-primary bg-primary/5" : "border-border"}`,
								children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
									className: "flex items-center gap-2 text-[14px] font-medium",
									children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Zap, { className: "size-4 text-primary" }), " Speed"]
								}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
									className: "mt-2 text-[12px] text-ink-secondary",
									children: "Maximize generated tokens per second with a latency guard. Uses fixed prompts, warmups, and repeated measurements."
								})]
							}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
								type: "button",
								onClick: () => setProfile("cost"),
								className: `text-left border rounded-[4px] p-4 ${profile === "cost" ? "border-primary bg-primary/5" : "border-border"}`,
								children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
									className: "flex items-center gap-2 text-[14px] font-medium",
									children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(SlidersHorizontal, { className: "size-4 text-primary" }), " Cost"]
								}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
									className: "mt-2 text-[12px] text-ink-secondary",
									children: "Minimize GPU joules per request. Requires usable GPU power telemetry on every candidate."
								})]
							})]
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "rounded-[4px] border border-border bg-muted",
							children: [
								/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
									type: "button",
									className: "flex w-full items-center justify-between gap-3 px-3.5 py-3 text-left",
									"aria-expanded": advancedOpen,
									"aria-controls": "tuning-advanced-controls",
									onClick: () => setAdvancedOpen((open) => !open),
									children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
										className: "flex items-center gap-2 text-[13px] font-medium text-ink",
										children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Settings2, { className: "size-4 text-primary" }), "Advanced controls"]
									}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
										className: "flex items-center gap-2 text-[11px] text-ink-secondary",
										children: [advancedOpen ? "Hide" : "Show", /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ChevronDown, { className: `size-4 transition-transform ${advancedOpen ? "rotate-180" : ""}` })]
									})]
								}),
								!advancedOpen && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", {
									className: "border-t border-border px-3.5 py-2.5 text-[11px] text-ink-secondary",
									children: [
										candidateLimit,
										" candidates · ",
										budgetMinutes,
										" min · ",
										repeats,
										" measurements ·",
										" ",
										ngramSpeculation === "default" ? "backend speculation default" : `n-gram ${ngramSpeculation}`
									]
								}),
								advancedOpen && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
									id: "tuning-advanced-controls",
									className: "grid gap-4 border-t border-border p-3.5",
									children: [
										/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
											className: "grid gap-3 sm:grid-cols-2 lg:grid-cols-3",
											children: [
												/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
													className: "grid gap-1 text-[12px]",
													children: [
														/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
															className: "rift-label",
															children: "Candidate limit"
														}),
														/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
															type: "number",
															min: "1",
															max: "24",
															step: "1",
															value: candidateLimit,
															onChange: (event) => setCandidateLimit(Number(event.target.value)),
															className: "h-9 rounded-[4px] border border-border bg-raised px-2"
														}),
														/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
															className: "text-[11px] text-ink-secondary",
															children: "Maximum configurations to test."
														})
													]
												}),
												/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
													className: "grid gap-1 text-[12px]",
													children: [
														/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
															className: "rift-label",
															children: "Experiment budget (minutes)"
														}),
														/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
															type: "number",
															min: "1",
															step: "1",
															value: budgetMinutes,
															onChange: (event) => setBudgetMinutes(Number(event.target.value)),
															className: "h-9 rounded-[4px] border border-border bg-raised px-2"
														}),
														/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
															className: "text-[11px] text-ink-secondary",
															children: "Stops before the time budget is exceeded."
														})
													]
												}),
												/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
													className: "grid gap-1 text-[12px]",
													children: [
														/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
															className: "rift-label",
															children: "Startup timeout (seconds)"
														}),
														/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
															type: "number",
															min: "30",
															step: "1",
															value: startupTimeoutSeconds,
															onChange: (event) => setStartupTimeoutSeconds(Number(event.target.value)),
															className: "h-9 rounded-[4px] border border-border bg-raised px-2"
														}),
														/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
															className: "text-[11px] text-ink-secondary",
															children: "Readiness deadline for each restart."
														})
													]
												})
											]
										}),
										/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
											className: "grid gap-3 sm:grid-cols-2 lg:grid-cols-3",
											children: [
												/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
													className: "grid gap-1 text-[12px]",
													children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
														className: "rift-label",
														children: "Warmup runs"
													}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
														type: "number",
														min: "0",
														max: "10",
														step: "1",
														value: warmupRuns,
														onChange: (event) => setWarmupRuns(Number(event.target.value)),
														className: "h-9 rounded-[4px] border border-border bg-raised px-2"
													})]
												}),
												/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
													className: "grid gap-1 text-[12px]",
													children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
														className: "rift-label",
														children: "Measurement repeats"
													}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
														type: "number",
														min: "1",
														max: "20",
														step: "1",
														value: repeats,
														onChange: (event) => setRepeats(Number(event.target.value)),
														className: "h-9 rounded-[4px] border border-border bg-raised px-2"
													})]
												}),
												/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
													className: "grid gap-1 text-[12px]",
													children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
														className: "rift-label",
														children: "Maximum tokens"
													}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
														type: "number",
														min: "1",
														max: "128",
														step: "1",
														value: maxTokens,
														onChange: (event) => setMaxTokens(Number(event.target.value)),
														className: "h-9 rounded-[4px] border border-border bg-raised px-2"
													})]
												})
											]
										}),
										/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
											className: "grid gap-1 text-[12px]",
											children: [
												/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
													className: "rift-label",
													children: "Benchmark prompt"
												}),
												/* @__PURE__ */ (0, import_jsx_runtime.jsx)("textarea", {
													rows: 2,
													value: prompt,
													onChange: (event) => setPrompt(event.target.value),
													className: "rounded-[4px] border border-border bg-raised px-2 py-2 text-[12px]"
												}),
												/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
													className: "text-[11px] text-ink-secondary",
													children: "The same prompt is used for each candidate so comparisons remain reproducible."
												})
											]
										}),
										/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
											className: "grid gap-3 sm:grid-cols-2 lg:grid-cols-4",
											children: [
												/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
													className: "grid gap-1 text-[12px]",
													children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
														className: "rift-label",
														children: "Accuracy tolerance"
													}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
														type: "number",
														min: "0",
														step: "0.01",
														value: accuracyTolerance,
														onChange: (event) => setAccuracyTolerance(Number(event.target.value)),
														className: "h-9 rounded-[4px] border border-border bg-raised px-2"
													})]
												}),
												/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
													className: "grid gap-1 text-[12px]",
													children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
														className: "rift-label",
														children: "Accuracy case tolerance"
													}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
														type: "number",
														min: "0",
														step: "0.01",
														value: accuracyCaseTolerance,
														onChange: (event) => setAccuracyCaseTolerance(Number(event.target.value)),
														className: "h-9 rounded-[4px] border border-border bg-raised px-2"
													})]
												}),
												/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
													className: "flex items-center gap-2 text-[12px] text-ink-secondary",
													children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
														type: "checkbox",
														checked: kvPrecisionSearch,
														onChange: (event) => setKvPrecisionSearch(event.target.checked)
													}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
														/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
															className: "text-ink font-medium",
															children: "K/V precision search"
														}),
														/* @__PURE__ */ (0, import_jsx_runtime.jsx)("br", {}),
														"Allow safe K/V cache candidates."
													] })]
												}),
												/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
													className: "flex items-center gap-2 text-[12px] text-ink-secondary",
													children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
														type: "checkbox",
														checked: retainAccuracyResponses,
														onChange: (event) => setRetainAccuracyResponses(event.target.checked)
													}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
														/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
															className: "text-ink font-medium",
															children: "Retain accuracy responses"
														}),
														/* @__PURE__ */ (0, import_jsx_runtime.jsx)("br", {}),
														"Include response evidence in the report."
													] })]
												})
											]
										}),
										/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
											className: "grid gap-1 text-[12px] sm:max-w-sm",
											children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
												className: "grid gap-1",
												children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
													className: "rift-label",
													children: "N-gram speculation"
												}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("select", {
													value: ngramSpeculation,
													onChange: (event) => setNgramSpeculation(event.target.value),
													className: "h-9 rounded-[4px] border border-border bg-raised px-2",
													children: [
														/* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
															value: "default",
															children: "Backend default"
														}),
														/* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
															value: "off",
															children: "Explicitly off"
														}),
														/* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
															value: "on",
															children: "Explicitly on"
														})
													]
												})]
											}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
												className: "text-[11px] text-ink-secondary",
												children: "Keep it off for creative tasks; enable it only when predictable text makes speculation worthwhile."
											})]
										}),
										/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
											className: "flex flex-wrap items-center gap-3",
											children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
												type: "button",
												disabled: busy,
												onClick: () => void previewScope(),
												className: "inline-flex h-8 items-center gap-2 rounded-[4px] border border-border bg-raised px-3 text-[12px] font-medium text-ink disabled:opacity-50",
												children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Settings2, { className: "size-3.5" }), " Preview scope"]
											}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
												className: "text-[11px] text-ink-secondary",
												children: "Preview validates locks and candidate scope without restarting the service."
											})]
										}),
										preview && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
											className: "rounded-[4px] border border-border bg-raised p-3 text-[11px]",
											role: "status",
											children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
												className: "rift-label mb-1",
												children: "Preview ready"
											}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
												className: "grid gap-1 text-ink-secondary sm:grid-cols-2",
												children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: ["Mode: ", /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
													className: "rift-mono text-ink",
													children: preview.mode
												})] }), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
													"Candidates:",
													" ",
													/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
														className: "rift-mono text-ink",
														children: preview.candidates ?? "—"
													})
												] })]
											})]
										})
									]
								})
							]
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "grid gap-3 sm:grid-cols-2",
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
								className: "flex items-start gap-2 text-[12px] text-ink-secondary",
								children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
									type: "checkbox",
									checked: allowRestart,
									onChange: (event) => setAllowRestart(event.target.checked),
									className: "mt-0.5"
								}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
										className: "text-ink font-medium",
										children: "Allow maintenance restarts"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("br", {}),
									"Candidate settings are tested one at a time; monitoring recovery is paused for this run."
								] })]
							}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
								className: "flex items-start gap-2 text-[12px] text-ink-secondary",
								children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
									type: "checkbox",
									checked: noApply,
									onChange: (event) => setNoApply(event.target.checked),
									className: "mt-0.5"
								}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
										className: "text-ink font-medium",
										children: "Report only"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("br", {}),
									"Measure and explain the winner, then restore the baseline instead of applying it."
								] })]
							})]
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "flex flex-wrap items-center gap-3",
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
								type: "button",
								disabled: busy || !allowRestart,
								onClick: () => void start(),
								className: "inline-flex items-center gap-2 h-9 px-3.5 rounded-[4px] bg-primary text-primary-foreground text-[13px] font-medium disabled:opacity-50",
								children: [
									busy ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(LoaderCircle, { className: "size-4 animate-spin" }) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ShieldCheck, { className: "size-4" }),
									" ",
									"Start ",
									tuningProfileLabel(profile),
									" tuning"
								]
							}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Link, {
								to: service ? "/deployments/$id" : "/deployments",
								params: service ? { id: service.id } : void 0,
								className: "text-[12px] text-primary hover:underline",
								children: "View deployment state"
							})]
						}),
						message && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
							className: "rift-mono text-[11px] text-secondary",
							role: "status",
							children: message
						}),
						error && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
							className: "rift-mono text-[11px] text-error",
							role: "alert",
							children: error
						}),
						(activeRun.data || operationId) && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "rounded-[4px] border border-border bg-muted p-3",
							role: "status",
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
								className: "flex flex-wrap items-center gap-2 text-[12px]",
								children: [
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
										className: "font-medium text-ink",
										children: "Live tuning run"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
										className: "rift-mono text-[11px] text-ink-secondary",
										children: activeRun.data?.runId ?? operationId
									}),
									activeRun.data && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
										className: "rift-mono text-[11px] text-ink-secondary",
										children: activeRun.data.status
									}),
									(operationId || activeRun.data?.operationId) && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
										type: "button",
										onClick: () => void cancel(),
										className: "ml-auto text-[11px] text-error hover:underline",
										children: "Cancel safely"
									})
								]
							}), activeRun.data?.events?.length ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
								className: "mt-2 grid gap-1",
								children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
									className: "flex items-center justify-between rift-mono text-[11px] text-ink-secondary",
									children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: activeRun.data.events[activeRun.data.events.length - 1].message }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: activeRun.data.events[activeRun.data.events.length - 1].percent == null ? "" : `${activeRun.data.events[activeRun.data.events.length - 1].percent}%` })]
								}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
									className: "h-1.5 overflow-hidden rounded-full bg-raised",
									children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
										className: "h-full bg-primary transition-all",
										style: { width: `${Math.max(0, Math.min(100, activeRun.data.events[activeRun.data.events.length - 1].percent ?? 0))}%` }
									})
								})]
							}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
								className: "mt-2 rift-mono text-[11px] text-ink-secondary",
								children: "Waiting for the controller to create the durable run journal…"
							})]
						})
					]
				})
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(RunHistory, {
				runs: runs.data ?? [],
				loading: runs.isLoading
			})]
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ContractPanel, { run: runs.data?.[0] })]
	})] });
}
function RunHistory({ runs, loading }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
		title: "Run history",
		aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
			className: "rift-mono text-[11px] text-ink-secondary",
			children: "persistent"
		}),
		children: loading && !runs.length ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
			className: "text-[13px] text-ink-secondary",
			children: "Loading tuning history…"
		}) : !runs.length ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
			className: "text-[13px] text-ink-secondary",
			children: "No profiled runs yet."
		}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "divide-y divide-border",
			children: runs.map((run) => {
				const tone = tuningOutcomeTone(run.outcome ?? run.status);
				return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "py-3 first:pt-0 last:pb-0 flex flex-wrap items-center gap-3",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StatDot, { tone: tone === "success" ? "ok" : tone === "error" ? "error" : "attention" }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "min-w-0 flex-1",
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
								className: "text-[13px] text-ink font-medium",
								children: [
									tuningProfileLabel(run.profile),
									" · ",
									run.service
								]
							}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
								className: "rift-mono text-[10px] text-ink-secondary",
								children: [
									run.runId,
									" · ",
									run.outcome ?? run.status
								]
							})]
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
							className: "rift-mono text-[11px] text-ink-secondary",
							children: run.applied ? "applied" : "baseline kept"
						})
					]
				}, run.runId);
			})
		})
	});
}
function ContractPanel({ run }) {
	const locks = run?.precisionLocks ?? {};
	const winnerConfig = run?.winner?.config ?? run?.winner ?? {};
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Panel, {
		title: "Precision contract",
		children: [
			run && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "mb-5 border-b border-border pb-4",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "rift-label mb-2",
						children: "Latest result"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "grid grid-cols-2 gap-4",
						children: [
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
								label: "Profile",
								value: tuningProfileLabel(run.profile)
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
								label: "Outcome",
								value: run.outcome ?? run.status
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
								label: "Deployment",
								value: run.applied ? "winner applied" : "baseline kept"
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
								label: "Candidates",
								value: run.candidates?.length ?? "—"
							})
						]
					}),
					run.decision && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "mt-3 text-[12px] text-ink-secondary",
						children: run.decision
					}),
					run.winner && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "mt-3",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
							className: "rift-label mb-1",
							children: "Winning configuration"
						}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("code", {
							className: "block max-h-32 overflow-auto whitespace-pre-wrap break-all rounded-[3px] bg-muted p-2 rift-mono text-[10px] text-ink",
							children: JSON.stringify(run.winner.config ?? run.winner, null, 2)
						})]
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "mt-4 rounded-[4px] border border-border bg-muted p-3",
						"aria-label": "tuning result",
						children: [
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
								className: "rift-label mb-2",
								children: "Target / Accuracy / KV"
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
								className: "grid grid-cols-2 gap-3 text-[12px]",
								children: [
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
										label: "Target",
										value: run.target ? `${run.target.value ?? "—"} tok/s · ${run.target.reached ? "reached" : "not reached"}` : "—"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
										label: "Accuracy",
										value: run.accuracy ? `${run.accuracy.passed ? "PASS" : "FAIL"} · ${run.accuracy.aggregateScore ?? "—"}` : "—"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
										label: "K/V search",
										value: run.kvPrecisionSearch == null ? "—" : run.kvPrecisionSearch ? "enabled" : "disabled"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
										label: "Selected K cache",
										value: String(winnerConfig.cache_type_k ?? "—")
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
										label: "Selected V cache",
										value: String(winnerConfig.cache_type_v ?? "—")
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
										label: "Apply / rollback",
										value: run.applyState?.state ?? (run.applied ? "applied" : "baseline kept")
									})
								]
							}),
							!!run.rejected?.length && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
								className: "mt-3 text-[11px] text-ink-secondary",
								children: [
									"Rejected candidates:",
									" ",
									run.rejected.map((item) => item.rejectionReason ?? item.reason ?? "unspecified").join("; ")
								]
							})
						]
					})
				]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
				className: "text-[12px] text-ink-secondary",
				children: "Tuning never changes the model artifact, weight quantization, context, or concurrency. K/V cache precision is searched only when the explicit K/V precision search control is enabled; candidates remain accuracy-screened and any quality trade-off is reported."
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "mt-4 grid grid-cols-2 gap-4",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
						label: "Model",
						value: String(locks.model_path ?? "locked at run start")
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
						label: "Quantization",
						value: String(locks.weight_quantization ?? "locked")
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
						label: "K cache",
						value: String(locks.cache_type_k ?? "locked")
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
						label: "V cache",
						value: String(locks.cache_type_v ?? "locked")
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
						label: "Context",
						value: String(locks.context_length ?? "locked")
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
						label: "Concurrency",
						value: String(locks.concurrency ?? "locked")
					})
				]
			}),
			run?.opportunities?.length ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "mt-5 border-t border-border pt-4",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "rift-label mb-2",
					children: "Further improvement · recommendation only"
				}), run.opportunities.map((opportunity) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "mb-3 last:mb-0",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "text-[12px] text-ink font-medium",
						children: opportunity.title
					}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "text-[11px] text-ink-secondary mt-0.5",
						children: opportunity.warning
					})]
				}, opportunity.id))]
			}) : null
		]
	});
}
//#endregion
export { TuningPage as component };
