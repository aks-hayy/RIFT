import { i as require_react, r as require_jsx_runtime, s as __toESM } from "./useRouter-C_cgokP9.js";
import { t as useNavigate } from "./useNavigate-VOCCG6_j.js";
import { a as StatDot, b as useService, c as useBenchmarks, f as useLogs, i as SourceBadge, n as PageHeader, o as AppShell, r as Panel, t as KV, y as useRevisions } from "./primitives-At99O-dv.js";
import { c as createLucideIcon, i as cn, r as rift, t as Unavailable } from "./unavailable-Dh9iADmt.js";
import { n as Gauge, r as Copy, t as LoaderCircle } from "./loader-circle-DJNHY7Ri.js";
import { r as relativeTime, t as bytes } from "./format-gcr4F9Vx.js";
import { t as Route } from "./deployments._id-BFkwRckC.js";
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var RotateCcw = createLucideIcon("rotate-ccw", [["path", {
	d: "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8",
	key: "1357e3"
}], ["path", {
	d: "M3 3v5h5",
	key: "1xhq8a"
}]]);
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
var SlidersHorizontal = createLucideIcon("sliders-horizontal", [
	["path", {
		d: "M10 5H3",
		key: "1qgfaw"
	}],
	["path", {
		d: "M12 19H3",
		key: "yhmn1j"
	}],
	["path", {
		d: "M14 3v4",
		key: "1sua03"
	}],
	["path", {
		d: "M16 17v4",
		key: "1q0r14"
	}],
	["path", {
		d: "M21 12h-9",
		key: "1o4lsq"
	}],
	["path", {
		d: "M21 19h-5",
		key: "1rlt1p"
	}],
	["path", {
		d: "M21 5h-7",
		key: "1oszz2"
	}],
	["path", {
		d: "M8 10v4",
		key: "tgpxqk"
	}],
	["path", {
		d: "M8 12H3",
		key: "a7s4jb"
	}]
]);
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
	const { data: service, unavailable } = useService(id);
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
			className: "max-w-[1400px] mx-auto px-4 py-6 grid gap-4",
			children: [
				unavailable && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
					endpoint: `/v1/services/${id}`,
					resource: "Service"
				}),
				service && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ServiceActions, {
					service,
					onDeleted: () => navigate({ to: "/deployments" })
				}),
				service && tab === "overview" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(OverviewTab, { s: service }),
				service && tab === "playground" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(PlaygroundTab, { s: service }),
				service && tab === "performance" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(PerformanceTab, { s: service }),
				service && tab === "logs" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(LogsTab, { service }),
				service && tab === "configuration" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ConfigurationTab, { s: service }),
				tab === "revisions" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(RevisionsTab, { id })
			]
		})
	] });
}
function ServiceActions({ service, onDeleted }) {
	const [busy, setBusy] = (0, import_react.useState)(null);
	const [message, setMessage] = (0, import_react.useState)(null);
	const [error, setError] = (0, import_react.useState)(null);
	const [confirmDelete, setConfirmDelete] = (0, import_react.useState)(false);
	const [confirmTune, setConfirmTune] = (0, import_react.useState)(false);
	const [confirmRecover, setConfirmRecover] = (0, import_react.useState)(false);
	const run = async (action, task) => {
		setBusy(action);
		setMessage(null);
		setError(null);
		try {
			const result = await task();
			const payload = result && typeof result === "object" ? result : {};
			setMessage(typeof payload.reason === "string" ? payload.reason : `${action} completed; refresh the live service state for details.`);
		} catch (err) {
			setError(err instanceof Error ? err.message : String(err));
		} finally {
			setBusy(null);
			setConfirmDelete(false);
			setConfirmTune(false);
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
		}), (message || error || confirmTune || confirmRecover || confirmDelete) && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "mt-2 rift-mono text-[11px] text-ink-secondary",
			role: error ? "alert" : void 0,
			children: error ?? message ?? (confirmTune ? "Live tuning will restart the backend between candidates." : confirmRecover ? "Recovery will relaunch the last-known-good backend plan." : "Deletion stops the service and removes its RIFT-managed state; model files are retained.")
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
	const { data, unavailable } = useBenchmarks(s.id);
	if (unavailable) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
		endpoint: `/v1/services/${s.id}/benchmarks`,
		resource: "Benchmark[]"
	});
	const rows = data ?? [];
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
		title: "Benchmarks",
		bodyClassName: "p-0",
		children: rows.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "px-4 py-10 text-center text-[13px] text-ink-secondary",
			children: "No benchmarks recorded yet."
		}) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("table", {
			className: "w-full text-[13px] rift-mono",
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
	});
}
function LogsTab({ service }) {
	const { data, unavailable } = useLogs();
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
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Panel, {
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
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", {
			className: "mt-3 rift-mono text-[11px] text-ink-secondary",
			children: [
				"Advanced users can export this via GET /v1/services/",
				s.id,
				"/yaml or apply changes by generating a new plan."
			]
		})]
	});
}
function RevisionsTab({ id }) {
	const { data, unavailable } = useRevisions(id);
	if (unavailable) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
		endpoint: `/v1/services/${id}/revisions`,
		resource: "DeploymentRevision[]"
	});
	const rows = data ?? [];
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
		title: "Revisions",
		bodyClassName: "p-0",
		children: rows.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
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
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
						type: "button",
						className: "inline-flex items-center gap-1.5 h-7 px-2.5 rounded-[4px] border border-border text-[11.5px] hover:bg-muted",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(RotateCcw, { className: "size-3" }), " Roll back"]
					})
				]
			}, r.id))
		})
	});
}
//#endregion
export { DeploymentDetail as component };
