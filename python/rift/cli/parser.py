"""Argument parser for the public RIFT command line."""

from __future__ import annotations

import argparse
import re

from .console import _enable_terminal_color

from rift import __version__


class RiftHelpFormatter(argparse.RawDescriptionHelpFormatter):
    def __init__(self, prog: str) -> None:
        super().__init__(prog, max_help_position=30, width=100)


class RiftArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("formatter_class", RiftHelpFormatter)
        super().__init__(*args, **kwargs)

    def format_help(self) -> str:
        text = super().format_help()
        if not _enable_terminal_color(disabled=False):
            return text
        title = f"RIFT // {self.prog.upper()} COMMAND REFERENCE"
        rule = "=" * min(88, max(58, len(title)))
        text = re.sub(
            r"(?m)^(usage:|options:|commands:|[a-z ]+ commands:)$",
            lambda match: f"\x1b[38;5;75;1m{match.group(1)}\x1b[0m",
            text,
        )
        text = re.sub(r"(?m)^usage:", "\x1b[38;5;75;1musage:\x1b[0m", text)
        return (
            f"\x1b[38;5;27m{rule}\x1b[0m\n"
            f"\x1b[38;5;51;1m{title}\x1b[0m\n"
            f"\x1b[38;5;67mhardware-aware deployment / operations / recovery\x1b[0m\n"
            f"\x1b[38;5;27m{rule}\x1b[0m\n\n{text}"
        )


def _subcommands(
    parser: argparse.ArgumentParser,
    *,
    title: str = "commands",
    dest: str = "command",
):
    return parser.add_subparsers(dest=dest, title=title, metavar="COMMAND", required=True)


def _parser(subparsers, name: str, help_text: str, *, description: str | None = None, epilog: str | None = None):
    return subparsers.add_parser(name, help=help_text, description=description or help_text, epilog=epilog)


