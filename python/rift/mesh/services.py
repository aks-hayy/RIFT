"""Persistent service and gateway-group identity used by mesh routing."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def _id(value: str, label: str) -> str:
    value = str(value or "").strip()
    if not value or "/" in value or "\\" in value or value in {".", ".."}:
        raise ValueError(f"{label} must be a non-empty path-safe identifier")
    return value


@dataclass(frozen=True)
class ServiceDefinition:
    service_id: str
    model_id: str
    revision: str
    task: str = "chat"
    groups: tuple[str, ...] = field(default_factory=tuple)
    desired_replicas: int = 1
    policy_hash: str = ""

    def __post_init__(self) -> None:
        _id(self.service_id, "service_id")
        if not str(self.model_id).strip() or not str(self.revision).strip():
            raise ValueError("model_id and revision are required")
        if self.desired_replicas < 1:
            raise ValueError("desired_replicas must be positive")
        for group in self.groups:
            _id(group, "group_id")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["groups"] = list(self.groups)
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ServiceDefinition:
        return cls(
            service_id=str(value["service_id"]),
            model_id=str(value["model_id"]),
            revision=str(value["revision"]),
            task=str(value.get("task") or "chat"),
            groups=tuple(str(item) for item in value.get("groups") or ()),
            desired_replicas=int(value.get("desired_replicas") or 1),
            policy_hash=str(value.get("policy_hash") or ""),
        )


@dataclass(frozen=True)
class ServiceGroup:
    group_id: str
    service_ids: tuple[str, ...]
    default_service: str | None = None
    gateway_path: str | None = None

    def __post_init__(self) -> None:
        _id(self.group_id, "group_id")
        if not self.service_ids:
            raise ValueError("service group must contain at least one service")
        for service_id in self.service_ids:
            _id(service_id, "service_id")
        if self.default_service is not None and self.default_service not in self.service_ids:
            raise ValueError("default_service must belong to service_ids")
        if self.gateway_path is not None and not self.gateway_path.startswith("/"):
            raise ValueError("gateway_path must start with '/'")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ServiceGroup:
        return cls(
            group_id=str(value["group_id"]),
            service_ids=tuple(str(item) for item in value.get("service_ids") or ()),
            default_service=(str(value["default_service"]) if value.get("default_service") else None),
            gateway_path=(str(value["gateway_path"]) if value.get("gateway_path") else None),
        )


class ServiceCatalog:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._services: dict[str, ServiceDefinition] = {}
        self._groups: dict[str, ServiceGroup] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            self._services = {
                str(item["service_id"]): ServiceDefinition.from_dict(item)
                for item in payload.get("services", [])
            }
            self._groups = {
                str(item["group_id"]): ServiceGroup.from_dict(item)
                for item in payload.get("groups", [])
            }
        except (OSError, ValueError, TypeError, json.JSONDecodeError, KeyError) as exc:
            raise RuntimeError(f"failed to load service catalog {self.path}: {exc}") from exc

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        pending = self.path.with_suffix(self.path.suffix + ".tmp")
        pending.write_text(
            json.dumps(
                {"schema_version": 1, "services": [x.to_dict() for x in self.list_services()], "groups": [x.to_dict() for x in self.list_groups()]},
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        pending.replace(self.path)

    def upsert_service(self, service: ServiceDefinition) -> ServiceDefinition:
        self._services[service.service_id] = service
        self._save()
        return service

    def upsert_group(self, group: ServiceGroup) -> ServiceGroup:
        missing = [item for item in group.service_ids if item not in self._services]
        if missing:
            raise KeyError(f"unknown services in group: {', '.join(missing)}")
        self._groups[group.group_id] = group
        self._save()
        return group

    def list_services(self) -> list[ServiceDefinition]:
        return [self._services[key] for key in sorted(self._services)]

    def list_groups(self) -> list[ServiceGroup]:
        return [self._groups[key] for key in sorted(self._groups)]

    def resolve(self, group_id: str, service_id: str | None = None) -> ServiceDefinition:
        group = self._groups.get(_id(group_id, "group_id"))
        if group is None:
            raise KeyError(f"unknown service group: {group_id}")
        selected = service_id or group.default_service
        if selected is None:
            selected = group.service_ids[0]
        if selected not in group.service_ids:
            raise KeyError(f"service {selected} is not a member of group {group_id}")
        return self._services[selected]


__all__ = ["ServiceCatalog", "ServiceDefinition", "ServiceGroup"]
