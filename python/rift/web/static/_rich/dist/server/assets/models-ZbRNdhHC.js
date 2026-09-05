import { i as require_react, r as require_jsx_runtime, s as __toESM } from "./useRouter-C_cgokP9.js";
import { D as useServices, a as StatDot, i as SourceBadge, n as PageHeader, o as AppShell, r as Panel, x as useRecommendations } from "./primitives-D--W_sxj.js";
import { t as Unavailable } from "./unavailable-vAsxbBwJ.js";
import { t as Search } from "./search-CUmsEkpy.js";
import { t as Sparkles } from "./sparkles-CCGMYJUA.js";
import { t as bytes } from "./format-gcr4F9Vx.js";
//#region src/routes/models.tsx?tsr-split=component
var import_react = /* @__PURE__ */ __toESM(require_react());
var import_jsx_runtime = require_jsx_runtime();
function ModelsPage() {
	const services = useServices();
	const [task, setTask] = (0, import_react.useState)("chat");
	const [search, setSearch] = (0, import_react.useState)(null);
	const recommendations = useRecommendations(search ? {
		useCase: search,
		source: "huggingface"
	} : null);
	const active = (services.data ?? []).map((service) => ({
		id: service.artifactId,
		displayName: service.details?.modelPath?.replace(/\\/g, "/").split("/").pop() || service.artifactId,
		family: "controller-managed",
		parameters: "from artifact metadata",
		source: "local",
		format: service.artifactId.toLowerCase().endsWith(".gguf") ? "gguf" : "hf",
		quantization: service.artifactId.toLowerCase().includes("q8") ? "q8_0" : "none",
		sizeBytes: 0,
		license: "see model card",
		trust: "community",
		provenance: "derived-live"
	}));
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(AppShell, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(PageHeader, {
		eyebrow: "Catalog",
		title: "Models",
		description: "See what is deployed now, then let RIFT discover and rank Hugging Face models for this machine. No repository ID is required.",
		actions: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "flex items-center gap-2",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("select", {
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
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
				type: "button",
				onClick: () => setSearch(task),
				className: "inline-flex h-9 items-center gap-2 rounded-[4px] bg-primary px-3.5 text-[13px] font-medium text-primary-foreground hover:bg-[color:var(--oxide-deep)]",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Search, {
					className: "size-4",
					"aria-hidden": true
				}), "Find the best model"]
			})]
		})
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "max-w-[1400px] mx-auto px-4 py-6 grid gap-4",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
				title: "Active artifacts",
				aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: "derived-live" }),
				bodyClassName: "p-0",
				children: services.unavailable ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "p-4",
					children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
						endpoint: "/services",
						resource: "Controller-managed services"
					})
				}) : services.isLoading || !services.data ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "px-4 py-10 text-center text-[13px] text-ink-secondary",
					children: "Loading managed artifacts..."
				}) : active.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "px-4 py-10 text-center text-[13px] text-ink-secondary",
					children: "No model artifacts are attached to a managed service."
				}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ArtifactTable, { artifacts: active })
			}),
			search && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
				title: `Hardware-aware recommendations / ${search}`,
				aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: "live" }),
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
			}),
			!search && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
				title: "Model discovery",
				aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: "live" }),
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "px-4 py-10 text-center text-[13px] text-ink-secondary",
					children: "Choose a task and start discovery. RIFT will show only live controller results; no catalog records are fabricated when the controller has no data."
				})
			})
		]
	})] });
}
function ArtifactTable({ artifacts }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "overflow-x-auto",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("table", {
			className: "w-full min-w-[720px] text-[13px]",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("thead", {
				className: "rift-label",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
					className: "border-b border-border",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
							className: "h-9 px-4 text-left font-normal",
							children: "Artifact"
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
							className: "px-4 text-left font-normal",
							children: "Format"
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
							className: "px-4 text-left font-normal",
							children: "Parameters"
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
							className: "px-4 text-left font-normal",
							children: "Size"
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
							className: "px-4 text-left font-normal",
							children: "Trust"
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
							className: "px-4 text-left font-normal",
							children: "Source"
						})
					]
				})
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("tbody", { children: artifacts.map((artifact) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
				className: "border-b border-border last:border-0",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("td", {
						className: "px-4 py-3",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
							className: "font-medium text-ink",
							children: artifact.displayName
						}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
							className: "rift-mono text-[10.5px] text-ink-secondary",
							children: artifact.id
						})]
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("td", {
						className: "px-4 rift-mono text-[12px]",
						children: [
							artifact.format,
							" / ",
							artifact.quantization
						]
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
						className: "px-4 rift-mono text-[12px]",
						children: artifact.parameters
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
						className: "px-4 rift-mono text-[12px]",
						children: artifact.sizeBytes ? bytes(artifact.sizeBytes) : "controller metadata pending"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
						className: "px-4",
						children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
							className: "inline-flex items-center gap-2",
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StatDot, { tone: artifact.trust === "verified" ? "ok" : "attention" }), artifact.trust]
						})
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
						className: "px-4",
						children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: artifact.provenance })
					})
				]
			}, artifact.id)) })]
		})
	});
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
