"""Sustained resource signals with safe defaults and hysteresis."""

from __future__ import annotations

from typing import Any, ClassVar


class ResourcePolicy:
    DEFAULTS: ClassVar[dict[str, tuple[float, float, float]]] = {
        "cpu_temperature_c": (85.0, 95.0, 5.0),
        "gpu_temperature_c": (80.0, 90.0, 5.0),
        "host_ram_pressure_percent": (85.0, 95.0, 5.0),
        "gpu_vram_pressure_percent": (90.0, 97.0, 5.0),
        "disk_pressure_percent": (90.0, 95.0, 5.0),
    }

    def __init__(self, *, warning_dwell_seconds: float = 30.0, critical_dwell_seconds: float = 10.0, clear_dwell_seconds: float = 60.0, **overrides: float) -> None:
        self.warning_dwell_seconds = float(warning_dwell_seconds)
        self.critical_dwell_seconds = float(critical_dwell_seconds)
        self.clear_dwell_seconds = float(clear_dwell_seconds)
        self.thresholds = dict(self.DEFAULTS)
        for key, values in list(self.thresholds.items()):
            warning = overrides.get(f"warning_{key}")
            critical = overrides.get(f"critical_{key}")
            hysteresis = overrides.get(f"hysteresis_{key}")
            self.thresholds[key] = (float(warning if warning is not None else values[0]), float(critical if critical is not None else values[1]), float(hysteresis if hysteresis is not None else values[2]))
        self._state: dict[str, dict[str, Any]] = {}

    def evaluate(self, sample: dict[str, Any], *, observed_at: float) -> list[dict[str, Any]]:
        signals = []
        for metric, (warning, critical, hysteresis) in self.thresholds.items():
            value = sample.get(metric)
            if not isinstance(value, (int, float)):
                continue
            state = self._state.setdefault(metric, {"severity": None, "above_since": None, "clear_since": None})
            level = "critical" if float(value) >= critical else "warning" if float(value) >= warning else None
            if level:
                state["clear_since"] = None
                if state["above_since"] is None:
                    state["above_since"] = float(observed_at)
                dwell = self.critical_dwell_seconds if level == "critical" else self.warning_dwell_seconds
                if state["severity"] != level and float(observed_at) - float(state["above_since"]) >= dwell:
                    state["severity"] = level
                    signals.append({"severity": level, "resource": metric, "value": float(value), "threshold": critical if level == "critical" else warning, "reason": f"{metric} remained above {level} threshold for {dwell:g}s", "confidence": "measured"})
            elif state["severity"]:
                clear_at = float(observed_at) if state["clear_since"] is None else float(state["clear_since"])
                if state["clear_since"] is None:
                    state["clear_since"] = clear_at
                if float(value) <= warning - hysteresis and float(observed_at) - clear_at >= self.clear_dwell_seconds:
                    signals.append({"severity": "clear", "resource": metric, "value": float(value), "threshold": warning - hysteresis, "reason": f"{metric} returned below hysteresis clear threshold", "confidence": "measured"})
                    state.update({"severity": None, "above_since": None, "clear_since": None})
            else:
                state["above_since"] = None
        return signals


__all__ = ["ResourcePolicy"]
