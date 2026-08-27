import assert from "node:assert/strict";
import { deriveOperationDisplay } from "../src/lib/rift/operation-state.ts";

assert.deepEqual(deriveOperationDisplay({ status: "SUCCEEDED", result: { removed: ["chat"] } }), {
    stage: "succeeded",
    percent: 100,
    message: "Operation completed successfully.",
});

assert.deepEqual(deriveOperationDisplay({ status: "RUNNING" }), {
    stage: "running",
    percent: null,
    message: "Operation in progress.",
});

assert.deepEqual(
    deriveOperationDisplay({ status: "FAILED", error: "backend exited with code 1" }),
    {
        stage: "failed",
        percent: null,
        message: "backend exited with code 1",
    },
);

console.log("operation display normalization verification passed");
