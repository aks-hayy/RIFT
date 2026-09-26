import { r as require_jsx_runtime } from "./useRouter-C3Fl0Qct.js";
import { R as cn, V as createLucideIcon } from "./hooks-BdOll_GY.js";
import { t as LoaderCircle } from "./loader-circle-BiAxPFL-.js";
import { t as RefreshCw } from "./refresh-cw-OthjuVPx.js";
import { t as TriangleAlert } from "./triangle-alert-j_feiOpk.js";
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var CircleSlash2 = createLucideIcon("circle-slash-2", [["circle", {
	cx: "12",
	cy: "12",
	r: "10",
	key: "1mglay"
}], ["path", {
	d: "M22 2 2 22",
	key: "y4kqgn"
}]]);
//#endregion
//#region src/lib/rift/live-state-state.ts
function resolveLiveState(input) {
	if (input.unsupported) return "unsupported";
	if (input.unavailable) return "unavailable";
	if (input.error) return "error";
	if (input.isLoading && !input.hasData) return "loading";
	if (!input.hasData || input.empty) return "empty";
	return "ready";
}
//#endregion
//#region src/components/rift/live-state.tsx
var import_jsx_runtime = require_jsx_runtime();
function LiveState({ children, className, title, loadingLabel = "Loading live data…", emptyTitle = "No data returned", emptyDescription = "The controller returned an empty result for this view.", reason, onRetry, ...input }) {
	const state = resolveLiveState(input);
	if (state === "ready") return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(import_jsx_runtime.Fragment, { children });
	const content = {
		loading: {
			icon: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(LoaderCircle, {
				className: "size-4 animate-spin text-primary motion-reduce:animate-none",
				"aria-hidden": true
			}),
			heading: title ?? "Loading",
			message: loadingLabel
		},
		empty: {
			icon: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(CircleSlash2, {
				className: "size-4 text-ink-muted",
				"aria-hidden": true
			}),
			heading: emptyTitle,
			message: emptyDescription
		},
		unavailable: {
			icon: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(TriangleAlert, {
				className: "size-4 text-attention",
				"aria-hidden": true
			}),
			heading: title ?? "Controller unavailable",
			message: reason ?? "RIFT did not return this resource. Check the controller connection and retry."
		},
		error: {
			icon: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(TriangleAlert, {
				className: "size-4 text-error",
				"aria-hidden": true
			}),
			heading: title ?? "Could not load data",
			message: reason ?? "The controller request failed. Existing measurements have not been replaced with estimates."
		},
		unsupported: {
			icon: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(CircleSlash2, {
				className: "size-4 text-ink-muted",
				"aria-hidden": true
			}),
			heading: title ?? "Not supported here",
			message: reason ?? "The selected service or backend does not advertise this capability."
		},
		ready: {
			icon: null,
			heading: "",
			message: ""
		}
	}[state];
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: cn("rift-live-state flex min-h-24 items-start gap-3 rounded-xl border border-border/70 bg-white/45 p-4 text-left", className),
		role: "status",
		"aria-live": "polite",
		"data-live-state": state,
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
			className: "mt-0.5 shrink-0",
			children: content.icon
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "min-w-0 flex-1",
			children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "text-[13px] font-medium text-ink",
					children: content.heading
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
					className: "mt-1 max-w-2xl text-[12.5px] leading-relaxed text-ink-secondary",
					children: content.message
				}),
				onRetry && state !== "loading" && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
					type: "button",
					onClick: onRetry,
					className: "mt-3 inline-flex h-8 items-center gap-2 rounded-lg border border-border/80 bg-white/75 px-3 text-[12px] font-medium text-ink transition-colors hover:border-primary/35 hover:text-primary",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(RefreshCw, {
						className: "size-3.5",
						"aria-hidden": true
					}), "Retry"]
				})
			]
		})]
	});
}
//#endregion
export { LiveState as t };
