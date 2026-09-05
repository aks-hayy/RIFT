"""Transport-neutral discovery aggregation for the RIFT mesh controller."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable, Iterable, Protocol

from .contracts import NodeSighting


class DiscoveryProvider(Protocol):
    name: str

    def discover(self) -> Iterable[NodeSighting]: ...


@dataclass
class StaticDiscoveryProvider:
    """Deterministic provider used by the mesh laboratory and contract tests."""

    name: str
    sightings: list[NodeSighting]

    def discover(self) -> Iterable[NodeSighting]:
        return tuple(self.sightings)


class DiscoveryManager:
    def __init__(
        self,
        providers: Iterable[DiscoveryProvider] = (),
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        provider_list = tuple(providers)
        self._providers = {provider.name: provider for provider in provider_list}
        if len(self._providers) != len(provider_list):
            raise ValueError("discovery provider names must be unique")
        self._clock = clock
        self._sightings: dict[str, NodeSighting] = {}
        self._diagnostics: dict[str, dict[str, object]] = {
            name: {"provider": name, "scan_count": 0, "last_error": None, "last_result_count": 0}
            for name in self._providers
        }

    def register(self, provider: DiscoveryProvider, *, replace: bool = False) -> None:
        if provider.name in self._providers and not replace:
            raise ValueError(f"discovery provider is already registered: {provider.name}")
        self._providers[provider.name] = provider
        self._diagnostics[provider.name] = {
            "provider": provider.name,
            "scan_count": 0,
            "last_error": None,
            "last_result_count": 0,
        }

    def scan(self, provider_names: Iterable[str] | None = None) -> list[NodeSighting]:
        now = float(self._clock())
        selected = list(provider_names) if provider_names is not None else sorted(self._providers)
        unknown = [name for name in selected if name not in self._providers]
        if unknown:
            raise ValueError(f"unknown discovery providers: {', '.join(sorted(unknown))}")
        for name in selected:
            provider = self._providers[name]
            diagnostic = self._diagnostics[name]
            diagnostic["scan_count"] = int(diagnostic["scan_count"]) + 1
            try:
                found = list(provider.discover())
                diagnostic["last_error"] = None
                diagnostic["last_result_count"] = len(found)
            except Exception as exc:
                diagnostic["last_error"] = str(exc)
                diagnostic["last_result_count"] = 0
                continue
            for sighting in found:
                if sighting.is_expired(now):
                    continue
                previous = self._sightings.get(sighting.sighting_id)
                if previous is None or sighting.observed_at >= previous.observed_at:
                    self._sightings[sighting.sighting_id] = sighting
        return self.list_sightings()

    def list_sightings(self) -> list[NodeSighting]:
        now = float(self._clock())
        expired = [key for key, value in self._sightings.items() if value.is_expired(now)]
        for key in expired:
            del self._sightings[key]
        return sorted(self._sightings.values(), key=lambda item: (item.node_hint, item.sighting_id))

    def get(self, sighting_id: str) -> NodeSighting:
        for sighting in self.list_sightings():
            if sighting.sighting_id == sighting_id:
                return sighting
        raise KeyError(f"unknown or expired node sighting: {sighting_id}")

    def provider_diagnostics(self) -> list[dict[str, object]]:
        return [dict(self._diagnostics[name]) for name in sorted(self._diagnostics)]


__all__ = ["DiscoveryManager", "DiscoveryProvider", "StaticDiscoveryProvider"]
