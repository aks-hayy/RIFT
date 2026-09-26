import assert from "node:assert/strict";
import { DEFAULT_ROUTE, NAVIGATION } from "../src/lib/rift/navigation.ts";

assert.equal(DEFAULT_ROUTE, "/workloads");
assert.deepEqual(
  NAVIGATION.primary.map(({ label, to }) => [label, to]),
  [
    ["Overview", "/overview"],
    ["Services", "/deployments"],
    ["Nodes", "/nodes"],
    ["Models", "/models"],
    ["Groups", "/groups"],
    ["Operations", "/operations"],
    ["Tuning", "/tuning"],
    ["Settings", "/settings"],
  ],
);
assert.deepEqual(
  NAVIGATION.deployment.map(({ label, to }) => [label, to]),
  [
    ["Workload Deploy", "/workloads"],
    ["Best Fit Setup", "/setup"],
  ],
);
assert.deepEqual(NAVIGATION.modelsCatalog, { label: "Catalog", to: "/models/catalog" });

console.log("navigation contract verified");
