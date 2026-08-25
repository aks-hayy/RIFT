import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


def test_managed_node_store_creates_persistent_identity_and_config_outside_checkout(tmp_path):
    from rift.node_enrollment import ManagedNodeStore

    checkout = tmp_path / "checkout"
    checkout.mkdir()
    store = ManagedNodeStore(tmp_path / "runtime", checkout_root=checkout)

    first = store.ensure_identity(display_name="worker-one", port=11750)
    second = store.ensure_identity(display_name="changed-name", port=11751)

    assert first.node_id == second.node_id
    assert first.display_name == "worker-one"
    assert second.port == 11750
    assert first.config_path.parent == tmp_path / "runtime" / "node"
    assert not (checkout / "node-agent.yaml").exists()
    assert json.loads(first.identity_path.read_text(encoding="utf-8"))["node_id"] == first.node_id
    config = first.config_path.read_text(encoding="utf-8")
    assert "allow_inference: false" in config
    assert "allow_launch: false" in config


def test_managed_node_store_creates_stable_private_key_and_csr(tmp_path):
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    from cryptography.x509.oid import NameOID
    from rift.node_enrollment import ManagedNodeStore

    store = ManagedNodeStore(tmp_path / "runtime")
    identity = store.ensure_identity(display_name="worker-one")
    first = store.ensure_csr(identity.node_id)
    second = store.ensure_csr(identity.node_id)

    assert first["csr_pem"] == second["csr_pem"]
    assert first["private_key_path"] == second["private_key_path"]
    csr = x509.load_pem_x509_csr(first["csr_pem"].encode("ascii"))
    assert csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == identity.node_id
    key = serialization.load_pem_private_key(Path(first["private_key_path"]).read_bytes(), password=None)
    assert key is not None


def test_pairing_handshake_derives_same_code_and_envelope_key():
    from rift.node_enrollment import PairingHandshake

    node = PairingHandshake.create(role="node")
    controller = PairingHandshake.create(role="controller")
    transcript = "enrollment-1|node-a|controller-a"

    node_result = node.complete(controller.public_key, transcript)
    controller_result = controller.complete(node.public_key, transcript)

    assert node_result.code == controller_result.code
    assert node_result.envelope_key == controller_result.envelope_key
    assert len(node_result.code) == 6
    assert node_result.code.isdigit()


def test_pairing_handshake_rejects_changed_transcript():
    from rift.node_enrollment import PairingHandshake

    node = PairingHandshake.create(role="node")
    controller = PairingHandshake.create(role="controller")
    result = node.complete(controller.public_key, "original")

    assert result.code != controller.complete(node.public_key, "changed").code


def test_pairing_envelope_detects_tampering():
    from rift.node_enrollment import PairingHandshake

    node = PairingHandshake.create(role="node")
    controller = PairingHandshake.create(role="controller")
    node_result = node.complete(controller.public_key, "session")
    controller_result = controller.complete(node.public_key, "session")
    envelope = controller_result.encrypt({"certificate": "public-cert"})
    envelope["ciphertext"] = envelope["ciphertext"][:-2] + "aa"

    try:
        node_result.decrypt(envelope)
    except ValueError as exc:
        assert "encrypted enrollment payload" in str(exc)
    else:
        raise AssertionError("tampered enrollment payload was accepted")


def test_node_certificate_supports_server_and_client_authentication(tmp_path):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    from rift.mesh.identity import NodeCertificateAuthority

    authority = NodeCertificateAuthority(tmp_path / "pki")
    key = ec.generate_private_key(ec.SECP256R1())
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "node-test")]))
        .sign(key, hashes.SHA256())
    )
    issued = authority.issue_node_certificate(
        node_id="node-test",
        csr_pem=csr.public_bytes(serialization.Encoding.PEM).decode("ascii"),
        addresses=["127.0.0.1"],
    )
    cert = x509.load_pem_x509_certificate(issued["certificate_pem"].encode("ascii"))
    usages = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert ExtendedKeyUsageOID.CLIENT_AUTH in usages
    assert ExtendedKeyUsageOID.SERVER_AUTH in usages
    assert x509.UniformResourceIdentifier("rift-node:node-test") in names
    assert x509.IPAddress(__import__("ipaddress").ip_address("127.0.0.1")) in names


