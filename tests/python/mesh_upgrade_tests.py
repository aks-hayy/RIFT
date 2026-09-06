import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from rift.mesh.contracts import (  # noqa: E402
    InferenceIntent,
    LinkMeasurement,
    MeshGraph,
    RuntimeOffer,
    TrustedNode,
)
from rift.mesh.routing import NoRouteError, RoutePlanner  # noqa: E402
from rift.mesh.services import ServiceCatalog, ServiceDefinition, ServiceGroup  # noqa: E402
from rift.mesh.permissions import ParticipationGrant, ParticipationMode  # noqa: E402
from rift.mesh.enrollment import EnrollmentService  # noqa: E402
from rift.mesh.contracts import NodeSighting  # noqa: E402
from rift.mesh.controller import MeshController  # noqa: E402
from rift.mesh.grants import RouteGrant, RouteGrantSigner, RouteGrantVerifier  # noqa: E402
from rift.mesh.admission import RequestCoordinator  # noqa: E402
from rift.cli.parser import build_parser  # noqa: E402
from rift.node_enrollment import ManagedNodeStore  # noqa: E402
from rift.mesh.catalog import CatalogEntry, SignedCatalogStore  # noqa: E402
from rift.mesh.artifacts import ResumableArtifactStore  # noqa: E402
from rift.mesh.gateway import MeshGatewayRouter, MeshGatewayProxy  # noqa: E402
from rift.mesh.consensus import ControllerProfile, ControllerFence  # noqa: E402
from rift.mesh.deployment import DeploymentManager  # noqa: E402


def _offer(model_id: str, offer_id: str) -> RuntimeOffer:
    return RuntimeOffer(
        offer_id=offer_id,
        task="chat",
        model_id=model_id,
        backend="cpu",
        context_tokens=4096,
        quality_score=0.8,
        first_token_ms=100,
        decode_tokens_per_second=20,
    )


def test_route_planner_honors_exact_requested_model():
    graph = MeshGraph(
        nodes={
            "entry": TrustedNode("entry", "entry", offers=[_offer("other", "entry-other")]),
            "worker": TrustedNode("worker", "worker", offers=[_offer("target", "worker-target")]),
        },
        links={
            ("entry", "worker"): LinkMeasurement("entry", "worker", 2, 4, 1, 0, 100, 100, 1, "test"),
        },
    )
    decision = RoutePlanner().resolve(
        graph=graph,
        intent=InferenceIntent("entry", "chat", 1024, model_id="target"),
    )
    assert decision.selected.node_id == "worker"
    assert decision.selected.offer_id == "worker-target"


def test_route_planner_reports_model_mismatch_as_rejection():
    graph = MeshGraph(
        nodes={"entry": TrustedNode("entry", "entry", offers=[_offer("other", "entry-other")])},
        links={},
    )
    with pytest.raises(NoRouteError, match="model"):
        RoutePlanner().resolve(
            graph=graph,
            intent=InferenceIntent("entry", "chat", 1024, model_id="target"),
        )


def test_route_planner_respects_access_only_viewpoint():
    graph = MeshGraph(
        nodes={
            "view": TrustedNode("view", "view"),
            "worker": TrustedNode("worker", "worker", compute_shared=False, offers=[_offer("target", "worker-target")]),
        },
        links={("view", "worker"): LinkMeasurement("view", "worker", 1, 2, 1, 0, 100, 100, 1, "test")},
    )
    with pytest.raises(NoRouteError, match="requested model"):
        RoutePlanner().resolve(graph=graph, intent=InferenceIntent("view", "chat", 1, model_id="target"))


def test_service_catalog_persists_groups_and_resolves_default_service(tmp_path):
    catalog = ServiceCatalog(tmp_path / "services.json")
    catalog.upsert_service(ServiceDefinition("code-small", "qwen-coder", "rev-1", groups=("code",)))
    catalog.upsert_service(ServiceDefinition("code-large", "qwen-coder", "rev-2", groups=("code",)))
    catalog.upsert_group(ServiceGroup("code", ("code-small", "code-large"), default_service="code-small"))

    reloaded = ServiceCatalog(tmp_path / "services.json")
    assert reloaded.resolve("code").service_id == "code-small"
    assert reloaded.resolve("code", "code-large").model_id == "qwen-coder"
    assert {item.service_id for item in reloaded.list_services()} == {"code-small", "code-large"}


