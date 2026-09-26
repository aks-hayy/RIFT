"""Bounded workload-to-deployment controller.

This is the easy-path orchestration layer.  It reuses recommendation,
immutable plan/apply, benchmark, evaluation, and profiled tuning primitives;
it does not implement a second serving stack.  Every transition is journaled
and failures are classified conservatively.
"""
from __future__ import annotations

import time
import json
from pathlib import Path
from typing import Any, Callable

from .orchestrator import ApplyPermissions, RiftOrchestrator
from .rift_yaml import read_yaml, write_yaml
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
        search_candidate_limit: int = 250,
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

            local_recommendation = None
            if models_dir:
                local_recommendation = self.orchestrator.recommend_local_models(
                    task=task, models_dir=models_dir, top=limit, workload_contract=contract
                )
            if local_recommendation and local_recommendation.get("recommendations"):
                recommendation = local_recommendation
                generated = self.orchestrator.generate_config(
                    task=task, source="local", models_dir=models_dir,
                    output=self.orchestrator.rift_dir / "generated" / f"workload-{run_id}.yaml",
                    selected_candidate=recommendation["recommendations"][0],
                    workload_contract=contract,
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
                        gateway = configured_service.setdefault("gateway", {})
                        if required_context > 0:
                            serving = configured_service.setdefault("serving", {})
                            serving["context_length"] = max(
                                required_context,
                                int(serving.get("context_length") or 0),
                            )
                            serving["concurrency"] = max(
                                int((contract.get("performance") or {}).get("concurrency") or 1),
                                int(serving.get("concurrency") or 1),
                            )
                            gateway["max_prompt_tokens"] = max(
                                required_context,
                                int(gateway.get("max_prompt_tokens") or 0),
                            )
                            gateway["max_total_tokens"] = max(
                                required_context + 1024,
                                int(gateway.get("max_total_tokens") or 0),
                            )
                        schema_artifact = contract.get("output_schema")
                        if isinstance(schema_artifact, dict) and isinstance(schema_artifact.get("schema"), dict):
                            schema_file = self._materialize_schema_file(run_id, schema_artifact)
                            # The gateway is the backend-neutral enforcement
                            # point. Backend adapters receive the same schema
                            # via response_format/structured_outputs, while
                            # the gateway validates the returned payload. The
                            # llama.cpp adapter additionally receives a
                            # run-owned --json-schema-file artifact.
                            gateway["output_schema"] = schema_artifact["schema"]
                            gateway["output_schema_sha256"] = schema_artifact.get("sha256")
                            gateway["structured_output_enforced"] = True
                            serving = configured_service.setdefault("serving", {})
                            tuning = serving.setdefault("tuning", {})
                            tuning["json_schema_file"] = schema_file
                            gateway["output_schema_file"] = schema_file
                        workload_monitoring = contract.get("monitoring")
                        if isinstance(workload_monitoring, dict) and isinstance(workload_monitoring.get("objectives"), list):
                            monitoring = configured_service.setdefault("monitoring", {})
                            if isinstance(monitoring, dict):
                                monitoring["objectives"] = workload_monitoring["objectives"]
                                monitoring["sla"] = {key: workload_monitoring[key] for key in ("observation_window_seconds", "probe_interval_seconds", "error_budget_seconds", "source") if key in workload_monitoring}
                if service_name != "chat":
                    if isinstance(services, dict) and "chat" in services:
                        services[service_name] = services.pop("chat")
                # The context overlay and optional service rename must both be
                # persisted before plan hashing; otherwise the plan would still
                # point at the generator's 8K file on disk.
                write_yaml(generated["path"], config)
                plan = self.orchestrator.plan(config_path=generated["path"], write=True)
            elif network == "offline":
                if not models_dir:
                    return self._finish(run_id, "BLOCKED", reason="offline workload requires an explicit local models directory")
                return self._finish(run_id, "INFEASIBLE", reason="no compatible local artifact passed hardware/backend preflight")
            else:
                if not envelope.get("actions", {}).get("download"):
                    return self._finish(run_id, "BLOCKED", reason="online workload search requires approved download permission")
                approved_sources = {str(item).strip().lower() for item in envelope.get("sources", [])}
                if approved_sources and not any(item in {"huggingface", "https://huggingface.co"} for item in approved_sources):
                    return self._finish(run_id, "BLOCKED", reason="Hugging Face is not an approved model source")
                recommendation = self.orchestrator.engine.recommend_models(
                    task=task, top=limit, candidate_limit=limit,
                    search_candidate_limit=search_candidate_limit,
                    workload_contract=contract,
                    allowed_licenses=envelope.get("licenses"),
                    model_ref=model_ref, max_download_gb=max(0.001, float((envelope.get("limits") or {}).get("total_download_bytes", 1)) / (1024**3)),
                    run_store_root=str(self.orchestrator.rift_dir),
                )
                if not recommendation.get("recommendations"):
                    return self._finish(run_id, "EXHAUSTED", reason="approved candidate search returned no admissible artifacts")
                rec_run_id = str(recommendation.get("recommendation_run_id") or "")
                plan = self.orchestrator.plan_recommendation_run(
                    run_id=rec_run_id, selector="best_estimated", service_name=service_name,
                )
            # Online recommendation materialization also produces a mutable
            # YAML source. Attach the reviewed schema before the immutable plan
            # hash is finalized, just as in the local/offline path.
            schema_artifact = contract.get("output_schema")
            config_path = plan.get("materialized_config") or plan.get("config_path")
            if config_path:
                materialized = read_yaml(config_path)
                materialized_services = materialized.get("services") if isinstance(materialized, dict) else None
                target_service = materialized_services.get(service_name) if isinstance(materialized_services, dict) else None
                if isinstance(target_service, dict):
                    serving = target_service.setdefault("serving", {})
                    required_context = int((contract.get("performance") or {}).get("context_tokens") or 0)
                    required_concurrency = int((contract.get("performance") or {}).get("concurrency") or 1)
                    if required_context:
                        serving["context_length"] = max(required_context, int(serving.get("context_length") or 0))
                        gateway = target_service.setdefault("gateway", {})
                        gateway["max_prompt_tokens"] = max(required_context, int(gateway.get("max_prompt_tokens") or 0))
                        gateway["max_total_tokens"] = max(required_context + 1024, int(gateway.get("max_total_tokens") or 0))
                    serving["concurrency"] = max(required_concurrency, int(serving.get("concurrency") or 1))
                    write_yaml(config_path, materialized)
                    plan = self.orchestrator.plan(config_path=config_path, write=True)
                    config_path = plan.get("materialized_config") or plan.get("config_path") or config_path
            if isinstance(schema_artifact, dict) and isinstance(schema_artifact.get("schema"), dict) and config_path:
                materialized = read_yaml(config_path)
                materialized_services = materialized.get("services") if isinstance(materialized, dict) else None
                target_service = materialized_services.get(service_name) if isinstance(materialized_services, dict) else None
                if isinstance(target_service, dict):
                    schema_file = self._materialize_schema_file(run_id, schema_artifact)
                    target_gateway = target_service.setdefault("gateway", {})
                    target_gateway["output_schema"] = schema_artifact["schema"]
                    target_gateway["output_schema_sha256"] = schema_artifact.get("sha256")
                    target_gateway["structured_output_enforced"] = True
                    target_gateway["output_schema_file"] = schema_file
                    serving = target_service.setdefault("serving", {})
                    serving.setdefault("tuning", {})["json_schema_file"] = schema_file
                    write_yaml(config_path, materialized)
                    plan = self.orchestrator.plan(config_path=config_path, write=True)
            workload_monitoring = contract.get("monitoring")
            if isinstance(workload_monitoring, dict) and isinstance(workload_monitoring.get("objectives"), list) and config_path:
                materialized = read_yaml(config_path)
                materialized_services = materialized.get("services") if isinstance(materialized, dict) else None
                target_service = materialized_services.get(service_name) if isinstance(materialized_services, dict) else None
                if isinstance(target_service, dict):
                    target_monitoring = target_service.setdefault("monitoring", {})
                    target_monitoring["objectives"] = workload_monitoring["objectives"]
                    target_monitoring["sla"] = {key: workload_monitoring[key] for key in ("observation_window_seconds", "probe_interval_seconds", "error_budget_seconds", "source") if key in workload_monitoring}
                    write_yaml(config_path, materialized)
                    plan = self.orchestrator.plan(config_path=config_path, write=True)
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
            if bool(capabilities.get("structured_output")) and (
                not contract.get("output_schema")
                or self._evaluation_suite(contract) is None
            ):
                return self._finish(
                    run_id,
                    "BLOCKED",
                    reason="strict structured output requires an attached schema and a registered executable evaluator",
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
            # Tool calling is a capability gate, not an execution feature.  If
            # the approved workload requires it, certify the exact deployed
            # model/backend/template/runtime before accepting the endpoint.
            tool_requirement = capabilities.get("tool_calling")
            tool_required = bool(tool_requirement.get("required")) if isinstance(tool_requirement, dict) else bool(tool_requirement)
            tool_capability = None
            if tool_required:
                step("capability", "Verifying core tool-call capability for the exact deployment")
                tool_capability = self.orchestrator.verify_tool_capability(service_name=service_name, write=True)
                if tool_capability.get("status") != "VERIFIED":
                    return self._finish(
                        run_id,
                        "INFEASIBLE",
                        reason="selected model/backend/runtime did not pass the required core tool-call capability suite",
                        tool_capability=tool_capability,
                        deployment=applied,
                    )
            step("acceptance", "Running fresh health, quality, and performance checks", details={"readiness": readiness})
            health = self.orchestrator.status()
            structured_acceptance = isinstance(contract.get("output_schema"), dict)
            acceptance_max_tokens = 512 if structured_acceptance else 48
            benchmark = self.orchestrator.benchmark_suite(
                service_name=service_name, warmups=1, repetitions=5,
                concurrency=int((contract.get("performance") or {}).get("concurrency") or 1),
                max_tokens=acceptance_max_tokens,
            )
            evaluation = self.orchestrator.evaluate_service(
                service_name=service_name,
                suite=self._evaluation_suite(contract),
                max_tokens=acceptance_max_tokens,
                required=True,
                write=True,
            )
            result: dict[str, Any] = {
                "health": health,
                "benchmark": benchmark,
                "evaluation": evaluation,
                "deployment": applied,
                "tool_capability": tool_capability,
            }
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
                "tool_capability_required": tool_required,
                "tool_capability_verified": (tool_capability or {}).get("status") == "VERIFIED" if tool_required else None,
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
        except ValueError as exc:
            # A strict output workload cannot be satisfied by silently
            # dropping its schema. Treat a missing/unsupported backend
            # capability as a bounded BLOCKED result so candidate search or a
            # user-approved backend change can be attempted explicitly.
            message = str(exc)
            lowered = message.lower()
            if "json-schema" in lowered or "structured output schema" in lowered:
                return self._finish(run_id, "BLOCKED", reason=message)
            return self._finish(run_id, "FAILED", reason=message)
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

    def _materialize_schema_file(self, run_id: str, artifact: dict[str, Any]) -> str:
        """Persist the approved schema as a run-owned backend input.

        The immutable deployment plan records this path and its hash.  Keeping
        it under the run directory makes ownership and cleanup explicit while
        allowing a promoted llama.cpp service to continue enforcing the same
        schema after the controller exits.
        """
        schema = artifact.get("schema")
        if not isinstance(schema, dict):
            raise ValueError("output schema artifact must contain an object schema")
        digest = str(artifact.get("sha256") or "unknown").strip().lower()
        safe_digest = "".join(char for char in digest if char in "0123456789abcdef")[:64] or "schema"
        target = self.orchestrator.rift_dir / "workload-runs" / str(run_id) / "schemas" / f"{safe_digest}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if target.exists() and target.read_text(encoding="utf-8") != canonical:
            raise ValueError("run-owned schema artifact hash collision")
        target.write_text(canonical, encoding="utf-8")
        return str(target)

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
            cases = [{
                "id": "response_nonempty",
                "prompt": "Reply with one concise sentence confirming the local service is ready.",
                "kind": "nonempty",
                "required": True,
            }]
            artifact = contract.get("output_schema")
            if isinstance(artifact, dict) and isinstance(artifact.get("schema"), (dict, bool)):
                schema_text = json.dumps(artifact["schema"], sort_keys=True, separators=(",", ":"))
                schema_prompt = f"Return only one JSON object matching this schema (no markdown): {schema_text}"
                # The gateway enforces the approved schema on every request.  A
                # generic prose smoke prompt would therefore be an invalid test
                # for a structured service and can reject an otherwise healthy
                # model.  Keep the case id for report compatibility, but make
                # its prompt schema-compatible whenever structured output is
                # required.
                cases[0]["prompt"] = schema_prompt
                cases.append({
                    "id": "uploaded_output_schema",
                    "prompt": schema_prompt,
                    "kind": "json_schema",
                    "schema": artifact["schema"],
                    "required": True,
                })
            return {
                "id": suite_id,
                "version": version,
                "cases": cases,
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
