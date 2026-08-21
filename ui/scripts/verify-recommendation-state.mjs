import assert from "node:assert/strict";
import {
    recommendationViewState,
    recommendationFailureSummary,
} from "../src/lib/rift/recommendation-state.ts";

const live = {
    recommendations: [{ id: "one" }],
    stale: false,
    queryArmErrors: [],
};
assert.equal(recommendationViewState(live), "ready");

const cached = {
    recommendations: [{ id: "one" }],
    stale: true,
    queryArmErrors: ["text-generation: WinError 10013"],
};
assert.equal(recommendationViewState(cached), "stale");
assert.match(recommendationFailureSummary(cached), /last successful shortlist/i);

const empty = {
    recommendations: [],
    stale: false,
    queryArmErrors: ["text-generation: WinError 10013", "downloads: WinError 10013"],
};
assert.equal(recommendationViewState(empty), "empty");
assert.match(recommendationFailureSummary(empty), /Hub search failed/i);

console.log("recommendation state verification passed");
