import assert from "node:assert/strict";
import { buildNodeMapLayout } from "../src/lib/rift/topology-layout.ts";

assert.deepEqual(
  buildNodeMapLayout(
    [{ nodeId: "node-a" }, { nodeId: "node-b" }, { nodeId: "node-c" }],
    [
      { sourceNodeId: "node-a", targetNodeId: "node-b", rttP50Ms: 4 },
      { sourceNodeId: "node-a", targetNodeId: "missing", rttP50Ms: 999 },
    ],
  ),
  {
    nodes: [
      { id: "node-a", x: 25, y: 25 },
      { id: "node-b", x: 75, y: 25 },
      { id: "node-c", x: 25, y: 75 },
    ],
    links: [{ sourceNodeId: "node-a", targetNodeId: "node-b", rttP50Ms: 4 }],
  },
);

console.log("node map only lays out registered nodes and measured links");
