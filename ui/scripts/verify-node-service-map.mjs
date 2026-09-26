import assert from "node:assert/strict";
import { assignedServices } from "../src/lib/rift/node-services.ts";

const services = [
    { id: "api", assignments: [{ nodeId: "node-a" }] },
    { id: "worker", assignments: [{ nodeId: "node-b" }] },
    { id: "shared", assignments: [{ nodeId: "node-a" }, { nodeId: "node-b" }] },
];

assert.deepEqual(
    assignedServices(services, "node-a").map(({ id }) => id),
    ["api", "shared"],
);
assert.deepEqual(assignedServices(services, "missing"), []);
assert.deepEqual(assignedServices(services, null), []);
console.log("node-service mapping contract verified");
