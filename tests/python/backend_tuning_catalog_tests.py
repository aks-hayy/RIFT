from __future__ import annotations

from rift.backends import BackendCatalog


def test_folder_tuning_adapters_are_available_for_qualified_backends() -> None:
    catalog = BackendCatalog.discover()
    for backend_id in ("llama.cpp", "vllm"):
        provider = catalog.load(backend_id)
        adapter = catalog.load_tuning_adapter(backend_id, provider)
        assert adapter is not None
        assert adapter.backend == backend_id


def test_backends_without_tuning_module_report_none() -> None:
    catalog = BackendCatalog.discover()
    for backend_id in ("sglang", "mlx-lm"):
        assert catalog.load_tuning_adapter(backend_id, catalog.load(backend_id)) is None
