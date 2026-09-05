import { i as require_react, r as require_jsx_runtime, s as __toESM } from "./useRouter-C_cgokP9.js";
import { t as Link } from "./link-DZw2_uJJ.js";
import { D as useServices, a as StatDot, n as PageHeader, o as AppShell, r as Panel, u as useDeploymentRecords } from "./primitives-D--W_sxj.js";
import { r as rift, s as createLucideIcon, t as Unavailable } from "./unavailable-vAsxbBwJ.js";
import { t as LoaderCircle } from "./loader-circle-DFyVsy-h.js";
import { t as Plus } from "./plus-DrITkcwW.js";
import { t as RotateCcw } from "./rotate-ccw-S4Bt286B.js";
import { t as Search } from "./search-CUmsEkpy.js";
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Play = createLucideIcon("play", [["path", {
	d: "M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z",
	key: "10ikf1"
}]]);
//#endregion
//#region src/routes/deployments.index.tsx?tsr-split=component
var import_react = /* @__PURE__ */ __toESM(require_react());
var import_jsx_runtime = require_jsx_runtime();
function DeploymentsListPage() {
	const { data, unavailable, isLoading } = useServices();
	const records = useDeploymentRecords();
	const [filter, setFilter] = (0, import_react.useState)("");
	const query = filter.trim().toLowerCase();
	const activeServices = (data ?? []).filter((service) => !query || `${service.name} ${service.artifactId} ${service.backendKind}`.toLowerCase().includes(query));
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(AppShell, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(PageHeader, {
		eyebrow: "Deployments",
		title: "Model services",
		description: "Every LLM service RIFT is running, across every node.",
		actions: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Link, {
			to: "/setup",
			className: "inline-flex items-center gap-2 h-9 px-3.5 rounded-[4px] bg-primary text-primary-foreground text-[13px] font-medium hover:bg-[color:var(--oxide-deep)]",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Plus, {
				className: "size-4",
				"aria-hidden": true
			}), " Deploy a model"]
		})
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "max-w-[1400px] mx-auto min-w-0 px-4 py-6 grid gap-4",
		children: [unavailable ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
			endpoint: "/services",
			resource: "Service[] { id, name, status, useCase, endpoint, assignments }"
		}) : isLoading || !data ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
			title: "Services",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "text-[13px] text-ink-secondary",
				children: "Loading services..."
			})
		}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
			bodyClassName: "p-0",
			title: `${activeServices.length} service${activeServices.length === 1 ? "" : "s"}`,
			aside: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "relative",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Search, {
					className: "size-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-ink-secondary",
					"aria-hidden": true
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
					type: "search",
					placeholder: "Filter",
					value: filter,
					onChange: (event) => setFilter(event.target.value),
					className: "h-7 pl-7 pr-2 rounded-[4px] border border-border bg-raised text-[12px] rift-mono w-40 focus:outline-none focus:border-primary"
				})]
			}),
			children: activeServices.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "px-4 py-14 text-center text-[13px] text-ink-secondary",
				children: "No services deployed. Start the guided setup to deploy one."
			}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
				className: "divide-y divide-border",
				children: activeServices.map((s) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("li", { children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Link, {
					to: "/deployments/$id",
					params: { id: s.id },
					className: "flex items-center gap-4 px-4 py-3 hover:bg-muted/50",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StatDot, { tone: s.status === "running" ? "ok" : s.status === "degraded" ? "attention" : s.status === "failed" ? "error" : "info" }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "min-w-0 flex-1",
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
								className: "text-[14px] text-ink font-medium",
								children: s.name
							}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
								className: "rift-mono text-[11.5px] text-ink-secondary truncate",
								children: [
									s.artifactId,
									" · ",
									s.backendKind,
									" · ",
									s.useCase
								]
							})]
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "hidden sm:block rift-mono text-[11.5px] text-ink-secondary text-right",
							children: [
								s.endpoint.scheme,
								"://",
								s.endpoint.bindAddress,
								":",
								s.endpoint.port
							]
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "rift-mono text-[11.5px] text-ink-secondary w-20 text-right",
							children: [
								s.assignments.length,
								" node",
								s.assignments.length === 1 ? "" : "s"
							]
						})
					]
				}) }, s.id))
			})
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SavedDeployments, {
			records: records.data ?? [],
			unavailable: records.unavailable !== null
		})]
	})] });
}
function SavedDeployments({ records, unavailable }) {
	const [confirming, setConfirming] = (0, import_react.useState)(null);
	const [launching, setLaunching] = (0, import_react.useState)(null);
	const [message, setMessage] = (0, import_react.useState)(null);
	const [error, setError] = (0, import_react.useState)(null);
	const launchAgain = async (record) => {
		setLaunching(record.deploymentId);
		setConfirming(null);
		setMessage(null);
		setError(null);
		try {
			const result = await rift.relaunchDeployment(record.deploymentId, { allowLaunch: true });
			if (result.applied === false) setError(String(result.reason ?? "The saved deployment could not be launched."));
			else setMessage(`${record.serviceName} relaunched through the saved configuration.`);
		} catch (reason) {
			setError(reason instanceof Error ? reason.message : String(reason));
		} finally {
			setLaunching(null);
		}
	};
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Panel, {
		title: "Saved deployments",
		aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
			className: "rift-mono text-[11px] text-ink-secondary",
			children: "reusable history"
		}),
		bodyClassName: "p-0",
		children: [unavailable ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "px-4 py-8 text-[13px] text-ink-secondary",
			children: "Saved deployment history is unavailable on this controller version."
		}) : records.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "px-4 py-8 text-[13px] text-ink-secondary",
			children: "Successful deployments will remain here after they are stopped or deleted."
		}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
			className: "divide-y divide-border",
			children: records.map((record) => {
				const modelName = String(record.model.selected_file ?? record.model.local_path ?? record.model.id ?? "model");
				const context = record.serving.context_length;
				return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("li", {
					className: "px-4 py-3",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "flex flex-wrap items-start gap-3",
						children: [
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StatDot, { tone: record.status === "ready" ? "ok" : record.status === "failed" ? "error" : "attention" }),
							/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
								className: "min-w-0 flex-1",
								children: [
									/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
										className: "flex flex-wrap items-center gap-2",
										children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
											className: "text-[13.5px] font-medium text-ink",
											children: record.displayName
										}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
											className: "rift-mono text-[10px] uppercase text-ink-secondary",
											children: record.status
										})]
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
										className: "mt-1 text-[12px] text-ink-secondary break-all",
										children: [
											modelName,
											" · ",
											record.backend.kind,
											record.backend.version ? ` ${record.backend.version}` : ""
										]
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
										className: "mt-1 rift-mono text-[10.5px] text-ink-secondary",
										children: [
											record.endpoint.openaiBase ?? record.endpoint.apiBase ?? "endpoint not recorded",
											context ? ` · context ${String(context)}` : "",
											record.relaunchCount ? ` · relaunched ${record.relaunchCount}x` : ""
										]
									})
								]
							}),
							confirming === record.deploymentId ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
								className: "flex flex-wrap items-center gap-2",
								children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
									type: "button",
									onClick: () => void launchAgain(record),
									disabled: launching !== null,
									className: "inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] bg-primary text-primary-foreground text-[12px] font-medium disabled:opacity-50",
									children: [launching === record.deploymentId ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(LoaderCircle, { className: "size-3.5 animate-spin" }) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Play, { className: "size-3.5" }), "Confirm launch"]
								}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
									type: "button",
									onClick: () => setConfirming(null),
									className: "h-8 px-2.5 rounded-[4px] border border-border text-[12px]",
									children: "Cancel"
								})]
							}) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
								type: "button",
								onClick: () => setConfirming(record.deploymentId),
								disabled: launching !== null,
								className: "inline-flex items-center gap-1.5 h-8 px-3 rounded-[4px] border border-border text-[12px] hover:bg-muted disabled:opacity-50",
								children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(RotateCcw, { className: "size-3.5" }), " Launch again"]
							})
						]
					}), confirming === record.deploymentId && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "mt-2 pl-6 rift-mono text-[10.5px] text-ink-secondary",
						children: "RIFT will revalidate the saved artifact and backend. This authorizes launch only; missing downloads or installs remain blocked."
					})]
				}, record.deploymentId);
			})
		}), (message || error) && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "border-t border-border px-4 py-2 rift-mono text-[11px]",
			role: error ? "alert" : void 0,
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: error ? "text-error" : "text-secondary",
				children: error ?? message
			})
		})]
	});
}
//#endregion
export { DeploymentsListPage as component };
