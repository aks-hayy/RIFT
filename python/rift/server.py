"""Minimal local RIFT HTTP API server."""

from __future__ import annotations

import json
import hashlib
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Optional
from urllib.parse import urlparse

from .cluster import RiftClusterController
from .mesh.controller import MeshController
from .orchestrator import ApplyPermissions, RiftOrchestrator
from .operations import OperationStore
from .runtime_paths import RiftPaths
from .rift import RiftEngine


JsonDict = dict[str, Any]
EngineFactory = Callable[[], RiftEngine]
OrchestratorFactory = Callable[[], RiftOrchestrator]
ClusterFactory = Callable[[], RiftClusterController]
MeshControllerFactory = Callable[[], MeshController]


@dataclass
class RiftServerRuntime:
    model_path: Optional[str] = None
    plan_path: Optional[str] = None
    engine_factory: EngineFactory = RiftEngine
    orchestrator_factory: OrchestratorFactory = RiftOrchestrator
    cluster_factory: ClusterFactory = RiftClusterController
    mesh_controller_factory: MeshControllerFactory = MeshController
    last_run: JsonDict | None = None
    request_count: int = 0
    busy: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)
    _mesh_controller: MeshController | None = field(default=None, init=False, repr=False)
    operation_store: OperationStore | None = field(default=None, repr=False)
    bootstrap_host: str = "0.0.0.0"
    bootstrap_port: int = 11748
    _bootstrap_server: Any = field(default=None, init=False, repr=False)
    _bootstrap_thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _bootstrap_advertiser: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.operation_store is None:
            self.operation_store = OperationStore(RiftPaths.from_environment().operations)

    @staticmethod
    def request_id(supplied: str | None) -> str:
        value = str(supplied or "").strip()
        if value and len(value) <= 200:
            return value
        return f"rift-{uuid.uuid4().hex}"

    @staticmethod
    def identity(authorization: str | None, client_host: str) -> str:
        source = str(authorization or "").strip() or str(client_host or "unknown")
        return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]

    def mesh_controller(self) -> MeshController:
        if self._mesh_controller is None:
            if self.mesh_controller_factory is MeshController:
                self._mesh_controller = MeshController(root=RiftPaths.from_environment().home / "mesh")
            else:
                self._mesh_controller = self.mesh_controller_factory()
        return self._mesh_controller

    def start_bootstrap_listener(self) -> JsonDict:
        if self._bootstrap_server is not None:
            return {"started": True, "port": self._bootstrap_server.server_port}
        from .mesh.bootstrap_server import create_bootstrap_server
        from .mesh.discovery_transports import ControllerAdvertiser

        advertised_host = os.environ.get("RIFT_CONTROLLER_ADVERTISE_HOST", "127.0.0.1")
        server = create_bootstrap_server(
            controller=self.mesh_controller(),
            host=self.bootstrap_host,
            port=self.bootstrap_port,
            advertised_host=advertised_host,
        )
        thread = threading.Thread(target=server.serve_forever, name="rift-controller-bootstrap", daemon=True)
        thread.start()
        self._bootstrap_server = server
        self._bootstrap_thread = thread
        try:
            material = self.mesh_controller().bootstrap_tls_material(addresses=[advertised_host])
            advertiser = ControllerAdvertiser(
                controller_id=self.mesh_controller().controller_id,
                host=advertised_host,
                port=server.server_port,
                fingerprint=str(material["fingerprint"]),
            )
            advertiser.start()
            self._bootstrap_advertiser = advertiser
        except Exception:
            self.stop_bootstrap_listener()
            raise
        return {"started": True, "host": advertised_host, "port": server.server_port, "controller_id": self.mesh_controller().controller_id}

    def stop_bootstrap_listener(self) -> JsonDict:
        if self._bootstrap_advertiser is not None:
            self._bootstrap_advertiser.stop()
            self._bootstrap_advertiser = None
        if self._bootstrap_server is not None:
            self._bootstrap_server.shutdown()
            self._bootstrap_server.server_close()
            self._bootstrap_server = None
        if self._bootstrap_thread is not None:
            self._bootstrap_thread.join(timeout=5)
            self._bootstrap_thread = None
        return {"stopped": True}

    def shutdown(self) -> None:
        self.stop_bootstrap_listener()

    def model_id(self) -> str:
        source = self.plan_path or self.model_path or "unconfigured"
        return str(source).replace("\\", "/").rstrip("/").split("/")[-1]

    def status(self) -> JsonDict:
        plan = self.current_plan(summary_only=True)
        return {
            "ok": True,
            "service": "rift",
            "model_path": self.model_path,
            "plan_path": self.plan_path,
            "selected_backend": (plan.get("backend_decision") or {}).get("selected_backend"),
            "backend_label": (plan.get("backend_decision") or {}).get("backend_label"),
            "runnable_now": (plan.get("serving_plan") or {}).get("runnable_now"),
            "request_count": self.request_count,
            "busy": self.busy,
            "last_status": None if self.last_run is None else self.last_run.get("status"),
            "last_usability_verdict": None
            if self.last_run is None
            else self.last_run.get("usability_verdict"),
        }

    def run_prompt(self, prompt: str, payload: JsonDict) -> JsonDict:
        if not prompt:
            raise ValueError("prompt is required")
        if not self.lock.acquire(blocking=False):
            raise RuntimeError("RIFT runtime is busy")
        self.busy = True
        try:
            engine = self.engine_factory()
            result = engine.run(
                prompt=prompt,
                model_path=self.model_path,
                plan_path=self.plan_path,
                max_tokens=int(payload.get("max_tokens", 1)),
                temperature=float(payload.get("temperature", 0.0)),
                top_p=float(payload.get("top_p", 1.0)),
                top_k=int(payload.get("top_k", 32)),
                repetition_penalty=float(payload.get("repetition_penalty", 1.0)),
            )
            self.request_count += 1
            self.last_run = result
            return result
        finally:
            self.busy = False
            self.lock.release()

    def report(self) -> JsonDict:
        if self.last_run is None:
            return {"available": False, "reason": "no run has completed yet"}
        return {
            "available": True,
            "report_path": self.last_run.get("report_path"),
            "usability_verdict": self.last_run.get("usability_verdict"),
            "recommendations": self.last_run.get("recommendations", []),
            "metrics": {
                "tokens_per_second": self.last_run.get("tokens_per_second"),
                "generated_tokens": self.last_run.get("generated_tokens"),
                "total_seconds": self.last_run.get("total_seconds"),
                "backend_metrics": self.last_run.get("backend_metrics", {}),
            },
        }

    def reports(self) -> JsonDict:
        return self.engine_factory().list_reports()

    def compatibility(self) -> JsonDict:
        model = self.model_path
        if model is None and self.plan_path is not None:
            try:
                model = str(self.engine_factory().load_plan(self.plan_path).get("model_path"))
            except Exception:
                model = None
        if not model:
            return {"available": False, "reason": "server has no configured model path"}
        return self.engine_factory().compatibility_advice(model)

    def current_plan(self, *, summary_only: bool = False) -> JsonDict:
        try:
            if self.plan_path is not None:
                plan = self.engine_factory().load_plan(self.plan_path)
            elif self.model_path is not None and not summary_only:
                plan = self.engine_factory().plan_model(
                    self.model_path,
                    benchmark_read_bytes=4 * 1024 * 1024,
                    write=False,
                )
            else:
                plan = {}
        except Exception as exc:
            return {"available": False, "reason": str(exc)}
        if not plan:
            return {"available": False, "reason": "server has no deployment plan yet"}
        if summary_only:
            return plan
        return {
            "available": True,
            "model_path": plan.get("model_path"),
            "selected_backend": plan.get("selected_backend"),
            "backend_decision": plan.get("backend_decision", {}),
            "serving_plan": plan.get("serving_plan", {}),
            "kv_plan": plan.get("kv_plan", {}),
        }

    def control_get(self, path: str) -> JsonDict:
        if path == "/api/rift/v2/mesh/enrollment-window":
            return self.mesh_controller().enrollment_window_status()
        if path == "/api/rift/v2/mesh/enrollments":
            return self.mesh_controller().managed_enrollments()
        if path == "/api/rift/v2/mesh/sightings":
            return self.mesh_controller().sightings()
        if path == "/api/rift/v2/mesh/nodes":
            return self.mesh_controller().nodes()
        if path == "/api/rift/v2/mesh/topology":
            return self.mesh_controller().topology()
        orchestrator = self.orchestrator_factory()
        if path == "/api/rift/v2/adapters":
            return {
                "api_version": "2",
                "registry": orchestrator.backend_host.diagnostics(),
                "adapters": [
                    {
                        "adapter_id": adapter_id,
                        "enabled": registration.enabled,
                        "source": registration.source,
                        "manifest": (
                            registration.adapter.manifest.to_dict()
                            if getattr(registration.adapter, "manifest", None)
                            else None
                        ),
                        "diagnostics": [item.to_dict() for item in registration.diagnostics],
                    }
                    for adapter_id, registration in sorted(orchestrator.backend_host.all().items())
                ],
            }
        if path.startswith("/api/rift/v2/adapters/"):
            adapter_id = path.rsplit("/", 1)[-1]
            registration = orchestrator.backend_host.all().get(adapter_id)
            if registration is None:
                raise KeyError(path)
            detection = (
                orchestrator._provider_probe(registration.adapter, adapter_id)
                if registration.enabled
                else None
            )
            return {
                "api_version": "2",
                "adapter_id": adapter_id,
                "enabled": registration.enabled,
                "source": registration.source,
                "manifest": registration.adapter.manifest.to_dict(),
                "capabilities": (
                    registration.adapter.capabilities() if registration.enabled else None
                ),
                "detection": detection,
                "runtime_negotiation": {
                    "upstream_version": (detection or {}).get("version"),
                    "feature_probe": (detection or {}).get("runtime_feature_probe"),
                    "boundary": (
                        "Installed-version probes may narrow the static manifest. "
                        "A declared feature is not physical acceptance evidence."
                    ),
                },
                "diagnostics": [item.to_dict() for item in registration.diagnostics],
            }
        if path == "/api/rift/v2/artifact-adapters":
            host = orchestrator.engine.artifact_adapters
            return {
                "api_version": "2",
                "registry": host.diagnostics(),
                "adapters": [
                    {
                        "adapter_id": adapter_id,
                        "enabled": registration.enabled,
                        "source": registration.source,
                        "manifest": registration.adapter.manifest.to_dict(),
                    }
                    for adapter_id, registration in sorted(host.all().items())
                ],
            }
        if path == "/api/rift/v2/converter-adapters":
            host = orchestrator.converter_host
            return {
                "api_version": "2",
                "registry": host.diagnostics(),
                "adapters": [
                    {
                        "adapter_id": adapter_id,
                        "enabled": registration.enabled,
                        "source": registration.source,
                        "manifest": registration.adapter.manifest.to_dict(),
                    }
                    for adapter_id, registration in sorted(host.all().items())
                ],
            }
        if path == "/api/rift/v2/artifacts":
            artifact_root = orchestrator.rift_dir / "artifacts"
            artifacts = []
            if artifact_root.is_dir():
                for item in sorted(artifact_root.glob("*.json")):
                    try:
                        artifacts.append(json.loads(item.read_text(encoding="utf-8")))
                    except (OSError, json.JSONDecodeError):
                        continue
            return {"api_version": "2", "count": len(artifacts), "artifacts": artifacts}
        if path == "/api/rift/v2/capabilities":
            return {
                "api_version": "2",
                "backend_adapters": {
                    name: adapter.manifest.capability.to_dict()
                    for name, adapter in sorted(orchestrator.providers.items())
                },
                "artifact_adapters": {
                    name: registration.adapter.manifest.capability.to_dict()
                    for name, registration in sorted(
                        orchestrator.engine.artifact_adapters.all().items()
                    )
                    if registration.enabled
                },
                "converter_adapters": {
                    name: registration.adapter.manifest.capability.to_dict()
                    for name, registration in sorted(orchestrator.converter_host.all().items())
                    if registration.enabled
                },
            }
        if path == "/api/rift/v2/recommendation-runs":
            return orchestrator.recommendation_store.list_recommendations()
        if path.startswith("/api/rift/v2/recommendation-runs/"):
            return orchestrator.recommendation_store.load_recommendation(path.rsplit("/", 1)[-1])
        if path == "/api/rift/v2/verification-runs":
            return orchestrator.recommendation_store.list_verifications()
        if path.startswith("/api/rift/v2/verification-runs/"):
            return orchestrator.recommendation_store.load_verification(path.rsplit("/", 1)[-1])
        if path == "/api/rift/state":
            return orchestrator.read_state()
        if path == "/api/rift/discovery":
            return orchestrator.latest_discovery()
        if path == "/api/rift/generated-config":
            return orchestrator.generated_config()
        if path == "/api/rift/backends":
            return orchestrator.backend_status()
        if path == "/api/rift/hardware":
            discovery = orchestrator.discover(write=False)
            nodes = discovery.get("nodes") or []
            return (nodes[0].get("hardware") or {}) if nodes else {}
        if path == "/api/rift/services":
            return orchestrator.status().get("services", {})
        if path == "/api/rift/metrics":
            return {"status": orchestrator.status(), "reports": orchestrator.reports()}
        if path == "/api/rift/reports":
            return orchestrator.reports()
        if path == "/api/rift/incidents":
            return orchestrator.incidents()
        if path == "/api/rift/gateway":
            return orchestrator.gateway_status()
        if path == "/api/rift/observability":
            return orchestrator.observability()
        if path == "/api/rift/timeline":
            return orchestrator.observability_store.timeline(limit=500)
        if path == "/api/rift/logs":
            return orchestrator.logs(service_name="chat", tail=500)
        if path == "/api/rift/provider-gates":
            return {
                "providers": {
                    name: details.get("lifecycle_gate")
                    for name, details in orchestrator.backend_status().get("providers", {}).items()
                }
            }
        if path == "/api/rift/cluster/status":
            return self.cluster_factory().status()
        if path == "/api/rift/plan":
            if self.model_path is not None or self.plan_path is not None:
                return self.current_plan()
            latest = orchestrator.latest_plan()
            if latest.get("available") is False:
                return self.current_plan()
            return latest
        raise KeyError(path)

    def control_post(self, path: str, payload: JsonDict, *, authorization: str | None = None) -> JsonDict:
        if path == "/api/rift/v2/mesh/enrollment-window":
            result = self.mesh_controller().open_enrollment_window(
                ttl_seconds=int(payload.get("ttl_seconds") or 600)
            )
            return {**result, "bootstrap": self.start_bootstrap_listener()}
        if path == "/api/rift/v2/mesh/discover":
            providers = payload.get("providers")
            if providers is not None and not isinstance(providers, list):
                raise ValueError("providers must be an array of discovery provider names")
            return self.mesh_controller().discover(providers, options=payload)
        if path == "/api/rift/v2/mesh/enrollments":
            sighting_id = str(payload.get("sighting_id") or "")
            if not sighting_id:
                raise ValueError("sighting_id is required")
            return self.mesh_controller().begin_enrollment(
                sighting_id, ttl_seconds=int(payload.get("ttl_seconds") or 120)
            )
        if path.startswith("/api/rift/v2/mesh/enrollments/"):
            parts = path.strip("/").split("/")
            if len(parts) != 7:
                raise KeyError(path)
            enrollment_id, action = parts[-2], parts[-1]
            if action == "approve":
                pairing_code = str(payload.get("pairing_code") or "")
                if not pairing_code:
                    raise ValueError("pairing_code is required")
                return self.mesh_controller().approve_enrollment(enrollment_id, pairing_code)
            if action == "cancel":
                return self.mesh_controller().enrollment_window.cancel(enrollment_id)
            if action == "activate":
                fingerprint = str(payload.get("certificate_fingerprint") or "")
                if not fingerprint:
                    raise ValueError("certificate_fingerprint is required")
                return self.mesh_controller().activate_enrollment(enrollment_id, fingerprint)
            if action == "certificate":
                csr_pem = str(payload.get("csr_pem") or "")
                if not csr_pem:
                    raise ValueError("csr_pem is required")
                return self.mesh_controller().issue_node_certificate(enrollment_id, csr_pem)
            raise KeyError(path)
        if path.startswith("/api/rift/v2/mesh/nodes/") and path.endswith("/capabilities"):
            parts = path.strip("/").split("/")
            if len(parts) != 7:
                raise KeyError(path)
            return self.mesh_controller().update_capability(parts[-2], payload)
        if path.startswith("/api/rift/v2/mesh/nodes/") and path.endswith("/telemetry"):
            parts = path.strip("/").split("/")
            if len(parts) != 7:
                raise KeyError(path)
            token = authorization.removeprefix("Bearer ").strip() if authorization else None
            return self.mesh_controller().record_telemetry(parts[-2], payload, token)
        if path == "/api/rift/v2/mesh/links":
            return self.mesh_controller().record_link(payload)
        if path == "/api/rift/v2/mesh/routes/resolve":
            return self.mesh_controller().resolve_route(payload)
        orchestrator = self.orchestrator_factory()
        if path == "/api/rift/v2/recommendations":
            return orchestrator.engine.recommend_models(
                task=str(payload.get("task") or "chat"),
                top=int(payload.get("top") or 10),
                candidate_limit=int(payload.get("candidate_limit") or 250),
                max_download_gb=(
                    float(payload["max_download_gb"])
                    if payload.get("max_download_gb") is not None
                    else None
                ),
                formats=payload.get("formats"),
                include_gated=bool(payload.get("include_gated", False)),
                refresh=bool(payload.get("refresh", False)),
                download_root=payload.get("download_root"),
                disk_reserve_gb=float(payload.get("disk_reserve_gb") or 2.0),
                endpoint=str(payload.get("endpoint") or "https://huggingface.co"),
                token=payload.get("token"),
                run_store_root=str(orchestrator.rift_dir),
            )
        if path == "/api/rift/v2/compatibility":
            artifact = payload.get("artifact")
            if not isinstance(artifact, dict):
                raise ValueError("artifact must be an object")
            hardware = payload.get("hardware")
            if not isinstance(hardware, dict):
                discovery = orchestrator.discover(write=False)
                nodes = discovery.get("nodes") or []
                hardware = (nodes[0].get("hardware") or {}) if nodes else {}
            results = orchestrator.backend_host.rank(
                artifact=artifact,
                hardware=hardware,
                workload=str(payload.get("task") or "chat"),
                search_root=orchestrator.rift_dir / "backends",
            )
            return {
                "api_version": "2",
                "artifact": artifact,
                "results": [item.to_dict() for item in results],
            }
        if path == "/api/rift/v2/artifacts/inspect":
            model_path = str(payload.get("model_path") or "")
            if not model_path:
                raise ValueError("model_path is required")
            return orchestrator.artifact_manifest(
                model_path=model_path,
                hash_mode=str(payload.get("hash_mode") or "model"),
            )
        if path == "/api/rift/v2/plans":
            run_id = str(payload.get("recommendation_run_id") or "")
            if not run_id:
                raise ValueError("recommendation_run_id is required")
            return orchestrator.plan_recommendation_run(
                run_id=run_id,
                selector=str(payload.get("selector") or "best_estimated"),
                output=payload.get("output"),
            )
        if path == "/api/rift/v2/verification-runs":
            run_id = str(payload.get("recommendation_run_id") or "")
            if not run_id:
                raise ValueError("recommendation_run_id is required")
            return orchestrator.verify_recommendation_run(
                run_id=run_id,
                permissions=ApplyPermissions(
                    allow_download=bool(payload.get("allow_download", False)),
                    allow_install=bool(payload.get("allow_install", False)),
                    allow_launch=bool(payload.get("allow_launch", False)),
                ),
                finalists=int(payload.get("finalists") or 3),
                prompt=str(
                    payload.get("prompt")
                    or "Reply briefly: what is one benefit of local language models?"
                ),
                max_tokens=int(payload.get("max_tokens") or 32),
                startup_timeout_seconds=float(payload.get("startup_timeout_seconds") or 180.0),
                endpoint=payload.get("endpoint"),
                token=payload.get("token"),
            )
        if path == "/api/rift/recommend":
            return orchestrator.engine.recommend_models(
                task=str(payload.get("task") or "chat"),
                top=int(payload.get("top") or 10),
                candidate_limit=int(payload.get("candidate_limit") or 200),
                max_download_gb=(
                    float(payload["max_download_gb"])
                    if payload.get("max_download_gb") is not None
                    else None
                ),
                formats=payload.get("formats"),
                include_gated=bool(payload.get("include_gated", False)),
                refresh=bool(payload.get("refresh", False)),
                download_root=payload.get("download_root"),
                disk_reserve_gb=float(payload.get("disk_reserve_gb") or 2.0),
                run_store_root=str(orchestrator.rift_dir),
            )
        if path == "/api/rift/calibrate":
            return orchestrator.calibrate_hardware(
                sample_bytes=int(payload.get("sample_bytes") or 32 * 1024**2),
                force=bool(payload.get("force", False)),
            )
        if path == "/api/rift/artifact-manifest":
            return orchestrator.artifact_manifest(
                model_path=str(payload.get("model_path") or ""),
                hash_mode=str(payload.get("hash_mode") or "model"),
            )
        if path == "/api/rift/discover":
            return orchestrator.discover(
                local=bool(payload.get("local", True)),
                cluster_config=payload.get("cluster"),
                models_dir=payload.get("models_dir"),
                allow_remote=bool(payload.get("allow_remote", False)),
            )
        if path == "/api/rift/generate":
            return orchestrator.generate_config(
                task=str(payload.get("task") or "chat"),
                source=str(payload.get("source") or "huggingface"),
                models_dir=payload.get("models_dir"),
                endpoint=str(payload.get("endpoint") or "https://huggingface.co"),
                output=str(payload.get("output") or ".rift/generated/rift.generated.yaml"),
                top=int(payload.get("top") or 10),
                candidate_limit=int(payload.get("candidate_limit") or 300),
                max_download_gb=float(payload.get("max_download_gb") or 12.0),
            )
        if path == "/api/rift/plan":
            return orchestrator.plan(config_path=str(payload.get("config") or "rift.yaml"))
        if path == "/api/rift/apply":
            return orchestrator.apply(
                config_path=str(payload.get("config") or "rift.yaml"),
                permissions=ApplyPermissions(
                    allow_download=bool(payload.get("allow_download", False)),
                    allow_install=bool(payload.get("allow_install", False)),
                    allow_launch=bool(payload.get("allow_launch", False)),
                    allow_remote=bool(payload.get("allow_remote", False)),
                    optimize=bool(payload.get("optimize", False)),
                    write_back=bool(payload.get("write_back", False)),
                ),
            )
        if path == "/api/rift/benchmark":
            return orchestrator.benchmark(
                service_name=str(payload.get("service") or "chat"),
                prompt=str(payload.get("prompt") or "Explain what RIFT does in one sentence."),
                max_tokens=int(payload.get("max_tokens") or 32),
            )
        if path == "/api/rift/benchmark-suite":
            return orchestrator.benchmark_suite(
                service_name=str(payload.get("service") or "chat"),
                warmups=int(payload.get("warmups") or 1),
                repetitions=int(payload.get("repetitions") or 3),
            )
        if path == "/api/rift/tune":
            return orchestrator.tune_service(
                service_name=str(payload.get("service") or "chat"),
                config_path=str(payload.get("config") or "rift.yaml"),
                live=bool(payload.get("live", False)),
                allow_restart=bool(payload.get("allow_restart", False)),
                candidate_limit=int(payload.get("candidate_limit") or 4),
                warmup_runs=int(payload.get("warmup_runs") or 1),
                repeats=int(payload.get("repeats") or 2),
                startup_timeout_seconds=float(
                    payload.get("startup_timeout_seconds") or 180.0
                ),
                prompt=str(
                    payload.get("prompt")
                    or "Reply briefly: what is one benefit of local inference?"
                ),
                max_tokens=int(payload.get("max_tokens") or 32),
            )
        if path == "/api/rift/monitor":
            return orchestrator.monitor(
                service_name=payload.get("service"),
                allow_recovery=bool(payload.get("allow_recovery", False)),
                interval_seconds=float(payload.get("interval_seconds", 0.0)),
                iterations=int(payload.get("iterations", 1)),
            )
        if path == "/api/rift/recover":
            return orchestrator.recover(
                service_name=str(payload.get("service") or "chat"),
                allow_launch=bool(payload.get("allow_launch", False)),
                force=bool(payload.get("force", False)),
            )
        if path == "/api/rift/destroy":
            return orchestrator.destroy(service_name=payload.get("service"))
        if path == "/api/rift/gateway/keys/create":
            return orchestrator.gateway_key_create(
                label=str(payload.get("label") or "dashboard key"),
                quota=payload.get("quota") if isinstance(payload.get("quota"), dict) else None,
            )
        if path == "/api/rift/gateway/keys/revoke":
            return orchestrator.gateway_key_revoke(key_id=str(payload.get("key_id") or ""))
        if path == "/api/rift/gateway/keys/rotate":
            return orchestrator.gateway_key_rotate(key_id=str(payload.get("key_id") or ""))
        if path == "/api/rift/observability/prune":
            return orchestrator.prune_observability()
        if path == "/api/rift/migrate":
            return orchestrator.migrate(
                config_path=str(payload.get("config") or "rift.yaml"),
                write=bool(payload.get("write", False)),
            )
        if path == "/api/rift/diagnostics":
            return orchestrator.diagnostics(output=payload.get("output"))
        if path == "/api/rift/export":
            return orchestrator.export_deployment(output=payload.get("output"))
        cluster = self.cluster_factory()
        cluster_config = str(payload.get("cluster") or "cluster.yaml")
        if path == "/api/rift/cluster/discover":
            return cluster.discover(
                cluster_config=cluster_config,
                allow_remote=bool(payload.get("allow_remote", False)),
            )
        if path == "/api/rift/cluster/check":
            return cluster.check(cluster_config=cluster_config)
        if path == "/api/rift/cluster/plan":
            return cluster.plan(cluster_config=cluster_config)
        if path == "/api/rift/cluster/apply":
            return cluster.apply(
                cluster_config=cluster_config,
                allow_deploy=bool(payload.get("allow_launch", False)),
                allow_remote=bool(payload.get("allow_remote", False)),
                allow_download=bool(payload.get("allow_download", False)),
                allow_install=bool(payload.get("allow_install", False)),
            )
        if path == "/api/rift/cluster/monitor":
            return cluster.monitor(allow_recovery=bool(payload.get("allow_recovery", False)))
        if path == "/api/rift/cluster/benchmark":
            return cluster.benchmark(service_name=payload.get("service"))
        if path == "/api/rift/cluster/tune":
            return cluster.tune(service_name=payload.get("service"))
        if path == "/api/rift/cluster/fault":
            return cluster.inject_failure(
                node_name=payload.get("node"),
                instance_id=payload.get("instance"),
                kind=str(payload.get("kind") or "process_crash"),
            )
        if path == "/api/rift/cluster/recover":
            return cluster.monitor(allow_recovery=bool(payload.get("allow_recovery", False)))
        if path == "/api/rift/cluster/destroy":
            return cluster.destroy()
        if path == "/api/rift/cluster/rollout/plan":
            return cluster.rollout_plan(
                service_name=str(payload.get("service") or "chat"),
                desired=payload.get("desired") if isinstance(payload.get("desired"), dict) else {},
                strategy=str(payload.get("strategy") or "canary"),
                max_unavailable=int(payload.get("max_unavailable") or 0),
            )
        if path == "/api/rift/cluster/rollout/gate":
            return cluster.rollout_gate(
                readiness=payload.get("readiness") if isinstance(payload.get("readiness"), dict) else {},
                baseline=payload.get("baseline") if isinstance(payload.get("baseline"), dict) else {},
                candidate=payload.get("candidate") if isinstance(payload.get("candidate"), dict) else {},
            )
        raise KeyError(path)

    def control_delete(self, path: str) -> JsonDict:
        if path == "/api/rift/v2/mesh/enrollment-window":
            result = self.mesh_controller().close_enrollment_window()
            return {**result, "bootstrap": self.stop_bootstrap_listener()}
        raise KeyError(path)


