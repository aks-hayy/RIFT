import base64
import json
import sys
import tempfile
import time
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

fake_core = types.ModuleType("rift._core")
fake_core.InferenceEngine = object
fake_core.__version__ = "test"
fake_core.build_info = lambda: {"version": "test"}
fake_core.cuda_device_count = lambda: 0
fake_core.inspect_model = lambda *args, **kwargs: {}
fake_core.parse_model_topology = lambda *args, **kwargs: {}
sys.modules["rift._core"] = fake_core


def signed_snapshot(root: Path, *, unsigned: bool = False, malformed: bool = False) -> Path:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    now = time.time()
    payload = {
        "source_id": "leaderboard-snapshot",
        "observed_unix_seconds": now,
        "records": [
            {
                "subject": "org/model",
                "model_revision": "abc123",
                "artifact_id": "model-q4.gguf",
                "benchmark": "arena",
                "task": "chat",
                "metric": "preference_score",
                "value": 0.81,
                "normalized_value": 0.81,
                "relation": "direct",
                "confidence": 0.92,
                "provenance": "published",
                "source": "arena",
                "claim": "Published preference score.",
            }
        ],
    }
    if malformed:
        payload["records"][0]["normalized_value"] = "not-a-number"
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes_raw()
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    envelope = {"payload": payload}
    if not unsigned:
        envelope["signature"] = {
            "algorithm": "ed25519",
            "key_id": "test-key",
            "value": base64.b64encode(private_key.sign(canonical)).decode("ascii"),
        }
        (root / "trusted-keys.json").write_text(
            json.dumps(
                {
                    "keys": [
                        {
                            "id": "test-key",
                            "public_key": base64.b64encode(public_key).decode("ascii"),
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
    path = root / "snapshot.json"
    path.write_text(json.dumps(envelope), encoding="utf-8")
    return path


def test_typed_record_round_trip_and_aggregation() -> None:
    from rift.evidence import EvidenceLevel, EvidenceRecord, aggregate_quality_evidence

    record = EvidenceRecord(
        level=EvidenceLevel.CURATED_EVALUATION,
        subject="org/model",
        claim="EvalPlus pass rate.",
        source="evalplus",
        benchmark="evalplus",
        task="coding",
        metric="pass_at_1",
        value=0.72,
        normalized_value=0.72,
        observed_unix_seconds=time.time(),
        model_revision="abc123",
        artifact_id="model-q4.gguf",
        backend="llama.cpp",
        hardware_fingerprint="published-cpu",
        relation="direct",
        confidence=0.9,
        provenance="published",
    )
    restored = EvidenceRecord.from_dict(record.to_dict())
    assert restored == record
    result = aggregate_quality_evidence([record], "coding")
    assert result["score"] == 0.72
    assert result["coverage"] == 1
    assert result["published_records"] == 1
    assert result["claim_boundary"] == "published_quality_evidence"


def test_signed_json_source_accepts_valid_records_and_rejects_unsigned() -> None:
    from rift.evidence_sources import JsonEvidenceSource

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        valid = signed_snapshot(root)
        source = JsonEvidenceSource(
            valid,
            "leaderboard-snapshot",
            trusted_keys_path=root / "trusted-keys.json",
        )
        records = source.load()
        assert len(records) == 1
        assert records[0].benchmark == "arena"
        assert records[0].normalized_value == 0.81
        assert source.diagnostics()["verified"] is True

        unsigned = signed_snapshot(root, unsigned=True)
        rejected = JsonEvidenceSource(
            unsigned,
            "leaderboard-snapshot",
            trusted_keys_path=root / "trusted-keys.json",
        )
        assert rejected.load() == []
        assert rejected.diagnostics()["verified"] is False


def test_json_source_rejects_malformed_numeric_records() -> None:
    from rift.evidence_sources import JsonEvidenceSource

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = signed_snapshot(root, malformed=True)
        source = JsonEvidenceSource(
            path,
            "leaderboard-snapshot",
            trusted_keys_path=root / "trusted-keys.json",
        )
        assert source.load() == []
        assert "numeric" in source.diagnostics()["reason"]


def main() -> None:
    test_typed_record_round_trip_and_aggregation()
    test_signed_json_source_accepts_valid_records_and_rejects_unsigned()
    test_json_source_rejects_malformed_numeric_records()
    print("evidence_tests: PASS")


if __name__ == "__main__":
    main()
