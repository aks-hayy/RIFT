"""Policy-balanced route selection over a measured RIFT capability graph."""

from __future__ import annotations

from .contracts import (
    InferenceIntent,
    MeshGraph,
    PrivacyPolicy,
    RouteCandidate,
    RouteDecision,
    TrustState,
)


class NoRouteError(RuntimeError):
    pass


class RoutePlanner:
    def resolve(self, *, graph: MeshGraph, intent: InferenceIntent) -> RouteDecision:
        if intent.source_node_id not in graph.nodes:
            raise NoRouteError(f"source node is unknown: {intent.source_node_id}")
        candidates: list[RouteCandidate] = []
        rejected: list[dict[str, object]] = []
        privacy_rejected = False
        for node_id, node in graph.nodes.items():
            reasons: list[str] = []
            if node.trust_state != TrustState.ACTIVE:
                rejected.append({"node_id": node_id, "reason": "node is not trusted and active"})
                continue
            if not node.healthy:
                rejected.append({"node_id": node_id, "reason": "node is unhealthy"})
                continue
            if intent.privacy == PrivacyPolicy.LOCAL_ONLY and node_id != intent.source_node_id:
                privacy_rejected = True
                rejected.append({"node_id": node_id, "reason": "privacy policy requires local execution"})
                continue
            link = graph.link(intent.source_node_id, node_id)
            if link is None or link.loss_ratio >= 1.0:
                rejected.append({"node_id": node_id, "reason": "node is unreachable"})
                continue
            for offer in node.offers:
                if offer.task != intent.task:
                    continue
                if offer.context_tokens < intent.minimum_context_tokens:
                    continue
                if offer.quality_score < intent.minimum_quality_score:
                    continue
                if offer.local_only and node_id != intent.source_node_id:
                    continue
                predicted = offer.first_token_ms + link.rtt_p95_ms + node.queue_depth * 120.0
                score = predicted - offer.quality_score * 2.0
                if node_id == intent.source_node_id:
                    score -= 1000.0
                    reasons.append("suitable local execution avoids network dependency")
                else:
                    reasons.append("remote node satisfies capability and privacy constraints")
                reasons.append(f"predicted first token {predicted:.1f} ms")
                candidates.append(
                    RouteCandidate(
                        node_id=node_id,
                        offer_id=offer.offer_id,
                        execution_mode="local" if node_id == intent.source_node_id else "remote",
                        score=round(score, 3),
                        predicted_first_token_ms=round(predicted, 3),
                        reasons=tuple(reasons),
                    )
                )
        candidates.sort(key=lambda item: (item.score, item.node_id, item.offer_id))
        if not candidates:
            suffix = " because privacy policy requires local execution" if privacy_rejected else ""
            raise NoRouteError(f"no feasible inference route{suffix}")
        return RouteDecision(
            selected=candidates[0],
            fallbacks=tuple(candidates[1:4]),
            rejected=tuple(rejected),
            evidence=graph.evidence,
        )


__all__ = ["NoRouteError", "RoutePlanner"]

