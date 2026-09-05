import { i as require_react, r as require_jsx_runtime, s as __toESM } from "./useRouter-C_cgokP9.js";
import { t as Link } from "./link-DZw2_uJJ.js";
import { t as useNavigate } from "./useNavigate-VOCCG6_j.js";
import { C as useResourceReports, E as useServiceTelemetryAccounting, M as SlidersHorizontal, S as useReports, T as useService, a as StatDot, d as useEvaluations, h as useLogs, i as SourceBadge, k as useTelemetryLatest, l as useBenchmarks, n as PageHeader, o as AppShell, r as Panel, t as KV, w as useRevisions } from "./primitives-D--W_sxj.js";
import { i as cn, r as rift, s as createLucideIcon, t as Unavailable } from "./unavailable-vAsxbBwJ.js";
import { n as Copy, t as Gauge } from "./gauge-DZZuhHUS.js";
import { t as LoaderCircle } from "./loader-circle-DFyVsy-h.js";
import { t as RotateCcw } from "./rotate-ccw-S4Bt286B.js";
import { t as ShieldCheck } from "./shield-check-Ck-kEyQf.js";
import { r as relativeTime, t as bytes } from "./format-gcr4F9Vx.js";
import { t as Route } from "./deployments._id-6YyIXZgk.js";
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var CircleCheck = createLucideIcon("circle-check", [["circle", {
	cx: "12",
	cy: "12",
	r: "10",
	key: "1mglay"
}], ["path", {
	d: "m9 12 2 2 4-4",
	key: "dzmm74"
}]]);
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var CircleX = createLucideIcon("circle-x", [
	["circle", {
		cx: "12",
		cy: "12",
		r: "10",
		key: "1mglay"
	}],
	["path", {
		d: "m15 9-6 6",
		key: "1uzhvr"
	}],
	["path", {
		d: "m9 9 6 6",
		key: "z0biqf"
	}]
]);
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Save = createLucideIcon("save", [
	["path", {
		d: "M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z",
		key: "1c8476"
	}],
	["path", {
		d: "M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7",
		key: "1ydtos"
	}],
	["path", {
		d: "M7 3v4a1 1 0 0 0 1 1h7",
		key: "t51u73"
	}]
]);
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Send = createLucideIcon("send", [["path", {
	d: "M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11z",
	key: "1ffxy3"
}], ["path", {
	d: "m21.854 2.147-10.94 10.939",
	key: "12cjpa"
}]]);
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Trash2 = createLucideIcon("trash-2", [
	["path", {
		d: "M10 11v6",
		key: "nco0om"
	}],
	["path", {
		d: "M14 11v6",
		key: "outv1u"
	}],
	["path", {
		d: "M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6",
		key: "miytrc"
	}],
	["path", {
		d: "M3 6h18",
		key: "d0wm0j"
	}],
	["path", {
		d: "M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2",
		key: "e791ji"
	}]
]);
//#endregion
//#region src/routes/deployments.$id.tsx?tsr-split=component
var import_react = /* @__PURE__ */ __toESM(require_react());
var import_jsx_runtime = require_jsx_runtime();
var TABS = [
	{
		id: "overview",
		label: "Overview"
	},
	{
		id: "playground",
		label: "Playground"
	},
	{
		id: "performance",
		label: "Performance"
	},
	{
		id: "tuning",
		label: "Tuning"
	},
	{
		id: "logs",
		label: "Logs"
	},
	{
		id: "configuration",
		label: "Configuration"
	},
	{
		id: "revisions",
		label: "Revisions"
	}
];
function DeploymentDetail() {
	const { id } = Route.useParams();
	const { tab } = Route.useSearch();
	const navigate = useNavigate({ from: "/deployments/$id" });
	const { data: service, unavailable, error, isLoading, refetch } = useService(id);
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(AppShell, { children: [
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)(PageHeader, {
			eyebrow: "Deployment",
			title: service?.name ?? id,
			description: service ? `${service.artifactId} on ${service.backendKind}` : void 0,
			actions: service && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
				className: "inline-flex items-center gap-2 rift-mono text-[12px]",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StatDot, { tone: service.status === "running" ? "ok" : service.status === "degraded" ? "attention" : service.status === "failed" ? "error" : "info" }), service.status]
			})
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "border-b border-border bg-raised",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "max-w-[1400px] mx-auto px-4 flex gap-0 overflow-x-auto",
				children: TABS.map((t) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
					onClick: () => navigate({
						search: { tab: t.id },
						replace: true
					}),
					className: cn("h-11 px-4 text-[13px] border-b-2 -mb-px whitespace-nowrap", tab === t.id ? "border-primary text-ink font-medium" : "border-transparent text-ink-secondary hover:text-ink"),
					children: t.label
				}, t.id))
			})
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "max-w-[1400px] mx-auto min-w-0 px-4 py-6 grid gap-4",
			children: [
				unavailable && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
					endpoint: "/services",
					resource: "Service"
				}),
				isLoading && !service && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
					title: "Live deployment state",
					children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "flex items-center gap-2 text-[13px] text-ink-secondary",
						role: "status",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(LoaderCircle, {
							className: "size-4 animate-spin",
							"aria-hidden": true
						}), "Reading live service state..."]
					})
				}),
				error && !service && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
					title: "Live deployment state",
					children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "text-[13px] text-error",
						role: "alert",
						children: ["The controller could not return this deployment: ", error.message]
					})
				}),
				service && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ServiceActions, {
					service,
					onChanged: () => {
						refetch();
						window.setTimeout(refetch, 3e3);
						window.setTimeout(refetch, 12e3);
					},
					onDeleted: () => navigate({ to: "/deployments" })
				}),
				service && tab === "overview" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(OverviewTab, { s: service }),
				service && tab === "playground" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(PlaygroundTab, { s: service }),
				service && tab === "performance" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(PerformanceTab, { s: service }),
				service && tab === "tuning" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(DeploymentTuningTab, { service }),
				service && tab === "logs" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(LogsTab, { service }),
				service && tab === "configuration" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ConfigurationTab, { s: service }),
				tab === "revisions" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(RevisionsTab, { id })
			]
		})
	] });
}
function DeploymentTuningTab({ service }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
		title: "Autonomous tuning",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "max-w-2xl",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "flex items-start gap-3",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(SlidersHorizontal, {
					className: "size-5 text-primary mt-0.5",
					"aria-hidden": true
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("h2", {
						className: "text-[15px] text-ink font-medium",
						children: [
							"Tune ",
							service.name,
							" after deployment"
						]
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "mt-1.5 text-[13px] text-ink-secondary",
						children: "Choose Speed or Cost in the tuning workspace. RIFT will benchmark bounded llama.cpp settings, keep the model and precision contract locked, and show the evidence behind the winner."
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Link, {
						to: "/tuning",
						className: "mt-4 inline-flex items-center h-9 px-3.5 rounded-[4px] bg-primary text-primary-foreground text-[13px] font-medium hover:bg-[color:var(--oxide-deep)]",
						children: "Open tuning workspace"
					})
				] })]
			})
		})
	});
}
function ServiceActions({ service, onChanged, onDeleted }) {
	const [busy, setBusy] = (0, import_react.useState)(null);
	const [message, setMessage] = (0, import_react.useState)(null);
	const [error, setError] = (0, import_react.useState)(null);
	const [confirmDelete, setConfirmDelete] = (0, import_react.useState)(false);
	const [confirmTune, setConfirmTune] = (0, import_react.useState)(false);
	const [confirmRestart, setConfirmRestart] = (0, import_react.useState)(false);
	const [confirmRecover, setConfirmRecover] = (0, import_react.useState)(false);
	const run = async (action, task) => {
		setBusy(action);
		setMessage(null);
		setError(null);
		try {
			const result = await task();
			const payload = result && typeof result === "object" ? result : {};
			setMessage(typeof payload.reason === "string" ? payload.reason : ["restart", "recover"].includes(action) ? `${action} completed; verifying service health.` : `${action} completed; refresh the live service state for details.`);
			onChanged();
		} catch (err) {
			setError(err instanceof Error ? err.message : String(err));
		} finally {
			setBusy(null);
			setConfirmDelete(false);
			setConfirmTune(false);
			setConfirmRestart(false);
			setConfirmRecover(false);
		}
	};
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("section", {
		className: "rift-panel px-4 py-3",
		"aria-label": "Service operations",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "flex flex-wrap items-center gap-2",
			children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "rift-label mr-2",
					children: "Operations"
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
					type: "button",
					disabled: busy !== null,
					onClick: () => run("benchmark", () => rift.benchmarkSuite(service.name)),
					className: "inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] border border-border text-[12px] hover:bg-muted disabled:opacity-50",
					children: [busy === "benchmark" ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(LoaderCircle, { className: "size-3.5 animate-spin" }) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Gauge, { className: "size-3.5" }), "Benchmark"]
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
					type: "button",
					disabled: busy !== null,
					onClick: () => run("tune plan", () => rift.tuneService(service.name)),
					className: "inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] border border-border text-[12px] hover:bg-muted disabled:opacity-50",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(SlidersHorizontal, { className: "size-3.5" }), " Tune plan"]
				}),
				confirmRestart ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
					type: "button",
					disabled: busy !== null,
					onClick: () => run("restart", () => rift.restartService(service.name)),
					className: "inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] bg-attention text-ink text-[12px] font-medium disabled:opacity-50",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(RotateCcw, { className: "size-3.5" }), " Confirm restart"]
				}) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
					type: "button",
					disabled: busy !== null,
					onClick: () => setConfirmRestart(true),
					className: "inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] border border-border text-[12px] hover:bg-muted disabled:opacity-50",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(RotateCcw, { className: "size-3.5" }), " Restart"]
				}),
				confirmRecover ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
					type: "button",
					disabled: busy !== null,
					onClick: () => run("recover", () => rift.recoverService(service.name)),
					className: "inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] bg-secondary text-white text-[12px] font-medium disabled:opacity-50",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(ShieldCheck, { className: "size-3.5" }), " Confirm recover"]
				}) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
					type: "button",
					disabled: busy !== null,
					onClick: () => setConfirmRecover(true),
					className: "inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] border border-border text-[12px] hover:bg-muted disabled:opacity-50",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(ShieldCheck, { className: "size-3.5" }), " Recover"]
				}),
				confirmTune ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
					type: "button",
					disabled: busy !== null,
					onClick: () => run("live tune", () => rift.tuneService(service.name, {
						live: true,
						allowRestart: true,
						candidateLimit: 2
					})),
					className: "inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] bg-attention text-ink text-[12px] font-medium disabled:opacity-50",
					children: "Confirm live tune"
				}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
					type: "button",
					disabled: busy !== null,
					onClick: () => setConfirmTune(true),
					className: "inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] border border-border text-[12px] hover:bg-muted disabled:opacity-50",
					children: "Tune live"
				}),
				service.status !== "running" && (confirmRecover ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
					type: "button",
					disabled: busy !== null,
					onClick: () => run("recover", () => rift.recoverService(service.name)),
					className: "inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] bg-primary text-white text-[12px] font-medium disabled:opacity-50",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(RotateCcw, { className: "size-3.5" }), " Confirm recovery"]
				}) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
					type: "button",
					disabled: busy !== null,
					onClick: () => setConfirmRecover(true),
					className: "inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] border border-primary/40 text-primary text-[12px] hover:bg-primary/10 disabled:opacity-50",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(RotateCcw, { className: "size-3.5" }), " Recover service"]
				})),
				confirmDelete ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
					type: "button",
					disabled: busy !== null,
					onClick: () => run("delete", async () => {
						const result = await rift.destroyService(service.name);
						onDeleted();
						return result;
					}),
					className: "inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] bg-error text-white text-[12px] font-medium disabled:opacity-50",
					children: "Confirm delete"
				}) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
					type: "button",
					disabled: busy !== null,
					onClick: () => setConfirmDelete(true),
					className: "inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] border border-error/40 text-error text-[12px] hover:bg-error/10 disabled:opacity-50",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Trash2, { className: "size-3.5" }), " Delete service"]
				})
			]
		}), (message || error || confirmTune || confirmDelete || confirmRestart || confirmRecover) && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "mt-2 rift-mono text-[11px] text-ink-secondary",
			role: error ? "alert" : void 0,
			children: error ?? message ?? (confirmTune ? "Live tuning will restart the backend between candidates." : confirmRestart ? "Restart stops and relaunches the selected service using its current launch plan." : confirmRecover ? "Recovery may relaunch the service using its last-known-good launch plan." : "Deletion stops the service and removes its RIFT-managed state; model files are retained.")
		})]
	});
}
function OverviewTab({ s }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "grid gap-4 lg:grid-cols-3",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "lg:col-span-2 grid gap-4",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Panel, {
				title: "Endpoint",
				aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: s.provenance }),
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "flex items-center gap-2",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("code", {
						className: "flex-1 rift-mono text-[13px] text-ink break-all",
						children: [
							s.endpoint.scheme,
							"://",
							s.endpoint.bindAddress,
							":",
							s.endpoint.port,
							s.endpoint.path
						]
					}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
						type: "button",
						onClick: () => navigator.clipboard.writeText(`${s.endpoint.scheme}://${s.endpoint.bindAddress}:${s.endpoint.port}${s.endpoint.path}`),
						className: "inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] border border-border text-[12px] hover:bg-muted",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Copy, { className: "size-3.5" }), " Copy"]
					})]
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", {
					className: "mt-2 rift-mono text-[11px] text-ink-secondary",
					children: [
						s.endpoint.openaiCompatible ? "OpenAI-compatible" : "Custom protocol",
						" · binds to",
						" ",
						s.endpoint.bindAddress === "127.0.0.1" ? "localhost only" : s.endpoint.bindAddress
					]
				})]
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
				title: "Assignments",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
					className: "divide-y divide-border -mx-4 -my-4",
					children: s.assignments.map((a, i) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("li", {
						className: "px-4 py-3 flex items-center gap-4 text-[13px]",
						children: [
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "rift-mono text-ink",
								children: a.nodeId
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
								className: "rift-mono text-[11.5px] text-ink-secondary",
								children: ["GPU ", a.gpuIndices.join(", ") || "cpu"]
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
								className: "ml-auto rift-mono text-[11.5px] text-ink-secondary",
								children: [bytes(a.reservedVramBytes), " reserved"]
							})
						]
					}, i))
				})
			})]
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "grid gap-4",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
				title: "Meta",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "grid gap-3",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "Service ID",
							value: s.id
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "Artifact",
							value: s.artifactId
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "Backend",
							value: s.backendKind
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "Use case",
							value: s.useCase
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "Revision",
							value: s.currentRevision
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "Updated",
							value: relativeTime(s.updatedAt)
						})
					]
				})
			})
		})]
	});
}
function PlaygroundTab({ s }) {
	const [input, setInput] = (0, import_react.useState)("");
	const [busy, setBusy] = (0, import_react.useState)(false);
	const [out, setOut] = (0, import_react.useState)("");
	const [err, setErr] = (0, import_react.useState)(null);
	const submit = async () => {
		setBusy(true);
		setErr(null);
		setOut("");
		try {
			const endpoint = `${s.endpoint.scheme}://${s.endpoint.bindAddress}:${s.endpoint.port}${s.endpoint.path}`;
			let model = s.artifactId;
			try {
				const catalog = await fetch(`${endpoint}/models`);
				if (catalog.ok) model = (await catalog.json()).data?.find((item) => item.id)?.id ?? model;
			} catch {}
			const url = `${endpoint}/chat/completions`;
			const res = await fetch(url, {
				method: "POST",
				headers: { "content-type": "application/json" },
				body: JSON.stringify({
					model,
					messages: [{
						role: "user",
						content: input
					}]
				})
			});
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			const j = await res.json();
			setOut(j.choices?.[0]?.message?.content ?? "");
		} catch (e) {
			setErr(e instanceof Error ? e.message : String(e));
		} finally {
			setBusy(false);
		}
	};
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "grid gap-4 lg:grid-cols-2",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Panel, {
			title: "Prompt",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("textarea", {
				value: input,
				onChange: (e) => setInput(e.target.value),
				rows: 10,
				placeholder: "Ask the model something…",
				className: "w-full p-3 rounded-[4px] border border-border bg-raised text-[13px] focus:outline-none focus:border-primary resize-y"
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "mt-3 flex items-center gap-2",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
					type: "button",
					onClick: submit,
					disabled: busy || !input.trim(),
					className: "inline-flex items-center gap-2 h-9 px-3.5 rounded-[4px] bg-primary text-primary-foreground text-[13px] font-medium hover:bg-[color:var(--oxide-deep)] disabled:opacity-60",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Send, { className: "size-4" }), " Send"]
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "rift-mono text-[11px] text-ink-secondary",
					children: "Calls the service's own OpenAI-compatible endpoint (not the controller API)."
				})]
			})]
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
			title: "Response",
			children: err ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "text-[13px] text-error rift-mono",
				children: err
			}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("pre", {
				className: "whitespace-pre-wrap text-[13px] text-ink min-h-[8rem]",
				children: out || /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "text-ink-secondary",
					children: "Waiting for prompt…"
				})
			})
		})]
	});
}
function PerformanceTab({ s }) {
	const { data, unavailable, refetch } = useBenchmarks(s.id);
	const telemetry = useTelemetryLatest(s.name);
	const resourceReports = useResourceReports(s.name);
	const accounting = useServiceTelemetryAccounting(s.name);
	const evaluations = useEvaluations(s.name);
	const reports = useReports();
	const [benchmarkPrompt, setBenchmarkPrompt] = (0, import_react.useState)("Explain one practical benefit of local LLM inference in two sentences.");
	const [benchmarkMaxTokens, setBenchmarkMaxTokens] = (0, import_react.useState)(48);
	const [benchmarkWarmups, setBenchmarkWarmups] = (0, import_react.useState)(1);
	const [benchmarkRepetitions, setBenchmarkRepetitions] = (0, import_react.useState)(3);
	const [benchmarkConcurrency, setBenchmarkConcurrency] = (0, import_react.useState)(1);
	const [benchmarkBusy, setBenchmarkBusy] = (0, import_react.useState)(false);
	const [benchmarkError, setBenchmarkError] = (0, import_react.useState)(null);
	const [evaluationBusy, setEvaluationBusy] = (0, import_react.useState)(false);
	const [evaluationError, setEvaluationError] = (0, import_react.useState)(null);
	const [electricityPrice, setElectricityPrice] = (0, import_react.useState)("");
	const [computeCost, setComputeCost] = (0, import_react.useState)("");
	const [accountingBusy, setAccountingBusy] = (0, import_react.useState)(false);
	const [accountingError, setAccountingError] = (0, import_react.useState)(null);
	const [accountingSaved, setAccountingSaved] = (0, import_react.useState)(false);
	(0, import_react.useEffect)(() => {
		if (!accounting.data) return;
		setElectricityPrice(accounting.data.electricityPricePerKwh == null ? "" : String(accounting.data.electricityPricePerKwh));
		setComputeCost(accounting.data.computeCostPerNodeHour == null ? "" : String(accounting.data.computeCostPerNodeHour));
	}, [accounting.data]);
	const latestEvaluation = evaluations.data?.[0];
	const latestTuning = (Array.isArray(reports.data?.reports) ? reports.data.reports : []).map((value) => {
		const entry = asRecord(value);
		return {
			created: Number(entry.created_unix_seconds ?? 0),
			report: asRecord(entry.summary)
		};
	}).filter(({ report }) => {
		return String(report.service ?? "") === s.name && "winning_config" in report;
	}).sort((left, right) => right.created - left.created)[0]?.report;
	const runEvaluation = async () => {
		setEvaluationBusy(true);
		setEvaluationError(null);
		try {
			await rift.evaluateService(s.name);
			evaluations.refetch();
		} catch (error) {
			setEvaluationError(error instanceof Error ? error.message : String(error));
		} finally {
			setEvaluationBusy(false);
		}
	};
	const runBenchmark = async () => {
		setBenchmarkBusy(true);
		setBenchmarkError(null);
		try {
			await rift.benchmarkSuite(s.name, {
				prompt: benchmarkPrompt,
				maxTokens: Math.min(128, Math.max(1, benchmarkMaxTokens)),
				warmups: Math.max(0, benchmarkWarmups),
				repetitions: Math.max(1, benchmarkRepetitions),
				concurrency: Math.max(1, benchmarkConcurrency)
			});
			refetch();
		} catch (error) {
			setBenchmarkError(error instanceof Error ? error.message : String(error));
		} finally {
			setBenchmarkBusy(false);
		}
	};
	const saveAccounting = async () => {
		const parseRate = (value, label) => {
			if (!value.trim()) return null;
			const parsed = Number(value);
			if (!Number.isFinite(parsed) || parsed < 0) throw new Error(`${label} must be a non-negative number or blank.`);
			return parsed;
		};
		setAccountingBusy(true);
		setAccountingError(null);
		setAccountingSaved(false);
		try {
			await rift.updateServiceTelemetryAccounting(s.name, {
				electricityPricePerKwh: parseRate(electricityPrice, "Electricity price"),
				computeCostPerNodeHour: parseRate(computeCost, "Compute cost")
			});
			await Promise.all([accounting.refetch(), resourceReports.refetch()]);
			setAccountingSaved(true);
		} catch (error) {
			setAccountingError(error instanceof Error ? error.message : String(error));
		} finally {
			setAccountingBusy(false);
		}
	};
	if (unavailable) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
		endpoint: "/reports",
		resource: "Benchmark[]"
	});
	const rows = data ?? [];
	const liveSample = (telemetry.data?.[0])?.sample;
	const value = (item, suffix = "") => item == null || Number.isNaN(item) ? "unavailable" : `${item.toFixed(1)}${suffix}`;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "grid gap-4",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
				title: "Live resources",
				aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "rift-mono text-[11px] text-ink-secondary",
					children: liveSample ? `sampled ${relativeTime(liveSample.observedAt)}` : "waiting for telemetry"
				}),
				children: telemetry.unavailable ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "text-[13px] text-ink-secondary",
					children: "Resource telemetry is not available from this controller."
				}) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "grid grid-cols-2 gap-4 sm:grid-cols-4",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "Service CPU",
							value: value(liveSample?.processCpuPercent, "%")
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "Service memory",
							value: liveSample?.processRssBytes == null ? "unavailable" : bytes(liveSample.processRssBytes)
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "GPU utilization",
							value: value(liveSample?.gpuUtilizationPercent, "%")
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "GPU temperature",
							value: value(liveSample?.gpuTemperatureC, "°C")
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "GPU power",
							value: value(liveSample?.gpuPowerWatts, " W")
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "Host RAM pressure",
							value: value(liveSample?.hostRamPressurePercent, "%")
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "GPU VRAM",
							value: liveSample?.gpuVramUsedBytes == null ? "unavailable" : `${bytes(liveSample.gpuVramUsedBytes)} / ${bytes(liveSample.gpuVramTotalBytes ?? 0)}`
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "Collection",
							value: liveSample?.availability?.gpu === "measured" ? "measured" : "partial"
						})
					]
				})
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
				title: "Resource accounting",
				aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: "live" }),
				children: accounting.unavailable ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
					className: "text-[12px] text-ink-secondary",
					children: "Service accounting settings are unavailable from this controller."
				}) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "grid gap-3",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "grid gap-3 sm:grid-cols-2",
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
								className: "grid gap-1 text-[12px]",
								children: [
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
										className: "rift-label",
										children: "Electricity price / kWh"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
										type: "number",
										min: 0,
										step: "0.0001",
										value: electricityPrice,
										onChange: (event) => setElectricityPrice(event.target.value),
										placeholder: "Not configured",
										className: "h-8 rounded-[4px] border border-border bg-raised px-2 rift-mono"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
										className: "text-[11px] text-ink-secondary",
										children: accounting.data?.electricityPriceSource === "global" ? "Using the global telemetry default. Enter a value to override it for this service." : "Leave blank to clear this service override."
									})
								]
							}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
								className: "grid gap-1 text-[12px]",
								children: [
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
										className: "rift-label",
										children: "Compute cost / node-hour"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
										type: "number",
										min: 0,
										step: "0.0001",
										value: computeCost,
										onChange: (event) => setComputeCost(event.target.value),
										placeholder: "Not configured",
										className: "h-8 rounded-[4px] border border-border bg-raised px-2 rift-mono"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
										className: "text-[11px] text-ink-secondary",
										children: "Applied to this service's runtime duration in future reports."
									})
								]
							})]
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "flex flex-wrap items-center gap-3",
							children: [
								/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
									type: "button",
									onClick: saveAccounting,
									disabled: accountingBusy,
									className: "inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] bg-primary text-primary-foreground text-[12px] font-medium hover:bg-[color:var(--oxide-deep)] disabled:opacity-50",
									children: [accountingBusy ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(LoaderCircle, { className: "size-3.5 animate-spin" }) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Save, { className: "size-3.5" }), "Save service rates"]
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
									className: "rift-mono text-[11px] text-ink-secondary",
									children: accounting.data?.configPath ? `Stored in ${accounting.data.configPath}` : "Stored in the service configuration"
								}),
								accountingSaved && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
									className: "text-[11px] text-secondary",
									children: "Saved"
								})
							]
						}),
						accountingError && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
							className: "rift-mono text-[11px] text-error",
							role: "alert",
							children: accountingError
						})
					]
				})
			}),
			resourceReports.data && resourceReports.data.length > 0 && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
				title: "Completed resource reports",
				bodyClassName: "p-0",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "overflow-x-auto",
					children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("table", {
						className: "w-full min-w-[640px] text-[13px] rift-mono",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("thead", {
							className: "rift-label",
							children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
								className: "border-b border-border",
								children: [
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-left px-4 h-9 font-normal",
										children: "Stopped"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-left px-4 font-normal",
										children: "Samples"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-left px-4 font-normal",
										children: "CPU avg"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-left px-4 font-normal",
										children: "GPU energy"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-left px-4 font-normal",
										children: "Cost"
									})
								]
							})
						}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("tbody", { children: resourceReports.data.map((report) => {
							const cpu = report.metrics.process_cpu_percent?.average;
							const energy = report.costs?.energyJoules;
							const electricity = report.costs?.electricityCost;
							const compute = report.costs?.computeCost;
							const cost = report.costs?.totalCost ?? (electricity == null && compute == null ? void 0 : (electricity ?? 0) + (compute ?? 0));
							return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
								className: "border-b border-border last:border-0",
								children: [
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
										className: "px-4 py-2",
										children: relativeTime(report.stoppedAt)
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
										className: "px-4",
										children: report.sampleCount
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
										className: "px-4",
										children: value(cpu, "%")
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
										className: "px-4",
										children: energy == null ? "unavailable" : `${energy.toFixed(1)} J`
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
										className: "px-4",
										children: cost == null ? "unconfigured" : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
											title: `Electricity: ${electricity ?? 0}; compute: ${compute ?? 0}`,
											children: cost.toFixed(4)
										})
									})
								]
							}, report.reportId);
						}) })]
					})
				})
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
				title: "Benchmarks",
				bodyClassName: "p-0",
				children: rows.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "px-4 py-10 text-center text-[13px] text-ink-secondary",
					children: "No benchmarks recorded yet."
				}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "overflow-x-auto",
					children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("table", {
						className: "w-full min-w-[620px] text-[13px] rift-mono",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("thead", {
							className: "rift-label",
							children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
								className: "border-b border-border",
								children: [
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-left px-4 h-9 font-normal",
										children: "At"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-left px-4 font-normal",
										children: "tok/s"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-left px-4 font-normal",
										children: "first token"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-left px-4 font-normal",
										children: "concurrency"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-left px-4 font-normal",
										children: "ctx"
									})
								]
							})
						}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("tbody", { children: rows.map((b) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
							className: "border-b border-border last:border-0",
							children: [
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-4 py-2",
									children: relativeTime(b.measuredAt)
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-4",
									children: b.tokensPerSec.toFixed(1)
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("td", {
									className: "px-4",
									children: [b.firstTokenMs, "ms"]
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-4",
									children: b.concurrency
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-4",
									children: b.contextTokens
								})
							]
						}, b.id)) })]
					})
				})
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
				title: "Run benchmark",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "grid gap-3",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
							className: "grid gap-1 text-[12px]",
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "rift-label",
								children: "Prompt"
							}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("textarea", {
								value: benchmarkPrompt,
								onChange: (event) => setBenchmarkPrompt(event.target.value),
								rows: 3,
								className: "w-full rounded-[4px] border border-border bg-raised p-2 text-[13px] resize-y"
							})]
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "grid grid-cols-2 gap-3 sm:grid-cols-4",
							children: [
								/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
									className: "grid gap-1 text-[12px]",
									children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
										className: "rift-label",
										children: "Output tokens"
									}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
										type: "number",
										min: 1,
										max: 128,
										value: benchmarkMaxTokens,
										onChange: (event) => setBenchmarkMaxTokens(Number(event.target.value)),
										className: "h-8 rounded-[4px] border border-border bg-raised px-2 rift-mono"
									})]
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
									className: "grid gap-1 text-[12px]",
									children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
										className: "rift-label",
										children: "Warmups"
									}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
										type: "number",
										min: 0,
										max: 10,
										value: benchmarkWarmups,
										onChange: (event) => setBenchmarkWarmups(Number(event.target.value)),
										className: "h-8 rounded-[4px] border border-border bg-raised px-2 rift-mono"
									})]
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
									className: "grid gap-1 text-[12px]",
									children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
										className: "rift-label",
										children: "Repetitions"
									}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
										type: "number",
										min: 1,
										max: 20,
										value: benchmarkRepetitions,
										onChange: (event) => setBenchmarkRepetitions(Number(event.target.value)),
										className: "h-8 rounded-[4px] border border-border bg-raised px-2 rift-mono"
									})]
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
									className: "grid gap-1 text-[12px]",
									children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
										className: "rift-label",
										children: "Concurrency"
									}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
										type: "number",
										min: 1,
										max: 8,
										value: benchmarkConcurrency,
										onChange: (event) => setBenchmarkConcurrency(Number(event.target.value)),
										className: "h-8 rounded-[4px] border border-border bg-raised px-2 rift-mono"
									})]
								})
							]
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "flex flex-wrap items-center gap-3",
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
								type: "button",
								onClick: runBenchmark,
								disabled: benchmarkBusy || !benchmarkPrompt.trim() || !["running", "healthy"].includes(s.status),
								className: "inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] bg-primary text-primary-foreground text-[12px] font-medium hover:bg-[color:var(--oxide-deep)] disabled:opacity-50",
								children: [benchmarkBusy ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(LoaderCircle, { className: "size-3.5 animate-spin" }) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Gauge, { className: "size-3.5" }), "Run measured benchmark"]
							}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "rift-mono text-[11px] text-ink-secondary",
								children: "Defaults: 1 warmup, 3 samples, concurrency 1."
							})]
						}),
						benchmarkError && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
							className: "rift-mono text-[11px] text-error",
							role: "alert",
							children: benchmarkError
						})
					]
				})
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
				title: "Latest tuning result",
				aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: "live" }),
				children: reports.unavailable ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
					className: "text-[12px] text-ink-secondary",
					children: "Tuning history is unavailable."
				}) : !latestTuning ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
					className: "text-[12px] text-ink-secondary",
					children: "No tuning result recorded yet."
				}) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "grid gap-4",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "grid gap-4 sm:grid-cols-4",
							children: [
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
									label: "Performance delta",
									value: typeof latestTuning.improvement_percent === "number" ? `${latestTuning.improvement_percent.toFixed(2)}%` : "not measured"
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
									label: "Baseline score",
									value: typeof latestTuning.baseline_score === "number" ? latestTuning.baseline_score.toFixed(3) : "not measured"
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
									label: "Winning score",
									value: typeof latestTuning.winning_score === "number" ? latestTuning.winning_score.toFixed(3) : "not measured"
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
									label: "Mode",
									value: String(latestTuning.mode ?? "measured")
								})
							]
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
							className: "rift-label",
							children: "Winning parameters"
						}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("pre", {
							className: "mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded-[4px] border border-border bg-raised p-3 rift-mono text-[11.5px] text-ink",
							children: JSON.stringify(latestTuning.winning_config, null, 2)
						})] }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
							className: "text-[12px] text-ink-secondary",
							children: String(latestTuning.decision ?? "Winner selected from the recorded tuning candidates.")
						})
					]
				})
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Panel, {
				title: "Answer quality",
				aside: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
					type: "button",
					onClick: runEvaluation,
					disabled: evaluationBusy || s.status !== "running",
					className: "inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] bg-primary text-primary-foreground text-[12px] font-medium hover:bg-[color:var(--oxide-deep)] disabled:opacity-50",
					children: [evaluationBusy ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(LoaderCircle, { className: "size-3.5 animate-spin" }) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ShieldCheck, { className: "size-3.5" }), "Run smoke check"]
				}),
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "text-[12px] text-ink-secondary",
						children: "Five bounded, deterministic checks. This measures behavior against explicit criteria; it is not a general accuracy certification."
					}),
					evaluationError && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "mt-3 rift-mono text-[11px] text-error",
						role: "alert",
						children: evaluationError
					}),
					evaluations.unavailable ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "mt-3 rift-mono text-[11px] text-ink-secondary",
						children: "Answer evaluation is unavailable on this controller."
					}) : latestEvaluation ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "mt-4 grid gap-2",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "flex flex-wrap items-center gap-3 rift-mono text-[11px]",
							children: [
								/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
									className: "text-ink",
									children: [
										latestEvaluation.suite.id,
										" v",
										latestEvaluation.suite.version
									]
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
									className: "text-ink-secondary",
									children: [latestEvaluation.summary.pass ?? 0, " passed"]
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
									className: "text-error",
									children: [latestEvaluation.summary.fail ?? 0, " failed"]
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
									className: "text-ink-secondary",
									children: [latestEvaluation.summary.not_assessed ?? 0, " not assessed"]
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
									className: "ml-auto text-ink-secondary",
									children: latestEvaluation.status
								})
							]
						}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
							className: "divide-y divide-border border border-border rounded-[4px]",
							children: latestEvaluation.cases.map((item) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("li", {
								className: "flex items-start gap-2 px-3 py-2 text-[12px]",
								children: [item.status === "pass" ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(CircleCheck, { className: "mt-0.5 size-3.5 text-secondary shrink-0" }) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(CircleX, { className: "mt-0.5 size-3.5 text-error shrink-0" }), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
									className: "min-w-0",
									children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
										className: "font-medium text-ink",
										children: item.caseId
									}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
										className: "block text-ink-secondary",
										children: item.detail
									})]
								})]
							}, item.caseId))
						})]
					}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "mt-3 rift-mono text-[11px] text-ink-secondary",
						children: "No evaluation run recorded yet."
					})
				]
			})
		]
	});
}
function LogsTab({ service }) {
	const { data, unavailable } = useLogs(service.name);
	if (unavailable) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
		endpoint: "/logs",
		resource: `${service.name} service logs`
	});
	const lines = Array.isArray(data?.lines) ? data.lines : typeof data?.text === "string" ? data.text.split(/\r?\n/) : [];
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
		title: `${service.name} / latest logs`,
		aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: "live" }),
		bodyClassName: "p-0",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("pre", {
			className: "max-h-[580px] overflow-auto bg-[color:var(--ink)] px-4 py-3 rift-mono text-[11.5px] leading-5 text-[color:var(--surface)]",
			children: lines.length ? lines.map((line) => typeof line === "string" ? line : JSON.stringify(line)).join("\n") : "No log lines available."
		})
	});
}
function ConfigurationTab({ s }) {
	const details = s.details ?? {};
	const model = details.model ?? {};
	const serving = details.serving ?? {};
	const gateway = details.gateway ?? {};
	const launchPlan = details.launchPlan ?? {};
	const modelPath = String(details.modelPath ?? model.selected_file ?? model.id ?? s.artifactId);
	const contextLength = serving.context_length ?? launchPlan.context_length ?? details.contextLength;
	const concurrency = serving.concurrency ?? launchPlan.concurrency ?? details.concurrency;
	const gatewayCors = gateway.cors_origins;
	const corsOrigins = Array.isArray(gatewayCors) ? gatewayCors.map(String) : typeof gatewayCors === "string" ? [gatewayCors] : [];
	const exposed = ![
		"127.0.0.1",
		"localhost",
		"::1"
	].includes(s.endpoint.bindAddress);
	const securityWarnings = [];
	if (corsOrigins.includes("*")) securityWarnings.push("Unrestricted CORS is enabled for this service.");
	if (exposed && gateway.api_key_protection === "not_configured") securityWarnings.push("The service is network-exposed but gateway API-key protection is not configured.");
	const effectiveLaunch = {
		service: s.name,
		backend: s.backendKind,
		backend_version: details.backendVersion ?? launchPlan.version ?? "unknown",
		artifact: s.artifactId,
		model: modelPath,
		serving,
		endpoint: s.endpoint,
		placement: s.assignments,
		launch_plan: launchPlan,
		gateway,
		process: {
			pid: details.pid ?? null,
			restart_count: details.restartCount ?? null
		}
	};
	const yaml = `service:
  name: ${s.name}
  artifact: ${s.artifactId}
  backend: ${s.backendKind}
  endpoint:
    scheme: ${s.endpoint.scheme}
    bind: ${s.endpoint.bindAddress}
    port: ${s.endpoint.port}
    path: ${s.endpoint.path}
assignments:
${s.assignments.map((a) => `  - node: ${a.nodeId}\n    gpus: [${a.gpuIndices.join(", ")}]`).join("\n")}
`;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "grid gap-4",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Panel, {
			title: "Effective launch settings",
			aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: "live" }),
			children: [
				securityWarnings.length > 0 && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "mb-4 border border-error/50 bg-error/5 px-3 py-3 text-[12px] text-error",
					role: "alert",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "rift-label text-error",
						children: "Security attention required"
					}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
						className: "mt-2 grid gap-1 list-disc pl-4",
						children: securityWarnings.map((warning) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("li", { children: warning }, warning))
					})]
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "grid gap-4 sm:grid-cols-2 lg:grid-cols-4",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "Backend",
							value: `${s.backendKind} · ${String(details.backendVersion ?? launchPlan.version ?? "version unknown")}`
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "Model",
							value: modelPath
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "Endpoint",
							value: `${s.endpoint.scheme}://${s.endpoint.bindAddress}:${s.endpoint.port}${s.endpoint.path}`
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "Exposure",
							value: `${String(details.exposure ?? "local")} · ${s.endpoint.bindAddress}`
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "Context length",
							value: contextLength == null ? "unknown" : String(contextLength)
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "Concurrency",
							value: concurrency == null ? "unknown" : String(concurrency)
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "Process",
							value: details.pid == null ? "not running" : `PID ${details.pid}`
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "Gateway",
							value: gateway.status == null ? "not configured" : String(gateway.status)
						})
					]
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("details", {
					className: "mt-4 border-t border-border pt-3",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("summary", {
						className: "cursor-pointer rift-label",
						children: "Full effective launch payload"
					}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("pre", {
						className: "mt-2 max-h-96 overflow-auto whitespace-pre-wrap rift-mono text-[11.5px] text-ink",
						children: JSON.stringify(effectiveLaunch, null, 2)
					})]
				})
			]
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Panel, {
			title: "Normalized configuration",
			aside: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
				type: "button",
				onClick: () => navigator.clipboard.writeText(yaml),
				className: "inline-flex items-center gap-1.5 h-7 px-2.5 rounded-[4px] border border-border text-[11.5px] hover:bg-muted",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Copy, { className: "size-3" }), " Copy YAML"]
			}),
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("pre", {
				className: "rift-mono text-[12.5px] text-ink whitespace-pre",
				children: yaml
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
				className: "mt-3 rift-mono text-[11px] text-ink-secondary",
				children: "Advanced users can export this via GET /services or apply changes by generating a new plan."
			})]
		})]
	});
}
function asRecord(value) {
	return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}
