import importlib
import json
import sys
import tempfile
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = ROOT / "python"
sys.path.insert(0, str(PYTHON_ROOT))


class FakeNativeEngine:
    def __init__(self, cuda_device_id=0):
        self.cuda_device_id = cuda_device_id

    def hardware_profile(self):
        return {}

    def build_info(self):
        return {"version": "test"}


fake_core = types.ModuleType("rift._core")
fake_core.InferenceEngine = FakeNativeEngine
fake_core.__version__ = "test"
fake_core.build_info = lambda: {"version": "test"}
fake_core.cuda_device_count = lambda: 0
fake_core.inspect_model = lambda *args, **kwargs: {}
fake_core.parse_model_topology = lambda *args, **kwargs: {}
sys.modules["rift._core"] = fake_core

contracts = importlib.import_module("rift.mesh.contracts")
emulator = importlib.import_module("rift.mesh.emulator")
routing = importlib.import_module("rift.mesh.routing")
controller_mod = importlib.import_module("rift.mesh.controller")
discovery_mod = importlib.import_module("rift.mesh.discovery")
enrollment_mod = importlib.import_module("rift.mesh.enrollment")
transport_discovery = importlib.import_module("rift.mesh.discovery_transports")
topology_mod = importlib.import_module("rift.mesh.topology")
lease_mod = importlib.import_module("rift.mesh.leases")
failover_mod = importlib.import_module("rift.mesh.failover")
identity_mod = importlib.import_module("rift.mesh.identity")


def test_node_sighting_is_untrusted_and_expires():
    sighting = contracts.NodeSighting.create(
        provider="mdns",
        endpoint="https://192.168.1.20:11749",
        node_hint="phone-a",
        api_version="2",
        bootstrap_fingerprint="sha256:abc",
        ttl_seconds=120,
        observed_at=1000.0,
    )
    assert sighting.trust_state == contracts.TrustState.DISCOVERED_UNTRUSTED
    assert sighting.expires_at == 1120.0
    assert not sighting.is_expired(1119.9)
    assert sighting.is_expired(1120.0)


def test_sparse_measurement_scales_linearly_and_intensive_is_explicit():
    lab = emulator.MeshLab(seed=17)
    lab.add_standard_fleet(50)
    sparse = lab.measure(mode="sparse", candidates_per_client=3)
    assert sparse["evidence"] == "EMULATED"
    assert sparse["node_count"] == 50
    assert sparse["directional_edge_count"] <= 4 * 50

    intensive = lab.measure(mode="intensive", allow_intensive=True)
    assert intensive["directional_edge_count"] == 50 * 49
    assert intensive["cost_warning"]

    try:
        lab.measure(mode="intensive")
    except PermissionError as exc:
        assert "explicit" in str(exc).lower()
    else:
        raise AssertionError("intensive measurement ran without explicit authorization")


def test_policy_balanced_routing_prefers_suitable_local_then_remote_capacity():
    graph = emulator.MeshLab(seed=9).example_elastic_graph()
    planner = routing.RoutePlanner()

    local = planner.resolve(
        graph=graph,
        intent=contracts.InferenceIntent(
            source_node_id="laptop",
            task="chat",
            minimum_context_tokens=2048,
            privacy=contracts.PrivacyPolicy.MESH_ALLOWED,
        ),
    )
    assert local.selected.node_id == "laptop"
    assert local.selected.execution_mode == "local"

    remote = planner.resolve(
        graph=graph,
        intent=contracts.InferenceIntent(
            source_node_id="phone",
            task="chat",
            minimum_context_tokens=4096,
            privacy=contracts.PrivacyPolicy.MESH_ALLOWED,
        ),
    )
    assert remote.selected.node_id == "gpu-server"
    assert remote.selected.execution_mode == "remote"
    assert remote.fallbacks

    try:
        planner.resolve(
            graph=graph,
            intent=contracts.InferenceIntent(
                source_node_id="phone",
                task="chat",
                minimum_context_tokens=4096,
                privacy=contracts.PrivacyPolicy.LOCAL_ONLY,
            ),
        )
    except routing.NoRouteError as exc:
        assert "privacy" in str(exc).lower()
    else:
        raise AssertionError("local-only request was routed remotely")


