import { c as __toESM, i as require_react, r as require_jsx_runtime, t as useRouter } from "./useRouter-C3Fl0Qct.js";
import { t as useStore } from "./useStore-BJu31CTG.js";
import { t as Link } from "./link-RSGdeuyI.js";
import { n as useStructuralSharing } from "./useMatch-dyXsb1Mw.js";
import { n as useQueryClient } from "./QueryClientProvider-D_537aby.js";
import { B as createLucideIcon, I as rift, L as cn, t as keys, z as Terminal } from "./hooks-DK2temI-.js";
//#region node_modules/@tanstack/react-router/dist/esm/useRouterState.js
/**
* Subscribe to the router's state store with optional selection and
* structural sharing for render optimization.
*
* Options:
* - `select`: Project the full router state to a derived slice
* - `structuralSharing`: Replace-equal semantics for stable references
* - `router`: Read state from a specific router instance instead of context
*
* @returns The selected router state (or the full state by default).
* @link https://tanstack.com/router/latest/docs/framework/react/api/router/useRouterStateHook
*/
function useRouterState(opts) {
	const contextRouter = useRouter({ warn: opts?.router === void 0 });
	const router = opts?.router || contextRouter;
	{
		const state = router.stores.__store.get();
		return opts?.select ? opts.select(state) : state;
	}
	return useStore(router.stores.__store, useStructuralSharing(opts, router));
}
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Activity = createLucideIcon("activity", [["path", {
	d: "M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2",
	key: "169zse"
}]]);
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Boxes = createLucideIcon("boxes", [
	["path", {
		d: "M2.97 12.92A2 2 0 0 0 2 14.63v3.24a2 2 0 0 0 .97 1.71l3 1.8a2 2 0 0 0 2.06 0L12 19v-5.5l-5-3-4.03 2.42Z",
		key: "lc1i9w"
	}],
	["path", {
		d: "m7 16.5-4.74-2.85",
		key: "1o9zyk"
	}],
	["path", {
		d: "m7 16.5 5-3",
		key: "va8pkn"
	}],
	["path", {
		d: "M7 16.5v5.17",
		key: "jnp8gn"
	}],
	["path", {
		d: "M12 13.5V19l3.97 2.38a2 2 0 0 0 2.06 0l3-1.8a2 2 0 0 0 .97-1.71v-3.24a2 2 0 0 0-.97-1.71L17 10.5l-5 3Z",
		key: "8zsnat"
	}],
	["path", {
		d: "m17 16.5-5-3",
		key: "8arw3v"
	}],
	["path", {
		d: "m17 16.5 4.74-2.85",
		key: "8rfmw"
	}],
	["path", {
		d: "M17 16.5v5.17",
		key: "k6z78m"
	}],
	["path", {
		d: "M7.97 4.42A2 2 0 0 0 7 6.13v4.37l5 3 5-3V6.13a2 2 0 0 0-.97-1.71l-3-1.8a2 2 0 0 0-2.06 0l-3 1.8Z",
		key: "1xygjf"
	}],
	["path", {
		d: "M12 8 7.26 5.15",
		key: "1vbdud"
	}],
	["path", {
		d: "m12 8 4.74-2.85",
		key: "3rx089"
	}],
	["path", {
		d: "M12 13.5V8",
		key: "1io7kd"
	}]
]);
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var CircleDot = createLucideIcon("circle-dot", [["circle", {
	cx: "12",
	cy: "12",
	r: "10",
	key: "1mglay"
}], ["circle", {
	cx: "12",
	cy: "12",
	r: "1",
	key: "41hilf"
}]]);
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var House = createLucideIcon("house", [["path", {
	d: "M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8",
	key: "5wwlr5"
}], ["path", {
	d: "M3 10a2 2 0 0 1 .709-1.528l7-6a2 2 0 0 1 2.582 0l7 6A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
	key: "r6nss1"
}]]);
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Layers = createLucideIcon("layers", [
	["path", {
		d: "M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83z",
		key: "zw3jo"
	}],
	["path", {
		d: "M2 12a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 12",
		key: "1wduqc"
	}],
	["path", {
		d: "M2 17a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 17",
		key: "kqbvx6"
	}]
]);
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Menu = createLucideIcon("menu", [
	["path", {
		d: "M4 5h16",
		key: "1tepv9"
	}],
	["path", {
		d: "M4 12h16",
		key: "1lakjw"
	}],
	["path", {
		d: "M4 19h16",
		key: "1djgab"
	}]
]);
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Package = createLucideIcon("package", [
	["path", {
		d: "M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z",
		key: "1a0edw"
	}],
	["path", {
		d: "M12 22V12",
		key: "d0xqtd"
	}],
	["polyline", {
		points: "3.29 7 12 12 20.71 7",
		key: "ousv84"
	}],
	["path", {
		d: "m7.5 4.27 9 5.15",
		key: "1c824w"
	}]
]);
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Server = createLucideIcon("server", [
	["rect", {
		width: "20",
		height: "8",
		x: "2",
		y: "2",
		rx: "2",
		ry: "2",
		key: "ngkwjq"
	}],
	["rect", {
		width: "20",
		height: "8",
		x: "2",
		y: "14",
		rx: "2",
		ry: "2",
		key: "iecqi9"
	}],
	["line", {
		x1: "6",
		x2: "6.01",
		y1: "6",
		y2: "6",
		key: "16zg32"
	}],
	["line", {
		x1: "6",
		x2: "6.01",
		y1: "18",
		y2: "18",
		key: "nzw8ys"
	}]
]);
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Settings2 = createLucideIcon("settings-2", [
	["path", {
		d: "M14 17H5",
		key: "gfn3mx"
	}],
	["path", {
		d: "M19 7h-9",
		key: "6i9tg"
	}],
	["circle", {
		cx: "17",
		cy: "17",
		r: "3",
		key: "18b49y"
	}],
	["circle", {
		cx: "7",
		cy: "7",
		r: "3",
		key: "dfmy0x"
	}]
]);
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
var WandSparkles = createLucideIcon("wand-sparkles", [
	["path", {
		d: "m21.64 3.64-1.28-1.28a1.21 1.21 0 0 0-1.72 0L2.36 18.64a1.21 1.21 0 0 0 0 1.72l1.28 1.28a1.2 1.2 0 0 0 1.72 0L21.64 5.36a1.2 1.2 0 0 0 0-1.72",
		key: "ul74o6"
	}],
	["path", {
		d: "m14 7 3 3",
		key: "1r5n42"
	}],
	["path", {
		d: "M5 6v4",
		key: "ilb8ba"
	}],
	["path", {
		d: "M19 14v4",
		key: "blhpug"
	}],
	["path", {
		d: "M10 2v2",
		key: "7u0qdc"
	}],
	["path", {
		d: "M7 8H3",
		key: "zfb6yr"
	}],
	["path", {
		d: "M21 16h-4",
		key: "1cnmox"
	}],
	["path", {
		d: "M11 3H9",
		key: "1obp7u"
	}]
]);
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var X = createLucideIcon("x", [["path", {
	d: "M18 6 6 18",
	key: "1bl5f8"
}], ["path", {
	d: "m6 6 12 12",
	key: "d8bk6v"
}]]);
//#endregion
//#region src/components/rift/app-shell.tsx
var import_react = /* @__PURE__ */ __toESM(require_react());
var import_jsx_runtime = require_jsx_runtime();
var NAV = [
	{
		to: "/",
		label: "Home",
		icon: House,
		exact: true
	},
	{
		to: "/deployments",
		label: "Deployments",
		icon: Boxes
	},
	{
		to: "/nodes",
		label: "Nodes",
		icon: Server
	},
	{
		to: "/models",
		label: "Models",
		icon: Package
	},
	{
		to: "/groups",
		label: "Groups",
		icon: Layers
	},
	{
		to: "/operations",
		label: "Operations",
		icon: Activity
	},
	{
		to: "/tuning",
		label: "Tuning",
		icon: SlidersHorizontal
	},
	{
		to: "/workloads",
		label: "Easy deploy",
		icon: WandSparkles
	},
	{
		to: "/settings",
		label: "Settings",
		icon: Settings2
	}
];
function AppShell({ children }) {
	const pathname = useRouterState({ select: (s) => s.location.pathname });
	const [stale, setStale] = (0, import_react.useState)(null);
	const [mobileOpen, setMobileOpen] = (0, import_react.useState)(false);
	const qc = useQueryClient();
	const connection = rift.connectionInfo();
	(0, import_react.useEffect)(() => {
		if (!rift.isConfigured()) {
			setStale(true);
			return;
		}
		return rift.subscribe((e) => {
			switch (e.kind) {
				case "health":
					qc.setQueryData(keys.health, e.health);
					break;
				case "node.enrolled":
				case "node.status":
					qc.invalidateQueries({ queryKey: keys.nodes });
					break;
				case "service.status":
					qc.invalidateQueries({ queryKey: keys.services });
					break;
				case "incident.opened":
				case "incident.resolved":
					qc.invalidateQueries({ queryKey: keys.incidents });
					break;
				case "plan.progress": break;
			}
		}, setStale);
	}, [qc]);
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "min-h-dvh flex flex-col bg-canvas",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("header", {
				className: "border-b border-border bg-raised",
				role: "banner",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "max-w-[1400px] mx-auto flex items-center gap-6 px-4 h-14",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Link, {
							to: "/",
							className: "flex items-center gap-2 font-mono text-[13px] tracking-[0.14em] font-medium text-ink",
							"aria-label": "RIFT home",
							children: [
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)(RiftMark, {}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: "RIFT" }),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
									className: "text-ink-secondary font-normal",
									children: "controller"
								})
							]
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("nav", {
							className: "hidden lg:flex items-center gap-0.5 ml-4",
							"aria-label": "Primary",
							children: NAV.map((item) => {
								const Icon = item.icon;
								const active = item.exact ? pathname === item.to : pathname === item.to || pathname.startsWith(item.to + "/");
								return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Link, {
									to: item.to,
									className: cn("px-3 h-9 inline-flex items-center gap-2 text-[13px] rounded-[4px] transition-colors", active ? "bg-muted text-ink font-medium" : "text-ink-secondary hover:text-ink hover:bg-muted"),
									children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Icon, {
										className: "size-3.5",
										"aria-hidden": true
									}), item.label]
								}, item.to);
							})
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "ml-auto flex items-center gap-3 text-[12px] rift-mono",
							children: [
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)(ControllerStatus, { stale }),
								/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
									type: "button",
									className: "hidden lg:inline-flex items-center gap-1.5 text-ink-secondary hover:text-ink",
									"aria-label": "Open CLI reference",
									children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Terminal, {
										className: "size-3.5",
										"aria-hidden": true
									}), " CLI"]
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
									type: "button",
									className: "lg:hidden inline-flex size-9 items-center justify-center rounded-[4px] border border-border text-ink-secondary hover:bg-muted hover:text-ink",
									"aria-label": mobileOpen ? "Close navigation" : "Open navigation",
									"aria-expanded": mobileOpen,
									onClick: () => setMobileOpen((open) => !open),
									children: mobileOpen ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(X, { className: "size-4" }) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Menu, { className: "size-4" })
								})
							]
						})
					]
				}), mobileOpen && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("nav", {
					className: "lg:hidden border-t border-border px-3 py-2 grid grid-cols-2 gap-1",
					"aria-label": "Mobile primary",
					children: NAV.map((item) => {
						const Icon = item.icon;
						const active = item.exact ? pathname === item.to : pathname === item.to || pathname.startsWith(item.to + "/");
						return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Link, {
							to: item.to,
							onClick: () => setMobileOpen(false),
							className: cn("h-9 px-3 inline-flex items-center gap-2 rounded-[4px] text-[13px]", active ? "bg-muted text-ink font-medium" : "text-ink-secondary hover:bg-muted"),
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Icon, {
								className: "size-3.5",
								"aria-hidden": true
							}), item.label]
						}, item.to);
					})
				})]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "border-b border-border bg-surface",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "max-w-[1400px] mx-auto min-h-7 px-4 py-1 flex flex-wrap items-center gap-x-3 gap-y-1 rift-mono text-[10.5px] text-ink-secondary",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
							className: "inline-flex items-center gap-1.5 text-secondary",
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "rift-dot !size-1.5",
								"aria-hidden": true
							}), "live controller data"]
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: connection.root }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "hidden sm:inline",
							children: "compatibility adapter"
						}),
						connection.previewEnabled && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "ml-auto text-attention",
							children: "preview-only surfaces are explicitly labeled"
						})
					]
				})
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("main", {
				className: "flex-1 min-w-0",
				role: "main",
				children
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("footer", {
				className: "border-t border-border bg-raised",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "max-w-[1400px] mx-auto px-4 h-9 flex items-center justify-between text-[11px] rift-mono text-ink-secondary",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: "RIFT · operator console" }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: "Controller binds locally by default" })]
				})
			})
		]
	});
}
function ControllerStatus({ stale }) {
	const state = stale === null ? "connecting" : stale ? "offline" : "live";
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
		className: cn("inline-flex items-center gap-1.5", stale === true ? "text-attention" : stale === null ? "text-ink-secondary" : "text-secondary"),
		title: stale === null ? "Connecting to the controller" : stale ? "Controller poll failed; retrying" : "Live controller polling",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(CircleDot, {
			className: "size-3.5",
			"aria-hidden": true
		}), state]
	});
}
function RiftMark() {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("svg", {
		width: "20",
		height: "20",
		viewBox: "0 0 20 20",
		"aria-hidden": true,
		className: "text-primary",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("path", {
			d: "M1 10 L4 10 L5.5 5 L7 15 L8.5 7 L10 13 L11.5 6 L13 14 L14.5 9 L16 11 L19 10",
			fill: "none",
			stroke: "currentColor",
			strokeWidth: "1.25",
			strokeLinecap: "square",
			strokeLinejoin: "miter"
		})
	});
}
//#endregion
//#region src/components/rift/primitives.tsx
function PageHeader({ eyebrow, title, description, actions }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "border-b border-border bg-surface",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "max-w-[1400px] mx-auto px-4 py-6 flex flex-wrap items-end justify-between gap-4",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "min-w-0",
				children: [
					eyebrow && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "rift-label mb-2",
						children: eyebrow
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h1", {
						className: "text-[22px] leading-tight font-medium text-ink",
						children: title
					}),
					description && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "mt-1.5 text-[13px] text-ink-secondary max-w-2xl",
						children: description
					})
				]
			}), actions && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "flex items-center gap-2",
				children: actions
			})]
		})
	});
}
function Panel({ title, aside, className, bodyClassName, children }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("section", {
		className: cn("rift-panel min-w-0 max-w-full", className),
		children: [title && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("header", {
			className: "flex items-center justify-between px-4 h-10 border-b border-border",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", {
				className: "rift-label",
				children: title
			}), aside]
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: cn("p-4", bodyClassName),
			children
		})]
	});
}
function StatDot({ tone }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
		className: cn("rift-dot", tone === "ok" ? "text-success" : tone === "attention" ? "text-attention" : tone === "error" ? "text-error" : tone === "info" ? "text-secondary" : "text-ink-muted"),
		"aria-hidden": true
	});
}
function KV({ label, value, mono = true }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "flex flex-col gap-1",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
			className: "rift-label",
			children: label
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
			className: cn("text-[13px] text-ink", mono && "rift-mono"),
			children: value
		})]
	});
}
function SourceBadge({ source }) {
	if (!source) return null;
	const label = source === "derived-live" ? "live / normalized" : source;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
		className: cn("inline-flex h-5 items-center rounded-[3px] border px-1.5 rift-mono text-[10px] uppercase", source === "preview" ? "border-attention/50 bg-attention/10 text-ink" : "border-secondary/40 bg-secondary/10 text-secondary"),
		children: label
	});
}
//#endregion
export { StatDot as a, Settings2 as c, SourceBadge as i, Layers as l, PageHeader as n, AppShell as o, Panel as r, SlidersHorizontal as s, KV as t, Activity as u };
