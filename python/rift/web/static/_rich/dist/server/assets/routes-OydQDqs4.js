import { r as require_jsx_runtime } from "./useRouter-C_cgokP9.js";
import { t as Link } from "./link-DZw2_uJJ.js";
import { A as useTimeline, D as useServices, a as StatDot, f as useHealth, i as SourceBadge, k as useTelemetryLatest, n as PageHeader, o as AppShell, p as useIncidents, r as Panel, t as KV, y as useNodes } from "./primitives-D--W_sxj.js";
import { r as rift, s as createLucideIcon, t as Unavailable } from "./unavailable-vAsxbBwJ.js";
import { t as ArrowRight } from "./arrow-right-BNUEhhr1.js";
import { t as Plus } from "./plus-DrITkcwW.js";
import { n as pct, r as relativeTime, t as bytes } from "./format-gcr4F9Vx.js";
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Rocket = createLucideIcon("rocket", [
	["path", {
		d: "M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5",
		key: "qeys4"
	}],
	["path", {
		d: "M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09",
		key: "u4xsad"
	}],
	["path", {
		d: "M9 12a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.4 22.4 0 0 1-4 2z",
		key: "676m9"
	}],
	["path", {
		d: "M9 12H4s.55-3.03 2-4c1.62-1.08 5 .05 5 .05",
		key: "92ym6u"
	}]
]);
//#endregion
//#region src/routes/index.tsx?tsr-split=component
var import_jsx_runtime = require_jsx_runtime();
function HomePage() {
	if (!rift.isConfigured()) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(FirstRunGate, {});
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(AppShell, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(PageHeader, {
		eyebrow: "Overview",
		title: "Fleet",
		description: "What's running, where, how it's performing, and what needs attention.",
		actions: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Link, {
			to: "/setup",
			className: "inline-flex items-center gap-2 h-9 px-3.5 rounded-[4px] bg-primary text-primary-foreground text-[13px] font-medium hover:bg-[color:var(--oxide-deep)]",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Plus, {
				className: "size-4",
				"aria-hidden": true
			}), "Deploy a model"]
		})
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "max-w-[1400px] mx-auto px-4 py-6 grid gap-4 lg:grid-cols-3",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "lg:col-span-2 grid gap-4",
			children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(HealthPanel, {}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(FleetTelemetryPanel, {}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(ServicesPanel, {})
			]
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "grid gap-4",
			children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(IncidentsPanel, {}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(NodesPanel, {}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(RecentChangesPanel, {})
			]
		})]
	})] });
}
function FleetTelemetryPanel() {
	const { data, unavailable, isLoading } = useTelemetryLatest();
	if (unavailable) return null;
	if (isLoading && !data) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
		title: "Resource telemetry",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "text-[13px] text-ink-secondary",
			children: "Loading live resource telemetry…"
		})
	});
	const samples = data ?? [];
	const cpu = samples.map((item) => item.sample.cpuPercent).filter((item) => item != null);
	const gpuTemp = samples.map((item) => item.sample.gpuTemperatureC).filter((item) => item != null);
	const ram = samples.map((item) => item.sample.hostRamPressurePercent).filter((item) => item != null);
	const max = (items) => items.length ? Math.max(...items).toFixed(1) : "unavailable";
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
		title: "Resource telemetry",
		aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
			className: "rift-mono text-[11px] text-ink-secondary",
			children: "live · 2s"
		}),
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "grid grid-cols-2 gap-4 sm:grid-cols-4",
			children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
					label: "Host CPU peak",
					value: cpu.length ? `${max(cpu)}%` : "unavailable"
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
					label: "Host RAM pressure",
					value: ram.length ? `${max(ram)}%` : "unavailable"
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
					label: "GPU temperature",
					value: gpuTemp.length ? `${max(gpuTemp)}°C` : "unavailable"
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
					label: "Telemetry sources",
					value: `${samples.length} service${samples.length === 1 ? "" : "s"}`
				})
			]
		})
	});
}
function FirstRunGate() {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(AppShell, { children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "max-w-[1400px] mx-auto px-4 py-12",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "rift-panel p-8 max-w-2xl",
			children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "rift-label mb-3",
					children: "First run"
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h1", {
					className: "text-[24px] font-medium text-ink",
					children: "Set up RIFT"
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
					className: "mt-2 text-[13px] text-ink-secondary max-w-lg",
					children: "RIFT hasn't been connected to a controller yet. Start the guided setup to run on this computer or manage a cluster of nodes."
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "mt-5",
					children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Link, {
						to: "/setup",
						className: "inline-flex items-center gap-2 h-10 px-4 rounded-[4px] bg-primary text-primary-foreground text-[13px] font-medium hover:bg-[color:var(--oxide-deep)]",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Rocket, {
							className: "size-4",
							"aria-hidden": true
						}), "Start guided setup"]
					})
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "mt-8 rift-ticks",
					"aria-hidden": true
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", {
					className: "mt-4 text-[12px] rift-mono text-ink-secondary",
					children: [
						"Controller URL is configured via",
						" ",
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "text-ink",
							children: "VITE_RIFT_CONTROLLER_URL"
						}),
						". The controller binds to 127.0.0.1 by default."
					]
				})
			]
		})
	}) });
}
function HealthPanel() {
	const { data, unavailable, isLoading } = useHealth();
	if (unavailable) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
		endpoint: "/hardware",
		resource: "FleetHealth { nodesReady, servicesRunning, incidentsOpen, capacity }",
		hint: "The controller exposes live hardware and service health through the configured control API."
	});
	if (isLoading || !data) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
		title: "Health",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "text-[13px] text-ink-secondary",
			children: "Loading…"
		})
	});
	const nodesOk = data.nodesReady === data.nodesTotal;
	const svcsOk = data.servicesRunning === data.servicesTotal;
	const overall = data.incidentsOpen > 0 ? "error" : nodesOk && svcsOk ? "ok" : "attention";
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Panel, {
		title: "Fleet health",
		aside: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "flex items-center gap-2",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: data.provenance }), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
				className: "hidden sm:inline rift-mono text-[11px] text-ink-secondary",
				children: ["controller ", data.controllerVersion]
			})]
		}),
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "flex items-center gap-3 mb-4",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StatDot, { tone: overall }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "text-[15px] text-ink font-medium",
					children: overall === "ok" ? "All systems nominal" : overall === "attention" ? "Attention required" : "Incidents open"
				})]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "grid grid-cols-2 sm:grid-cols-4 gap-6",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
						label: "Nodes ready",
						value: `${data.nodesReady} / ${data.nodesTotal}`
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
						label: "Services running",
						value: `${data.servicesRunning} / ${data.servicesTotal}`
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
						label: "Open incidents",
						value: data.incidentsOpen
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
						label: "Updated",
						value: relativeTime(data.updatedAt)
					})
				]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "mt-6 grid sm:grid-cols-2 gap-4",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(CapacityBar, {
					label: "VRAM",
					used: data.capacity.vramUsedBytes,
					total: data.capacity.vramTotalBytes
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(CapacityBar, {
					label: "RAM",
					used: data.capacity.ramUsedBytes,
					total: data.capacity.ramTotalBytes
				})]
			})
		]
	});
}
function CapacityBar({ label, used, total }) {
	const p = pct(used, total);
	const tone = p > 90 ? "var(--error)" : p > 75 ? "var(--saffron)" : "var(--verdigris)";
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "flex items-center justify-between mb-1.5",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
			className: "rift-label",
			children: label
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
			className: "rift-mono text-[12px] text-ink",
			children: [
				bytes(used),
				" / ",
				bytes(total)
			]
		})]
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "h-1.5 bg-muted rounded-[2px] overflow-hidden",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "h-full",
			style: {
				width: `${p}%`,
				background: tone
			}
		})
	})] });
}
function ServicesPanel() {
	const { data, unavailable, isLoading } = useServices();
	if (unavailable) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
		endpoint: "/services",
		resource: "Service[] { id, name, status, artifactId, endpoint, assignments }"
	});
	if (isLoading || !data) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
		title: "Running models",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "text-[13px] text-ink-secondary",
			children: "Loading services..."
		})
	});
	const services = data;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
		title: "Running models",
		aside: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Link, {
			to: "/deployments",
			className: "text-[12px] text-primary inline-flex items-center gap-1 hover:underline",
			children: ["All deployments ", /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ArrowRight, {
				className: "size-3",
				"aria-hidden": true
			})]
		}),
		bodyClassName: "p-0",
		children: services.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "px-4 py-10 text-center",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
				className: "text-[13px] text-ink-secondary",
				children: "No services deployed yet."
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Link, {
				to: "/setup",
				className: "mt-3 inline-flex items-center gap-2 h-9 px-3.5 rounded-[4px] bg-primary text-primary-foreground text-[13px] font-medium hover:bg-[color:var(--oxide-deep)]",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Plus, {
					className: "size-4",
					"aria-hidden": true
				}), " Deploy a model"]
			})]
		}) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("table", {
			className: "w-full text-[13px]",
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
							children: "Status"
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
							className: "text-left px-4 font-normal",
							children: "Nodes"
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
							className: "text-left px-4 font-normal",
							children: "Endpoint"
						})
					]
				})
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("tbody", { children: services.map((s) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ServiceRow, { s }, s.id)) })]
		})
	});
}
function ServiceRow({ s }) {
	const tone = s.status === "running" ? "ok" : s.status === "degraded" ? "attention" : s.status === "failed" ? "error" : "info";
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
		className: "border-b border-border last:border-0 hover:bg-muted/50",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
				className: "px-4 py-2.5",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Link, {
					to: "/deployments/$id",
					params: { id: s.id },
					className: "text-ink hover:underline font-medium",
					children: s.name
				})
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
				className: "px-4",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
					className: "inline-flex items-center gap-2",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StatDot, { tone }),
						" ",
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "rift-mono text-[12px]",
							children: s.status
						})
					]
				})
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
				className: "px-4 rift-mono text-[12px]",
				children: s.assignments.length
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("td", {
				className: "px-4 rift-mono text-[12px] text-ink-secondary",
				children: [
					s.endpoint.scheme,
					"://",
					s.endpoint.bindAddress,
					":",
					s.endpoint.port,
					s.endpoint.path
				]
			})
		]
	});
}
function IncidentsPanel() {
	const { data, unavailable, isLoading } = useIncidents();
	if (unavailable) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
		endpoint: "/incidents",
		resource: "Incident[] { severity, status, title, nodeId?, serviceId? }"
	});
	if (isLoading || !data) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
		title: "Active incidents",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "text-[13px] text-ink-secondary",
			children: "Loading incidents..."
		})
	});
	const open = data.filter((i) => i.status !== "resolved");
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
		title: "Active incidents",
		children: open.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "text-[13px] text-ink-secondary flex items-center gap-2",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StatDot, { tone: "ok" }), " No open incidents."]
		}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
			className: "grid gap-2",
			children: open.slice(0, 5).map((i) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("li", {
				className: "flex items-start gap-2",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StatDot, { tone: i.severity === "critical" ? "error" : i.severity === "warning" ? "attention" : "info" }), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "min-w-0",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "text-[13px] text-ink truncate",
						children: i.title
					}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "text-[11.5px] rift-mono text-ink-secondary",
						children: relativeTime(i.openedAt)
					})]
				})]
			}, i.id))
		})
	});
}
function NodesPanel() {
	const { data, unavailable, isLoading } = useNodes();
	if (unavailable) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
		endpoint: "/hardware",
		resource: "RiftNode[] { hostname, status, accelerators[] }"
	});
	if (isLoading || !data) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
		title: "Nodes",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "text-[13px] text-ink-secondary",
			children: "Loading nodes..."
		})
	});
	const nodes = data;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
		title: "Nodes",
		aside: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Link, {
			to: "/nodes",
			className: "text-[12px] text-primary hover:underline inline-flex items-center gap-1",
			children: ["All ", /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ArrowRight, {
				className: "size-3",
				"aria-hidden": true
			})]
		}),
		children: nodes.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "text-[13px] text-ink-secondary",
			children: "No nodes enrolled."
		}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
			className: "grid gap-1.5 text-[13px]",
			children: nodes.slice(0, 6).map((n) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("li", {
				className: "flex items-center gap-2",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StatDot, { tone: n.status === "ready" ? "ok" : n.status === "offline" || n.status === "error" ? "error" : "attention" }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Link, {
						to: "/nodes/$id",
						params: { id: n.id },
						className: "hover:underline",
						children: n.hostname
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
						className: "ml-auto rift-mono text-[11.5px] text-ink-secondary",
						children: [
							n.accelerators.length,
							" GPU · ",
							bytes(n.ramBytes)
						]
					})
				]
			}, n.id))
		})
	});
}
function RecentChangesPanel() {
	const { data, unavailable, isLoading } = useTimeline();
	if (unavailable) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
		title: "Recent changes",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
			endpoint: "/timeline",
			resource: "Controller timeline events",
			reason: "The controller timeline is unavailable."
		})
	});
	const events = Array.isArray(data?.events) ? data.events : [];
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
		title: "Recent changes",
		aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: "live" }),
		children: isLoading ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
			className: "text-[13px] text-ink-secondary",
			children: "Loading timeline..."
		}) : events.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
			className: "text-[13px] text-ink-secondary",
			children: "No controller events recorded."
		}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("ol", {
			className: "grid gap-3",
			children: events.slice(0, 6).map((value, index) => {
				const event = value && typeof value === "object" ? value : {};
				const created = Number(event.created_unix_seconds ?? 0);
				return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("li", {
					className: "flex items-start gap-2",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StatDot, { tone: String(event.status) === "error" ? "error" : "info" }), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "min-w-0",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
							className: "text-[12.5px] text-ink truncate",
							children: String(event.event ?? "controller event").replaceAll("_", " ")
						}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "rift-mono text-[10.5px] text-ink-secondary",
							children: [event.service ? `${String(event.service)} · ` : "", created ? relativeTime((/* @__PURE__ */ new Date(created * 1e3)).toISOString()) : "time unavailable"]
						})]
					})]
				}, `${String(event.event)}-${created}-${index}`);
			})
		})
	});
}
//#endregion
export { HomePage as component };
