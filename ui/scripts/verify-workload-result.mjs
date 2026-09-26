import assert from "node:assert/strict";
import { summarizeWorkloadRun } from "../src/lib/rift/workload-result.ts";

const summary = summarizeWorkloadRun(
  {
    deployment: {
      plan: {
        services: {
          assistant: {
            backend: "llama.cpp",
            model: { selected_file: "Qwen2.5-7B-Q4_K_M.gguf", source: "local" },
            serving: { context_length: 8192, concurrency: 1 },
          },
        },
      },
    },
    benchmark: { summary: { median_tokens_per_second: 45.195, sample_count: 15 } },
    evaluation: { summary: { pass: 1, fail: 0, error: 0 } },
    acceptance: { evaluation_passed: true },
  },
  "VERIFIED",
);

assert.equal(summary.status, "VERIFIED");
assert.equal(summary.serviceName, "assistant");
assert.equal(summary.backend, "llama.cpp");
assert.equal(summary.model, "Qwen2.5-7B-Q4_K_M.gguf");
assert.equal(summary.contextTokens, 8192);
assert.equal(summary.decodeTokensPerSecond, 45.195);
assert.equal(summary.evaluationPassed, true);

const empty = summarizeWorkloadRun({ operation_id: "op-1" }, "RUNNING");
assert.equal(empty.backend, null);
assert.equal(empty.decodeTokensPerSecond, null);
