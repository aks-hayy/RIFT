import { r as require_jsx_runtime } from "./useRouter-C_cgokP9.js";
import { t as useNavigate } from "./useNavigate-VOCCG6_j.js";
import { O as useSettings, a as StatDot, c as useBackends, f as useHealth, i as SourceBadge, n as PageHeader, o as AppShell, r as Panel, t as KV } from "./primitives-D--W_sxj.js";
import { i as cn, r as rift, t as Unavailable } from "./unavailable-vAsxbBwJ.js";
import { t as Route } from "./settings-zgkGtgIE.js";
//#region src/routes/settings.tsx?tsr-split=component
var import_jsx_runtime = require_jsx_runtime();
var TABS = [
	{
		id: "controller",
		label: "Controller"
	},
	{
		id: "sources",
		label: "Model sources"
	},
	{
		id: "security",
		label: "Security"
	},
	{
		id: "policies",
		label: "Policies"
	},
	{
		id: "integrations",
		label: "Integrations"
	}
];
function SettingsPage() {
	const { tab } = Route.useSearch();
	const navigate = useNavigate({ from: "/settings" });
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(AppShell, { children: [
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)(PageHeader, {
			eyebrow: "Settings",
			title: "Configuration"
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "border-b border-border bg-raised",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "max-w-[1400px] mx-auto px-4 flex overflow-x-auto",
				children: TABS.map((t) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
					onClick: () => navigate({
						search: { tab: t.id },
						replace: true
					}),
					className: cn("h-11 px-4 text-[13px] border-b-2 -mb-px whitespace-nowrap", tab === t.id ? "border-primary text-ink font-medium" : "border-transparent text-ink-secondary hover:text-ink"),
					children: t.label
				}, t.id))
			})
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "max-w-[1400px] mx-auto px-4 py-6 grid gap-4",
			children: [
				tab === "controller" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ControllerTab, {}),
				tab === "sources" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourcesTab, {}),
				tab === "security" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SecurityTab, {}),
				tab === "policies" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(PoliciesTab, {}),
				tab === "integrations" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(BackendIntegrations, {})
			]
		})
	] });
}
function ControllerTab() {
	const connection = rift.connectionInfo();
	const { data: health, unavailable, error, isLoading } = useHealth();
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Panel, {
		title: "Controller",
		aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: "live" }),
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "grid gap-4 sm:grid-cols-2 lg:grid-cols-4",
			children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
					label: "Status",
					value: unavailable || error ? "unavailable" : isLoading ? "checking" : health ? "live" : "unknown"
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
					label: "URL",
					value: connection.root
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
					label: "Compatibility",
					value: "live compatibility adapter"
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
					label: "Preview surfaces",
					value: connection.previewEnabled ? "enabled" : "disabled"
				})
			]
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", {
			className: "mt-4 max-w-2xl text-[12.5px] text-ink-secondary",
			children: [
				"This dashboard is connected to the live controller. The compatibility adapter translates the current controller API into the dashboard contract; preview surfaces are disabled. Set",
				" ",
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "rift-mono text-ink",
					children: "VITE_RIFT_CONTROLLER_URL"
				}),
				" only when the controller is not available through the same-origin proxy."
			]
		})]
	});
}
function SourcesTab() {
	const { data, unavailable, error } = useSettings();
	if (unavailable || error) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
		endpoint: "/v2/settings",
		resource: "SettingsSnapshot { modelSources, gateway, services, policies, mesh }",
		reason: unavailable?.detail ?? error?.message
	});
	const sources = Array.isArray(data?.modelSources.sources) ? data.modelSources.sources : [];
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
		title: "Model sources",
		aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: "live" }),
		bodyClassName: "p-0",
		children: sources.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "p-4 text-[13px] text-ink-secondary",
			children: "No model sources are configured."
		}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
			className: "divide-y divide-border text-[13px]",
			children: sources.map((entry, index) => {
				const source = asRecord(entry);
				return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("li", {
					className: "flex flex-wrap items-center gap-3 px-4 py-3",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StatDot, { tone: String(source.status ?? "unknown") === "ready" ? "ok" : "muted" }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "font-medium text-ink",
							children: String(source.id ?? "source")
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "rift-mono text-[11px] text-ink-secondary break-all",
							children: String(source.endpoint ?? source.path ?? "not specified")
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "ml-auto rift-mono text-[11px] text-ink-secondary",
							children: String(source.status ?? "unknown")
						})
					]
				}, String(source.id ?? index));
			})
		})
	});
}
function BackendIntegrations() {
	const { data, unavailable, error, isLoading } = useBackends();
	if (unavailable || error) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
		endpoint: "/backends",
		resource: "Backend provider detection",
		reason: unavailable?.detail ?? error?.message
	});
	if (isLoading) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
		title: "Backend integrations",
		aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: "live" }),
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
			className: "text-[13px] text-ink-secondary",
			children: "Loading backend providers..."
		})
	});
	const providers = data?.providers && typeof data.providers === "object" ? Object.entries(data.providers) : [];
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
		title: "Backend integrations",
		aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: "live" }),
		bodyClassName: "p-0",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "overflow-x-auto",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("table", {
				className: "w-full min-w-[680px] text-[12.5px]",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("thead", {
					className: "rift-label",
					children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
						className: "border-b border-border",
						children: [
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
								className: "h-9 px-4 text-left font-normal",
								children: "Provider"
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
								className: "px-4 text-left font-normal",
								children: "Detected"
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
								className: "px-4 text-left font-normal",
								children: "Version"
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
								className: "px-4 text-left font-normal",
								children: "License"
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
								className: "px-4 text-left font-normal",
								children: "Lifecycle gate"
							})
						]
					})
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("tbody", { children: providers.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("tr", { children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
					colSpan: 5,
					className: "px-4 py-10 text-center text-[13px] text-ink-secondary",
					children: "The live controller returned no backend providers."
				}) }) : providers.map(([name, value]) => {
					const provider = asRecord(value);
					const detection = asRecord(provider.detection);
					const gate = asRecord(provider.lifecycle_gate);
					const manifest = asRecord(provider.manifest);
					const available = detection.available === true;
					return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
						className: "border-b border-border last:border-0",
						children: [
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
								className: "px-4 py-3 font-medium text-ink",
								children: name
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
								className: "px-4",
								children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
									className: "inline-flex items-center gap-2",
									children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StatDot, { tone: available ? "ok" : "muted" }), available ? "yes" : "no"]
								})
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
								className: "px-4 rift-mono text-[11px] text-ink-secondary",
								children: String(detection.version ?? "not detected")
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
								className: "px-4 rift-mono text-[11px]",
								children: String(detection.license ?? manifest.license ?? "unknown")
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
								className: "px-4 rift-mono text-[11px] text-ink-secondary",
								children: String(gate.advertised_status ?? "unknown")
							})
						]
					}, name);
				}) })]
			})
		})
	});
}
function asRecord(value) {
	return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}
