"""Small YAML helpers for RIFT configuration files.

RIFT writes JSON-compatible YAML so the core package does not require a YAML
dependency to function. If PyYAML is installed, hand-written YAML is accepted as
well.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def dumps_yaml(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=False) + "\n"


def loads_yaml(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as json_error:
        try:
            import yaml  # type: ignore[import-not-found]
        except Exception as exc:  # pragma: no cover - depends on optional package
            raise ValueError(
                "rift.yaml must be JSON-compatible YAML unless PyYAML is installed"
            ) from exc
        data = yaml.safe_load(text)
        return {} if data is None else data


def read_yaml(path: str | Path) -> Any:
    return loads_yaml(Path(path).read_text(encoding="utf-8"))


def write_yaml(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dumps_yaml(payload), encoding="utf-8")
