import { r as require_jsx_runtime } from "./useRouter-C_cgokP9.js";
import { t as useNavigate } from "./useNavigate-VOCCG6_j.js";
import { S as useTimeline, a as StatDot, d as useLatestPlan, f as useLogs, i as SourceBadge, n as PageHeader, o as AppShell, r as Panel, u as useIncidents, v as useReports } from "./primitives-At99O-dv.js";
import { i as cn, t as Unavailable } from "./unavailable-Dh9iADmt.js";
import { r as relativeTime } from "./format-gcr4F9Vx.js";
import { t as Route } from "./operations-BVLCyD33.js";
//#region src/routes/operations.tsx?tsr-split=component
var import_jsx_runtime = require_jsx_runtime();
var TABS = [
	{
		id: "incidents",
		label: "Incidents"
	},
	{
		id: "rollouts",
		label: "Rollouts"
	},
	{
		id: "audit",
		label: "Audit log"
	},
	{
		id: "logs",
		label: "Fleet logs"
	},
	{
		id: "metrics",
		label: "Metrics"
	}
];
function OperationsPage() {
	const { tab } = Route.useSearch();
	const navigate = useNavigate({ from: "/operations" });
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(AppShell, { children: [
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)(PageHeader, {
			eyebrow: "Operations",
			title: "Fleet operations",
			description: "Incidents, rollouts, and everything that has happened."
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
				tab === "incidents" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(IncidentsTab, {}),
				tab === "rollouts" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(RolloutsTab, {}),
				tab === "audit" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(AuditTab, {}),
				tab === "logs" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(LogsTab, {}),
				tab === "metrics" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(MetricsTab, {})
			]
		})
	] });
}
function RolloutsTab() {
	const { data, unavailable, isLoading } = useLatestPlan();
	if (unavailable) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
		endpoint: "/plan",
		resource: "Latest read-only RIFT plan"
	});
	if (isLoading || !data) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
		title: "Latest rollout",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
			className: "text-[13px] text-ink-secondary",
			children: "Loading plan..."
		})
	});
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Panel, {
		title: "Latest rollout plan",
		aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: data.provenance }),
		bodyClassName: "p-0",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "grid grid-cols-2 gap-4 border-b border-border px-4 py-3 sm:grid-cols-4",
			children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Metric, {
					label: "Plan",
					value: data.hash.slice(0, 12)
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Metric, {
					label: "Service",
					value: data.serviceId
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Metric, {
					label: "Actions",
					value: String(data.actions.length)
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Metric, {
					label: "Apply",
					value: data.previewOnly ? "CLI guarded" : "available"
				})
			]
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
			className: "divide-y divide-border",
			children: data.actions.map((action) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("li", {
				className: "flex items-start gap-3 px-4 py-3",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StatDot, { tone: action.risk === "high" ? "error" : action.risk === "medium" ? "attention" : "info" }), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "min-w-0",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "text-[13px] text-ink",
						children: action.summary
					}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "rift-mono text-[10.5px] text-ink-secondary",
						children: [
							action.group,
							" · ",
							action.nodeId ?? "controller",
							" ·",
							" ",
							action.reversible ? "reversible" : "not reversible"
						]
					})]
				})]
			}, action.id))
		})]
	});
}
function AuditTab() {
	const { data, unavailable } = useTimeline();
	if (unavailable) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
		endpoint: "/timeline",
		resource: "Controller audit timeline"
	});
	const events = Array.isArray(data?.events) ? data.events : [];
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
		title: `${events.length} recent controller events`,
		aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: "live" }),
		bodyClassName: "p-0",
		children: events.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "px-4 py-12 text-center text-[13px] text-ink-secondary",
			children: "No events recorded."
		}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
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
								children: "Time"
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
								className: "px-4 text-left font-normal",
								children: "Event"
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
								className: "px-4 text-left font-normal",
								children: "Service"
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
								className: "px-4 text-left font-normal",
								children: "Node"
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
								className: "px-4 text-left font-normal",
								children: "Status"
							})
						]
					})
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("tbody", { children: events.map((value, index) => {
					const event = asRecord(value);
					const created = Number(event.created_unix_seconds ?? 0);
					return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
						className: "border-b border-border last:border-0",
						children: [
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
								className: "px-4 py-2 rift-mono text-[11px] text-ink-secondary",
								children: created ? relativeTime((/* @__PURE__ */ new Date(created * 1e3)).toISOString()) : "--"
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
								className: "px-4 rift-mono",
								children: String(event.event ?? "event").replaceAll("_", " ")
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
								className: "px-4 rift-mono text-ink-secondary",
								children: String(event.service ?? "--")
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
								className: "px-4 rift-mono text-ink-secondary",
								children: String(event.node ?? "--")
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
								className: "px-4",
								children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(StatDot, { tone: String(event.status) === "error" ? "error" : "info" })
							})
						]
					}, `${String(event.event)}-${created}-${index}`);
				}) })]
			})
		})
	});
}
function LogsTab() {
	const { data, unavailable } = useLogs();
	if (unavailable) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
		endpoint: "/logs",
		resource: "Bounded controller service logs"
	});
	const lines = Array.isArray(data?.lines) ? data.lines : typeof data?.text === "string" ? data.text.split(/\r?\n/) : [];
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
		title: "chat / latest log lines",
		aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: "live" }),
		bodyClassName: "p-0",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("pre", {
			className: "max-h-[560px] overflow-auto bg-[color:var(--ink)] px-4 py-3 rift-mono text-[11.5px] leading-5 text-[color:var(--surface)]",
			children: lines.length ? lines.map((line) => typeof line === "string" ? line : JSON.stringify(line)).join("\n") : "No log lines available."
		})
	});
}
function MetricsTab() {
	const { data, unavailable } = useReports();
	if (unavailable) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
		endpoint: "/reports",
		resource: "Benchmark and tuning reports"
	});
	const reports = Array.isArray(data?.reports) ? data.reports : [];
	const benchmarkCount = reports.filter((value) => String(asRecord(value).path ?? "").includes("benchmark")).length;
	const tuningCount = reports.filter((value) => String(asRecord(value).path ?? "").includes("tuning")).length;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "grid gap-4 sm:grid-cols-3",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
				title: "Reports",
				aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: "live" }),
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Metric, {
					label: "Total retained",
					value: String(reports.length)
				})
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
				title: "Benchmarks",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Metric, {
					label: "Runs",
					value: String(benchmarkCount)
				})
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
				title: "Tuning",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Metric, {
					label: "Runs",
					value: String(tuningCount)
				})
			})
		]
	});
}
function Metric({ label, value }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "rift-label",
		children: label
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "mt-1 rift-mono text-[13px] text-ink",
		children: value
	})] });
}
function asRecord(value) {
	return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}
