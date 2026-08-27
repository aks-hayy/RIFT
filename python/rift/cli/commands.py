"""Command execution for the public RIFT CLI."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

from rift.cluster import RiftClusterController, example_emulated_cluster
from rift.adapters.conformance import BackendConformanceSuite
from rift.dashboard import launch_dashboard_detached, serve_dashboard
from rift.gateway import serve_gateway
from rift.node_agent import default_node_agent_config, serve_node_agent
from rift.node_bootstrap import NodeBootstrapClient, install_node_service
from rift.orchestrator import ApplyPermissions, RiftOrchestrator
from rift.providers import provider_lifecycle_gate
from rift.rift import RiftEngine
from rift.rift_yaml import write_yaml
from rift.runtime_paths import RiftPaths

from .console import RiftConsole


def execute(args: Any, console: RiftConsole) -> int:
    orchestrator = RiftOrchestrator()

    if args.command == "init":
        result = orchestrator.init_config(path=args.config, overwrite=args.force)
        console.render(result, view="init")
        return 0 if result.get("created") else 1

    if args.command == "doctor":
        result = RiftEngine().doctor(
            model_path=args.model,
            benchmark_read_bytes=16 * 1024**2,
        )
        console.render(result, title="RIFT doctor")
        return 0 if result.get("overall_status") in (None, "PASS", "WARN") else 1

    if args.command == "start":
        if args.detach:
            result = launch_dashboard_detached(
                host=args.host,
                port=args.port,
                control_port=args.control_port,
                dashboard_root=args.root,
            )
            console.render(result, title="RIFT started")
            return 0
        serve_dashboard(
            host=args.host,
            port=args.port,
            open_browser=not args.no_browser,
            control_port=args.control_port,
            dashboard_root=args.root,
        )
        return 0

    if args.command == "discover":
        result = orchestrator.discover(
            local=True,
            cluster_config=args.cluster,
            models_dir=args.models,
            allow_remote=args.allow_remote,
        )
        console.render(result, view="discover")
        return 0

    if args.command in {"recommend", "pull"}:
        automatic_pull = args.command == "pull"
        dry_run = bool(getattr(args, "dry_run", False))
        source = str(getattr(args, "source", "huggingface") or "huggingface")
        if source == "local" and not automatic_pull:
            result = orchestrator.generate_config(
                task=args.task,
                source="local",
                models_dir=getattr(args, "models_dir", None),
                output=args.output or ".rift/generated/rift.generated.yaml",
                top=args.top,
                candidate_limit=args.candidate_limit,
                max_download_gb=args.max_download_gb or 12.0,
                write=True,
            )
            selected = dict(result.get("selected") or {})
            service = dict((result.get("config") or {}).get("services", {}).get("chat", {}))
            result["source"] = "local"
            result["recommendations"] = [
                {
                    "rank": 1,
                    "id": selected.get("path"),
                    "format": selected.get("format"),
                    "backend": dict(service.get("policy") or {}).get("backend"),
                    "decision": dict(service.get("model") or {}).get("decision"),
                }
            ]
            console.render(result, view="result", title="Local model recommendation")
            return 0
        simulated_hardware = getattr(args, "simulate_hardware", None)
        if simulated_hardware and (automatic_pull or bool(getattr(args, "verify", False))):
            console.error(
                "Simulated hardware is read-only and cannot be used with pull or verification.",
                hint="Run `rift model recommend --simulate-hardware ...` without side-effect flags.",
            )
            return 2
        result = RiftEngine().recommend_models(
            task=args.task,
            mode="balanced",
            top=args.top,
            candidate_limit=args.candidate_limit,
            max_download_gb=args.max_download_gb,
            formats=args.formats,
            include_gated=args.include_gated,
            refresh=args.refresh,
            pull_best=(automatic_pull and not dry_run)
            or bool(getattr(args, "pull_best", False)),
            output_dir=args.output,
            download_root=args.download_root,
            disk_reserve_gb=args.disk_reserve_gb,
            endpoint=args.endpoint,
            token=args.token,
            simulated_hardware=simulated_hardware,
            benchmark_snapshots=getattr(args, "benchmark_snapshot", None),
        )
        if args.command == "recommend" and args.verify:
            verify_top = args.verify_top if args.verify_top is not None else args.verify_finalists
            result["verification"] = orchestrator.verify_recommendation_run(
                run_id=str(result["recommendation_run_id"]),
                permissions=ApplyPermissions(
                    allow_download=args.allow_download,
                    allow_install=args.allow_install,
                    allow_launch=args.allow_launch,
                ),
                finalists=verify_top or 1,
                budget_seconds=args.verify_budget,
                prompt=args.verify_prompt,
                max_tokens=args.verify_max_tokens,
                startup_timeout_seconds=args.verify_timeout,
                endpoint=args.endpoint,
                token=args.token,
            )
        if automatic_pull:
            recommendations = result.get("recommendations") or []
            winner = recommendations[0] if recommendations else None
            result["automatic_pull"] = {
                "dry_run": dry_run,
                "repository_input_required": False,
                "selected_repo_id": winner.get("repo_id") if winner else None,
                "selected_file": winner.get("selected_file") if winner else None,
                "downloaded": bool(result.get("pull_best")),
            }
        if args.write_report:
            target = Path(args.write_report)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
            result["report_path"] = str(target)
        console.render(
            result,
            view="recommend",
            title="Automatic model pull" if automatic_pull else None,
        )
        return 0 if result.get("recommendations") else 1

    if args.command == "plan":
        if args.recommendation_run:
            result = orchestrator.plan_recommendation_run(
                run_id=args.recommendation_run,
                selector=args.selector,
                output=args.materialized_config,
            )
        else:
            result = orchestrator.plan(config_path=args.config)
        console.render(result, view="plan")
        return 1 if any(item.get("kind") == "error" for item in result.get("actions", [])) else 0

    if args.command == "apply":
        selected_plan = _select_apply_plan(orchestrator, console, getattr(args, "plan", None))
        if selected_plan is False:
            return 2
        plan_id = str(selected_plan.get("plan_id")) if selected_plan else None
        reviewed_hash = str(
            getattr(args, "plan_hash", None)
            or (selected_plan or {}).get("plan_hash")
            or ""
        ) or None
        result = orchestrator.apply(
            config_path=(selected_plan or {}).get("config_path") or args.config,
            plan_id=plan_id,
            plan_hash=reviewed_hash,
            permissions=ApplyPermissions(
                allow_download=args.allow_download,
                allow_install=args.allow_install,
                allow_launch=args.allow_launch,
                allow_remote=args.allow_remote,
                optimize=args.optimize,
                write_back=args.write_back,
            ),
        )
        console.render(result, view="apply", title="Deployment")
        return 0 if result.get("applied") else 2 if result.get("blocked_actions") else 1

    if args.command == "status":
        result = orchestrator.status()
        if args.service:
            service = (result.get("services") or {}).get(args.service)
            if service is None:
                console.error(f"Unknown service: {args.service}", hint="Run `rift status` to list services.")
                return 1
            result = {**result, "services": {args.service: service}}
        console.render(result, view="status")
        return 0

    if args.command == "benchmark":
        if args.suite:
            result = orchestrator.benchmark_suite(
                service_name=args.service,
                warmups=args.warmups,
                repetitions=args.repeats,
            )
        else:
            result = orchestrator.benchmark(
                service_name=args.service,
                prompt=args.prompt,
                max_tokens=args.max_tokens,
            )
        console.render(result, view="benchmark")
        return 0 if result.get("available", True) else 1

    if args.command == "tune":
        result = orchestrator.tune_service(
            service_name=args.service,
            config_path=args.config,
            live=args.live,
            allow_restart=args.allow_restart,
            candidate_limit=args.candidate_limit,
            warmup_runs=args.warmups,
            repeats=args.repeats,
            startup_timeout_seconds=args.startup_timeout,
            prompt=args.prompt,
            max_tokens=args.max_tokens,
        )
        console.render(result, view="benchmark", title="Tuning result")
        if args.live and not result.get("applied"):
            return 2 if result.get("required_permission") else 1
        return 0

    if args.command == "stop":
        if not args.yes:
            console.warning("No service was stopped. Destructive confirmation is required.")
            print("Run `rift stop --yes` or scope it with `--service NAME`.")
            return 2
        result = orchestrator.destroy(service_name=args.service)
        console.render(result, title="Services stopped")
        return 0

    if args.command == "dashboard":
        if args.detach:
            result = launch_dashboard_detached(
                host=args.host,
                port=args.port,
                control_port=args.control_port,
                dashboard_root=args.root,
            )
            console.render(result, title="Dashboard")
            return 0
        serve_dashboard(
            host=args.host,
            port=args.port,
            open_browser=not args.no_browser,
            control_port=args.control_port,
            dashboard_root=args.root,
        )
        return 0

    if args.command == "model":
        return _model(args, console, orchestrator)
    if args.command == "backend":
        return _backend(args, console, orchestrator)
    if args.command == "service":
        return _service(args, console, orchestrator)
    if args.command == "cluster":
        return _cluster(args, console)
    if args.command == "node":
        return _node(args, console)
    if args.command == "system":
        return _system(args, console, orchestrator)
    raise ValueError(f"unsupported command: {args.command}")


def _select_apply_plan(
    orchestrator: RiftOrchestrator,
    console: RiftConsole,
    requested: str | None,
) -> dict[str, Any] | bool | None:
    """Choose an immutable saved plan without falling back to an unrelated latest plan."""

    plans = orchestrator.list_plans()
    if not plans and not requested:
        return None
    if requested:
        value = str(requested).strip()
        if value.isdigit():
            index = int(value)
            if 1 <= index <= len(plans):
                return plans[index - 1]
            console.error(f"Unknown plan number: {value}", hint="Run `rift plan` to create a plan.")
            return False
        try:
            return orchestrator.load_plan_by_id(value)
        except (KeyError, ValueError) as exc:
            console.error(str(exc), hint="Run `rift apply --plan NUMBER` to choose a saved plan.")
            return False

    if not sys.stdin.isatty():
        console.error(
            "Saved deployment plans require an explicit selection in noninteractive mode.",
            hint="Use `rift apply --plan PLAN_ID --plan-hash HASH ...`.",
        )
        return False

    console._heading("Saved deployment plans")
    rows = []
    for index, plan in enumerate(plans, 1):
        services = plan.get("services") or {}
        names = ", ".join(str(name) for name in services) or "-"
        model = "-"
        if services:
            first = next(iter(services.values())) or {}
            model_data = first.get("model") or {}
            model = str(model_data.get("id") or model_data.get("selected_file") or "-")
        blockers = sum(1 for item in plan.get("actions", []) if item.get("kind") == "error")
        rows.append(
            [
                index,
                str(plan.get("plan_id") or "-")[:24],
                model[:42],
                names[:20],
                blockers,
                str(plan.get("plan_hash") or "")[:12],
            ]
        )
    console._table(["#", "PLAN", "MODEL", "SERVICES", "BLOCKERS", "HASH"], rows)
    try:
        answer = input("Choose a plan number or ID (blank to cancel): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        answer = ""
    if not answer:
        console.warning("No deployment plan selected. Nothing was applied.")
        return False
    return _select_apply_plan(orchestrator, console, answer)


def _model(args: Any, console: RiftConsole, orchestrator: RiftOrchestrator) -> int:
    if args.model_command == "recommend":
        original_command = args.command
        args.command = "recommend"
        try:
            return execute(args, console)
        finally:
            args.command = original_command
    if args.command == "model" and args.model_command == "pull":
        if not args.repo_id:
            original_command = args.command
            args.command = "pull"
            try:
                return execute(args, console)
            finally:
                args.command = original_command
        result = RiftEngine().pull_model_from_hub(
            args.repo_id,
            revision=args.revision,
            output_dir=args.output,
            allow_patterns=args.allow_patterns,
            ignore_patterns=args.ignore_patterns,
            token=args.token,
            dry_run=args.dry_run,
            max_bytes=args.max_bytes,
            endpoint=args.endpoint,
            inspect_after=not args.no_inspect,
        )
        console.render(result, title="Model pull")
        return 0
    if args.model_command == "inspect":
        manifest = orchestrator.artifact_manifest(model_path=args.path, hash_mode="metadata")
        result: dict[str, Any] = {"artifact": manifest}
        try:
            result["compatibility"] = RiftEngine().compatibility_advice(args.path)
        except Exception as exc:
            result["compatibility"] = {"available": False, "reason": str(exc)}
        console.render(result, title="Model inspection")
        return 0 if manifest.get("verification", {}).get("valid", True) else 1
    if args.model_command == "verify":
        result = orchestrator.artifact_manifest(model_path=args.path, hash_mode=args.hash_mode)
        console.render(result, title="Artifact verification")
        return 0 if result.get("verification", {}).get("valid", True) else 1
    raise ValueError("rift model requires a subcommand")


def _backend(args: Any, console: RiftConsole, orchestrator: RiftOrchestrator) -> int:
    providers = orchestrator.providers
    if args.backend_command == "list":
        console.render(orchestrator.backend_status(), view="backends")
        return 0
    if args.backend_command == "detect":
        selected = providers if args.name is None else {args.name: providers.get(args.name)}
        result = {
            name: orchestrator._provider_probe(provider, name)
            for name, provider in selected.items()
            if provider is not None
        }
        if args.name and not result:
            console.error(f"Unknown backend: {args.name}", hint="Run `rift backend list`.")
            return 1
        console.render(result, view="backends", title="Backend detection")
        return 0
    if args.backend_command == "inspect":
        registration = orchestrator.backend_host.all().get(args.name)
        if registration is None:
            console.error(f"Unknown backend adapter: {args.name}", hint="Run `rift backend list`.")
            return 1
        provider = registration.adapter
        result = {
            "adapter_id": args.name,
            "source": registration.source,
            "enabled": registration.enabled,
            "manifest": provider.manifest.to_dict() if getattr(provider, "manifest", None) else None,
            "detection": orchestrator._provider_probe(provider, args.name) if registration.enabled else None,
            "install_plan": provider.install_plan() if registration.enabled else None,
            "diagnostics": [item.to_dict() for item in registration.diagnostics],
        }
        console.render(result, title=f"{args.name} adapter")
        return 0 if registration.enabled else 1
    if args.backend_command == "doctor":
        selected = providers if args.name is None else {args.name: providers.get(args.name)}
        if args.name and selected.get(args.name) is None:
            console.error(f"Unknown backend adapter: {args.name}", hint="Run `rift backend list`.")
            return 1
        checks = {}
        healthy = True
        for name, provider in selected.items():
            if provider is None:
                continue
            detection = orchestrator._provider_probe(provider, name)
            gate = provider_lifecycle_gate(provider)
            conformance = BackendConformanceSuite().run(provider)
            available = bool(detection.get("available"))
            checks[name] = {
                "manifest": provider.manifest.to_dict() if getattr(provider, "manifest", None) else None,
                "contract": gate,
                "conformance": conformance,
                "detection": detection,
                "ready_now": available and bool(gate.get("gate_passed")) and bool(conformance.get("passed")),
                "remediation": None if available else provider.install_plan(),
            }
            healthy = healthy and bool(checks[name]["ready_now"])
        result = {"healthy": healthy, "checks": checks, "registry": orchestrator.backend_host.diagnostics()}
        console.render(result, title="Backend adapter doctor")
        return 0 if healthy else 1
    provider = providers.get(args.name)
    if provider is None:
        console.error(f"Unknown backend: {args.name}", hint="Run `rift backend list`.")
        return 1
    if args.backend_command == "install-plan":
        console.render(provider.install_plan(), title=f"{args.name} install plan")
        return 0
    if args.backend_command == "install":
        if not args.allow_install:
            console.warning("Backend installation was not authorized.")
            console.render(provider.install_plan(), title=f"{args.name} install plan")
            return 2
        result = provider.install(
            target_dir=args.target or str(Path(".rift") / "backends" / args.name),
            variant=args.variant,
            force=args.force,
        )
        console.render(result, title=f"{args.name} installation")
        return 0 if result.get("installed", True) else 1
    if args.backend_command == "health":
        result = provider.health(base_url=args.base_url)
        console.render(result, title=f"{args.name} health")
        return 0 if result.get("healthy") else 1
    raise ValueError("rift backend requires a subcommand")


def _service(args: Any, console: RiftConsole, orchestrator: RiftOrchestrator) -> int:
    if args.service_command in {"benchmark", "tune"}:
        original_command = args.command
        args.command = args.service_command
        try:
            return execute(args, console)
        finally:
            args.command = original_command
    if args.service_command == "monitor":
        result = orchestrator.monitor(
            service_name=args.service,
            allow_recovery=args.allow_recovery,
            interval_seconds=args.interval,
            iterations=args.iterations,
        )
        console.render(result, title="Service monitor")
        return 0
    if args.service_command == "restart":
        result = orchestrator.recover(
            service_name=args.service,
            allow_launch=args.allow_launch,
            force=args.force,
        )
        console.render(result, title="Service recovery")
        return 0 if result.get("recovered") else 2 if not args.allow_launch else 1
    if args.service_command == "rollback":
        result = orchestrator.recover(
            service_name=args.service,
            allow_launch=args.allow_launch,
            force=True,
        )
        console.render(result, title="Service rollback")
        return 0 if result.get("recovered") else 2 if not args.allow_launch else 1
    if args.service_command == "incidents":
        console.render(orchestrator.incidents(limit=args.limit), title="Service incidents")
        return 0
    if args.service_command == "logs":
        result = orchestrator.logs(service_name=args.service, tail=args.tail)
        console.render(result, title=f"{args.service} logs")
        return 0 if result.get("available") else 1
    if args.service_command == "gateway":
        serve_gateway(
            config_path=args.config,
            service_name=args.service,
            host=args.host,
            port=args.port,
            fallback_services=args.fallback_services,
        )
        return 0
    raise ValueError("rift service requires a subcommand")


def _cluster(args: Any, console: RiftConsole) -> int:
    controller = RiftClusterController()
    if args.cluster_command == "init":
        target = Path(args.config)
        if target.exists() and not args.force:
            console.warning(f"{target} already exists; no changes made.")
            return 1
        write_yaml(target, example_emulated_cluster())
        console.success(f"Created {target}")
        return 0
    if args.cluster_command == "discover":
        result = controller.discover(
            cluster_config=args.config,
            allow_remote=args.allow_remote,
        )
        console.render(result, view="discover", title="Cluster discovery")
        return 0
    if args.cluster_command == "plan":
        result = controller.plan(cluster_config=args.config)
        console.render(result, view="plan", title="Cluster placement plan")
        return 0 if not result.get("unscheduled") else 1
    if args.cluster_command == "apply":
        result = controller.apply(
            cluster_config=args.config,
            allow_deploy=args.allow_launch,
            allow_remote=args.allow_remote,
            allow_download=args.allow_download,
            allow_install=args.allow_install,
        )
        console.render(result, view="apply", title="Cluster apply")
        return 0 if args.allow_launch else 2
    if args.cluster_command == "status":
        console.render(controller.status(), title="Cluster status")
        return 0
    if args.cluster_command == "drain":
        result = controller.drain_node(node_name=args.node, force=args.force)
        console.render(result, title="Cluster node drain")
        return 0
    if args.cluster_command == "benchmark":
        console.render(controller.benchmark(service_name=args.service), view="benchmark", title="Cluster benchmark")
        return 0
    if args.cluster_command == "tune":
        console.render(controller.tune(service_name=args.service), view="benchmark", title="Cluster tuning")
        return 0
    if args.cluster_command == "recover":
        result = controller.monitor(allow_recovery=args.allow_recovery)
        console.render(result, title="Cluster recovery")
        return 0 if args.allow_recovery else 2
    if args.cluster_command == "destroy":
        if not args.yes:
            console.warning("No cluster instance was stopped. Pass --yes to confirm.")
            return 2
        console.render(controller.destroy(), title="Cluster destroy")
        return 0
    raise ValueError("rift cluster requires a subcommand")


def _node(args: Any, console: RiftConsole) -> int:
    if args.node_command == "start":
        client = NodeBootstrapClient(
            root=args.root,
            controller=args.controller,
            display_name=args.name,
            host=args.host,
            advertise_host=args.advertise,
            port=args.port,
            output=lambda value: print(value),
        )
        if args.install_service:
            result = client.enroll(timeout_seconds=args.timeout)
            server = result.pop("server", None)
            thread = result.pop("thread", None)
            if server is not None:
                server.shutdown()
                server.server_close()
            if thread is not None:
                thread.join(timeout=3)
            installed = install_node_service(root=client.root)
            console.render({"enrollment": result, "service": installed}, title="RIFT node service installed")
            return 0
        client.run_foreground()
        return 0
    if args.node_command == "stop":
        from rift.node_enrollment import ManagedNodeStore
        import os
        import signal

        store = ManagedNodeStore(Path(args.root).expanduser().resolve() if args.root else RiftPaths.from_environment().home)
        pid_path = store.node_dir / "node.pid"
        if not pid_path.is_file():
            console.render({"stopped": False, "reason": "node agent is not running"}, title="RIFT node")
            return 0
        pid = int(pid_path.read_text(encoding="ascii"))
        if os.name == "nt":
            subprocess_result = __import__("subprocess").run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True, text=True)
            if subprocess_result.returncode != 0:
                raise RuntimeError((subprocess_result.stderr or subprocess_result.stdout or "taskkill failed").strip())
        else:
            os.kill(pid, signal.SIGTERM)
        console.render({"stopped": True, "pid": pid}, title="RIFT node stopped")
        return 0
    if args.node_command in {"init", "enroll"}:
        target = Path(args.config)
        if target.exists() and not args.force:
            console.warning(f"{target} already exists; no changes made.")
            return 1
        write_yaml(target, default_node_agent_config(args.node_id))
        console.render(
            {
                "created": True,
                "path": str(target.resolve()),
                "node_id": args.node_id,
                "next_steps": [
                    "Provision a node certificate and key signed for this host.",
                    "Install the controller CA certificate named in tls.client_ca.",
                    "Keep permissions disabled until the operator explicitly authorizes node-side actions.",
                    f"Run `rift node serve --config {target}`.",
                ],
            },
            title="RIFT node agent",
        )
        return 0
    if args.node_command == "status":
        if not args.config:
            result = NodeBootstrapClient(root=args.root).status()
            console.render(result, title="RIFT managed node status")
            return 0
        from rift.node_agent import NodeAgentController, NodeAgentPolicy

        root = Path(args.root or ".").resolve()
        policy = NodeAgentPolicy.from_file(args.config)
        result = NodeAgentController(root=root, policy=policy).status()
        console.render(result, title="Node agent status")
        return 0
    if args.node_command == "permissions":
        client = NodeBootstrapClient(root=args.root)
        if args.permissions_command == "show":
            console.render(client.status()["permissions"], title="RIFT node permissions")
            return 0
        updates = {}
        for option, key in (("inference", "allow_inference"), ("download", "allow_download"), ("install", "allow_install"), ("launch", "allow_launch")):
            value = getattr(args, option)
            if value is not None:
                updates[key] = value == "allow"
        if not updates:
            console.error("At least one permission flag is required", hint="Use `rift node permissions set --inference allow`.")
            return 2
        from rift.node_enrollment import ManagedNodeStore

        result = ManagedNodeStore(client.root).update_permissions(updates)
        console.render(result.get("permissions") or {}, title="RIFT node permissions updated")
        return 0
    if args.node_command == "serve":
        serve_node_agent(config_path=args.config, root=args.root)
        return 0
    raise ValueError("rift node requires a subcommand")


def _system(args: Any, console: RiftConsole, orchestrator: RiftOrchestrator) -> int:
    if args.system_command == "info":
        console.render(RiftEngine().build_info(), title="RIFT build information")
        return 0
    if args.system_command == "hardware":
        discovery = orchestrator.discover(write=False)
        nodes = discovery.get("nodes") or []
        result = nodes[0].get("hardware") if nodes else {}
        console.render(result or {}, view="hardware")
        return 0
    if args.system_command == "calibrate":
        result = orchestrator.calibrate_hardware(
            sample_bytes=args.sample_mib * 1024**2,
            force=args.force,
        )
        console.render(result, title="Hardware calibration")
        return 0
    if args.system_command == "doctor":
        result = RiftEngine().doctor(
            model_path=args.model,
            benchmark_read_bytes=16 * 1024**2,
        )
        console.render(result, title="RIFT doctor")
        return 0 if result.get("overall_status") in (None, "PASS", "WARN") else 1
    if args.system_command == "diagnostics":
        console.render(orchestrator.diagnostics(output=args.output), title="Diagnostic bundle")
        return 0
    if args.system_command == "backup":
        console.render(orchestrator.backup_state(output=args.output), title="Controller state backup")
        return 0
    if args.system_command == "restore":
        if not args.yes:
            console.warning("No state was restored. Replacement confirmation is required.")
            print("Run `rift system restore --input PATH --yes` after reviewing the backup.")
            return 2
        console.render(orchestrator.restore_state(source=args.input), title="Controller state restore")
        return 0
    if args.system_command == "export":
        console.render(orchestrator.export_deployment(output=args.output), title="Deployment export")
        return 0
    if args.system_command == "migrate":
        if args.paths:
            paths = RiftPaths.from_environment(cwd=args.source_root or Path.cwd())
            result = paths.migrate_checkout(
                source_root=args.source_root,
                move=args.move,
                write=args.write,
            )
            console.render(result, title="Runtime path migration")
            return 0
        console.render(orchestrator.migrate(config_path=args.config, write=args.write), title="Schema migration")
        return 0
    raise ValueError("rift system requires a subcommand")


__all__ = ["execute"]
