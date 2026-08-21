"""Stateful controller facade consumed by the RIFT API and operator UI."""

from __future__ import annotations

from pathlib import Path
from dataclasses import asdict
import json
import secrets
import time
from typing import Callable
from typing import Iterable

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
        self.clock = clock
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
        self._links_path = self.root / "links.json"
        self._links = self._load_links()

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

    def approve_enrollment(self, enrollment_id: str, pairing_code: str) -> dict[str, object]:
        return self.enrollments.approve(enrollment_id, pairing_code)

    def activate_enrollment(
        self, enrollment_id: str, certificate_fingerprint: str
    ) -> dict[str, object]:
        return self.enrollments.activate(
            enrollment_id, certificate_fingerprint=certificate_fingerprint
        )

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
