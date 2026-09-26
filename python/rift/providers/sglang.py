"""Compatibility import for the folder-owned backend implementation."""

from ..backends.sglang import backend as _implementation

container_runtime_detection = _implementation.container_runtime_detection
wsl_detection = _implementation.wsl_detection


class SglangProvider(_implementation.SglangProvider):
    """Legacy import shim that preserves patchable module-level helpers."""

    def plan_launch(self, *args, **kwargs):
        _implementation.container_runtime_detection = container_runtime_detection
        _implementation.wsl_detection = wsl_detection
        return super().plan_launch(*args, **kwargs)


__all__ = ["SglangProvider"]
