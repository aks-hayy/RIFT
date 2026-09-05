import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const { tuningProfileLabel, tuningOutcomeTone } =
    await import("../src/lib/rift/tuning-contract.ts");

assert.equal(tuningProfileLabel("speed"), "Speed");
assert.equal(tuningProfileLabel("cost"), "Cost");
assert.equal(tuningOutcomeTone("improved"), "success");
assert.equal(tuningOutcomeTone("no_improvement"), "attention");
assert.equal(tuningOutcomeTone("failed"), "error");
const route = readFileSync(new URL("../src/routes/tuning.tsx", import.meta.url), "utf8");
const client = readFileSync(new URL("../src/lib/rift/client.ts", import.meta.url), "utf8");
assert.match(route, /Target throughput/);
assert.match(route, /Accuracy/);
assert.match(route, /K\/V precision search/);
assert.match(route, /Advanced controls/);
assert.match(route, /N-gram speculation/);
assert.match(route, /Experiment budget/);
assert.match(route, /Warmup runs/);
assert.match(route, /Measurement repeats/);
assert.match(route, /Benchmark prompt/);
assert.match(route, /Preview scope/);
assert.match(route, /rejectionReason/);
assert.match(route, /Selected K cache/);
assert.match(route, /Selected V cache/);
assert.match(route, /rollback|baseline kept/i);
for (const field of [
    "ngram_speculation",
    "budget_seconds",
    "warmup_runs",
    "repeats",
    "startup_timeout_seconds",
    "max_tokens",
    "retain_accuracy_responses",
]) {
    assert.match(client, new RegExp(field), `client serializes ${field}`);
}
console.log("tuning-flow: PASS");