def test_access_only_grant_cannot_enable_compute():
    grant = ParticipationGrant(mode=ParticipationMode.ACCESS_ONLY, allow_inference=True)
    with pytest.raises(ValueError, match="access-only"):
        grant.validate()


def test_share_compute_grant_requires_explicit_capability():
    grant = ParticipationGrant(mode=ParticipationMode.SHARE_COMPUTE, allow_inference=True, max_concurrency=2)
    assert grant.validate().mode is ParticipationMode.SHARE_COMPUTE


def test_enrollment_owner_grant_is_persisted_and_explicit(tmp_path):
    service = EnrollmentService(
        state_path=tmp_path / "enrollment.json",
        code_factory=lambda: "123456",
        id_factory=lambda: "enroll-1",
    )
    sighting = NodeSighting.create(
        provider="test",
        endpoint="https://node.local:11749",
        node_hint="node-a",
        api_version="2",
        bootstrap_fingerprint="sha256:test",
        ttl_seconds=60,
        observed_at=1,
    )
    service.begin(sighting)
    approved = service.approve("enroll-1", "123456")
    node_id = str(approved["node"]["node_id"])
    updated = service.set_owner_grant(
        node_id,
        ParticipationGrant(mode=ParticipationMode.SHARE_COMPUTE, allow_inference=True),
    )
    assert updated["participation"]["mode"] == "SHARE_COMPUTE"
    reloaded = EnrollmentService(state_path=tmp_path / "enrollment.json")
    assert reloaded.list_nodes()[0]["participation"]["allow_inference"] is True


def test_controller_persists_service_and_group_catalog(tmp_path):
    controller = MeshController(root=tmp_path)
    service = controller.register_service(
        {"service_id": "code-small", "model_id": "qwen-coder", "revision": "sha256:1", "groups": ["code"]}
    )
    group = controller.register_group(
        {"group_id": "code", "service_ids": ["code-small"], "default_service": "code-small", "gateway_path": "/v1/code"}
    )
    assert service["service"]["service_id"] == "code-small"
    assert group["group"]["gateway_path"] == "/v1/code"
    assert controller.groups()["groups"][0]["group_id"] == "code"


def test_outbound_activation_requires_node_proof(tmp_path):
    service = EnrollmentService(
        state_path=tmp_path / "enrollment.json",
        code_factory=lambda: "123456",
        id_factory=lambda: "enroll-1",
    )
    sighting = NodeSighting.create(
        provider="test",
        endpoint="https://node.local:11749",
        node_hint="node-a",
        api_version="2",
        bootstrap_fingerprint="sha256:test2",
        ttl_seconds=60,
        observed_at=1,
    )
    service.begin(sighting)
    service.approve("enroll-1", "123456")
    with pytest.raises(PermissionError, match="proof"):
        service.activate_outbound("enroll-1", certificate_fingerprint="sha256:cert", activation_proof="")
    active = service.activate_outbound(
        "enroll-1", certificate_fingerprint="sha256:cert", activation_proof="node-signature"
    )
    assert active["node"]["routable"] is True


def test_active_node_certificate_rotation_preserves_routability(tmp_path):
    service = EnrollmentService(
        state_path=tmp_path / "enrollment.json",
        code_factory=lambda: "123456",
        id_factory=lambda: "enroll-1",
    )
    sighting = NodeSighting.create(
        provider="test", endpoint="https://node.local:11749", node_hint="node-a",
        api_version="2", bootstrap_fingerprint="sha256:test3", ttl_seconds=60, observed_at=1,
    )
    service.begin(sighting)
    service.approve("enroll-1", "123456")
    service.activate("enroll-1", certificate_fingerprint="sha256:old")
    rotated = service.rotate_certificate("enroll-1", certificate_fingerprint="sha256:new")
    assert rotated["node"]["certificate_fingerprint"] == "sha256:new"
    assert rotated["node"]["previous_certificate_fingerprint"] == "sha256:old"
    assert rotated["node"]["routable"] is True


