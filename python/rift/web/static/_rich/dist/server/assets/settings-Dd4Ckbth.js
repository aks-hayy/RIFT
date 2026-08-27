import { r as require_jsx_runtime } from "./useRouter-C_cgokP9.js";
import { t as useNavigate } from "./useNavigate-VOCCG6_j.js";
import { a as StatDot, i as SourceBadge, n as PageHeader, o as AppShell, r as Panel, s as useBackends, t as KV } from "./primitives-At99O-dv.js";
import { i as cn, r as rift, t as Unavailable } from "./unavailable-Dh9iADmt.js";
import { t as Route } from "./settings-D6ZnN4cI.js";
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
		id: "users",
		label: "Users"
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
				tab === "sources" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourcesPreview, {}),
				tab === "security" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SecurityTab, {}),
				tab === "policies" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
					endpoint: "/v1/settings/policies",
					resource: "Policy[] { id, scope, requiresConfirmation, allowedActions }",
					hint: "Policies replace multi-checkbox permission prompts with reusable rules."
				}),
				tab === "users" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
					endpoint: "/v1/settings/users",
					resource: "User[] { email, role, lastActiveAt }"
				}),
				tab === "integrations" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(BackendIntegrations, {})
			]
		})
	] });
}
function ControllerTab() {
	const connection = rift.connectionInfo();
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Panel, {
		title: "Controller",
		aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: "live" }),
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "grid sm:grid-cols-3 gap-4",
			children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
					label: "URL",
					value: connection.root
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
					label: "Adapter",
					value: connection.mode
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
					label: "Preview surfaces",
					value: connection.previewEnabled ? "enabled" : "disabled"
				})
			]
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", {
			className: "mt-4 text-[12.5px] text-ink-secondary max-w-2xl",
			children: [
				"The console uses the live legacy controller through a typed compatibility adapter. Set",
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
function SourcesPreview() {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Panel, {
		title: "Model sources / contract preview",
		aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: "preview" }),
		bodyClassName: "p-0",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "border-b border-border bg-attention/5 px-4 py-2 text-[11.5px] text-ink-secondary",
			children: "These rows demonstrate the future source registry. Credentials and verification are not wired yet."
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("ul", {
			className: "divide-y divide-border text-[13px]",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("li", {
				className: "flex items-center gap-3 px-4 py-3",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StatDot, { tone: "info" }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "font-medium text-ink",
						children: "Hugging Face Hub"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "rift-mono text-[11px] text-ink-secondary",
						children: "https://huggingface.co"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "ml-auto rift-mono text-[11px] text-attention",
						children: "preview"
					})
				]
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("li", {
				className: "flex items-center gap-3 px-4 py-3",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StatDot, { tone: "info" }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "font-medium text-ink",
						children: "Local model directory"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "rift-mono text-[11px] text-ink-secondary",
						children: ".rift/models"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "ml-auto rift-mono text-[11px] text-attention",
						children: "preview"
					})
				]
			})]
		})]
	});
}
function BackendIntegrations() {
	const { data, unavailable } = useBackends();
	if (unavailable) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
		endpoint: "/backends",
		resource: "Backend provider detection"
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
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("tbody", { children: providers.map(([name, value]) => {
					const provider = asRecord(value);
					const detection = asRecord(provider.detection);
					const gate = asRecord(provider.lifecycle_gate);
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
								children: String(detection.version ?? "--")
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
								className: "px-4 rift-mono text-[11px]",
								children: String(detection.license ?? "unknown")
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
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "grid gap-4",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
			title: "Enrollment tokens",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
				endpoint: "/v1/settings/tokens",
				resource: "EnrollmentToken[] { token (redacted), expiresAt, createdBy, usedAt? }",
				hint: "Tokens are one-time and expire. Never revealed after creation."
			})
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
			title: "Service API keys",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
				endpoint: "/v1/settings/api-keys",
				resource: "ApiKey[] { id, label, prefix, createdAt, lastUsedAt }",
				hint: "Only the key prefix is stored; the full value is shown once at creation and never again."
			})
		})]
	});
}
//#endregion
export { SettingsPage as component };
