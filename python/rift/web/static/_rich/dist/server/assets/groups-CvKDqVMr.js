import { c as __toESM, i as require_react, r as require_jsx_runtime } from "./useRouter-C3Fl0Qct.js";
import { a as StatDot, l as Layers, n as PageHeader, o as AppShell, r as Panel } from "./primitives-DeAXA1eZ.js";
import { L as rift, V as createLucideIcon, _ as useMeshServices, g as useMeshServiceGroups, l as useGatewayStatus } from "./hooks-BdOll_GY.js";
import { t as Unavailable } from "./unavailable-D_3mUZyv.js";
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Route = createLucideIcon("route", [
	["circle", {
		cx: "6",
		cy: "19",
		r: "3",
		key: "1kj8tv"
	}],
	["path", {
		d: "M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15",
		key: "1d8sl"
	}],
	["circle", {
		cx: "18",
		cy: "5",
		r: "3",
		key: "gq8acd"
	}]
]);
//#endregion
//#region src/routes/groups.tsx?tsr-split=component
var import_react = /* @__PURE__ */ __toESM(require_react());
var import_jsx_runtime = require_jsx_runtime();
function GroupsPage() {
	const groups = useMeshServiceGroups();
	const services = useMeshServices();
	const gateway = useGatewayStatus();
	const [ports, setPorts] = (0, import_react.useState)({});
	const [busy, setBusy] = (0, import_react.useState)(null);
	const servicesById = new Map((services.data ?? []).map((service) => [service.serviceId, service]));
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(AppShell, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(PageHeader, {
		eyebrow: "Mesh gateway organization",
		title: "Groups",
		description: "Gateway groups expose a stable entry point while RIFT routes requests across their model-backed services."
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "max-w-[1400px] mx-auto px-4 py-6 grid gap-4",
		children: groups.unavailable || services.unavailable ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
			endpoint: "/v2/mesh/service-groups",
			resource: "Mesh gateway groups"
		}) : groups.isLoading || services.isLoading ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
			title: "Gateway groups",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "p-4 text-[13px] text-ink-secondary",
				children: "Loading groups…"
			})
		}) : (groups.data ?? []).length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
			title: "Gateway groups",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "p-10 text-center text-[13px] text-ink-secondary",
				children: "No service groups configured yet."
			})
		}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "grid gap-4 md:grid-cols-2",
			children: (groups.data ?? []).map((group) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Panel, {
				title: group.groupId,
				aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(StatDot, { tone: "ok" }),
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "flex items-center gap-2 text-[12px] text-ink-secondary",
						children: [
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Route, {
								className: "size-3.5",
								"aria-hidden": true
							}),
							" ",
							group.gatewayPath ?? "no published path"
						]
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "mt-4 grid gap-2",
						children: group.serviceIds.map((serviceId) => {
							const service = servicesById.get(serviceId);
							return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
								className: "flex items-center justify-between border-t border-border pt-2 text-[13px]",
								children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
									className: "font-medium",
									children: serviceId
								}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
									className: "rift-mono text-[11px] text-ink-secondary",
									children: service ? `${service.modelId} · ${service.revision}` : "missing service"
								})]
							}, serviceId);
						})
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "mt-4 flex items-center gap-2 text-[11px] uppercase tracking-[0.12em] text-ink-secondary",
						children: [
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Layers, {
								className: "size-3.5",
								"aria-hidden": true
							}),
							" default: ",
							group.defaultService ?? group.serviceIds[0]
						]
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "mt-4 border-t border-border pt-3 grid gap-2",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "flex items-center justify-between text-[11px] uppercase tracking-[0.1em] text-ink-secondary",
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: "Main gateway route" }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "rift-mono",
								children: gateway.data?.status ?? "unknown"
							})]
						}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "flex flex-wrap items-center gap-2",
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
								"aria-label": `Dedicated port for ${group.groupId}`,
								value: ports[group.groupId] ?? "11736",
								onChange: (event) => setPorts((current) => ({
									...current,
									[group.groupId]: event.target.value
								})),
								className: "h-8 w-24 rounded-[4px] border border-border bg-transparent px-2 rift-mono text-[12px]",
								inputMode: "numeric"
							}), (() => {
								const listener = gateway.data?.groups?.find((item) => item.groupId === group.groupId);
								const running = listener?.status === "running" && listener.processAlive;
								return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
									type: "button",
									disabled: busy === group.groupId,
									onClick: async () => {
										setBusy(group.groupId);
										try {
											await rift.gatewayGroupAction(group.groupId, running ? "stop" : "start", running ? {} : { port: Number(ports[group.groupId] ?? 11736) });
											gateway.refetch();
										} finally {
											setBusy(null);
										}
									},
									className: "h-8 px-3 rounded-[4px] border border-border text-[12px] disabled:opacity-50",
									children: busy === group.groupId ? "Working…" : running ? "Stop dedicated listener" : "Start dedicated listener"
								});
							})()]
						})]
					})
				]
			}, group.groupId))
		})
	})] });
}
//#endregion
export { GroupsPage as component };