def test_mesh_gateway_resolves_group_to_service_and_admits_fallbacks(tmp_path):
    class Controller:
        def resolve_route(self, payload):
            assert payload["service_id"] == "code-small"
            return {
                "decision": {
                    "selected": {"node_id": "worker-a"},
                    "fallbacks": [{"node_id": "worker-b"}],
                }
            }

    catalog = ServiceCatalog(tmp_path / "services.json")
    catalog.upsert_service(ServiceDefinition("code-small", "qwen-coder", "rev-1", groups=("code",)))
    catalog.upsert_group(ServiceGroup("code", ("code-small",), default_service="code-small"))
    router = MeshGatewayRouter(Controller(), catalog, wait_timeout_seconds=30)
    admitted = router.admit("req-1", group_id="code", source_node_id="view", prompt_metadata={})
    assert admitted["node_id"] == "worker-a"
    assert admitted["service_id"] == "code-small"


def test_mesh_gateway_proxy_fails_over_without_replaying_after_response(tmp_path):
    class Controller:
        def resolve_route(self, payload):
            return {
                "decision": {"selected": {"node_id": "worker-a"}, "fallbacks": [{"node_id": "worker-b"}]},
            }

    catalog = ServiceCatalog(tmp_path / "services.json")
    catalog.upsert_service(ServiceDefinition("code", "qwen", "rev", groups=("code",)))
    catalog.upsert_group(ServiceGroup("code", ("code",), default_service="code"))
    router = MeshGatewayRouter(Controller(), catalog)
    calls = []

    def send(node_id, body, grant):
        calls.append(node_id)
        if node_id == "worker-a":
            raise ConnectionError("worker unavailable before response")
        return {"id": "resp-1", "choices": [{"message": {"content": "ok"}}]}

    result = MeshGatewayProxy(router).execute(
        {"model": "qwen", "messages": [{"role": "user", "content": "hello"}]},
        request_id="req-2",
        group_id="code",
        source_node_id="view",
        send=send,
    )
    assert result["status_code"] == 200
    assert calls == ["worker-a", "worker-b"]


def test_production_controller_fence_blocks_without_quorum_and_rejects_stale_epoch(tmp_path):
    fence = ControllerFence(tmp_path / "fence.json", controller_id="c1", profile=ControllerProfile.PRODUCTION)
    first = fence.issue("deploy", {"service_id": "code"}, ttl_seconds=30, now=100)
    assert fence.validate(first, now=110)["action"] == "deploy"
    fence.set_quorum(False)
    with pytest.raises(PermissionError, match="quorum"):
        fence.issue("scale", {}, ttl_seconds=30, now=111)
    fence.set_quorum(True)
    fence.become_leader("c2")
    with pytest.raises(PermissionError, match="epoch"):
        fence.validate(first, now=112)


def test_mesh_controller_exposes_profile_and_operation_authority(tmp_path):
    controller = MeshController(root=tmp_path)
    status = controller.controller_status()
    assert status["profile"] == "SIMPLE"
    authority = controller.issue_operation_authority("deploy", {"service_id": "code"})
    assert authority["action"] == "deploy"


def test_deployment_manager_is_idempotent_and_supports_rollback(tmp_path):
    manager = DeploymentManager(tmp_path / "deployments.json")
    first = manager.deploy("code", revision="rev-1", replicas=2)
    repeated = manager.deploy("code", revision="rev-1", replicas=2)
    assert repeated["generation"] == first["generation"]
    manager.deploy("code", revision="rev-2", replicas=3)
    rolled = manager.rollback("code")
    assert rolled["active_revision"] == "rev-1"
    scaled = manager.scale("code", replicas=4)
    assert scaled["desired_replicas"] == 4
    stopped = manager.terminate("code")
    assert stopped["status"] == "STOPPED"


