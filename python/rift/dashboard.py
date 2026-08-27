"""Launcher for the RIFT operator dashboard and local control API."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
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
from urllib.error import HTTPError
from urllib.request import Request, urlopen

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


def bundled_rich_dashboard_root() -> Path:
    """Return the optional server-rendered dashboard bundle shipped in the wheel."""

    return bundled_dashboard_root() / "_rich"


def rich_dashboard_plan(
    dashboard_root: str | Path | None = None,
    *,
    port: int = 8765,
    control_port: int = 8777,
) -> dict[str, str] | None:
    """Return a local or packaged server-rendered UI when it is available."""

    requested = Path(dashboard_root).resolve() if dashboard_root else find_dashboard_root()
    candidates: list[Path] = []
    if requested is not None:
        candidates.append(requested)
    packaged = bundled_rich_dashboard_root()
    if packaged not in candidates:
        candidates.append(packaged)
    node = shutil.which("node")
    if not node:
        return None
    for root in candidates:
        server_script = root / "scripts" / "serve-dist.mjs"
        server_bundle = root / "dist" / "server" / "server.js"
        client_root = root / "dist" / "client"
        if not server_script.is_file() or not server_bundle.is_file() or not client_root.is_dir():
            continue
        return {
            "node": node,
            "root": str(root),
            "server_script": str(server_script),
            "server_bundle": str(server_bundle),
            "client_root": str(client_root),
            "port": str(int(port)),
            "control_api": f"http://127.0.0.1:{int(control_port)}",
        }
    return None


def _launch_rich_dashboard(plan: dict[str, str]) -> subprocess.Popen[bytes]:
    environment = os.environ.copy()
    environment.update(
        {
            "RIFT_UI_HOST": "127.0.0.1",
            "RIFT_UI_PORT": plan["port"],
            "RIFT_CONTROL_API": plan["control_api"],
        }
    )
    return subprocess.Popen(
        [plan["node"], plan["server_script"]],
        cwd=plan["root"],
        env=environment,
        stdin=subprocess.DEVNULL,
    )


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
    control_runtime = None
    if not _control_api_ready(host, control_port):
        from .server import create_rift_server

        from .server import RiftServerRuntime

        dashboard_origins = {
            f"http://127.0.0.1:{int(port)}",
            f"http://localhost:{int(port)}",
        }
        if host not in {"127.0.0.1", "localhost", "0.0.0.0", "::"}:
            dashboard_origins.add(f"http://{host}:{int(port)}")
        control_runtime = RiftServerRuntime(cors_origins=tuple(sorted(dashboard_origins)))
        control_server = create_rift_server(host=host, port=control_port, runtime=control_runtime)
        control_thread = threading.Thread(
            target=control_server.serve_forever,
            name="rift-control-api",
            daemon=True,
        )
        control_thread.start()

    rich_process = None
    static_server = None
    static_thread = None
    rich_plan = rich_dashboard_plan(
        dashboard_root or find_dashboard_root(Path.cwd()), port=port, control_port=control_port
    )
    if rich_plan is not None:
        rich_process = _launch_rich_dashboard(rich_plan)
    else:
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
        if static_server is not None:
            static_server.shutdown()
        if rich_process is not None:
            rich_process.terminate()
            rich_process.wait(timeout=5)
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
        if static_server is not None:
            static_server.shutdown()
            static_server.server_close()
        if static_thread is not None:
            static_thread.join(timeout=5)
        if rich_process is not None and rich_process.poll() is None:
            rich_process.terminate()
            try:
                rich_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                rich_process.kill()
                rich_process.wait(timeout=5)
        reconcile_stop.set()
        reconcile_thread.join(timeout=5)
        if control_server is not None:
            control_server.shutdown()
            control_server.server_close()
        if control_runtime is not None:
            control_runtime.shutdown()
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
    requested_root = (
        Path(dashboard_root).resolve()
        if dashboard_root
        else find_dashboard_root(Path.cwd())
    )
    child_root = plan.dashboard_root
    if requested_root is not None and rich_dashboard_plan(
        requested_root,
        port=port,
        control_port=control_port,
    ) is not None:
        child_root = str(requested_root)
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
        child_root,
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
    route_files = {
        "/": "/index.html",
        "/setup": "/setup.html",
        "/deployments": "/deployments.html",
        "/nodes": "/nodes.html",
        "/models": "/models.html",
        "/operations": "/operations.html",
        "/settings": "/settings.html",
    }

    class StaticHandler(SimpleHTTPRequestHandler):
        def __init__(self, request, client_address, server):
            super().__init__(request, client_address, server, directory=str(root))

        def _proxy_controller(self) -> None:
            target = f"{control_api_url}{self.path}"
            request_body = None
            if self.command not in {"GET", "HEAD"}:
                try:
                    content_length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    self._write_proxy_response(400, "application/json", b'{"error":"invalid content length"}')
                    return
                if content_length < 0 or content_length > 32 * 1024 * 1024:
                    self._write_proxy_response(413, "application/json", b'{"error":"request body too large"}')
                    return
                request_body = self.rfile.read(content_length)
            headers = {
                key: value
                for key, value in self.headers.items()
                if key.lower() not in {"host", "content-length", "connection"}
            }
            upstream_request = Request(
                target,
                data=request_body,
                headers=headers,
                method=self.command,
            )
            try:
                with urlopen(upstream_request, timeout=30) as upstream:
                    payload = upstream.read()
                    content_type = upstream.headers.get("Content-Type", "application/octet-stream")
                    self._write_proxy_response(upstream.status, content_type, payload, upstream.headers)
            except HTTPError as error:
                payload = error.read()
                content_type = error.headers.get("Content-Type", "application/json")
                self._write_proxy_response(error.code, content_type, payload, error.headers)
            except OSError as error:
                detail = json.dumps({"error": "controller proxy unavailable", "detail": str(error)})
                self._write_proxy_response(502, "application/json", detail.encode("utf-8"))

        def _write_proxy_response(
            self,
            status: int,
            content_type: str,
            payload: bytes,
            headers=None,
        ) -> None:
            self.send_response(status)
            if headers is not None:
                for key, value in headers.items():
                    if key.lower() in {
                        "connection",
                        "content-length",
                        "content-type",
                        "transfer-encoding",
                        "server",
                        "date",
                    }:
                        continue
                    self.send_header(key, value)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/rift"):
                self._proxy_controller()
                return
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
            if parsed.path in route_files:
                self.path = route_files[parsed.path]
            candidate = root / urlparse(self.path).path.lstrip("/")
            if not candidate.is_file() and not parsed.path.startswith("/assets/"):
                self.path = "/index.html"
            super().do_GET()

        def do_POST(self):  # noqa: N802
            if urlparse(self.path).path.startswith("/api/rift"):
                self._proxy_controller()
                return
            self.send_error(405, "POST is only supported for controller API routes")

        def do_PUT(self):  # noqa: N802
            if urlparse(self.path).path.startswith("/api/rift"):
                self._proxy_controller()
                return
            self.send_error(405, "PUT is only supported for controller API routes")

        def do_PATCH(self):  # noqa: N802
            if urlparse(self.path).path.startswith("/api/rift"):
                self._proxy_controller()
                return
            self.send_error(405, "PATCH is only supported for controller API routes")

        def do_DELETE(self):  # noqa: N802
            if urlparse(self.path).path.startswith("/api/rift"):
                self._proxy_controller()
                return
            self.send_error(405, "DELETE is only supported for controller API routes")

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
