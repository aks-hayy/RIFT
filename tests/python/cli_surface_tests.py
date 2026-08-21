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


def test_stop_is_a_confirmed_service_operation() -> None:
    args = build_parser().parse_args(["stop", "--service", "chat", "--yes"])
    assert args.command == "stop"
    assert args.service == "chat"
    assert args.yes is True


def test_state_backup_and_restore_require_explicit_restore_confirmation() -> None:
    backup = build_parser().parse_args(["system", "backup", "--output", "state.db"])
    assert backup.system_command == "backup"
    assert backup.output == "state.db"
    restore = build_parser().parse_args(["system", "restore", "--input", "state.db", "--yes"])
    assert restore.system_command == "restore"
    assert restore.input == "state.db"
    assert restore.yes is True


def main() -> None:
    test_apply_accepts_explicit_permissions_and_config()
    test_stop_is_a_confirmed_service_operation()
    test_state_backup_and_restore_require_explicit_restore_confirmation()
    print("cli_surface_tests: PASS")


if __name__ == "__main__":
    main()
