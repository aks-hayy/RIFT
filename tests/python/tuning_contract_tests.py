import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


def test_contract_hashes_are_stable_and_measurement_provenance_is_required():
    import pytest
    from rift.tuning_contracts import AcceptanceSpec, DeploymentIdentity, MeasurementRecord, TuningRequest

    identity = DeploymentIdentity("rev", "sha", "tok", "template", "vllm", "build", "native", "bf16", ("cuda:0",))
    req = TuningRequest("chat", "speed", "interactive", AcceptanceSpec("suite", "1", .9))
    assert len(identity.identity_hash) == 64
    assert req.request_hash == TuningRequest("chat", "speed", "interactive", AcceptanceSpec("suite", "1", .9)).request_hash
    with pytest.raises(ValueError):
        MeasurementRecord("tokens", 1, "tok/s", "benchmark", "now", "")