def build_parser() -> argparse.ArgumentParser:
    parser = RiftArgumentParser(
        prog="rift",
        description=(
            "RIFT fits LLM deployments to real hardware.\n\n"
            "Discover capacity, choose an exact model artifact and backend, review the plan, "
            "then deploy, benchmark, tune, monitor, and recover it."
        ),
        epilog=(
            "Typical workflow:\n"
            "  rift discover\n"
            "  rift model recommend --task chat\n"
            "  rift model pull --task chat --dry-run\n"
            "  rift plan\n"
            "  rift apply --allow-download --allow-launch\n"
            "  rift status\n\n"
            "Use `rift COMMAND --help` for examples and permission details. "
            "Add `--json` before the command for automation."
        ),
    )
    parser.add_argument("--version", action="version", version=f"RIFT {__version__}")
    parser.add_argument("--json", action="store_true", help="Emit complete machine-readable JSON")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color output")
    parser.add_argument("--debug", action="store_true", help="Show tracebacks for unexpected failures")
    commands = _subcommands(parser)

    init = _parser(
        commands,
        "init",
        "Create a documented starter rift.yaml",
        epilog="Example: rift init --config rift.yaml",
    )
    init.add_argument("--config", default="rift.yaml", help="Configuration path")
    init.add_argument("--force", action="store_true", help="Replace an existing starter config")

    start = _parser(
        commands,
        "start",
        "Start the local RIFT controller and dashboard",
        epilog=(
            "RIFT performs no model download, backend installation, or model launch "
            "without explicit permission. Example: rift start --no-browser"
        ),
    )
    start.add_argument("--host", default="127.0.0.1", help="Dashboard bind address")
    start.add_argument("--port", type=int, default=8765, help="Dashboard HTTP port")
    start.add_argument("--control-port", type=int, default=8777, help="Control API port")
    start.add_argument("--root", help="Dashboard source directory for development")
    start.add_argument("--no-browser", action="store_true", help="Do not open a browser")
    start.add_argument("--detach", action="store_true", help="Run in the background")

    doctor = _parser(
        commands,
        "doctor",
        "Check controller, storage, permissions, and optional model readiness",
        epilog="Example: rift doctor --model C:\\models\\model.gguf",
    )
    doctor.add_argument("--model", help="Optional model path for compatibility checks")

    stop = _parser(
        commands,
        "stop",
        "Stop RIFT-managed model services without deleting model files",
        epilog="Example: rift stop --service chat --yes",
    )
    stop.add_argument("--service")
    stop.add_argument("--yes", action="store_true", help="Confirm the stop operation")

    discover = _parser(
        commands,
        "discover",
        "Inspect local or declared cluster infrastructure",
        epilog=(
            "Examples:\n"
            "  rift discover\n"
            "  rift discover --models models/local\n"
            "  rift discover --cluster cluster.yaml --allow-remote"
        ),
    )
    discover.add_argument("--cluster", help="Optional cluster inventory YAML")
    discover.add_argument("--models", help="Optional local model directory to scan")
    discover.add_argument("--allow-remote", action="store_true", help="Permit remote read-only discovery")

    plan = _parser(
        commands,
        "plan",
        "Preview every deployment action without side effects",
        epilog="Example: rift plan --config rift.yaml",
    )
    plan.add_argument("--config", default="rift.yaml")
    plan.add_argument(
        "--recommendation-run",
        help="Materialize and plan a persisted recommendation run instead of --config",
    )
    plan.add_argument(
        "--selector",
        default="best_estimated",
        help="Run category, repo id, identity id, or artifact id",
    )
    plan.add_argument(
        "--materialized-config",
        help="Optional path for YAML generated from --recommendation-run",
    )

    apply = _parser(
        commands,
        "apply",
        "Apply reviewed intent with explicit permissions",
        epilog=(
            "Examples:\n"
            "  rift apply --config rift.yaml\n"
            "  rift apply --allow-download --allow-install --allow-launch\n\n"
            "Without permission flags RIFT returns blocked actions and changes nothing."
        ),
    )
    apply.add_argument("--config", default="rift.yaml")
    apply.add_argument("--allow-download", action="store_true")
    apply.add_argument("--allow-install", action="store_true")
    apply.add_argument("--allow-launch", action="store_true")
    apply.add_argument("--allow-remote", action="store_true")
    apply.add_argument("--optimize", action="store_true", help="Benchmark safe backend candidates")
    apply.add_argument("--write-back", action="store_true", help="Write optimized settings to the source config")

    status = _parser(commands, "status", "Show desired and observed service state")
    status.add_argument("--service", help="Show one service")

    dashboard = _parser(
        commands,
        "dashboard",
        "Launch the local operator dashboard and control API",
        epilog="Example: rift dashboard --port 8765 --control-port 8777",
    )
    dashboard.add_argument("--host", default="127.0.0.1", help="Local bind address")
    dashboard.add_argument("--port", type=int, default=8765, help="Dashboard HTTP port")
    dashboard.add_argument(
        "--control-port",
        type=int,
        default=8777,
        help="Local RIFT control API port",
    )
    dashboard.add_argument(
        "--root",
        help="Dashboard source directory; auto-detected from the checkout by default",
    )
    dashboard.add_argument(
        "--no-browser",
        action="store_true",
        help="Start without opening the system browser",
    )
    dashboard.add_argument(
        "--detach",
        action="store_true",
        help="Run in the background and write logs under .rift/logs",
    )

    _add_model_group(commands)
    _add_backend_group(commands)
    _add_service_group(commands)
    _add_cluster_group(commands)
    _add_node_group(commands)
    _add_system_group(commands)
    return parser