def test_mesh_controller_exposes_fenced_deployment_lifecycle(tmp_path):
    controller = MeshController(root=tmp_path)
    controller.register_service({"service_id": "code", "model_id": "qwen", "revision": "rev-1"})
    deployed = controller.deploy_service("code", revision="rev-1", replicas=2)
    assert deployed["status"] == "RUNNING"
    updated = controller.scale_service("code", replicas=3)
    assert updated["desired_replicas"] == 3
    stopped = controller.terminate_service("code")
    assert stopped["status"] == "STOPPED"


def test_mesh_controller_publishes_signed_model_catalog(tmp_path):
    controller = MeshController(root=tmp_path, clock=lambda: 10.0)
    published = controller.publish_catalog(
        sequence=1,
        entries=[
            {
                "entry_id": "tiny",
                "repository": "org/tiny",
                "revision": "rev-1",
                "filename": "tiny.gguf",
                "digest": "sha256:" + "c" * 64,
                "license": "Apache-2.0",
                "size_bytes": 10,
                "baseline": {"backend": "llama.cpp"},
            }
        ],
        issued_at=1,
        expires_at=100,
    )
    assert controller.model_catalog()["sequence"] == 1
    assert published["key_id"]


def test_mesh_controller_revocation_withdraws_node_from_routing(tmp_path):
    enrollments = EnrollmentService(
        state_path=tmp_path / "enrollment.json",
        code_factory=lambda: "123456",
        id_factory=lambda: "enroll-1",
    )
    sighting = NodeSighting.create(
        provider="test", endpoint="https://node.local:11749", node_hint="node-a",
        api_version="2", bootstrap_fingerprint="sha256:test4", ttl_seconds=60, observed_at=1,
    )
    enrollments.begin(sighting)
    enrollments.approve("enroll-1", "123456")
    active = enrollments.activate("enroll-1", certificate_fingerprint="sha256:cert")
    controller = MeshController(root=tmp_path, enrollments=enrollments)
    revoked = controller.revoke_node(str(active["node"]["node_id"]))
    assert revoked["routable"] is False
    assert revoked["trust_state"] == "REVOKED"


def test_deployment_reconcile_assigns_only_healthy_shared_nodes(tmp_path):
    manager = DeploymentManager(tmp_path / "deployments.json")
    manager.deploy("code", revision="rev-1", replicas=2)
    result = manager.reconcile(
        "code",
        [
            {"node_id": "view", "healthy": True, "compute_shared": False},
            {"node_id": "worker-b", "healthy": True, "compute_shared": True},
            {"node_id": "worker-a", "healthy": True, "compute_shared": True},
        ],
    )
    assert result["status"] == "RUNNING"
    assert [item["node_id"] for item in result["actions"]] == ["worker-a", "worker-b"]


def test_route_grant_is_scoped_signed_and_rejects_tampering(tmp_path):
    signer = RouteGrantSigner(tmp_path / "route-grant-key.pem")
    grant = RouteGrant(
        grant_id="grant-1",
        controller_id="controller-1",
        source_node_id="view",
        service_id="code",
        model_id="qwen-coder",
        primary_node_id="worker",
        fallback_node_ids=("worker-2",),
        inference_endpoint="https://worker.local:8443",
        policy_hash="policy-1",
        issued_at=100.0,
        expires_at=130.0,
    )
    token = signer.issue(grant)
    verified = RouteGrantVerifier(signer.public_key()).verify(token, now=110.0)
    assert verified.service_id == "code"
    assert verified.primary_node_id == "worker"
    with pytest.raises(ValueError, match="signature"):
        RouteGrantVerifier(signer.public_key()).verify(token[:-2] + "aa", now=110.0)
    with pytest.raises(TimeoutError, match="expired"):
        RouteGrantVerifier(signer.public_key()).verify(token, now=131.0)


