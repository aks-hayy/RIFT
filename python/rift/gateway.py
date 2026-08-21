"""RIFT OpenAI-compatible gateway and policy enforcement layer."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import math
import os
from pathlib import Path
import re
import socket
import secrets
import threading
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid

from .orchestrator import RiftOrchestrator
from .rift_yaml import read_yaml
from .runtime_paths import RiftPaths


JsonDict = dict[str, Any]
OrchestratorFactory = Callable[[], RiftOrchestrator]
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_RETRYABLE_UPSTREAM_STATUS = {502, 503, 504}
_OPENAI_PATHS = {
    "/v1/chat/completions",
    "/v1/completions",
    "/v1/embeddings",
    "/v1/models",
}


class ApiKeyStore:
    """Hash-only API key store with create, revoke, and rotation operations."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def list(self) -> JsonDict:
        payload = self._read()
        keys = []
        for item in payload.get("keys", []):
            keys.append({key: value for key, value in item.items() if key != "sha256"})
        return {"keys": keys, "count": len(keys), "path": str(self.path)}

    def create(self, *, label: str, quota: JsonDict | None = None) -> JsonDict:
        if not str(label).strip():
            raise ValueError("API key label is required")
        secret = f"rift_{secrets.token_urlsafe(32)}"
        key_id = f"key_{secrets.token_hex(8)}"
        record = {
            "id": key_id,
            "label": str(label).strip(),
            "sha256": self._digest(secret),
            "fingerprint": self._digest(secret)[:12],
            "created_unix_seconds": time.time(),
            "revoked_unix_seconds": None,
            "quota": dict(quota or {}),
        }
        with self._lock:
            payload = self._read()
            payload.setdefault("keys", []).append(record)
            self._write(payload)
        return {
            "created": True,
            "id": key_id,
            "label": record["label"],
            "secret": secret,
            "fingerprint": record["fingerprint"],
            "warning": "The plaintext key is returned once and is never stored by RIFT.",
        }

    def revoke(self, key_id: str) -> JsonDict:
        changed = False
        with self._lock:
            payload = self._read()
            for item in payload.get("keys", []):
                if item.get("id") == key_id and not item.get("revoked_unix_seconds"):
                    item["revoked_unix_seconds"] = time.time()
                    changed = True
            if changed:
                self._write(payload)
        return {"id": key_id, "revoked": changed}

    def rotate(self, key_id: str) -> JsonDict:
        payload = self._read()
        existing = next((item for item in payload.get("keys", []) if item.get("id") == key_id), None)
        if existing is None:
            raise ValueError(f"API key does not exist: {key_id}")
        self.revoke(key_id)
        created = self.create(label=f"{existing.get('label') or key_id} (rotated)", quota=existing.get("quota"))
        return {"rotated": True, "old_id": key_id, "new": created}

    def verify(self, secret: str) -> bool:
        if not secret:
            return False
        digest = self._digest(secret)
        for item in self._read().get("keys", []):
            if item.get("revoked_unix_seconds"):
                continue
            if secrets.compare_digest(str(item.get("sha256") or ""), digest):
                return True
        return False

    def active(self) -> bool:
        return any(not item.get("revoked_unix_seconds") for item in self._read().get("keys", []))

    def _read(self) -> JsonDict:
        if not self.path.is_file():
            return {"schema_version": 1, "keys": []}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"schema_version": 1, "keys": []}
        return payload if isinstance(payload, dict) else {"schema_version": 1, "keys": []}

    def _write(self, payload: JsonDict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self.path)

    @staticmethod
    def _digest(secret: str) -> str:
        return hashlib.sha256(secret.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class GatewayPolicy:
    enabled: bool = True
    service_name: str = "chat"
    fallback_services: tuple[str, ...] = ()
    host: str = "127.0.0.1"
    port: int = 11734
    request_timeout_seconds: float = 120.0
    max_concurrent_requests: int = 2
    requests_per_minute: int = 60
    burst_requests_per_second: int = 4
    max_prompt_tokens: int = 8192
    max_completion_tokens: int = 1024
    max_total_tokens: int = 9216
    max_body_bytes: int = 4 * 1024 * 1024
    api_key_env: str = "RIFT_GATEWAY_API_KEYS"
    cors_origins: tuple[str, ...] = ()

    @classmethod
    def from_mapping(
        cls,
        payload: JsonDict | None,
        *,
        service_name: str = "chat",
        overrides: JsonDict | None = None,
    ) -> "GatewayPolicy":
        values = dict(payload or {})
        values.update({key: value for key, value in (overrides or {}).items() if value is not None})
        fallbacks = values.get("fallback_services") or ()
        if isinstance(fallbacks, str):
            fallbacks = (fallbacks,)
        cors_origins = values.get("cors_origins") or ()
        if isinstance(cors_origins, str):
            cors_origins = (cors_origins,)
        policy = cls(
            enabled=bool(values.get("enabled", True)),
            service_name=str(values.get("service_name") or service_name),
            fallback_services=tuple(str(item) for item in fallbacks if str(item).strip()),
            host=str(values.get("host") or "127.0.0.1"),
            port=int(values.get("port", 11734)),
            request_timeout_seconds=float(values.get("request_timeout_seconds", 120.0)),
            max_concurrent_requests=int(values.get("max_concurrent_requests", 2)),
            requests_per_minute=int(values.get("requests_per_minute", 60)),
            burst_requests_per_second=int(values.get("burst_requests_per_second", 4)),
            max_prompt_tokens=int(values.get("max_prompt_tokens", 8192)),
            max_completion_tokens=int(values.get("max_completion_tokens", 1024)),
            max_total_tokens=int(values.get("max_total_tokens", 9216)),
            max_body_bytes=int(values.get("max_body_bytes", 4 * 1024 * 1024)),
            api_key_env=str(values.get("api_key_env") or "RIFT_GATEWAY_API_KEYS"),
            cors_origins=tuple(str(item) for item in cors_origins if str(item).strip()),
        )
        policy.validate()
        return policy

    def validate(self) -> None:
        if not self.service_name:
            raise ValueError("gateway service_name is required")
        if not 1 <= self.port <= 65535:
            raise ValueError("gateway port must be between 1 and 65535")
        if self.request_timeout_seconds <= 0.0:
            raise ValueError("gateway request_timeout_seconds must be positive")
        if self.max_concurrent_requests <= 0:
            raise ValueError("gateway max_concurrent_requests must be positive")
        if self.requests_per_minute < 0 or self.burst_requests_per_second < 0:
            raise ValueError("gateway rate limits cannot be negative")
        if min(self.max_prompt_tokens, self.max_completion_tokens, self.max_total_tokens) <= 0:
            raise ValueError("gateway token limits must be positive")
        if self.max_total_tokens < self.max_completion_tokens:
            raise ValueError("gateway max_total_tokens cannot be smaller than max_completion_tokens")
        if self.max_body_bytes <= 0:
            raise ValueError("gateway max_body_bytes must be positive")


@dataclass
class GatewayResponse:
    status: int
    content_type: str
    backend_service: str | None
    backend_url: str | None
    body: bytes | None = None
    stream: Any | None = None
    fallback_count: int = 0
    error: str | None = None


class SlidingWindowLimiter:
    def __init__(self, requests_per_minute: int, burst_per_second: int) -> None:
        self.requests_per_minute = requests_per_minute
        self.burst_per_second = burst_per_second
        self._minute: dict[str, deque[float]] = defaultdict(deque)
        self._second: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, identity: str, *, now: float | None = None) -> tuple[bool, float]:
        current = time.monotonic() if now is None else float(now)
        with self._lock:
            minute = self._minute[identity]
            second = self._second[identity]
            while minute and current - minute[0] >= 60.0:
                minute.popleft()
            while second and current - second[0] >= 1.0:
                second.popleft()
            waits = []
            if self.requests_per_minute > 0 and len(minute) >= self.requests_per_minute:
                waits.append(max(0.001, 60.0 - (current - minute[0])))
            if self.burst_per_second > 0 and len(second) >= self.burst_per_second:
                waits.append(max(0.001, 1.0 - (current - second[0])))
            if waits:
                return False, max(waits)
            minute.append(current)
            second.append(current)
            return True, 0.0