def _add_model_group(commands) -> None:
    model = _parser(
        commands,
        "model",
        "Inspect, verify, or pull model artifacts",
        epilog=(
            "Examples:\n"
            "  rift model inspect models/local/my-model\n"
            "  rift model pull org/repository --dry-run  # exact-repo expert override\n"
            "  rift model verify models/local/my-model --hash-mode model"
        ),
    )
    sub = _subcommands(model, title="model commands", dest="model_command")
    recommend = _parser(
        sub,
        "recommend",
        "Rank exact model artifacts for the current hardware without downloading",
        epilog=(
            "Examples:\n"
            "  rift model recommend --task chat\n"
            "  rift model recommend --task coding --formats gguf,gptq --top 5\n"
            "  rift model recommend --verify --allow-download --allow-install --allow-launch"
        ),
    )
    recommend.add_argument("--task", default="chat")
    recommend.add_argument(
        "--source",
        choices=["huggingface", "private", "local"],
        default="huggingface",
        help="Model source to rank; local uses artifacts found under --models-dir",
    )
    recommend.add_argument("--models-dir", help="Local model directory used with --source local")
    recommend.add_argument("--top", type=int, default=10)
    recommend.add_argument("--candidate-limit", type=int, default=250)
    recommend.add_argument("--max-download-gb", type=float)
    recommend.add_argument("--formats")
    recommend.add_argument("--include-gated", action="store_true")
    recommend.add_argument("--refresh", action="store_true")
    recommend.add_argument("--pull-best", action="store_true")
    recommend.add_argument("--output")
    recommend.add_argument("--download-root")
    recommend.add_argument("--disk-reserve-gb", type=float, default=2.0)
    recommend.add_argument("--endpoint", default="https://huggingface.co")
    recommend.add_argument("--token")
    recommend.add_argument("--benchmark-snapshot", action="append", default=[], metavar="PATH_OR_URL")
    recommend.add_argument("--simulate-hardware", metavar="SPEC_OR_JSON")
    recommend.add_argument("--write-report")
    recommend.add_argument("--verify", action="store_true")
    recommend.add_argument("--verify-top", type=int)
    recommend.add_argument("--verify-finalists", type=int, default=None)
    recommend.add_argument("--verify-budget", type=float)
    recommend.add_argument("--verify-prompt", default="Reply briefly: what is one benefit of local language models?")
    recommend.add_argument("--verify-max-tokens", type=int, default=32)
    recommend.add_argument("--verify-timeout", type=float, default=180.0)
    recommend.add_argument("--allow-download", action="store_true")
    recommend.add_argument("--allow-install", action="store_true")
    recommend.add_argument("--allow-launch", action="store_true")
    pull = _parser(sub, "pull", "Download an exact model snapshot with disk preflight")
    pull.add_argument("repo_id", nargs="?")
    pull.add_argument("--task", default="chat", help="Automatic selection task when repo_id is omitted")
    pull.add_argument("--top", type=int, default=10)
    pull.add_argument("--candidate-limit", type=int, default=250)
    pull.add_argument("--max-download-gb", type=float)
    pull.add_argument("--formats")
    pull.add_argument("--include-gated", action="store_true")
    pull.add_argument("--refresh", action="store_true")
    pull.add_argument("--revision", default="main")
    pull.add_argument("--output")
    pull.add_argument("--include", dest="allow_patterns", action="append")
    pull.add_argument("--ignore", dest="ignore_patterns", action="append")
    pull.add_argument("--token")
    pull.add_argument("--dry-run", action="store_true")
    pull.add_argument("--max-bytes", type=int)
    pull.add_argument("--endpoint", default="https://huggingface.co")
    pull.add_argument("--no-inspect", action="store_true")
    pull.add_argument("--download-root")
    pull.add_argument("--disk-reserve-gb", type=float, default=2.0)
    pull.add_argument("--write-report")
    inspect = _parser(sub, "inspect", "Inspect model metadata and deployment compatibility")
    inspect.add_argument("path")
    inspect.add_argument("--quant-format", default="awq_int4")
    verify = _parser(sub, "verify", "Build and validate an artifact manifest")
    verify.add_argument("path")
    verify.add_argument("--hash-mode", default="model", choices=["none", "metadata", "model", "all"])


def _add_backend_group(commands) -> None:
    backend = _parser(
        commands,
        "backend",
        "Manage external serving providers",
        epilog=(
            "Examples:\n"
            "  rift backend list\n"
            "  rift backend install-plan llama.cpp\n"
            "  rift backend install llama.cpp --allow-install"
        ),
    )
    sub = _subcommands(backend, title="backend commands", dest="backend_command")
    _parser(sub, "list", "Show provider detection and support gates")
    detect = _parser(sub, "detect", "Probe one or every provider")
    detect.add_argument("name", nargs="?")
    inspect = _parser(sub, "inspect", "Show one adapter manifest, capability contract, and diagnostics")
    inspect.add_argument("name")
    doctor = _parser(sub, "doctor", "Validate adapter contracts, environments, and remediation paths")
    doctor.add_argument("name", nargs="?")
    install_plan = _parser(sub, "install-plan", "Show an official, read-only install plan")
    install_plan.add_argument("name", default="llama.cpp", nargs="?")
    install = _parser(sub, "install", "Install a provider only with explicit permission")
    install.add_argument("name", default="llama.cpp", nargs="?")
    install.add_argument("--allow-install", action="store_true")
    install.add_argument("--target")
    install.add_argument("--variant", default="auto")
    install.add_argument("--force", action="store_true")
    health = _parser(sub, "health", "Probe a provider's serving endpoint")
    health.add_argument("name", default="llama.cpp", nargs="?")
    health.add_argument("--base-url", default="http://127.0.0.1:11735")


