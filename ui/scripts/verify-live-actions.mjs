import assert from "node:assert/strict";
import {
    applyRequest,
    isDeployableRecommendation,
    planRequest,
    recommendationSelector,
} from "../src/lib/rift/action-contract.ts";

assert.equal(
    isDeployableRecommendation({ support_level: "INSTALLABLE_BACKEND", backend: "llama.cpp" }),
    true,
);
assert.equal(isDeployableRecommendation({ support_level: "UNSUPPORTED", backend: "none" }), false);

assert.equal(recommendationSelector("recommended"), "best_estimated");
assert.equal(recommendationSelector("quality"), "highest_quality");
assert.equal(recommendationSelector("speed"), "fastest");

assert.deepEqual(planRequest("run-123", "fastest"), {
    recommendation_run_id: "run-123",
    selector: "fastest",
});

assert.deepEqual(
    applyRequest("C:/rift/generated/recommendation-run-123.yaml", {
        allowDownload: true,
        allowInstall: true,
        allowLaunch: true,
    }),
    {
        config: "C:/rift/generated/recommendation-run-123.yaml",
        allow_download: true,
        allow_install: true,
        allow_launch: true,
        allow_remote: false,
        optimize: false,
        write_back: false,
    },
);

console.log("live action contract verification passed");
