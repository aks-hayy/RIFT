"""Permission-gated host for independently packaged artifact converters."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .contracts import ArtifactVariant, ConversionPlan, JsonDict
from .registry import AdapterRegistry


class ConversionPermissionError(PermissionError):
    pass


class ConverterAdapterHost(AdapterRegistry):
    def plans(
        self,
        *,
        source: ArtifactVariant,
        target_format: str,
        output_path: str | Path,
        options: JsonDict | None = None,
    ) -> list[ConversionPlan]:
        if not target_format.strip():
            raise ValueError("target_format is required")
        target = Path(output_path)
        if not str(target).strip():
            raise ValueError("output_path is required")
        plans: list[ConversionPlan] = []
        for adapter in self.enabled().values():
            compatibility = adapter.can_convert(source=source, target_format=target_format)
            if not compatibility.compatible:
                continue
            plan = adapter.plan_conversion(
                source=source,
                target_format=target_format,
                output_path=str(target),
                options=dict(options or {}),
            )
            if not isinstance(plan, ConversionPlan):
                raise TypeError(f"converter {adapter.manifest.adapter_id} returned an invalid plan")
            if not plan.requires_permission:
                raise ValueError(
                    f"converter {adapter.manifest.adapter_id} must retain an explicit permission gate"
                )
            plans.append(plan)
        plans.sort(key=lambda item: (item.destructive, item.converter_id))
        return plans

    def execute(self, plan: ConversionPlan, *, allow_conversion: bool = False) -> JsonDict:
        if not allow_conversion:
            raise ConversionPermissionError(
                "artifact conversion requires explicit allow_conversion permission"
            )
        adapter = self.get(plan.converter_id)
        if adapter is None:
            raise ValueError(f"converter adapter is unavailable: {plan.converter_id}")
        result = adapter.convert(plan)
        if not isinstance(result, dict):
            raise TypeError(f"converter {plan.converter_id} returned a non-object result")
        return {
            "converter_id": plan.converter_id,
            "target_format": plan.target_format,
            "output_path": plan.output_path,
            "result": result,
        }


def converter_adapter_host(
    *,
    builtins: Iterable[object] = (),
    disabled: Iterable[str] = (),
    load_entry_points: bool = True,
) -> ConverterAdapterHost:
    return ConverterAdapterHost(
        builtins=builtins,
        entry_point_group="rift.converter_adapters",
        disabled=disabled,
        load_entry_points=load_entry_points,
    )


__all__ = [
    "ConversionPermissionError",
    "ConverterAdapterHost",
    "converter_adapter_host",
]
