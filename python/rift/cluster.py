"""RIFT cluster scheduler, remote discovery, and deterministic node emulator.

The emulator exercises the same desired-state, placement, tuning, and recovery
contracts that remote node transports will implement. It never pretends to be
a physical benchmark: every report identifies measurements as simulated.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any

from .providers import backend_adapter_host
from .observability import ObservabilityStore
from .rollout import RolloutEngine
from .rift_yaml import read_yaml
from .runtime_paths import RiftPaths
from .state_store import StateStore
from .transport import transport_registry


JsonDict = dict[str, Any]
_GIB = 1024**3


class RiftClusterController:
    """Declarative scheduler/reconciler with honest emulated and remote modes."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root else Path.cwd()
        self.rift_dir = (
            self.root / ".rift"
            if root is not None
            else RiftPaths.from_environment(cwd=self.root).home
        )
        self.state_path = self.rift_dir / "cluster" / "state.json"
        self.state_store = StateStore(
            self.rift_dir / "cluster" / "state.db",
            legacy_path=self.state_path,
        )
        self.transports = transport_registry()
        self.rollouts = RolloutEngine()
        self.observability = ObservabilityStore(root=self.root, data_root=self.rift_dir)
        self.backend_host = backend_adapter_host()

    def discover(
        self,
        *,
        cluster_config: str | Path = "cluster.yaml",
        write: bool = True,
        allow_remote: bool = False,
    ) -> JsonDict:
        config_path = self._resolve(cluster_config)
        config = read_yaml(config_path)
        self._validate_config(config)
        mode = str(config.get("mode") or "emulated")
        nodes = []
        for source in config["nodes"]:
            node = self._normalize_node(source)
            transport_name = str(source.get("transport") or ("emulated" if mode == "emulated" else "ssh"))
            node["transport"] = transport_name
            if mode != "emulated" and str(node.get("host") or "").lower() not in ("localhost", "127.0.0.1"):
                transport = self.transports.get(transport_name)
                if transport is None:
                    node.update({"ready": False, "status": "unsupported_transport", "remote_discovery": {"error": f"unknown transport: {transport_name}"}})
                else:
                    remote = transport.discover(source, allow_remote=allow_remote)
                    node["remote_discovery"] = remote
                    if remote.get("ok"):
                        measured = remote.get("hardware") or {}
                        node["hardware"].update(measured)
                        node["ready"] = True
                        node["status"] = "ready"
                    elif not allow_remote:
                        node["ready"] = False
                        node["status"] = "requires_allow_remote"
                    else:
                        node["ready"] = False
                        node["status"] = "remote_discovery_failed"
            nodes.append(node)
        result = {
            "rift_product": "RIFT",
            "controller": "cluster",
            "mode": mode,
            "verification_status": "deterministic_emulation" if mode == "emulated" else "remote_transport_probe",
            "created_unix_seconds": int(time.time()),
            "config_path": str(config_path),
            "nodes": nodes,
            "summary": {
                "node_count": len(nodes),
                "ready_nodes": sum(1 for node in nodes if node["ready"]),
                "total_vram_bytes": sum(int(node["hardware"]["total_vram_bytes"]) for node in nodes),
                "total_host_ram_bytes": sum(
                    int(node["hardware"]["total_host_ram_bytes"]) for node in nodes
                ),
            },
        }
        if write:
            self._write_json(self.rift_dir / "cluster" / "discovery.json", result)
        return result

    def check(self, *, cluster_config: str | Path = "cluster.yaml") -> JsonDict:
        discovery = self.discover(cluster_config=cluster_config, write=True)
        plan = self.plan(cluster_config=cluster_config, write=True)
        return {
            "valid": not plan["unscheduled"],
            "discovery": discovery["summary"],
            "placement_summary": plan["summary"],
            "unscheduled": plan["unscheduled"],
            "warnings": plan["warnings"],
        }

    def plan(self, *, cluster_config: str | Path = "cluster.yaml", write: bool = True) -> JsonDict:
        config_path = self._resolve(cluster_config)
        config = read_yaml(config_path)
        self._validate_config(config)
        nodes = [self._normalize_node(node) for node in config["nodes"]]
        allocations = {
            node["name"]: {"vram_bytes": 0, "host_ram_bytes": 0, "disk_bytes": 0, "instances": 0}
            for node in nodes
        }
        placements: list[JsonDict] = []
        unscheduled: list[JsonDict] = []
        warnings: list[str] = []

        for service_name, service in config["services"].items():
            replicas = int(service.get("replicas") or 1)
            for replica in range(replicas):
                ranked, rejected = self._rank_nodes(
                    nodes=nodes,
                    allocations=allocations,
                    service_name=service_name,
                    service=service,
                    replica=replica,
                    existing=placements,
                )
                if not ranked:
                    unscheduled.append(
                        {
                            "service": service_name,
                            "replica": replica,
                            "reason": "no feasible node",
                            "rejected_nodes": rejected,
                        }
                    )
                    continue
                winner = ranked[0]
                requirements = winner["requirements"]
                reservation = allocations[winner["node"]]
                reservation["vram_bytes"] += int(requirements["vram_bytes"])
                reservation["host_ram_bytes"] += int(requirements["host_ram_bytes"])
                reservation["disk_bytes"] += int(requirements["disk_bytes"])
                reservation["instances"] += 1
                placements.append(
                    {
                        "instance_id": f"{service_name}-{replica}",
                        "service": service_name,
                        "replica": replica,
                        "node": winner["node"],
                        "backend": winner["backend"],
                        "score": winner["score"],
                        "requirements": requirements,
                        "decision": {
                            "reason": winner["reasons"],
                            "alternatives": ranked[1:4],
                            "rejected_nodes": rejected,
                        },
                    }
                )
        if unscheduled:
            warnings.append("One or more service replicas could not be placed.")
        actions = []
        for placement in placements:
            actions.extend(
                [
                    {
                        "kind": "reserve",
                        "instance": placement["instance_id"],
                        "node": placement["node"],
                    },
                    {
                        "kind": "deploy",
                        "instance": placement["instance_id"],
                        "node": placement["node"],
                        "backend": placement["backend"],
                        "permission": "allow_deploy",
                    },
                    {
                        "kind": "monitor",
                        "instance": placement["instance_id"],
                        "node": placement["node"],
                    },
                ]
            )
        result = {
            "rift_product": "RIFT",
            "controller": "cluster",
            "mode": str(config.get("mode") or "emulated"),
            "read_only": True,
            "created_unix_seconds": int(time.time()),
            "config_path": str(config_path),
            "config_fingerprint": self._fingerprint(config),
            "nodes": nodes,
            "placements": placements,
            "unscheduled": unscheduled,
            "allocations": allocations,
            "actions": actions,
            "warnings": warnings,
            "summary": {
                "requested_instances": sum(
                    int(service.get("replicas") or 1) for service in config["services"].values()
                ),
                "scheduled_instances": len(placements),
                "unscheduled_instances": len(unscheduled),
            },
        }
        if write:
            self._write_json(self.rift_dir / "cluster" / "plan.json", result)
        return result

    def apply(
        self,
        *,
        cluster_config: str | Path = "cluster.yaml",
        allow_deploy: bool = False,
        allow_remote: bool = False,
        allow_download: bool = False,
        allow_install: bool = False,
    ) -> JsonDict:
        plan = self.plan(cluster_config=cluster_config, write=True)
        if not allow_deploy:
            return {
                "applied": False,
                "reason": "cluster deployment requires --allow-launch",
                "required_permission": "allow_deploy",
                "plan": plan,
            }
        if plan["unscheduled"]:
            return {
                "applied": False,
                "reason": "plan contains unscheduled replicas",
                "plan": plan,
            }
        if plan["mode"] != "emulated" and not allow_remote:
            return {
                "applied": False,
                "reason": "remote cluster deployment requires --allow-remote",
                "required_permission": "allow_remote",
                "plan": plan,
            }
        config = read_yaml(plan["config_path"])
        now = int(time.time())
        instances: JsonDict = {}
        for placement in plan["placements"]:
            service = config["services"][placement["service"]]
            instances[placement["instance_id"]] = {
                **placement,
                "model": dict(service.get("model") or {}),
                "task": str(service.get("task") or "chat"),
                "serving": dict(service.get("serving") or {}),
                "recovery": {
                    "max_restarts": 3,
                    "reschedule_on_node_failure": True,
                    **dict(service.get("recovery") or {}),
                },
                "desired_state": "running",
                "phase": "running",
                "ready": True,
                "restart_count": 0,
                "generation": 1,
                "fault": None,
                "tuning": dict(service.get("tuning") or {}),
                "deployed_unix_seconds": now,
            }
        state = {
            "schema_version": 1,
            "mode": plan["mode"],
            "config_path": plan["config_path"],
            "config_fingerprint": plan["config_fingerprint"],
            "nodes": {node["name"]: node for node in plan["nodes"]},
            "instances": instances,
            "allocations": plan["allocations"],
            "incidents": [],
            "benchmark_history": [],
            "tuning_history": [],
            "created_unix_seconds": now,
            "verification_status": "deterministic_emulation" if plan["mode"] == "emulated" else "remote_apply_not_yet_verified",
        }
        remote_dispatch: list[JsonDict] = []
        if plan["mode"] != "emulated":
            remote_dispatch = self._dispatch_remote_desired_state(
                config=config,
                plan=plan,
                allow_remote=allow_remote,
                allow_download=allow_download,
                allow_install=allow_install,
            )
            state["remote_dispatch"] = remote_dispatch
            failed = [item for item in remote_dispatch if not item.get("ok")]
            if failed:
                state["verification_status"] = "remote_apply_partial_failure"
                self._write_state(state)
                return {
                    "applied": False,
                    "reason": "one or more remote node agents rejected deployment",
                    "remote_dispatch": remote_dispatch,
                    "state_path": str(self.state_path),
                }
            state["verification_status"] = "remote_agents_reconciled"
        self._write_state(state)
        return {
            "applied": True,
            "mode": plan["mode"],
            "deployed_instances": list(instances.values()),
            "state_path": str(self.state_path),
            "remote_dispatch": remote_dispatch,
        }

    def _dispatch_remote_desired_state(
        self,
        *,
        config: JsonDict,
        plan: JsonDict,
        allow_remote: bool,
        allow_download: bool,
        allow_install: bool,
    ) -> list[JsonDict]:
        source_nodes = {str(item.get("name") or ""): item for item in config.get("nodes", [])}
        by_node: dict[str, list[JsonDict]] = {}
        for placement in plan.get("placements", []):
            by_node.setdefault(str(placement["node"]), []).append(placement)
        generation = time.time_ns()
        results: list[JsonDict] = []
        for node_name, placements in sorted(by_node.items()):
            source = source_nodes.get(node_name) or {}
            transport_name = str(source.get("transport") or "ssh")
            transport = self.transports.get(transport_name)
            if transport_name != "rift_agent" or transport is None:
                results.append(
                    {
                        "node": node_name,
                        "transport": transport_name,
                        "ok": False,
                        "reason": "remote apply requires the rift_agent transport; SSH/PowerShell are discovery and bootstrap transports",
                    }
                )
                continue
            services: JsonDict = {}
            for placement in placements:
                service = json.loads(
                    json.dumps(config["services"][placement["service"]])
                )
                serving = service.setdefault("serving", {})
                serving["port"] = int(serving.get("port") or 11735) + int(placement.get("replica") or 0)
                service.setdefault("policy", {})["backend"] = placement["backend"]
                services[str(placement["instance_id"])] = service
            node_config = {
                "version": int(config.get("version") or 1),
                "project": f"{config.get('project') or 'rift-cluster'}-{node_name}",
                "nodes": [{"name": "local", "host": "localhost", "role": "worker"}],
                "services": services,
            }
            try:
                submitted = transport.submit_desired_state(
                    source,
                    generation=generation,
                    config=node_config,
                    allow_remote=allow_remote,
                )
                reconciled = transport.reconcile(
                    source,
                    permissions={
                        "allow_download": allow_download,
                        "allow_install": allow_install,
                        "allow_launch": True,
                    },
                    allow_remote=allow_remote,
                )
                results.append(
                    {
                        "node": node_name,
                        "transport": transport_name,
                        "ok": bool(submitted.get("accepted"))
                        and bool(reconciled.get("applied")),
                        "generation": generation,
                        "submitted": submitted,
                        "reconciled": reconciled,
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "node": node_name,
                        "transport": transport_name,
                        "ok": False,
                        "generation": generation,
                        "error": str(exc),
                    }
                )
        return results

    def status(self) -> JsonDict:
        state = self._read_state()
        instances = list(state.get("instances", {}).values())
        phases: JsonDict = {}
        for instance in instances:
            phase = str(instance.get("phase") or "unknown")
            phases[phase] = int(phases.get(phase) or 0) + 1
        return {
            "available": bool(state),
            "mode": state.get("mode"),
            "nodes": list(state.get("nodes", {}).values()),
            "instances": instances,
            "summary": {
                "node_count": len(state.get("nodes", {})),
                "instance_count": len(instances),
                "phases": phases,
                "incident_count": len(state.get("incidents", [])),
            },
        }

    def monitor(self, *, allow_recovery: bool = False) -> JsonDict:
        state = self._read_state(required=True)
        results = []
        for instance_id, instance in state["instances"].items():
            node = state["nodes"][instance["node"]]
            fault = instance.get("fault")
            healthy = (
                instance.get("desired_state") == "running"
                and bool(node.get("ready"))
                and not fault
            )
            if healthy:
                instance["phase"] = "running"
                instance["ready"] = True
                action = "observed"
            else:
                instance["ready"] = False
                instance["phase"] = "node_lost" if not node.get("ready") else "failed"
                action = "recovery_not_authorized"
                if allow_recovery:
                    action = self._recover_instance(state, instance_id, instance)
            results.append(
                {
                    "instance_id": instance_id,
                    "node": instance["node"],
                    "healthy": bool(instance.get("ready")),
                    "phase": instance["phase"],
                    "action": action,
                }
            )
        self._write_state(state)
        return {
            "allow_recovery": allow_recovery,
            "results": results,
            "healthy": all(item["healthy"] for item in results),
        }

    def benchmark(self, *, service_name: str | None = None) -> JsonDict:
        state = self._read_state(required=True)
        results = []
        for instance in state["instances"].values():
            if service_name and instance["service"] != service_name:
                continue
            node = state["nodes"][instance["node"]]
            result = self._simulate_benchmark(instance, node, instance.get("tuning") or {})
            results.append(result)
        report = {
            "measurement_mode": "deterministic_emulation",
            "created_unix_seconds": int(time.time()),
            "results": results,
            "summary": {
                "instance_count": len(results),
                "aggregate_tokens_per_second": round(
                    sum(float(item["decode_tokens_per_second"]) for item in results), 3
                ),
                "all_usable": all(item["usability"] != "unusable" for item in results),
            },
        }
        state.setdefault("benchmark_history", []).append(report)
        self._write_state(state)
        self._write_json(self._timestamped_report("cluster-benchmark"), report)
        return report

    def tune(self, *, service_name: str | None = None) -> JsonDict:
        state = self._read_state(required=True)
        results = []
        for instance in state["instances"].values():
            if service_name and instance["service"] != service_name:
                continue
            node = state["nodes"][instance["node"]]
            baseline = dict(instance.get("tuning") or {})
            candidates = self._tuning_candidates(instance["backend"], baseline, node)
            measurements = [
                {
                    "tuning": candidate,
                    "benchmark": self._simulate_benchmark(instance, node, candidate),
                }
                for candidate in candidates
            ]
            winner = max(
                measurements,
                key=lambda item: float(item["benchmark"]["decode_tokens_per_second"]),
            )
            baseline_result = self._simulate_benchmark(instance, node, baseline)
            instance["tuning"] = winner["tuning"]
            instance["generation"] = int(instance.get("generation") or 1) + 1
            results.append(
                {
                    "instance_id": instance["instance_id"],
                    "baseline": baseline_result,
                    "candidates": measurements,
                    "winning_config": winner["tuning"],
                    "winning_benchmark": winner["benchmark"],
                    "improvement_percent": round(
                        (
                            float(winner["benchmark"]["decode_tokens_per_second"])
                            / float(baseline_result["decode_tokens_per_second"])
                            - 1.0
                        )
                        * 100.0,
                        3,
                    ),
                }
            )
        report = {
            "measurement_mode": "deterministic_emulation",
            "created_unix_seconds": int(time.time()),
            "results": results,
        }
        state.setdefault("tuning_history", []).append(report)
        self._write_state(state)
        self._write_json(self._timestamped_report("cluster-tuning"), report)
        return report

    def inject_failure(
        self,
        *,
        node_name: str | None = None,
        instance_id: str | None = None,
        kind: str = "process_crash",
    ) -> JsonDict:
        state = self._read_state(required=True)
        if kind in ("node_down", "network_partition"):
            if not node_name or node_name not in state["nodes"]:
                raise ValueError(f"{kind} requires a valid node_name")
            state["nodes"][node_name]["ready"] = False
            state["nodes"][node_name]["status"] = (
                "network_partitioned" if kind == "network_partition" else "not_ready"
            )
            if kind == "network_partition":
                state["nodes"][node_name]["network_reachable"] = False
            affected = [
                key for key, value in state["instances"].items() if value["node"] == node_name
            ]
        else:
            if not instance_id or instance_id not in state["instances"]:
                raise ValueError("process_crash requires a valid instance_id")
            state["instances"][instance_id]["fault"] = kind
            affected = [instance_id]
        self._write_state(state)
        return {"injected": True, "kind": kind, "affected_instances": affected}

    def restore_node(self, *, node_name: str) -> JsonDict:
        state = self._read_state(required=True)
        if node_name not in state["nodes"]:
            raise ValueError(f"node not found: {node_name}")
        state["nodes"][node_name]["ready"] = True
        state["nodes"][node_name]["status"] = "ready"
        state["nodes"][node_name]["network_reachable"] = True
        self._write_state(state)
        return {"restored": True, "node": node_name}

    def drain_node(self, *, node_name: str, force: bool = False) -> JsonDict:
        """Stop new placement on a node and optionally reschedule its instances."""

        state = self._read_state(required=True)
        node = state["nodes"].get(node_name)
        if node is None:
            raise ValueError(f"node not found: {node_name}")
        node["ready"] = False
        node["status"] = "draining"
        node["draining"] = True
        affected = [
            instance_id
            for instance_id, instance in state["instances"].items()
            if instance.get("node") == node_name
        ]
        rescheduled = []
        if force:
            for instance_id in affected:
                recovery = self._recover_instance(state, instance_id, state["instances"][instance_id])
                rescheduled.append({"instance_id": instance_id, "recovery": recovery})
        self._write_state(state)
        return {
            "drained": True,
            "node": node_name,
            "affected_instances": affected,
            "rescheduled": rescheduled,
            "force": force,
        }

    def destroy(self) -> JsonDict:
        state = self._read_state(required=True)
        stopped = []
        for instance in state["instances"].values():
            instance["desired_state"] = "stopped"
            instance["phase"] = "stopped"
            instance["ready"] = False
            stopped.append(instance["instance_id"])
        self._write_state(state)
        return {"destroyed": True, "stopped_instances": stopped}

    def rollout_plan(
        self,
        *,
        service_name: str,
        desired: JsonDict,
        strategy: str = "canary",
        max_unavailable: int = 0,
    ) -> JsonDict:
        state = self._read_state(required=True)
        instances = [item for item in state.get("instances", {}).values() if item.get("service") == service_name]
        if not instances:
            raise ValueError(f"cluster service not found: {service_name}")
        current = instances[0].get("launch_plan") or instances[0].get("tuning") or {}
        result = self.rollouts.plan(
            service=service_name,
            current=current,
            desired=desired,
            strategy=strategy,
            replicas=len(instances),
            max_unavailable=max_unavailable,
        )
        self._write_json(self.rift_dir / "cluster" / "rollout-plan.json", result)
        return result

    def rollout_gate(
        self,
        *,
        readiness: JsonDict,
        baseline: JsonDict,
        candidate: JsonDict,
    ) -> JsonDict:
        result = self.rollouts.promotion_gate(
            readiness=readiness,
            baseline_benchmark=baseline,
            candidate_benchmark=candidate,
        )
        self.observability.append(
            "cluster_rollout_gate",
            status="ok" if result["promote"] else "error",
            details=result,
        )
        return result

    def _rank_nodes(
        self,
        *,
        nodes: list[JsonDict],
        allocations: JsonDict,
        service_name: str,
        service: JsonDict,
        replica: int,
        existing: list[JsonDict],
    ) -> tuple[list[JsonDict], list[JsonDict]]:
        ranked = []
        rejected = []
        model = service.get("model") or {}
        requested_backend = str((service.get("policy") or {}).get("backend") or "auto")
        required_labels = dict((service.get("placement") or {}).get("required_labels") or {})
        prior_nodes = {
            placement["node"]
            for placement in existing
            if placement["service"] == service_name
        }
        for node in nodes:
            requirements = self._requirements(service, node=node)
            reasons = []
            blockers = []
            if not node["ready"]:
                blockers.append("node is not Ready")
            for key, value in required_labels.items():
                if str(node["labels"].get(key)) != str(value):
                    blockers.append(f"required label {key}={value} is absent")
            backend = self._select_backend(
                node,
                model,
                requested_backend,
                workload=str(service.get("task") or "chat"),
            )
            if not backend:
                blockers.append("no compatible installed backend")
            reserved = allocations[node["name"]]
            free_vram = int(node["hardware"]["total_vram_bytes"]) - int(reserved["vram_bytes"])
            free_ram = int(node["hardware"]["total_host_ram_bytes"]) - int(
                reserved["host_ram_bytes"]
            )
            free_disk = int(node["hardware"].get("disk_free_bytes") or 0) - int(reserved.get("disk_bytes") or 0)
            if int(requirements["vram_bytes"]) > free_vram:
                blockers.append("insufficient unreserved VRAM")
            if int(requirements["host_ram_bytes"]) > free_ram:
                blockers.append("insufficient unreserved host RAM")
            if int(requirements["disk_bytes"]) > free_disk:
                blockers.append("insufficient unreserved disk capacity")
            if not bool(node.get("network_reachable", True)):
                blockers.append("node network is not reachable")
            if blockers:
                rejected.append({"node": node["name"], "reasons": blockers})
                continue

            vram_total = max(1, int(node["hardware"]["total_vram_bytes"]))
            ram_total = max(1, int(node["hardware"]["total_host_ram_bytes"]))
            resource_score = min(
                1.0,
                max(0.0, (free_vram - int(requirements["vram_bytes"])) / vram_total * 0.6)
                + max(0.0, (free_ram - int(requirements["host_ram_bytes"])) / ram_total * 0.4),
            )
            cache_hit = str(model.get("id") or "") in set(node.get("model_cache") or [])
            reliability = float(node.get("reliability") or 0.95)
            accelerator = 1.0 if int(node["hardware"]["total_vram_bytes"]) > 0 else 0.2
            spread = 0.0 if node["name"] in prior_nodes else 1.0
            score = (
                resource_score * 0.35
                + 1.0 * 0.20
                + accelerator * 0.15
                + (1.0 if cache_hit else 0.0) * 0.15
                + reliability * 0.10
                + spread * 0.05
            )
            reasons.append(f"{backend} supports {str(model.get('format') or 'unknown').lower()} on this node")
            reasons.append("hard VRAM/RAM reservations fit")
            reasons.append("model is already cached" if cache_hit else "model download/cache miss is required")
            if spread:
                reasons.append("placement spreads replicas across failure domains")
            ranked.append(
                {
                    "node": node["name"],
                    "backend": backend,
                    "score": round(score, 6),
                    "requirements": requirements,
                    "reasons": reasons,
                    "replica": replica,
                }
            )
        ranked.sort(key=lambda item: (-float(item["score"]), str(item["node"])))
        return ranked, rejected

    def _recover_instance(self, state: JsonDict, instance_id: str, instance: JsonDict) -> str:
        node = state["nodes"][instance["node"]]
        policy = instance.get("recovery") or {}
        old_node = instance["node"]
        action = "restart_failed"
        if not node.get("ready") and bool(policy.get("reschedule_on_node_failure", True)):
            replacement = self._find_recovery_node(state, instance)
            if replacement:
                requirements = instance["requirements"]
                old_allocation = state.setdefault("allocations", {}).setdefault(
                    old_node,
                    {"vram_bytes": 0, "host_ram_bytes": 0, "disk_bytes": 0, "instances": 0},
                )
                new_allocation = state["allocations"].setdefault(
                    replacement,
                    {"vram_bytes": 0, "host_ram_bytes": 0, "disk_bytes": 0, "instances": 0},
                )
                old_allocation["vram_bytes"] = max(
                    0,
                    int(old_allocation.get("vram_bytes") or 0)
                    - int(requirements["vram_bytes"]),
                )
                old_allocation["host_ram_bytes"] = max(
                    0,
                    int(old_allocation.get("host_ram_bytes") or 0)
                    - int(requirements["host_ram_bytes"]),
                )
                old_allocation["instances"] = max(
                    0,
                    int(old_allocation.get("instances") or 0) - 1,
                )
                old_allocation["disk_bytes"] = max(
                    0,
                    int(old_allocation.get("disk_bytes") or 0)
                    - int(requirements.get("disk_bytes") or 0),
                )
                new_allocation["vram_bytes"] = int(
                    new_allocation.get("vram_bytes") or 0
                ) + int(requirements["vram_bytes"])
                new_allocation["host_ram_bytes"] = int(
                    new_allocation.get("host_ram_bytes") or 0
                ) + int(requirements["host_ram_bytes"])
                new_allocation["instances"] = int(
                    new_allocation.get("instances") or 0
                ) + 1
                new_allocation["disk_bytes"] = int(
                    new_allocation.get("disk_bytes") or 0
                ) + int(requirements.get("disk_bytes") or 0)
                instance["node"] = replacement
                instance["phase"] = "running"
                instance["ready"] = True
                instance["fault"] = None
                instance["generation"] = int(instance.get("generation") or 1) + 1
                action = "rescheduled"
        elif int(instance.get("restart_count") or 0) < int(policy.get("max_restarts") or 3):
            instance["restart_count"] = int(instance.get("restart_count") or 0) + 1
            instance["phase"] = "running"
            instance["ready"] = True
            instance["fault"] = None
            instance["generation"] = int(instance.get("generation") or 1) + 1
            action = "restarted"
        else:
            instance["phase"] = "degraded"
            instance["ready"] = False
            action = "marked_degraded"
        incident = {
            "created_unix_seconds": time.time(),
            "instance_id": instance_id,
            "old_node": old_node,
            "new_node": instance["node"],
            "action": action,
        }
        state.setdefault("incidents", []).append(incident)
        return action

    def _find_recovery_node(self, state: JsonDict, instance: JsonDict) -> str | None:
        model_format = str((instance.get("model") or {}).get("format") or "").lower()
        requirements = instance["requirements"]
        occupied = {
            value["node"]
            for key, value in state["instances"].items()
            if key != instance["instance_id"] and value["service"] == instance["service"]
        }
        candidates = []
        for node_name, node in state["nodes"].items():
            if node_name == instance["node"] or not node.get("ready"):
                continue
            backend = self._select_backend(
                node,
                {"format": model_format},
                str(instance["backend"]),
                workload=str(instance.get("task") or "chat"),
            )
            if not backend:
                continue
            other_vram = sum(
                int(value["requirements"]["vram_bytes"])
                for key, value in state["instances"].items()
                if key != instance["instance_id"]
                and value["node"] == node_name
                and value.get("desired_state") == "running"
            )
            other_ram = sum(
                int(value["requirements"]["host_ram_bytes"])
                for key, value in state["instances"].items()
                if key != instance["instance_id"]
                and value["node"] == node_name
                and value.get("desired_state") == "running"
            )
            other_disk = sum(
                int(value["requirements"].get("disk_bytes") or 0)
                for key, value in state["instances"].items()
                if key != instance["instance_id"]
                and value["node"] == node_name
                and value.get("desired_state") == "running"
            )
            if other_vram + int(requirements["vram_bytes"]) > int(node["hardware"]["total_vram_bytes"]):
                continue
            if other_ram + int(requirements["host_ram_bytes"]) > int(node["hardware"]["total_host_ram_bytes"]):
                continue
            if other_disk + int(requirements.get("disk_bytes") or 0) > int(node["hardware"].get("disk_free_bytes") or 0):
                continue
            score = float(node.get("reliability") or 0.95) + (0.1 if node_name not in occupied else 0.0)
            candidates.append((score, node_name))
        return max(candidates)[1] if candidates else None

    def _requirements(self, service: JsonDict, *, node: JsonDict | None = None) -> JsonDict:
        model = service.get("model") or {}
        serving = service.get("serving") or {}
        model_bytes = int(model.get("estimated_bytes") or model.get("size_bytes") or 0)
        params_b = float(model.get("parameters_b") or 0.0)
        if not model_bytes and params_b > 0.0:
            quantization = str(model.get("quantization") or "").lower()
            bits = model.get("bits")
            if isinstance(bits, (int, float)) and float(bits) > 0.0:
                bytes_per_param = float(bits) / 8.0 * 1.12
            elif any(marker in quantization for marker in ("q2", "2bit", "int2")):
                bytes_per_param = 0.34
            elif any(marker in quantization for marker in ("q3", "3bit", "int3")):
                bytes_per_param = 0.46
            elif any(marker in quantization for marker in ("q4", "4bit", "int4", "awq", "gptq")):
                bytes_per_param = 0.58
            elif any(marker in quantization for marker in ("q8", "8bit", "int8", "fp8")):
                bytes_per_param = 1.08
            else:
                bytes_per_param = 2.05
            model_bytes = int(params_b * 1_000_000_000 * bytes_per_param)
        context = int(serving.get("context_length") or 4096)
        concurrency = int(serving.get("concurrency") or 1)
        kv_bytes = int(max(256 * 1024**2, context * concurrency * max(params_b, 1.0) * 16384))
        node_vram = int(((node or {}).get("hardware") or {}).get("total_vram_bytes") or 0)
        if node is not None and node_vram <= 0:
            vram = 0
            host = int(model_bytes * 1.12 + kv_bytes + 512 * 1024**2)
        else:
            residency = max(0.05, min(1.0, float(model.get("vram_residency_fraction") or 0.90)))
            vram = int(model_bytes * residency + kv_bytes)
            host = int(max(512 * 1024**2, model_bytes * (1.0 - residency) * 1.20))
        return {
            "model_bytes": model_bytes,
            "kv_cache_bytes": kv_bytes,
            "vram_bytes": vram,
            "host_ram_bytes": host,
            "disk_bytes": int(model_bytes * 1.05),
        }

    def _select_backend(
        self,
        node: JsonDict,
        model: JsonDict,
        requested: str,
        *,
        workload: str = "chat",
    ) -> str | None:
        installed = {str(item) for item in node["backends"]}
        registrations = self.backend_host.all()
        names = [requested] if requested != "auto" else sorted(installed)
        ranked: list[tuple[float, str]] = []
        for name in names:
            if name not in installed:
                continue
            registration = registrations.get(name)
            if registration is None or not registration.enabled:
                continue
            manifest = registration.adapter.manifest
            capability = manifest.capability
            fmt = str(model.get("format") or "").lower()
            quantization = str(model.get("quantization") or "").lower()
            architecture = str(model.get("architecture") or model.get("model_type") or "unknown").lower()
            if fmt not in {item.lower() for item in capability.formats}:
                continue
            advertised_quantizations = {item.lower() for item in capability.quantizations}
            if quantization and advertised_quantizations and not (
                quantization in advertised_quantizations
                or any(quantization.startswith(f"{item}_") for item in advertised_quantizations)
            ):
                continue
            if not self.backend_host._task_supported(capability.tasks, workload):
                continue
            if "*" not in capability.architectures and architecture not in {
                item.lower() for item in capability.architectures
            }:
                continue
            hardware = node.get("hardware") or {}
            has_accelerator = int(hardware.get("total_vram_bytes") or 0) > 0
            accelerators = {item.lower() for item in capability.accelerators}
            if has_accelerator:
                accelerator_match = bool(accelerators.intersection({"cuda", "rocm", "metal", "vulkan", "xpu"}))
            else:
                accelerator_match = "cpu" in accelerators or "cpu_limited" in accelerators
            if accelerators and not accelerator_match:
                continue
            score = 0.60
            score += 0.12 if accelerator_match else 0.0
            score += 0.08 if capability.streaming else 0.0
            score += 0.08 if capability.multi_gpu and len(node.get("gpu_devices") or []) > 1 else 0.0
            score += 0.07 if manifest.evidence_status in ("verified_local", "verified_physical", "production") else 0.0
            score += self.backend_host._workload_bonus(name, workload)
            ranked.append((score, name))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return ranked[0][1] if ranked else None

    def _simulate_benchmark(self, instance: JsonDict, node: JsonDict, tuning: JsonDict) -> JsonDict:
        params_b = max(0.5, float((instance.get("model") or {}).get("parameters_b") or 7.0))
        vram_gb = float(node["hardware"]["total_vram_bytes"]) / _GIB
        cpu_threads = max(1, int(node["hardware"].get("cpu_threads") or 8))
        backend_factor = self._emulated_backend_factor(str(instance["backend"]))
        accelerator = math.sqrt(max(vram_gb, 0.25) / 8.0) if vram_gb else 0.16 * math.sqrt(cpu_threads / 8.0)
        batch = int(tuning.get("batch") or tuning.get("max_num_batched_tokens") or 512)
        optimal_batch = 512 if vram_gb <= 10.0 else 1024
        batch_factor = max(0.72, 1.0 - abs(batch - optimal_batch) / max(optimal_batch, 1) * 0.18)
        context = int((instance.get("serving") or {}).get("context_length") or 4096)
        context_factor = max(0.60, 1.0 - max(0, context - 4096) / 65536.0)
        tps = max(0.15, 11.5 * backend_factor * accelerator * (7.0 / params_b) * batch_factor * context_factor)
        ttft = max(0.05, params_b / max(1.0, vram_gb * backend_factor) * 0.42)
        return {
            "instance_id": instance["instance_id"],
            "service": instance["service"],
            "node": node["name"],
            "backend": instance["backend"],
            "decode_tokens_per_second": round(tps, 3),
            "time_to_first_token_seconds": round(ttft, 3),
            "model_load_seconds": round(params_b * 0.65 / max(backend_factor, 0.1), 3),
            "usability": "interactive" if tps >= 5.0 else "usable" if tps >= 1.0 else "unusable",
            "simulated": True,
            "tuning": dict(tuning),
        }

    def _emulated_backend_factor(self, backend: str) -> float:
        registration = self.backend_host.all().get(backend)
        if registration is None or not registration.enabled:
            return 0.65
        manifest = registration.adapter.manifest
        features = {item.lower() for item in manifest.capability.features}
        factor = 0.78
        if "continuous-batching" in features:
            factor += 0.12
        if features.intersection({"paged-attention", "radix-prefix-cache"}):
            factor += 0.10
        if features.intersection({"tensor-parallel", "tensor-split"}):
            factor += 0.05
        if "unified-memory" in features:
            factor += 0.03
        if manifest.evidence_status in ("verified_local", "verified_physical", "production"):
            factor += 0.05
        return min(1.30, factor)

    def _tuning_candidates(self, backend: str, baseline: JsonDict, node: JsonDict) -> list[JsonDict]:
        candidates = [dict(baseline)]
        if backend == "llama.cpp":
            for batch in (256, 512, 1024):
                candidate = dict(baseline)
                candidate.update({"batch": batch, "ubatch": min(256, batch)})
                candidates.append(candidate)
        else:
            for batch in (512, 1024, 2048):
                candidate = dict(baseline)
                candidate.update(
                    {
                        "max_num_batched_tokens": batch,
                        "gpu_memory_utilization": 0.82
                        if int(node["hardware"]["total_vram_bytes"]) <= 10 * _GIB
                        else 0.90,
                    }
                )
                candidates.append(candidate)
        unique = []
        seen = set()
        for candidate in candidates:
            key = json.dumps(candidate, sort_keys=True)
            if key not in seen:
                seen.add(key)
                unique.append(candidate)
        return unique

    def _normalize_node(self, node: JsonDict) -> JsonDict:
        hardware = dict(node.get("hardware") or {})
        vram_gb = float(hardware.get("vram_gb") or 0.0)
        ram_gb = float(hardware.get("ram_gb") or 0.0)
        disk_gb = float(hardware.get("disk_free_gb") or 0.0)
        hardware.update(
            {
                "total_vram_bytes": int(hardware.get("total_vram_bytes") or vram_gb * _GIB),
                "total_host_ram_bytes": int(
                    hardware.get("total_host_ram_bytes") or ram_gb * _GIB
                ),
                "disk_free_bytes": int(hardware.get("disk_free_bytes") or disk_gb * _GIB),
                "cpu_threads": int(hardware.get("cpu_threads") or 8),
                "cuda_available": bool(
                    hardware.get("cuda_available", vram_gb > 0.0)
                ),
            }
        )
        backends_value = node.get("backends") or []
        if isinstance(backends_value, dict):
            backends = sorted(
                name
                for name, value in backends_value.items()
                if value is True or (isinstance(value, dict) and value.get("available"))
            )
        else:
            backends = sorted(str(value) for value in backends_value)
        return {
            "name": str(node.get("name") or ""),
            "host": str(node.get("host") or node.get("name") or ""),
            "ready": str(node.get("status") or "ready").lower() == "ready",
            "status": str(node.get("status") or "ready").lower(),
            "hardware": hardware,
            "backends": backends,
            "labels": dict(node.get("labels") or {}),
            "model_cache": list(node.get("model_cache") or []),
            "reliability": float(node.get("reliability") or 0.95),
            "network_reachable": bool(node.get("network_reachable", True)),
            "transport": str(node.get("transport") or "emulated"),
            "agent": dict(node.get("agent") or {}),
            "transport_config": dict(node.get("transport_config") or {}),
        }

    def _validate_config(self, config: JsonDict) -> None:
        if not isinstance(config, dict):
            raise ValueError("cluster config must be an object")
        if str(config.get("mode") or "emulated") not in ("emulated", "remote"):
            raise ValueError("cluster mode must be emulated or remote")
        if not isinstance(config.get("nodes"), list) or not config["nodes"]:
            raise ValueError("cluster config requires nodes")
        names = [str(node.get("name") or "") for node in config["nodes"]]
        if any(not name for name in names) or len(set(names)) != len(names):
            raise ValueError("cluster node names must be non-empty and unique")
        if not isinstance(config.get("services"), dict) or not config["services"]:
            raise ValueError("cluster config requires services")
        for name, service in config["services"].items():
            if not isinstance(service.get("model"), dict):
                raise ValueError(f"cluster service {name} requires model")
            fmt = str(service["model"].get("format") or "").lower()
            supported_formats = {
                item.lower()
                for registration in self.backend_host.all().values()
                if registration.enabled
                for item in registration.adapter.manifest.capability.formats
            }
            if not fmt or fmt not in supported_formats:
                raise ValueError(
                    f"cluster service {name} format {fmt or 'missing'} is not advertised by an enabled backend adapter"
                )
            if int(service.get("replicas") or 1) <= 0:
                raise ValueError(f"cluster service {name} replicas must be positive")

    def _read_state(self, *, required: bool = False) -> JsonDict:
        state = self.state_store.read()
        if not state and not self.state_path.is_file():
            if required:
                raise ValueError("cluster state does not exist; run cluster apply first")
            return {}
        return state

    def _write_state(self, state: JsonDict) -> None:
        state["updated_unix_seconds"] = int(time.time())
        self.state_store.write(state)

    def _timestamped_report(self, stem: str) -> Path:
        return self.rift_dir / "reports" / f"{int(time.time())}-{stem}.json"

    def _resolve(self, path: str | Path) -> Path:
        target = Path(path)
        return target if target.is_absolute() else self.root / target

    def _write_json(self, path: Path, payload: JsonDict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _fingerprint(self, payload: Any) -> str:
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()


def example_emulated_cluster() -> JsonDict:
    """Return a three-node acceptance scenario for docs and CLI users."""

    return {
        "version": 1,
        "mode": "emulated",
        "nodes": [
            {
                "name": "laptop-4060",
                "hardware": {
                    "vram_gb": 8,
                    "ram_gb": 16,
                    "disk_free_gb": 60,
                    "cpu_threads": 16,
                },
                "backends": ["llama.cpp"],
                "labels": {"zone": "desk-a", "class": "consumer"},
                "model_cache": ["Qwen/Qwen2.5-7B-Instruct-GGUF"],
            },
            {
                "name": "workstation-4090",
                "hardware": {
                    "vram_gb": 24,
                    "ram_gb": 64,
                    "disk_free_gb": 240,
                    "cpu_threads": 32,
                },
                "backends": ["llama.cpp", "vllm", "sglang"],
                "labels": {"zone": "desk-b", "class": "cuda"},
                "model_cache": ["org/coder-14b-awq"],
            },
            {
                "name": "cpu-edge",
                "hardware": {
                    "vram_gb": 0,
                    "ram_gb": 32,
                    "disk_free_gb": 120,
                    "cpu_threads": 24,
                    "cuda_available": False,
                },
                "backends": ["llama.cpp"],
                "labels": {"zone": "desk-c", "class": "cpu"},
            },
        ],
        "services": {
            "chat": {
                "replicas": 2,
                "model": {
                    "id": "Qwen/Qwen2.5-7B-Instruct-GGUF",
                    "format": "gguf",
                    "parameters_b": 7.0,
                    "estimated_bytes": int(4.7 * _GIB),
                },
                "serving": {"context_length": 4096, "concurrency": 1},
                "policy": {"backend": "auto"},
            },
            "coder": {
                "replicas": 1,
                "model": {
                    "id": "org/coder-14b-awq",
                    "format": "awq",
                    "parameters_b": 14.0,
                    "estimated_bytes": int(8.2 * _GIB),
                },
                "serving": {"context_length": 8192, "concurrency": 2},
                "policy": {"backend": "vllm"},
                "placement": {"required_labels": {"class": "cuda"}},
            },
        },
    }
