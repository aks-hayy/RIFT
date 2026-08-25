"""Short-lived TLS listener exposing only controller node-enrollment routes."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ssl
import threading
import time
from typing import Any
from urllib.parse import urlparse

from .controller import MeshController


class _BootstrapHandler(BaseHTTPRequestHandler):
    server_version = "RIFTBootstrap/1"
    controller: MeshController
    advertised_host: str
    advertised_port: int
    bootstrap_fingerprint: str
    max_request_bytes = 1024 * 1024

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path == "/.well-known/rift-controller":
                self._send(
                    HTTPStatus.OK,
                    {
                        "controller_id": self.controller.controller_id,
                        "endpoint": f"https://{self.advertised_host}:{self.advertised_port}",
                        "api_version": "2",
                        "bootstrap_fingerprint": self.bootstrap_fingerprint,
                        "ttl_seconds": 120,
                    },
                )
                return
            if path.startswith("/v1/bootstrap/enrollments/"):
                enrollment_id = path.rsplit("/", 1)[-1]
                self._send(HTTPStatus.OK, self.controller.bootstrap_status(enrollment_id))
                return
        except TimeoutError as exc:
            self._send(HTTPStatus.GONE, {"error": str(exc)})
            return
        except (KeyError, ValueError, PermissionError) as exc:
            self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._send(HTTPStatus.NOT_FOUND, {"error": "unknown bootstrap endpoint"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path.startswith("/v1/bootstrap/enrollments/") and path.endswith("/activate"):
            enrollment_id = path.split("/")[-2]
            try:
                self._send(HTTPStatus.OK, self.controller.bootstrap_activate(enrollment_id))
            except TimeoutError as exc:
                self._send(HTTPStatus.GONE, {"error": str(exc)})
            except (KeyError, ValueError, PermissionError) as exc:
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except RuntimeError as exc:
                self._send(HTTPStatus.CONFLICT, {"error": str(exc)})
            return
        if path != "/v1/bootstrap/enrollments":
            self._send(HTTPStatus.NOT_FOUND, {"error": "unknown bootstrap endpoint"})
            return
        if not self.server.allow_attempt(self.client_address[0]):
            self._send(HTTPStatus.TOO_MANY_REQUESTS, {"error": "bootstrap enrollment rate limit exceeded"})
            return
        try:
            payload = self._read_json()
            result = self.controller.bootstrap_begin(
                node_id=str(payload.get("node_id") or ""),
                display_name=str(payload.get("display_name") or ""),
                endpoint=str(payload.get("endpoint") or ""),
                csr_pem=str(payload.get("csr_pem") or ""),
                node_public_key=str(payload.get("node_public_key") or ""),
            )
            self._send(HTTPStatus.CREATED, result)
        except PermissionError as exc:
            self._send(HTTPStatus.FORBIDDEN, {"error": str(exc)})
        except (ValueError, KeyError) as exc:
            self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except RuntimeError as exc:
            self._send(HTTPStatus.TOO_MANY_REQUESTS, {"error": str(exc)})

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > self.max_request_bytes:
            raise ValueError("bootstrap request body length is invalid")
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("bootstrap request body must be an object")
        return value

    def _send(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


class _BootstrapHTTPServer(ThreadingHTTPServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._rate_lock = threading.Lock()
        self._rates: dict[str, tuple[float, int]] = {}

    def allow_attempt(self, address: str) -> bool:
        now = time.monotonic()
        with self._rate_lock:
            started, count = self._rates.get(address, (now, 0))
            if now - started >= 60.0:
                started, count = now, 0
            if count >= 20:
                self._rates[address] = (started, count)
                return False
            self._rates[address] = (started, count + 1)
            return True

    def handle_error(self, _request, _client_address) -> None:
        # A discovery client may close its pinning socket immediately after
        # reading the certificate. Bootstrap must not emit noisy tracebacks.
        return


def create_bootstrap_server(
    *,
    controller: MeshController,
    host: str = "0.0.0.0",
    port: int = 11748,
    advertised_host: str = "127.0.0.1",
) -> ThreadingHTTPServer:
    if not 1 <= int(port) <= 65535:
        raise ValueError("bootstrap port must be between 1 and 65535")
    material = controller.bootstrap_tls_material(addresses=[advertised_host])
    server = _BootstrapHTTPServer((host, int(port)), _BootstrapHandler)
    handler = type(
        "BoundBootstrapHandler",
        (_BootstrapHandler,),
        {
            "controller": controller,
            "advertised_host": advertised_host,
            "advertised_port": int(server.server_port),
            "bootstrap_fingerprint": material["fingerprint"],
        },
    )
    server.RequestHandlerClass = handler
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(material["certificate"], material["private_key"])
    server.socket = context.wrap_socket(server.socket, server_side=True)
    return server


__all__ = ["create_bootstrap_server"]
