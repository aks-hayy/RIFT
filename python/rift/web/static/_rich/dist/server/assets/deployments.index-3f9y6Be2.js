import { r as require_jsx_runtime } from "./useRouter-C_cgokP9.js";
import { t as Link } from "./link-DZw2_uJJ.js";
import { a as StatDot, n as PageHeader, o as AppShell, r as Panel, x as useServices } from "./primitives-At99O-dv.js";
import { t as Unavailable } from "./unavailable-Dh9iADmt.js";
import { t as Plus } from "./plus-DPEkU_Gm.js";
import { t as Search } from "./search-CKiKkti1.js";
//#region src/routes/deployments.index.tsx?tsr-split=component
var import_jsx_runtime = require_jsx_runtime();
function DeploymentsListPage() {
	const { data, unavailable, isLoading } = useServices();
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
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "max-w-[1400px] mx-auto px-4 py-6 grid gap-4",
		children: unavailable ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
			endpoint: "/v1/services",
			resource: "Service[] { id, name, status, useCase, endpoint, assignments }"
		}) : isLoading || !data ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
			title: "Services",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "text-[13px] text-ink-secondary",
				children: "Loading services..."
			})
		}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
			bodyClassName: "p-0",
			title: `${data.length} service${data.length === 1 ? "" : "s"}`,
			aside: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "relative",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Search, {
					className: "size-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-ink-secondary",
					"aria-hidden": true
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
					type: "search",
					placeholder: "Filter",
					className: "h-7 pl-7 pr-2 rounded-[4px] border border-border bg-raised text-[12px] rift-mono w-40 focus:outline-none focus:border-primary"
				})]
			}),
			children: data.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "px-4 py-14 text-center text-[13px] text-ink-secondary",
				children: "No services deployed. Start the guided setup to deploy one."
			}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
				className: "divide-y divide-border",
				children: data.map((s) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("li", { children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Link, {
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
		})
	})] });
}
//#endregion
export { DeploymentsListPage as component };
