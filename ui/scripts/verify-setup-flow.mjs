import assert from "node:assert/strict";
import { getNextSetupStep, getPreviousSetupStep } from "../src/lib/rift/setup-flow.ts";

const standalone = (index) => index === 0 || index === 1 || index >= 4;
const cluster = () => true;

assert.equal(getNextSetupStep(1, standalone, 11), 4);
assert.equal(getPreviousSetupStep(4, standalone, 0), 1);
assert.equal(getNextSetupStep(1, cluster, 11), 2);
assert.equal(getPreviousSetupStep(2, cluster, 0), 1);

console.log("setup-flow verification passed");
