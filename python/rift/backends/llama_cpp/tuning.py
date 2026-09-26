"""llama.cpp-owned tuning policy.

Only the coordinator is shared.  Parameter proposal and backend diagnostics
live beside the serving implementation so adding a backend does not require
editing a central registry.
"""
from __future__ import annotations

import inspect

from ...tuning_base import BackendTuningAdapter


class LlamaCppTuningAdapter(BackendTuningAdapter):
    backend = "llama.cpp"

    def probe(self, deployment):
        return {
            "backend": self.backend,
            "profiles": ["speed", "cost"],
            "qualification": "legacy_local_evidence; shared coordinator requires qualification",
            "groups": ["placement", "batching", "cpu", "kv_precision", "execution", "speculation"],
            "parameters": [],
            "schema_version": 1,
        }

    def propose(self, *, launch_plan, hardware, contract):
        fn = getattr(
            self.provider,
            "tuning_space",
            self.provider.tune_candidates if hasattr(self.provider, "tune_candidates") else None,
        )
        if fn is None:
            return []
        kwargs = {"launch_plan": launch_plan, "hardware": hardware}
        if "contract" in inspect.signature(fn).parameters:
            kwargs["contract"] = contract
        return fn(**kwargs)


def create_tuning_adapter(provider):
    return LlamaCppTuningAdapter(provider)


__all__ = ["LlamaCppTuningAdapter", "create_tuning_adapter"]
