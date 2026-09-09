"""Shared tuning transaction; serving lifecycle remains in the orchestrator."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable
from .tuning_engine import TuningContract, TuningStore, candidate_is_allowed, select_profile_winner
from .tuning_accuracy import AccuracySuite, score_accuracy_suite
from .tuning_adapters import tuning_adapter

JsonDict = dict[str, Any]


class TuningCoordinatorMixin:
    def profiled_tune_service(
        self,
        *,
        service_name: str,
        profile: str,
        write: bool = True,
        allow_restart: bool = False,
        no_apply: bool = False,
        dry_run: bool = False,
        candidate_limit: int = 24,
        warmup_runs: int = 1,
        repeats: int = 3,
        requests_per_window: int = 1,
        startup_timeout_seconds: float = 180.0,
        prompt: str = "Reply briefly: what is one benefit of local inference?",
        max_tokens: int = 32,
        budget_seconds: float | None = None,
        target_tokens_per_second: float = 100.0,
        accuracy_tolerance: float = 0.05,
        accuracy_case_tolerance: float = 0.15,
        retain_accuracy_responses: bool = False,
        kv_precision_search: bool = True,
        ngram_speculation: bool | None = None,
        accuracy_runner: Callable[[JsonDict, AccuracySuite], JsonDict] | None = None,
        measurement_runner: Callable[[JsonDict, str], JsonDict] | None = None,
        cancel_check: Callable[[], bool] | None = None,
        operation_id: str | None = None,
        progress: Callable[[str, str, float | None, JsonDict | None], None] | None = None,
        usage: str | None = None,
        parent_run_id: str | None = None,
        contract_hash: str | None = None,
    ) -> JsonDict:
        """Run a backend-neutral, profile-aware tuning transaction.

        The legacy plan/live tuner remains available through ``tune_service``.
        This path adds a durable run journal, immutable model/precision locks,
        paired reliability gates, and a monitoring-safe maintenance marker.
        ``measurement_runner`` is intentionally injectable for deterministic
        controller tests; production runs use the local benchmark and energy
        sampler below.
        """

        profile = str(profile or "").strip().lower()
        if profile not in {"speed", "cost"}:
            raise ValueError("profile must be speed or cost")
        if candidate_limit <= 0:
            raise ValueError("candidate_limit must be positive")
        if warmup_runs < 0 or repeats <= 0:
            raise ValueError("warmup_runs cannot be negative and repeats must be positive")
        if requests_per_window <= 0:
            raise ValueError("requests_per_window must be positive")
        if startup_timeout_seconds <= 0.0:
            raise ValueError("startup_timeout_seconds must be positive")
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if target_tokens_per_second <= 0 or accuracy_tolerance < 0 or accuracy_case_tolerance < 0:
            raise ValueError("target and accuracy tolerances must be valid")
        if not allow_restart and not dry_run:
            return {
                "available": False,
                "applied": False,
                "outcome": "permission_required",
                "service": service_name,
                "profile": profile,
                "reason": "profiled tuning uses a maintenance window and requires --allow-restart",
                "required_permission": "allow_restart",
            }

        state = self.read_state()
        service = (state.get("services") or {}).get(service_name)
        if not isinstance(service, dict):
            return {
                "available": False,
                "applied": False,
                "outcome": "unavailable",
                "service": service_name,
                "profile": profile,
                "reason": "service is not deployed",
            }
        backend = str(service.get("backend") or "")
        provider = self.providers.get(backend)
        adapter = tuning_adapter(backend, provider) if provider is not None else None
        if adapter is None:
            return {
                "available": False,
                "applied": False,
                "outcome": "unavailable",
                "service": service_name,
                "profile": profile,
                "reason": "No qualified tuning adapter is registered for this service backend",
                "backend": backend,
            }
        provider = self.providers.get(backend)
        if provider is None:
            return {
                "available": False,
                "applied": False,
                "outcome": "unavailable",
                "service": service_name,
                "profile": profile,
                "reason": "service provider is not registered",
            }
        observation = self._service_observation(service_name, service)
        if not observation.get("healthy"):
            return {
                "available": False,
                "applied": False,
                "outcome": "unavailable",
                "service": service_name,
                "profile": profile,
                "reason": "service must be healthy before profiled tuning",
                "observation": observation,
            }

        baseline_plan = dict(service.get("launch_plan") or {})
        # Launch-plan summaries retain optional controls as ``None`` for
        # serialization, but those are not valid values to pass back through
        # a provider's command builder (for example ``int(None)`` for
        # llama.cpp's polling flags).  Keep only concrete launch values in
        # the profiled baseline; the provider will supply defaults for any
        # omitted optional controls while the tuning contract preserves the
        # immutable model/context/precision fields.
        baseline_tuning = {
            key: value
            for key, value in dict(baseline_plan.get("tuning") or {}).items()
            if value is not None
        }
        if ngram_speculation is not None and backend != "llama.cpp":
            raise ValueError("n-gram speculation override is specific to llama.cpp")
        if ngram_speculation is not None:
            baseline_tuning["ngram_speculation"] = bool(ngram_speculation)
            if not ngram_speculation:
                for key in ("spec_type", "spec_ngram_mod_n_min", "spec_ngram_mod_n_max", "spec_ngram_mod_n_match"):
                    if baseline_tuning.get(key) == "ngram-mod" or key != "spec_type":
                        baseline_tuning.pop(key, None)
            # Pass the explicit switch into provider candidate generation too.
            # Older launch summaries default this display-only marker to true
            # when no speculative flag is present; without this copy, the
            # provider would discard every ordinary candidate while the user
            # had speculation disabled.
            baseline_plan["tuning"] = dict(baseline_tuning)
        hardware = self.engine.hardware_profile()
        model_path = self._model_path_from_launch_plan(baseline_plan)
        if not model_path:
            model = service.get("model") or {}
            model_path = str(model.get("local_path") or model.get("selected_file") or "")
        if not model_path:
            return {
                "available": False,
                "applied": False,
                "outcome": "unavailable",
                "service": service_name,
                "profile": profile,
                "reason": "deployed service has no recoverable model path",
            }
        model_sha256 = None
        model_file = Path(model_path)
        if model_file.is_file():
            try:
                digest = hashlib.sha256()
                with model_file.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                model_sha256 = digest.hexdigest()
            except OSError:
                model_sha256 = None
        model_metadata = service.get("model") or {}
        serving = service.get("serving") or {}
        context_length = int(
            baseline_plan.get("context_length")
            or serving.get("context_length")
            or 4096
        )
        concurrency = int(
            baseline_plan.get("concurrency")
            or serving.get("concurrency")
            or 1
        )
        usage = usage or service.get("usage") or ("interactive" if concurrency == 1 else "shared")
        if usage not in {"interactive", "shared"}:
            raise ValueError("usage must be interactive or shared")
        baseline_plan["tuning_usage"] = usage
        locked = {
            "model_path": model_path,
            "context_length": context_length,
            "concurrency": concurrency,
        }
        if model_sha256:
            locked["model_sha256"] = model_sha256
        else:
            # A deployed path can be remote or temporarily unreadable.  Keep
            # artifact identity as an explicit unverifiable lock so tuning
            # cannot silently substitute a different model.
            locked["model_sha256"] = "unavailable"
        weight_quantization = str(
            model_metadata.get("quantization")
            or model_metadata.get("weight_quantization")
            or baseline_tuning.get("weight_quantization")
            or "unknown"
        )
        # Keep the lock explicit even when an older deployment did not record
        # its quantization metadata.  ``unknown`` is safer than silently
        # allowing a backend candidate to imply a precision change.
        locked["weight_quantization"] = weight_quantization
        for cache_key in (("cache_type_k", "cache_type_v") if backend == "llama.cpp" else ("kv_cache_dtype",)):
            if cache_key in baseline_tuning:
                locked[cache_key] = baseline_tuning[cache_key] or ("f16" if backend == "llama.cpp" else "auto")
            elif cache_key in serving:
                locked[cache_key] = serving[cache_key] or "f16"
            else:
                # llama.cpp defaults both K and V cache tensors to f16.  Make
                # that implicit precision explicit in the contract and in
                # every candidate so a tuning run cannot change it by
                # omission.
                locked[cache_key] = "f16" if backend == "llama.cpp" else "auto"
        from .tuning_adapters import IDENTITY_KEYS
        for key in IDENTITY_KEYS:
            if key in baseline_tuning:
                locked[key] = baseline_tuning[key]
        contract = TuningContract.from_mapping(
            {
                "service": service_name,
                "profile": profile,
                "model_path": model_path,
                "context_length": context_length,
                "concurrency": concurrency,
                "kv_precision_search": bool(kv_precision_search),
                "ngram_speculation": bool(baseline_tuning.get("ngram_speculation", True)),
                **locked,
            }
        )
        if dry_run:
            candidates = [baseline_tuning]
            try:
                candidates.extend(
                    adapter.propose(
                        launch_plan=baseline_plan,
                        hardware=hardware,
                        contract=contract,
                    )
                )
            except Exception as exc:
                return {
                    "api_version": "1",
                    "service": service_name,
                    "profile": profile,
                    "backend": backend,
                    "mode": "profiled_preview",
                    "outcome": "unavailable",
                    "available": False,
                    "applied": False,
                    "precision_locks": contract.to_dict()["locked"],
                    "reason": f"could not enumerate backend tuning candidates: {exc}",
                }
            unique_candidates: list[JsonDict] = []
            seen_candidates: set[str] = set()
            for tuning in candidates:
                item = dict(tuning or {})
                if not candidate_is_allowed(contract, item):
                    continue
                if adapter.validate(self._candidate_config(item, contract), contract.locked, contract, hardware):
                    continue
                key = json.dumps(item, sort_keys=True, default=str)
                if key in seen_candidates:
                    continue
                seen_candidates.add(key)
                unique_candidates.append(self._candidate_config(item, contract))
                if len(unique_candidates) >= candidate_limit:
                    break
            return {
                "api_version": "1",
                "service": service_name,
                "profile": profile,
                "backend": backend,
                "mode": "profiled_preview",
                "outcome": "preview",
                "available": True,
                "applied": False,
                "precision_locks": contract.to_dict()["locked"],
                "candidates": unique_candidates,
                "usage": usage,
                "schema_version": 2,
                "opportunities": self._tuning_opportunities(contract, profile),
                "decision": "Preview only. No process was restarted and no state was changed.",
            }
        store = TuningStore(self.rift_dir / "tuning.db")
        run = store.create_run(
            {
                "service": service_name,
                "profile": profile,
                "backend": backend,
                "status": "RUNNING",
                "candidate_limit": candidate_limit,
                "warmup_runs": warmup_runs,
                "repeats": repeats,
                "budget_seconds": budget_seconds,
                "operation_id": operation_id,
                "parent_run_id": parent_run_id,
                "contract_hash": contract_hash,
                "usage": usage,
                "schema_version": 2,
                "precision_locks": contract.to_dict()["locked"],
                "baseline": {"launch_plan": baseline_plan, "tuning": baseline_tuning},
            }
        )
        run_id = str(run["run_id"])
        try:
            # Conservatively serialize local device use until per-runtime
            # device-domain identity is qualified. This does not stop telemetry.
            store.acquire(run_id, [f"service:{service_name}", "devices:local"])
        except ValueError as exc:
            blocked = {"available": False, "applied": False, "outcome": "blocked", "reason": str(exc), "run_id": run_id}
            store.update_run(run_id, {"status": "BLOCKED", **blocked})
            return blocked
        started = time.time()
        accuracy_suite = AccuracySuite.default()
        baseline_restored = False
        report: JsonDict = {
            "api_version": "1",
            "run_id": run_id,
            "service": service_name,
            "profile": profile,
            "backend": backend,
            "mode": "profiled",
            "usage": usage,
            "parent_run_id": parent_run_id,
            "contract_hash": contract_hash,
            "schema_version": 2,
            "quality_policy": "rift-tuning-core/v2",
            "quality_suite": {
                "id": "rift-tuning-core",
                "version": "2",
                "cases": [case.id for case in accuracy_suite.cases],
                "method": "deterministic required-term, status, finish, and structured-output checks with baseline-relative similarity",
                "limitations": "This suite is a bounded acceptance floor, not a proof of universal task quality.",
            },
            "deployment_identity": {
                "model_path": model_path,
                "artifact_sha256": model_sha256,
                "backend": backend,
                "runtime": {k: baseline_tuning.get(k) for k in ("runtime_mode", "executable", "container_image") if baseline_tuning.get(k) is not None},
                "precision": {k: contract.locked.get(k) for k in ("weight_quantization", "dtype", "cache_type_k", "cache_type_v", "kv_cache_dtype") if contract.locked.get(k) is not None},
                "context_length": context_length,
                "concurrency": concurrency,
                "device_ids": baseline_tuning.get("device_ids") or hardware.get("device_ids"),
            },
            "created_unix_seconds": int(started),
            "candidate_limit": candidate_limit,
            "warmup_runs": warmup_runs,
            "repeats": repeats,
            "budget_seconds": budget_seconds,
            "target": {"tokens_per_second": float(target_tokens_per_second), "reached": False},
            "capabilities": dict((baseline_plan.get("capabilities") or {})),
            "baseline": {"tuning": baseline_tuning, "launch_plan": baseline_plan},
            "precision_locks": contract.to_dict()["locked"],
            "candidates": [],
            "applied": False,
            "no_apply": bool(no_apply),
            "opportunities": self._tuning_opportunities(contract, profile),
        }

        service["tuning_active"] = {
            "run_id": run_id,
            "profile": profile,
            "started_unix_seconds": started,
            "maintenance_window": True,
        }
        self.write_state(state)
        store.append_event(run_id, {"stage": "started", "message": "maintenance window opened"})

        def emit_progress(
            stage: str,
            message: str,
            percent: float | None = None,
            details: JsonDict | None = None,
        ) -> None:
            if progress is not None:
                progress(stage, message, percent, details)
            store.append_event(
                run_id,
                {"stage": stage, "message": message, "percent": percent, "details": details or {}},
            )

        emit_progress("baseline", "Measuring the untouched deployment baseline", 10.0)

        class _TuningCancelled(Exception):
            pass

        class _ProfileUnavailable(Exception):
            pass

        def checkpoint() -> None:
            if cancel_check is not None and cancel_check():
                raise _TuningCancelled()

        def restore_baseline() -> JsonDict:
            nonlocal baseline_restored
            current_plan = dict(service.get("launch_plan") or {})
            try:
                healthy = self._service_observation(service_name, service).get("healthy")
                if self._fingerprint(current_plan) != self._fingerprint(baseline_plan) or not healthy:
                    restored = self._replace_service_runtime(
                        state=state, service_name=service_name, service=service, provider=provider,
                        launch_plan=baseline_plan, startup_timeout_seconds=startup_timeout_seconds,
                    )
                else:
                    restored = {"ready": True, "reused_running_baseline": True}
            except Exception as exc:
                restored = {"ready": False, "error": str(exc)}
            service["launch_plan"] = baseline_plan
            service["status"] = "healthy" if restored.get("ready") else "degraded"
            service["desired_state"] = "running"
            if restored.get("ready"):
                service["last_known_good_launch_plan"] = baseline_plan
            baseline_restored = bool(restored.get("ready"))
            return restored

        def accuracy_for(plan: JsonDict) -> JsonDict | None:
            """Capture deterministic responses and score them against baseline."""
            if accuracy_runner is not None:
                return dict(accuracy_runner(plan, accuracy_suite) or {})
            benchmark = getattr(provider, "benchmark", None)
            if not callable(benchmark):
                return None
            responses: JsonDict = {}
            for case in accuracy_suite.cases:
                raw = dict(benchmark(
                    base_url=str(plan.get("api_base") or ""), prompt=case.prompt,
                    # Quality probes are separate from throughput probes. Give
                    # code/refusal cases enough room to finish so a baseline is
                    # not rejected merely because the benchmark token cap was
                    # intentionally short.
                    max_tokens=max(128, int(max_tokens)), seed=17, temperature=0.0, ignore_eos=False,
                ) or {})
                responses[case.id] = raw
            return responses

        try:
            checkpoint()
            tuning_candidates = [baseline_tuning]
            tuning_candidates.extend(
                adapter.propose(
                    launch_plan=baseline_plan,
                    hardware=hardware,
                    contract=contract,
                )
            )
            unique: list[JsonDict] = []
            seen: set[str] = set()
            for tuning in tuning_candidates:
                item = dict(tuning or {})
                if not candidate_is_allowed(contract, item):
                    continue
                if adapter.validate(self._candidate_config(item, contract), contract.locked, contract, hardware):
                    continue
                key = json.dumps(item, sort_keys=True, default=str)
                if key in seen:
                    continue
                seen.add(key)
                unique.append(item)
                if len(unique) >= candidate_limit:
                    break

            if not unique:
                raise RuntimeError("provider returned no candidates preserving the tuning contract")

            baseline_plan_normalized = self._rebuild_launch_plan(
                provider=provider,
                service=service,
                launch_plan=baseline_plan,
                hardware=hardware,
                tuning=unique[0],
            )
            baseline_plan_normalized["tuning_usage"] = usage
            if ngram_speculation is not None:
                baseline_plan = baseline_plan_normalized
            # A CLI/config speculation override changes the baseline itself,
            # not just the candidate list. Ensure the live process is replaced
            # before measuring it; otherwise an inherited optimized server
            # could make the "off" baseline accidentally include speculation.
            if self._fingerprint(service.get("launch_plan") or {}) != self._fingerprint(baseline_plan_normalized):
                baseline_startup = self._replace_service_runtime(
                    state=state,
                    service_name=service_name,
                    service=service,
                    provider=provider,
                    launch_plan=baseline_plan_normalized,
                    startup_timeout_seconds=startup_timeout_seconds,
                )
                if not baseline_startup.get("ready"):
                    raise RuntimeError("requested baseline configuration failed its readiness check")
                service["launch_plan"] = baseline_plan_normalized
            baseline_measurement_raw = self._profile_measurement(
                provider=provider,
                launch_plan=baseline_plan_normalized,
                profile=profile,
                observation=observation,
                service_name=service_name,
                prompt=prompt,
                max_tokens=max_tokens,
                warmup_runs=warmup_runs,
                repeats=repeats,
                requests_per_window=requests_per_window,
                measurement_runner=measurement_runner,
                usage=usage,
            )
            baseline_measurement = self._profile_metric(profile, baseline_measurement_raw)
            if baseline_measurement is None:
                report.update(
                    {
                        "available": False,
                        "outcome": "unavailable",
                        "reason": "GPU energy telemetry is unavailable for the cost profile"
                        if profile == "cost"
                        else "baseline benchmark did not produce a valid measurement",
                    }
                )
                restore_baseline()
                raise _ProfileUnavailable()
            report["candidates"].append(
                {
                    "index": 0,
                    "kind": "baseline",
                    "config": self._candidate_config(unique[0], contract),
                    "tuning": unique[0],
                    "launch_plan": baseline_plan_normalized,
                    "measurement": baseline_measurement.to_dict(),
                    "raw_measurement": baseline_measurement_raw,
                    "status": "baseline",
                    "target": dict(report["target"]),
                    "capabilities": dict(baseline_plan_normalized.get("capabilities") or {}),
                }
            )
            baseline_accuracy_raw = accuracy_for(baseline_plan_normalized)
            baseline_accuracy = None
            if baseline_accuracy_raw is not None and all(case.id in baseline_accuracy_raw for case in accuracy_suite.cases):
                baseline_accuracy = score_accuracy_suite(
                    accuracy_suite, baseline_accuracy_raw, baseline_accuracy_raw,
                    aggregate_tolerance=accuracy_tolerance, case_tolerance=accuracy_case_tolerance,
                )
                report["baseline"]["accuracy"] = baseline_accuracy.to_dict(retain_accuracy_responses)
                report["baseline"]["capabilities"] = dict(baseline_plan_normalized.get("capabilities") or {})
                report["candidates"][0]["accuracy"] = report["baseline"]["accuracy"]
            report["baseline"]["target"] = dict(report["target"])
            report["baseline"].setdefault("accuracy", {"status": "not_evaluated", "passed": False})
            report["baseline"].setdefault("capabilities", dict(baseline_plan_normalized.get("capabilities") or {}))
            if baseline_accuracy is None or not baseline_accuracy.passed:
                report.update({"available": False, "outcome": "unavailable", "applied": False,
                               "reason": "deterministic accuracy baseline unavailable or failed"})
                restore_baseline()
                raise _ProfileUnavailable()
            store.append_event(run_id, {"stage": "baseline_measured"})

            for index, tuning in enumerate(unique[1:], start=1):
                checkpoint()
                if budget_seconds is not None and time.time() - started >= float(budget_seconds):
                    break
                emit_progress(
                    "candidate",
                    f"Testing candidate {index} of {max(1, len(unique) - 1)}",
                    min(90.0, 15.0 + index / max(1, len(unique) - 1) * 70.0),
                    {"index": index, "run_id": run_id},
                )
                candidate_plan = self._rebuild_launch_plan(
                    provider=provider,
                    service=service,
                    launch_plan=baseline_plan,
                    hardware=hardware,
                    tuning=tuning,
                )
                candidate_plan["tuning_usage"] = usage
                entry: JsonDict = {
                    "index": index,
                    "kind": "candidate",
                    "config": self._candidate_config(tuning, contract),
                    "tuning": tuning,
                    "launch_plan": candidate_plan,
                }
                replacement = self._replace_service_runtime(
                    state=state,
                    service_name=service_name,
                    service=service,
                    provider=provider,
                    launch_plan=candidate_plan,
                    startup_timeout_seconds=startup_timeout_seconds,
                )
                entry["startup"] = replacement
                if not replacement.get("ready"):
                    entry.update({"status": "failed", "reason": "candidate did not become ready"})
                    report["candidates"].append(entry)
                    continue
                try:
                    measurement_raw = self._profile_measurement(
                        provider=provider,
                        launch_plan=candidate_plan,
                        profile=profile,
                        observation={**observation, "api_base": candidate_plan.get("api_base")},
                        service_name=service_name,
                        prompt=prompt,
                        max_tokens=max_tokens,
                        warmup_runs=warmup_runs,
                    repeats=repeats,
                    requests_per_window=requests_per_window,
                        measurement_runner=measurement_runner,
                        usage=usage,
                    )
                except Exception as exc:
                    # A single runtime/HTTP failure must reject only this
                    # candidate.  Candidate search is intentionally bounded
                    # and sequential, so later configurations can still be
                    # launched and measured after an unsupported flag or
                    # transient backend error.
                    entry.update({
                        "status": "failed",
                        "reason": f"candidate measurement failed: {exc}",
                    })
                    report["candidates"].append(entry)
                    store.append_event(run_id, {
                        "stage": "candidate_failed",
                        "index": index,
                        "reason": entry["reason"],
                    })
                    continue
                measurement = self._profile_metric(profile, measurement_raw)
                if measurement is None:
                    entry.update({"status": "failed", "reason": "candidate measurement unavailable"})
                    report["candidates"].append(entry)
                    continue
                entry.update(
                    {
                        "measurement": measurement.to_dict(),
                        "raw_measurement": measurement_raw,
                        "status": "measured",
                        "capabilities": dict(candidate_plan.get("capabilities") or {}),
                    }
                )
                entry.setdefault("accuracy", {"status": "not_evaluated", "passed": False})
                entry["target"] = dict(report["target"])
                report["candidates"].append(entry)
                store.append_event(run_id, {"stage": "candidate_measured", "index": index})

            # Throughput/latency screen first; only a bounded top shortlist
            # incurs deterministic quality calls.  Keep enough candidates to
            # avoid letting one aggressive (but inaccurate) cache/batch
            # combination hide the next-best configuration that would pass
            # the quality gate.
            measured = [item for item in report["candidates"][1:] if item.get("measurement") and item.get("status") == "measured"]
            for candidate in report["candidates"]:
                candidate.setdefault("accuracy", {"status": "not_evaluated", "passed": False})
                candidate.setdefault("target", dict(report["target"]))
                candidate.setdefault("capabilities", dict((candidate.get("launch_plan") or {}).get("capabilities") or {}))
            if profile == "speed":
                measured.sort(key=lambda item: float((item.get("measurement") or {}).get("tokens_per_second") or 0.0), reverse=True)
                ranking_metric = "tokens_per_second"
            else:
                measured.sort(key=lambda item: float((item.get("measurement") or {}).get("gpu_joules_per_request") or float("inf")))
                ranking_metric = "gpu_joules_per_request"
            shortlist = measured[: min(8, len(measured))]
            report["accuracy_shortlist"] = [item.get("config") for item in shortlist]
            report["accuracy_shortlist_cap"] = min(8, len(measured))
            report["shortlist_ranking_metric"] = ranking_metric
            for item in shortlist:
                try:
                    # Candidate measurement is sequential: the next
                    # candidate restart stops the previous process.  Bring
                    # each shortlisted candidate back before probing quality;
                    # otherwise the probe would hit a stale port and turn a
                    # valid performance result into a false connection
                    # failure.
                    quality_startup = self._replace_service_runtime(
                        state=state,
                        service_name=service_name,
                        service=service,
                        provider=provider,
                        launch_plan=dict(item["launch_plan"]),
                        startup_timeout_seconds=startup_timeout_seconds,
                    )
                    item["quality_startup"] = quality_startup
                    if not quality_startup.get("ready"):
                        raise RuntimeError("candidate did not become ready for quality probe")
                    service["launch_plan"] = dict(item["launch_plan"])
                    candidate_accuracy_raw = accuracy_for(item["launch_plan"])
                except Exception as exc:
                    # A malformed response or transient backend HTTP error is
                    # a candidate-quality failure, not a reason to abort the
                    # whole tuning transaction. Keep the candidate visible in
                    # the report and let the baseline/other candidates proceed.
                    item["status"] = "rejected_accuracy"
                    item["reason"] = f"candidate accuracy probe failed: {exc}"
                    item["accuracy"] = {
                        "status": "probe_error",
                        "passed": False,
                        "error": str(exc),
                    }
                    item["target"] = dict(report["target"])
                    continue
                candidate_accuracy = score_accuracy_suite(
                    accuracy_suite, baseline_accuracy_raw or {}, candidate_accuracy_raw or {},
                    aggregate_tolerance=accuracy_tolerance, case_tolerance=accuracy_case_tolerance,
                )
                item["accuracy"] = candidate_accuracy.to_dict(retain_accuracy_responses)
                if retain_accuracy_responses:
                    item["accuracy_raw"] = candidate_accuracy_raw
                if not candidate_accuracy.passed:
                    item["status"] = "rejected_accuracy"
                    item["reason"] = "candidate failed deterministic accuracy gate"
                else:
                    item["improvement_interval"] = self._profile_improvement_interval(
                        profile, baseline_measurement, self._profile_metric(profile, item["measurement"]),
                        baseline_raw=baseline_measurement_raw, candidate_raw=item.get("raw_measurement") or {},
                    )
                item["target"] = dict(report["target"])

            selection_candidates = [
                {
                    "config": item.get("config") or {},
                    "measurement": item.get("measurement") or {},
                    "improvement_interval": item.get("improvement_interval"),
                }
                for item in report["candidates"][1:]
                if item.get("measurement")
                and item.get("status") != "rejected_accuracy"
                and item.get("improvement_interval") is not None
            ]
            selection = select_profile_winner(
                profile,
                baseline=baseline_measurement,
                candidates=selection_candidates,
            )
            report["selection"] = selection
            selected = selection.get("selected")
            # Targets never bypass the shared improvement or latency guards.
            validated_targets = [
                item for item in report["candidates"][1:]
                if item.get("status") == "measured"
                and any(entry.get("config") == item.get("config") for entry in selection.get("feasible", []))
                and float((item.get("measurement") or {}).get("tokens_per_second") or 0.0) >= target_tokens_per_second
                and (item.get("accuracy") or {}).get("passed", False)
            ]
            if profile == "speed" and validated_targets:
                validated_targets.sort(key=lambda item: float((item.get("measurement") or {}).get("tokens_per_second") or 0.0), reverse=True)
                target_entry = validated_targets[0]
                selected = next((item for item in selection_candidates if item.get("config") == target_entry.get("config")), None) or {"config": target_entry.get("config"), "objective_improvement": 0.0}
                report["target"]["reached"] = True
            for candidate in report["candidates"]:
                candidate["target"] = dict(report["target"])
            if not selected:
                restore = restore_baseline()
                report.update(
                    {
                        "available": True,
                        "outcome": "no_improvement",
                        "applied": False,
                        "baseline_restored": baseline_restored,
                        "restore": restore,
                        "decision": "No candidate had a reliably positive improvement interval after profile guardrails.",
                    }
                )
            else:
                winner_entry = next(
                    item
                    for item in report["candidates"]
                    if item.get("config") == selected.get("config")
                )
                selected = {
                    **selected,
                    "accuracy": winner_entry.get("accuracy"),
                    "target": dict(report.get("target") or {}),
                    "capabilities": dict(winner_entry.get("capabilities") or {}),
                }
                winning_plan = dict(winner_entry["launch_plan"])
                # Cancellation is a transaction boundary: do not begin final
                # promotion after the operation has been cancelled.
                checkpoint()
                if no_apply:
                    restore = restore_baseline()
                    report.update(
                        {
                            "available": True,
                            "outcome": "improved",
                            "applied": False,
                            "winner": selected,
                            "winner_launch_plan": winning_plan,
                            "baseline_restored": baseline_restored,
                            "restore": restore,
                            "decision": "A winner was measured, but --no-apply kept the baseline deployment active.",
                        }
                    )
                else:
                    final_startup = self._replace_service_runtime(
                        state=state,
                        service_name=service_name,
                        service=service,
                        provider=provider,
                        launch_plan=winning_plan,
                        startup_timeout_seconds=startup_timeout_seconds,
                    )
                    if not final_startup.get("ready"):
                        raise RuntimeError("winning configuration failed its final readiness check")
                    final_accuracy_raw = accuracy_for(winning_plan)
                    if baseline_accuracy_raw is not None:
                        final_accuracy = score_accuracy_suite(
                            accuracy_suite, baseline_accuracy_raw, final_accuracy_raw or {},
                            aggregate_tolerance=accuracy_tolerance, case_tolerance=accuracy_case_tolerance,
                        )
                        report["final_accuracy"] = final_accuracy.to_dict(retain_accuracy_responses)
                        if not final_accuracy.passed:
                            raise RuntimeError("winning configuration failed final accuracy validation")
                    final_measurement_raw = self._profile_measurement(
                        provider=provider, launch_plan=winning_plan, profile=profile,
                        observation={**observation, "api_base": winning_plan.get("api_base")},
                        service_name=service_name, prompt=prompt, max_tokens=max_tokens,
                        warmup_runs=0, repeats=max(1, repeats), requests_per_window=requests_per_window,
                        measurement_runner=measurement_runner,
                        usage=usage,
                    )
                    final_measurement = self._profile_metric(profile, final_measurement_raw)
                    final_confidence = self._profile_confidence_interval(
                        profile, final_measurement, final_measurement_raw,
                    )
                    final_speed_lower_bound = float(final_confidence.get("lower_bound") or 0.0)
                    if final_measurement is None or (
                        profile == "speed"
                        and report["target"].get("reached")
                        and (
                            (final_measurement.tokens_per_second or 0.0) < target_tokens_per_second
                            or not final_confidence.get("available")
                            or final_speed_lower_bound < target_tokens_per_second
                        )
                    ):
                        raise RuntimeError("winning configuration failed final throughput validation")
                    report["final_measurement"] = {
                        **final_measurement.to_dict(),
                        "confidence_interval": final_confidence,
                    }
                    final_improvement_interval = self._profile_improvement_interval(
                        profile,
                        baseline_measurement,
                        final_measurement,
                        baseline_raw=baseline_measurement_raw,
                        candidate_raw=final_measurement_raw,
                    )
                    report["final_improvement_interval"] = final_improvement_interval
                    if final_improvement_interval[0] <= 0.0:
                        restore = restore_baseline()
                        report.update(
                            {
                                "available": True,
                                "outcome": "no_improvement",
                                "applied": False,
                                "baseline_restored": baseline_restored,
                                "restore": restore,
                                "decision": "The promotion retest did not show a reliably positive improvement over the baseline; the baseline was restored.",
                            }
                        )
                        raise _ProfileUnavailable()
                    if profile == "speed":
                        report["target"]["validated_tokens_per_second"] = final_measurement.tokens_per_second
                        report["target"]["confidence_lower_bound"] = final_speed_lower_bound
                    report["target"]["validated"] = True
                    selected["target"] = dict(report["target"])
                    report["winner"] = selected
                    # A cancellation can arrive while the final process is
                    # becoming ready.  Restore the baseline in the handler
                    # before exposing a terminal CANCELLED state.
                    checkpoint()
                    service["launch_plan"] = winning_plan
                    service["last_known_good_launch_plan"] = winning_plan
                    service["status"] = "healthy"
                    service["desired_state"] = "running"
                    history = service.setdefault("tuning_history", [])
                    history.append(
                        {
                            "run_id": run_id,
                            "created_unix_seconds": int(started),
                            "profile": profile,
                            "winning_config": winner_entry.get("tuning") or {},
                            "objective_improvement": selected.get("objective_improvement"),
                        }
                    )
                    del history[: max(0, len(history) - 50)]
                    report.update(
                        {
                            "available": True,
                            "outcome": "improved",
                            "applied": True,
                            "winner": selected,
                            "winner_launch_plan": winning_plan,
                            "final_startup": final_startup,
                            "decision": self._tuning_decision_text(profile, baseline_measurement, selected),
                        }
                    )
            self.write_state(state)
            emit_progress("complete", "Profiled tuning finished", 100.0, {"outcome": report.get("outcome")})
            store.update_run(run_id, {"status": "SUCCEEDED", **report})
        except _ProfileUnavailable:
            store.update_run(run_id, {"status": "SUCCEEDED", **report})
        except _TuningCancelled:
            restore = restore_baseline()
            report.update(
                {
                    "available": True,
                    "outcome": "cancelled" if baseline_restored else "rollback_failed",
                    "applied": False,
                    "baseline_restored": baseline_restored,
                    "restore": restore,
                    "decision": "The run was cancelled and the baseline restored." if baseline_restored else "Cancellation could not restore the baseline; operator recovery is required.",
                }
            )
            store.update_run(run_id, {"status": "CANCELLED" if baseline_restored else "ROLLBACK_FAILED", **report})
        except Exception as exc:
            restore = restore_baseline()
            report.update(
                {
                    "available": True,
                    "outcome": "failed",
                    "applied": False,
                    "error": str(exc),
                    "baseline_restored": baseline_restored,
                    "restore": restore,
                }
            )
            store.update_run(run_id, {"status": "FAILED", **report})
        finally:
            recovery_failed = bool(report.get("restore")) and not bool(report["restore"].get("ready"))
            if recovery_failed:
                report.update(outcome="rollback_failed", applied=False)
                store.update_run(run_id, {"status": "ROLLBACK_FAILED", **report})
            else:
                service.pop("tuning_active", None)
                store.release(run_id)
            self.write_state(state)
            store.append_event(run_id, {"stage": "finished", "outcome": report.get("outcome")})

        # Keep the durable/API shape stable across every terminal outcome.
        target = dict(report.get("target") or {})
        target.setdefault("value", target.get("tokens_per_second"))
        report["target"] = target
        report["accuracy"] = report.get("final_accuracy") or report.get("baseline", {}).get("accuracy")
        report["kv_precision_search"] = bool(contract.kv_precision_search)
        report["rejected"] = [
            {"candidate": item.get("config"), "rejection_reason": item.get("reason")}
            for item in report.get("candidates", [])
            if item.get("status", "").startswith("rejected") or item.get("reason")
        ]
        report["apply_state"] = {
            "applied": bool(report.get("applied")),
            "rolled_back": bool(report.get("baseline_restored")) and not bool(report.get("applied")),
            "state": "applied" if report.get("applied") else ("rolled_back" if report.get("baseline_restored") else "baseline_kept"),
        }
        store.update_run(run_id, report)

        if write:
            target = self._timestamped("reports", f"{service_name}-profiled-tuning-{profile}")
            self._write_json(target, report)
            report["report_path"] = str(target)
            # The persisted run is updated after the report path is known so
            # API/CLI history can deep-link directly to the immutable report.
            store.update_run(run_id, {"report_path": str(target)})
        return report
