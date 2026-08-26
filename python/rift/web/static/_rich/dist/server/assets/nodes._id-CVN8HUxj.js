import { r as require_jsx_runtime } from "./useRouter-C_cgokP9.js";
import { t as useNavigate } from "./useNavigate-VOCCG6_j.js";
import { a as StatDot, h as useNode, i as SourceBadge, n as PageHeader, o as AppShell, r as Panel, t as KV } from "./primitives-At99O-dv.js";
import { i as cn, t as Unavailable } from "./unavailable-Dh9iADmt.js";
import { n as pct, r as relativeTime, t as bytes } from "./format-gcr4F9Vx.js";
import { t as Route } from "./nodes._id-DeoMDpHR.js";
//#region src/routes/nodes.$id.tsx?tsr-split=component
var import_jsx_runtime = require_jsx_runtime();
var TABS = [
	{
		id: "hardware",
		label: "Hardware"
	},
	{
		id: "assignments",
		label: "Assignments"
	},
	{
		id: "backends",
		label: "Backends"
	},
	{
		id: "cache",
		label: "Model cache"
	},
	{
		id: "health",
		label: "Health"
	},
	{
		id: "diagnostics",
		label: "Diagnostics"
	}
];
function NodeDetail() {
	const { id } = Route.useParams();
	const { tab } = Route.useSearch();
	const navigate = useNavigate({ from: "/nodes/$id" });
	const { data: node, unavailable } = useNode(id);
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(AppShell, { children: [
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)(PageHeader, {
			eyebrow: "Node",
			title: node?.hostname ?? id,
			description: node ? `${node.role} · ${node.os} ${node.arch} · agent ${node.version}` : void 0,
			actions: node && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
				className: "inline-flex items-center gap-2 rift-mono text-[12px]",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StatDot, { tone: node.status === "ready" ? "ok" : node.status === "offline" || node.status === "error" ? "error" : "attention" }), node.status]
			})
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
				unavailable && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
					endpoint: `/v1/nodes/${id}`,
					resource: "RiftNode"
				}),
				node && tab === "hardware" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(HardwareTab, { n: node }),
				tab === "assignments" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
					endpoint: `/v1/nodes/${id}/assignments`,
					resource: "Assignment[] { serviceId, gpuIndices, reservedVramBytes }"
				}),
				node && tab === "backends" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(BackendsTab, { n: node }),
				tab === "cache" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
					endpoint: `/v1/nodes/${id}/artifacts`,
					resource: "CachedArtifact[] { artifactId, sizeBytes, sha256, lastUsedAt }"
				}),
				node && tab === "health" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(HealthTab, { n: node }),
				tab === "diagnostics" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
					endpoint: `/v1/nodes/${id}/diagnostics`,
					method: "POST",
					resource: "DiagnosticsBundle { url, expiresAt }",
					hint: "Bundle should include driver info, kernel, dmesg tail, backend logs."
				})
			]
		})
	] });
}
function HardwareTab({ n }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "grid gap-4 lg:grid-cols-3",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "lg:col-span-2 grid gap-4",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
				title: "Accelerators",
				aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: n.provenance }),
				bodyClassName: "p-0",
				children: n.accelerators.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "px-4 py-8 text-[13px] text-ink-secondary text-center",
					children: "No accelerators detected — CPU inference only."
				}) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("table", {
					className: "w-full text-[13px]",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("thead", {
						className: "rift-label",
						children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
							className: "border-b border-border",
							children: [
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
									className: "text-left px-4 h-9 font-normal",
									children: "#"
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
									className: "text-left px-4 font-normal",
									children: "Vendor"
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
									className: "text-left px-4 font-normal",
									children: "Model"
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
									className: "text-left px-4 font-normal",
									children: "VRAM used"
								})
							]
						})
					}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("tbody", { children: n.accelerators.map((a) => {
						const used = a.vramBytes - a.vramFreeBytes;
						return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
							className: "border-b border-border last:border-0",
							children: [
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-4 py-2.5 rift-mono",
									children: a.index
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-4 rift-mono text-[12px] uppercase",
									children: a.vendor
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-4",
									children: a.name
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-4",
									children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
										className: "flex items-center gap-2",
										children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
											className: "w-24 h-1.5 bg-muted rounded-[2px] overflow-hidden",
											children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
												className: "h-full bg-secondary",
												style: { width: `${pct(used, a.vramBytes)}%` }
											})
										}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
											className: "rift-mono text-[11.5px] text-ink-secondary",
											children: [
												bytes(used),
												" / ",
												bytes(a.vramBytes)
											]
										})]
									})
								})
							]
						}, a.index);
					}) })]
				})
			})
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "grid gap-4",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
				title: "System",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "grid gap-3",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "OS",
							value: `${n.os} ${n.arch}`
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "RAM",
							value: `${bytes(n.ramBytes - n.ramFreeBytes)} / ${bytes(n.ramBytes)}`
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "Disk",
							value: `${bytes(n.diskBytes - n.diskFreeBytes)} / ${bytes(n.diskBytes)}`
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "Enrolled",
							value: relativeTime(n.enrolledAt)
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
							label: "Address",
							value: n.address
						})
					]
				})
			})
		})]
	});
}
function HealthTab({ n }) {
	const telemetry = n.telemetry;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "grid gap-4 lg:grid-cols-3",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
			title: "Observed telemetry",
			aside: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SourceBadge, { source: n.provenance }),
			className: "lg:col-span-2",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "grid grid-cols-2 gap-5 sm:grid-cols-4",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
						label: "GPU utilization",
						value: telemetry?.gpuUtilizationPercent != null ? `${telemetry.gpuUtilizationPercent}%` : "not reported"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
						label: "Temperature",
						value: telemetry?.temperatureC != null ? `${telemetry.temperatureC} C` : "not reported"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
						label: "Power draw",
						value: telemetry?.powerDrawW != null ? `${telemetry.powerDrawW} W` : "not reported"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
						label: "Disk read sample",
						value: telemetry?.diskReadMiBs ? `${telemetry.diskReadMiBs.toFixed(1)} MiB/s` : "not calibrated"
					})
				]
			})
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
			title: "Processor",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "grid gap-3",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
						label: "CPU",
						value: telemetry?.cpuModel ?? "not reported",
						mono: false
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
						label: "Logical processors",
						value: telemetry?.logicalCpuCount ?? "--"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KV, {
						label: "Last heartbeat",
						value: relativeTime(n.lastHeartbeatAt)
					})
				]
			})
		})]
	});
}
function BackendsTab({ n }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
		title: "Installed backends",
		children: n.backends.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
			className: "text-[13px] text-ink-secondary",
			children: "No backends installed on this node."
		}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
			className: "grid gap-1.5",
			children: n.backends.map((b) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("li", {
				className: "rift-mono text-[13px] text-ink",
				children: b
			}, b))
		})
	});
}
//#endregion
export { NodeDetail as component };
