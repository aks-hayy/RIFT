import { c as __toESM, i as require_react, r as require_jsx_runtime } from "./useRouter-C3Fl0Qct.js";
import { t as Link } from "./link-RSGdeuyI.js";
import { a as StatDot, d as Activity, n as PageHeader, o as AppShell, r as Panel } from "./primitives-DeAXA1eZ.js";
import { O as useServices, V as createLucideIcon, h as useMeshNodes, v as useMeshTopology } from "./hooks-BdOll_GY.js";
import { t as Network } from "./network-Dc-p0ssL.js";
import { t as ShieldCheck } from "./shield-check-BLFQ9QZC.js";
import { r as relativeTime } from "./format-gcr4F9Vx.js";
import { t as Unavailable } from "./unavailable-D_3mUZyv.js";
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var ArrowUpRight = createLucideIcon("arrow-up-right", [["path", {
	d: "M7 7h10v10",
	key: "1tivn9"
}], ["path", {
	d: "M7 17 17 7",
	key: "1vkiza"
}]]);
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
//#region src/lib/rift/node-services.ts
var import_react = /* @__PURE__ */ __toESM(require_react());
function assignedServices(services, nodeId) {
	if (!nodeId) return [];
	return services.filter((service) => service.assignments.some((assignment) => assignment.nodeId === nodeId));
}
//#endregion
//#region src/lib/rift/topology-layout.ts
function buildNodeMapLayout(nodes, links) {
	const columns = Math.max(1, Math.ceil(Math.sqrt(nodes.length)));
	const rows = Math.max(1, Math.ceil(nodes.length / columns));
	const layoutNodes = nodes.map((node, index) => ({
		id: node.nodeId,
		x: (index % columns + .5) * (100 / columns),
		y: (Math.floor(index / columns) + .5) * (100 / rows)
	}));
	const ids = new Set(nodes.map((node) => node.nodeId));
	return {
		nodes: layoutNodes,
		links: links.filter((link) => ids.has(link.sourceNodeId) && ids.has(link.targetNodeId))
	};
}
//#endregion
//#region src/components/rift/node-map.tsx
var import_jsx_runtime = require_jsx_runtime();
function NodeMap({ nodes, links, services }) {
	const [selectedId, setSelectedId] = (0, import_react.useState)(null);
	const layout = (0, import_react.useMemo)(() => buildNodeMapLayout(nodes, links), [nodes, links]);
	const selectedIdNow = nodes.some((node) => node.nodeId === selectedId) ? selectedId : nodes[0]?.nodeId ?? null;
	const selectedNode = nodes.find((node) => node.nodeId === selectedIdNow) ?? null;
	const nodeServices = assignedServices(services, selectedNode?.nodeId ?? null);
	const nodePositions = new Map(layout.nodes.map((node) => [node.id, node]));
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Panel, {
		title: "Node map",
		aside: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
			className: "inline-flex items-center gap-1.5 rift-mono text-[10.5px] text-ink-secondary",
			children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Network, {
					className: "size-3.5 text-primary",
					"aria-hidden": true
				}),
				nodes.length,
				" nodes · ",
				layout.links.length,
				" measured links"
			]
		}),
		children: !nodes.length ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "rounded-xl border border-dashed border-border-strong bg-white/35 px-5 py-10 text-center",
			children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Network, {
					className: "mx-auto size-5 text-ink-muted",
					"aria-hidden": true
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
					className: "mt-2 text-[13px] font-medium text-ink",
					children: "No enrolled nodes to map"
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
					className: "mt-1 text-[12px] text-ink-secondary",
					children: "Discovery sightings remain separate until an operator approves node pairing."
				})
			]
		}) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "relative min-h-[310px] overflow-hidden rounded-2xl border border-border/70 bg-[radial-gradient(ellipse_at_center,rgba(255,255,255,.93),rgba(245,242,244,.72))] p-3 sm:min-h-[370px]",
			children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "pointer-events-none absolute inset-0 opacity-40 [background-image:linear-gradient(rgba(105,56,64,.08)_1px,transparent_1px),linear-gradient(90deg,rgba(105,56,64,.08)_1px,transparent_1px)] [background-size:32px_32px]",
					"aria-hidden": true
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("svg", {
					className: "pointer-events-none absolute inset-0 size-full",
					viewBox: "0 0 1000 440",
					preserveAspectRatio: "none",
					"aria-hidden": "true",
					children: layout.links.map((link) => {
						const source = nodePositions.get(link.sourceNodeId);
						const target = nodePositions.get(link.targetNodeId);
						if (!source || !target) return null;
						return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("line", {
							x1: source.x * 10,
							y1: source.y * 4.4,
							x2: target.x * 10,
							y2: target.y * 4.4,
							stroke: "var(--oxide)",
							strokeWidth: "1.5",
							strokeDasharray: "6 7",
							strokeOpacity: ".56",
							children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("title", { children: [
								"Measured link · ",
								link.rttP50Ms.toFixed(1),
								" ms p50 · ",
								link.evidence
							] })
						}, `${link.sourceNodeId}-${link.targetNodeId}`);
					})
				}),
				layout.nodes.map((position) => {
					const node = nodes.find((item) => item.nodeId === position.id);
					if (!node) return null;
					const active = node.nodeId === selectedIdNow;
					return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
						type: "button",
						onClick: () => setSelectedId(node.nodeId),
						"aria-pressed": active,
						"aria-label": `Select node ${node.hostname}, ${node.healthy ? "healthy" : "unhealthy"}, ${node.routable ? "routable" : "not routable"}`,
						className: `absolute z-10 flex w-[min(40vw,190px)] -translate-x-1/2 -translate-y-1/2 flex-col rounded-xl border px-3 py-2.5 text-left shadow-lg backdrop-blur-lg transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${active ? "border-primary/60 bg-white/95 ring-2 ring-primary/15" : "border-white/80 bg-white/75 hover:border-primary/35 hover:bg-white/95"}`,
						style: {
							left: `${position.x}%`,
							top: `${position.y}%`
						},
						children: [
							/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
								className: "flex min-w-0 items-center gap-2",
								children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StatDot, { tone: !node.healthy || node.trustState === "REVOKED" ? "error" : node.routable ? "ok" : "attention" }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
									className: "truncate text-[12px] font-semibold text-ink",
									children: node.hostname
								})]
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "mt-1 truncate pl-4 rift-mono text-[9.5px] text-ink-muted",
								children: node.nodeId
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
								className: "mt-1 flex items-center justify-between pl-4 text-[10px] text-ink-secondary",
								children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: node.trustState.toLowerCase().replaceAll("_", " ") }), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [node.queueDepth, " queued"] })]
							})
						]
					}, node.nodeId);
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "absolute bottom-3 left-3 rounded-lg border border-border/60 bg-white/80 px-2.5 py-1.5 rift-mono text-[9.5px] text-ink-secondary backdrop-blur",
					children: "schematic layout · only measured links are drawn"
				})
			]
		}), selectedNode && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "mt-4 grid gap-4 rounded-xl border border-border/70 bg-white/45 p-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "rift-label",
					children: "Selected node"
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "mt-1 flex items-center gap-2 text-[14px] font-semibold text-ink",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StatDot, { tone: !selectedNode.healthy ? "error" : selectedNode.routable ? "ok" : "attention" }), selectedNode.hostname]
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "mt-1 rift-mono text-[10.5px] text-ink-secondary",
					children: selectedNode.nodeId
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Link, {
					to: "/nodes/$id",
					params: { id: selectedNode.nodeId },
					className: "mt-3 inline-flex h-8 items-center gap-1.5 rounded-lg border border-border bg-white/80 px-3 text-[11.5px] font-medium text-primary hover:bg-primary/5",
					children: ["Inspect node ", /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ArrowUpRight, {
						className: "size-3.5",
						"aria-hidden": true
					})]
				})
			] }), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "rift-label",
				children: "Services assigned to this node"
			}), nodeServices.length ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
				className: "mt-2 flex flex-wrap gap-2",
				children: nodeServices.map((service) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("li", { children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Link, {
					to: "/deployments/$id",
					params: { id: service.id },
					className: "inline-flex items-center gap-2 rounded-lg border border-border bg-white/80 px-3 py-2 text-[11.5px] text-ink hover:border-primary/35 hover:text-primary",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StatDot, { tone: service.status === "running" ? "ok" : service.status === "failed" ? "error" : "attention" }), service.name]
				}) }, service.id))
			}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
				className: "mt-2 text-[12px] text-ink-secondary",
				children: "No service assignment is reported for this node."
			})] })]
		})] })
	});
}
//#endregion
//#region src/routes/nodes.index.tsx?tsr-split=component
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
	const servicesQuery = useServices();
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
			!nodesQuery.unavailable && !nodesQuery.isLoading && !nodesQuery.error && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(NodeMap, {
				nodes,
				links: topologyQuery.data?.links ?? [],
				services: servicesQuery.data ?? []
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
