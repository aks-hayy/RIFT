import assert from "node:assert/strict";
import { alignTelemetrySeries } from "../src/lib/rift/telemetry-series.ts";

const aligned = alignTelemetrySeries([
  {
    id: "service-a",
    unit: "%",
    scope: "service",
    points: [
      { observed_at: 100, count: 2, mean: 12, minimum: 8, maximum: 16 },
      { observed_at: 200, count: 0, mean: null, minimum: null, maximum: null },
    ],
  },
  {
    id: "service-b",
    unit: "%",
    scope: "service",
    points: [
      { observed_at: 100, count: 1, mean: 21, minimum: 21, maximum: 21 },
      { observed_at: 300, count: 1, mean: 25, minimum: 25, maximum: 25 },
    ],
  },
]);

assert.deepEqual(aligned, {
  unit: "%",
  scope: "service",
  points: [
    { observed_at: 100, "service-a": 12, "service-b": 21 },
    { observed_at: 200, "service-a": null, "service-b": null },
    { observed_at: 300, "service-a": null, "service-b": 25 },
  ],
});

assert.throws(
  () =>
    alignTelemetrySeries([
      { id: "a", unit: "bytes", scope: "service", points: [] },
      { id: "b", unit: "percent", scope: "service", points: [] },
    ]),
  /units differ/,
);
assert.throws(
  () =>
    alignTelemetrySeries([
      { id: "a", unit: "%", scope: "service", points: [] },
      { id: "b", unit: "%", scope: "host", points: [] },
    ]),
  /scopes differ/,
);

console.log("telemetry series alignment verified");