def test_emulated_faults_change_routes_without_claiming_physical_evidence():
    lab = emulator.MeshLab(seed=3)
    graph = lab.example_elastic_graph()
    planner = routing.RoutePlanner()
    intent = contracts.InferenceIntent(
        source_node_id="phone",
        task="chat",
        minimum_context_tokens=4096,
        privacy=contracts.PrivacyPolicy.MESH_ALLOWED,
    )
    first = planner.resolve(graph=graph, intent=intent)
    assert first.selected.node_id == "gpu-server"
    lab.set_node_pressure(graph, "gpu-server", queue_depth=20, healthy=True)
    second = planner.resolve(graph=graph, intent=intent)
    assert second.selected.node_id == "laptop"
    assert second.evidence == "EMULATED"


def test_discovery_deduplicates_sightings_and_never_grants_trust():
    now = [1000.0]
    first = contracts.NodeSighting.create(
        provider="mdns",
        endpoint="https://192.168.1.20:11749",
        node_hint="studio-pc",
        api_version="2",
        bootstrap_fingerprint="sha256:node-a",
        ttl_seconds=30,
        observed_at=now[0],
    )
    duplicate = contracts.NodeSighting.create(
        provider="mdns",
        endpoint="https://192.168.1.20:11749",
        node_hint="studio-pc",
        api_version="2",
        bootstrap_fingerprint="sha256:node-a",
        ttl_seconds=60,
        observed_at=now[0] + 1,
    )
    provider = discovery_mod.StaticDiscoveryProvider("mdns", [first, duplicate])
    manager = discovery_mod.DiscoveryManager([provider], clock=lambda: now[0])

    found = manager.scan()
    assert len(found) == 1
    assert found[0].trust_state == contracts.TrustState.DISCOVERED_UNTRUSTED
    assert manager.provider_diagnostics()[0]["scan_count"] == 1

    now[0] = 1062.0
    assert manager.list_sightings() == []


def test_enrollment_requires_correct_pairing_code_and_certificate_activation(tmp_path):
    now = [2000.0]
    sighting = contracts.NodeSighting.create(
        provider="usb-network",
        endpoint="https://192.168.55.2:11749",
        node_hint="field-phone",
        api_version="2",
        bootstrap_fingerprint="sha256:phone",
        ttl_seconds=120,
        observed_at=now[0],
    )
    service = enrollment_mod.EnrollmentService(
        state_path=tmp_path / "enrollment.json",
        clock=lambda: now[0],
        code_factory=lambda: "483921",
        id_factory=lambda: "enroll-1",
    )
    challenge = service.begin(sighting, ttl_seconds=90)
    assert challenge["state"] == "PAIRING_PENDING"
    assert "pairing_code" not in challenge

    try:
        service.approve("enroll-1", "000000")
    except PermissionError as exc:
        assert "pairing" in str(exc).lower()
    else:
        raise AssertionError("wrong pairing code was accepted")

    approved = service.approve("enroll-1", "483921")
    assert approved["node"]["trust_state"] == "ENROLLED"
    assert approved["node"]["routable"] is False
    assert approved["node"]["mtls_status"] == "CERTIFICATE_REQUIRED"

    active = service.activate("enroll-1", certificate_fingerprint="sha256:cert")
    assert active["node"]["trust_state"] == "ACTIVE"
    assert active["node"]["routable"] is True
    assert service.list_nodes()[0]["certificate_fingerprint"] == "sha256:cert"

    reloaded = enrollment_mod.EnrollmentService(state_path=tmp_path / "enrollment.json")
    assert reloaded.list_nodes()[0]["trust_state"] == "ACTIVE"
    revoked = reloaded.revoke(active["node"]["node_id"])
    assert revoked["trust_state"] == "REVOKED"


