import assert from "node:assert/strict";
import { mapLocalArtifact } from "../src/lib/rift/local-artifacts.ts";

const artifact = mapLocalArtifact({
    manifest: {
        manifest_sha256: "abc123",
        resolved_path: "C:/models/Qwen-3B-Q4_K_M.gguf",
        formats: ["gguf"],
        quantization: "Q4_K_M",
        model_bytes: 100,
        total_bytes: 120,
        files: [{ path: "Qwen-3B-Q4_K_M.gguf", role: "model", hash_status: "verified" }],
    },
    verification: { valid: true },
});
assert.equal(artifact.id, "abc123");
assert.equal(artifact.displayName, "Qwen-3B-Q4_K_M.gguf");
assert.equal(artifact.sizeBytes, 100);
assert.equal(artifact.quantization, "q4_k_m");
assert.equal(artifact.trust, "verified");

const unhashed = mapLocalArtifact({
    manifest: { resolved_path: "C:/models/model", formats: ["safetensors"], files: [] },
    verification: { valid: true },
});
assert.equal(
    unhashed.trust,
    "unknown",
    "presence-only verification must not imply verified hashes",
);
console.log("local artifact mapping contract verified");
