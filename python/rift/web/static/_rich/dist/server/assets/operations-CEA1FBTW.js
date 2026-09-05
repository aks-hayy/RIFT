import { i as require_react, r as require_jsx_runtime, s as __toESM } from "./useRouter-C_cgokP9.js";
import { t as useNavigate } from "./useNavigate-VOCCG6_j.js";
import { A as useTimeline, C as useResourceReports, S as useReports, a as StatDot, b as useOperations, h as useLogs, i as SourceBadge, m as useLatestPlan, n as PageHeader, o as AppShell, p as useIncidents, r as Panel } from "./primitives-D--W_sxj.js";
import { i as cn, r as rift, t as Unavailable } from "./unavailable-vAsxbBwJ.js";
import { r as relativeTime } from "./format-gcr4F9Vx.js";
import { t as Route } from "./operations-CyuGU5ab.js";
//#region src/routes/operations.tsx?tsr-split=component
var import_react = /* @__PURE__ */ __toESM(require_react());
var import_jsx_runtime = require_jsx_runtime();
var TABS = [
	{
		id: "operations",
		label: "Operations"
	},
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
			className: "max-w-[1400px] mx-auto min-w-0 px-4 py-6 grid gap-4",
			children: [
				tab === "operations" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(OperationsTab, {}),
				tab === "incidents" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(IncidentsTab, {}),
				tab === "rollouts" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(RolloutsTab, {}),
				tab === "audit" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(AuditTab, {}),
				tab === "logs" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(LogsTab, {}),
				tab === "metrics" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(MetricsTab, {})
			]
		})
	] });
}
function OperationsTab() {
	const { data, unavailable, error, isLoading, refetch } = useOperations();
	const [cancelling, setCancelling] = (0, import_react.useState)(null);
	if (unavailable || error) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
		endpoint: "/v2/operations",
		resource: "Durable operations",
		reason: unavailable?.detail ?? error?.message
	});
	const operations = data ?? [];
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
		title: `${operations.length} durable operation${operations.length === 1 ? "" : "s"}`,
		aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: "live" }),
		bodyClassName: "p-0",
		children: isLoading ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "px-4 py-12 text-center text-[13px] text-ink-secondary",
			children: "Loading operations..."
		}) : operations.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "px-4 py-12 text-center text-[13px] text-ink-secondary",
			children: "No controller operations have been recorded."
		}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "overflow-x-auto",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("table", {
				className: "w-full min-w-[860px] text-[12.5px]",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("thead", {
					className: "rift-label",
					children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
						className: "border-b border-border",
						children: [
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
								className: "h-9 px-4 text-left font-normal",
								children: "Operation"
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
								className: "px-4 text-left font-normal",
								children: "Action"
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
								className: "px-4 text-left font-normal",
								children: "Stage"
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
								className: "px-4 text-left font-normal",
								children: "Progress"
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
								className: "px-4 text-left font-normal",
								children: "Updated"
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
								className: "px-4 text-right font-normal",
								children: "Control"
							})
						]
					})
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("tbody", { children: operations.map((operation) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)(OperationRow, {
					operation,
					cancelling: cancelling === operation.operationId,
					onCancel: async () => {
						setCancelling(operation.operationId);
						try {
							await rift.cancelOperation(operation.operationId);
							refetch();
						} finally {
							setCancelling(null);
						}
					}
				}, operation.operationId)) })]
			})
		})
	});
}
function OperationRow({ operation, cancelling, onCancel }) {
	const active = operation.status === "RUNNING";
	const [expanded, setExpanded] = (0, import_react.useState)(false);
	const hasDetails = Boolean(operation.error || operation.details || operation.result);
	const tone = operation.status === "FAILED" || operation.status === "INTERRUPTED" ? "error" : active ? "attention" : "ok";
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_react.Fragment, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
		className: "border-b border-border last:border-0",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
				className: "px-4 py-3 rift-mono text-[11px] text-ink break-all",
				children: operation.operationId
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("td", {
				className: "px-4 py-3 rift-mono text-[11px] text-ink-secondary break-all",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { children: operation.action }), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "mt-1 text-[10px] text-ink-secondary",
					children: ["request ", operation.requestId]
				})]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("td", {
				className: "px-4 py-3",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
					className: "inline-flex items-center gap-2",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StatDot, { tone }), operation.stage]
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "block mt-1 text-[11px] text-ink-secondary max-w-[280px]",
					children: operation.message
				})]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
				className: "px-4 py-3 rift-mono text-[11px]",
				children: operation.percent == null ? "indeterminate" : `${Math.round(operation.percent)}%`
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
				className: "px-4 py-3 rift-mono text-[11px] text-ink-secondary",
				children: relativeTime(operation.updatedAt)
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
				className: "px-4 py-3 text-right",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "flex items-center justify-end gap-2",
					children: [hasDetails && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
						type: "button",
						"aria-expanded": expanded,
						onClick: () => setExpanded((value) => !value),
						className: "h-7 px-2.5 rounded-[4px] border border-border text-[11px] hover:bg-muted",
						children: expanded ? "Hide details" : "Details"
					}), active ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
						type: "button",
						onClick: () => void onCancel(),
						disabled: cancelling,
						className: "h-7 px-2.5 rounded-[4px] border border-error/40 text-error text-[11px] hover:bg-error/10 disabled:opacity-50",
						children: cancelling ? "Cancelling..." : "Cancel"
					}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "rift-mono text-[11px] text-ink-secondary",
						children: operation.status.toLowerCase()
					})]
				})
			})
		]
	}), expanded && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("tr", {
		className: "border-b border-border bg-muted/20",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
			colSpan: 6,
			className: "px-4 py-3",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "grid gap-2 text-[11px]",
				children: [
					operation.error && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "border-l-2 border-error pl-3",
						role: "alert",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
							className: "rift-label text-error",
							children: "Failure"
						}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
							className: "mt-1 text-error break-words",
							children: operation.error
						})]
					}),
					operation.details && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "rift-label",
						children: "Stage details"
					}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("pre", {
						className: "mt-1 overflow-x-auto whitespace-pre-wrap rift-mono text-ink-secondary",
						children: JSON.stringify(operation.details, null, 2)
					})] }),
					operation.result && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "rift-label",
						children: "Result"
					}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("pre", {
						className: "mt-1 max-h-52 overflow-auto whitespace-pre-wrap rift-mono text-ink-secondary",
						children: JSON.stringify(operation.result, null, 2)
					})] })
				]
			})
		})
	})] });
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
	const resourceReports = useResourceReports();
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
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
				title: "Resource reports",
				className: "sm:col-span-3",
				aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: "live" }),
				bodyClassName: "p-0",
				children: resourceReports.data?.length ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "overflow-x-auto",
					children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("table", {
						className: "w-full min-w-[700px] text-[12px] rift-mono",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("thead", {
							className: "rift-label",
							children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
								className: "border-b border-border",
								children: [
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-left px-4 h-9 font-normal",
										children: "Service"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-left px-4 font-normal",
										children: "Node"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-left px-4 font-normal",
										children: "Duration"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-left px-4 font-normal",
										children: "Samples"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-left px-4 font-normal",
										children: "GPU energy"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-left px-4 font-normal",
										children: "Status"
									})
								]
							})
						}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("tbody", { children: resourceReports.data.map((report) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
							className: "border-b border-border last:border-0",
							children: [
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-4 py-2",
									children: report.serviceName
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-4",
									children: report.nodeId
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("td", {
									className: "px-4",
									children: [report.durationSeconds.toFixed(1), "s"]
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-4",
									children: report.sampleCount
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-4",
									children: report.costs?.energyJoules == null ? "unavailable" : `${report.costs.energyJoules.toFixed(1)} J`
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-4",
									children: "completed"
								})
							]
						}, report.reportId)) })]
					})
				}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "px-4 py-8 text-[13px] text-ink-secondary",
					children: "No completed resource reports yet."
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
		endpoint: "/incidents",
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