def test_mesh_controller_exposes_ui_first_discovery_and_enrollment(tmp_path):
    sighting = contracts.NodeSighting.create(
        provider="mdns",
        endpoint="https://10.0.0.14:11749",
        node_hint="render-box",
        api_version="2",
        bootstrap_fingerprint="sha256:render",
        ttl_seconds=300,
        observed_at=3000.0,
    )
    manager = discovery_mod.DiscoveryManager(
        [discovery_mod.StaticDiscoveryProvider("mdns", [sighting])],
        clock=lambda: 3000.0,
    )
    enrollments = enrollment_mod.EnrollmentService(
        state_path=tmp_path / "enrollment.json",
        clock=lambda: 3000.0,
        code_factory=lambda: "111222",
        id_factory=lambda: "enrollment-fixed",
    )
    mesh = controller_mod.MeshController(
        root=tmp_path,
        discovery=manager,
        enrollments=enrollments,
    )

    discovery_payload = mesh.discover()
    assert discovery_payload["evidence"] == "LIVE_DISCOVERY"
    assert discovery_payload["sightings"][0]["trust_state"] == "DISCOVERED_UNTRUSTED"
    assert mesh.nodes()["nodes"] == []
    try:
        mesh.discover(options={"private_networks": ["192.168.4.0/30"]})
    except PermissionError as exc:
        assert "allow_subnet_scan" in str(exc)
    else:
        raise AssertionError("controller started a subnet scan without explicit permission")

    challenge = mesh.begin_enrollment(sighting.sighting_id, ttl_seconds=60)
    approved = mesh.approve_enrollment(challenge["enrollment_id"], "111222")
    assert approved["node"]["trust_state"] == "ENROLLED"
    assert len(mesh.nodes()["nodes"]) == 1
    topology = mesh.topology()
    assert topology["evidence"] == "DISCOVERY_AND_ENROLLMENT_STATE"
    assert topology["links"] == []


def test_private_subnet_scan_is_bounded_consent_gated_and_private_only():
    probed = []

    def probe(endpoint, interface_id):
        probed.append((endpoint, interface_id))
        return {
            "node_hint": endpoint.split("//", 1)[1].split(":", 1)[0],
            "api_version": "2",
            "bootstrap_fingerprint": f"sha256:{len(probed)}",
            "ttl_seconds": 30,
        }

    blocked = transport_discovery.PrivateSubnetDiscoveryProvider(
        networks=["192.168.50.0/30"], authorized=False, probe=probe, clock=lambda: 10.0
    )
    try:
        list(blocked.discover())
    except PermissionError as exc:
        assert "consent" in str(exc).lower()
    else:
        raise AssertionError("subnet scan ran without consent")

    provider = transport_discovery.PrivateSubnetDiscoveryProvider(
        networks=["192.168.50.0/29"],
        authorized=True,
        max_hosts=3,
        probe=probe,
        clock=lambda: 10.0,
    )
    found = list(provider.discover())
    assert len(found) == 3
    assert len(probed) == 3
    assert all(item.provider == "private-subnet" for item in found)

    try:
        transport_discovery.PrivateSubnetDiscoveryProvider(
            networks=["8.8.8.0/30"], authorized=True, probe=probe
        )
    except ValueError as exc:
        assert "private" in str(exc).lower()
    else:
        raise AssertionError("public address range was accepted for discovery")


