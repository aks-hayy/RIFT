import { r as require_jsx_runtime } from "./useRouter-C_cgokP9.js";
import { t as Link } from "./link-DZw2_uJJ.js";
import { C as Activity, a as StatDot, m as useMeshTopology, n as PageHeader, o as AppShell, p as useMeshNodes, r as Panel } from "./primitives-At99O-dv.js";
import { c as createLucideIcon, t as Unavailable } from "./unavailable-Dh9iADmt.js";
import { n as Network, t as ShieldCheck } from "./shield-check-BRN_ydtb.js";
import { r as relativeTime } from "./format-gcr4F9Vx.js";
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var UserPlus = createLucideIcon("user-plus", [
	["path", {
		d: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2",
		key: "1yyitq"
	}],
	["circle", {
		cx: "9",
		cy: "7",
		r: "4",
		key: "nufk8"
	}],
	["line", {
		x1: "19",
		x2: "19",
		y1: "8",
		y2: "14",
		key: "1bvyxn"
	}],
	["line", {
		x1: "22",
		x2: "16",
		y1: "11",
		y2: "11",
		key: "1shjgl"
	}]
]);
//#endregion
//#region src/routes/nodes.index.tsx?tsr-split=component
var import_jsx_runtime = require_jsx_runtime();
function nodeTone(node) {
	if (node.trustState === "REVOKED" || !node.healthy) return "error";
	if (node.trustState === "ACTIVE" && node.routable) return "ok";
	return "attention";
}
function nodeStatus(node) {
	if (node.trustState === "ACTIVE" && node.routable) return "active";
	if (node.trustState === "ENROLLED") return "enrolled";
	return node.trustState.toLowerCase().replaceAll("_", " ");
}
function certificateStatus(node) {
	if (node.certificateRequired) return "activation pending";
	if (node.trustState === "ACTIVE") return "active";
	return "not active";
}
function NodesListPage() {
	const nodesQuery = useMeshNodes();
	const topologyQuery = useMeshTopology();
	const nodes = nodesQuery.data ?? [];
	const topology = topologyQuery.data;
	const routable = nodes.filter((node) => node.routable && node.trustState === "ACTIVE").length;
	const certificatePending = nodes.filter((node) => node.certificateRequired).length;
	const unhealthy = nodes.filter((node) => !node.healthy).length;
	const nodeNames = new Map([...nodes, ...topology?.nodes ?? []].map((node) => [node.nodeId, node.hostname]));
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(AppShell, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(PageHeader, {
		eyebrow: "Mesh operations",
		title: "Nodes",
		description: "Live enrollment, activation, routing, and measured-link state from the RIFT controller.",
		actions: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Link, {
			to: "/setup",
			className: "inline-flex items-center gap-2 h-9 px-3.5 rounded-[4px] border border-border text-[13px] font-medium hover:bg-muted",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(UserPlus, {
				className: "size-4",
				"aria-hidden": true
			}), " Discover node"]
		})
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "max-w-[1400px] mx-auto px-4 py-6 grid gap-6",
		children: [
			!nodesQuery.unavailable && !nodesQuery.isLoading && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("section", {
				className: "grid grid-cols-2 lg:grid-cols-4 border-y border-border bg-raised",
				"aria-label": "Mesh node summary",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(MeshStat, {
						label: "Enrolled",
						value: nodes.length,
						icon: Network
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(MeshStat, {
						label: "Active / routable",
						value: routable,
						icon: Activity
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(MeshStat, {
						label: "Certificate pending",
						value: certificatePending,
						icon: ShieldCheck
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(MeshStat, {
						label: "Unhealthy",
						value: unhealthy,
						icon: Activity,
						tone: unhealthy ? "error" : "default"
					})
				]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("section", {
				"aria-labelledby": "mesh-node-registry",
				children: nodesQuery.unavailable ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
					endpoint: "/api/rift/v2/mesh/nodes",
					resource: "{ api_version, nodes: MeshNode[] }",
					hint: "Start the RIFT controller or complete controller configuration before managing mesh enrollment."
				}) : nodesQuery.isLoading ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
					title: "Enrollment registry",
					children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "text-[13px] text-ink-secondary",
						children: "Loading enrolled identities…"
					})
				}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
					bodyClassName: "p-0 overflow-x-auto",
					title: `${nodes.length} enrolled node${nodes.length === 1 ? "" : "s"}`,
					children: nodes.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "px-4 py-14 text-center",
						children: [
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)(ShieldCheck, {
								className: "size-5 text-ink-secondary mx-auto",
								"aria-hidden": true
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
								className: "mt-3 text-[13px] font-medium text-ink",
								children: "No enrolled nodes"
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
								className: "mt-1 text-[12.5px] text-ink-secondary",
								children: "Discovery sightings do not appear here until an operator approves pairing."
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Link, {
								to: "/setup",
								className: "mt-4 inline-flex items-center gap-2 h-9 px-3 rounded-[4px] border border-border text-[12px] font-medium hover:bg-muted",
								children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(UserPlus, {
									className: "size-3.5",
									"aria-hidden": true
								}), " Open discovery"]
							})
						]
					}) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("table", {
						className: "w-full min-w-[960px] text-[13px]",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("thead", {
							className: "rift-label",
							children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
								className: "border-b border-border",
								children: [
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										id: "mesh-node-registry",
										className: "text-left px-4 h-9 font-normal",
										children: "Node"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-left px-4 font-normal",
										children: "Enrollment"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-left px-4 font-normal",
										children: "Routable"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-left px-4 font-normal",
										children: "Certificate"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-left px-4 font-normal",
										children: "Health"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-right px-4 font-normal",
										children: "Queue"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-left px-4 font-normal",
										children: "Last seen"
									})
								]
							})
						}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("tbody", { children: nodes.map((node) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
							className: "border-b border-border last:border-0 hover:bg-muted/50",
							children: [
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-4 py-3",
									children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
										className: "flex items-center gap-2",
										children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StatDot, { tone: nodeTone(node) }), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
											className: "min-w-0",
											children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
												className: "font-medium text-ink",
												children: node.hostname
											}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
												className: "rift-mono text-[10.5px] text-ink-secondary truncate max-w-[260px]",
												children: [node.nodeId, node.endpoint ? ` · ${node.endpoint}` : ""]
											})]
										})]
									})
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-4 rift-mono text-[11.5px] uppercase text-ink-secondary",
									children: nodeStatus(node)
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-4",
									children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(StateLabel, {
										active: node.routable,
										yes: "yes",
										no: "no"
									})
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-4 rift-mono text-[11.5px] text-ink-secondary",
									children: certificateStatus(node)
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-4",
									children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(StateLabel, {
										active: node.healthy,
										yes: "healthy",
										no: "unhealthy"
									})
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-4 text-right rift-mono text-[12px]",
									children: node.queueDepth
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-4 rift-mono text-[11.5px] text-ink-secondary whitespace-nowrap",
									children: node.lastSeenAt ? relativeTime(node.lastSeenAt) : "not reported"
								})
							]
						}, node.nodeId)) })]
					})
				})
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("section", {
				"aria-labelledby": "mesh-link-table",
				children: topologyQuery.unavailable ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Unavailable, {
					endpoint: "/api/rift/v2/mesh/topology",
					resource: "{ api_version, nodes: MeshNode[], links: MeshLink[], evidence }",
					reason: "Link measurements are unavailable. Enrolled-node state above may still be current.",
					hint: "RIFT does not infer latency or draw synthetic connections when topology telemetry is absent."
				}) : topologyQuery.isLoading || !topology ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
					title: "Measured links",
					children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "text-[13px] text-ink-secondary",
						children: "Loading link measurements…"
					})
				}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
					bodyClassName: "p-0 overflow-x-auto",
					title: `Measured links · ${topology.evidence}`,
					children: topology.links.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "px-4 py-10 text-[13px] text-ink-secondary",
						children: "No measured links reported. RIFT will show routes here after the controller records real link telemetry."
					}) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("table", {
						className: "w-full min-w-[980px] text-[13px]",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("thead", {
							className: "rift-label",
							children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
								className: "border-b border-border",
								children: [
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										id: "mesh-link-table",
										className: "text-left px-4 h-9 font-normal",
										children: "Source"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-left px-4 font-normal",
										children: "Target"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-right px-4 font-normal",
										children: "RTT p50"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-right px-4 font-normal",
										children: "RTT p95"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-right px-4 font-normal",
										children: "Jitter"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-right px-4 font-normal",
										children: "Loss"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-right px-4 font-normal",
										children: "Up"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-right px-4 font-normal",
										children: "Down"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "text-left px-4 font-normal",
										children: "Evidence"
									})
								]
							})
						}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("tbody", { children: topology.links.map((link) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
							className: "border-b border-border last:border-0 hover:bg-muted/50",
							children: [
								/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("td", {
									className: "px-4 py-3",
									children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
										className: "font-medium text-ink",
										children: nodeNames.get(link.sourceNodeId) ?? link.sourceNodeId
									}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
										className: "rift-mono text-[10.5px] text-ink-secondary",
										children: link.sourceNodeId
									})]
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("td", {
									className: "px-4 py-3",
									children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
										className: "font-medium text-ink",
										children: nodeNames.get(link.targetNodeId) ?? link.targetNodeId
									}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
										className: "rift-mono text-[10.5px] text-ink-secondary",
										children: link.targetNodeId
									})]
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Metric, {
									value: link.rttP50Ms,
									unit: "ms"
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Metric, {
									value: link.rttP95Ms,
									unit: "ms"
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Metric, {
									value: link.jitterMs,
									unit: "ms"
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Metric, {
									value: link.lossRatio * 100,
									unit: "%"
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Metric, {
									value: link.uploadMbps,
									unit: "Mbps"
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Metric, {
									value: link.downloadMbps,
									unit: "Mbps"
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-4 rift-mono text-[10.5px] uppercase text-ink-secondary",
									children: link.evidence
								})
							]
						}, `${link.sourceNodeId}-${link.targetNodeId}`)) })]
					})
				})
			})
		]
	})] });
}
function MeshStat({ label, value, icon: Icon, tone = "default" }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "min-h-20 px-4 py-3 border-r border-b lg:border-b-0 border-border last:border-r-0",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "flex items-center gap-2 rift-label",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Icon, { className: tone === "error" ? "size-3.5 text-error" : "size-3.5 text-primary" }), label]
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: tone === "error" ? "mt-2 rift-mono text-[20px] text-error" : "mt-2 rift-mono text-[20px] text-ink",
			children: value
		})]
	});
}
function StateLabel({ active, yes, no }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
		className: active ? "rift-mono text-[10.5px] uppercase text-success" : "rift-mono text-[10.5px] uppercase text-attention",
		children: active ? yes : no
	});
}
function Metric({ value, unit }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("td", {
		className: "px-4 text-right rift-mono text-[11.5px] whitespace-nowrap",
		children: [
			Number.isFinite(value) ? value.toFixed(value < 10 ? 2 : 1) : "—",
			" ",
			unit
		]
	});
}
//#endregion
export { NodesListPage as component };