def _add_service_group(commands) -> None:
    service = _parser(
        commands,
        "service",
        "Operate managed services and incidents",
        epilog=(
            "Examples:\n"
            "  rift service monitor --iterations 1\n"
            "  rift service restart --service chat --allow-launch\n"
            "  rift service logs --service chat --tail 100"
        ),
    )
    sub = _subcommands(service, title="service commands", dest="service_command")
    benchmark = _parser(sub, "benchmark", "Measure a managed service with reproducible settings")
    benchmark.add_argument("--service", default="chat")
    benchmark.add_argument("--prompt", default="Explain what RIFT does in one sentence.")
    benchmark.add_argument("--max-tokens", type=int, default=32)
    benchmark.add_argument("--suite", action="store_true")
    benchmark.add_argument("--warmups", type=int, default=1)
    benchmark.add_argument("--repeats", type=int, default=3)
    tune = _parser(sub, "tune", "Search bounded backend settings and reject regressions")
    tune.add_argument("--service", default="chat")
    tune.add_argument("--config", default="rift.yaml")
    tune.add_argument("--live", action="store_true")
    tune.add_argument("--allow-restart", action="store_true")
    tune.add_argument("--candidate-limit", type=int, default=4)
    tune.add_argument("--warmups", type=int, default=1)
    tune.add_argument("--repeats", type=int, default=2)
    tune.add_argument("--startup-timeout", type=float, default=180.0)
    tune.add_argument("--prompt", default="Reply briefly: what is one benefit of local inference?")
    tune.add_argument("--max-tokens", type=int, default=32)
    monitor = _parser(sub, "monitor", "Observe health and optionally reconcile failures")
    monitor.add_argument("--service")
    monitor.add_argument("--interval", type=float, default=5.0)
    monitor.add_argument("--iterations", type=int, default=1, help="0 runs until interrupted")
    monitor.add_argument("--allow-recovery", action="store_true")
    restart = _parser(sub, "restart", "Restart through the bounded recovery policy")
    restart.add_argument("--service", default="chat")
    restart.add_argument("--allow-launch", action="store_true")
    restart.add_argument("--force", action="store_true")
    rollback = _parser(sub, "rollback", "Restart from the last known-good launch snapshot")
    rollback.add_argument("--service", default="chat")
    rollback.add_argument("--allow-launch", action="store_true")
    incidents = _parser(sub, "incidents", "List persisted incident reports")
    incidents.add_argument("--limit", type=int, default=50)
    logs = _parser(sub, "logs", "Read a managed service log tail")
    logs.add_argument("--service", default="chat")
    logs.add_argument("--tail", type=int, default=200)
    gateway = _parser(sub, "gateway", "Run the policy-enforcing OpenAI-compatible gateway")
    gateway.add_argument("--config", default="rift.yaml")
    gateway.add_argument("--service", default="chat")
    gateway.add_argument("--host")
    gateway.add_argument("--port", type=int)
    gateway.add_argument("--fallback-service", dest="fallback_services", action="append")


