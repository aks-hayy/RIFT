import contextlib
import io
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

core = types.ModuleType("rift._core")
core.InferenceEngine = object
core.__version__ = "test"
core.build_info = lambda: {}
core.cuda_device_count = lambda: 0
core.inspect_model = lambda *args, **kwargs: {}
core.parse_model_topology = lambda *args, **kwargs: {}
sys.modules.setdefault("rift._core", core)

from rift.cli.parser import build_parser
from rift.cli.console import RiftConsole


def test_apply_accepts_explicit_permissions_and_config() -> None:
    args = build_parser().parse_args(
        [
            "apply",
            "--config",
            "rift.yaml",
            "--allow-download",
            "--allow-install",
            "--allow-launch",
            "--optimize",
        ]
    )
    assert args.command == "apply"
    assert args.config == "rift.yaml"
    assert args.allow_download is True
    assert args.allow_install is True
    assert args.allow_launch is True
    assert args.optimize is True


def test_plan_list_and_apply_plan_selection_options() -> None:
    listed = build_parser().parse_args(["plan", "list", "--limit", "10"])
    assert listed.command == "plan"
    assert listed.plan_action == "list"
    assert listed.limit == 10

    cleared = build_parser().parse_args(["plan", "clear", "--yes"])
    assert cleared.command == "plan"
    assert cleared.plan_action == "clear"
    assert cleared.yes is True

    apply = build_parser().parse_args(["apply", "--plan", "2", "--no-prompt"])
    assert apply.config is None
    assert apply.plan == "2"
    assert apply.no_prompt is True


def test_stop_is_a_confirmed_service_operation() -> None:
    args = build_parser().parse_args(["stop", "--service", "chat", "--yes"])
    assert args.command == "stop"
    assert args.service == "chat"
    assert args.yes is True


def test_plan_accepts_model_source_options() -> None:
    args = build_parser().parse_args(
        [
            "plan",
            "--huggingface",
            "Qwen/Qwen2.5-Coder-7B-Instruct-GGUF",
            "--task",
            "coding",
            "--select",
            "1",
            "--no-prompt",
        ]
    )
    assert args.command == "plan"
    assert args.huggingface == "Qwen/Qwen2.5-Coder-7B-Instruct-GGUF"
    assert args.local_model is None
    assert args.models_dir is None
    assert args.task == "coding"
    assert args.select == "1"
    assert args.no_prompt is True


def test_state_backup_and_restore_require_explicit_restore_confirmation() -> None:
    backup = build_parser().parse_args(["system", "backup", "--output", "state.db"])
    assert backup.system_command == "backup"
    assert backup.output == "state.db"
    restore = build_parser().parse_args(["system", "restore", "--input", "state.db", "--yes"])
    assert restore.system_command == "restore"
    assert restore.input == "state.db"
    assert restore.yes is True


def test_recommendation_render_prints_plan_handoff() -> None:
    output = io.StringIO()
    payload = {
        "recommendation_run_id": "coding-run-123",
        "recommendations": [],
    }
    with contextlib.redirect_stdout(output):
        RiftConsole(no_color=True).render(payload, view="recommend")
    rendered = output.getvalue()
    assert "Recommendation run: coding-run-123" in rendered
    assert "rift plan --recommendation-run coding-run-123" in rendered


def test_apply_progress_renders_stage_bar() -> None:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        console = RiftConsole(no_color=True)
        console.apply_progress("planning", "running", {"total": 1})
        console.apply_progress("planning", "complete", {"total": 1})
        console.apply_progress("complete", "complete", {})
    rendered = output.getvalue()
    assert "Plan deployment" in rendered
    assert "100%" in rendered
    assert "[OK]" in rendered


def test_tune_parser_exposes_target_accuracy_and_kv_controls() -> None:
    args = build_parser().parse_args([
        "tune", "--profile", "speed", "--target-tokens-per-second", "100",
        "--accuracy-tolerance", "0.05", "--accuracy-case-tolerance", "0.15",
        "--retain-accuracy-responses", "--no-kv-precision-search",
    ])
    assert args.target_tokens_per_second == 100.0
    assert args.accuracy_tolerance == 0.05
    assert args.accuracy_case_tolerance == 0.15
    assert args.retain_accuracy_responses is True
    assert args.kv_precision_search is False


def test_tune_parser_exposes_ngram_speculation_switch() -> None:
    parser = build_parser()
    assert parser.parse_args(["tune", "--no-ngram-speculation"]).ngram_speculation is False
    assert parser.parse_args(["tune", "--ngram-speculation"]).ngram_speculation is True


def test_tune_parser_rejects_invalid_target_and_tolerances() -> None:
    import pytest
    parser = build_parser()
    for option, value in (("--target-tokens-per-second", "0"), ("--target-tokens-per-second", "nan"), ("--accuracy-tolerance", "-0.1"), ("--accuracy-tolerance", "inf"), ("--accuracy-case-tolerance", "-1")):
        with pytest.raises(SystemExit):
            parser.parse_args(["tune", option, value])


def main() -> None:
    test_apply_accepts_explicit_permissions_and_config()
    test_plan_list_and_apply_plan_selection_options()
    test_stop_is_a_confirmed_service_operation()
    test_plan_accepts_model_source_options()
    test_state_backup_and_restore_require_explicit_restore_confirmation()
    test_recommendation_render_prints_plan_handoff()
    test_apply_progress_renders_stage_bar()
    test_tune_parser_exposes_target_accuracy_and_kv_controls()
    test_tune_parser_rejects_invalid_target_and_tolerances()
    print("cli_surface_tests: PASS")


if __name__ == "__main__":
    main()