class RiftGatewayRuntime:
    def __init__(
        self,
        *,
        root: str | Path | None = None,
        data_root: str | Path | None = None,
        policy: GatewayPolicy | None = None,
        orchestrator_factory: OrchestratorFactory | None = None,
    ) -> None:
        self.root = Path(root) if root else Path.cwd()
        self.rift_dir = Path(data_root) if data_root is not None else self.root / ".rift"
        self.policy = policy or GatewayPolicy()
        self.orchestrator_factory = orchestrator_factory or (
            lambda: RiftOrchestrator(root=self.root, runtime_root=self.rift_dir)
        )
        self._semaphore = threading.BoundedSemaphore(self.policy.max_concurrent_requests)
        self._limiter = SlidingWindowLimiter(
            self.policy.requests_per_minute,
            self.policy.burst_requests_per_second,
        )
        self.key_store = ApiKeyStore(self.rift_dir / "gateway" / "api_keys.json")
        self._metrics_lock = threading.Lock()
        self._log_lock = threading.Lock()
        self._metrics: JsonDict = {
            "started_unix_seconds": time.time(),
            "requests_total": 0,
            "requests_active": 0,
            "requests_succeeded": 0,
            "requests_failed": 0,
            "rate_limited": 0,
            "concurrency_rejected": 0,
            "authentication_rejected": 0,
            "token_limit_rejected": 0,
            "body_limit_rejected": 0,
            "upstream_failures": 0,
            "fallbacks_used": 0,
            "bytes_received": 0,
            "bytes_sent": 0,
            "latency_seconds_total": 0.0,
            "status_codes": {},
            "backends": {},
            "last_request": None,
        }

    def request_id(self, supplied: str | None) -> str:
        value = str(supplied or "").strip()
        if value and _REQUEST_ID_RE.fullmatch(value):
            return value
        return f"rift-{uuid.uuid4().hex}"

    def api_keys(self) -> set[str]:
        raw = os.environ.get(self.policy.api_key_env, "") if self.policy.api_key_env else ""
        return {item.strip() for item in raw.split(",") if item.strip()}

    def authorize(self, authorization: str | None) -> bool:
        keys = self.api_keys()
        if not keys and not self.key_store.active():
            return True
        value = str(authorization or "")
        token = value[7:].strip() if value.lower().startswith("bearer ") else ""
        return token in keys or self.key_store.verify(token)

    def identity(self, authorization: str | None, client_host: str) -> str:
        source = str(authorization or "").strip() or str(client_host or "unknown")
        return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]

    def rate_limit(self, identity: str) -> tuple[bool, float]:
        return self._limiter.allow(identity)

    def acquire(self) -> bool:
        return self._semaphore.acquire(blocking=False)

    def release(self) -> None:
        self._semaphore.release()

    def validate_payload(self, payload: JsonDict, *, path: str) -> JsonDict:
        prompt_text = self._prompt_text(payload)
        prompt_tokens = self._estimate_tokens(prompt_text)
        completion_tokens = 0
        if path != "/v1/embeddings":
            requested_completion = payload.get("max_completion_tokens", payload.get("max_tokens", 256))
            try:
                completion_tokens = int(requested_completion)
            except (TypeError, ValueError) as exc:
                raise ValueError("max_tokens must be an integer") from exc
            if completion_tokens <= 0:
                raise ValueError("max_tokens must be positive")
        if prompt_tokens > self.policy.max_prompt_tokens:
            raise ValueError(
                f"estimated prompt tokens {prompt_tokens} exceed limit {self.policy.max_prompt_tokens}"
            )
        if completion_tokens > self.policy.max_completion_tokens:
            raise ValueError(
                f"requested completion tokens {completion_tokens} exceed limit "
                f"{self.policy.max_completion_tokens}"
            )
        if prompt_tokens + completion_tokens > self.policy.max_total_tokens:
            raise ValueError(
                f"estimated total tokens {prompt_tokens + completion_tokens} exceed limit "
                f"{self.policy.max_total_tokens}"
            )
        return {
            "prompt_tokens_estimate": prompt_tokens,
            "completion_tokens_requested": completion_tokens,
            "total_tokens_estimate": prompt_tokens + completion_tokens,
            "estimation": "conservative character heuristic; backend tokenizer remains authoritative",
        }

    def routes(self) -> list[JsonDict]:
        state = self.orchestrator_factory().read_state()
        services = state.get("services", {})
        ordered = [self.policy.service_name, *self.policy.fallback_services]
        routes = []
        seen = set()
        for name in ordered:
            if name in seen:
                continue
            seen.add(name)
            service = services.get(name)
            if not isinstance(service, dict):
                continue
            if str(service.get("desired_state") or "running") == "stopped":
                continue
            runtime = service.get("runtime") or {}
            launch_plan = service.get("launch_plan") or {}
            base_url = runtime.get("api_base") or launch_plan.get("api_base")
            if not base_url:
                continue
            routes.append(
                {
                    "service": name,
                    "backend": service.get("backend"),
                    "base_url": str(base_url).rstrip("/"),
                    "status": service.get("status"),
                    "model": (service.get("model") or {}).get("id"),
                }
            )
        return routes

    def proxy(
        self,
        *,
        method: str,
        path: str,
        body: bytes | None,
        request_id: str,
        stream_requested: bool,
    ) -> GatewayResponse:
        routes = self.routes()
        if not routes:
            return GatewayResponse(
                status=HTTPStatus.SERVICE_UNAVAILABLE.value,
                content_type="application/json",
                backend_service=None,
                backend_url=None,
                body=json.dumps({"error": "no RIFT-managed backend route is available"}).encode("utf-8"),
                error="no backend route",
            )
        failures = []
        for index, route in enumerate(routes):
            target = f"{route['base_url']}{path}"
            headers = {
                "Accept": "text/event-stream" if stream_requested else "application/json",
                "Content-Type": "application/json",
                "User-Agent": "RIFT-Gateway/1.0",
                "X-Request-ID": request_id,
            }
            request = Request(target, data=body, headers=headers, method=method)
            try:
                response = urlopen(request, timeout=self.policy.request_timeout_seconds)
            except HTTPError as exc:
                status = int(exc.code)
                if status in _RETRYABLE_UPSTREAM_STATUS and index + 1 < len(routes):
                    failures.append({"service": route["service"], "status": status})
                    exc.close()
                    continue
                error_body = exc.read(self.policy.max_body_bytes)
                content_type = exc.headers.get("Content-Type", "application/json")
                exc.close()
                return GatewayResponse(
                    status=status,
                    content_type=content_type,
                    backend_service=str(route["service"]),
                    backend_url=target,
                    body=error_body,
                    fallback_count=index,
                    error=f"upstream HTTP {status}",
                )
            except (URLError, TimeoutError, socket.timeout, OSError) as exc:
                failures.append({"service": route["service"], "error": str(exc)})
                if index + 1 < len(routes):
                    continue
                reason = getattr(exc, "reason", None)
                timed_out = isinstance(exc, (TimeoutError, socket.timeout)) or isinstance(
                    reason, (TimeoutError, socket.timeout)
                )
                return GatewayResponse(
                    status=(
                        HTTPStatus.GATEWAY_TIMEOUT.value
                        if timed_out
                        else HTTPStatus.BAD_GATEWAY.value
                    ),
                    content_type="application/json",
                    backend_service=str(route["service"]),
                    backend_url=target,
                    body=json.dumps(
                        {"error": "all backend routes failed", "attempts": failures}
                    ).encode("utf-8"),
                    fallback_count=index,
                    error=str(exc),
                )
            status = int(response.status)
            content_type = response.headers.get("Content-Type", "application/json")
            is_stream = stream_requested or content_type.lower().startswith("text/event-stream")
            if is_stream:
                return GatewayResponse(
                    status=status,
                    content_type=content_type,
                    backend_service=str(route["service"]),
                    backend_url=target,
                    stream=response,
                    fallback_count=index,
                )
            response_body = response.read(self.policy.max_body_bytes + 1)
            response.close()
            if len(response_body) > self.policy.max_body_bytes:
                return GatewayResponse(
                    status=HTTPStatus.BAD_GATEWAY.value,
                    content_type="application/json",
                    backend_service=str(route["service"]),
                    backend_url=target,
                    body=json.dumps({"error": "upstream response exceeded gateway body limit"}).encode("utf-8"),
                    fallback_count=index,
                    error="upstream response body too large",
                )
            return GatewayResponse(
                status=status,
                content_type=content_type,
                backend_service=str(route["service"]),
                backend_url=target,
                body=response_body,
                fallback_count=index,
            )
        return GatewayResponse(
            status=HTTPStatus.BAD_GATEWAY.value,
            content_type="application/json",
            backend_service=None,
            backend_url=None,
            body=json.dumps({"error": "no backend route completed"}).encode("utf-8"),
            error="routing exhausted",
        )

    def begin_request(self, body_bytes: int) -> None:
        with self._metrics_lock:
            self._metrics["requests_total"] += 1
            self._metrics["requests_active"] += 1
            self._metrics["bytes_received"] += int(body_bytes)

    def reject(
        self,
        kind: str,
        *,
        status: int,
        request_id: str,
        method: str,
        path: str,
        identity: str,
        error: str,
    ) -> None:
        record = {
            "created_unix_seconds": time.time(),
            "request_id": request_id,
            "method": method,
            "path": path,
            "identity_hash": identity,
            "status": status,
            "latency_seconds": 0.0,
            "bytes_sent": 0,
            "backend_service": None,
            "fallback_count": 0,
            "tokens": None,
            "error": error,
        }
        with self._metrics_lock:
            self._metrics["requests_total"] += 1
            self._metrics["requests_failed"] += 1
            self._metrics[kind] = int(self._metrics.get(kind) or 0) + 1
            status_codes = self._metrics["status_codes"]
            status_codes[str(status)] = int(status_codes.get(str(status)) or 0) + 1
            self._metrics["last_request"] = record
            self._persist_metrics_locked()
        self._append_request_log(record)

    def finish_request(
        self,
        *,
        request_id: str,
        method: str,
        path: str,
        identity: str,
        status: int,
        latency_seconds: float,
        bytes_sent: int,
        backend_service: str | None,
        fallback_count: int,
        token_estimate: JsonDict | None,
        error: str | None,
    ) -> None:
        record = {
            "created_unix_seconds": time.time(),
            "request_id": request_id,
            "method": method,
            "path": path,
            "identity_hash": identity,
            "status": status,
            "latency_seconds": round(latency_seconds, 6),
            "bytes_sent": bytes_sent,
            "backend_service": backend_service,
            "fallback_count": fallback_count,
            "tokens": token_estimate,
            "error": error,
        }
        with self._metrics_lock:
            self._metrics["requests_active"] = max(0, int(self._metrics["requests_active"]) - 1)
            success = 200 <= status < 400
            key = "requests_succeeded" if success else "requests_failed"
            self._metrics[key] += 1
            if status >= 500:
                self._metrics["upstream_failures"] += 1
            self._metrics["fallbacks_used"] += fallback_count
            self._metrics["bytes_sent"] += bytes_sent
            self._metrics["latency_seconds_total"] += latency_seconds
            status_codes = self._metrics["status_codes"]
            status_codes[str(status)] = int(status_codes.get(str(status)) or 0) + 1
            if backend_service:
                backends = self._metrics["backends"]
                backend = backends.setdefault(backend_service, {"requests": 0, "failures": 0})
                backend["requests"] += 1
                if not success:
                    backend["failures"] += 1
            self._metrics["last_request"] = record
            self._persist_metrics_locked()
        self._append_request_log(record)

    def metrics(self) -> JsonDict:
        with self._metrics_lock:
            metrics = json.loads(json.dumps(self._metrics))
        completed = int(metrics["requests_succeeded"]) + int(metrics["requests_failed"])
        metrics["average_latency_seconds"] = (
            metrics["latency_seconds_total"] / completed if completed else None
        )
        metrics["policy"] = asdict(self.policy)
        metrics["routes"] = self.routes()
        return metrics

    def health(self) -> JsonDict:
        routes = self.routes()
        ready_routes = [
            route
            for route in routes
            if str(route.get("status") or "").lower()
            not in ("crashed", "degraded", "stopped", "unhealthy")
        ]
        return {
            "status": "ok" if ready_routes else "degraded",
            "healthy": bool(ready_routes),
            "gateway": f"http://{self.policy.host}:{self.policy.port}",
            "route_count": len(routes),
            "ready_route_count": len(ready_routes),
            "routes": routes,
            "api_keys": self.key_store.list(),
            "public_exposure_warning": (
                None
                if self.policy.host in ("127.0.0.1", "localhost", "::1")
                else "Gateway is bound beyond loopback. Configure TLS at a trusted reverse proxy."
            ),
        }

    def _persist_metrics_locked(self) -> None:
        path = self.rift_dir / "gateway" / "metrics.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(self._metrics, indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(path)

    def _append_request_log(self, record: JsonDict) -> None:
        path = self.rift_dir / "logs" / "gateway.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, sort_keys=True) + "\n"
        with self._log_lock, path.open("a", encoding="utf-8") as output:
            output.write(line)

    def _prompt_text(self, payload: JsonDict) -> str:
        prompt = payload.get("prompt")
        if isinstance(prompt, str):
            return prompt
        if isinstance(prompt, list):
            return " ".join(str(item) for item in prompt)
        parts: list[str] = []
        messages = payload.get("messages") or []
        if isinstance(messages, list):
            for message in messages:
                if not isinstance(message, dict):
                    continue
                content = message.get("content")
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and isinstance(item.get("text"), str):
                            parts.append(item["text"])
        return "\n".join(parts)

    def _estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        word_floor = len(re.findall(r"\S+", text))
        character_estimate = math.ceil(len(text) / 3.0)
        return max(word_floor, character_estimate)


