"""Bounded workload-to-deployment controller.

This is the easy-path orchestration layer.  It reuses recommendation,
immutable plan/apply, benchmark, evaluation, and profiled tuning primitives;
it does not implement a second serving stack.  Every transition is journaled
and failures are classified conservatively.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from .orchestrator import ApplyPermissions, RiftOrchestrator
from .rift_yaml import write_yaml
from .workload_store import WorkloadStore


class WorkloadController:
    def __init__(self, orchestrator: RiftOrchestrator, store: WorkloadStore | None = None):
        self.orchestrator = orchestrator
        self.store = store or WorkloadStore(orchestrator.rift_dir / "workloads.db")

    def run(
        self,
        approval_id: str,
        *,
        run_id: str | None = None,
        models_dir: str | None = None,
        model_ref: str | None = None,
        candidate_limit: int = 3,
        tune: bool = True,
        progress: Callable[[str, str, float | None, dict[str, Any] | None], None] | None = None,
    ) -> dict[str, Any]:
        approval = self.store.get_approval(approval_id)
        contract = approval["contract"]
        envelope = approval["envelope"]
        run = self.store.create_run(draft_id=approval["draft_id"], approval_id=approval_id, run_id=run_id)
        run_id = run["run_id"]

        def step(stage: str, message: str, *, status: str | None = None, details: dict[str, Any] | None = None, **payload: Any) -> None:
            self.store.update_run(run_id, status=status, payload=payload or None, stage=stage, message=message, details=details)
            if progress is not None:
                progress(stage, message, None, details)

        try:
            self.store.update_run(run_id, status="RUNNING", stage="preflight", message="Checking approved workload and execution envelope")
            target = str((envelope.get("targets") or ["local"])[0])
            if target != "local":
                return self._finish(run_id, "BLOCKED", reason="easy-path execution currently supports the enrolled local target only", target=target)
            task = str(contract.get("task") or "chat")
            service_name = str((contract.get("service") or {}).get("name") or "workload-service")
            policies = contract.get("policies") or {}
            network = str(policies.get("network") or "approved_sources")
            limit = max(1, min(int(candidate_limit), int((envelope.get("limits") or {}).get("max_artifacts") or candidate_limit)))
            step("search", "Searching admissible model artifacts", details={"network": network, "candidate_limit": limit})

            if network == "offline":
                if not models_dir:
                    return self._finish(run_id, "BLOCKED", reason="offline workload requires an explicit local models directory")
                recommendation = self.orchestrator.recommend_local_models(task=task, models_dir=models_dir, top=limit)
                if not recommendation.get("recommendations"):
                    return self._finish(run_id, "INFEASIBLE", reason="no compatible local artifact passed hardware/backend preflight")
                generated = self.orchestrator.generate_config(
                    task=task, source="local", models_dir=models_dir,
                    output=self.orchestrator.rift_dir / "generated" / f"workload-{run_id}.yaml",
                    write=True,
                )
                # The standard generator intentionally uses an 8K default for
                # ordinary deployments.  A workload contract is authoritative:
                # carry its explicit context requirement into the materialized
                # service before hashing the immutable plan.  Gateway prompt
                # limits must be raised with it or the endpoint would reject a
                # valid long-history request before llama.cpp sees it.
                config = generated.get("config") or {}
                services = config.get("services") if isinstance(config, dict) else None
                if isinstance(services, dict):
                    configured_name = "chat" if "chat" in services else service_name
                    configured_service = services.get(configured_name)
                    if isinstance(configured_service, dict):
                        required_context = int((contract.get("performance") or {}).get("context_tokens") or 0)
                        if required_context > 0:
                            serving = configured_service.setdefault("serving", {})
                            serving["context_length"] = max(
                                required_context,
                                int(serving.get("context_length") or 0),
                            )
                            gateway = configured_service.setdefault("gateway", {})
                            gateway["max_prompt_tokens"] = max(
                                required_context,
                                int(gateway.get("max_prompt_tokens") or 0),
                            )
                            gateway["max_total_tokens"] = max(
                                required_context + 1024,
                                int(gateway.get("max_total_tokens") or 0),
                            )
                if service_name != "chat":
                    if isinstance(services, dict) and "chat" in services:
                        services[service_name] = services.pop("chat")
                # The context overlay and optional service rename must both be
                # persisted before plan hashing; otherwise the plan would still
                # point at the generator's 8K file on disk.
                write_yaml(generated["path"], config)
                plan = self.orchestrator.plan(config_path=generated["path"], write=True)
            else:
                if not envelope.get("actions", {}).get("download"):
                    return self._finish(run_id, "BLOCKED", reason="online workload search requires approved download permission")
                recommendation = self.orchestrator.engine.recommend_models(
                    task=task, top=limit, candidate_limit=limit,
                    model_ref=model_ref, max_download_gb=max(0.001, float((envelope.get("limits") or {}).get("total_download_bytes", 1)) / (1024**3)),
                    run_store_root=str(self.orchestrator.rift_dir),
                )
                if not recommendation.get("recommendations"):
                    return self._finish(run_id, "EXHAUSTED", reason="approved candidate search returned no admissible artifacts")
                rec_run_id = str(recommendation.get("recommendation_run_id") or "")
                plan = self.orchestrator.plan_recommendation_run(
                    run_id=rec_run_id, selector="best_estimated", service_name=service_name,
                )
            step("plan", "Created immutable deployment plan", details={"plan_id": plan.get("plan_id"), "backend": plan.get("backend_kind") or plan.get("selected_backend")})
            planned_service = (plan.get("services") or {}).get(service_name) or {}
            planned_serving = planned_service.get("serving") or {}
            required_context = int((contract.get("performance") or {}).get("context_tokens") or 0)
            effective_context = int(planned_serving.get("context_length") or 0)
            if required_context and effective_context < required_context:
                return self._finish(
                    run_id,
                    "INFEASIBLE",
                    reason="selected deployment plan cannot provide the requested context capacity",
                    context_requirement={"required_tokens": required_context, "planned_tokens": effective_context},
                    backend=planned_service.get("policy", {}).get("backend") or planned_service.get("backend"),
                    model=(planned_service.get("model") or {}).get("selected_file") or (planned_service.get("model") or {}).get("id"),
                )
            capabilities = contract.get("capabilities") or {}
            quality = contract.get("quality") or {}
            if bool(capabilities.get("structured_output")) and str(quality.get("suite_id") or "") == "rift-text-core":
                return self._finish(
                    run_id,
                    "BLOCKED",
                    reason="strict structured output requires a registered schema evaluator; the generic text suite cannot prove EHR conformance",
                    model=(planned_service.get("model") or {}).get("selected_file") or (planned_service.get("model") or {}).get("id"),
                    backend=planned_service.get("policy", {}).get("backend") or planned_service.get("backend"),
                    context_requirement={"required_tokens": required_context, "planned_tokens": effective_context},
                )
            permissions = ApplyPermissions(
                allow_download=bool(envelope.get("actions", {}).get("download")),
                allow_install=bool(envelope.get("actions", {}).get("install")),
                allow_launch=bool(envelope.get("actions", {}).get("temporary_launch")),
                allow_remote=bool(envelope.get("actions", {}).get("remote_execution")),
            )
            if not permissions.allow_launch:
                return self._finish(run_id, "BLOCKED", reason="approval does not authorize temporary launch")
            step("deploy", "Applying the reviewed immutable plan")
            applied = self.orchestrator.apply(
                plan_id=str(plan.get("plan_id") or ""), plan_hash=str(plan.get("plan_hash") or ""),
                permissions=permissions, progress=progress,
            )
            if not applied.get("applied"):
                reason = str(applied.get("reason") or "deployment plan was not applied")
                status = "BLOCKED" if applied.get("required_permissions") else "FAILED"
                return self._finish(run_id, status, reason=reason, deployment=applied)
            step("readiness", "Waiting for the deployed endpoint to become ready")
            readiness = self._wait_for_readiness(service_name)
            if not readiness.get("ready"):
                return self._finish(run_id, "FAILED", reason="deployed endpoint did not become ready", readiness=readiness, deployment=applied)
            step("acceptance", "Running fresh health, quality, and performance checks", details={"readiness": readiness})
            health = self.orchestrator.status()
            benchmark = self.orchestrator.benchmark_suite(
                service_name=service_name, warmups=1, repetitions=5,
                concurrency=int((contract.get("performance") or {}).get("concurrency") or 1),
                max_tokens=48,
            )
            evaluation = self.orchestrator.evaluate_service(
                service_name=service_name,
                suite=self._evaluation_suite(contract),
                required=True,
                write=True,
            )
            result: dict[str, Any] = {"health": health, "benchmark": benchmark, "evaluation": evaluation, "deployment": applied}
            summary = benchmark.get("summary") or {}
            metrics = summary.get("metrics") or summary
            benchmark_available = bool(benchmark.get("available", summary.get("valid") is True and int(summary.get("failure_count") or 0) == 0))
            evaluation_cases = evaluation.get("cases") if isinstance(evaluation.get("cases"), list) else []
            evaluation_passed = bool(evaluation.get("available")) and all(
                str(case.get("status") or "").lower() == "pass"
                for case in evaluation_cases
                if isinstance(case, dict) and bool(case.get("required", True))
            )
            result["acceptance"] = {
                "benchmark_available": benchmark_available,
                "evaluation_available": bool(evaluation.get("available")),
                "evaluation_passed": evaluation_passed,
                "required_evaluation_failures": [
                    case.get("case_id") for case in evaluation_cases
                    if isinstance(case, dict) and bool(case.get("required", True)) and str(case.get("status") or "").lower() != "pass"
                ],
            }
            if not benchmark_available or not evaluation_passed:
                return self._finish(run_id, "FAILED", reason="fresh acceptance failed a required endpoint, benchmark, or quality gate", **result)
            measured_tps = metrics.get("median_tokens_per_second")
            perf = contract.get("performance") or {}
            meets_speed = perf.get("min_decode_tps") is None or (measured_tps is not None and float(measured_tps) >= float(perf["min_decode_tps"]))
            if not meets_speed and tune and contract.get("objective") in {"speed", "cost"} and envelope.get("actions", {}).get("restart"):
                step("tuning", "Invoking the shared backend tuning coordinator", details={"profile": contract.get("objective")})
                tuned = self.orchestrator.profiled_tune_service(
                    service_name=service_name, profile=str(contract.get("objective")), allow_restart=True,
                    candidate_limit=min(24, int((envelope.get("limits") or {}).get("tuning_candidates") or 1)),
                    warmup_runs=1, repeats=5, parent_run_id=run_id,
                )
                result["tuning"] = tuned
                if tuned.get("status") not in {"VERIFIED", "SUCCEEDED", "COMPLETED"} and not tuned.get("applied"):
                    return self._finish(run_id, "EXHAUSTED", reason="tuning completed without a passing configuration", **result)
            elif not meets_speed:
                return self._finish(run_id, "INFEASIBLE", reason="deployed candidate failed the hard throughput requirement and tuning was not authorized", **result)
            step("promote", "Verified endpoint satisfies the approved workload", status="VERIFIED", details={"measured_decode_tps": measured_tps})
            return self._finish(run_id, "VERIFIED", **result)
        except PermissionError as exc:
            return self._finish(run_id, "BLOCKED", reason=str(exc))
        except (TimeoutError, OSError) as exc:
            return self._finish(run_id, "FAILED", reason=str(exc))
        except Exception as exc:
            # The HTTP operation worker uses a private cancellation signal;
            # preserve it so the operation store can keep CANCELLED semantics.
            if exc.__class__.__name__ == "OperationCancelled":
                raise
            return self._finish(run_id, "FAILED", reason=str(exc))

    def _finish(self, run_id: str, status: str, **payload: Any) -> dict[str, Any]:
        return self.store.update_run(run_id, status=status, payload=payload, stage="complete", message=f"Workload run {status.lower()}")

    @staticmethod
    def _evaluation_suite(contract: dict[str, Any]) -> dict[str, Any] | None:
        """Resolve the reviewed workload suite into an executable evaluator.

        The compiler's first-party ``response_nonempty`` pack is intentionally
        small and maps to the evaluator's deterministic nonempty case. Other
        suite ids are left for a future registered suite resolver rather than
        silently substituting the default deployment smoke suite.
        """
        quality = contract.get("quality") or {}
        suite_id = str(quality.get("suite_id") or "")
        version = str(quality.get("suite_version") or "v1")
        required = quality.get("required_cases") or []
        if suite_id == "rift-text-core" and required == ["response_nonempty"]:
            return {
                "id": suite_id,
                "version": version,
                "cases": [{
                    "id": "response_nonempty",
                    "prompt": "Reply with one concise sentence confirming the local service is ready.",
                    "kind": "nonempty",
                    "required": True,
                }],
            }
        return None

    def _wait_for_readiness(self, service_name: str) -> dict[str, Any]:
        """Wait for backend HTTP readiness after process launch.

        ``apply`` records a started process before the backend has necessarily
        finished loading weights.  The easy path must not turn that transient
        state into benchmark failures, so readiness is a distinct journaled
        gate with a bounded timeout.
        """
        timeout = 180.0
        try:
            configured = self.orchestrator.read_state().get("services", {}).get(service_name, {})
            timeout = max(5.0, min(900.0, float((configured.get("monitoring") or {}).get("startup_grace_seconds", timeout))))
        except (TypeError, ValueError, AttributeError):
            pass
        deadline = time.monotonic() + timeout
        last: dict[str, Any] = {"ready": False, "service": service_name}
        while time.monotonic() < deadline:
            try:
                snapshot = self.orchestrator.status()
                service = (snapshot.get("services") or {}).get(service_name) or {}
                observation = service.get("observation") or {}
                last = {
                    "ready": bool(observation.get("healthy")),
                    "service": service_name,
                    "phase": observation.get("phase"),
                    "health": observation.get("health"),
                    "pid": (service.get("runtime") or {}).get("pid"),
                }
                if last["ready"]:
                    return last
                if observation.get("process_alive") is False:
                    return {**last, "reason": "backend process exited during startup"}
            except Exception as exc:  # transient probe failures are retryable
                last = {"ready": False, "service": service_name, "error": str(exc)}
            time.sleep(0.5)
        return {**last, "ready": False, "reason": "startup readiness timeout", "timeout_seconds": timeout}


__all__ = ["WorkloadController"]