function IncidentsTab() {
	const { data, unavailable } = useIncidents();
	if (unavailable) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
		endpoint: "/v1/incidents",
		resource: "Incident[] { severity, status, title, detail, recovery }"
	});
	const rows = data ?? [];
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
		title: `${rows.length} incident${rows.length === 1 ? "" : "s"}`,
		bodyClassName: "p-0",
		children: rows.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "px-4 py-14 text-center text-[13px] text-ink-secondary",
			children: "No incidents recorded."
		}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
			className: "divide-y divide-border",
			children: rows.map((i) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("li", {
				className: "px-4 py-3 flex items-start gap-3",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StatDot, { tone: i.severity === "critical" ? "error" : i.severity === "warning" ? "attention" : "info" }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "min-w-0 flex-1",
						children: [
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
								className: "text-[13.5px] text-ink font-medium",
								children: i.title
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
								className: "text-[12.5px] text-ink-secondary mt-0.5",
								children: i.detail
							}),
							i.recovery && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
								className: "rift-mono text-[11.5px] mt-1.5 text-secondary",
								children: [
									"recovery: ",
									i.recovery.automatic ? "auto — " : "",
									i.recovery.action
								]
							})
						]
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "rift-mono text-[11px] text-ink-secondary shrink-0 text-right",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { children: i.status }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { children: relativeTime(i.openedAt) })]
					})
				]
			}, i.id))
		})
	});
}
//#endregion
export { OperationsPage as component };