def test_mass_storage_and_adb_bootstrap_are_explicit_and_parsed(tmp_path):
    marker = tmp_path / ".rift" / "rift-node.json"
    marker.parent.mkdir(parents=True)
    marker.write_text(
        '{"endpoint":"https://192.168.55.2:11749","node_hint":"usb-phone",'
        '"api_version":"2","bootstrap_fingerprint":"sha256:usb"}',
        encoding="utf-8",
    )
    storage = transport_discovery.MassStorageBootstrapProvider(
        roots=[tmp_path], clock=lambda: 20.0
    )
    found = list(storage.discover())
    assert len(found) == 1
    assert found[0].provider == "mass-storage"

    commands = []

    def runner(command):
        commands.append(command)
        if command[-1] == "devices":
            return "List of devices attached\nSERIAL-1\tdevice\n"
        return (
            '{"endpoint":"https://127.0.0.1:11749","node_hint":"android",'
            '"api_version":"2","bootstrap_fingerprint":"sha256:adb"}'
        )

    adb = transport_discovery.AdbBootstrapProvider(runner=runner, clock=lambda: 30.0)
    adb_found = list(adb.discover())
    assert len(adb_found) == 1
    assert adb_found[0].interface_id == "adb:SERIAL-1"
    assert len(commands) == 2

    mdns = transport_discovery.MdnsDiscoveryProvider(
        resolver=lambda: [
            {
                "endpoint": "https://192.168.1.40:11749",
                "node_hint": "mdns-node",
                "api_version": "2",
                "bootstrap_fingerprint": "sha256:mdns",
                "interface_id": "wifi",
            }
        ],
        clock=lambda: 40.0,
    )
    mdns_found = list(mdns.discover())
    assert mdns_found[0].provider == "mdns"
    assert mdns_found[0].interface_id == "wifi"


def test_topology_measurement_is_sparse_by_default_and_intensive_by_consent():
    nodes = ["a", "b", "c", "d", "e"]
    calls = []

    def probe(source, target):
        calls.append((source, target))
        return contracts.LinkMeasurement(source, target, 4, 7, 1, 0, 900, 800, 1, "EMULATED")

    planner = topology_mod.TopologyMeasurer(probe=probe, clock=lambda: 1.0)
    sparse = planner.measure(nodes, mode="sparse", candidates_per_node=2)
    assert sparse["mode"] == "sparse"
    assert len(sparse["links"]) <= len(nodes) * 2
    assert sparse["evidence"] == "EMULATED"

    try:
        planner.measure(nodes, mode="intensive")
    except PermissionError:
        pass
    else:
        raise AssertionError("all-pairs probing ran without consent")

    calls.clear()
    intensive = planner.measure(nodes, mode="intensive", allow_intensive=True)
    assert len(intensive["links"]) == len(nodes) * (len(nodes) - 1)


def test_route_leases_expire_and_cached_autonomy_fails_closed(tmp_path):
    now = [5000.0]
    store = lease_mod.RouteLeaseStore(tmp_path / "leases.json", clock=lambda: now[0])
    lease = store.issue(
        source_node_id="phone",
        service_id="chat",
        primary_node_id="gpu",
        fallback_node_ids=["laptop"],
        ttl_seconds=30,
        policy_hash="policy-v1",
    )
    assert store.resolve("phone", "chat", policy_hash="policy-v1")["lease_id"] == lease["lease_id"]
    try:
        store.resolve("phone", "chat", policy_hash="policy-v2")
    except PermissionError as exc:
        assert "policy" in str(exc).lower()
    else:
        raise AssertionError("stale policy lease was used")
    now[0] = 5031.0
    try:
        store.resolve("phone", "chat", policy_hash="policy-v1")
    except TimeoutError:
        pass
    else:
        raise AssertionError("expired route lease was used")


def test_controller_promotion_is_manual_or_quorum_gated(tmp_path):
    recovery = failover_mod.ControllerRecovery(
        tmp_path / "recovery.json", recovery_key="correct horse battery staple"
    )
    try:
        recovery.promote_manual("standby-a", recovery_key="wrong")
    except PermissionError:
        pass
    else:
        raise AssertionError("controller promoted with a wrong recovery key")
    manual = recovery.promote_manual(
        "standby-a", recovery_key="correct horse battery staple"
    )
    assert manual["controller_node_id"] == "standby-a"
    assert manual["mode"] == "manual-recovery-key"

    election = failover_mod.QuorumElection(voters=["a", "b", "c"])
    election.vote(term=2, voter="a", candidate="b")
    assert election.winner(term=2) is None
    election.vote(term=2, voter="c", candidate="b")
    assert election.winner(term=2) == "b"


