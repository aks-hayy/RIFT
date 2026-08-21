"""Long-running, explicitly emulated RIFT fleet service for integration labs."""

from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from spoolstream.cluster import RiftClusterController, example_emulated_cluster
from spoolstream.rift_yaml import write_yaml


JsonDict = dict[str, Any]


def build_snapshot(root: Path) -> JsonDict:
    config_path = root / "cluster.yaml"
    if not config_path.exists():
        write_yaml(config_path, example_emulated_cluster())
    controller = RiftClusterController(root=root)
    discovery = controller.discover(cluster_config=config_path)
    plan = controller.plan(cluster_config=config_path)
    return {
        "ok": not bool(plan.get("unscheduled")),
        "evidence_level": "EMULATED",
        "physical_hardware_verified": False,
        "discovery": discovery,
        "plan": plan,
    }


def main() -> None:
    root = Path(os.environ.get("RIFT_STATE_ROOT", "/var/lib/rift"))
    root.mkdir(parents=True, exist_ok=True)
    snapshot = build_snapshot(root)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                payload = {
                    "ok": snapshot["ok"],
                    "evidence_level": "EMULATED",
                    "physical_hardware_verified": False,
                }
            elif self.path == "/v1/state":
                payload = snapshot
            else:
                self.send_error(HTTPStatus.NOT_FOUND.value)
                return
            body = json.dumps(payload, sort_keys=True).encode("utf-8")
            self.send_response(HTTPStatus.OK.value)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    host = os.environ.get("RIFT_EMULATOR_HOST", "0.0.0.0")
    port = int(os.environ.get("RIFT_EMULATOR_PORT", "8788"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"RIFT mesh emulator listening on http://{host}:{port} [EMULATED]")
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