class RiftGatewayHandler(BaseHTTPRequestHandler):
    runtime: RiftGatewayRuntime
    protocol_version = "HTTP/1.1"
    server_version = "RIFTGateway/1.0"

    def do_OPTIONS(self) -> None:  # noqa: N802
        origin = self.headers.get("Origin")
        if not self._origin_allowed(origin):
            self._send_json(HTTPStatus.FORBIDDEN.value, {"error": "CORS origin is not allowed"}, self.runtime.request_id(None))
            return
        self.send_response(HTTPStatus.NO_CONTENT.value)
        self._send_cors(origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Request-ID")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        request_path = self.path.split("?", 1)[0]
        if request_path == "/health":
            self._send_json(HTTPStatus.OK.value, self.runtime.health(), self.runtime.request_id(None))
            return
        if request_path in ("/metrics", "/api/rift/gateway/metrics"):
            self._send_json(HTTPStatus.OK.value, self.runtime.metrics(), self.runtime.request_id(None))
            return
        if request_path == "/v1/models":
            self._handle_proxy("GET")
            return
        self._send_json(HTTPStatus.NOT_FOUND.value, {"error": "unknown gateway endpoint"}, self.runtime.request_id(None))

    def do_POST(self) -> None:  # noqa: N802
        request_path = self.path.split("?", 1)[0]
        if request_path not in _OPENAI_PATHS or request_path == "/v1/models":
            self._send_json(HTTPStatus.NOT_FOUND.value, {"error": "unknown gateway endpoint"}, self.runtime.request_id(None))
            return
        self._handle_proxy("POST")

    def _handle_proxy(self, method: str) -> None:
        started = time.perf_counter()
        request_id = self.runtime.request_id(self.headers.get("X-Request-ID"))
        authorization = self.headers.get("Authorization")
        identity = self.runtime.identity(authorization, self.client_address[0])
        if not self.runtime.authorize(authorization):
            self.runtime.reject(
                "authentication_rejected",
                status=HTTPStatus.UNAUTHORIZED.value,
                request_id=request_id,
                method=method,
                path=self.path,
                identity=identity,
                error="invalid gateway API key",
            )
            self._send_json(HTTPStatus.UNAUTHORIZED.value, {"error": "invalid gateway API key"}, request_id)
            return
        allowed, retry_after = self.runtime.rate_limit(identity)
        if not allowed:
            self.runtime.reject(
                "rate_limited",
                status=HTTPStatus.TOO_MANY_REQUESTS.value,
                request_id=request_id,
                method=method,
                path=self.path,
                identity=identity,
                error="gateway request rate exceeded",
            )
            self._send_json(
                HTTPStatus.TOO_MANY_REQUESTS.value,
                {"error": "gateway request rate exceeded", "retry_after_seconds": retry_after},
                request_id,
                extra_headers={"Retry-After": str(max(1, math.ceil(retry_after)))},
            )
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length < 0 or length > self.runtime.policy.max_body_bytes:
            self.runtime.reject(
                "body_limit_rejected",
                status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE.value,
                request_id=request_id,
                method=method,
                path=self.path,
                identity=identity,
                error="request body exceeds gateway limit",
            )
            self._send_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE.value,
                {"error": "request body exceeds gateway limit"},
                request_id,
            )
            return
        body = self.rfile.read(length) if length else None
        payload: JsonDict = {}
        token_estimate = None
        if method == "POST":
            try:
                payload = json.loads((body or b"{}").decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("request JSON must be an object")
                token_estimate = self.runtime.validate_payload(
                    payload,
                    path=self.path.split("?", 1)[0],
                )
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                self.runtime.reject(
                    "token_limit_rejected",
                    status=HTTPStatus.BAD_REQUEST.value,
                    request_id=request_id,
                    method=method,
                    path=self.path,
                    identity=identity,
                    error=str(exc),
                )
                self._send_json(HTTPStatus.BAD_REQUEST.value, {"error": str(exc)}, request_id)
                return
        if not self.runtime.acquire():
            self.runtime.reject(
                "concurrency_rejected",
                status=HTTPStatus.TOO_MANY_REQUESTS.value,
                request_id=request_id,
                method=method,
                path=self.path,
                identity=identity,
                error="gateway concurrency limit reached",
            )
            self._send_json(
                HTTPStatus.TOO_MANY_REQUESTS.value,
                {"error": "gateway concurrency limit reached"},
                request_id,
                extra_headers={"Retry-After": "1"},
            )
            return
        self.runtime.begin_request(length)
        result: GatewayResponse | None = None
        bytes_sent = 0
        try:
            try:
                result = self.runtime.proxy(
                    method=method,
                    path=self.path,
                    body=body,
                    request_id=request_id,
                    stream_requested=bool(payload.get("stream", False)),
                )
            except Exception as exc:
                result = GatewayResponse(
                    status=HTTPStatus.BAD_GATEWAY.value,
                    content_type="application/json",
                    backend_service=None,
                    backend_url=None,
                    body=json.dumps({"error": "gateway upstream failure", "detail": str(exc)}).encode("utf-8"),
                    error=str(exc),
                )
            if result.stream is not None:
                bytes_sent = self._send_stream(result, request_id)
            else:
                response_body = result.body or b""
                bytes_sent = len(response_body)
                self._send_bytes(
                    result.status,
                    response_body,
                    result.content_type,
                    request_id,
                    backend_service=result.backend_service,
                )
        finally:
            self.runtime.release()
            if result is not None:
                self.runtime.finish_request(
                    request_id=request_id,
                    method=method,
                    path=self.path,
                    identity=identity,
                    status=result.status,
                    latency_seconds=time.perf_counter() - started,
                    bytes_sent=bytes_sent,
                    backend_service=result.backend_service,
                    fallback_count=result.fallback_count,
                    token_estimate=token_estimate,
                    error=result.error,
                )

    def _send_stream(self, result: GatewayResponse, request_id: str) -> int:
        self.send_response(result.status)
        self.send_header("Content-Type", result.content_type)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("X-Request-ID", request_id)
        if result.backend_service:
            self.send_header("X-RIFT-Backend-Service", result.backend_service)
        self.end_headers()
        self.close_connection = True
        sent = 0
        stream = result.stream
        try:
            while True:
                chunk = stream.read(8192)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
                sent += len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            stream.close()
        return sent

    def _send_json(
        self,
        status: int,
        payload: JsonDict,
        request_id: str,
        *,
        extra_headers: JsonDict | None = None,
    ) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self._send_bytes(
            status,
            body,
            "application/json; charset=utf-8",
            request_id,
            extra_headers=extra_headers,
        )

    def _send_bytes(
        self,
        status: int,
        body: bytes,
        content_type: str,
        request_id: str,
        *,
        backend_service: str | None = None,
        extra_headers: JsonDict | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Request-ID", request_id)
        self._send_cors(self.headers.get("Origin"))
        if backend_service:
            self.send_header("X-RIFT-Backend-Service", backend_service)
        for key, value in (extra_headers or {}).items():
            self.send_header(str(key), str(value))
        self.end_headers()
        self.wfile.write(body)

    def _origin_allowed(self, origin: str | None) -> bool:
        if not origin:
            return True
        allowed = self.runtime.policy.cors_origins
        return "*" in allowed or origin in allowed

    def _send_cors(self, origin: str | None) -> None:
        if origin and self._origin_allowed(origin):
            self.send_header("Access-Control-Allow-Origin", "*" if "*" in self.runtime.policy.cors_origins else origin)
            self.send_header("Vary", "Origin")

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def load_gateway_policy(
    config_path: str | Path = "rift.yaml",
    *,
    service_name: str = "chat",
    overrides: JsonDict | None = None,
) -> GatewayPolicy:
    path = Path(config_path)
    config = read_yaml(path)
    services = config.get("services") if isinstance(config, dict) else None
    if not isinstance(services, dict) or service_name not in services:
        raise ValueError(f"gateway service not found in config: {service_name}")
    service = services[service_name]
    gateway = service.get("gateway") if isinstance(service, dict) else None
    return GatewayPolicy.from_mapping(
        gateway if isinstance(gateway, dict) else {},
        service_name=service_name,
        overrides=overrides,
    )


def create_gateway_server(
    *,
    host: str | None = None,
    port: int | None = None,
    runtime: RiftGatewayRuntime | None = None,
) -> ThreadingHTTPServer:
    runtime = runtime or RiftGatewayRuntime()
    bind_host = host or runtime.policy.host
    bind_port = runtime.policy.port if port is None else int(port)

    class BoundGatewayHandler(RiftGatewayHandler):
        pass

    BoundGatewayHandler.runtime = runtime
    return ThreadingHTTPServer((bind_host, bind_port), BoundGatewayHandler)


def serve_gateway(
    *,
    config_path: str | Path = "rift.yaml",
    service_name: str = "chat",
    host: str | None = None,
    port: int | None = None,
    fallback_services: list[str] | None = None,
) -> None:
    config = Path(config_path).resolve()
    overrides: JsonDict = {"host": host, "port": port}
    if fallback_services is not None:
        overrides["fallback_services"] = fallback_services
    policy = load_gateway_policy(config, service_name=service_name, overrides=overrides)
    if not policy.enabled:
        raise ValueError(f"gateway is disabled for service: {service_name}")
    runtime = RiftGatewayRuntime(
        root=config.parent,
        data_root=RiftPaths.from_environment(cwd=config.parent).home,
        policy=policy,
    )
    server = create_gateway_server(runtime=runtime)
    state_path = runtime.rift_dir / "gateway" / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "status": "running",
        "pid": os.getpid(),
        "host": server.server_address[0],
        "port": server.server_port,
        "service": service_name,
        "fallback_services": list(policy.fallback_services),
        "started_unix_seconds": time.time(),
    }
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    print(f"RIFT gateway listening on http://{server.server_address[0]}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nRIFT gateway stopped")
    finally:
        server.server_close()
        state["status"] = "stopped"
        state["stopped_unix_seconds"] = time.time()
        state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


__all__ = [
    "GatewayPolicy",
    "RiftGatewayRuntime",
    "create_gateway_server",
    "load_gateway_policy",
    "serve_gateway",
]