def test_request_coordinator_retries_candidates_then_times_out():
    now = [100.0]
    coordinator = RequestCoordinator(wait_timeout_seconds=30, clock=lambda: now[0])
    first = coordinator.submit("request-1", ["worker-a", "worker-b"])
    assert first["status"] == "DISPATCHING"
    assert first["node_id"] == "worker-a"
    retry = coordinator.fail("request-1", "worker-a", "busy")
    assert retry["status"] == "DISPATCHING"
    assert retry["node_id"] == "worker-b"
    waiting = coordinator.fail("request-1", "worker-b", "busy")
    assert waiting["status"] == "WAITING_RECOVERY"
    now[0] = 131.0
    assert coordinator.expire("request-1")["status"] == "TIMED_OUT"


def test_mesh_cli_exposes_group_and_service_operations():
    parser = build_parser()
    assert parser.parse_args(["mesh", "groups", "list"]).mesh_command == "groups"
    args = parser.parse_args(["mesh", "service", "register", "--id", "code", "--model", "qwen", "--revision", "rev-1"])
    assert args.mesh_command == "service"
    assert args.mesh_service_command == "register"
    deploy = parser.parse_args(["mesh", "deployment", "deploy", "--service", "code", "--revision", "rev-1"])
    assert deploy.mesh_command == "deployment"
    assert deploy.mesh_deployment_command == "deploy"


def test_node_local_permissions_make_compute_sharing_explicit(tmp_path):
    store = ManagedNodeStore(tmp_path)
    store.ensure_identity(display_name="view")
    with pytest.raises(ValueError, match="access-only"):
        store.update_permissions({"allow_inference": True})
    updated = store.update_permissions({"participation_mode": "SHARE_COMPUTE", "allow_inference": True})
    assert updated["permissions"]["participation_mode"] == "SHARE_COMPUTE"


def test_signed_model_catalog_rejects_tampering_and_rollback(tmp_path):
    store = SignedCatalogStore(tmp_path / "catalog")
    entry = CatalogEntry(
        entry_id="tiny-q4",
        repository="org/tiny",
        revision="abc123",
        filename="tiny.gguf",
        digest="sha256:" + "a" * 64,
        license="Apache-2.0",
        size_bytes=123,
        baseline={"context_tokens": 2048, "backend": "llama.cpp"},
    )
    signed = store.sign(sequence=1, entries=[entry], issued_at=10, expires_at=100)
    accepted = store.accept(signed, now=20)
    assert accepted["sequence"] == 1
    with pytest.raises(ValueError, match="rollback"):
        store.accept(store.sign(sequence=1, entries=[entry], issued_at=11, expires_at=100), now=20)
    tampered = dict(signed)
    tampered["entries"] = [{**tampered["entries"][0], "digest": "sha256:" + "b" * 64}]
    with pytest.raises(ValueError, match="signature"):
        store.accept(tampered, now=20)


def test_resumable_artifact_download_verifies_hash_and_atomically_activates(tmp_path):
    payload = b"model-bytes-for-rift"
    destination = tmp_path / "models" / "tiny.gguf"
    partial = destination.with_suffix(destination.suffix + ".partial")
    partial.parent.mkdir(parents=True)
    partial.write_bytes(payload[:5])

    class Response:
        status = 206
        headers = {"ETag": '"v1"', "Content-Range": f"bytes 5-{len(payload) - 1}/{len(payload)}"}

        def __init__(self):
            self._read = False

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, size=-1):
            if self._read:
                return b""
            self._read = True
            return payload[5:]

    seen = {}

    def opener(request):
        seen["range"] = request.headers.get("Range")
        return Response()

    store = ResumableArtifactStore(tmp_path / "state")
    result = store.download(
        "https://models.example/tiny.gguf",
        destination,
        expected_digest="sha256:" + __import__("hashlib").sha256(payload).hexdigest(),
        expected_size=len(payload),
        approved=True,
        opener=opener,
    )
    assert result["activated"] is True
    assert destination.read_bytes() == payload
    assert not partial.exists()
    assert seen["range"] == "bytes=5-"
