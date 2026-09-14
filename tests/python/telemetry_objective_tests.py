from __future__ import annotations

import pytest

from rift.telemetry.objectives import ObjectiveEvaluator, normalize_objectives


def sample(at: float, **values):
    return {"observed_at": at, **values}


def test_normalize_objectives_accepts_target_alias_and_defaults():
    objectives = normalize_objectives([
        {"id": "latency", "metric": "inference.ttft_ms", "target": {"operator": "<=", "value": 500}},
    ])

    assert objectives == [{
        "id": "latency",
        "metric": "inference.ttft_ms",
        "operator": "<=",
        "threshold": 500.0,
        "aggregation": "latest",
        "window_seconds": 0.0,
        "consecutive_breaches": 1,
        "recovery_consecutive": 1,
        "warning_threshold": None,
        "recovery_threshold": None,
        "alerts": [],
    }]


def test_evaluator_aggregates_p95_and_reports_pass():
    evaluator = ObjectiveEvaluator(normalize_objectives([
        {"id": "ttft", "metric": "inference.ttft_ms", "aggregation": "p95", "operator": "<=", "threshold": 550, "window_seconds": 300},
    ]))

    for index, value in enumerate([100, 200, 300, 400, 450, 480, 490, 510, 520, 530], start=1):
        result = evaluator.evaluate(sample(float(index), **{"inference.ttft_ms": value}))[0]

    assert result["status"] == "pass"
    assert result["value"] == pytest.approx(530)
    assert result["sample_count"] == 10


def test_evaluator_marks_missing_metric_unknown_instead_of_passing():
    evaluator = ObjectiveEvaluator(normalize_objectives([
        {"id": "errors", "metric": "request.error_ratio", "operator": "<=", "threshold": 0.01},
    ]))

    result = evaluator.evaluate(sample(1.0))[0]

    assert result["status"] == "unknown"
    assert result["reason"] == "metric_unavailable"


def test_evaluator_requires_consecutive_breaches_and_recovers_with_hysteresis():
    evaluator = ObjectiveEvaluator(normalize_objectives([
        {
            "id": "temperature",
            "metric": "gpu_temperature_c",
            "operator": "<=",
            "threshold": 80,
            "warning_threshold": 75,
            "consecutive_breaches": 2,
            "recovery_threshold": 70,
            "recovery_consecutive": 2,
        },
    ]))

    assert evaluator.evaluate(sample(1, gpu_temperature_c=81))[0]["status"] == "pass"
    assert evaluator.evaluate(sample(2, gpu_temperature_c=82))[0]["status"] == "breach"
    assert evaluator.evaluate(sample(3, gpu_temperature_c=78))[0]["status"] == "warning"
    assert evaluator.evaluate(sample(4, gpu_temperature_c=69))[0]["status"] == "warning"
    assert evaluator.evaluate(sample(5, gpu_temperature_c=68))[0]["status"] == "pass"
    events = evaluator.events()
    assert [event["status"] for event in events if event["previous_status"] != "unknown"] == ["breach", "warning", "pass"]


def test_normalize_objectives_rejects_duplicate_ids_and_invalid_operator():
    with pytest.raises(ValueError, match="duplicate"):
        normalize_objectives([
            {"id": "same", "metric": "cpu_percent", "operator": ">=", "threshold": 1},
            {"id": "same", "metric": "cpu_percent", "operator": ">=", "threshold": 1},
        ])
    with pytest.raises(ValueError, match="operator"):
        normalize_objectives([{ "id": "bad", "metric": "cpu_percent", "operator": "~=", "threshold": 1 }])
