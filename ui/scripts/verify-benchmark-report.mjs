import assert from "node:assert/strict";
import { mapBenchmarkReport } from "../src/lib/rift/report-mapping.ts";

const report = {
    path: "C:\\rift\\reports\\1787613420-chat-benchmark-suite.json",
    summary: {
        created_unix_seconds: 1787613408.5,
        metadata: { launch_plan: { concurrency: 1, context_length: 8192 } },
        summary: { case_count: 3, median_tokens_per_second: 68.437986, valid: true },
        cases: [
            {
                summary: {
                    median_first_token_seconds: 0.023998,
                    median_tokens_per_second: 68.437986,
                },
            },
        ],
    },
};

const mapped = mapBenchmarkReport(report, "chat");
assert.equal(mapped?.tokensPerSec, 68.437986);
assert.equal(mapped?.firstTokenMs, 24);
assert.equal(mapped?.concurrency, 1);
assert.equal(mapped?.contextTokens, 8192);
assert.equal(mapped?.provenance, "live");

console.log("benchmark report mapping verification passed");