def test_enrollment_window_requires_matching_node_code_and_expires(tmp_path):
    from rift.mesh.bootstrap import EnrollmentWindow
    from rift.node_enrollment import PairingHandshake

    now = [100.0]
    window = EnrollmentWindow(
        controller_id="controller-a",
        clock=lambda: now[0],
        id_factory=lambda: "enroll-1",
    )
    window.open(ttl_seconds=600)
    node_handshake = PairingHandshake.create(role="node")
    challenge = window.begin(
        node_id="node-a",
        display_name="worker-a",
        endpoint="https://127.0.0.1:11750",
        csr_pem="CSR",
        node_public_key=node_handshake.public_key,
    )
    node_result = node_handshake.complete(
        bytes.fromhex(challenge["controller_public_key"]), challenge["transcript"]
    )

    try:
        window.approve("enroll-1", "000000")
    except PermissionError:
        pass
    else:
        raise AssertionError("wrong pairing code was accepted")

    approved = window.approve("enroll-1", node_result.code)
    assert approved["state"] == "ENROLLED"
    encrypted = window.encrypt_for("enroll-1", {"certificate": "CERT"})
    assert node_result.decrypt(encrypted)["certificate"] == "CERT"

    now[0] = 1000.0
    try:
        window.status("enroll-1")
    except TimeoutError:
        pass
    else:
        raise AssertionError("expired enrollment session remained active")


def test_mesh_controller_managed_bootstrap_returns_encrypted_certificate(tmp_path):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    from rift.mesh.controller import MeshController
    from rift.node_enrollment import PairingHandshake

    controller = MeshController(root=tmp_path / "mesh")
    controller.open_enrollment_window(ttl_seconds=600)
    node_id = "node-managed"
    key = ec.generate_private_key(ec.SECP256R1())
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, node_id)]))
        .sign(key, hashes.SHA256())
    )
    node_handshake = PairingHandshake.create(role="node")
    challenge = controller.bootstrap_begin(
        node_id=node_id,
        display_name="managed-worker",
        endpoint="https://127.0.0.1:11750",
        csr_pem=csr.public_bytes(serialization.Encoding.PEM).decode("ascii"),
        node_public_key=node_handshake.public_key.hex(),
    )
    node_result = node_handshake.complete(
        bytes.fromhex(challenge["controller_public_key"]), challenge["transcript"]
    )
    controller.approve_enrollment(challenge["enrollment_id"], node_result.code)
    bundle = controller.bootstrap_status(challenge["enrollment_id"])
    payload = node_result.decrypt(bundle["certificate_envelope"])

    assert payload["node_id"] == node_id
    assert "BEGIN CERTIFICATE" in payload["certificate_pem"]
    assert controller.nodes()["nodes"][0]["trust_state"] == "ENROLLED"


def test_managed_enrollment_remains_visible_after_controller_restart(tmp_path):
    from rift.mesh.controller import MeshController

    root = tmp_path / "mesh"
    controller = MeshController(root=root)
    controller.enrollments.adopt_approved(
        enrollment_id="enroll-persistent",
        node_id="node-persistent",
        node_hint="persistent-worker",
        endpoint="https://node:11750",
    )
    controller.enrollments.activate(
        "enroll-persistent", certificate_fingerprint="sha256:persistent"
    )

    restarted = MeshController(root=root)
    enrollments = restarted.managed_enrollments()["enrollments"]

    assert any(
        item.get("enrollment_id") == "enroll-persistent" and item.get("state") == "ACTIVE"
        for item in enrollments
    ), enrollments


def test_control_api_exposes_managed_enrollment_window_and_bootstrap(tmp_path):
    from rift.mesh.controller import MeshController
    from rift.server import RiftServerRuntime

    controller = MeshController(root=tmp_path / "mesh")
    runtime = RiftServerRuntime(mesh_controller_factory=lambda: controller)
    opened = runtime.control_post(
        "/api/rift/v2/mesh/enrollment-window", {"ttl_seconds": 600}
    )
    assert opened["open"] is True
    listed = runtime.control_get("/api/rift/v2/mesh/enrollments")
    assert listed["enrollments"] == []
    closed = runtime.control_delete("/api/rift/v2/mesh/enrollment-window")
    assert closed["open"] is False


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        test_managed_node_store_creates_persistent_identity_and_config_outside_checkout(Path(tmp))
    with tempfile.TemporaryDirectory() as tmp:
        test_managed_node_store_creates_stable_private_key_and_csr(Path(tmp))
    test_pairing_handshake_derives_same_code_and_envelope_key()
    test_pairing_handshake_rejects_changed_transcript()
    test_pairing_envelope_detects_tampering()
    with tempfile.TemporaryDirectory() as tmp:
        test_node_certificate_supports_server_and_client_authentication(Path(tmp))
    with tempfile.TemporaryDirectory() as tmp:
        test_enrollment_window_requires_matching_node_code_and_expires(Path(tmp))
    with tempfile.TemporaryDirectory() as tmp:
        test_mesh_controller_managed_bootstrap_returns_encrypted_certificate(Path(tmp))
    with tempfile.TemporaryDirectory() as tmp:
        test_managed_enrollment_remains_visible_after_controller_restart(Path(tmp))
    with tempfile.TemporaryDirectory() as tmp:
        test_control_api_exposes_managed_enrollment_window_and_bootstrap(Path(tmp))
    print("node_enrollment_tests: PASS")
