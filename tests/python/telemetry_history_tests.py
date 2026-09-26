"""History/transaction regressions; synthetic values are not hardware evidence."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))
from rift.telemetry.store import TelemetryStore


@pytest.fixture
def store():
    value = TelemetryStore(":memory:")
    yield value
    value.close()


def test_latest_is_newest_even_with_out_of_order_observations(store):
    session = store.start_session("chat")["session_id"]
    for at in (100, 300, 200):
        store.record_sample(session, {"observed_at": at, "cpu_percent": at / 10})
    assert store.series(session, limit=1)["samples"][0]["observed_at"] == 100
    assert store.series(session, limit=1, latest=True)["samples"][0]["observed_at"] == 300
    assert store.series(session, limit=1)["truncated"]


def test_history_has_null_gaps_and_preserves_zero(store):
    for at, value in ((0, 0), (1, 20), (5, None), (8, 80)):
        store.record_sample("session", {"observed_at": at, "cpu_percent": value})
    history = store.history("session", metric="cpu_percent", since=0, until=10, buckets=5)
    assert history["points"][0] == {"observed_at": 0, "count": 2, "mean": 10, "minimum": 0, "maximum": 20}
    assert history["points"][2]["mean"] is None
    assert history["points"][2]["count"] == 0
    assert history["points"][4]["maximum"] == 80


def test_history_does_not_aggregate_distinct_service_sessions(store):
    store.record_sample("a", {"observed_at": 1, "gpu_power_watts": 10})
    store.record_sample("b", {"observed_at": 1, "gpu_power_watts": 90})
    assert store.history("a", metric="gpu_power_watts", since=0, until=10, buckets=1)["points"][0]["mean"] == 10


@pytest.mark.parametrize("options", [
    {"metric": "p95"}, {"buckets": 0}, {"buckets": 1201},
    {"until": float("nan")}, {"since": 20}, {"until": 48 * 3600 + 1},
])
def test_history_rejects_unbounded_or_unsupported_queries(store, options):
    with pytest.raises(ValueError):
        store.history("a", **({"metric": "cpu_percent", "since": 0, "until": 10} | options))


def test_finished_report_includes_samples_beyond_api_page(store):
    session = store.start_session("chat", started_at=0)["session_id"]
    store.connection.executemany(
        "INSERT INTO samples VALUES(?,?,?,?)",
        ((session, i + 1, i, json.dumps({"cpu_percent": 99 if i == 20000 else 1})) for i in range(20001)),
    )
    store.connection.commit()
    report = store.finish_session(session, stopped_at=20001, status="interrupted")
    assert report["sample_count"] == 20001
    assert report["metrics"]["cpu_percent"]["maximum"] == 99
    assert report["status"] == "interrupted"


def test_parallel_writers_cannot_clobber_sequence_or_identity(store):
    def write(i):
        return store.record_sample("real", {"observed_at": i, "sequence": -1, "session_id": "fake"})
    with ThreadPoolExecutor(max_workers=8) as executor:
        points = list(executor.map(write, range(100)))
    assert {point["sequence"] for point in points} == set(range(1, 101))
    assert {point["session_id"] for point in points} == {"real"}
    assert len(store.series("real")["samples"]) == 100


def test_nonfinite_sample_rejected_without_poisoning_transaction(store):
    with pytest.raises(ValueError):
        store.record_sample("a", {"observed_at": 1, "cpu_percent": float("nan")})
    assert store.record_sample("a", {"observed_at": 1, "cpu_percent": 0})["sequence"] == 1


def test_history_api_returns_same_recorded_buckets(store, tmp_path):
    from rift.server import RiftServerRuntime
    from rift.operations import OperationStore
    store.record_sample("a", {"observed_at": 2, "cpu_percent": 42})
    class Controller:
        telemetry_store = store
    runtime = RiftServerRuntime(orchestrator_factory=Controller, operation_store=OperationStore(tmp_path / "operations"))
    try:
        result = runtime.control_get("/api/rift/v2/telemetry/history", {"session_id": ["a"], "since": ["0"], "until": ["10"], "buckets": ["1"]})
        assert result["points"][0]["mean"] == 42
        with pytest.raises(ValueError):
            runtime.control_get("/api/rift/v2/telemetry/history")
    finally:
        runtime.shutdown()
