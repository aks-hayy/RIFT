"""Mutual-TLS node agent for RIFT cluster desired-state reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import ssl
import time
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .orchestrator import ApplyPermissions, RiftOrchestrator
from .rift_yaml import read_yaml, write_yaml


JsonDict = dict[str, Any]
_INFERENCE_PATHS = frozenset({"/v1/chat/completions", "/v1/completions", "/v1/embeddings"})


@dataclass(frozen=True)
class NodeAgentPolicy:
    node_id: str
    host: str
    port: int
    certificate: str
    private_key: str
    client_ca: str
    expected_controller_id: str | None = None
    allow_download: bool = False
    allow_install: bool = False
    allow_launch: bool = False
    allow_inference: bool = False
    max_request_bytes: int = 4 * 1024 * 1024

    @classmethod
    def from_file(cls, path: str | Path) -> "NodeAgentPolicy":
        payload = read_yaml(path)
        if not isinstance(payload, dict):
            raise ValueError("node agent config must be an object")
        tls = payload.get("tls") or {}
        permissions = payload.get("permissions") or {}
        policy = cls(
            node_id=str(payload.get("node_id") or "").strip(),
            host=str(payload.get("host") or "127.0.0.1"),
            port=int(payload.get("port") or 11750),
            certificate=str(tls.get("certificate") or ""),
            private_key=str(tls.get("private_key") or ""),
            client_ca=str(tls.get("client_ca") or ""),
            expected_controller_id=(str(tls.get("expected_controller_id")) if tls.get("expected_controller_id") else None),
            allow_download=bool(permissions.get("allow_download", False)),
            allow_install=bool(permissions.get("allow_install", False)),
            allow_launch=bool(permissions.get("allow_launch", False)),
            allow_inference=bool(permissions.get("allow_inference", False)),
            max_request_bytes=int(payload.get("max_request_bytes") or 4 * 1024 * 1024),
        )
        policy.validate()
        return policy

    def validate(self) -> None:
        if not self.node_id:
            raise ValueError("node_id is required")
        if not 1 <= self.port <= 65535:
            raise ValueError("node agent port must be between 1 and 65535")
        if self.max_request_bytes <= 0:
            raise ValueError("max_request_bytes must be positive")
        for label, value in (
            ("certificate", self.certificate),
            ("private_key", self.private_key),
            ("client_ca", self.client_ca),
        ):
            if not value:
                raise ValueError(f"node agent TLS {label} is required")


def default_node_agent_config(node_id: str = "rift-node") -> JsonDict:
    return {
        "version": 1,
        "node_id": node_id,
        "host": "127.0.0.1",
        "port": 11750,
        "tls": {
            "certificate": ".rift/agent/tls/node.crt",
            "private_key": ".rift/agent/tls/node.key",
            "client_ca": ".rift/agent/tls/controller-ca.crt",
            "minimum_version": "TLSv1.2",
            "client_certificate_required": True,
        },
        "permissions": {
            "allow_download": False,
            "allow_install": False,
            "allow_launch": False,
            "allow_inference": False,
        },
        "max_request_bytes": 4 * 1024 * 1024,
    }


class NodeAgentController:
    """Node-side desired-state boundary; network authentication lives in the server."""

    def __init__(
        self,
        *,
        root: str | Path,
        policy: NodeAgentPolicy,
        orchestrator: RiftOrchestrator | None = None,
    ) -> None:
        self.root = Path(root)
        self.policy = policy
        self.orchestrator = orchestrator or RiftOrchestrator(root=self.root)
        self.agent_root = self.root / ".rift" / "agent"
        self.desired_path = self.agent_root / "desired-state.json"
        self.agent_state_path = self.agent_root / "state.json"

    def health(self) -> JsonDict:
        state = self._read_json(self.agent_state_path)
        return {
            "ok": True,
            "node_id": self.policy.node_id,
            "mutual_tls_required": True,
            "desired_generation": state.get("desired_generation", 0),
            "last_reconciled_generation": state.get("last_reconciled_generation", 0),
            "created_unix_seconds": time.time(),
        }

    def discover(self) -> JsonDict:
        discovery = self.orchestrator.discover(local=True, write=False)
        node = (discovery.get("nodes") or [{}])[0]
        return {
            "node_id": self.policy.node_id,
            "hardware": node.get("hardware") or {},
            "backends": node.get("backends") or {},
            "artifact_inventory": self.artifact_inventory(),
            "agent": self.health(),
        }

    def artifact_inventory(self) -> JsonDict:
        models_root = self.root / ".rift" / "models"
        artifacts = []
        if models_root.is_dir():
            for model_dir in sorted(item for item in models_root.iterdir() if item.is_dir()):
                try:
                    resolved = self.orchestrator.scan_local_models(str(model_dir))
                except Exception as exc:
                    artifacts.append({"path": str(model_dir), "error": str(exc)})
                    continue
                artifacts.extend(resolved)
        return {"model_root": str(models_root), "artifacts": artifacts}

    def submit_desired_state(self, payload: JsonDict) -> JsonDict:
        generation = int(payload.get("generation") or 0)
        config = payload.get("config")
        if generation <= 0:
            raise ValueError("desired-state generation must be positive")
        if not isinstance(config, dict):
            raise ValueError("desired-state config must be an object")
        current = self._read_json(self.desired_path)
        current_generation = int(current.get("generation") or 0)
        digest = self._fingerprint(config)
        if generation < current_generation:
            raise ValueError(
                f"stale desired-state generation {generation}; current generation is {current_generation}"
            )
        if generation == current_generation:
            if digest != str(current.get("config_fingerprint") or ""):
                raise ValueError("desired-state generation collision with different content")
            return {
                "accepted": True,
                "changed": False,
                "generation": generation,
                "config_fingerprint": digest,
            }
        desired = {
            "schema_version": 1,
            "node_id": self.policy.node_id,
            "generation": generation,
            "config_fingerprint": digest,
            "config": config,
            "received_unix_seconds": time.time(),
        }
        self._write_json(self.desired_path, desired)
        state = self._read_json(self.agent_state_path)
        state.update(
            {
                "node_id": self.policy.node_id,
                "desired_generation": generation,
                "desired_fingerprint": digest,
                "updated_unix_seconds": time.time(),
            }
        )
        self._write_json(self.agent_state_path, state)
        return {
            "accepted": True,
            "changed": True,
            "generation": generation,
            "config_fingerprint": digest,
        }

    def reconcile(self, payload: JsonDict | None = None) -> JsonDict:
        desired = self._read_json(self.desired_path)
        if not desired:
            return {"reconciled": False, "reason": "no desired state has been submitted"}
        config_path = self.agent_root / "desired.rift.yaml"
        write_yaml(config_path, desired["config"])
        plan = self.orchestrator.plan(config_path=config_path, write=True)
        request = payload or {}
        apply_requested = bool(request.get("apply", False))
        if not apply_requested:
            result: JsonDict = {"reconciled": True, "applied": False, "plan": plan}
        else:
            requested = request.get("permissions") or {}
            permissions = ApplyPermissions(
                allow_download=bool(requested.get("allow_download", False))
                and self.policy.allow_download,
                allow_install=bool(requested.get("allow_install", False))
                and self.policy.allow_install,
                allow_launch=bool(requested.get("allow_launch", False))
                and self.policy.allow_launch,
            )
            result = self.orchestrator.apply(config_path=config_path, permissions=permissions)
            result["reconciled"] = True
        state = self._read_json(self.agent_state_path)
        state.update(
            {
                "last_reconciled_generation": int(desired["generation"]),
                "last_reconciled_fingerprint": desired["config_fingerprint"],
                "last_result": {
                    "applied": result.get("applied"),
                    "reason": result.get("reason"),
                },
                "updated_unix_seconds": time.time(),
            }
        )
        self._write_json(self.agent_state_path, state)
        result["generation"] = int(desired["generation"])
        return result

    def status(self) -> JsonDict:
        return {
            "agent": self.health(),
            "desired_state": self._read_json(self.desired_path),
            "runtime": self.orchestrator.status(),
        }

    def telemetry(self) -> JsonDict:
        """Return this node's local telemetry for controller forwarding."""
        latest = self.orchestrator.telemetry_latest(node_id="local")
        latest_items = [item for item in latest.get("samples") or [] if isinstance(item, dict)]
        latest_sample = next(
            (item.get("sample") for item in latest_items if isinstance(item.get("sample"), dict)),
            {},
        )
        samples = [item["sample"] for item in latest_items if isinstance(item.get("sample"), dict)]
        state = self._read_json(self.agent_state_path)
        sequence = int(state.get("telemetry_sequence") or 0) + 1
        state["telemetry_sequence"] = sequence
        state["updated_unix_seconds"] = time.time()
        self._write_json(self.agent_state_path, state)
        latest_session = latest_items[0].get("session") if latest_items else {}
        if not isinstance(latest_session, dict):
            latest_session = {}
        return {
            "node_id": self.policy.node_id,
            "observed_at": time.time(),
            "sequence": sequence,
            "session_id": str(latest_session.get("session_id") or "") or None,
            "samples": samples[:1000],
            **latest_sample,
            "telemetry": latest,
            "sessions": self.orchestrator.telemetry_sessions(node_id="local"),
        }

    def inference(self, payload: JsonDict) -> JsonDict:
        """Proxy one bounded OpenAI-compatible request through the node policy.

        The agent derives the upstream URL from RIFT-managed service state. The
        caller cannot supply an arbitrary target, which prevents the mTLS agent
        from becoming a general-purpose SSRF proxy. Streaming is intentionally
        rejected until the raw response path is implemented end to end.
        """
        if not self.policy.allow_inference:
            raise PermissionError("node inference proxy is disabled by policy")
        path = str(payload.get("path") or "")
        if path not in _INFERENCE_PATHS:
            raise ValueError(f"unsupported inference path: {path or 'missing'}")
        body = payload.get("body")
        if not isinstance(body, dict):
            raise ValueError("inference body must be an object")
        if bool(body.get("stream")):
            raise ValueError("streaming inference is not available through this agent revision")
        service_name = str(payload.get("service") or "chat")
        state = self.orchestrator.read_state()
        service = (state.get("services") or {}).get(service_name)
        if not isinstance(service, dict):
            raise ValueError(f"managed service is not found: {service_name}")
        runtime = service.get("runtime") or {}
        launch_plan = service.get("launch_plan") or {}
        base_url = str(runtime.get("api_base") or launch_plan.get("api_base") or "").rstrip("/")
        if not base_url.startswith("http://") and not base_url.startswith("https://"):
            raise ValueError(f"managed service {service_name} has no HTTP API route")
        request_body = json.dumps(body).encode("utf-8")
        if len(request_body) > self.policy.max_request_bytes:
            raise ValueError("inference request exceeds node agent body limit")
        request = Request(
            f"{base_url}{path}",
            data=request_body,
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "RIFT-Node-Inference/1",
                "X-RIFT-Node-ID": self.policy.node_id,
            },
        )
        try:
            response = urlopen(request, timeout=120.0)
        except HTTPError as exc:
            raw = exc.read(self.policy.max_request_bytes + 1)
            exc.close()
            return {
                "ok": False,
                "status": int(exc.code),
                "service": service_name,
                "upstream": f"{base_url}{path}",
                "body": self._decode_response(raw, exc.headers.get("Content-Type", "")),
            }
        with response:
            raw = response.read(self.policy.max_request_bytes + 1)
            if len(raw) > self.policy.max_request_bytes:
                raise ValueError("inference response exceeds node agent body limit")
            return {
                "ok": 200 <= int(response.status) < 400,
                "status": int(response.status),
                "service": service_name,
                "upstream": f"{base_url}{path}",
                "body": self._decode_response(raw, response.headers.get("Content-Type", "")),
            }

    @staticmethod
    def _decode_response(raw: bytes, content_type: str) -> Any:
        if "json" in content_type.lower():
            try:
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return {"raw_body": raw.decode("utf-8", errors="replace")}
            return value
        return {"raw_body": raw.decode("utf-8", errors="replace")}

    @staticmethod
    def _fingerprint(payload: Any) -> str:
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _read_json(path: Path) -> JsonDict:
        if not path.is_file():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _write_json(path: Path, payload: JsonDict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(path)


class _NodeAgentHandler(BaseHTTPRequestHandler):
    controller: NodeAgentController
    server_version = "RIFTNode/1"

    def do_GET(self) -> None:  # noqa: N802
        self._require_controller_identity()
        routes: dict[str, Callable[[], JsonDict]] = {
            "/v1/health": self.controller.health,
            "/v1/discovery": self.controller.discover,
            "/v1/artifacts": self.controller.artifact_inventory,
            "/v1/state": self.controller.status,
            "/v1/telemetry": self.controller.telemetry,
        }
        operation = routes.get(self.path)
        if operation is None:
            self._send(HTTPStatus.NOT_FOUND, {"error": "unknown endpoint"})
            return
        try:
            self._send(HTTPStatus.OK, operation())
        except Exception as exc:
            self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        try:
            self._require_controller_identity()
            payload = self._read_body()
            if self.path == "/v1/desired-state":
                result = self.controller.submit_desired_state(payload)
            elif self.path == "/v1/reconcile":
                result = self.controller.reconcile(payload)
            elif self.path == "/v1/inference":
                result = self.controller.inference(payload)
            else:
                self._send(HTTPStatus.NOT_FOUND, {"error": "unknown endpoint"})
                return
            self._send(HTTPStatus.OK, result)
        except ValueError as exc:
            self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def _require_controller_identity(self) -> None:
        expected = self.controller.policy.expected_controller_id
        if not expected:
            return
        from cryptography import x509

        certificate = self.connection.getpeercert(binary_form=True)
        if not certificate:
            raise PermissionError("controller client certificate is required")
        peer = x509.load_der_x509_certificate(certificate)
        try:
            san = peer.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            uris = {str(value) for value in san.get_values_for_type(x509.UniformResourceIdentifier)}
        except x509.ExtensionNotFound as exc:
            raise PermissionError("controller certificate has no URI identity") from exc
        if f"rift-controller:{expected}" not in uris:
            raise PermissionError("controller certificate identity does not match this node")

    def _read_body(self) -> JsonDict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > self.controller.policy.max_request_bytes:
            raise ValueError("request body length is invalid")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("request body must be an object")
        return payload

    def _send(self, status: HTTPStatus, payload: JsonDict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


def create_node_agent_server(*, config_path: str | Path, root: str | Path | None = None) -> ThreadingHTTPServer:
    config_file = Path(config_path).resolve()
    policy = NodeAgentPolicy.from_file(config_file)
    base = Path(root).resolve() if root is not None else config_file.parent

    def resolve_tls(value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else base / path

    certificate = resolve_tls(policy.certificate)
    private_key = resolve_tls(policy.private_key)
    client_ca = resolve_tls(policy.client_ca)
    for label, path in (
        ("certificate", certificate),
        ("private key", private_key),
        ("client CA", client_ca),
    ):
        if not path.is_file():
            raise ValueError(f"node agent TLS {label} does not exist: {path}")
    controller = NodeAgentController(root=base, policy=policy)
    handler = type("RiftNodeAgentHandler", (_NodeAgentHandler,), {"controller": controller})
    server = ThreadingHTTPServer((policy.host, policy.port), handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_cert_chain(certfile=str(certificate), keyfile=str(private_key))
    context.load_verify_locations(cafile=str(client_ca))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    return server


def serve_node_agent(*, config_path: str | Path, root: str | Path | None = None) -> None:
    server = create_node_agent_server(config_path=config_path, root=root)
    try:
        server.serve_forever()
    finally:
        server.server_close()


__all__ = [
    "NodeAgentController",
    "NodeAgentPolicy",
    "default_node_agent_config",
    "create_node_agent_server",
    "serve_node_agent",
]
