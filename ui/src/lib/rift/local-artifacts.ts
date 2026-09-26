import type { ModelArtifact } from "./types";

type JsonObject = Record<string, unknown>;
const object = (value: unknown): JsonObject =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as JsonObject) : {};
const string = (value: unknown): string => (typeof value === "string" ? value : "");

export function mapLocalArtifact(value: unknown): ModelArtifact {
  const record = object(value);
  const manifest = object(record.manifest);
  const verification = object(record.verification);
  const resolvedPath = string(manifest.resolved_path);
  const parts = resolvedPath.replace(/\\/g, "/").split("/").filter(Boolean);
  const displayName = parts.at(-1) ?? string(manifest.repo_id) ?? "Local artifact";
  const formats = Array.isArray(manifest.formats) ? manifest.formats.map(String) : [];
  const format = formats.includes("gguf") ? "gguf" : "hf";
  const quant = string(manifest.quantization).toLowerCase();
  const files = Array.isArray(manifest.files) ? manifest.files.map(object) : [];
  const modelFiles = files.filter((file) => file.role === "model");
  const hashesVerified =
    modelFiles.length > 0 && modelFiles.every((file) => file.hash_status === "verified");
  const verified = verification.valid === true && hashesVerified;
  const sizeBytes = Number(manifest.model_bytes ?? manifest.total_bytes ?? 0);
  const id = string(manifest.manifest_sha256) || resolvedPath || displayName;

  return {
    id,
    displayName,
    family: string(manifest.repo_id) || "local artifact",
    parameters: "not reported in manifest",
    source: "local",
    repo: string(manifest.repo_id) || undefined,
    revision: string(manifest.revision) || undefined,
    format,
    quantization: quant as ModelArtifact["quantization"],
    sizeBytes: Number.isFinite(sizeBytes) ? sizeBytes : 0,
    sha256: string(manifest.manifest_sha256) || undefined,
    license: string(manifest.license) || "not reported",
    trust: verified ? "verified" : "unknown",
    provenance: "live",
  };
}
