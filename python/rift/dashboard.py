"""Launcher for the RIFT operator dashboard and local control API."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from urllib.request import urlopen

from .orchestrator import RiftOrchestrator
from .reconciliation import ReconcilePolicy, RiftReconciler


@dataclass(frozen=True)
class DashboardLaunchPlan:
    dashboard_root: str
    dashboard_url: str
    control_api_url: str
    command: list[str]
    dependencies_ready: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def find_dashboard_root(start: str | Path | None = None) -> Path | None:
    """Locate the contributor UI source for development tooling."""

    configured = os.environ.get("RIFT_DASHBOARD_ROOT")
    package_root = Path(__file__).resolve().parent
    base = Path(start).resolve() if start else Path.cwd().resolve()
    candidates: list[Path | None] = [Path(configured).expanduser() if configured else None]
    for name in ("ui",):
        candidates.extend(parent / name for parent in (base, *base.parents))
        candidates.extend(parent / name for parent in (package_root, *package_root.parents))
    visited: set[Path] = set()
    for candidate in candidates:
        if not candidate:
            continue
        resolved = candidate.resolve()
        if resolved in visited:
            continue
        visited.add(resolved)
        if (resolved / "package.json").is_file() and (
            resolved / "src" / "routes" / "__root.tsx"
        ).is_file():
            return resolved
    return None


def bundled_dashboard_root() -> Path:
    """Return the dashboard shipped in the Python wheel."""

    return Path(__file__).resolve().parent / "web" / "static"


def dashboard_launch_plan(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    control_port: int = 8777,
    dashboard_root: str | Path | None = None,
) -> DashboardLaunchPlan:
    if not 1 <= int(port) <= 65535 or not 1 <= int(control_port) <= 65535:
        raise ValueError("dashboard and control ports must be between 1 and 65535")
    root = Path(dashboard_root).resolve() if dashboard_root else bundled_dashboard_root()
    if root.is_dir() and (root / "package.json").is_file():
        root = bundled_dashboard_root()
    if not (root / "index.html").is_file():
        raise RuntimeError(
            "RIFT dashboard assets were not found. Reinstall the package or build the "
            "contributor UI into python/rift/web/static."
        )
    dependencies_ready = True
    return DashboardLaunchPlan(
        dashboard_root=str(root),
        dashboard_url=f"http://{host}:{int(port)}",
        control_api_url=f"http://{host}:{int(control_port)}",
        command=[
            sys.executable,
            "-m",
            "rift.cli",
            "dashboard",
            "--host",
            host,
            "--port",
            str(int(port)),
            "--control-port",
            str(int(control_port)),
            "--no-browser",
        ],
        dependencies_ready=dependencies_ready,
    )


def serve_dashboard(
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    control_port: int = 8777,
    dashboard_root: str | Path | None = None,
) -> None:
    plan = dashboard_launch_plan(
        host=host,
        port=port,
        control_port=control_port,
        dashboard_root=dashboard_root,
    )
    control_server = None
    control_thread = None
    if not _control_api_ready(host, control_port):
        from .server import create_rift_server

        control_server = create_rift_server(host=host, port=control_port)
        control_thread = threading.Thread(
            target=control_server.serve_forever,
            name="rift-control-api",
            daemon=True,
        )
        control_thread.start()

    static_server = _create_static_server(host, port, plan.control_api_url)
    static_thread = threading.Thread(
        target=static_server.serve_forever,
        name="rift-dashboard-static",
        daemon=True,
    )
    static_thread.start()
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        if _dashboard_ready(plan.dashboard_url):
            break
        time.sleep(0.25)
    else:
        static_server.shutdown()
        raise RuntimeError(
            f"Dashboard did not become ready at {plan.dashboard_url} within 30 seconds"
        )
    reconcile_stop = threading.Event()
    reconcile_policy = ReconcilePolicy(
        allow_recovery=os.environ.get("RIFT_AUTO_RECOVER") == "1"
    )
    reconciler = RiftReconciler(
        RiftOrchestrator(),
        policy=reconcile_policy,
    )
    reconcile_thread = threading.Thread(
        target=reconciler.run,
        args=(reconcile_stop,),
        name="rift-reconciler",
        daemon=True,
    )
    reconcile_thread.start()
    if open_browser:
        webbrowser.open(plan.dashboard_url)
    print(f"RIFT dashboard     {plan.dashboard_url}")
    print(f"RIFT control API   {plan.control_api_url}")
    print("Press Ctrl+C to stop the dashboard. Managed model services are not stopped.")
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nStopping the RIFT dashboard...")
    finally:
        static_server.shutdown()
        static_server.server_close()
        static_thread.join(timeout=5)
        reconcile_stop.set()
        reconcile_thread.join(timeout=5)
        if control_server is not None:
            control_server.shutdown()
            control_server.server_close()
        if control_thread is not None:
            control_thread.join(timeout=5)


def launch_dashboard_detached(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    control_port: int = 8777,
    dashboard_root: str | Path | None = None,
) -> dict[str, object]:
    plan = dashboard_launch_plan(
        host=host,
        port=port,
        control_port=control_port,
        dashboard_root=dashboard_root,
    )
    if _dashboard_ready(plan.dashboard_url):
        return {
            "started": False,
            "reason": "dashboard is already running",
            "dashboard_url": plan.dashboard_url,
            "control_api_url": plan.control_api_url,
        }

    from .runtime_paths import RiftPaths

    logs = RiftPaths.from_environment().logs
    logs.mkdir(parents=True, exist_ok=True)
    stdout_path = logs / "dashboard.out.log"
    stderr_path = logs / "dashboard.err.log"
    command = [
        sys.executable,
        "-m",
        "rift.cli",
        "dashboard",
        "--host",
        host,
        "--port",
        str(int(port)),
        "--control-port",
        str(int(control_port)),
        "--root",
        plan.dashboard_root,
        "--no-browser",
    ]
    environment = {
        name: value for name, value in os.environ.items() if name.lower() != "path"
    }
    environment["PATH"] = os.environ.get("PATH") or os.environ.get("Path", "")
    environment["RIFT_DASHBOARD_ROOT"] = plan.dashboard_root
    flags = 0
    breakaway_flag = 0
    if os.name == "nt":
        flags = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        breakaway_flag = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
    with stdout_path.open("ab", buffering=0) as stdout, stderr_path.open(
        "ab", buffering=0
    ) as stderr:
        popen_kwargs = {
            "cwd": str(Path.cwd()),
            "env": environment,
            "stdin": subprocess.DEVNULL,
            "stdout": stdout,
            "stderr": stderr,
            "start_new_session": os.name != "nt",
        }
        try:
            process = subprocess.Popen(
                command,
                creationflags=flags | breakaway_flag,
                **popen_kwargs,
            )
        except OSError:
            if not breakaway_flag:
                raise
            process = subprocess.Popen(
                command,
                creationflags=flags,
                **popen_kwargs,
            )

    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        if process.poll() is not None:
            detail = stderr_path.read_text(encoding="utf-8", errors="replace")[-2000:]
            raise RuntimeError(
                "Detached dashboard exited during startup"
                + (f":\n{detail}" if detail else "")
            )
        if _dashboard_ready(plan.dashboard_url):
            return {
                "started": True,
                "pid": process.pid,
                "dashboard_url": plan.dashboard_url,
                "control_api_url": plan.control_api_url,
                "stdout_log": str(stdout_path.resolve()),
                "stderr_log": str(stderr_path.resolve()),
            }
        time.sleep(0.25)
    process.terminate()
    raise RuntimeError(
        f"Detached dashboard did not become ready at {plan.dashboard_url} within 30 seconds"
    )


def _control_api_ready(host: str, port: int) -> bool:
    try:
        with urlopen(f"http://{host}:{port}/api/rift/status", timeout=0.5) as response:
            return 200 <= int(response.status) < 500
    except Exception:
        return False


def _dashboard_ready(url: str) -> bool:
    try:
        with urlopen(url, timeout=1.0) as response:
            return 200 <= int(response.status) < 500
    except Exception:
        return False


def _create_static_server(host: str, port: int, control_api_url: str) -> ThreadingHTTPServer:
    root = bundled_dashboard_root()

    class StaticHandler(SimpleHTTPRequestHandler):
        def __init__(self, request, client_address, server):
            super().__init__(request, client_address, server, directory=str(root))

        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/rift-config.js":
                body = (
                    "window.RIFT_CONTROL_API = "
                    + repr(control_api_url)
                    + ";\n"
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            candidate = root / parsed.path.lstrip("/")
            if not candidate.is_file() and not parsed.path.startswith("/assets/"):
                self.path = "/index.html"
            super().do_GET()

        def log_message(self, format, *args):
            return

    return ThreadingHTTPServer((host, int(port)), StaticHandler)


__all__ = [
    "DashboardLaunchPlan",
    "dashboard_launch_plan",
    "find_dashboard_root",
    "launch_dashboard_detached",
    "serve_dashboard",
]
