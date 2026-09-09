import { r as require_jsx_runtime } from "./useRouter-C_cgokP9.js";
import { a as StatDot, b as useMeshServices, n as PageHeader, o as AppShell, r as Panel, y as useMeshServiceGroups, z as Layers } from "./primitives-Cc4n31Rd.js";
import { s as createLucideIcon, t as Unavailable } from "./unavailable-z8_2XgY7.js";
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
var import_jsx_runtime = require_jsx_runtime();
function GroupsPage() {
	const groups = useMeshServiceGroups();
	const services = useMeshServices();
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
					})
				]
			}, group.groupId))
		})
	})] });
}
//#endregion
export { GroupsPage as component };