def test_controller_routes_only_active_capabilities_and_issues_short_lease(tmp_path):
    now = [7000.0]
    phone = contracts.NodeSighting.create(
        provider="mdns",
        endpoint="https://10.0.0.2:11749",
        node_hint="phone",
        api_version="2",
        bootstrap_fingerprint="sha256:phone-route",
        ttl_seconds=300,
        observed_at=now[0],
    )
    gpu = contracts.NodeSighting.create(
        provider="mdns",
        endpoint="https://10.0.0.3:11749",
        node_hint="gpu",
        api_version="2",
        bootstrap_fingerprint="sha256:gpu-route",
        ttl_seconds=300,
        observed_at=now[0],
    )
    manager = discovery_mod.DiscoveryManager(
        [discovery_mod.StaticDiscoveryProvider("mdns", [phone, gpu])], clock=lambda: now[0]
    )
    codes = iter(["111111", "222222"])
    enrollment_ids = iter(["enroll-phone", "enroll-gpu"])
    enrollments = enrollment_mod.EnrollmentService(
        state_path=tmp_path / "enrollment.json",
        clock=lambda: now[0],
        code_factory=lambda: next(codes),
        id_factory=lambda: next(enrollment_ids),
    )
    mesh = controller_mod.MeshController(
        root=tmp_path, discovery=manager, enrollments=enrollments, clock=lambda: now[0]
    )
    mesh.discover()
    ids = {}
    for sighting, code in ((phone, "111111"), (gpu, "222222")):
        challenge = mesh.begin_enrollment(sighting.sighting_id)
        approved = mesh.approve_enrollment(challenge["enrollment_id"], code)
        active = mesh.activate_enrollment(challenge["enrollment_id"], f"sha256:cert-{sighting.node_hint}")
        ids[sighting.node_hint] = active["node"]["node_id"]

    mesh.update_capability(
        ids["phone"],
        {
            "sequence": 1,
            "observed_at": now[0],
            "hardware": {"class": "android"},
            "runtime_offers": [
                {
                    "offer_id": "tiny",
                    "task": "chat",
                    "model_id": "tiny-1b",
                    "backend": "llama.cpp",
                    "context_tokens": 1024,
                    "quality_score": 30,
                    "first_token_ms": 900,
                    "decode_tokens_per_second": 3,
                }
            ],
        },
    )
    mesh.update_capability(
        ids["gpu"],
        {
            "sequence": 1,
            "observed_at": now[0],
            "hardware": {"class": "cuda"},
            "runtime_offers": [
                {
                    "offer_id": "fast-chat",
                    "task": "chat",
                    "model_id": "qwen-14b",
                    "backend": "vllm",
                    "context_tokens": 8192,
                    "quality_score": 82,
                    "first_token_ms": 100,
                    "decode_tokens_per_second": 50,
                }
            ],
        },
    )
    mesh.record_link(
        {
            "source_node_id": ids["phone"],
            "target_node_id": ids["gpu"],
            "rtt_p50_ms": 5,
            "rtt_p95_ms": 8,
            "jitter_ms": 1,
            "loss_ratio": 0,
            "upload_mbps": 200,
            "download_mbps": 500,
            "observed_at": now[0],
            "evidence": "EMULATED",
        }
    )
    result = mesh.resolve_route(
        {
            "source_node_id": ids["phone"],
            "service_id": "chat-service",
            "task": "chat",
            "minimum_context_tokens": 4096,
            "privacy": "MESH_ALLOWED",
            "policy_hash": "policy-1",
            "lease_ttl_seconds": 30,
        }
    )
    assert result["decision"]["selected"]["node_id"] == ids["gpu"]
    assert result["lease"]["primary_node_id"] == ids["gpu"]
    assert result["lease"]["controller_id"] == "rift-controller"
    assert result["lease"]["inference_endpoint"].startswith("https://")
    assert result["lease"]["bearer_token"]
    assert mesh.topology()["links"][0]["evidence"] == "EMULATED"


