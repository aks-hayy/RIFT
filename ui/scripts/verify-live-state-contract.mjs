import assert from "node:assert/strict";
import { resolveLiveState } from "../src/lib/rift/live-state-state.ts";

const scenarios = [
  [{ isLoading: true, hasData: false }, "loading"],
  [{ isLoading: false, hasData: true, empty: true }, "empty"],
  [{ isLoading: false, hasData: false, unavailable: true }, "unavailable"],
  [{ isLoading: false, hasData: false, error: true }, "error"],
  [{ isLoading: false, hasData: false, unsupported: true }, "unsupported"],
  [{ isLoading: false, hasData: true }, "ready"],
];

for (const [input, expected] of scenarios) {
  assert.equal(resolveLiveState(input), expected, `wrong state for ${JSON.stringify(input)}`);
}

assert.equal(
  resolveLiveState({ isLoading: true, hasData: false, unavailable: true }),
  "unavailable",
  "an explicit controller failure must not be disguised as loading",
);

console.log("live state contract verified");
