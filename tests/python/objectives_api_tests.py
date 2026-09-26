from __future__ import annotations

import sys
import types

ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
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
from rift.operations import OperationStore
from rift.orchestrator import RiftOrchestrator
from rift.server import RiftServerRuntime


def test_objective_status_endpoint_returns_policy_snapshot_and_events(tmp_path):
    orchestrator = RiftOrchestrator(root=tmp_path)
    session = orchestrator.telemetry_store.start_session(
        "chat",
        metadata={"objectives": [{"id": "temp", "metric": "gpu_temperature_c", "operator": "<=", "threshold": 85}]},
    )
    orchestrator.telemetry_store.record_objective_event(session["session_id"], {
        "objective_id": "temp", "metric": "gpu_temperature_c", "status": "breach", "value": 90, "threshold": 85, "observed_at": 1,
    })
    runtime = RiftServerRuntime(orchestrator_factory=lambda: orchestrator, operation_store=OperationStore(tmp_path / "ops"))

    result = runtime.control_get("/api/rift/telemetry/objectives", {"service": ["chat"], "events": ["true"]})

    assert result["service"] == "chat"
    assert result["events"][0]["objective_id"] == "temp"


def test_objective_catalog_endpoint_and_cli_surface():
    parser = build_parser()
    args = parser.parse_args(["service", "objectives", "--service", "chat", "--events"])
    assert args.service_command == "objectives"
    assert args.events is True