function SecurityTab() {
	const { data, unavailable, error } = useSettings();
	if (unavailable || error) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
		endpoint: "/v2/settings",
		resource: "SettingsSnapshot { gateway, mesh, policies }",
		reason: unavailable?.detail ?? error?.message
	});
	const gateway = data?.gateway ?? {};
	const mesh = data?.mesh ?? {};
	const securityWarnings = Array.isArray(gateway.security_warnings) ? gateway.security_warnings.map(String) : [];
	const corsOrigins = Array.isArray(gateway.cors_origins) ? gateway.cors_origins.map(String) : [];
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "grid gap-4",
		children: [
			securityWarnings.length === 0 && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "border border-ok/40 bg-ok/5 px-4 py-3 text-[12.5px] text-ink-secondary",
				children: "No active exposure warnings. The gateway is not running, is loopback-bound, and has no configured CORS origins."
			}),
			securityWarnings.length > 0 && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "border-2 border-error/60 bg-error/10 px-4 py-4 text-[13px] text-error",
				role: "alert",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "rift-label text-error",
						children: "Security warnings require operator attention"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
						className: "mt-2 grid gap-1 list-disc pl-4",
						children: securityWarnings.map((warning) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("li", { children: warning }, warning))
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "mt-3 text-[12px] text-error/90",
						children: "Restrict the gateway to loopback or configure trusted origins and API keys before exposing it to a network."
					})
				]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Panel, {
				title: "Gateway and credentials",
				aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: "live" }),
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "grid gap-4 sm:grid-cols-2 lg:grid-cols-4",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "Gateway",
							value: String(gateway.status ?? "not_started")
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "Process",
							value: gateway.process_alive === true ? "alive" : "not running"
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "Stored key records",
							value: String(gateway.key_count ?? 0)
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "API-key protection",
							value: String(gateway.api_key_protection ?? "not reported")
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "Bound host",
							value: String(gateway.bound_host ?? "not reported")
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "CORS origins",
							value: corsOrigins.length ? corsOrigins.join(", ") : "none configured"
						})
					]
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
					className: "mt-4 text-[12px] text-ink-secondary",
					children: "Secret values are never returned to the dashboard. Create or rotate keys through an explicit operator action."
				})]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
				title: "Mesh trust",
				aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: "live" }),
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "grid gap-4 sm:grid-cols-3",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "Controller",
							value: String(mesh.controller_id ?? "not initialized")
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "Managed nodes",
							value: String(mesh.managed_nodes ?? 0)
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "Enrollment",
							value: String(asRecord(mesh.enrollment_window).open === true ? "open" : "closed")
						})
					]
				})
			})
		]
	});
}
function PoliciesTab() {
	const { data, unavailable, error } = useSettings();
	if (unavailable || error) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
		endpoint: "/v2/settings",
		resource: "SettingsSnapshot { policies, services }",
		reason: unavailable?.detail ?? error?.message
	});
	const policies = data?.policies ?? {};
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
		title: "Effective policy",
		aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: "live" }),
		children: Object.keys(policies).length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
			className: "text-[13px] text-ink-secondary",
			children: "The live controller returned no effective policies."
		}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "grid gap-3 text-[13px]",
			children: Object.entries(policies).map(([key, value]) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "flex flex-wrap items-center justify-between gap-3 border-b border-border pb-2 last:border-0",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "text-ink-secondary",
					children: key.replaceAll("_", " ")
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "rift-mono text-ink",
					children: String(value)
				})]
			}, key))
		})
	});
}
//#endregion
export { SettingsPage as component };