class RiftRequestHandler(BaseHTTPRequestHandler):
    runtime: RiftServerRuntime

    server_version = "RIFTServer/0.1"

    def do_OPTIONS(self) -> None:  # noqa: N802
        if not self._cors_allowed(self.headers.get("Origin")):
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "CORS origin is not allowed"})
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Request-ID")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json(HTTPStatus.OK, self.runtime.status())
            return
        if parsed.path == "/v1/models":
            self._send_json(
                HTTPStatus.OK,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": self.runtime.model_id(),
                            "object": "model",
                            "owned_by": "local",
                        }
                    ],
                },
            )
            return
        if parsed.path in ("/rift/status", "/api/rift/status"):
            self._send_json(HTTPStatus.OK, self.runtime.status())
            return
        if parsed.path == "/rift/plan":
            self._send_json(HTTPStatus.OK, self.runtime.current_plan())
            return
        if parsed.path.startswith("/api/rift/"):
            if parsed.path == "/api/rift/metrics/prometheus":
                body = self.runtime.orchestrator_factory().prometheus_metrics().encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(body)
                return
            try:
                self._send_json(HTTPStatus.OK, self.runtime.control_get(parsed.path))
            except KeyError:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "unknown endpoint"})
            return
        if parsed.path == "/rift/metrics":
            self._send_json(HTTPStatus.OK, self.runtime.report())
            return
        if parsed.path == "/rift/report":
            self._send_json(HTTPStatus.OK, self.runtime.report())
            return
        if parsed.path == "/rift/reports":
            self._send_json(HTTPStatus.OK, self.runtime.reports())
            return
        if parsed.path in ("/rift/compatibility", "/api/rift/compatibility"):
            self._send_json(HTTPStatus.OK, self.runtime.compatibility())
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "unknown endpoint"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        payload = self._read_json_body()
        request_id: str | None = None
        try:
            if parsed.path.startswith("/api/rift/"):
                request_id = self.runtime.request_id(
                    self.headers.get("X-Request-ID") or payload.get("request_id")
                )
                assert self.runtime.operation_store is not None
                prior = self.runtime.operation_store.load(request_id)
                if prior is not None:
                    if prior.get("status") == "RUNNING":
                        self._send_json(
                            HTTPStatus.CONFLICT,
                            {
                                "error": "operation with this request_id is already running",
                                "request_id": request_id,
                                "operation_id": prior.get("operation_id"),
                            },
                        )
                        return
                    self._send_json(
                        HTTPStatus.OK if prior.get("status") == "SUCCEEDED" else HTTPStatus.INTERNAL_SERVER_ERROR,
                        {
                            **(prior.get("result") or {}),
                            "request_id": request_id,
                            "operation_id": prior.get("operation_id"),
                            "replayed": True,
                        },
                    )
                    return
                operation = self.runtime.operation_store.begin(
                    request_id,
                    action=parsed.path,
                    actor=self.runtime.identity(
                        self.headers.get("Authorization"),
                        self.client_address[0],
                    ),
                )
                result = self.runtime.control_post(
                    parsed.path,
                    payload,
                    authorization=self.headers.get("Authorization"),
                )
                result = {
                    **result,
                    "request_id": request_id,
                    "operation_id": operation["operation_id"],
                }
                self.runtime.operation_store.complete(request_id, result=result)
                self._send_json(HTTPStatus.OK, result)
                return
            if parsed.path == "/v1/completions":
                prompt = str(payload.get("prompt", ""))
                result = self.runtime.run_prompt(prompt, payload)
                if bool(payload.get("stream", False)):
                    self._send_completion_stream(result)
                    return
                self._send_json(HTTPStatus.OK, self._completion_response(result))
                return
            if parsed.path == "/v1/chat/completions":
                prompt = self._chat_prompt(payload)
                result = self.runtime.run_prompt(prompt, payload)
                if bool(payload.get("stream", False)):
                    self._send_chat_stream(result)
                    return
                self._send_json(HTTPStatus.OK, self._chat_response(result))
                return
        except PermissionError as exc:
            if request_id and parsed.path.startswith("/api/rift/") and self.runtime.operation_store is not None:
                self.runtime.operation_store.fail(request_id, error=str(exc))
            self._send_json(HTTPStatus.FORBIDDEN, {"error": str(exc)})
            return
        except TimeoutError as exc:
            self._send_json(HTTPStatus.GONE, {"error": str(exc)})
            return
        except (ValueError, KeyError) as exc:
            if request_id and parsed.path.startswith("/api/rift/") and self.runtime.operation_store is not None:
                self.runtime.operation_store.fail(request_id, error=str(exc))
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except RuntimeError as exc:
            if request_id and parsed.path.startswith("/api/rift/") and self.runtime.operation_store is not None:
                self.runtime.operation_store.fail(request_id, error=str(exc))
            status = HTTPStatus.TOO_MANY_REQUESTS if "busy" in str(exc).lower() else HTTPStatus.INTERNAL_SERVER_ERROR
            self._send_json(status, {"error": str(exc)})
            return
        except Exception as exc:  # pragma: no cover - HTTP boundary
            if request_id and parsed.path.startswith("/api/rift/") and self.runtime.operation_store is not None:
                self.runtime.operation_store.fail(request_id, error=str(exc))
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "unknown endpoint"})

    def do_DELETE(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/rift/"):
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "unknown endpoint"})
            return
        request_id = self.runtime.request_id(self.headers.get("X-Request-ID"))
        assert self.runtime.operation_store is not None
        try:
            prior = self.runtime.operation_store.load(request_id)
            if prior is not None:
                self._send_json(
                    HTTPStatus.OK if prior.get("status") == "SUCCEEDED" else HTTPStatus.INTERNAL_SERVER_ERROR,
                    {**(prior.get("result") or {}), "request_id": request_id, "operation_id": prior.get("operation_id"), "replayed": True},
                )
                return
            operation = self.runtime.operation_store.begin(request_id, action=parsed.path, actor=self.runtime.identity(self.headers.get("Authorization"), self.client_address[0]))
            result = {**self.runtime.control_delete(parsed.path), "request_id": request_id, "operation_id": operation["operation_id"]}
            self.runtime.operation_store.complete(request_id, result=result)
            self._send_json(HTTPStatus.OK, result)
        except KeyError:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "unknown endpoint"})
        except (PermissionError, ValueError, RuntimeError) as exc:
            self.runtime.operation_store.fail(request_id, error=str(exc))
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _completion_response(self, result: JsonDict) -> JsonDict:
        return {
            "id": "rift-completion-local",
            "object": "text_completion",
            "model": self.runtime.model_id(),
            "choices": [
                {
                    "index": 0,
                    "text": result.get("text", ""),
                    "finish_reason": "length",
                }
            ],
            "rift": result,
        }

    def _chat_response(self, result: JsonDict) -> JsonDict:
        return {
            "id": "rift-chat-local",
            "object": "chat.completion",
            "model": self.runtime.model_id(),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": result.get("text", "")},
                    "finish_reason": "length",
                }
            ],
            "rift": result,
        }

    def _send_completion_stream(self, result: JsonDict) -> None:
        payload = {
            "id": "rift-completion-local",
            "object": "text_completion.chunk",
            "created": int(time.time()),
            "model": self.runtime.model_id(),
            "choices": [{"index": 0, "text": result.get("text", ""), "finish_reason": None}],
            "rift": {"usability_verdict": result.get("usability_verdict")},
        }
        final = {
            "id": "rift-completion-local",
            "object": "text_completion.chunk",
            "created": int(time.time()),
            "model": self.runtime.model_id(),
            "choices": [{"index": 0, "text": "", "finish_reason": "length"}],
        }
        self._send_sse([payload, final])

    def _send_chat_stream(self, result: JsonDict) -> None:
        payload = {
            "id": "rift-chat-local",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": self.runtime.model_id(),
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": result.get("text", "")},
                    "finish_reason": None,
                }
            ],
            "rift": {"usability_verdict": result.get("usability_verdict")},
        }
        final = {
            "id": "rift-chat-local",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": self.runtime.model_id(),
            "choices": [{"index": 0, "delta": {}, "finish_reason": "length"}],
        }
        self._send_sse([payload, final])

    def _send_sse(self, payloads: list[JsonDict]) -> None:
        chunks = [f"data: {json.dumps(payload, sort_keys=True)}\n\n" for payload in payloads]
        chunks.append("data: [DONE]\n\n")
        body = "".join(chunks).encode("utf-8")
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _chat_prompt(self, payload: JsonDict) -> str:
        messages = payload.get("messages", [])
        if not isinstance(messages, list) or not messages:
            raise ValueError("messages must be a non-empty list")
        parts: list[str] = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role", "user"))
            content = str(message.get("content", ""))
            parts.append(f"{role}: {content}")
        parts.append("assistant:")
        return "\n".join(parts)

    def _read_json_body(self) -> JsonDict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8")) if raw else {}

    def _send_json(self, status: HTTPStatus, payload: JsonDict) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _allowed_origins(self) -> set[str]:
        raw = os.environ.get(
            "RIFT_CONTROL_CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173,http://localhost:8765,http://127.0.0.1:8765",
        )
        return {item.strip() for item in raw.split(",") if item.strip()}

    def _cors_allowed(self, origin: str | None) -> bool:
        return not origin or origin in self._allowed_origins()

    def _send_cors_headers(self) -> None:
        origin = self.headers.get("Origin")
        if origin and self._cors_allowed(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")


def create_rift_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8777,
    model_path: Optional[str] = None,
    plan_path: Optional[str] = None,
    runtime: Optional[RiftServerRuntime] = None,
) -> ThreadingHTTPServer:
    runtime = runtime or RiftServerRuntime(model_path=model_path, plan_path=plan_path)

    class BoundHandler(RiftRequestHandler):
        pass

    BoundHandler.runtime = runtime
    return ThreadingHTTPServer((host, port), BoundHandler)


def serve_rift(
    *,
    host: str = "127.0.0.1",
    port: int = 8777,
    model_path: Optional[str] = None,
    plan_path: Optional[str] = None,
) -> None:
    server = create_rift_server(
        host=host,
        port=port,
        model_path=model_path,
        plan_path=plan_path,
    )
    url = f"http://{host}:{server.server_port}"
    print(f"RIFT server listening on {url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nRIFT server stopped")
    finally:
        server.server_close()
