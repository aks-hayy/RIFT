import { r as require_jsx_runtime } from "./useRouter-C3Fl0Qct.js";
import { B as createLucideIcon } from "./hooks-DK2temI-.js";
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var TriangleAlert = createLucideIcon("triangle-alert", [
	["path", {
		d: "m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3",
		key: "wmoenq"
	}],
	["path", {
		d: "M12 9v4",
		key: "juzpu7"
	}],
	["path", {
		d: "M12 17h.01",
		key: "p32p05"
	}]
]);
//#endregion
//#region src/components/rift/unavailable.tsx
var import_jsx_runtime = require_jsx_runtime();
/**
* `Unavailable` — shown wherever a required RIFT controller endpoint is
* not reachable. Per spec: never silently substitute mock data. Instead
* we name the endpoint, method, and expected resource shape so operators
* can wire it up (or confirm the controller is offline).
*/
function Unavailable({ endpoint, method = "GET", resource, hint, reason }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "rift-surface p-5",
		role: "status",
		"aria-live": "polite",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "flex items-start gap-3",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(TriangleAlert, {
				className: "size-4 mt-0.5 text-attention shrink-0",
				"aria-hidden": true
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "min-w-0",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "rift-label mb-1 text-ink",
						children: "Data unavailable"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "text-[13px] text-ink-secondary max-w-xl",
						children: reason ?? "The controller endpoint required to render this view is not reachable."
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "mt-3 grid gap-1.5 text-[12.5px] rift-mono",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "flex gap-2",
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "text-ink-secondary w-16",
								children: "endpoint"
							}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
								className: "text-ink",
								children: [
									method,
									" ",
									endpoint
								]
							})]
						}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "flex gap-2",
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "text-ink-secondary w-16",
								children: "returns"
							}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "text-ink",
								children: resource
							})]
						})]
					}),
					hint && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "mt-3 text-[12px] text-ink-secondary max-w-xl",
						children: hint
					})
				]
			})]
		})
	});
}
//#endregion
export { TriangleAlert as n, Unavailable as t };
