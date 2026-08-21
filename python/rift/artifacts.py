"""Artifact selection, provenance manifests, and cache integrity for RIFT."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import time
from typing import Any, Iterable


JsonDict = dict[str, Any]
_MODEL_SUFFIXES = {".gguf", ".safetensors", ".bin", ".pt", ".pth"}
_METADATA_NAMES = {
    "config.json",
    "generation_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "model.safetensors.index.json",
}


class ArtifactManifest:
    """Build and validate an exact deployment artifact manifest."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root else Path.cwd()

    def build(
        self,
        model_path: str | Path,
        *,
        source: str = "local",
        repo_id: str | None = None,
        revision: str | None = None,
        license_name: str | None = None,
        gated: bool | None = None,
        hash_mode: str = "model",
    ) -> JsonDict:
        root = Path(model_path)
        if not root.exists():
            raise ValueError(f"artifact path does not exist: {root}")
        if hash_mode not in ("none", "metadata", "model", "all"):
            raise ValueError("hash_mode must be none, metadata, model, or all")
        files = [root] if root.is_file() else sorted(path for path in root.rglob("*") if path.is_file())
        entries = []
        total = 0
        model_total = 0
        for path in files:
            relative = path.name if root.is_file() else path.relative_to(root).as_posix()
            size = int(path.stat().st_size)
            is_model = path.suffix.lower() in _MODEL_SUFFIXES
            is_metadata = path.name.lower() in _METADATA_NAMES or path.suffix.lower() in {".json", ".model"}
            should_hash = hash_mode == "all" or (hash_mode == "model" and is_model) or (
                hash_mode == "metadata" and is_metadata
            )
            entry = {
                "path": relative,
                "size": size,
                "role": "model" if is_model else "metadata" if is_metadata else "auxiliary",
                "sha256": self._sha256(path) if should_hash else None,
                "hash_status": "verified" if should_hash else "not_computed",
            }
            entries.append(entry)
            total += size
            if is_model:
                model_total += size
        formats = sorted({Path(item["path"]).suffix.lower().lstrip(".") for item in entries if item["role"] == "model"})
        manifest = {
            "schema_version": 1,
            "created_unix_seconds": time.time(),
            "source": source,
            "repo_id": repo_id,
            "revision": revision,
            "resolved_path": str(root.resolve()),
            "license": license_name,
            "gated": gated,
            "formats": formats,
            "quantization": self._detect_quantization(entries),
            "file_count": len(entries),
            "total_bytes": total,
            "model_bytes": model_total,
            "hash_mode": hash_mode,
            "files": entries,
        }
        manifest["manifest_sha256"] = hashlib.sha256(
            json.dumps(manifest, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return manifest

    def verify(self, manifest: JsonDict, *, root: str | Path | None = None) -> JsonDict:
        base = Path(root or manifest.get("resolved_path") or self.root)
        if base.is_file():
            base_parent = base.parent
            single_name = base.name
        else:
            base_parent = base
            single_name = None
        checks = []
        for item in manifest.get("files", []):
            relative = str(item.get("path") or "")
            path = base if single_name and relative == single_name else base_parent / relative
            check = {"path": relative, "exists": path.is_file(), "size_ok": False, "hash_ok": None}
            if path.is_file():
                check["size_ok"] = int(path.stat().st_size) == int(item.get("size") or -1)
                expected = item.get("sha256")
                if expected:
                    check["hash_ok"] = self._sha256(path) == str(expected)
            check["valid"] = bool(check["exists"] and check["size_ok"] and check["hash_ok"] is not False)
            checks.append(check)
        valid = bool(checks) and all(check["valid"] for check in checks)
        return {
            "valid": valid,
            "checked_unix_seconds": time.time(),
            "root": str(base),
            "file_count": len(checks),
            "invalid_files": [check for check in checks if not check["valid"]],
            "checks": checks,
        }

    def write(self, manifest: JsonDict, target: str | Path) -> str:
        path = Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(path)
        return str(path)

    def classify_remote_files(self, files: Iterable[JsonDict]) -> JsonDict:
        normalized = [dict(item) for item in files]
        gguf = [item for item in normalized if str(item.get("path") or "").lower().endswith(".gguf")]
        safetensors = [
            item for item in normalized if str(item.get("path") or "").lower().endswith(".safetensors")
        ]
        names = [str(item.get("path") or "").lower() for item in normalized]
        quantization = "unknown"
        if gguf:
            quantization = self._detect_quantization(
                [{"path": item.get("path"), "role": "model"} for item in gguf]
            )
        elif any("qweight" in name or "gptq" in name for name in names):
            quantization = "GPTQ"
        elif any("awq" in name for name in names):
            quantization = "AWQ"
        return {
            "formats": sorted(
                {
                    "gguf" if gguf else "",
                    "safetensors" if safetensors else "",
                }
                - {""}
            ),
            "quantization": quantization,
            "gguf_files": gguf,
            "safetensors_files": safetensors,
            "metadata_files": [item for item in normalized if Path(str(item.get("path") or "")).name.lower() in _METADATA_NAMES],
            "unsafe_legacy_files": [
                item
                for item in normalized
                if Path(str(item.get("path") or "")).suffix.lower() in {".bin", ".pt", ".pth", ".pkl"}
            ],
        }

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(4 * 1024**2), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _detect_quantization(entries: list[JsonDict]) -> str:
        names = " ".join(str(item.get("path") or "").lower() for item in entries)
        match = re.search(r"(?:^|[-_.])(iq\d(?:_[a-z0-9]+)+|q\d(?:_[a-z0-9]+)+|q8_0)(?:[-_.]|$)", names)
        if match:
            return match.group(1).upper()
        if "gptq" in names:
            return "GPTQ"
        if "awq" in names:
            return "AWQ"
        return "unknown"


__all__ = ["ArtifactManifest"]
