import assert from "node:assert/strict";
import { buildWorkloadEnvelope, hasValidAcquisitionApproval } from "../src/lib/rift/workload-approval.ts";

const values = {
    network: "offline",
    licensePolicy: "apache-2.0",
    actions: {
        cleanup: false,
        download: false,
        install: false,
        promote: true,
        remote_execution: false,
        restart: false,
        temporary_launch: true,
    },
    explorationSeconds: "7200",
    maxArtifacts: "4",
    tuningCandidates: "18",
    perArtifactGiB: "0",
    totalDownloadGiB: "0",
};
const envelope = buildWorkloadEnvelope(values);
assert.equal(envelope.limits.exploration_seconds, 7200);
assert.equal(envelope.limits.max_artifacts, 4);
assert.equal(envelope.limits.tuning_candidates, 18);
assert.equal(envelope.limits.total_download_bytes, 0);
assert.equal(
    hasValidAcquisitionApproval({
        network: "approved_sources",
        allowDownload: false,
        allowInstall: true,
        perArtifactGiB: "0",
        totalDownloadGiB: "0",
    }),
    true,
    "backend-only installation must be approvable with a zero model-download budget",
);
assert.equal(
    hasValidAcquisitionApproval({
        network: "approved_sources",
        allowDownload: false,
        allowInstall: false,
        perArtifactGiB: "0",
        totalDownloadGiB: "0",
    }),
    false,
);
assert.deepEqual(envelope.licenses, []);
assert.deepEqual(
    buildWorkloadEnvelope({
        ...values,
        network: "approved_sources",
        licensePolicy: "apache-2.0",
        actions: { ...values.actions, download: true },
        explorationSeconds: "10",
        perArtifactGiB: "1",
        totalDownloadGiB: "2",
    }).licenses,
    ["Apache-2.0"],
);
assert.throws(
    () => buildWorkloadEnvelope({ ...values, explorationSeconds: "" }),
    /exploration time/i,
);
assert.throws(
    () => buildWorkloadEnvelope({ ...values, network: "offline", totalDownloadGiB: "1" }),
    /offline/i,
);
assert.throws(() => buildWorkloadEnvelope({ ...values, maxArtifacts: "0" }), /artifact/i);
console.log("explicit workload approval limits verified");
