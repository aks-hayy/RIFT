"""Gateway-side service-group resolution and bounded mesh admission."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .admission import RequestCoordinator
from .services import ServiceCatalog


class MeshGatewayRouter:
    def __init__(self, controller: Any, catalog: ServiceCatalog, *, wait_timeout_seconds: float = 30.0):
        self.controller = controller
        self.catalog = catalog
        self.admission = RequestCoordinator(wait_timeout_seconds=wait_timeout_seconds)

    def admit(
        self,
        request_id: str,
        *,
        group_id: str,
        source_node_id: str,
        service_id: str | None = None,
        prompt_metadata: dict[str, object] | None = None,
    ) -> dict[str, object]:
        service = self.catalog.resolve(group_id, service_id)
        metadata = dict(prompt_metadata or {})
        policy_hash = service.policy_hash or hashlib.sha256(
            json.dumps(service.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        route = self.controller.resolve_route(
            {
                "source_node_id": source_node_id,
                "service_id": service.service_id,
                "model_id": service.model_id,
                "task": service.task,
                "minimum_context_tokens": int(metadata.get("minimum_context_tokens") or 1),
                "privacy": str(metadata.get("privacy") or "MESH_ALLOWED"),
                "minimum_quality_score": float(metadata.get("minimum_quality_score") or 0),
                "policy_hash": policy_hash,
                "lease_ttl_seconds": min(int(metadata.get("lease_ttl_seconds") or 30), 30),
            }
        )
        decision = dict(route.get("decision") or {})
        selected = dict(decision.get("selected") or {})
        fallback_ids = [str(item.get("node_id")) for item in decision.get("fallbacks") or [] if isinstance(item, dict)]
        admission = self.admission.submit(request_id, [str(selected.get("node_id") or ""), *fallback_ids])
        return {
            **admission,
            "group_id": group_id,
            "service_id": service.service_id,
            "model_id": service.model_id,
            "route": route,
        }

    def fail(self, request_id: str, node_id: str, reason: str) -> dict[str, object]:
        return self.admission.fail(request_id, node_id, reason)

    def complete(self, request_id: str, response: object) -> dict[str, object]:
        return self.admission.complete(request_id, response)

    def expire(self, request_id: str) -> dict[str, object]:
        return self.admission.expire(request_id)


class MeshGatewayProxy:
    """Execute one OpenAI-shaped request over a resolved mesh route."""

    def __init__(self, router: MeshGatewayRouter):
        self.router = router

    def execute(
        self,
        body: dict[str, object],
        *,
        request_id: str,
        group_id: str,
        source_node_id: str,
        send,
    ) -> dict[str, object]:
        model = str(body.get("model") or "")
        prompt_metadata = {"minimum_context_tokens": int(body.get("max_context_tokens") or 1)}
        admitted = self.router.admit(
            request_id,
            group_id=group_id,
            source_node_id=source_node_id,
            prompt_metadata=prompt_metadata,
        )
        route = admitted["route"]
        while admitted.get("status") == "DISPATCHING":
            node_id = str(admitted["node_id"])
            try:
                response = send(node_id, body, route.get("route_grant") or route.get("lease", {}).get("bearer_token"))
            except Exception as exc:  # noqa: BLE001 - transport adapters surface arbitrary request failures
                admitted = {**self.router.fail(request_id, node_id, str(exc)), "route": route}
                continue
            self.router.complete(request_id, response)
            return {"status_code": 200, "body": response, "node_id": node_id, "model": model}
        if admitted.get("status") == "WAITING_RECOVERY":
            return {"status_code": 503, "body": {"error": "all mesh executors are unavailable", "retry_after_seconds": 30}}
        return {"status_code": 504, "body": {"error": "mesh admission deadline expired"}}


__all__ = ["MeshGatewayProxy", "MeshGatewayRouter"]