function RevisionsTab({ id }) {
	const { data, unavailable } = useRevisions(id);
	const [busy, setBusy] = (0, import_react.useState)(false);
	const [message, setMessage] = (0, import_react.useState)(null);
	const [error, setError] = (0, import_react.useState)(null);
	const [confirm, setConfirm] = (0, import_react.useState)(false);
	if (unavailable) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
		endpoint: "/state",
		resource: "DeploymentRevision[]"
	});
	const rows = data ?? [];
	const rollback = async () => {
		setBusy(true);
		setMessage(null);
		setError(null);
		try {
			await rift.rollback(id);
			setMessage("Rollback completed; refresh the live service state for details.");
		} catch (err) {
			setError(err instanceof Error ? err.message : String(err));
		} finally {
			setBusy(false);
			setConfirm(false);
		}
	};
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Panel, {
		title: "Revisions",
		bodyClassName: "p-0",
		aside: rows.length > 0 && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
			type: "button",
			disabled: busy,
			onClick: () => setConfirm(true),
			className: "inline-flex items-center gap-1.5 h-7 px-2.5 rounded-[4px] border border-border text-[11.5px] hover:bg-muted disabled:opacity-50",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(RotateCcw, { className: "size-3" }), " Roll back last known-good"]
		}),
		children: [
			(message || error) && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "px-4 py-2 border-b border-border rift-mono text-[11px]",
				role: error ? "alert" : void 0,
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: error ? "text-error" : "text-ink-secondary",
					children: error ?? message
				})
			}),
			confirm && !busy && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "px-4 py-2 border-b border-border flex flex-wrap items-center gap-2 rift-mono text-[11px]",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "text-ink-secondary",
						children: "This relaunches the last known-good service configuration."
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
						type: "button",
						onClick: rollback,
						className: "inline-flex items-center gap-1.5 h-7 px-2.5 rounded-[4px] bg-attention text-ink font-medium",
						children: "Confirm rollback"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
						type: "button",
						onClick: () => setConfirm(false),
						className: "inline-flex items-center h-7 px-2.5 rounded-[4px] border border-border",
						children: "Cancel"
					})
				]
			}),
			rows.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "px-4 py-10 text-center text-[13px] text-ink-secondary",
				children: "No revisions yet."
			}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
				className: "divide-y divide-border",
				children: rows.map((r) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("li", {
					className: "px-4 py-3 flex items-center gap-3 text-[13px]",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "rift-mono text-ink",
							children: r.id
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
							className: "rift-mono text-[11.5px] text-ink-secondary truncate",
							children: [
								"plan ",
								r.planHash.slice(0, 12),
								"… · by ",
								r.appliedBy
							]
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "rift-mono text-[11.5px] text-ink-secondary ml-auto",
							children: relativeTime(r.createdAt)
						})
					]
				}, r.id))
			})
		]
	});
}
//#endregion
export { DeploymentDetail as component };
