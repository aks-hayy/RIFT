"""Explicit owner grants controlling how an enrolled node participates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class ParticipationMode(str, Enum):
    ACCESS_ONLY = "ACCESS_ONLY"
    SHARE_COMPUTE = "SHARE_COMPUTE"


@dataclass(frozen=True)
class ParticipationGrant:
    mode: ParticipationMode = ParticipationMode.ACCESS_ONLY
    allow_download: bool = False
    allow_install: bool = False
    allow_launch: bool = False
    allow_inference: bool = False
    max_concurrency: int = 1
    max_memory_bytes: int | None = None
    expires_at: float | None = None

    def validate(self) -> ParticipationGrant:
        mode = ParticipationMode(self.mode)
        if self.max_concurrency < 1:
            raise ValueError("max_concurrency must be positive")
        if self.max_memory_bytes is not None and self.max_memory_bytes < 0:
            raise ValueError("max_memory_bytes must be nonnegative")
        if mode is ParticipationMode.ACCESS_ONLY and any(
            (self.allow_download, self.allow_install, self.allow_launch, self.allow_inference)
        ):
            raise ValueError("access-only grants cannot enable compute")
        if mode is ParticipationMode.SHARE_COMPUTE and not any(
            (self.allow_download, self.allow_install, self.allow_launch, self.allow_inference)
        ):
            raise ValueError("share-compute grants must enable an explicit capability")
        return self

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        value = asdict(self)
        value["mode"] = self.mode.value
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> ParticipationGrant:
        value = dict(value or {})
        grant = cls(
            mode=ParticipationMode(str(value.get("mode") or ParticipationMode.ACCESS_ONLY.value)),
            allow_download=bool(value.get("allow_download", False)),
            allow_install=bool(value.get("allow_install", False)),
            allow_launch=bool(value.get("allow_launch", False)),
            allow_inference=bool(value.get("allow_inference", False)),
            max_concurrency=int(value.get("max_concurrency") or 1),
            max_memory_bytes=(int(value["max_memory_bytes"]) if value.get("max_memory_bytes") is not None else None),
            expires_at=(float(value["expires_at"]) if value.get("expires_at") is not None else None),
        )
        return grant.validate()


__all__ = ["ParticipationGrant", "ParticipationMode"]
