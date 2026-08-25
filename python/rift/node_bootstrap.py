"""One-command node enrollment and foreground agent orchestration."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import ssl
import subprocess
import sys
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .mesh.discovery_transports import resolve_controller_mdns
from .node_agent import create_node_agent_server
from .node_enrollment import ManagedNodeStore, PairingHandshake
from .runtime_paths import RiftPaths


JsonDict = dict[str, Any]


def _certificate_fingerprint(host: str, port: int, *, timeout: float = 5.0) -> str:
    import socket

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=timeout) as raw:
        with context.wrap_socket(raw, server_hostname=host) as tls:
            certificate = tls.getpeercert(binary_form=True)
    return "sha256:" + hashlib.sha256(certificate).hexdigest()


def _request_json(
    url: str,
    *,
    method: str = "GET",
    payload: JsonDict | None = None,
    bootstrap_fingerprint: str | None = None,
    context: ssl.SSLContext | None = None,
    timeout: float = 10.0,
) -> JsonDict:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("RIFT node enrollment requires an HTTPS controller URL")
    if bootstrap_fingerprint:
        actual = _certificate_fingerprint(parsed.hostname, parsed.port or 443, timeout=timeout)
        if actual != bootstrap_fingerprint:
            raise PermissionError("controller bootstrap certificate fingerprint changed")
    body = None if payload is None else json.dumps(payload, sort_keys=True).encode("utf-8")
    request = Request(
        url,
        data=body,
        method=method,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "RIFT-Node-Bootstrap/1",
        },
    )
    active_context = context or ssl._create_unverified_context()
    try:
        with urlopen(request, timeout=timeout, context=active_context) as response:
            value = json.loads(response.read(1024 * 1024).decode("utf-8"))
    except HTTPError as exc:
        try:
            detail = json.loads(exc.read(256 * 1024).decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            detail = {"error": str(exc)}
        raise RuntimeError(str(detail.get("error") or f"controller returned HTTP {exc.code}")) from exc
    except (OSError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"controller request failed: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError("controller returned a non-object bootstrap response")
    return value


def _normalize_controller(url: str) -> str:
    value = url.strip().rstrip("/")
    if not value:
        raise ValueError("controller URL is empty")
    if "://" not in value:
        value = "https://" + value
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("controller URL must be HTTPS and include a hostname")
    return value


class NodeBootstrapClient:
    """Node-owned enrollment flow; the controller never receives the SAS code."""

    def __init__(
        self,
        *,
        root: str | Path | None = None,
        controller: str | None = None,
        display_name: str | None = None,
        host: str = "0.0.0.0",
        advertise_host: str | None = None,
        port: int = 11750,
        output: Callable[[str], None] = print,
    ) -> None:
        paths = RiftPaths.from_environment() if root is None else None
        self.root = Path(root).expanduser().resolve() if root is not None else paths.home.resolve()
        self.store = ManagedNodeStore(self.root)
        self.controller = controller
        self.display_name = display_name
        self.host = host
        self.advertise_host = advertise_host
        self.port = int(port)
        self.output = output

    def resolve_controller(self) -> JsonDict:
        if self.controller:
            base = _normalize_controller(self.controller)
            return self._discover_controller(base)
        candidates = list(resolve_controller_mdns(timeout_seconds=2.0))
        if not candidates:
            raise RuntimeError(
                "no enrollment-enabled RIFT controller was discovered; retry with "
                "`rift node start --controller https://HOST:11748`"
            )
        if len(candidates) > 1:
            raise RuntimeError(
                "multiple RIFT controllers were discovered; retry with --controller. "
                + ", ".join(str(item.get("endpoint")) for item in candidates)
            )
        record = dict(candidates[0])
        record["endpoint"] = _normalize_controller(str(record["endpoint"]))
        return record

    def _discover_controller(self, base: str) -> JsonDict:
        parsed = urlparse(base)
        discovery_url = base + "/.well-known/rift-controller"
        record = _request_json(discovery_url)
        advertised = str(record.get("bootstrap_fingerprint") or "")
        if not advertised:
            raise RuntimeError("controller discovery did not provide a bootstrap fingerprint")
        actual = _certificate_fingerprint(parsed.hostname or "", parsed.port or 443)
        if actual != advertised:
            raise PermissionError("controller discovery certificate fingerprint does not match")
        record["endpoint"] = _normalize_controller(str(record.get("endpoint") or base))
        record["bootstrap_fingerprint"] = advertised
        return record

    def _endpoint(self) -> str:
        advertised = (self.advertise_host or self.host).strip()
        if advertised in {"0.0.0.0", "::", ""}:
            advertised = "127.0.0.1"
        return f"https://{advertised}:{self.port}"

    def enroll(self, *, timeout_seconds: float = 600.0) -> JsonDict:
        identity = self.store.ensure_identity(
            display_name=self.display_name,
            host=self.host,
            port=self.port,
        )
        csr = self.store.ensure_csr(identity.node_id)
        controller = self.resolve_controller()
        controller_url = str(controller["endpoint"]).rstrip("/")
        handshake = PairingHandshake.create(role="node")
        begin = _request_json(
            controller_url + "/v1/bootstrap/enrollments",
            method="POST",
            payload={
                "node_id": identity.node_id,
                "display_name": identity.display_name,
                "endpoint": self._endpoint(),
                "csr_pem": csr["csr_pem"],
                "node_public_key": handshake.public_key.hex(),
            },
            bootstrap_fingerprint=str(controller.get("bootstrap_fingerprint") or ""),
        )
        enrollment_id = str(begin.get("enrollment_id") or "")
        transcript = str(begin.get("transcript") or "")
        controller_public_key = str(begin.get("controller_public_key") or "")
        if not enrollment_id or not transcript or not controller_public_key:
            raise RuntimeError("controller returned an incomplete enrollment challenge")
        pairing = handshake.complete(bytes.fromhex(controller_public_key), transcript)
        self.store.save_enrollment(
            {
                "schema_version": 1,
                "enrollment_id": enrollment_id,
                "controller_id": str(controller.get("controller_id") or ""),
                "controller_endpoint": controller_url,
                "bootstrap_fingerprint": str(controller.get("bootstrap_fingerprint") or ""),
                "node_id": identity.node_id,
                "transcript": transcript,
                "state": "PAIRING_PENDING",
                "created_at": time.time(),
            }
        )
        self.output(f"RIFT node identity: {identity.node_id}")
        self.output(f"Controller: {controller_url}")
        self.output(f"PAIRING CODE (enter this in the controller UI): {pairing.code}")
        deadline = time.monotonic() + max(5.0, float(timeout_seconds))
        status: JsonDict = begin
        while time.monotonic() < deadline:
            time.sleep(1.0)
            status = _request_json(
                controller_url + f"/v1/bootstrap/enrollments/{enrollment_id}",
                bootstrap_fingerprint=str(controller.get("bootstrap_fingerprint") or ""),
            )
            state = str(status.get("state") or "")
            if state == "CERTIFICATE_ISSUED":
                self._install_certificate_bundle(pairing, status)
                return self._activate(
                    pairing,
                    controller,
                    enrollment_id,
                    controller_url,
                    status,
                )
            if state in {"REJECTED", "CANCELLED", "EXPIRED"}:
                raise RuntimeError(f"controller enrollment ended in state {state}")
        raise TimeoutError("pairing challenge timed out; rerun `rift node start` to begin again")

    def _install_certificate_bundle(self, pairing, status: JsonDict) -> None:
        envelope = status.get("certificate_envelope")
        if not isinstance(envelope, dict):
            raise RuntimeError("controller did not return a certificate envelope")
        payload = pairing.decrypt(envelope)
        if str(payload.get("node_id")) != str(self.store.ensure_identity().node_id):
            raise PermissionError("certificate bundle node identity does not match this node")
        certificate_pem = str(payload.get("certificate_pem") or "")
        ca_pem = str(payload.get("ca_certificate_pem") or "")
        if not certificate_pem or not ca_pem:
            raise RuntimeError("certificate bundle is incomplete")
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import ExtendedKeyUsageOID

        key_info = self.store.ensure_csr(self.store.ensure_identity().node_id)
        key = serialization.load_pem_private_key(Path(key_info["private_key_path"]).read_bytes(), password=None)
        certificate = x509.load_pem_x509_certificate(certificate_pem.encode("ascii"))
        ca_certificate = x509.load_pem_x509_certificate(ca_pem.encode("ascii"))
        if certificate.public_key().public_numbers() != key.public_key().public_numbers():
            raise PermissionError("issued certificate does not match the node private key")
        if certificate.issuer != ca_certificate.subject:
            raise PermissionError("issued certificate is not signed by the returned controller CA")
        usages = certificate.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        if ExtendedKeyUsageOID.CLIENT_AUTH not in usages or ExtendedKeyUsageOID.SERVER_AUTH not in usages:
            raise PermissionError("issued node certificate does not have the required TLS usages")
        san = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        expected_uri = f"rift-node:{self.store.ensure_identity().node_id}"
        if expected_uri not in {str(value) for value in san.get_values_for_type(x509.UniformResourceIdentifier)}:
            raise PermissionError("issued certificate has the wrong node URI identity")
        if not isinstance(key, ec.EllipticCurvePrivateKey):
            raise PermissionError("node certificate key type is unsupported")
        tls_dir = self.store.node_dir / "tls"
        tls_dir.mkdir(parents=True, exist_ok=True)
        from .node_enrollment import _atomic_text

        _atomic_text(tls_dir / "node.crt.pem", certificate_pem, private=True)
        _atomic_text(tls_dir / "controller-ca.crt.pem", ca_pem, private=False)
        self.store.update_config(
            {
                "tls": {
                    "certificate": str(tls_dir / "node.crt.pem"),
                    "private_key": str(key_info["private_key_path"]),
                    "client_ca": str(tls_dir / "controller-ca.crt.pem"),
                    "expected_controller_id": str(payload.get("controller_id") or ""),
                },
                "controller": {"id": str(payload.get("controller_id") or "")},
            }
        )

    def _activate(
        self,
        pairing,
        controller: JsonDict,
        enrollment_id: str,
        controller_url: str,
        status: JsonDict,
    ) -> JsonDict:
        from .node_enrollment import _atomic_json

        server = create_node_agent_server(config_path=self.store.config_path, root=self.root)
        import threading

        thread = threading.Thread(target=server.serve_forever, name="rift-node-agent", daemon=True)
        thread.start()
        try:
            result = _request_json(
                controller_url + f"/v1/bootstrap/enrollments/{enrollment_id}/activate",
                method="POST",
                payload={},
                bootstrap_fingerprint=str(controller.get("bootstrap_fingerprint") or ""),
            )
            envelope = result.get("activation_envelope")
            if not isinstance(envelope, dict):
                raise RuntimeError("controller did not return an activation envelope")
            credentials = pairing.decrypt(envelope)
            if str(credentials.get("node_id")) != str(self.store.ensure_identity().node_id):
                raise PermissionError("activation identity does not match this node")
            _atomic_json(self.store.credentials_path, credentials)
            self.store.save_enrollment(
                {
                    "schema_version": 1,
                    "enrollment_id": enrollment_id,
                    "controller_id": str(controller.get("controller_id") or ""),
                    "controller_endpoint": controller_url,
                    "bootstrap_fingerprint": str(controller.get("bootstrap_fingerprint") or ""),
                    "node_id": self.store.ensure_identity().node_id,
                    "state": "ACTIVE",
                    "activated_at": time.time(),
                }
            )
            return {"enrolled": True, "state": "ACTIVE", "node_id": self.store.ensure_identity().node_id, "server": server, "thread": thread}
        except Exception:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
            raise

    def run_foreground(self) -> None:
        identity = self.store.ensure_identity(
            display_name=self.display_name,
            host=self.host,
            port=self.port,
        )
        config = self.store.read_config()
        credentials = self.store.enrollment_path.is_file() and self.store.credentials_path.is_file()
        if credentials and self.controller:
            saved = json.loads(self.store.enrollment_path.read_text(encoding="utf-8"))
            saved_endpoint = _normalize_controller(str(saved.get("controller_endpoint") or ""))
            requested_endpoint = _normalize_controller(self.controller)
            if requested_endpoint != saved_endpoint:
                raise PermissionError(
                    "this node is already enrolled with a different controller; explicit re-enrollment is required"
                )
        if not credentials:
            result = self.enroll()
            server = result.pop("server")
            thread = result.pop("thread")
        else:
            server = create_node_agent_server(config_path=self.store.config_path, root=self.root)
            thread = None
            server_thread = __import__("threading").Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            thread = server_thread
            self.output(f"RIFT node {identity.node_id} is already enrolled; pairing skipped")
        pid_path = self.store.node_dir / "node.pid"
        pid_path.write_text(str(os.getpid()), encoding="ascii")
        self.output(f"RIFT node agent listening on {config.get('host', self.host)}:{config.get('port', self.port)}")
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            self.output("Stopping RIFT node agent; enrollment state was preserved.")
        finally:
            server.shutdown()
            server.server_close()
            if thread is not None:
                thread.join(timeout=3)
            if pid_path.exists():
                pid_path.unlink()

    def status(self) -> JsonDict:
        identity = self.store.ensure_identity(
            display_name=self.display_name,
            host=self.host,
            port=self.port,
        )
        return {
            "node_id": identity.node_id,
            "display_name": identity.display_name,
            "config_path": str(identity.config_path),
            "enrollment": json.loads(self.store.enrollment_path.read_text(encoding="utf-8")) if self.store.enrollment_path.is_file() else {"state": "UNENROLLED"},
            "credentials_present": self.store.credentials_path.is_file(),
            "pid": int(self.store.node_dir.joinpath("node.pid").read_text(encoding="ascii")) if self.store.node_dir.joinpath("node.pid").is_file() else None,
            "permissions": dict(self.store.read_config().get("permissions") or {}),
        }


def service_install_plan(*, root: str | Path | None = None) -> JsonDict:
    home = (Path(root) if root is not None else RiftPaths.from_environment().home).expanduser().resolve()
    command = [sys.executable, "-m", "rift.cli", "node", "start"]
    system = platform.system().lower()
    if system == "windows":
        return {"platform": "windows", "kind": "scheduled-task", "task_name": "RIFT Node", "command": " ".join(command), "install": "schtasks /Create /TN RIFT Node /SC ONLOGON /TR ... /F", "state_root": str(home)}
    if system == "darwin":
        return {"platform": "macos", "kind": "launch-agent", "label": "dev.rift.node", "command": command, "path": str(home / "service" / "dev.rift.node.plist")}
    return {"platform": "linux", "kind": "systemd-user", "unit": "rift-node.service", "command": command, "path": str(home / "service" / "rift-node.service")}


def install_node_service(*, root: str | Path | None = None) -> JsonDict:
    """Install a user-scoped auto-start service without elevating privileges."""

    home = (Path(root) if root is not None else RiftPaths.from_environment().home).expanduser().resolve()
    command = [sys.executable, "-m", "rift.cli", "node", "start", "--root", str(home)]
    plan = service_install_plan(root=home)
    system = platform.system().lower()
    if system == "windows":
        task_command = subprocess.list2cmdline(command)
        completed = subprocess.run(
            ["schtasks", "/Create", "/TN", "RIFT Node", "/SC", "ONLOGON", "/TR", task_command, "/F"],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "schtasks failed").strip())
        started = subprocess.run(["schtasks", "/Run", "/TN", "RIFT Node"], check=False, capture_output=True, text=True)
        if started.returncode != 0:
            raise RuntimeError((started.stderr or started.stdout or "scheduled task could not be started").strip())
        return {**plan, "installed": True, "started": True, "output": started.stdout.strip()}
    service_dir = home / "service"
    service_dir.mkdir(parents=True, exist_ok=True)
    if system == "darwin":
        import plistlib

        path = service_dir / "dev.rift.node.plist"
        path.write_bytes(
            plistlib.dumps(
                {"Label": "dev.rift.node", "ProgramArguments": command, "RunAtLoad": True, "KeepAlive": True}
            )
        )
        completed = subprocess.run(["launchctl", "load", str(path)], check=False, capture_output=True, text=True)
    else:
        path = service_dir / "rift-node.service"
        path.write_text(
            "[Unit]\nDescription=RIFT node agent\nAfter=network-online.target\n\n"
            "[Service]\nExecStart=" + subprocess.list2cmdline(command) + "\nRestart=on-failure\n\n"
            "[Install]\nWantedBy=default.target\n",
            encoding="utf-8",
        )
        completed = subprocess.run(["systemctl", "--user", "daemon-reload"], check=False, capture_output=True, text=True)
        if completed.returncode == 0:
            completed = subprocess.run(["systemctl", "--user", "enable", "--now", "rift-node.service"], check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "service manager failed").strip())
    return {**plan, "installed": True, "started": True, "path": str(path)}


__all__ = ["NodeBootstrapClient", "service_install_plan", "install_node_service"]
