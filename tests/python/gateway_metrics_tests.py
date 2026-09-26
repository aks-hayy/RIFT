import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from rift.gateway import GatewayPolicy, RiftGatewayRuntime


class _Orchestrator:
    def __init__(self, state):
        self.state = state

    def read_state(self):
        return self.state


def test_route_metrics_are_scoped_and_keep_aggregate_totals(tmp_path):
    runtime = RiftGatewayRuntime(
        root=tmp_path,
        data_root=tmp_path / ".rift",
        policy=GatewayPolicy(requests_per_minute=0, burst_requests_per_second=0),
        orchestrator_factory=lambda: _Orchestrator({"services": {}}),
    )
    runtime.begin_request(12, route_scope="service:chat")
    runtime.finish_request(
        request_id="req-1",
        method="POST",
        path="/v1/chat/completions",
        identity="client",
        status=200,
        latency_seconds=0.25,
        bytes_sent=24,
        backend_service="chat",
        fallback_count=0,
        token_estimate=None,
        error=None,
        route_scope="service:chat",
    )
    runtime.reject(
        "authentication_rejected",
        status=401,
        request_id="req-2",
        method="POST",
        path="/v1/chat/completions",
        identity="client",
        error="invalid key",
        route_scope="service:chat",
    )
    metrics = runtime.metrics()
    route = metrics["route_metrics"]["service:chat"]
    assert metrics["requests_total"] == 2
    assert route["requests_total"] == 2
    assert route["requests_succeeded"] == 1
    assert route["requests_failed"] == 1
    assert route["status_codes"] == {"200": 1, "401": 1}
    assert route["average_latency_seconds"] == 0.125


def test_virtual_group_path_resolves_to_member_order(tmp_path):
    runtime_root = tmp_path / ".rift"
    catalog_path = runtime_root / "mesh" / "services.json"
    catalog_path.parent.mkdir(parents=True)
    catalog_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "services": [],
                "groups": [
                    {
                        "group_id": "team-a",
                        "service_ids": ["chat", "backup"],
                        "default_service": "chat",
                        "gateway_path": "/team-a",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    runtime = RiftGatewayRuntime(
        root=tmp_path,
        data_root=runtime_root,
        policy=GatewayPolicy(requests_per_minute=0, burst_requests_per_second=0),
        orchestrator_factory=lambda: _Orchestrator({"services": {}}),
    )
    scope, upstream, members = runtime.resolve_request_path("/team-a/v1/chat/completions")
    assert scope == "group:team-a"
    assert upstream == "/v1/chat/completions"
    assert members == ["chat", "backup"]