def test_node_certificate_authority_issues_client_identity_without_private_key(tmp_path):
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    except ImportError:
        return
    authority = identity_mod.NodeCertificateAuthority(tmp_path / "pki")
    private_key = ec.generate_private_key(ec.SECP256R1())
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "node-test")]))
        .sign(private_key, hashes.SHA256())
    )
    issued = authority.issue_node_certificate(
        node_id="node-test", csr_pem=csr.public_bytes(serialization.Encoding.PEM).decode()
    )
    assert "private" not in " ".join(issued).lower()
    certificate = x509.load_pem_x509_certificate(issued["certificate_pem"].encode())
    usage = certificate.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    assert ExtendedKeyUsageOID.CLIENT_AUTH in usage
    assert issued["fingerprint"].startswith("sha256:")
    reloaded = identity_mod.NodeCertificateAuthority(tmp_path / "pki")
    assert reloaded.ca_fingerprint() == authority.ca_fingerprint()


def test_active_node_accepts_monotonic_telemetry_without_prompt_content(tmp_path):
    sighting = contracts.NodeSighting.create(
        provider="test",
        endpoint="https://phone.example:7443",
        node_hint="phone",
        api_version="2",
        bootstrap_fingerprint="sha256:bootstrap",
        ttl_seconds=120,
        observed_at=1,
    )
    enrollments = enrollment_mod.EnrollmentService(
        state_path=tmp_path / "enrollment.json", code_factory=lambda: "123456"
    )
    controller = controller_mod.MeshController(root=tmp_path, enrollments=enrollments)
    challenge = enrollments.begin(sighting)
    controller.approve_enrollment(challenge["enrollment_id"], "123456")
    activation = controller.activate_enrollment(challenge["enrollment_id"], "sha256:phone")
    try:
        controller.record_telemetry(challenge["node_id"], {"sequence": 1}, "wrong-token")
    except PermissionError:
        pass
    else:
        raise AssertionError("telemetry accepted an invalid node credential")

    result = controller.record_telemetry(
        challenge["node_id"],
        {"sequence": 1, "observed_at": 10, "battery_percent": 90, "thermal_status": 0},
        activation["node_token"],
    )
    assert result["telemetry"]["sequence"] == 1
    assert "prompt" not in json.dumps(result).lower()
    try:
        controller.record_telemetry(challenge["node_id"], {"sequence": 1}, activation["node_token"])
    except ValueError as exc:
        assert "sequence" in str(exc)
    else:
        raise AssertionError("stale telemetry sequence should be rejected")


def main():
    test_node_sighting_is_untrusted_and_expires()
    test_sparse_measurement_scales_linearly_and_intensive_is_explicit()
    test_policy_balanced_routing_prefers_suitable_local_then_remote_capacity()
    test_emulated_faults_change_routes_without_claiming_physical_evidence()
    test_discovery_deduplicates_sightings_and_never_grants_trust()
    with tempfile.TemporaryDirectory() as directory:
        test_enrollment_requires_correct_pairing_code_and_certificate_activation(Path(directory))
    with tempfile.TemporaryDirectory() as directory:
        test_mesh_controller_exposes_ui_first_discovery_and_enrollment(Path(directory))
    test_private_subnet_scan_is_bounded_consent_gated_and_private_only()
    with tempfile.TemporaryDirectory() as directory:
        test_mass_storage_and_adb_bootstrap_are_explicit_and_parsed(Path(directory))
    test_topology_measurement_is_sparse_by_default_and_intensive_by_consent()
    with tempfile.TemporaryDirectory() as directory:
        test_route_leases_expire_and_cached_autonomy_fails_closed(Path(directory))
    with tempfile.TemporaryDirectory() as directory:
        test_controller_promotion_is_manual_or_quorum_gated(Path(directory))
    with tempfile.TemporaryDirectory() as directory:
        test_controller_routes_only_active_capabilities_and_issues_short_lease(Path(directory))
    with tempfile.TemporaryDirectory() as directory:
        test_node_certificate_authority_issues_client_identity_without_private_key(Path(directory))
    with tempfile.TemporaryDirectory() as directory:
        test_active_node_accepts_monotonic_telemetry_without_prompt_content(Path(directory))
    print("RIFT mesh contract and emulator tests passed")


if __name__ == "__main__":
    main()
