"""Stateful controller facade consumed by the RIFT API and operator UI."""

from __future__ import annotations

from pathlib import Path
from dataclasses import asdict
import json
import hashlib
import secrets
import time
from typing import Callable
from typing import Iterable
from urllib.parse import urlparse

from .contracts import (
    InferenceIntent,
    LinkMeasurement,
    MeshGraph,
    PrivacyPolicy,
    RuntimeOffer,
    TrustState,
    TrustedNode,
)
from .discovery import DiscoveryManager, DiscoveryProvider
from .discovery_transports import (
    AdbBootstrapProvider,
    MassStorageBootstrapProvider,
    MdnsDiscoveryProvider,
    PrivateSubnetDiscoveryProvider,
    UsbNetworkDiscoveryProvider,
)
from .enrollment import EnrollmentService
from .bootstrap import EnrollmentWindow
from .leases import RouteLeaseStore
from .identity import NodeCertificateAuthority
from .routing import RoutePlanner


class MeshController:
    def __init__(
        self,
        *,
        root: Path | str = ".rift/mesh",
        providers: Iterable[DiscoveryProvider] | None = None,
        discovery: DiscoveryManager | None = None,
        enrollments: EnrollmentService | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.controller_id = self._load_controller_id()
        default_providers = (MdnsDiscoveryProvider(), AdbBootstrapProvider())
        self.discovery_manager = discovery or DiscoveryManager(
            default_providers if providers is None else providers
        )
        self.enrollments = enrollments or EnrollmentService(
            state_path=self.root / "enrollment.json", clock=clock
        )
        self.route_leases = RouteLeaseStore(self.root / "route-leases.json", clock=clock)
        self._certificate_authority: NodeCertificateAuthority | None = None
        self.route_planner = RoutePlanner()
        self.enrollment_window = EnrollmentWindow(
            controller_id=self.controller_id,
            clock=clock,
        )
        self._bootstrap_payloads: dict[str, dict[str, object]] = {}
        self._bootstrap_fingerprints: dict[str, str] = {}
        self._links_path = self.root / "links.json"
        self._links = self._load_links()

    def _load_controller_id(self) -> str:
        path = self.root / "controller-id.json"
        if path.is_file():
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                controller_id = str(value.get("controller_id") or "").strip()
                if controller_id:
                    return controller_id
            except (OSError, json.JSONDecodeError, AttributeError):
                pass
        controller_id = f"controller-{secrets.token_hex(8)}"
        path.write_text(json.dumps({"controller_id": controller_id}, indent=2), encoding="utf-8")
        if hasattr(path, "chmod"):
            try:
                path.chmod(0o600)
            except OSError:
                pass
        return controller_id

    def _load_links(self) -> dict[tuple[str, str], LinkMeasurement]:
        if not self._links_path.is_file():
            return {}
        try:
            payload = json.loads(self._links_path.read_text(encoding="utf-8"))
            return {
                (str(item["source_node_id"]), str(item["target_node_id"])): LinkMeasurement(**item)
                for item in payload.get("links", [])
            }
        except (OSError, ValueError, TypeError, json.JSONDecodeError, KeyError) as exc:
            raise RuntimeError(f"failed to load mesh links: {exc}") from exc

    def _save_links(self) -> None:
        self._links_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._links_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(
                {"schema_version": 1, "links": [asdict(item) for item in self._links.values()]},
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        temporary.replace(self._links_path)

    def discover(
        self,
        providers: Iterable[str] | None = None,
        *,
        options: dict[str, object] | None = None,
    ) -> dict[str, object]:
        settings = options or {}
        private_networks = settings.get("private_networks") or []
        usb_networks = settings.get("usb_networks") or []
        storage_roots = settings.get("storage_roots") or []
        if private_networks:
            if not bool(settings.get("allow_subnet_scan", False)):
                raise PermissionError("private subnet scan requires allow_subnet_scan=true")
            self.discovery_manager.register(
                PrivateSubnetDiscoveryProvider(
                    networks=[str(value) for value in private_networks],
                    authorized=True,
                    max_hosts=int(settings.get("max_hosts") or 256),
                ),
                replace=True,
            )
        if usb_networks:
            if not bool(settings.get("allow_usb_scan", False)):
                raise PermissionError("USB-network scan requires allow_usb_scan=true")
            self.discovery_manager.register(
                UsbNetworkDiscoveryProvider(
                    networks=[str(value) for value in usb_networks],
                    authorized=True,
                    max_hosts=int(settings.get("max_usb_hosts") or 32),
                ),
                replace=True,
            )
        if storage_roots:
            self.discovery_manager.register(
                MassStorageBootstrapProvider(roots=[str(value) for value in storage_roots]),
                replace=True,
            )
        selected = list(providers) if providers is not None else None
        for name, enabled in (
            ("private-subnet", bool(private_networks)),
            ("usb-network", bool(usb_networks)),
            ("mass-storage", bool(storage_roots)),
        ):
            if enabled and selected is not None and name not in selected:
                selected.append(name)
        return self._sighting_payload(self.discovery_manager.scan(selected))

    def sightings(self) -> dict[str, object]:
        return self._sighting_payload(self.discovery_manager.list_sightings())

    def _sighting_payload(self, sightings) -> dict[str, object]:
        return {
            "api_version": "2",
            "evidence": "LIVE_DISCOVERY",
            "trust_boundary": "Discovery never grants trust. Pairing and certificate activation are separate.",
            "sightings": [item.to_dict() for item in sightings],
            "providers": self.discovery_manager.provider_diagnostics(),
        }

    def begin_enrollment(self, sighting_id: str, *, ttl_seconds: int = 120) -> dict[str, object]:
        return self.enrollments.begin(
            self.discovery_manager.get(sighting_id), ttl_seconds=ttl_seconds
        )

    def open_enrollment_window(self, *, ttl_seconds: int = 600) -> dict[str, object]:
        return self.enrollment_window.open(ttl_seconds=ttl_seconds)

    def close_enrollment_window(self) -> dict[str, object]:
        return self.enrollment_window.close()

    def enrollment_window_status(self) -> dict[str, object]:
        return self.enrollment_window.status()

    def managed_enrollments(self) -> dict[str, object]:
        records = {
            str(item["enrollment_id"]): dict(item)
            for item in self.enrollments.list_enrollments()
            if item.get("enrollment_id")
        }
        for session in self.enrollment_window.list_sessions():
            enrollment_id = str(session.get("enrollment_id") or "")
            if enrollment_id:
                records[enrollment_id] = {**records.get(enrollment_id, {}), **session}
        return {
            "api_version": "2",
            "enrollments": [records[key] for key in sorted(records)],
        }

    def bootstrap_begin(
        self,
        *,
        node_id: str,
        display_name: str,
        endpoint: str,
        csr_pem: str,
        node_public_key: str,
    ) -> dict[str, object]:
        try:
            public_key = bytes.fromhex(node_public_key)
        except ValueError as exc:
            raise ValueError("node_public_key must be hexadecimal X25519 bytes") from exc
        if len(public_key) != 32:
            raise ValueError("node_public_key must contain 32 bytes")
        return self.enrollment_window.begin(
            node_id=node_id,
            display_name=display_name,
            endpoint=endpoint,
            csr_pem=csr_pem,
            node_public_key=public_key,
        )

    def approve_enrollment(self, enrollment_id: str, pairing_code: str) -> dict[str, object]:
        if self.enrollment_window.has_session(enrollment_id):
            approved = self.enrollment_window.approve(enrollment_id, pairing_code)
            self.enrollments.adopt_approved(
                enrollment_id=enrollment_id,
                node_id=str(approved["node_id"]),
                node_hint=str(approved["display_name"]),
                endpoint=str(approved["endpoint"]),
            )
            return {"enrollment": approved, "node": self.nodes_for_id(str(approved["node_id"]))}
        return self.enrollments.approve(enrollment_id, pairing_code)

    def nodes_for_id(self, node_id: str) -> dict[str, object]:
        return next(
            (dict(node) for node in self.enrollments.list_nodes() if node.get("node_id") == node_id),
            {},
        )

    def bootstrap_status(self, enrollment_id: str) -> dict[str, object]:
        status = self.enrollment_window.status(enrollment_id)
        if status["state"] in {"ENROLLED", "CERTIFICATE_ISSUED"} and enrollment_id not in self._bootstrap_payloads:
            session = self.enrollment_window.session(enrollment_id)
            parsed = urlparse(str(session["endpoint"]))
            addresses = [parsed.hostname] if parsed.hostname else []
            if self._certificate_authority is None:
                self._certificate_authority = NodeCertificateAuthority(self.root / "pki")
            issued = self._certificate_authority.issue_node_certificate(
                node_id=str(session["node_id"]),
                csr_pem=str(session["csr_pem"]),
                addresses=addresses,
            )
            payload = {
                "node_id": str(session["node_id"]),
                "controller_id": self.controller_id,
                **issued,
            }
            self._bootstrap_fingerprints[enrollment_id] = str(issued["fingerprint"])
            self._bootstrap_payloads[enrollment_id] = self.enrollment_window.encrypt_for(
                enrollment_id, payload
            )
            self.enrollment_window.mark_certificate_issued(enrollment_id)
            status = self.enrollment_window.status(enrollment_id)
        if enrollment_id in self._bootstrap_payloads:
            return {**status, "certificate_envelope": self._bootstrap_payloads[enrollment_id]}
        return status

    def activate_enrollment(
        self, enrollment_id: str, certificate_fingerprint: str
    ) -> dict[str, object]:
        return self.enrollments.activate(
            enrollment_id, certificate_fingerprint=certificate_fingerprint
        )

    def bootstrap_activate(self, enrollment_id: str) -> dict[str, object]:
        """Verify the freshly enrolled node over mTLS before making it routable."""

        import http.client
        import json as _json
        import ssl
        from urllib.parse import urlparse as _urlparse

        status = self.bootstrap_status(enrollment_id)
        if status.get("state") != "CERTIFICATE_ISSUED":
            if status.get("state") == "ACTIVE":
                return status
            raise PermissionError("certificate issuance must complete before activation")
        session = self.enrollment_window.session(enrollment_id)
        parsed = _urlparse(str(session["endpoint"]))
        if parsed.scheme != "https" or not parsed.hostname or not parsed.port:
            raise ValueError("enrolled node endpoint must be an HTTPS host:port URL")
        if self._certificate_authority is None:
            self._certificate_authority = NodeCertificateAuthority(self.root / "pki")
        material = self.bootstrap_tls_material(addresses=[parsed.hostname])
        context = ssl.create_default_context(cafile=material["ca_certificate"])
        context.check_hostname = False
        context.load_cert_chain(material["certificate"], material["private_key"])
        connection = http.client.HTTPSConnection(parsed.hostname, parsed.port, context=context, timeout=5.0)
        try:
            connection.connect()
            peer_certificate = connection.sock.getpeercert(binary_form=True) if connection.sock is not None else None
            if not peer_certificate:
                raise PermissionError("node did not present a certificate")
            from cryptography import x509

            node_certificate = x509.load_der_x509_certificate(peer_certificate)
            san = node_certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            node_uris = {str(value) for value in san.get_values_for_type(x509.UniformResourceIdentifier)}
            if f"rift-node:{session['node_id']}" not in node_uris:
                raise PermissionError("node certificate URI identity does not match the enrolled node")
            connection.request("GET", "/v1/health", headers={"Accept": "application/json"})
            response = connection.getresponse()
            if response.status != 200:
                raise RuntimeError(f"node health returned HTTP {response.status}")
            health = _json.loads(response.read(256 * 1024).decode("utf-8"))
        except Exception as exc:
            raise RuntimeError(f"node mTLS health verification failed: {exc}") from exc
        finally:
            connection.close()
        if not isinstance(health, dict) or str(health.get("node_id")) != str(session["node_id"]):
            raise PermissionError("node health identity does not match the enrolled node")
        certificate_fingerprint = str(self._bootstrap_fingerprints.get(enrollment_id) or "")
        if not certificate_fingerprint:
            raise RuntimeError("issued node certificate fingerprint is missing")
        activated = self.enrollments.activate(enrollment_id, certificate_fingerprint=certificate_fingerprint)
        activation = self.enrollment_window.encrypt_for(
            enrollment_id,
            {
                "node_id": str(session["node_id"]),
                "controller_id": self.controller_id,
                "node_token": activated["node_token"],
                "state": "ACTIVE",
            },
        )
        self.enrollment_window.mark_active(enrollment_id)
        return {"api_version": "2", **activated, "state": "ACTIVE", "activation_envelope": activation}

    def issue_node_certificate(self, enrollment_id: str, csr_pem: str) -> dict[str, object]:
        record = self.enrollments._record(enrollment_id)
        if record.get("state") != TrustState.ENROLLED.value:
            raise PermissionError("operator pairing approval is required before certificate issuance")
        if self._certificate_authority is None:
            self._certificate_authority = NodeCertificateAuthority(self.root / "pki")
        issued = self._certificate_authority.issue_node_certificate(
            node_id=str(record["node_id"]), csr_pem=csr_pem
        )
        activated = self.enrollments.activate(
            enrollment_id, certificate_fingerprint=issued["fingerprint"]
        )
        return {"api_version": "2", **issued, **activated}

    def bootstrap_tls_material(self, *, addresses: list[str] | None = None) -> dict[str, str]:
        """Create the controller bootstrap listener identity once per controller."""

        if self._certificate_authority is None:
            self._certificate_authority = NodeCertificateAuthority(self.root / "pki")
        pki_root = self.root / "pki"
        key_path = pki_root / "controller-bootstrap.key.pem"
        cert_path = pki_root / "controller-bootstrap.cert.pem"
        if key_path.is_file() and cert_path.is_file():
            return {
                "private_key": str(key_path),
                "certificate": str(cert_path),
                "ca_certificate": str(self._certificate_authority.cert_path),
                "fingerprint": self._certificate_fingerprint(cert_path),
            }
        if key_path.exists() or cert_path.exists():
            raise RuntimeError("controller bootstrap identity is incomplete")
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID

        key = ec.generate_private_key(ec.SECP256R1())
        csr = (
            x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, self.controller_id)]))
            .sign(key, hashes.SHA256())
        )
        issued = self._certificate_authority.issue_controller_certificate(
            controller_id=self.controller_id,
            csr_pem=csr.public_bytes(serialization.Encoding.PEM).decode("ascii"),
            addresses=addresses,
        )
        pki_root.mkdir(parents=True, exist_ok=True)
        key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        cert_path.write_text(issued["certificate_pem"], encoding="ascii")
        if hasattr(key_path, "chmod"):
            try:
                key_path.chmod(0o600)
                cert_path.chmod(0o644)
            except OSError:
                pass
        return {
            "private_key": str(key_path),
            "certificate": str(cert_path),
            "ca_certificate": str(self._certificate_authority.cert_path),
            "fingerprint": issued["fingerprint"],
        }

    @staticmethod
    def _certificate_fingerprint(path: Path) -> str:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes

        cert = x509.load_pem_x509_certificate(path.read_bytes())
        return "sha256:" + cert.fingerprint(hashes.SHA256()).hex()

    def nodes(self) -> dict[str, object]:
        nodes = self.enrollments.list_nodes()
        return {"api_version": "2", "count": len(nodes), "nodes": nodes}

    def update_capability(self, node_id: str, snapshot: dict[str, object]) -> dict[str, object]:
        return {"api_version": "2", "node": self.enrollments.update_capability(node_id, snapshot)}

    def record_telemetry(self, node_id: str, snapshot: dict[str, object], token: str | None = None) -> dict[str, object]:
        return {"api_version": "2", "telemetry": self.enrollments.record_telemetry(node_id, snapshot, token)}

    def record_link(self, payload: dict[str, object]) -> dict[str, object]:
        measurement = LinkMeasurement(
            source_node_id=str(payload.get("source_node_id") or ""),
            target_node_id=str(payload.get("target_node_id") or ""),
            rtt_p50_ms=float(payload.get("rtt_p50_ms") or 0),
            rtt_p95_ms=float(payload.get("rtt_p95_ms") or 0),
            jitter_ms=float(payload.get("jitter_ms") or 0),
            loss_ratio=float(payload.get("loss_ratio") or 0),
            upload_mbps=float(payload.get("upload_mbps") or 0),
            download_mbps=float(payload.get("download_mbps") or 0),
            observed_at=float(payload.get("observed_at") or self.clock()),
            evidence=str(payload.get("evidence") or "LIVE_MEASUREMENT"),
        )
        active = {
            str(node["node_id"])
            for node in self.enrollments.list_nodes()
            if node.get("trust_state") == TrustState.ACTIVE.value
        }
        if measurement.source_node_id not in active or measurement.target_node_id not in active:
            raise PermissionError("link reports require two active mTLS nodes")
        if measurement.source_node_id == measurement.target_node_id:
            raise ValueError("link endpoints must be different nodes")
        if measurement.rtt_p95_ms < measurement.rtt_p50_ms or not 0 <= measurement.loss_ratio <= 1:
            raise ValueError("link measurement values are invalid")
        key = (measurement.source_node_id, measurement.target_node_id)
        previous = self._links.get(key)
        if previous is None or measurement.observed_at >= previous.observed_at:
            self._links[key] = measurement
            self._save_links()
        return {"api_version": "2", "link": asdict(self._links[key])}

    @staticmethod
    def _offer(value: dict[str, object]) -> RuntimeOffer:
        return RuntimeOffer(
            offer_id=str(value["offer_id"]),
            task=str(value["task"]),
            model_id=str(value["model_id"]),
            backend=str(value["backend"]),
            context_tokens=int(value["context_tokens"]),
            quality_score=float(value["quality_score"]),
            first_token_ms=float(value["first_token_ms"]),
            decode_tokens_per_second=float(value["decode_tokens_per_second"]),
            local_only=bool(value.get("local_only", False)),
        )

    def _graph(self) -> MeshGraph:
        nodes = {}
        for value in self.enrollments.list_nodes():
            node_id = str(value["node_id"])
            nodes[node_id] = TrustedNode(
                node_id=node_id,
                hostname=str(value.get("hostname") or node_id),
                trust_state=TrustState(str(value["trust_state"])),
                healthy=bool(value.get("healthy", True)),
                queue_depth=int(value.get("queue_depth") or 0),
                labels={str(k): str(v) for k, v in dict(value.get("labels") or {}).items()},
                offers=[self._offer(item) for item in value.get("runtime_offers", [])],
            )
        evidence = {item.evidence for item in self._links.values()}
        return MeshGraph(
            nodes=nodes,
            links=dict(self._links),
            evidence=next(iter(evidence)) if len(evidence) == 1 else "MIXED",
        )

    def resolve_route(self, payload: dict[str, object]) -> dict[str, object]:
        policy_hash = str(payload.get("policy_hash") or "")
        service_id = str(payload.get("service_id") or "")
        if not policy_hash or not service_id:
            raise ValueError("service_id and policy_hash are required")
        intent = InferenceIntent(
            source_node_id=str(payload.get("source_node_id") or ""),
            task=str(payload.get("task") or "chat"),
            minimum_context_tokens=int(payload.get("minimum_context_tokens") or 1),
            privacy=PrivacyPolicy(str(payload.get("privacy") or PrivacyPolicy.MESH_ALLOWED.value)),
            minimum_quality_score=float(payload.get("minimum_quality_score") or 0),
        )
        decision = self.route_planner.resolve(graph=self._graph(), intent=intent)
        selected_node = next(
            (node for node in self.enrollments.list_nodes() if node.get("node_id") == decision.selected.node_id),
            {},
        )
        lease = self.route_leases.issue(
            source_node_id=intent.source_node_id,
            service_id=service_id,
            primary_node_id=decision.selected.node_id,
            fallback_node_ids=[item.node_id for item in decision.fallbacks],
            ttl_seconds=int(payload.get("lease_ttl_seconds") or 30),
            policy_hash=policy_hash,
            controller_id="rift-controller",
            inference_endpoint=str(selected_node.get("endpoint") or "https://127.0.0.1:8443"),
            bearer_token=secrets.token_urlsafe(32),
        )
        return {"api_version": "2", "decision": asdict(decision), "lease": lease}

    def topology(self) -> dict[str, object]:
        nodes = self.enrollments.list_nodes()
        return {
            "api_version": "2",
            "evidence": "DISCOVERY_AND_ENROLLMENT_STATE",
            "nodes": nodes,
            "links": [asdict(item) for item in self._links.values()],
            "measurement_mode": "reported",
        }


__all__ = ["MeshController"]
