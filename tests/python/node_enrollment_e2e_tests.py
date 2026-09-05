"""Local controller/node enrollment acceptance test with real TLS sockets."""

from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from rift.mesh.controller import MeshController
from rift.node_bootstrap import NodeBootstrapClient
from rift.runtime_paths import RiftPaths
from rift.server import RiftServerRuntime


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="rift-enrollment-e2e-") as directory:
        root = Path(directory)
        controller = MeshController(root=root / "controller" / "mesh")
        runtime = RiftServerRuntime(
            mesh_controller_factory=lambda: controller,
            bootstrap_host="127.0.0.1",
            bootstrap_port=_free_port(),
            operation_store=None,
        )
        runtime.control_post("/api/rift/v2/mesh/enrollment-window", {"ttl_seconds": 120})
        node_root = root / "node"
        node_port = _free_port()
        output: list[str] = []
        client = NodeBootstrapClient(
            root=node_root,
            controller=f"https://127.0.0.1:{runtime.bootstrap_port}",
            display_name="e2e-node",
            host="127.0.0.1",
            advertise_host="127.0.0.1",
            port=node_port,
            output=output.append,
        )
        result: dict[str, object] = {}
        failure: list[BaseException] = []

        def run() -> None:
            try:
                result.update(client.enroll(timeout_seconds=30))
            except BaseException as exc:  # pragma: no cover - test failure path
                failure.append(exc)

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not any("PAIRING CODE" in line for line in output):
            time.sleep(0.05)
        assert any("PAIRING CODE" in line for line in output), output
        enrollment_id = str(controller.managed_enrollments()["enrollments"][0]["enrollment_id"])
        code = next(line.rsplit(": ", 1)[-1] for line in output if "PAIRING CODE" in line)
        controller.approve_enrollment(enrollment_id, code)
        worker.join(timeout=20)
        assert not failure, failure
        assert result.get("state") == "ACTIVE", result
        assert client.status()["enrollment"]["state"] == "ACTIVE"
        node = controller.nodes_for_id(client.store.ensure_identity().node_id)
        assert node["trust_state"] == "ACTIVE", node
        assert node["routable"] is True, node
        assert node["mtls_status"] == "ACTIVE", node
        runtime.control_delete("/api/rift/v2/mesh/enrollment-window")
        runtime.shutdown()
    print("node_enrollment_e2e_tests: PASS")


if __name__ == "__main__":
    main()
