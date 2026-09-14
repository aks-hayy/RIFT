from __future__ import annotations

import pytest

from rift.orchestrator import RiftOrchestrator


def test_objective_metrics_are_added_to_effective_collection_selection(tmp_path):
    orchestrator = RiftOrchestrator(root=tmp_path)
    config = orchestrator.default_config()
    service = config["services"]["chat"]
    service["monitoring"]["objectives"] = [{
        "id": "gpu-temp",
        "metric": "gpu_temperature_c",
        "operator": "<=",
        "threshold": 85,
    }]

    effective = orchestrator._effective_telemetry_resources(service, config=config)

    assert "gpu_temperature_c" in effective["metrics"]
    assert effective["profile"] == "default"


def test_validate_config_rejects_malformed_objective(tmp_path):
    orchestrator = RiftOrchestrator(root=tmp_path)
    config = orchestrator.default_config()
    config["services"]["chat"]["monitoring"]["objectives"] = [{
        "id": "bad",
        "metric": "gpu_temperature_c",
        "operator": "~=",
        "threshold": 85,
    }]

    with pytest.raises(ValueError, match="operator"):
        orchestrator.validate_config(config)
