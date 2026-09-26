import { c as __toESM, i as require_react, r as require_jsx_runtime } from "./useRouter-C3Fl0Qct.js";
import { t as Link } from "./link-RSGdeuyI.js";
import { i as SourceBadge, n as PageHeader, o as AppShell, r as Panel } from "./primitives-DeAXA1eZ.js";
import { S as useRecommendations } from "./hooks-BdOll_GY.js";
import { t as RefreshCw } from "./refresh-cw-OthjuVPx.js";
import { t as Search } from "./search-C3Dg6PxT.js";
import { t as Sparkles } from "./sparkles-Bn9bIhdR.js";
import { t as bytes } from "./format-gcr4F9Vx.js";
import { t as Unavailable } from "./unavailable-D_3mUZyv.js";
//#region src/routes/models.tsx?tsr-split=component
var import_react = /* @__PURE__ */ __toESM(require_react());
var import_jsx_runtime = require_jsx_runtime();
function ModelsPage() {
	const [task, setTask] = (0, import_react.useState)("chat");
	const [search, setSearch] = (0, import_react.useState)(null);
	const [attempt, setAttempt] = (0, import_react.useState)(0);
	const recommendations = useRecommendations(search ? {
		useCase: search,
		source: "huggingface",
		refresh: attempt > 0
	} : null);
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(AppShell, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(PageHeader, {
		eyebrow: "Model discovery",
		title: "Find a model for this machine",
		description: "Run RIFT’s live hardware-aware discovery. Results come from the controller and retain their measured, estimated, and repository provenance.",
		actions: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "flex items-center gap-2",
			children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Link, {
					to: "/models/catalog",
					className: "inline-flex h-9 items-center rounded-xl border border-border bg-white/70 px-3 text-[12px] font-medium text-ink hover:border-primary/35 hover:text-primary",
					children: "Local artifact catalog"
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("select", {
					value: task,
					onChange: (event) => setTask(event.target.value),
					className: "h-9 rounded-[4px] border border-border bg-raised px-3 text-[12.5px] text-ink",
					"aria-label": "Recommendation task",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
							value: "chat",
							children: "Chat"
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
							value: "coding",
							children: "Coding"
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
							value: "documents",
							children: "Documents"
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
							value: "agent",
							children: "Agent"
						})
					]
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
					type: "button",
					onClick: () => {
						setAttempt(0);
						setSearch(task);
					},
					className: "inline-flex h-9 items-center gap-2 rounded-[4px] bg-primary px-3.5 text-[13px] font-medium text-primary-foreground hover:bg-[color:var(--oxide-deep)]",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Search, {
						className: "size-4",
						"aria-hidden": true
					}), "Find the best model"]
				})
			]
		})
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "max-w-[1400px] mx-auto px-4 py-6 grid gap-4",
		children: [search && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
			title: `Hardware-aware recommendations / ${search}`,
			aside: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "flex items-center gap-3",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: "live" }), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
					type: "button",
					onClick: () => setAttempt((value) => value + 1),
					className: "inline-flex items-center gap-1 text-[11px] text-primary hover:text-ink",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(RefreshCw, {
						className: "size-3",
						"aria-hidden": true
					}), " Refresh search"]
				})]
			}),
			bodyClassName: "p-0",
			children: recommendations.isLoading ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "px-4 py-12 text-center text-[13px] text-ink-secondary",
				children: "Searching Hugging Face's indexed catalog, enriching finalists, and scoring hardware fit..."
			}) : recommendations.unavailable ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "p-4",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
					endpoint: "/recommend",
					method: "POST",
					resource: "Hardware-aware Hugging Face recommendations",
					reason: recommendations.unavailable.message
				})
			}) : recommendations.error ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "px-4 py-8 text-[13px] text-error",
				children: recommendations.error.message
			}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(RecommendationTable, { rows: recommendations.data ?? [] })
		}), !search && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
			title: "Ready to discover",
			aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: "live" }),
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "px-4 py-10 text-center text-[13px] text-ink-secondary",
				children: "Select a workload category and start a fresh controller-backed discovery run."
			})
		})]
	})] });
}
function RecommendationTable({ rows }) {
	if (rows.length === 0) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "px-4 py-10 text-center text-[13px] text-ink-secondary",
		children: "No compatible candidates survived the current hardware and storage filters."
	});
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
		className: "divide-y divide-border",
		children: rows.map((row, index) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("li", {
			className: "px-4 py-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto]",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "min-w-0",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "flex flex-wrap items-center gap-2",
						children: [
							index === 0 && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Sparkles, {
								className: "size-4 text-primary",
								"aria-hidden": true
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "font-medium text-ink",
								children: row.artifact.displayName
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: row.provenance })
						]
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "mt-1 rift-mono text-[11px] text-ink-secondary",
						children: [
							row.artifact.id,
							" · ",
							row.artifact.format,
							" · ",
							row.backend.kind
						]
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "mt-2 max-w-3xl text-[12.5px] text-ink-secondary",
						children: row.rationale
					}),
					row.warnings.length > 0 && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "mt-2 text-[11.5px] text-attention",
						children: row.warnings.join(" · ")
					})
				]
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "grid grid-cols-3 gap-5 lg:min-w-[340px]",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Metric, {
						label: "Quality proxy",
						value: `${row.quality.score}/100`
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Metric, {
						label: "Download",
						value: bytes(row.resources.diskBytes)
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Metric, {
						label: "Target",
						value: row.targetNode
					})
				]
			})]
		}, row.id ?? row.artifact.id))
	});
}
function Metric({ label, value }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "rift-label",
		children: label
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "mt-1 rift-mono text-[12px] text-ink",
		children: value
	})] });
}
//#endregion
export { ModelsPage as component };
