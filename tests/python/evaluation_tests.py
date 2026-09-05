import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


def test_default_suite_is_bounded_and_explicit():
    from rift.evaluation import default_evaluation_suite

    suite = default_evaluation_suite()
    assert suite.version == "1"
    assert len(suite.cases) == 5
    assert all(case.prompt and case.kind for case in suite.cases)
    assert all("What is RIFT?" not in case.prompt for case in suite.cases)


def test_evaluation_uses_deterministic_checks_and_preserves_case_results():
    from rift.evaluation import EvaluationSuite, evaluate_suite

    suite = EvaluationSuite.from_mapping(
        {
            "id": "test-suite",
            "version": "1",
            "cases": [
                {"id": "exact", "prompt": "one", "kind": "exact", "expected": "yes"},
                {"id": "json", "prompt": "two", "kind": "json", "expected": {"ok": True}},
                {"id": "bad", "prompt": "three", "kind": "contains", "expected": "needle"},
            ],
        }
    )
    responses = {"one": "yes", "two": '{"ok": true}', "three": "no"}
    result = evaluate_suite(suite, lambda prompt, max_tokens: responses[prompt])
    assert result.status == "completed"
    assert result.summary == {"pass": 2, "fail": 1, "not_assessed": 0, "error": 0}
    assert [case.status for case in result.cases] == ["pass", "pass", "fail"]


def test_evaluation_deadline_marks_remaining_cases_not_assessed():
    from rift.evaluation import EvaluationSuite, evaluate_suite

    suite = EvaluationSuite.from_mapping(
        {
            "id": "deadline",
            "version": "1",
            "cases": [
                {"id": "one", "prompt": "one", "kind": "exact", "expected": "yes"},
                {"id": "two", "prompt": "two", "kind": "exact", "expected": "yes"},
            ],
        }
    )
    calls = []

    def invoke(prompt, max_tokens):
        calls.append((prompt, max_tokens))
        return "yes"

    result = evaluate_suite(suite, invoke, total_deadline_seconds=0.0)
    assert result.status == "deadline"
    assert result.summary["not_assessed"] == 2
    assert calls == []


def test_judge_assessment_is_separate_and_schema_validated():
    from rift.evaluation import EvaluationSuite, evaluate_suite

    suite = EvaluationSuite.from_mapping(
        {
            "id": "judge",
            "version": "1",
            "cases": [{"id": "one", "prompt": "one", "kind": "exact", "expected": "yes"}],
        }
    )
    result = evaluate_suite(
        suite,
        lambda _prompt, _max_tokens: "yes",
        judge=lambda _case, _response, _max_tokens: {
            "score": 0.8,
            "rationale": "The response satisfies the explicit criterion.",
        },
    )
    assert result.cases[0].status == "pass"
    assert result.cases[0].judge_status == "assessed"
    assert result.cases[0].judge_score == 0.8
    assert result.cases[0].response is None

    malformed = evaluate_suite(
        suite,
        lambda _prompt, _max_tokens: "yes",
        judge=lambda _case, _response, _max_tokens: {"score": 2, "rationale": "bad"},
    )
    assert malformed.cases[0].judge_status == "error"
    assert "between 0 and 1" in (malformed.cases[0].judge_detail or "")


def test_judge_endpoint_requires_an_approved_host():
    from rift.evaluation import invoke_judge_openai_compatible

    try:
        invoke_judge_openai_compatible(
            "http://127.0.0.1:11735",
            model="judge",
            allowed_hosts=["example.invalid"],
        )
    except ValueError as exc:
        assert "approved host" in str(exc)
    else:
        raise AssertionError("unapproved judge host must be rejected")


if __name__ == "__main__":
    test_default_suite_is_bounded_and_explicit()
    test_evaluation_uses_deterministic_checks_and_preserves_case_results()
    test_evaluation_deadline_marks_remaining_cases_not_assessed()
    test_judge_assessment_is_separate_and_schema_validated()
    test_judge_endpoint_requires_an_approved_host()
    print("evaluation_tests: PASS")