def _add_cluster_group(commands) -> None:
    cluster = _parser(
        commands,
        "cluster",
        "Plan and operate a declared node fleet",
        epilog=(
            "Workflow:\n"
            "  rift cluster init\n"
            "  rift cluster discover --config cluster.yaml\n"
            "  rift cluster plan --config cluster.yaml\n"
            "  rift cluster apply --config cluster.yaml --allow-launch"
        ),
    )
    sub = _subcommands(cluster, title="cluster commands", dest="cluster_command")
    init = _parser(sub, "init", "Create an emulated cluster inventory example")
    init.add_argument("--config", default="cluster.yaml")
    init.add_argument("--force", action="store_true")
    discover = _parser(sub, "discover", "Inspect declared cluster nodes")
    discover.add_argument("--config", default="cluster.yaml")
    discover.add_argument("--allow-remote", action="store_true")
    plan = _parser(sub, "plan", "Validate capacity and preview placement")
    plan.add_argument("--config", default="cluster.yaml")
    apply = _parser(sub, "apply", "Apply cluster placement with explicit permission")
    apply.add_argument("--config", default="cluster.yaml")
    apply.add_argument("--allow-launch", action="store_true")
    apply.add_argument("--allow-remote", action="store_true")
    apply.add_argument("--allow-download", action="store_true")
    apply.add_argument("--allow-install", action="store_true")
    _parser(sub, "status", "Show cluster desired and observed state")
    benchmark = _parser(sub, "benchmark", "Benchmark cluster services")
    benchmark.add_argument("--service")
    tune = _parser(sub, "tune", "Tune cluster service settings")
    tune.add_argument("--service")
    drain = _parser(sub, "drain", "Drain a node before maintenance or removal")
    drain.add_argument("--node", required=True)
    drain.add_argument("--force", action="store_true", help="Reschedule affected instances immediately")
    recover = _parser(sub, "recover", "Run the cluster recovery reconciler")
    recover.add_argument("--allow-recovery", action="store_true")
    destroy = _parser(sub, "destroy", "Stop managed cluster instances")
    destroy.add_argument("--yes", action="store_true")


def _add_node_group(commands) -> None:
    node = _parser(
        commands,
        "node",
        "Run the optional mTLS worker agent on a cluster node",
        epilog=(
            "Workflow:\n"
            "  rift node init --node-id worker-01\n"
            "  # provision the declared CA/node certificates\n"
            "  rift node serve --config node-agent.yaml"
        ),
    )
    sub = _subcommands(node, title="node commands", dest="node_command")
    init = _parser(sub, "init", "Create a locked-down node-agent config template")
    init.add_argument("--config", default="node-agent.yaml")
    init.add_argument("--node-id", default="rift-node")
    init.add_argument("--force", action="store_true")
    enroll = _parser(sub, "enroll", "Create a node enrollment configuration template")
    enroll.add_argument("--config", default="node-agent.yaml")
    enroll.add_argument("--node-id", default="rift-node")
    enroll.add_argument("--force", action="store_true")
    serve = _parser(sub, "serve", "Serve the authenticated node control API")
    serve.add_argument("--config", default="node-agent.yaml")
    serve.add_argument("--root")
    status = _parser(sub, "status", "Show node-agent health and local desired state")
    status.add_argument("--config", default="node-agent.yaml")
    status.add_argument("--root")


def _add_system_group(commands) -> None:
    system = _parser(
        commands,
        "system",
        "Inspect RIFT itself and create support artifacts",
        epilog=(
            "Examples:\n"
            "  rift system hardware\n"
            "  rift system doctor\n"
            "  rift system diagnostics --output rift-diagnostics.zip"
        ),
    )
    sub = _subcommands(system, title="system commands", dest="system_command")
    _parser(sub, "info", "Show build and native runtime information")
    _parser(sub, "hardware", "Show measurement-aware local hardware")
    calibrate = _parser(sub, "calibrate", "Measure bounded local storage throughput")
    calibrate.add_argument("--sample-mib", type=int, default=32)
    calibrate.add_argument("--force", action="store_true")
    doctor = _parser(sub, "doctor", "Run control-plane readiness diagnostics")
    doctor.add_argument("--model")
    diagnostics = _parser(sub, "diagnostics", "Create a redacted diagnostic bundle")
    diagnostics.add_argument("--output")
    backup = _parser(sub, "backup", "Create a crash-safe SQLite controller-state backup")
    backup.add_argument("--output")
    restore = _parser(sub, "restore", "Restore controller state from a validated SQLite backup")
    restore.add_argument("--input", required=True)
    restore.add_argument("--yes", action="store_true", help="Confirm replacement of active controller state")
    export = _parser(sub, "export", "Export deployment provenance and audit state")
    export.add_argument("--output")
    migrate = _parser(sub, "migrate", "Preview or write state/config migrations")
    migrate.add_argument("--config", default="rift.yaml")
    migrate.add_argument("--write", action="store_true")
    migrate.add_argument("--paths", action="store_true", help="Migrate checkout-local .rift/models data")
    migrate.add_argument("--source-root", help="Checkout root to inspect; defaults to the current directory")
    migrate.add_argument("--move", action="store_true", help="Remove legacy source data after verified copy")


__all__ = ["RiftArgumentParser", "RiftHelpFormatter", "build_parser"]
