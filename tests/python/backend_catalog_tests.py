from __future__ import annotations

import json
from pathlib import Path

import pytest

from rift.backends import BackendCatalog, BackendCatalogError, BackendManifest


def test_builtin_manifests_are_discoverable() -> None:
    catalog = BackendCatalog.discover()
    assert set(catalog.manifests()) == {"llama.cpp", "vllm", "sglang", "mlx-lm"}
    assert all(item.adapter_api_version == "1.0" for item in catalog.manifests().values())


@pytest.mark.parametrize("backend_id", ["llama.cpp", "vllm", "sglang", "mlx-lm"])
def test_builtin_backend_is_loaded_lazily(backend_id: str) -> None:
    provider = BackendCatalog.discover().load(backend_id)
    assert provider.name == backend_id
    assert provider.manifest.adapter_id == backend_id
    assert callable(provider.plan_launch)
    assert callable(provider.tune_candidates)


def test_disabled_backend_is_not_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RIFT_DISABLED_ADAPTERS", "vllm")
    catalog = BackendCatalog.discover()
    assert "vllm" not in catalog.manifests()
    with pytest.raises(BackendCatalogError):
        catalog.load("vllm")


def test_invalid_manifest_is_reported(tmp_path: Path) -> None:
    folder = tmp_path / "bad"
    folder.mkdir()
    (folder / "__init__.py").write_text("", encoding="utf-8")
    (folder / "manifest.json").write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    catalog = BackendCatalog.discover(tmp_path)
    assert catalog.manifests() == {}
    assert any("missing" in item for item in catalog.diagnostics()["host_diagnostics"])


def test_manifest_round_trip() -> None:
    manifest = BackendManifest.from_file(Path("python/rift/backends/llama_cpp/manifest.json"))
    payload = manifest.to_dict()
    assert payload["backend_id"] == "llama.cpp"
    assert "speed" in payload["tuning_profiles"]
    assert {item["name"] for item in payload["tuning_parameters"]} >= {"batch", "gpu_layers", "cache_type_k"}
    assert payload["module"] == "rift.backends.llama_cpp.backend"
