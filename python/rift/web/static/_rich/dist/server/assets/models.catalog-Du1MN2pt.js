import { r as require_jsx_runtime } from "./useRouter-C3Fl0Qct.js";
import { t as Link } from "./link-RSGdeuyI.js";
import { a as StatDot, i as SourceBadge, n as PageHeader, o as AppShell, r as Panel } from "./primitives-DeAXA1eZ.js";
import { V as createLucideIcon, p as useLocalArtifacts } from "./hooks-BdOll_GY.js";
import { t as LiveState } from "./live-state-CbJ8u5Rw.js";
import { t as RefreshCw } from "./refresh-cw-OthjuVPx.js";
import { t as bytes } from "./format-gcr4F9Vx.js";
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var PackageSearch = createLucideIcon("package-search", [
	["path", {
		d: "M21 10V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l2-1.14",
		key: "e7tb2h"
	}],
	["path", {
		d: "m7.5 4.27 9 5.15",
		key: "1c824w"
	}],
	["polyline", {
		points: "3.29 7 12 12 20.71 7",
		key: "ousv84"
	}],
	["line", {
		x1: "12",
		x2: "12",
		y1: "22",
		y2: "12",
		key: "a4e8g8"
	}],
	["circle", {
		cx: "18.5",
		cy: "15.5",
		r: "2.5",
		key: "b5zd12"
	}],
	["path", {
		d: "M20.27 17.27 22 19",
		key: "1l4muz"
	}]
]);
//#endregion
//#region src/routes/models.catalog.tsx?tsr-split=component
var import_jsx_runtime = require_jsx_runtime();
function LocalArtifactCatalogPage() {
	const artifacts = useLocalArtifacts();
	const rows = artifacts.data ?? [];
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(AppShell, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(PageHeader, {
		eyebrow: "Models / local inventory",
		title: "Local artifact catalog",
		description: "Artifacts registered in RIFT’s local manifest store. This view does not scan arbitrary folders or invent metadata.",
		actions: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "flex gap-2",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
				type: "button",
				onClick: artifacts.refetch,
				className: "inline-flex h-9 items-center gap-2 rounded-xl border border-border bg-white/70 px-3 text-[12px] font-medium hover:border-primary/35",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(RefreshCw, {
					className: "size-3.5",
					"aria-hidden": true
				}), " Refresh"]
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Link, {
				to: "/models",
				className: "inline-flex h-9 items-center rounded-xl bg-primary px-3.5 text-[12px] font-medium text-primary-foreground",
				children: "Discover models"
			})]
		})
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "mx-auto grid max-w-[1400px] gap-4 px-4 py-6",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Panel, {
			title: "Registered artifacts",
			aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: "live" }),
			bodyClassName: "p-0",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "p-4",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(LiveState, {
					isLoading: artifacts.isLoading,
					hasData: artifacts.data !== void 0,
					unavailable: !!artifacts.unavailable,
					error: !!artifacts.error,
					empty: rows.length === 0,
					title: "Local artifact inventory unavailable",
					loadingLabel: "Reading RIFT’s artifact manifests…",
					emptyTitle: "No registered artifacts",
					emptyDescription: "No persisted artifact manifests were returned by the controller. Deployments and cached files are not inferred as catalog records.",
					reason: artifacts.unavailable?.message ?? artifacts.error?.message,
					onRetry: artifacts.refetch,
					children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", {
						className: "text-[12px] text-ink-secondary",
						children: [
							rows.length,
							" manifest",
							rows.length === 1 ? "" : "s",
							" returned by the local controller."
						]
					})
				})
			}), rows.length > 0 && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "overflow-x-auto border-t border-border/70",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("table", {
					className: "w-full min-w-[780px] text-[12.5px]",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("thead", {
						className: "rift-label",
						children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
							className: "border-b border-border",
							children: [
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
									className: "h-10 px-4 text-left font-normal",
									children: "Artifact"
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
									className: "px-4 text-left font-normal",
									children: "Format / quantization"
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
									className: "px-4 text-right font-normal",
									children: "Model size"
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
									className: "px-4 text-left font-normal",
									children: "Integrity evidence"
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
									className: "px-4 text-left font-normal",
									children: "License"
								})
							]
						})
					}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("tbody", { children: rows.map((artifact) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
						className: "border-b border-border/70 last:border-0 hover:bg-white/35",
						children: [
							/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("td", {
								className: "px-4 py-3",
								children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
									className: "flex items-center gap-2 font-medium text-ink",
									children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(PackageSearch, {
										className: "size-4 text-primary",
										"aria-hidden": true
									}), artifact.displayName]
								}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
									className: "mt-1 rift-mono text-[10px] text-ink-muted",
									children: ["manifest ", artifact.id]
								})]
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("td", {
								className: "px-4 rift-mono text-[11px] text-ink-secondary",
								children: [
									artifact.format,
									" · ",
									artifact.quantization || "quantization not reported"
								]
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
								className: "px-4 text-right rift-mono text-[11px]",
								children: artifact.sizeBytes ? bytes(artifact.sizeBytes) : "not reported"
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
								className: "px-4",
								children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
									className: "inline-flex items-center gap-2",
									children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StatDot, { tone: artifact.trust === "verified" ? "ok" : "attention" }), artifact.trust === "verified" ? "model file hashes verified" : "hash verification not established"]
								})
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
								className: "px-4 text-[11px] text-ink-secondary",
								children: artifact.license
							})
						]
					}, artifact.id)) })]
				})
			})]
		})
	})] });
}
//#endregion
export { LocalArtifactCatalogPage as component };
