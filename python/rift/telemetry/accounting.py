"""Conservative service energy and cost accounting."""

from __future__ import annotations

from typing import Any


def energy_cost(joules: float | None, *, price_per_kwh: float | None) -> float | None:
    if joules is None or price_per_kwh is None:
        return None
    return max(0.0, float(joules)) / 3_600_000.0 * max(0.0, float(price_per_kwh))


def session_costs(report: dict[str, Any], *, electricity_price_per_kwh: float | None = None, compute_cost_per_node_hour: float | None = None) -> dict[str, Any]:
    energy = ((report.get("metrics") or {}).get("gpu_energy_joules") or {}).get("estimated")
    duration = float(report.get("duration_seconds") or 0.0)
    electricity_cost = energy_cost(energy, price_per_kwh=electricity_price_per_kwh)
    compute_cost = None if compute_cost_per_node_hour is None else duration / 3600.0 * max(0.0, float(compute_cost_per_node_hour))
    cost_components = [value for value in (electricity_cost, compute_cost) if value is not None]
    return {
        "energy_joules": energy,
        "electricity_cost": electricity_cost,
        "compute_cost": compute_cost,
        "total_cost": sum(cost_components) if cost_components else None,
        "currency": "configured" if electricity_price_per_kwh is not None or compute_cost_per_node_hour is not None else None,
        "basis": "measured device power where available; otherwise unavailable",
    }


__all__ = ["energy_cost", "session_costs"]
