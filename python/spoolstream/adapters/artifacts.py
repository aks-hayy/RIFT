"""Built-in model artifact adapters for remote metadata and local files."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Iterable

from .contracts import (
    ADAPTER_API_VERSION,
    AdapterManifest,
    ArtifactFile,
    ArtifactVariant,
    BackendCapability,
    JsonDict,
)
from .registry import AdapterRegistry


_METADATA_NAMES = {
    "config.json": "config",
    "generation_config.json": "generation_config",
    "tokenizer.json": "tokenizer",
    "tokenizer.model": "tokenizer",
    "spiece.model": "tokenizer",
    "vocab.json": "tokenizer_vocab",
    "merges.txt": "tokenizer_merges",
    "tokenizer_config.json": "tokenizer_config",
    "special_tokens_map.json": "special_tokens",
    "added_tokens.json": "special_tokens",
    "processor_config.json": "processor",
    "preprocessor_config.json": "processor",
    "chat_template.json": "chat_template",
    "chat_template.jinja": "chat_template",
    "model.safetensors.index.json": "weight_index",
    "quantize_config.json": "quantization_config",
    "quant_config.json": "quantization_config",
    "quantization_config.json": "quantization_config",
    "measurement.json": "quantization_measurement",
}


def source_from_candidate(candidate: JsonDict) -> JsonDict:
    files = []
    for item in candidate.get("siblings") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("rfilename") or item.get("path") or item.get("name") or "")
        if path:
            lfs = item.get("lfs") if isinstance(item.get("lfs"), dict) else {}
            oid = str(lfs.get("oid") or item.get("oid") or "")
            files.append(
                {
                    "path": path,
                    "size": item.get("size") or lfs.get("size"),
                    "sha256": oid.removeprefix("sha256:") if oid.startswith("sha256:") else None,
                    "etag": item.get("blobId") or item.get("etag"),
                }
            )
    return {
        "source": "huggingface",
        "repo_id": str(candidate.get("id") or candidate.get("modelId") or candidate.get("repo_id") or ""),
        "revision": candidate.get("sha") or candidate.get("revision"),
        "files": files,
        "config": candidate.get("config") or {},
        "tags": candidate.get("tags") or [],
        "library_name": candidate.get("library_name"),
        "safetensors": candidate.get("safetensors"),
        "json_documents": candidate.get("json_documents") or candidate.get("file_documents") or {},
    }


def source_from_local(path: str | Path) -> JsonDict:
    root = Path(path)
    if not root.exists():
        raise ValueError(f"artifact source does not exist: {root}")
    paths = [root] if root.is_file() else sorted(item for item in root.rglob("*") if item.is_file())
    files = []
    json_documents: JsonDict = {}
    for item in paths:
        relative = item.name if root.is_file() else item.relative_to(root).as_posix()
        size = int(item.stat().st_size)
        files.append({"path": relative, "size": size})
        if item.suffix.lower() == ".json" and size <= 2 * 1024**2:
            try:
                json_documents[relative] = json.loads(item.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                pass
    config = {}
    config_path = root.parent / "config.json" if root.is_file() else root / "config.json"
    if config_path.is_file():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            config = {}
    return {
        "source": "local",
        "path": str(root.resolve()),
        "repo_id": None,
        "revision": None,
        "files": files,
        "config": config,
        "tags": [],
        "json_documents": json_documents,
    }


class BaseArtifactAdapter:
    adapter_api_version = ADAPTER_API_VERSION
    adapter_id = "artifact-base"
    artifact_format = "unknown"
    quantization: str | None = None
    backend_hints: tuple[str, ...] = ()

    def __init__(self) -> None:
        self.manifest = AdapterManifest(
            adapter_id=self.adapter_id,
            display_name=self.adapter_id,
            upstream_project="RIFT",
            adapter_version="1.0.0",
            adapter_api_version=ADAPTER_API_VERSION,
            kind="artifact",
            capability=BackendCapability(tasks=("artifact-inspection",), formats=(self.artifact_format,)),
            evidence_status="verified_test",
        )

    def resolve_files(self, variant: ArtifactVariant) -> list[JsonDict]:
        return [item.to_dict() for item in variant.files]

    def validate(self, variant: ArtifactVariant) -> JsonDict:
        required = [item for item in variant.files if item.required]
        invalid = [item.path for item in required if not item.path or item.size == 0]
        roles = {item.role for item in variant.files}
        missing_dependencies: list[str] = []
        serving_warnings: list[str] = []
        if variant.metadata.get("complete") is False:
            missing_dependencies.extend(str(item) for item in variant.metadata.get("missing_shards") or [])
            if not variant.metadata.get("missing_shards"):
                missing_dependencies.append("one or more declared artifact shards")
        if variant.format != "gguf":
            if "config" not in roles:
                missing_dependencies.append("config.json")
            tokenizer_available = bool(
                roles.intersection({"tokenizer", "tokenizer_vocab"})
            )
            if not tokenizer_available:
                missing_dependencies.append("tokenizer.json/tokenizer.model/vocab.json")
            elif "tokenizer_vocab" in roles and "tokenizer_merges" not in roles:
                serving_warnings.append("vocab.json is present without merges.txt; tokenizer compatibility requires inspection")
        if variant.metadata.get("multimodal"):
            if variant.format == "gguf" and "multimodal_projection" not in roles:
                missing_dependencies.append("multimodal projection GGUF")
            if variant.format != "gguf" and "processor" not in roles:
                missing_dependencies.append("processor_config.json/preprocessor_config.json")
        missing_shards = list(variant.metadata.get("missing_shards") or [])
        if missing_shards:
            missing_dependencies.extend(missing_shards)
        if variant.metadata.get("sharded") and not variant.metadata.get("index_present"):
            if variant.metadata.get("shard_naming_complete"):
                serving_warnings.append("shards are filename-complete but no SafeTensors index was supplied")
            else:
                serving_warnings.append("multiple SafeTensors files have no parsed index; exact tensor routing is unverified")
        hashes = [item for item in required if item.sha256]
        integrity = (
            "HASHED_COMPLETE"
            if required and len(hashes) == len(required)
            else "HASHED_PARTIAL"
            if hashes
            else "UNVERIFIED"
        )
        missing_dependencies = list(dict.fromkeys(missing_dependencies))
        serving_ready = bool(required) and not invalid and not missing_dependencies
        return {
            "valid": bool(required)
            and not invalid
            and not missing_shards
            and variant.metadata.get("complete") is not False,
            "serving_ready": serving_ready,
            "required_file_count": len(required),
            "size_known": variant.size_known,
            "invalid_files": invalid,
            "missing_dependencies": missing_dependencies,
            "warnings": serving_warnings,
            "integrity_status": integrity,
            "hashed_required_files": len(hashes),
            "exact_revision": bool(variant.revision),
        }

    def estimate_resources(self, variant: ArtifactVariant, hardware: JsonDict) -> JsonDict:
        weight_bytes = int(variant.total_bytes or 0)
        total_download_bytes = int(variant.metadata.get("total_download_bytes") or weight_bytes or 0)
        vram = int(hardware.get("total_vram_bytes") or (hardware.get("capacity") or {}).get("vram_bytes") or 0)
        ram = int(hardware.get("total_host_ram_bytes") or (hardware.get("capacity") or {}).get("host_ram_bytes") or 0)
        context_length = int(hardware.get("context_length") or 8192)
        concurrency = int(hardware.get("concurrency") or 1)
        model_config = variant.metadata.get("model_config") if isinstance(variant.metadata.get("model_config"), dict) else {}
        layers = int(model_config.get("num_hidden_layers") or model_config.get("n_layer") or 0)
        hidden = int(model_config.get("hidden_size") or model_config.get("n_embd") or 0)
        attention_heads = int(model_config.get("num_attention_heads") or model_config.get("n_head") or 0)
        kv_heads = int(model_config.get("num_key_value_heads") or attention_heads or 0)
        head_dim = int(model_config.get("head_dim") or (hidden // attention_heads if hidden and attention_heads else 0))
        kv_bytes = (
            2 * layers * context_length * kv_heads * head_dim * 2 * concurrency
            if layers and kv_heads and head_dim
            else None
        )
        runtime_overhead = max(512 * 1024**2, int(weight_bytes * 0.08)) if weight_bytes else None
        recommended_vram = weight_bytes + int(kv_bytes or 0) + int(runtime_overhead or 0) if weight_bytes else None
        return {
            "weight_bytes": weight_bytes or None,
            "minimum_disk_bytes": total_download_bytes or None,
            "estimated_runtime_overhead_bytes": runtime_overhead,
            "estimated_kv_cache_bytes": kv_bytes,
            "recommended_vram_bytes": recommended_vram,
            "context_length": context_length,
            "concurrency": concurrency,
            "fits_vram_weights_only": None if not weight_bytes or not vram else weight_bytes <= int(vram * 0.85),
            "fits_host_ram_weights_only": None if not weight_bytes or not ram else weight_bytes <= int(ram * 0.65),
            "fits_recommended_vram": None if not recommended_vram or not vram else recommended_vram <= int(vram * 0.90),
            "estimate_boundary": (
                "Static estimator using exact artifact bytes when available and config-derived FP16 KV cache. "
                "Backend allocator overhead and platform-specific KV dtypes are resolved during planning."
            ),
        }

    def compatible_backends(self, variant: ArtifactVariant) -> tuple[str, ...]:
        del variant
        return self.backend_hints

    def _metadata_files(self, source: JsonDict) -> list[ArtifactFile]:
        result = []
        for item in _files(source):
            name = Path(item["path"]).name.lower()
            role = _METADATA_NAMES.get(name)
            if role:
                result.append(
                    ArtifactFile(
                        item["path"],
                        item["size"],
                        role,
                        required=False,
                        sha256=item.get("sha256"),
                        etag=item.get("etag"),
                    )
                )
        return result

    def _variant(
        self,
        source: JsonDict,
        *,
        artifact_id: str,
        model_files: list[ArtifactFile],
        quantization: str | None = None,
        metadata: JsonDict | None = None,
    ) -> ArtifactVariant:
        files = tuple([*model_files, *self._metadata_files(source)])
        model_sizes = [item.size for item in model_files]
        size_known = bool(model_files) and all(isinstance(item, int) for item in model_sizes)
        total = sum(int(item or 0) for item in model_sizes) if size_known else None
        all_sizes_known = all(isinstance(item.size, int) for item in files)
        total_download_bytes = (
            sum(int(item.size or 0) for item in files) if all_sizes_known else None
        )
        config = source.get("config") if isinstance(source.get("config"), dict) else {}
        architecture = config.get("model_type")
        if not architecture:
            architectures = config.get("architectures") or []
            architecture = architectures[0] if isinstance(architectures, list) and architectures else None
        provisional = ArtifactVariant(
            artifact_id=artifact_id,
            format=self.artifact_format,
            quantization=quantization if quantization is not None else self.quantization,
            files=files,
            total_bytes=total,
            size_known=size_known,
            source=str(source.get("source") or "unknown"),
            repo_id=source.get("repo_id"),
            revision=source.get("revision"),
            architecture=str(architecture).lower() if architecture else None,
            metadata={
                **dict(metadata or {}),
                "weight_bytes": (
                    sum(int(item.size or 0) for item in model_files)
                    if all(isinstance(item.size, int) for item in model_files)
                    else None
                ),
                "dependency_bytes": (
                    sum(int(item.size or 0) for item in files if item.role != "weights")
                    if all_sizes_known
                    else None
                ),
                "total_download_bytes": total_download_bytes,
                "dependency_roles": sorted({item.role for item in files}),
                "model_config": _resource_model_config(config),
                "quantization_method": _quantization_method(source),
                "multimodal": _is_multimodal(source),
            },
        )
        return ArtifactVariant(**{**provisional.__dict__, "validation": self.validate(provisional)})


class GgufArtifactAdapter(BaseArtifactAdapter):
    adapter_id = "artifact-gguf"
    artifact_format = "gguf"
    backend_hints = ("llama.cpp",)

    def detect(self, source: JsonDict) -> bool:
        return any(item["path"].lower().endswith(".gguf") and "mmproj" not in item["path"].lower() for item in _files(source))

    def inspect(self, source: JsonDict) -> list[ArtifactVariant]:
        groups: dict[str, JsonDict] = {}
        multimodal = _is_multimodal(source)
        mmproj = [item for item in _files(source) if item["path"].lower().endswith(".gguf") and "mmproj" in item["path"].lower()]
        for item in _files(source):
            path = item["path"]
            if not path.lower().endswith(".gguf") or "mmproj" in path.lower():
                continue
            shard = re.match(r"^(.*?)-(\d{5})-of-(\d{5})\.gguf$", path, re.IGNORECASE)
            key = path
            index = 1
            total = 1
            if shard:
                key = f"{shard.group(1)}-of-{shard.group(3)}"
                index = int(shard.group(2))
                total = int(shard.group(3))
            group = groups.setdefault(key, {"files": [], "seen": set(), "total": total})
            group["files"].append(
                ArtifactFile(path, item["size"], "weights", sha256=item.get("sha256"), etag=item.get("etag"))
            )
            group["seen"].add(index)
        variants = []
        for key, group in groups.items():
            model_files = sorted(group["files"], key=lambda item: item.path)
            complete = len(group["seen"]) == int(group["total"])
            missing = [
                f"{key}:shard-{index:05d}-of-{int(group['total']):05d}"
                for index in range(1, int(group["total"]) + 1)
                if index not in group["seen"]
            ]
            if mmproj:
                model_files.extend(
                    ArtifactFile(
                        item["path"],
                        item["size"],
                        "multimodal_projection",
                        required=multimodal,
                        sha256=item.get("sha256"),
                        etag=item.get("etag"),
                    )
                    for item in mmproj
                )
            variants.append(
                self._variant(
                    source,
                    artifact_id=f"gguf:{key}",
                    model_files=model_files,
                    quantization=_gguf_quantization(key),
                    metadata={
                        "complete": complete,
                        "shard_count": group["total"],
                        "missing_shards": missing,
                        "multimodal": multimodal,
                    },
                )
            )
        return variants


class QuantizedSafetensorsArtifactAdapter(BaseArtifactAdapter):
    markers: tuple[str, ...] = ()

    def detect(self, source: JsonDict) -> bool:
        return _has_safetensors(source) and self._matches(source)

    def _matches(self, source: JsonDict) -> bool:
        method = _quantization_method(source)
        if method:
            normalized = {item.replace("-", "").replace("_", "") for item in self.markers}
            if method.replace("-", "").replace("_", "") in normalized:
                return True
        corpus = _source_corpus(source)
        return any(marker in corpus for marker in self.markers)

    def inspect(self, source: JsonDict) -> list[ArtifactVariant]:
        weights = [
            ArtifactFile(
                item["path"],
                item["size"],
                "weights",
                sha256=item.get("sha256"),
                etag=item.get("etag"),
            )
            for item in _files(source)
            if item["path"].lower().endswith(".safetensors")
        ]
        if not weights:
            return []
        return [
            self._variant(
                source,
                artifact_id=f"{self.artifact_format}:{source.get('repo_id') or source.get('path') or 'local'}",
                model_files=weights,
                metadata=_safetensors_layout_metadata(source, weights),
            )
        ]


class AwqArtifactAdapter(QuantizedSafetensorsArtifactAdapter):
    adapter_id = "artifact-awq"
    artifact_format = "awq"
    quantization = "AWQ"
    markers = ("awq",)
    backend_hints = ("vllm", "sglang")


class GptqArtifactAdapter(QuantizedSafetensorsArtifactAdapter):
    adapter_id = "artifact-gptq"
    artifact_format = "gptq"
    quantization = "GPTQ"
    markers = ("gptq", "gptqmodel")
    backend_hints = ("vllm", "sglang")


class Fp8ArtifactAdapter(QuantizedSafetensorsArtifactAdapter):
    adapter_id = "artifact-fp8"
    artifact_format = "fp8"
    quantization = "FP8"
    markers = ("fp8", "float8")
    backend_hints = ("vllm", "sglang")


class Exl2ArtifactAdapter(QuantizedSafetensorsArtifactAdapter):
    adapter_id = "artifact-exl2"
    artifact_format = "exl2"
    quantization = "EXL2"
    markers = ("exl2", "exllamav2")
    backend_hints = ()


class MlxArtifactAdapter(QuantizedSafetensorsArtifactAdapter):
    adapter_id = "artifact-mlx"
    artifact_format = "mlx"
    quantization = "MLX"
    markers = ("mlx-community", "mlx_lm", "mlx-lm", '"quantization"')
    backend_hints = ("mlx-lm",)

    def _matches(self, source: JsonDict) -> bool:
        repo_id = str(source.get("repo_id") or "").lower()
        tags = {str(item).lower() for item in source.get("tags") or []}
        config = source.get("config") if isinstance(source.get("config"), dict) else {}
        return "mlx-community/" in repo_id or "mlx" in tags or "quantization" in config and "bits" in config


class SafetensorsArtifactAdapter(BaseArtifactAdapter):
    adapter_id = "artifact-safetensors"
    artifact_format = "safetensors"
    backend_hints = ("vllm", "sglang")

    def detect(self, source: JsonDict) -> bool:
        if not _has_safetensors(source):
            return False
        return not any(adapter.detect(source) for adapter in _specialized_safetensors())

    def inspect(self, source: JsonDict) -> list[ArtifactVariant]:
        weights = [
            ArtifactFile(
                item["path"],
                item["size"],
                "weights",
                sha256=item.get("sha256"),
                etag=item.get("etag"),
            )
            for item in _files(source)
            if item["path"].lower().endswith(".safetensors")
        ]
        config = source.get("config") if isinstance(source.get("config"), dict) else {}
        dtype = str(config.get("torch_dtype") or "").lower()
        quantization = dtype.upper() if dtype in {"float16", "bfloat16", "float32"} else None
        return [
            self._variant(
                source,
                artifact_id=f"safetensors:{source.get('repo_id') or source.get('path') or 'local'}",
                model_files=weights,
                quantization=quantization,
                metadata=_safetensors_layout_metadata(source, weights),
            )
        ] if weights else []


class ArtifactAdapterHost(AdapterRegistry):
    def resolve(self, source: JsonDict) -> list[ArtifactVariant]:
        variants: list[ArtifactVariant] = []
        seen: set[str] = set()
        for adapter in self.enabled().values():
            if not adapter.detect(source):
                continue
            for variant in adapter.inspect(source):
                if variant.artifact_id not in seen:
                    variants.append(variant)
                    seen.add(variant.artifact_id)
        variants.sort(key=lambda item: (item.format, item.quantization or "", item.artifact_id))
        return variants


def builtin_artifact_adapters() -> tuple[BaseArtifactAdapter, ...]:
    return (
        GgufArtifactAdapter(),
        AwqArtifactAdapter(),
        GptqArtifactAdapter(),
        Fp8ArtifactAdapter(),
        Exl2ArtifactAdapter(),
        MlxArtifactAdapter(),
        SafetensorsArtifactAdapter(),
    )


def artifact_adapter_host(*, disabled: Iterable[str] = (), load_entry_points: bool = True) -> ArtifactAdapterHost:
    return ArtifactAdapterHost(
        builtins=builtin_artifact_adapters(),
        entry_point_group="rift.artifact_adapters",
        disabled=disabled,
        load_entry_points=load_entry_points,
    )


def _specialized_safetensors() -> tuple[QuantizedSafetensorsArtifactAdapter, ...]:
    return (AwqArtifactAdapter(), GptqArtifactAdapter(), Fp8ArtifactAdapter(), Exl2ArtifactAdapter(), MlxArtifactAdapter())


def _files(source: JsonDict) -> list[JsonDict]:
    result = []
    for item in source.get("files") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or item.get("rfilename") or item.get("name") or "")
        if not path:
            continue
        size = item.get("size")
        result.append(
            {
                "path": path,
                "size": int(size) if isinstance(size, int) and size >= 0 else None,
                "sha256": item.get("sha256"),
                "etag": item.get("etag"),
            }
        )
    return result


def _has_safetensors(source: JsonDict) -> bool:
    return any(item["path"].lower().endswith(".safetensors") for item in _files(source))


def _source_corpus(source: JsonDict) -> str:
    config = source.get("config") or {}
    return " ".join(
        [
            str(source.get("repo_id") or ""),
            " ".join(str(item) for item in source.get("tags") or []),
            json.dumps(config, sort_keys=True, default=str),
            " ".join(item["path"] for item in _files(source)),
        ]
    ).lower()


def _gguf_quantization(path: str) -> str | None:
    match = re.search(r"(?:^|[-.])(iq\d(?:_[a-z0-9]+)+|q\d(?:_[a-z0-9]+)+|bf16|f16)(?:[-.]|$)", path.lower())
    return match.group(1).upper() if match else None


def _safetensors_layout_metadata(source: JsonDict, weights: list[ArtifactFile]) -> JsonDict:
    documents = source.get("json_documents") if isinstance(source.get("json_documents"), dict) else {}
    index = next(
        (
            value
            for path, value in documents.items()
            if Path(str(path)).name.lower() == "model.safetensors.index.json"
        ),
        None,
    )
    expected: set[str] = set()
    if isinstance(index, dict) and isinstance(index.get("weight_map"), dict):
        expected = {str(item) for item in index["weight_map"].values() if item}
    present = {item.path for item in weights}
    missing = sorted(expected - present)
    declared_totals: set[int] = set()
    declared_indices: set[int] = set()
    for item in weights:
        match = re.search(r"-(\d{5})-of-(\d{5})\.safetensors$", item.path, re.IGNORECASE)
        if match:
            declared_indices.add(int(match.group(1)))
            declared_totals.add(int(match.group(2)))
    shard_naming_complete = False
    if len(declared_totals) == 1:
        declared_total = next(iter(declared_totals))
        shard_naming_complete = declared_indices == set(range(1, declared_total + 1))
        if not shard_naming_complete and not expected:
            missing.extend(
                f"SafeTensors shard {index:05d}-of-{declared_total:05d}"
                for index in range(1, declared_total + 1)
                if index not in declared_indices
            )
    elif len(declared_totals) > 1:
        missing.append("inconsistent SafeTensors shard totals")
    index_present = any(
        Path(item["path"]).name.lower() == "model.safetensors.index.json"
        for item in _files(source)
    )
    return {
        "sharded": len(weights) > 1 or bool(expected),
        "shard_count": len(weights),
        "index_present": index_present,
        "index_parsed": bool(expected),
        "expected_shard_count": len(expected) if expected else None,
        "shard_naming_complete": shard_naming_complete,
        "complete": not missing,
        "missing_shards": list(dict.fromkeys(missing)),
    }


def _quantization_method(source: JsonDict) -> str | None:
    config = source.get("config") if isinstance(source.get("config"), dict) else {}
    candidates: list[Any] = [config.get("quant_method"), config.get("quantization_method")]
    quantization = config.get("quantization_config") or config.get("quantization")
    if isinstance(quantization, dict):
        candidates.extend(
            [
                quantization.get("quant_method"),
                quantization.get("method"),
                quantization.get("quantization_method"),
            ]
        )
    documents = source.get("json_documents") if isinstance(source.get("json_documents"), dict) else {}
    for path, document in documents.items():
        if Path(str(path)).name.lower() not in {
            "quantize_config.json",
            "quant_config.json",
            "quantization_config.json",
        }:
            continue
        if isinstance(document, dict):
            candidates.extend(
                [
                    document.get("quant_method"),
                    document.get("method"),
                    document.get("quantization_method"),
                ]
            )
    dtype = str(config.get("torch_dtype") or config.get("dtype") or "").lower()
    if dtype.startswith(("float8", "fp8")):
        candidates.append("fp8")
    for candidate in candidates:
        if candidate:
            return str(candidate).strip().lower()
    return None


def _is_multimodal(source: JsonDict) -> bool:
    tags = {str(item).strip().lower() for item in source.get("tags") or []}
    if tags.intersection(
        {
            "image-text-to-text",
            "image-to-text",
            "visual-question-answering",
            "vision-language",
            "multimodal",
        }
    ):
        return True
    config = source.get("config") if isinstance(source.get("config"), dict) else {}
    model_type = str(config.get("model_type") or "").lower()
    architectures = " ".join(str(item).lower() for item in config.get("architectures") or [])
    return any(token in f"{model_type} {architectures}" for token in ("vision", "vl", "llava", "mllama"))


def _resource_model_config(config: JsonDict) -> JsonDict:
    keys = (
        "model_type",
        "architectures",
        "hidden_size",
        "n_embd",
        "num_hidden_layers",
        "n_layer",
        "num_attention_heads",
        "n_head",
        "num_key_value_heads",
        "head_dim",
        "max_position_embeddings",
        "torch_dtype",
    )
    return {key: config[key] for key in keys if key in config}


__all__ = [
    "ArtifactAdapterHost",
    "AwqArtifactAdapter",
    "Exl2ArtifactAdapter",
    "Fp8ArtifactAdapter",
    "GgufArtifactAdapter",
    "GptqArtifactAdapter",
    "MlxArtifactAdapter",
    "SafetensorsArtifactAdapter",
    "artifact_adapter_host",
    "builtin_artifact_adapters",
    "source_from_candidate",
    "source_from_local",
]
