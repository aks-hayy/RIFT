"""Terraform-style RIFT orchestration layer."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import statistics
import subprocess
import tempfile
import time
from typing import Any, Callable
from urllib.parse import unquote, urlparse, urlsplit
import uuid

from .adapters.artifacts import source_from_candidate, source_from_local
from .adapters.contracts import AdapterManifest
from .artifacts import ArtifactManifest
from .adapters.converters import converter_adapter_host
from .benchmarking import BenchmarkSuite, summarize_samples
from .evidence import EvidenceEngine
from .governance import GovernancePolicy, deployment_manifest, write_deployment_manifest
from .hf_hub import HfHubClient
from .observability import ObservabilityStore
from .providers import (
    backend_adapter_host,
    overlay_registry,
    provider_lifecycle_gate,
)
from .release import DiagnosticBundle, migrate_config, migrate_state
from .recommendations import RecommendationStore
from .rift import RiftEngine
from .rift_yaml import read_yaml, write_yaml
from .system_profile import HardwareAnalyzer
from .state_store import StateStore
from .runtime_paths import RiftPaths
from .telemetry import ResourcePolicy, TelemetryStore, TelemetrySupervisor


JsonDict = dict[str, Any]
ApplyProgressCallback = Callable[[str, str, JsonDict], None]
_TELEMETRY_RUNTIMES: dict[str, tuple[TelemetryStore, TelemetrySupervisor | None]] = {}


@dataclass
class ApplyPermissions:
    allow_download: bool = False
    allow_install: bool = False
    allow_launch: bool = False
    allow_remote: bool = False
    optimize: bool = False
    write_back: bool = False


class RiftOrchestrator:
    """Declarative RIFT control plane over model/backends/services."""

    def __init__(
        self,
        root: str | Path | None = None,
        engine: RiftEngine | None = None,
        runtime_root: str | Path | None = None,
    ) -> None:
        self.root = Path(root).resolve() if root else Path.cwd().resolve()
        self._config_warnings: list[str] = []
        if runtime_root is not None:
            self.rift_dir = Path(runtime_root).expanduser().resolve()
        elif root is None:
            self.rift_dir = RiftPaths.from_environment(cwd=self.root).home
        else:
            self.rift_dir = self.root / ".rift"
        self.state_store = StateStore(
            self.rift_dir / "state.db",
            legacy_path=self.rift_dir / "state.json",
        )
        self.engine = engine or RiftEngine(root=self.root, runtime_root=self.rift_dir)
        self.backend_host = backend_adapter_host()
        self.converter_host = converter_adapter_host()
        self.providers = self.backend_host.enabled()
        self.overlays = overlay_registry()
        self.observability_store = ObservabilityStore(root=self.root, data_root=self.rift_dir)
        self._telemetry_store: TelemetryStore | None = None
        self._telemetry_supervisor: TelemetrySupervisor | None = None
        self._telemetry_ephemeral = str(self.root).lower().startswith(
            str(Path(tempfile.gettempdir())).lower()
        )
        self._telemetry_registry_key = (
            None if self._telemetry_ephemeral else str(self.rift_dir.resolve())
        )
        self.evidence_engine = EvidenceEngine(root=self.root, data_root=self.rift_dir)
        self.artifacts = ArtifactManifest(root=self.root)
        self.recommendation_store = RecommendationStore(self.rift_dir)
        from .gateway import ApiKeyStore

        self.api_keys = ApiKeyStore(self.rift_dir / "gateway" / "api_keys.json")

    @property
    def telemetry_store(self) -> TelemetryStore:
        if self._telemetry_store is None:
            # Test/fake orchestrators frequently use a short-lived temporary
            # root on Windows. An in-memory store avoids holding a SQLite file
            # handle across TemporaryDirectory cleanup while preserving the
            # durable on-disk store for every real controller/node.
            if self._telemetry_registry_key and self._telemetry_registry_key in _TELEMETRY_RUNTIMES:
                self._telemetry_store = _TELEMETRY_RUNTIMES[self._telemetry_registry_key][0]
            else:
                path: str | Path = ":memory:" if self._telemetry_ephemeral else self.rift_dir / "telemetry" / "telemetry.db"
                self._telemetry_store = TelemetryStore(path)
                if self._telemetry_registry_key:
                    _TELEMETRY_RUNTIMES[self._telemetry_registry_key] = (self._telemetry_store, None)
        return self._telemetry_store

    @property
    def telemetry_supervisor(self) -> TelemetrySupervisor:
        if self._telemetry_supervisor is None:
            if self._telemetry_registry_key and self._telemetry_registry_key in _TELEMETRY_RUNTIMES:
                store, supervisor = _TELEMETRY_RUNTIMES[self._telemetry_registry_key]
                self._telemetry_supervisor = supervisor or TelemetrySupervisor(
                    store, interval_seconds=2.0, node_id="local", policy=ResourcePolicy()
                )
                _TELEMETRY_RUNTIMES[self._telemetry_registry_key] = (store, self._telemetry_supervisor)
            else:
                self._telemetry_supervisor = TelemetrySupervisor(
                    self.telemetry_store,
                    interval_seconds=2.0,
                    node_id="local",
                    policy=ResourcePolicy(),
                )
        return self._telemetry_supervisor

    def close(self) -> None:
        if not self._telemetry_ephemeral:
            return
        if self._telemetry_supervisor is not None:
            self._telemetry_supervisor.close()
        if self._telemetry_store is not None:
            self._telemetry_store.close()

    def __del__(self) -> None:
        # Persistent controller/node runtimes share a registry-backed
        # supervisor. Ephemeral test/facade runtimes own their resources and
        # must release their sampler thread when the facade is collected.
        if getattr(self, "_telemetry_ephemeral", False):
            try:
                self.close()
            except (AttributeError, RuntimeError):
                pass

    def init_config(self, path: str | Path = "rift.yaml", *, overwrite: bool = False) -> JsonDict:
        target = self.root / path
        if target.exists() and not overwrite:
            return {"created": False, "path": str(target), "reason": "config already exists"}
        config = self.default_config()
        write_yaml(target, config)
        return {"created": True, "path": str(target), "config": config}

    def default_config(self) -> JsonDict:
        return {
            "schema_version": 1,
            "version": 1,
            "project": "rift-local",
            "observability": {
                "telemetry": {
                    "enabled": True,
                    "sample_interval_seconds": 2.0,
                    "raw_retention_hours": 48,
                    "rollup_retention_days": 90,
                    "report_retention_days": 365,
                    "electricity_price_per_kwh": None,
                    "compute_cost_per_node_hour": None,
                    "prometheus": {"enabled": True},
                    "otlp": {"enabled": False, "endpoint": None},
                }
            },
            "nodes": [
                {
                    "name": "local",
                    "host": "localhost",
                    "role": "edge",
                    "backend_policy": "auto",
                }
            ],
            "services": {
                "chat": {
                    "task": "chat",
                    "model": {
                        "source": "huggingface",
                        "id": "auto",
                        "max_download_gb": 12,
                    },
                    "serving": {
                        "api": "openai",
                        "host": "127.0.0.1",
                        "port": 11735,
                        "context_length": 8192,
                        "concurrency": 1,
                    },
                    "policy": {
                        "backend": "auto",
                        "allow_download": False,
                        "allow_install": False,
                        "license_mode": "warn",
                    },
                    "monitoring": {
                        "enabled": True,
                        "resources": {
                            "enabled": True,
                            "sample_interval_seconds": 2.0,
                            "electricity_price_per_kwh": None,
                            "compute_cost_per_node_hour": None,
                        },
                        "health_timeout_seconds": 2.0,
                        "startup_grace_seconds": 180.0,
                        "failure_threshold": 3,
                        "history_limit": 100,
                    },
                    "recovery": {
                        "enabled": True,
                        "max_restarts": 3,
                        "backoff_seconds": 2.0,
                        "max_backoff_seconds": 60.0,
                        "reset_after_healthy_seconds": 300.0,
                        "rollback_to_last_known_good": True,
                    },
                    "evaluation": {
                        "enabled": True,
                        "required": False,
                        "retain_responses": False,
                        "max_tokens": 128,
                        "deadline_seconds": 60.0,
                    },
                    "gateway": {
                        "enabled": True,
                        "host": "127.0.0.1",
                        "port": 11734,
                        "fallback_services": [],
                        "request_timeout_seconds": 120.0,
                        "max_concurrent_requests": 2,
                        "requests_per_minute": 60,
                        "burst_requests_per_second": 4,
                        "max_prompt_tokens": 8192,
                        "max_completion_tokens": 1024,
                        "max_total_tokens": 9216,
                        "max_body_bytes": 4 * 1024 * 1024,
                        "api_key_env": "RIFT_GATEWAY_API_KEYS",
                    },
                }
            },
        }

    def load_config(self, path: str | Path = "rift.yaml") -> JsonDict:
        config = read_yaml(self._resolve_path(path))
        self._config_warnings = []
        if "schema_version" not in config:
            config["schema_version"] = int(config.get("version") or 1)
            self._config_warnings.append(
                "legacy config is missing schema_version; run `rift system migrate --write`"
            )
        self.validate_config(config)
        return config

    def validate_config(self, config: JsonDict) -> None:
        if not isinstance(config, dict):
            raise ValueError("rift config must be an object")
        schema_version = int(config.get("schema_version") or 1)
        if schema_version > 2:
            raise ValueError(f"rift config schema {schema_version} is newer than supported 2")
        if not isinstance(config.get("nodes"), list) or not config["nodes"]:
            raise ValueError("rift config requires at least one node")
        if not isinstance(config.get("services"), dict) or not config["services"]:
            raise ValueError("rift config requires at least one service")
        telemetry = (config.get("observability") or {}).get("telemetry") or {}
        if not isinstance(telemetry, dict):
            raise ValueError("observability.telemetry must be an object")
        for key in ("electricity_price_per_kwh", "compute_cost_per_node_hour"):
            self._validate_accounting_rate(key, telemetry.get(key))
        for name, service in config["services"].items():
            if not isinstance(service, dict):
                raise ValueError(f"service {name} must be an object")
            if not isinstance(service.get("model"), dict):
                raise ValueError(f"service {name} requires model")
            if not isinstance(service.get("serving"), dict):
                raise ValueError(f"service {name} requires serving")
            monitoring = service.get("monitoring") or {}
            recovery = service.get("recovery") or {}
            gateway = service.get("gateway") or {}
            if not isinstance(monitoring, dict):
                raise ValueError(f"service {name} monitoring must be an object")
            if not isinstance(recovery, dict):
                raise ValueError(f"service {name} recovery must be an object")
            if not isinstance(gateway, dict):
                raise ValueError(f"service {name} gateway must be an object")
            resources = monitoring.get("resources") or {}
            if not isinstance(resources, dict):
                raise ValueError(f"service {name} monitoring.resources must be an object")
            for key in ("electricity_price_per_kwh", "compute_cost_per_node_hour"):
                self._validate_accounting_rate(key, resources.get(key))
            if float(resources.get("sample_interval_seconds", 2.0)) <= 0.0:
                raise ValueError(f"service {name} resource sample_interval_seconds must be positive")
            if float(monitoring.get("health_timeout_seconds", 2.0)) <= 0.0:
                raise ValueError(f"service {name} health_timeout_seconds must be positive")
            if float(monitoring.get("startup_grace_seconds", 180.0)) < 0.0:
                raise ValueError(f"service {name} startup_grace_seconds cannot be negative")
            if int(monitoring.get("failure_threshold", 3)) <= 0:
                raise ValueError(f"service {name} failure_threshold must be positive")
            if int(monitoring.get("history_limit", 100)) <= 0:
                raise ValueError(f"service {name} history_limit must be positive")
            if int(recovery.get("max_restarts", 3)) < 0:
                raise ValueError(f"service {name} max_restarts cannot be negative")
            if float(recovery.get("backoff_seconds", 2.0)) < 0.0:
                raise ValueError(f"service {name} backoff_seconds cannot be negative")
            if float(recovery.get("max_backoff_seconds", 60.0)) < 0.0:
                raise ValueError(f"service {name} max_backoff_seconds cannot be negative")
            if bool(gateway.get("enabled", True)):
                gateway_port = int(gateway.get("port", 11734))
                if not 1 <= gateway_port <= 65535:
                    raise ValueError(f"service {name} gateway port must be between 1 and 65535")
                if int(gateway.get("max_concurrent_requests", 2)) <= 0:
                    raise ValueError(f"service {name} gateway max_concurrent_requests must be positive")
                if float(gateway.get("request_timeout_seconds", 120.0)) <= 0.0:
                    raise ValueError(f"service {name} gateway request_timeout_seconds must be positive")
                if int(gateway.get("requests_per_minute", 60)) < 0:
                    raise ValueError(f"service {name} gateway requests_per_minute cannot be negative")
                if int(gateway.get("burst_requests_per_second", 4)) < 0:
                    raise ValueError(f"service {name} gateway burst_requests_per_second cannot be negative")
                token_limits = [
                    int(gateway.get("max_prompt_tokens", 8192)),
                    int(gateway.get("max_completion_tokens", 1024)),
                    int(gateway.get("max_total_tokens", 9216)),
                ]
                if min(token_limits) <= 0:
                    raise ValueError(f"service {name} gateway token limits must be positive")

    def discover(
        self,
        *,
        local: bool = True,
        cluster_config: str | None = None,
        models_dir: str | None = None,
        allow_remote: bool = False,
        write: bool = True,
    ) -> JsonDict:
        nodes = []
        if local:
            hardware = HardwareAnalyzer(root=self.root, data_root=self.rift_dir).analyze(
                self.engine.hardware_profile(), state=self.read_state()
            )
            nodes.append(
                {
                    "name": "local",
                    "host": "localhost",
                    "role": "edge",
                    "hardware": hardware,
                    "backends": self.detect_backends(),
                    "models": self.scan_local_models(models_dir) if models_dir else [],
                    "fingerprint": self._fingerprint({"hardware": hardware}),
                }
            )
        if cluster_config:
            cluster = read_yaml(self._resolve_path(cluster_config))
            for node in cluster.get("nodes", []):
                if str(node.get("host")) == "localhost":
                    continue
                nodes.append(
                    {
                        "name": node.get("name"),
                        "host": node.get("host"),
                        "role": node.get("role", "remote"),
                        "remote": True,
                        "status": "remote_allowed" if allow_remote else "requires --allow-remote",
                        "hardware": node.get("hardware", {}),
                        "backends": node.get("backends", {}),
                    }
                )
        result = {
            "rift_product": "RIFT",
            "schema_version": 1,
            "created_unix_seconds": int(time.time()),
            "nodes": nodes,
        }
        if write:
            self._write_json(self._timestamped("discovery", "discovery"), result)
            self._write_json(self.rift_dir / "discovery" / "latest.json", result)
        return result

    def detect_backends(self) -> JsonDict:
        return {
            name: self._provider_probe(provider, name)
            for name, provider in self.providers.items()
        }

    def scan_local_models(self, models_dir: str | None) -> list[JsonDict]:
        if not models_dir:
            return []
        root = Path(models_dir)
        if not root.exists():
            raise ValueError(f"models_dir does not exist: {root}")
        models: list[JsonDict] = []
        inspected_roots: set[str] = set()
        candidates = [root]
        if root.is_dir():
            candidates.extend(item for item in root.iterdir() if item.is_dir())
        for candidate in candidates:
            key = str(candidate.resolve())
            if key in inspected_roots:
                continue
            inspected_roots.add(key)
            try:
                source = source_from_local(candidate)
                variants = self.engine.artifact_adapters.resolve(source)
            except (OSError, ValueError):
                continue
            for variant in variants:
                weight_files = [item for item in variant.files if item.role == "weights"]
                selected_path = candidate.resolve()
                if len(weight_files) == 1 and candidate.is_dir() and variant.format == "gguf":
                    selected_path = (candidate / weight_files[0].path).resolve()
                models.append(
                    {
                        "path": str(selected_path),
                        "name": selected_path.name,
                        "format": variant.format,
                        "quantization": variant.quantization,
                        "size": variant.total_bytes,
                        "artifact": variant.to_dict(),
                    }
                )
        models.sort(key=lambda item: (str(item.get("format")), int(item.get("size") or 0), str(item.get("path"))))
        return models

    def rank_local_models(self, models_dir: str | Path, *, task: str = "chat") -> JsonDict:
        """Inspect and rank local artifacts without creating deployment state."""

        discovery = self.discover(local=True, models_dir=str(models_dir), write=False)
        hardware = discovery["nodes"][0]["hardware"]
        ranked: list[JsonDict] = []
        for item in discovery["nodes"][0].get("models", []):
            artifact = dict(item.get("artifact") or {})
            model = {**item, **artifact}
            decision = self._select_provider_for_model(
                model=model,
                hardware=hardware,
                requested="auto",
                workload=task,
            )
            backend = str(decision.get("backend") or "")
            winner = next(
                (
                    candidate for candidate in decision.get("candidates", [])
                    if candidate.get("backend") == backend
                ),
                None,
            )
            fit = bool(winner and winner.get("fits"))
            score = float(winner.get("score") or 0.0) if winner else 0.0
            score += self._artifact_local_preference(item) if fit else 0.0
            reasons = []
            if backend:
                reasons.append(f"{backend} is the strongest compatible backend adapter")
            if winner and winner.get("reason"):
                reasons.append(str(winner["reason"]))
            if not fit:
                reasons.append(str(decision.get("reason") or "No compatible backend accepted this artifact"))
            ranked.append(
                {
                    "path": item.get("path"),
                    "name": item.get("name") or Path(str(item.get("path") or "model")).name,
                    "task": task,
                    "format": item.get("format"),
                    "quantization": item.get("quantization"),
                    "size_bytes": item.get("size"),
                    "backend": backend or None,
                    "score": round(score, 6),
                    "fits": fit,
                    "evidence": "LOCAL_INSPECTION",
                    "reasons": reasons[:4],
                    "artifact": artifact,
                    "provider_decision": decision,
                }
            )
        ranked.sort(
            key=lambda item: (
                not bool(item.get("fits")),
                -float(item.get("score") or 0.0),
                int(item.get("size_bytes") or 0),
                str(item.get("path") or ""),
            )
        )
        return {"task": task, "hardware": hardware, "candidates": ranked}

    @staticmethod
    def normalize_huggingface_repo(value: str) -> str:
        """Normalize a Hub repository ID or common Hugging Face URL form."""

        raw = str(value or "").strip()
        if not raw:
            raise ValueError("Hugging Face repository or URL is required")
        if "://" not in raw:
            repo = raw.strip("/")
        else:
            parsed = urlparse(raw)
            if parsed.netloc.lower() not in {"huggingface.co", "www.huggingface.co"}:
                raise ValueError("Hugging Face URL must use huggingface.co")
            parts = [unquote(item) for item in parsed.path.strip("/").split("/") if item]
            if parts[:2] == ["api", "models"]:
                parts = parts[2:]
            for marker in ("tree", "resolve", "blob"):
                if marker in parts:
                    parts = parts[:parts.index(marker)]
                    break
            repo = "/".join(parts)
        if len(repo.split("/")) != 2 or any(not part for part in repo.split("/")):
            raise ValueError("Hugging Face input must look like `owner/model` or a model URL")
        return repo

    def generate_huggingface_config(
        self,
        *,
        repo_or_url: str,
        task: str = "chat",
        revision: str = "main",
        endpoint: str = "https://huggingface.co",
        refresh: bool = False,
        output: str | Path | None = None,
        selector: str | None = None,
        write: bool = True,
    ) -> JsonDict:
        """Inspect one Hub repository and materialize its best deployable artifact."""

        repo_id = self.normalize_huggingface_repo(repo_or_url)
        info = HfHubClient(endpoint=endpoint).model_info(
            repo_id,
            revision=revision,
            expand=("siblings", "config", "tags", "safetensors"),
            refresh=refresh,
        )
        info.setdefault("id", repo_id)
        source = source_from_candidate(info)
        if not source.get("files"):
            source["files"] = [
                {"path": item.path, "size": item.size}
                for item in HfHubClient(endpoint=endpoint).list_model_files(repo_id, revision=revision, refresh=refresh)
            ]
        variants = self.engine.artifact_adapters.resolve(source)
        if not variants:
            raise ValueError(f"Hub repository {repo_id} exposes no supported model artifact")
        discovery = self.discover(local=True, write=False)
        hardware = discovery["nodes"][0]["hardware"]
        ranked: list[JsonDict] = []
        for variant in variants:
            artifact = variant.to_dict()
            model = {
                **artifact,
                "format": variant.format,
                "quantization": variant.quantization,
                "architecture": variant.architecture,
                "config": source.get("config") or {},
                "artifact": artifact,
            }
            decision = self._select_provider_for_model(
                model=model,
                hardware=hardware,
                requested="auto",
                workload=task,
            )
            backend = str(decision.get("backend") or "")
            winner = next(
                (
                    candidate for candidate in decision.get("candidates", [])
                    if candidate.get("backend") == backend
                ),
                None,
            )
            weights = [item for item in variant.files if item.role == "weights"]
            selected_files = [item.path for item in variant.files]
            ranked.append(
                {
                    "repo_id": repo_id,
                    "revision": str(info.get("sha") or revision),
                    "selected_file": weights[0].path if weights else None,
                    "selected_files": selected_files,
                    "format": variant.format,
                    "quantization": variant.quantization,
                    "architecture": variant.architecture,
                    "artifact": artifact,
                    "size_bytes": variant.metadata.get("total_download_bytes") or variant.total_bytes,
                    "backend": backend or None,
                    "score": round(float(winner.get("score") or 0.0), 6) if winner else 0.0,
                    "fits": bool(winner and winner.get("fits")),
                    "evidence": "HUB_METADATA",
                    "reasons": [
                        f"{variant.format.upper()} artifact inspected from {repo_id}",
                        str(winner.get("reason") if winner else decision.get("reason") or "No compatible backend accepted this artifact"),
                    ],
                    "provider_decision": decision,
                }
            )
        ranked.sort(
            key=lambda item: (
                not bool(item.get("fits")),
                -float(item.get("score") or 0.0),
                int(item.get("size_bytes") or 0),
                str(item.get("selected_file") or ""),
            )
        )
        selected = ranked[0]
        if selector:
            value = str(selector).strip()
            if value.isdigit() and 1 <= int(value) <= len(ranked):
                selected = ranked[int(value) - 1]
            else:
                selected = next(
                    (
                        item for item in ranked
                        if value in {
                            str(item.get("selected_file") or ""),
                            str(item.get("format") or ""),
                            str((item.get("artifact") or {}).get("artifact_id") or ""),
                        }
                    ),
                    None,
                )
                if selected is None:
                    raise ValueError(f"Hub artifact selector {value!r} was not found")
        backend = str(selected.get("backend") or "auto")
        service = self.default_config()["services"]["chat"]
        service["task"] = task
        service["model"].update(
            {
                "source": "huggingface",
                "endpoint": endpoint,
                "id": repo_id,
                "revision": selected.get("revision") or revision,
                "selected_file": selected.get("selected_file"),
                "selected_files": selected.get("selected_files") or [],
                "format": selected.get("format"),
                "quantization": selected.get("quantization"),
                "artifact": selected.get("artifact") or {},
                "estimated_download_bytes": selected.get("size_bytes") or 0,
                "decision": {
                    "reason": selected.get("reasons") or [],
                    "alternatives": [
                        {"id": item.get("selected_file"), "reason": "lower hardware-fit score"}
                        for item in ranked[1:8]
                    ],
                },
            }
        )
        service["policy"]["backend"] = backend
        service["placement"] = {
            "node": "local",
            "decision": {
                "reason": ["local node is the selected execution target", f"{backend} selected for Hub artifact compatibility"],
                "rejected_nodes": [],
            },
        }
        config = self.default_config()
        config["project"] = f"rift-{task}-{repo_id.replace('/', '--')}"
        config["nodes"][0]["hardware_summary"] = self._hardware_summary(hardware)
        config["services"] = {"chat": service}
        output_path = self._resolve_path(
            output or self.rift_dir / "generated" / f"hub-{repo_id.replace('/', '--')}.yaml"
        )
        if write:
            write_yaml(output_path, config)
        return {
            "path": str(output_path),
            "config": config,
            "task": task,
            "repo_id": repo_id,
            "revision": selected.get("revision") or revision,
            "hardware": hardware,
            "candidates": ranked,
            "selected": selected,
        }

    def generate_config(
        self,
        *,
        task: str = "chat",
        source: str = "huggingface",
        models_dir: str | None = None,
        endpoint: str = "https://huggingface.co",
        output: str | Path = ".rift/generated/rift.generated.yaml",
        top: int = 10,
        candidate_limit: int = 300,
        max_download_gb: float = 12.0,
        write: bool = True,
    ) -> JsonDict:
        discovery = self.discover(local=True, models_dir=models_dir, write=True)
        hardware = discovery["nodes"][0]["hardware"]
        service = self.default_config()["services"]["chat"]
        service["task"] = task
        alternatives: list[JsonDict] = []
        selected: JsonDict

        if source == "local":
            local_models = discovery["nodes"][0].get("models", [])
            if not local_models:
                raise ValueError("local source requires at least one recognized model artifact in --models-dir")
            ranked_local = []
            for item in local_models:
                decision = self._select_provider_for_model(
                    model={**item, **dict(item.get("artifact") or {})},
                    hardware=hardware,
                    requested="auto",
                    workload=task,
                )
                winner = next((candidate for candidate in decision.get("candidates", []) if candidate.get("backend") == decision.get("backend")), None)
                if winner:
                    artifact_score = self._artifact_local_preference(item)
                    ranked_local.append((float(winner.get("score") or 0.0) + artifact_score, item, decision))
            if not ranked_local:
                raise ValueError("no installed or installable backend adapter accepted the local artifacts")
            ranked_local.sort(key=lambda entry: (-entry[0], int(entry[1].get("size") or 0), str(entry[1].get("path"))))
            _, selected, local_decision = ranked_local[0]
            alternatives = [
                {"id": item[1]["path"], "format": item[1].get("format"), "reason": "lower adapter compatibility score"}
                for item in ranked_local[1:8]
            ]
            service["model"].update(
                {
                    "source": "local",
                    "id": selected["path"],
                    "selected_file": selected["path"],
                    "format": selected.get("format"),
                    "quantization": selected.get("quantization"),
                    "artifact": selected.get("artifact"),
                }
            )
            backend = str(local_decision.get("backend") or "auto")
        elif source in ("huggingface", "private"):
            recommendation = self.engine.recommend_models(
                task=task,
                top=top,
                candidate_limit=candidate_limit,
                max_download_gb=max_download_gb,
                endpoint=endpoint,
            )
            best = recommendation.get("best_for_hardware", {}).get("absolute_best")
            if not best:
                raise ValueError("no model recommendation was available")
            selected = best
            alternatives = [
                {"id": item["repo_id"], "reason": "ranked alternative"}
                for item in recommendation.get("recommendations", [])[1:8]
            ]
            service["model"].update(
                {
                    "source": source,
                    "endpoint": endpoint,
                    "id": best["repo_id"],
                    "selected_file": best.get("selected_file"),
                    "selected_files": best.get("selected_files", []),
                    "quantization": best.get("quantization"),
                    "artifact": best.get("artifact_selection"),
                    "disk_feasibility": best.get("disk_feasibility"),
                    "format": best.get("format"),
                    "max_download_gb": max_download_gb,
                }
            )
            backend = str(best.get("backend") or "auto")
        else:
            raise ValueError("source must be huggingface, private, or local")

        service["policy"]["backend"] = backend
        service["model"]["decision"] = {
            "reason": self._selection_reasons(selected, hardware, backend),
            "alternatives": alternatives,
        }
        service["placement"] = {
            "node": "local",
            "decision": {
                "reason": [
                    "local node is the only discovered executable target in this generation run",
                    f"{backend} selected for model/source compatibility",
                ],
                "rejected_nodes": [],
            },
        }
        config = self.default_config()
        config["project"] = f"rift-{task}"
        config["nodes"][0]["hardware_summary"] = self._hardware_summary(hardware)
        config["services"] = {"chat": service}
        output_path = self._resolve_path(output)
        result = {
            "path": str(output_path),
            "config": config,
            "discovery": discovery,
            "selected": selected,
        }
        if write:
            write_yaml(output_path, config)
            self._write_json(self.rift_dir / "generated" / "latest.json", result)
        return result

    def _selection_reasons(self, selected: JsonDict, hardware: JsonDict, backend: str) -> list[str]:
        reasons = []
        params = selected.get("parameters_b")
        if params:
            reasons.append(f"{params}B parameters is a practical quality/performance band for this node")
        if selected.get("format"):
            reasons.append(f"{selected['format']} format maps to backend {backend}")
        reasons.append(
            f"hardware fit uses {self._hardware_summary(hardware).get('vram_gb')} GB VRAM and {self._hardware_summary(hardware).get('ram_gb')} GB RAM"
        )
        for evidence in selected.get("evidence", [])[:3]:
            reasons.append(str(evidence))
        return reasons

    def materialize_recommendation_config(
        self,
        *,
        run_id: str,
        selector: str = "best_estimated",
        output: str | Path | None = None,
        write: bool = True,
        artifact_id: str | None = None,
        backend_kind: str | None = None,
        target_node_id: str | None = None,
        service_name: str = "chat",
        exposure: str = "local",
    ) -> JsonDict:
        """Turn one immutable recommendation candidate into deployable YAML intent."""

        run = self.recommendation_store.load_recommendation(run_id)
        recommendations = [
            dict(item) for item in run.get("recommendations", []) if isinstance(item, dict)
        ]
        if not recommendations:
            raise ValueError(f"recommendation run {run_id} contains no candidates")
        category = (run.get("categories") or {}).get(selector)
        selected: JsonDict | None = None
        if isinstance(category, dict):
            category_repo = str(category.get("repo_id") or "")
            category_artifact = str(category.get("artifact_id") or "")
            selected = next(
                (
                    item
                    for item in recommendations
                    if str(item.get("repo_id") or "") == category_repo
                    and (
                        not category_artifact
                        or str((item.get("selected_artifact") or {}).get("artifact_id") or "")
                        == category_artifact
                    )
                ),
                None,
            )
        if selected is None:
            selected = next(
                (
                    item
                    for item in recommendations
                    if selector
                    in {
                        str(item.get("repo_id") or ""),
                        str((item.get("model_identity") or {}).get("identity_id") or ""),
                        str((item.get("selected_artifact") or {}).get("artifact_id") or ""),
                    }
                ),
                None,
            )
        if selected is None and artifact_id:
            selected = next(
                (
                    item
                    for item in recommendations
                    if str(item.get("artifact_id") or "") == artifact_id
                    or str((item.get("selected_artifact") or {}).get("artifact_id") or "")
                    == artifact_id
                    or str((item.get("artifact_selection") or {}).get("artifact_id") or "")
                    == artifact_id
                ),
                None,
            )
        elif artifact_id and selected is not None:
            selected = next(
                (
                    item
                    for item in recommendations
                    if str(item.get("artifact_id") or "") == artifact_id
                    or str((item.get("selected_artifact") or {}).get("artifact_id") or "")
                    == artifact_id
                    or str((item.get("artifact_selection") or {}).get("artifact_id") or "")
                    == artifact_id
                ),
                None,
            )
        if selected is None and selector == "best_estimated":
            selected = recommendations[0]
        if selected is None:
            raise ValueError(f"selector {selector} was not found in recommendation run {run_id}")

        backend = str(backend_kind or selected.get("backend") or "")
        if not backend or backend == "none":
            raise ValueError("selected candidate does not have a deployable backend adapter")
        if backend not in self.providers:
            raise ValueError(f"requested backend adapter is not registered: {backend}")
        if exposure not in {"local", "lan", "public"}:
            raise ValueError("exposure must be local, lan, or public")
        if not str(service_name).strip():
            raise ValueError("service_name must not be empty")
        artifact = dict(selected.get("selected_artifact") or selected.get("artifact_selection") or {})
        total_bytes = int(
            artifact.get("total_bytes")
            or artifact.get("size")
            or selected.get("selected_download_bytes")
            or selected.get("estimated_download_bytes")
            or 0
        )
        artifact.setdefault("size", total_bytes)
        selected_files = [
            str(item) for item in selected.get("selected_files", []) if str(item).strip()
        ]
        if not selected_files and selected.get("selected_file"):
            selected_files = [str(selected["selected_file"])]
        hardware = dict(run.get("hardware_profile") or {})
        config = self.default_config()
        task = str(run.get("task") or "chat")
        config["project"] = f"rift-{task}-{run_id[:8]}"
        model_source = str(
            selected.get("source")
            or run.get("source")
            or (run.get("discovery") or {}).get("source")
            or "huggingface"
        )
        config["recommendation_run"] = {
            "id": run_id,
            "selector": selector,
            "contract": run.get("recommendation_contract"),
        }
        config["nodes"][0]["hardware_summary"] = self._hardware_summary(hardware)
        service = config["services"]["chat"]
        service["task"] = task
        service["model"].update(
            {
                "source": model_source,
                "endpoint": str((run.get("discovery") or {}).get("source") or "https://huggingface.co"),
                "id": str(selected.get("repo_id") or ""),
                "revision": str(selected.get("revision") or "main"),
                "selected_file": selected.get("selected_file"),
                "selected_files": selected_files,
                "format": selected.get("format"),
                "quantization": selected.get("quantization"),
                "parameters_b": selected.get("parameters_b"),
                "estimated_download_bytes": total_bytes,
                "max_download_gb": max(
                    1.0,
                    round(total_bytes / 1024**3 + 0.25, 3) if total_bytes else float(run.get("max_download_gb") or 12.0),
                ),
                "artifact": artifact,
                "disk_feasibility": selected.get("disk_feasibility") or {},
                "license": selected.get("license"),
                "gated": selected.get("gated"),
                "decision": {
                    "recommendation_run_id": run_id,
                    "selector": selector,
                    "score": selected.get("final_score"),
                    "confidence": selected.get("confidence"),
                    "reason": list(selected.get("evidence") or []),
                    "warnings": list(selected.get("warnings") or []),
                    "backend_candidates": list(selected.get("backend_candidates") or []),
                },
            }
        )
        service["policy"]["backend"] = backend
        service["placement"] = {
            "node": str(target_node_id or "local"),
            "decision": {
                "reason": [
                    f"candidate was selected by recommendation run {run_id}",
                    f"adapter {backend} won manifest-driven artifact and platform matching",
                ],
                "rejected_nodes": [],
            },
        }
        service["exposure"] = exposure
        service["serving"]["host"] = "127.0.0.1" if exposure == "local" else "0.0.0.0"
        service["gateway"]["host"] = "127.0.0.1" if exposure == "local" else "0.0.0.0"
        config["services"] = {service_name: service}
        target = self._resolve_path(
            output or self.plan_dir / f"recommendation-{run_id}.yaml"
        )
        result = {
            "materialized": True,
            "recommendation_run_id": run_id,
            "selector": selector,
            "artifact_id": artifact_id or str(
                artifact.get("artifact_id") or selected.get("artifact_id") or ""
            ),
            "backend_kind": backend,
            "target_node_id": str(target_node_id or "local"),
            "service_name": service_name,
            "exposure": exposure,
            "selected": selected,
            "config_path": str(target),
            "config": config,
        }
        if write:
            write_yaml(target, config)
            self._write_json(
                self.rift_dir / "generated" / f"recommendation-{run_id}.json", result
            )
        return result

    def plan_recommendation_run(
        self,
        *,
        run_id: str,
        selector: str = "best_estimated",
        output: str | Path | None = None,
        artifact_id: str | None = None,
        backend_kind: str | None = None,
        target_node_id: str | None = None,
        service_name: str = "chat",
        exposure: str = "local",
    ) -> JsonDict:
        materialized = self.materialize_recommendation_config(
            run_id=run_id,
            selector=selector,
            output=output,
            write=True,
            artifact_id=artifact_id,
            backend_kind=backend_kind,
            target_node_id=target_node_id,
            service_name=service_name,
            exposure=exposure,
        )
        plan = self.plan(config_path=materialized["config_path"], write=True)
        plan["recommendation_run_id"] = run_id
        plan["recommendation_selector"] = selector
        plan["materialized_config"] = materialized["config_path"]
        plan["artifact_id"] = materialized.get("artifact_id")
        plan["backend_kind"] = materialized.get("backend_kind")
        plan["target_node_id"] = materialized.get("target_node_id")
        plan["service_name"] = materialized.get("service_name")
        plan["exposure"] = materialized.get("exposure")
        plan["plan_hash"] = self._plan_hash(plan)
        if plan.get("plan_path"):
            self._write_json(Path(str(plan["plan_path"])), plan)
        self._write_json(self.rift_dir / "plans" / "latest.json", plan)
        self._write_json(self.plan_dir / "latest.json", plan)
        return plan

    def list_plans(self, *, limit: int = 50) -> JsonDict:
        """List saved deployment plans with concise operator-facing metadata."""

        if limit <= 0:
            raise ValueError("limit must be positive")
        sources = [(self.plan_dir, "REPOSITORY")]
        runtime_plan_dir = self.rift_dir / "plans"
        if runtime_plan_dir.resolve() != self.plan_dir.resolve():
            sources.append((runtime_plan_dir, "RUNTIME_LEGACY"))

        discovered: dict[str, tuple[Path, str]] = {}
        for directory, source in sources:
            if not directory.is_dir():
                continue
            for path in directory.glob("*.json"):
                if path.name == "latest.json":
                    continue
                discovered.setdefault(path.name, (path, source))

        plans: list[JsonDict] = []
        ordered = sorted(
            discovered.values(),
            key=lambda item: (item[1] != "REPOSITORY", -item[0].stat().st_mtime_ns),
        )
        seen_plan_ids: set[str] = set()
        for path, source in ordered:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            services = payload.get("services") or {}
            if not isinstance(services, dict):
                services = {}
            models: list[str] = []
            backends: list[str] = []
            for name, service in services.items():
                if not isinstance(service, dict):
                    continue
                model = service.get("model") or {}
                if not isinstance(model, dict):
                    model = {}
                label = str(model.get("id") or model.get("selected_file") or model.get("local_path") or "")
                if label:
                    models.append(f"{name}: {label}")
                backend = str(service.get("backend") or (service.get("policy") or {}).get("backend") or "")
                if backend and backend not in backends:
                    backends.append(backend)
            actions = payload.get("actions") or []
            if not isinstance(actions, list):
                actions = []
            blockers = [item for item in actions if isinstance(item, dict) and item.get("kind") == "error"]
            config_path = str(payload.get("materialized_config") or payload.get("config_path") or "")
            plan_id = str(payload.get("plan_id") or path.stem)
            if plan_id in seen_plan_ids:
                continue
            seen_plan_ids.add(plan_id)
            plans.append(
                {
                    "plan_id": plan_id,
                    "recommendation_run_id": payload.get("recommendation_run_id"),
                    "created_unix_seconds": payload.get("created_unix_seconds"),
                    "source": source,
                    "plan_path": str(path.resolve()),
                    "config_path": config_path,
                    "model": "; ".join(models) or "-",
                    "backend": ", ".join(backends) or "-",
                    "service_count": len(services),
                    "action_count": len(actions),
                    "blocker_count": len(blockers),
                    "status": "BLOCKED" if blockers else "READY",
                }
            )
            if len(plans) >= limit:
                break
        return {"root": str(self.plan_dir.resolve()), "count": len(plans), "plans": plans}

    def clear_plans(self) -> JsonDict:
        """Remove generated deployment-plan artifacts without touching runtime state.

        The repository-local plan directory is authoritative for normal CLI use. The
        runtime directory is also cleaned when it is separate so legacy mirrored plans
        cannot reappear in a later ``rift apply`` listing.
        """

        sources = [(self.plan_dir, "REPOSITORY")]
        runtime_plan_dir = self.rift_dir / "plans"
        if runtime_plan_dir.resolve() != self.plan_dir.resolve():
            sources.append((runtime_plan_dir, "RUNTIME_LEGACY"))

        removed: list[JsonDict] = []
        skipped: list[str] = []
        for directory, source in sources:
            if not directory.is_dir():
                continue
            for path in sorted(directory.iterdir(), key=lambda item: item.name.lower()):
                if not path.is_file() or path.is_symlink():
                    continue
                if not self._is_saved_plan_artifact(path, source=source):
                    skipped.append(str(path.resolve()))
                    continue
                path.unlink()
                removed.append({"path": str(path.resolve()), "source": source})

        return {
            "cleared": True,
            "plan_directory": str(self.plan_dir.resolve()),
            "removed_count": len(removed),
            "removed": removed,
            "skipped": sorted(skipped),
        }

    @staticmethod
    def _is_saved_plan_artifact(path: Path, *, source: str) -> bool:
        name = path.name.lower()
        if name == "latest.json" or name.endswith("-riftplan.json"):
            return True
        if source != "REPOSITORY":
            return False
        if path.suffix.lower() not in {".json", ".yaml", ".yml"}:
            return False
        return name.startswith("plan-") or name.startswith("recommendation-")

    def verify_recommendation_run(
        self,
        *,
        run_id: str,
        permissions: ApplyPermissions | None = None,
        finalists: int = 1,
        budget_seconds: float | None = None,
        prompt: str = "Reply briefly: what is one benefit of local language models?",
        max_tokens: int = 32,
        startup_timeout_seconds: float = 180.0,
        endpoint: str | None = None,
        token: str | None = None,
    ) -> JsonDict:
        """Run a bounded, sequential, permission-gated finalist tournament."""

        if finalists <= 0:
            raise ValueError("finalists must be positive")
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if startup_timeout_seconds <= 0.0:
            raise ValueError("startup_timeout_seconds must be positive")
        if budget_seconds is not None and budget_seconds < 0.0:
            raise ValueError("budget_seconds cannot be negative")
        permissions = permissions or ApplyPermissions()
        recommendation = self.recommendation_store.load_recommendation(run_id)
        candidates = [
            dict(item)
            for item in recommendation.get("recommendations", [])
            if isinstance(item, dict)
            and str(item.get("backend") or "") in self.providers
            and str(item.get("support_level") or "") != "UNSUPPORTED"
        ][:finalists]
        if not candidates:
            raise ValueError(f"recommendation run {run_id} has no verifiable candidates")
        verification_id = hashlib.sha256(
            f"{run_id}:{time.time_ns()}".encode("utf-8")
        ).hexdigest()[:20]
        preflight = [self._verification_preflight(item) for item in candidates]
        required_permissions = sorted(
            {
                permission
                for item in preflight
                for permission in item.get("required_permissions", [])
            }
        )
        blocked_permissions = [
            name
            for name in required_permissions
            if not bool(getattr(permissions, name, False))
        ]
        report: JsonDict = {
            "rift_product": "RIFT",
            "schema_version": 2,
            "verification_run_id": verification_id,
            "recommendation_run_id": run_id,
            "created_unix_seconds": time.time(),
            "task": recommendation.get("task"),
            "status": "blocked" if blocked_permissions else "running",
            "permission_gate": {
                "required": required_permissions,
                "missing": blocked_permissions,
                "authorized": not blocked_permissions,
            },
            "preflight": preflight,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "verification_budget_seconds": budget_seconds,
            "results": [],
            "best_verified": None,
            "claim_boundary": (
                "Verification compares only the finalists, prompt, backend versions, and "
                "hardware recorded by this run; it is not a universal model-quality claim."
            ),
        }
        if blocked_permissions:
            report["verification_run_path"] = str(
                self.recommendation_store.verification_path(verification_id)
            )
            self.recommendation_store.save_verification(report)
            return report

        hardware = HardwareAnalyzer(root=self.root, data_root=self.rift_dir).analyze(
            self.engine.hardware_profile(), state=self.read_state()
        )
        results: list[JsonDict] = []
        started = time.monotonic()
        for index, candidate in enumerate(candidates):
            if budget_seconds is not None and time.monotonic() - started >= budget_seconds:
                results.append(
                    {
                        "candidate": self._verification_candidate_summary(candidate),
                        "status": "BUDGET_EXHAUSTED",
                        "reason": "verification wall-clock budget was exhausted before launch",
                        "steps": [],
                    }
                )
                continue
            result = self._verify_recommendation_candidate(
                candidate=candidate,
                hardware=hardware,
                workload=str(recommendation.get("task") or "chat"),
                permissions=permissions,
                prompt=prompt,
                max_tokens=max_tokens,
                port=11850 + index,
                startup_timeout_seconds=startup_timeout_seconds,
                verification_id=verification_id,
                endpoint=str(endpoint or (recommendation.get("discovery") or {}).get("source") or "https://huggingface.co"),
                token=token,
            )
            results.append(result)
        successful = [item for item in results if item.get("status") == "verified"]
        for item in successful:
            benchmark = item.get("benchmark") or {}
            tps = self._benchmark_tokens_per_second(benchmark)
            ttft = self._benchmark_ttft_seconds(benchmark)
            prior = float((item.get("candidate") or {}).get("final_score") or 0.0)
            item["verification_score"] = round(
                prior * 0.55
                + (tps / max(1.0, tps + 8.0)) * 0.30
                + (1.0 / (1.0 + max(0.0, ttft))) * 0.15,
                6,
            )
            candidate = item.get("candidate") or {}
            repo_id = str(candidate.get("repo_id") or "")
            if repo_id:
                self.evidence_engine.record_local_result(
                    repo_id=repo_id,
                    task=str(recommendation.get("task") or "chat"),
                    metrics=dict(benchmark),
                    artifact=str(candidate.get("selected_file") or candidate.get("artifact_id") or ""),
                    backend=str(candidate.get("backend") or ""),
                    model_revision=str(candidate.get("revision") or "") or None,
                    hardware_fingerprint=str(hardware.get("fingerprint") or "") or None,
                )
        successful.sort(
            key=lambda item: (
                float(item.get("verification_score") or 0.0),
                self._benchmark_tokens_per_second(item.get("benchmark") or {}),
            ),
            reverse=True,
        )
        report["results"] = results
        if successful:
            report["status"] = "verified"
        elif results and all(item.get("status") == "BUDGET_EXHAUSTED" for item in results):
            report["status"] = "blocked"
        else:
            report["status"] = "failed"
        report["best_verified"] = successful[0] if successful else None
        report["completed_unix_seconds"] = time.time()
        report["verification_run_path"] = str(
            self.recommendation_store.verification_path(verification_id)
        )
        self.recommendation_store.save_verification(report)
        return report

    @staticmethod
    def _verification_candidate_summary(candidate: JsonDict) -> JsonDict:
        return {
            "repo_id": candidate.get("repo_id"),
            "revision": candidate.get("revision"),
            "artifact_id": (candidate.get("selected_artifact") or {}).get("artifact_id"),
            "selected_file": candidate.get("selected_file"),
            "backend": candidate.get("backend"),
            "final_score": candidate.get("final_score"),
        }

    def _verification_preflight(self, candidate: JsonDict) -> JsonDict:
        backend = str(candidate.get("backend") or "")
        provider = self.providers.get(backend)
        model_root = self.rift_dir / "models" / str(candidate.get("repo_id") or "").replace("/", "--")
        model_path = self._candidate_cached_model_path(candidate, model_root)
        detection = self._provider_probe(provider, backend) if provider is not None else {"available": False}
        required = ["allow_launch"]
        actions = ["launch", "health", "benchmark", "stop"]
        if model_path is None:
            required.append("allow_download")
            actions.insert(0, "download")
        if not detection.get("available"):
            required.append("allow_install")
            actions.insert(0, "install")
        return {
            "repo_id": candidate.get("repo_id"),
            "artifact_id": (candidate.get("selected_artifact") or {}).get("artifact_id"),
            "backend": backend,
            "cached_model_path": str(model_path) if model_path else None,
            "backend_available": bool(detection.get("available")),
            "actions": actions,
            "required_permissions": sorted(set(required)),
        }

    def _verify_recommendation_candidate(
        self,
        *,
        candidate: JsonDict,
        hardware: JsonDict,
        workload: str,
        permissions: ApplyPermissions,
        prompt: str,
        max_tokens: int,
        port: int,
        startup_timeout_seconds: float,
        verification_id: str,
        endpoint: str,
        token: str | None,
    ) -> JsonDict:
        backend = str(candidate.get("backend") or "")
        provider = self.providers[backend]
        result: JsonDict = {
            "candidate": self._verification_candidate_summary(candidate),
            "status": "failed",
            "steps": [],
        }
        runtime: JsonDict | None = None
        launch_plan: JsonDict = {}
        try:
            detection = self._provider_probe(provider, backend)
            if not detection.get("available"):
                install = provider.install(
                    target_dir=str(self.rift_dir / "backends" / backend),
                    variant="auto",
                )
                result["steps"].append({"kind": "install", "result": install})
                detection = self._provider_probe(provider, backend)
                if not detection.get("available"):
                    raise RuntimeError(f"{backend} remained unavailable after installation")

            model_root = self.rift_dir / "models" / str(candidate.get("repo_id") or "").replace("/", "--")
            model_path = self._candidate_cached_model_path(candidate, model_root)
            if model_path is None:
                selected_bytes = int(
                    candidate.get("selected_download_bytes")
                    or candidate.get("estimated_download_bytes")
                    or (candidate.get("selected_artifact") or {}).get("total_bytes")
                    or 0
                )
                download = self.engine.pull_model_from_hub(
                    str(candidate.get("repo_id") or ""),
                    revision=str(candidate.get("revision") or "main"),
                    output_dir=str(model_root),
                    allow_patterns=self._candidate_pull_patterns(candidate),
                    inspect_after=False,
                    max_bytes=int(selected_bytes * 1.10) if selected_bytes else None,
                    endpoint=endpoint,
                    token=token,
                )
                result["steps"].append({"kind": "download", "result": download})
                model_path = self._candidate_cached_model_path(candidate, model_root)
                if model_path is None:
                    raise RuntimeError("download completed but the selected artifact was not found")

            fit = self._provider_fit(
                provider,
                model={
                    **dict(candidate.get("selected_artifact") or {}),
                    "format": candidate.get("format"),
                    "quantization": candidate.get("quantization"),
                    "estimated_download_bytes": candidate.get("estimated_download_bytes"),
                },
                hardware=hardware,
                workload=workload,
            )
            if not fit.get("fits"):
                raise RuntimeError(str(fit.get("reason") or f"{backend} rejected the artifact"))
            launch_plan = self._provider_launch_spec(
                provider,
                model_path=str(model_path),
                host="127.0.0.1",
                port=port,
                context_length=4096,
                concurrency=1,
                hardware=hardware,
                tuning={},
            )
            runtime = provider.launch(
                launch_plan,
                log_path=str(self.rift_dir / "logs" / f"verify-{verification_id}-{backend}.log"),
            )
            result["steps"].append({"kind": "launch", "result": runtime})
            readiness = self._wait_for_readiness(
                provider=provider,
                runtime=runtime,
                launch_plan=launch_plan,
                timeout_seconds=startup_timeout_seconds,
            )
            result["readiness"] = readiness
            if not readiness.get("ready"):
                raise RuntimeError(str(readiness.get("reason") or "backend did not become ready"))
            benchmark = provider.benchmark(
                base_url=str(runtime.get("api_base") or launch_plan.get("api_base") or ""),
                prompt=prompt,
                max_tokens=max_tokens,
                timeout_seconds=max(60.0, startup_timeout_seconds),
            )
            result["benchmark"] = benchmark
            result["status"] = "verified"
            result["model_path"] = str(model_path)
            result["backend_detection"] = detection
            result["fit"] = fit
        except Exception as exc:
            result["error"] = str(exc)
        finally:
            pid_value = (runtime or {}).get("pid")
            if pid_value not in (None, ""):
                try:
                    result["teardown"] = provider.stop(pid=int(pid_value))
                except Exception as exc:
                    result["teardown"] = {"stopped": False, "error": str(exc)}
            result["container_teardown"] = self._stop_container(launch_plan, runtime)
        return result

    def _candidate_cached_model_path(
        self, candidate: JsonDict, model_root: Path
    ) -> Path | None:
        selected_file = str(candidate.get("selected_file") or "")
        if selected_file:
            exact = model_root.joinpath(*Path(selected_file).parts)
            if exact.is_file():
                return exact
        selected_files = [
            str(item) for item in candidate.get("selected_files", []) if str(item).strip()
        ]
        if selected_files and all(
            model_root.joinpath(*Path(item).parts).is_file() for item in selected_files
        ):
            if str(candidate.get("format") or "").lower() == "gguf":
                return model_root.joinpath(*Path(selected_files[0]).parts)
            return model_root
        if model_root.is_dir():
            if str(candidate.get("format") or "").lower() == "gguf":
                ggufs = sorted(model_root.rglob("*.gguf"))
                return ggufs[0] if ggufs else None
            if (model_root / "config.json").is_file():
                return model_root
        return None

    @staticmethod
    def _candidate_pull_patterns(candidate: JsonDict) -> list[str] | None:
        selected = [
            str(item) for item in candidate.get("selected_files", []) if str(item).strip()
        ]
        if not selected and candidate.get("selected_file"):
            selected = [str(candidate["selected_file"])]
        if not selected:
            return None
        return list(
            dict.fromkeys(
                [*selected, "*.json", "*.model", "*.txt", "*.tiktoken", "*.md"]
            )
        )

    @staticmethod
    def _benchmark_tokens_per_second(benchmark: JsonDict) -> float:
        for key in (
            "decode_tokens_per_second",
            "tokens_per_second",
            "completion_tokens_per_second",
            "tokens_per_second_estimate",
        ):
            value = benchmark.get(key)
            if isinstance(value, (int, float)):
                return max(0.0, float(value))
        return 0.0

    @staticmethod
    def _benchmark_ttft_seconds(benchmark: JsonDict) -> float:
        for key in ("time_to_first_token_seconds", "first_token_seconds", "ttft_seconds"):
            value = benchmark.get(key)
            if isinstance(value, (int, float)):
                return max(0.0, float(value))
        return 60.0

    def plan(
        self,
        *,
        config_path: str | Path = "rift.yaml",
        write: bool = True,
    ) -> JsonDict:
        config_path_resolved = self._resolve_path(config_path)
        config = self.load_config(config_path_resolved)
        governance_policy = GovernancePolicy(config.get("governance") or {})
        discovery = self.discover(local=True, write=False)
        hardware = discovery["nodes"][0]["hardware"]
        actions = []
        services = {}
        for service_name, service in config["services"].items():
            model = dict(service["model"])
            artifact = model.get("artifact") or {}
            disk_fit = model.get("disk_feasibility") or {}
            model.setdefault(
                "estimated_download_bytes",
                int(artifact.get("size") or disk_fit.get("required_bytes") or 0),
            )
            serving = dict(service["serving"])
            policy = dict(service.get("policy") or {})
            backend_decision = self._select_provider_for_model(
                model=model,
                hardware=hardware,
                requested=str(policy.get("backend") or "auto"),
                workload=str(service.get("task") or "chat"),
            )
            backend = str(backend_decision.get("backend") or "")
            if not backend:
                actions.append(
                    self._action(
                        "error",
                        service_name,
                        "no backend passed model-format and hardware fit checks",
                        backend_decision=backend_decision,
                    )
                )
                services[service_name] = {
                    "backend": None,
                    "model": model,
                    "serving": serving,
                    "provider_detection": {"available": False},
                    "provider_fit": {"fits": False, "reason": "no compatible backend"},
                    "backend_decision": backend_decision,
                    "launch_plan": None,
                    "placement": service.get("placement", {"node": "local"}),
                    "decision": model.get("decision", {}),
                    "monitoring": dict(service.get("monitoring") or self._default_monitoring_policy()),
                    "recovery": dict(service.get("recovery") or self._default_recovery_policy()),
                    "gateway": dict(service.get("gateway") or {}),
                    "governance": governance_policy.evaluate(model=model, backend="none"),
                }
                continue
            provider = self.providers.get(backend)
            if provider is None:
                actions.append(self._action("error", service_name, f"backend {backend} is not implemented"))
                services[service_name] = {
                    "backend": backend,
                    "model": model,
                    "serving": serving,
                    "provider_detection": {"available": False},
                    "provider_fit": {"fits": False, "reason": "provider is not registered"},
                    "backend_decision": backend_decision,
                    "launch_plan": None,
                    "placement": service.get("placement", {"node": "local"}),
                    "decision": model.get("decision", {}),
                    "monitoring": dict(service.get("monitoring") or self._default_monitoring_policy()),
                    "recovery": dict(service.get("recovery") or self._default_recovery_policy()),
                    "gateway": dict(service.get("gateway") or {}),
                    "governance": governance_policy.evaluate(model=model, backend=backend),
                }
                continue
            detect = self._provider_probe(provider, backend)
            model_fit = self._provider_fit(
                provider,
                model=model,
                hardware=hardware,
                workload=str(service.get("task") or "chat"),
            )
            governance = governance_policy.evaluate(model=model, backend=backend)
            if not governance["allowed"]:
                actions.append(
                    self._action(
                        "error",
                        service_name,
                        "deployment violates governance policy",
                        governance=governance,
                    )
                )
            if not model_fit.get("fits"):
                actions.append(
                    self._action(
                        "error",
                        service_name,
                        f"{backend} rejected the model/hardware combination",
                        model_fit=model_fit,
                    )
                )
            model_path = str(model.get("selected_file") or model.get("local_path") or model.get("id"))
            tuning = {}
            for tuning_key in ("tuning", "optimized_tuning"):
                value = serving.get(tuning_key)
                if isinstance(value, dict):
                    tuning.update(value)
            launch_plan = self._provider_launch_spec(
                provider,
                model_path=model_path,
                host=str(serving.get("host") or "127.0.0.1"),
                port=int(serving.get("port") or 11735),
                context_length=int(serving.get("context_length") or 4096),
                concurrency=int(serving.get("concurrency") or 1),
                hardware=hardware,
                tuning=tuning,
            )
            if model.get("source") in ("huggingface", "private") and not model.get("local_path"):
                artifact = model.get("artifact") or {}
                disk_fit = model.get("disk_feasibility") or {}
                if str(disk_fit.get("status") or "").lower() == "insufficient":
                    actions.append(
                        self._action(
                            "error",
                            service_name,
                            "selected artifact does not fit available disk capacity",
                            required_bytes=disk_fit.get("required_bytes"),
                            usable_bytes=disk_fit.get("usable_bytes"),
                        )
                    )
                actions.append(
                    self._action(
                        "download",
                        service_name,
                        "selected model artifact must be pulled before launch",
                        permission="allow_download",
                        selected_file=model.get("selected_file"),
                        selected_files=model.get("selected_files", []),
                        quantization=model.get("quantization"),
                        required_bytes=artifact.get("size") or disk_fit.get("required_bytes"),
                        disk_feasibility=disk_fit,
                    )
                )
            if not detect.get("available"):
                actions.append(self._action("install", service_name, f"{backend} is not available", permission="allow_install", install_plan=provider.install_plan()))
            actions.append(self._action("launch", service_name, f"launch {backend} server", permission="allow_launch", launch_plan=launch_plan))
            services[service_name] = {
                "backend": backend,
                "model": model,
                "serving": serving,
                "provider_detection": detect,
                "provider_fit": model_fit,
                "backend_decision": backend_decision,
                "launch_plan": launch_plan,
                "placement": service.get("placement", {"node": "local"}),
                "decision": model.get("decision", {}),
                "monitoring": dict(service.get("monitoring") or self._default_monitoring_policy()),
                "recovery": dict(service.get("recovery") or self._default_recovery_policy()),
                "gateway": dict(service.get("gateway") or {}),
                "governance": governance,
            }
        plan = {
            "rift_product": "RIFT",
            "schema_version": 1,
            "created_unix_seconds": int(time.time()),
            "config_path": str(config_path_resolved),
            "read_only": True,
            "nodes": discovery["nodes"],
            "services": services,
            "actions": actions,
            "drift": self._drift(config, services),
        }
        if write:
            self.plan_dir.mkdir(parents=True, exist_ok=True)
            plan_id = f"{int(time.time())}-riftplan"
            candidate = self.plan_dir / f"{plan_id}.json"
            suffix = 1
            while candidate.exists():
                candidate = self.plan_dir / f"{plan_id}-{suffix}.json"
                suffix += 1
            runtime_target = self._timestamped("plans", "riftplan")
            plan["plan_id"] = candidate.stem
            plan["plan_path"] = str(candidate.resolve())
            plan["runtime_plan_path"] = str(runtime_target.resolve())
            plan["plan_hash"] = self._plan_hash(plan)
            self._write_json(candidate, plan)
            self._write_json(runtime_target, plan)
            self._write_json(self.plan_dir / "latest.json", plan)
            self._write_json(self.rift_dir / "plans" / "latest.json", plan)
        return plan

    def _select_provider_for_model(
        self,
        *,
        model: JsonDict,
        hardware: JsonDict,
        requested: str,
        workload: str = "chat",
    ) -> JsonDict:
        fmt = str(model.get("format") or "unknown").lower()
        quantization = str(model.get("quantization") or "").lower()
        architecture = str(model.get("architecture") or (model.get("config") or {}).get("model_type") or "unknown").lower()
        names = [requested] if requested != "auto" else sorted(self.providers)
        candidates = []
        for name in names:
            provider = self.providers.get(name)
            if provider is None:
                candidates.append(
                    {
                        "backend": name,
                        "fits": False,
                        "available": False,
                        "score": 0.0,
                        "reason": "provider is not registered",
                    }
                )
                continue
            manifest = getattr(provider, "manifest", None)
            format_supported = True
            quantization_supported = True
            architecture_supported = True
            platform_supported = True
            platform_reason = "Legacy provider does not expose platform constraints."
            if isinstance(manifest, AdapterManifest):
                capability = manifest.capability
                format_supported = fmt in {item.lower() for item in capability.formats}
                advertised_quantizations = {item.lower() for item in capability.quantizations}
                quantization_supported = (
                    not quantization
                    or not advertised_quantizations
                    or quantization in advertised_quantizations
                    or any(quantization.startswith(f"{item}_") for item in advertised_quantizations)
                )
                advertised_architectures = {item.lower() for item in capability.architectures}
                architecture_supported = "*" in advertised_architectures or architecture in advertised_architectures
                platform_supported, platform_reason = self.backend_host._platform_supported(
                    capability.operating_systems,
                    hardware,
                )
            try:
                if callable(getattr(provider, "evaluate_fit", None)):
                    fit = provider.evaluate_fit(artifact=model, hardware=hardware, workload=workload)
                else:
                    fit = provider.model_fit(model=model, hardware=hardware)
            except Exception as exc:
                fit = {"fits": False, "reason": f"provider fit check failed: {exc}"}
            detection = provider.probe(
                search_root=str(self.rift_dir / "backends" / name)
            ) if callable(getattr(provider, "probe", None)) else provider.detect(search_root=str(self.rift_dir / "backends" / name))
            compatible = bool(fit.get("fits")) and format_supported and quantization_supported and architecture_supported and platform_supported
            score = (
                (0.42 if format_supported else 0.0)
                + (0.10 if quantization_supported else 0.0)
                + (0.08 if architecture_supported else 0.0)
                + (0.15 if platform_supported else 0.0)
                + (0.18 if fit.get("fits") else 0.0)
                + (0.07 if detection.get("available") else 0.0)
                + self.backend_host._workload_bonus(name, workload)
            )
            reasons = [str(fit.get("reason") or "No fit explanation was returned.")]
            if not format_supported:
                reasons.append(f"adapter manifest does not advertise format {fmt}")
            if not quantization_supported:
                reasons.append(f"adapter manifest does not advertise quantization {quantization}")
            if not architecture_supported:
                reasons.append(f"adapter manifest does not advertise architecture {architecture}")
            if not platform_supported:
                reasons.append(platform_reason)
            candidates.append(
                {
                    "backend": name,
                    "fits": compatible,
                    "available": bool(detection.get("available")),
                    "score": round(score, 6),
                    "reason": "; ".join(reasons),
                    "fit": fit,
                    "detection": detection,
                    "manifest": manifest.to_dict() if isinstance(manifest, AdapterManifest) else None,
                }
            )
        feasible = [candidate for candidate in candidates if candidate["fits"]]
        feasible.sort(key=lambda item: (-float(item["score"]), str(item["backend"])))
        winner = feasible[0] if feasible else None
        return {
            "backend": winner["backend"] if winner else None,
            "requested": requested,
            "format": fmt,
            "candidates": candidates,
            "reason": (
                "Highest manifest-driven compatibility score; installed availability is a tie-break advantage."
                if winner
                else "No discovered backend adapter accepted this artifact/hardware pair."
            ),
        }

    @staticmethod
    def _artifact_local_preference(model: JsonDict) -> float:
        """Small tie-breaker for useful local quantizations, never a fit override."""
        quantization = str(model.get("quantization") or "").upper()
        order = {
            "Q4_K_M": 0.120,
            "Q5_K_M": 0.115,
            "Q6_K": 0.110,
            "Q8_0": 0.105,
            "Q4_K_S": 0.095,
            "Q4_0": 0.085,
            "Q3_K_M": 0.060,
            "Q3_K_S": 0.050,
            "Q2_K": 0.030,
        }
        return order.get(quantization, 0.070 if quantization else 0.0)

    def apply(
        self,
        *,
        config_path: str | Path = "rift.yaml",
        permissions: ApplyPermissions | None = None,
        plan_id: str | None = None,
        plan_hash: str | None = None,
        deployment_record_id: str | None = None,
        progress_callback: ApplyProgressCallback | None = None,
        progress: Callable[[str, str, float | None, JsonDict | None], None] | None = None,
    ) -> JsonDict:
        permissions = permissions or ApplyPermissions()

        def report(
            phase: str,
            message: str,
            percent: float | None = None,
            details: JsonDict | None = None,
            **extra: Any,
        ) -> None:
            payload = dict(details or {})
            payload.update(extra)
            if progress is not None:
                # The server callback supports cancellation through its
                # exception path, so preserve exceptions from this callback.
                progress(phase, message, percent, payload or None)
            elif progress_callback is not None:
                try:
                    progress_callback(phase, message, payload)
                except Exception:
                    # Console/UI progress must never change deployment behavior.
                    return

        report("planning", "running", 5.0, config_path=str(config_path))
        if plan_id:
            plan = self.load_plan_by_id(plan_id)
            expected_hash = self._plan_hash(plan)
            stored_hash = str(plan.get("plan_hash") or expected_hash)
            if stored_hash != expected_hash:
                return {
                    "applied": False,
                    "reason": "selected plan has been modified and must be recreated",
                    "plan_id": plan_id,
                }
            if plan_hash and str(plan_hash) != stored_hash:
                return {
                    "applied": False,
                    "reason": "reviewed plan hash does not match the selected plan",
                    "plan_id": plan_id,
                    "expected_plan_hash": stored_hash,
                    "received_plan_hash": plan_hash,
                }
            config_path = str(plan.get("config_path") or config_path)
        else:
            try:
                plan = self.plan(config_path=config_path, write=True)
            except Exception as exc:
                report("planning", "failed", None, error=str(exc))
                raise
        report(
            "planning",
            "complete",
            None,
            action_count=len(plan.get("actions") or []),
        )
        error_actions = [action for action in plan["actions"] if action.get("kind") == "error"]
        if error_actions:
            report("complete", "failed", reason="plan contains unsupported actions")
            return {
                "applied": False,
                "reason": "plan contains unsupported actions",
                "errors": error_actions,
                "plan": plan,
            }
        blocked = [
            action
            for action in plan["actions"]
            if action.get("permission")
            and not getattr(permissions, str(action["permission"]), False)
        ]
        if blocked:
            report(
                "complete",
                "blocked",
                required_permissions=sorted({action["permission"] for action in blocked}),
            )
            return {
                "applied": False,
                "reason": "permissions required",
                "required_permissions": sorted({action["permission"] for action in blocked}),
                "blocked_actions": blocked,
                "plan": plan,
            }

        install_results = []
        install_actions = [action for action in plan["actions"] if action.get("kind") == "install"]
        if install_actions:
            report("installing", "running", completed=0, total=len(install_actions))
            for index, action in enumerate(install_actions, 1):
                service = plan["services"].get(str(action["service"]))
                if not service:
                    continue
                backend = str(service["backend"])
                provider = self.providers[backend]
                report(
                    "installing",
                    "item_start",
                    service=str(action["service"]),
                    backend=backend,
                    completed=index - 1,
                    total=len(install_actions),
                )
                try:
                    result = provider.install(
                        target_dir=str(self.rift_dir / "backends" / backend),
                        variant=str(action.get("variant") or "auto"),
                    )
                except Exception as exc:
                    report(
                        "installing",
                        "failed",
                        service=str(action["service"]),
                        backend=backend,
                        error=str(exc),
                        completed=index - 1,
                        total=len(install_actions),
                    )
                    raise
                install_results.append({"service": action["service"], "backend": backend, **result})
                report(
                    "installing",
                    "item_complete",
                    service=str(action["service"]),
                    backend=backend,
                    completed=index,
                    total=len(install_actions),
                )
            report("installing", "complete", completed=len(install_actions), total=len(install_actions))
            plan = self.plan(config_path=config_path, write=True)
            remaining_installs = [action for action in plan["actions"] if action.get("kind") == "install"]
            if remaining_installs:
                report(
                    "installing",
                    "failed",
                    reason="backend installation did not make every required backend available",
                )
                return {
                    "applied": False,
                    "reason": "backend installation did not make every required backend available",
                    "install_results": install_results,
                    "remaining_install_actions": remaining_installs,
                    "plan": plan,
                }
        else:
            report("installing", "skipped", reason="backend already available")

        download_actions = [action for action in plan["actions"] if action.get("kind") == "download"]
        if permissions.allow_download and download_actions:
            report("downloading", "running", completed=0, total=len(download_actions))
            try:
                download_results = self._download_models(plan, progress_callback=report)
            except Exception as exc:
                report("downloading", "failed", error=str(exc))
                raise
            report("downloading", "complete", completed=len(download_actions), total=len(download_actions))
        else:
            download_results = []
            report(
                "downloading",
                "skipped",
                reason="no permission required or all model artifacts are already local",
            )
        state = self.read_state()
        config = self.load_config(config_path)
        state["config_fingerprint"] = self._fingerprint(config)
        results = []
        services = list(plan["services"].items())
        report("launching", "running", completed=0, total=len(services))
        for index, (service_name, service) in enumerate(services, 1):
            provider = self.providers[service["backend"]]
            report(
                "launching",
                "item_start",
                service=service_name,
                backend=str(service["backend"]),
                completed=index - 1,
                total=len(services),
            )
            launch_plan = dict(service["launch_plan"])
            downloaded = next(
                (item for item in download_results if item.get("service") == service_name),
                None,
            )
            if downloaded is None:
                cached_download = (
                    (state.get("services", {}).get(service_name) or {}).get("download")
                    or {}
                )
                if cached_download.get("local_dir"):
                    downloaded = {"service": service_name, **cached_download}
            if downloaded and downloaded.get("local_dir"):
                downloaded_model_path = self._downloaded_model_path(downloaded, service.get("model") or {})
                launch_plan = self._provider_launch_spec(
                    provider,
                    model_path=downloaded_model_path,
                    host=str(service["serving"].get("host") or "127.0.0.1"),
                    port=int(service["serving"].get("port") or 11735),
                    context_length=int(service["serving"].get("context_length") or 4096),
                    concurrency=int(service["serving"].get("concurrency") or 1),
                    hardware=plan["nodes"][0]["hardware"],
                    tuning=launch_plan.get("tuning"),
                )
            report(
                "launching",
                f"Starting {service_name} through {service['backend']}",
                None,
                {"service": service_name},
            )
            try:
                launched = provider.launch(
                    launch_plan,
                    log_path=str(self.rift_dir / "logs" / f"{service_name}.log"),
                )
            except Exception as exc:
                report(
                    "launching",
                    "failed",
                    service=service_name,
                    backend=str(service["backend"]),
                    error=str(exc),
                    completed=index - 1,
                    total=len(services),
                )
                raise
            state.setdefault("services", {})[service_name] = {
                **service,
                "runtime": launched,
                "download": downloaded,
                "status": "started",
                "desired_state": "running",
                "supervisor": {
                    "restart_count": 0,
                    "consecutive_failures": 0,
                    "next_retry_unix_seconds": 0.0,
                    "last_restart_unix_seconds": None,
                    "last_healthy_unix_seconds": None,
                    "last_observation": None,
                },
                "last_known_good_launch_plan": None,
                "updated_unix_seconds": int(time.time()),
            }
            self._telemetry_start_service(
                service_name,
                state["services"][service_name],
                backend=str(service.get("backend") or "unknown"),
            )
            results.append({"service": service_name, "launched": launched})
            report("launching", f"Started {service_name}; waiting for health", 85.0, {"service": service_name})
        self.write_state(state)
        tuning_results: list[JsonDict] = []
        if permissions.optimize:
            # Optimization is measured only after the reviewed deployment is
            # healthy. This prevents a plan-only candidate from being reported
            # as a measured improvement and keeps failed candidates reversible.
            for service_name in plan["services"]:
                report(
                    "benchmarking",
                    f"Measuring tuning candidates for {service_name}",
                    None,
                    {"service": service_name, "warmups": 1, "repetitions": 3, "candidates": 2},
                )
                tuning_results.append(
                    self.tune_service(
                        service_name=service_name,
                        config_path=config_path,
                        write=True,
                        live=True,
                        allow_restart=True,
                        candidate_limit=2,
                        warmup_runs=1,
                        repeats=3,
                    )
                )
            state = self.read_state()
        evaluation_results: list[JsonDict] = []
        for service_name, service in plan["services"].items():
            evaluation = service.get("evaluation") or {}
            if not bool(evaluation.get("enabled", True)):
                continue
            observation = self._service_observation(service_name, state["services"][service_name])
            if not observation.get("healthy"):
                if bool(evaluation.get("required", False)):
                    evaluation_results.append(
                        self.evaluate_service(
                            service_name=service_name,
                            max_tokens=min(128, int(evaluation.get("max_tokens") or 128)),
                            total_deadline_seconds=float(evaluation.get("deadline_seconds") or 60.0),
                            retain_responses=bool(evaluation.get("retain_responses", False)),
                            required=True,
                            write=True,
                            judge=evaluation.get("judge") if isinstance(evaluation.get("judge"), dict) else None,
                        )
                    )
                continue
            report("benchmarking", f"Running answer-quality smoke checks for {service_name}", None, {"service": service_name})
            evaluation_results.append(
                self.evaluate_service(
                    service_name=service_name,
                    max_tokens=min(128, int(evaluation.get("max_tokens") or 128)),
                    total_deadline_seconds=float(evaluation.get("deadline_seconds") or 60.0),
                    retain_responses=bool(evaluation.get("retain_responses", False)),
                    required=bool(evaluation.get("required", False)),
                    write=True,
                    judge=evaluation.get("judge") if isinstance(evaluation.get("judge"), dict) else None,
                )
            )
        if evaluation_results:
            for evaluation_result in evaluation_results:
                self._remember_evaluation_state(
                    state,
                    str(evaluation_result.get("service") or ""),
                    evaluation_result,
                )
            self.write_state(state)
        required_failures = [
            item
            for item in evaluation_results
            if bool(item.get("required"))
            and (
                item.get("status") != "completed"
                or int((item.get("summary") or {}).get("fail", 0)) > 0
            )
        ]
        if required_failures:
            stopped = []
            for item in required_failures:
                service_name = str(item.get("service") or "")
                if service_name:
                    stopped.append(self.stop_service(service_name=service_name))
            report("failed", "Required answer-quality evaluation blocked promotion", None)
            return {
                "applied": False,
                "reason": "required answer-quality evaluation failed; service was stopped",
                "promotion_blocked": True,
                "evaluation_failures": required_failures,
                "stopped": stopped,
                "plan": plan,
                "install_results": install_results,
                "results": results,
                "tuning": tuning_results,
                "evaluations": evaluation_results,
                "state_path": str(self.state_path),
            }
        records: list[JsonDict] = []
        for service_name, service in plan["services"].items():
            state_service = state.get("services", {}).get(service_name)
            if not isinstance(state_service, dict):
                continue
            record_id = deployment_record_id if len(plan["services"]) == 1 else None
            record = self._upsert_deployment_record(
                service_name=service_name,
                plan=plan,
                service=state_service,
                config=config,
                status="ready",
                record_id=record_id,
            )
            state_service["deployment_record_id"] = record["deployment_id"]
            records.append(record)
        if records:
            self.write_state(state)
        report("launching", "complete", completed=len(services), total=len(services))
        report("persisting", "running")
        report("persisting", "complete")
        report("complete", "complete", service_count=len(results))
        report("succeeded", "Deployment completed", 100.0)
        return {
            "applied": True,
            "plan": plan,
            "install_results": install_results,
            "results": results,
            "tuning": tuning_results,
            "evaluations": evaluation_results,
            "deployment_records": records,
            "state_path": str(self.state_path),
        }

    def _download_models(
        self,
        plan: JsonDict,
        *,
        progress_callback: ApplyProgressCallback | None = None,
        progress: Callable[[str, str, float | None, JsonDict | None], None] | None = None,
    ) -> list[JsonDict]:
        downloads = []
        download_actions = [action for action in plan["actions"] if action.get("kind") == "download"]
        completed = 0
        for service_name, service in plan["services"].items():
            model = service.get("model") or {}
            if model.get("source") not in ("huggingface", "private") or model.get("local_path"):
                continue
            repo_id = str(model.get("id") or "")
            if not repo_id or repo_id == "auto":
                raise ValueError(f"service {service_name} has no concrete Hub repo id")
            selected_file = model.get("selected_file")
            selected_files = [
                str(path) for path in model.get("selected_files", []) if str(path).strip()
            ]
            if not selected_files and selected_file:
                selected_files = [str(selected_file)]
            allow_patterns = (
                list(dict.fromkeys([*selected_files, "*.json", "*.model", "*.txt", "*.tiktoken", "*.md"]))
                if selected_files
                else None
            )
            output_dir = self.rift_dir / "models" / repo_id.replace("/", "--")
            max_download_gb = float(model.get("max_download_gb") or 0)
            max_bytes = int(max_download_gb * 1024**3) if max_download_gb > 0 else None
            revision = str(model.get("revision") or "main")
            existing = self._existing_download_result(
                model=model,
                repo_id=repo_id,
                revision=revision,
                output_dir=output_dir,
            )
            if existing is not None:
                result = existing
            else:
                result = self.engine.pull_model_from_hub(
                    repo_id,
                    revision=revision,
                    output_dir=str(output_dir),
                    allow_patterns=allow_patterns,
                    endpoint=str(model.get("endpoint") or "https://huggingface.co"),
                    inspect_after=False,
                    max_bytes=max_bytes,
                )
            local_dir = str(result.get("local_dir") or output_dir)
            manifest = self.artifacts.build(
                local_dir,
                source=str(model.get("source") or "huggingface"),
                repo_id=repo_id,
                revision=revision,
                license_name=model.get("license"),
                gated=model.get("gated"),
                hash_mode="model",
            )
            manifest_path = self.rift_dir / "artifacts" / f"{manifest['manifest_sha256']}.json"
            result["artifact_manifest"] = manifest
            result["artifact_manifest_path"] = self.artifacts.write(manifest, manifest_path)
            downloads.append({"service": service_name, **result})
            completed += 1
            details = {
                "service": service_name,
                "repo_id": repo_id,
                "completed": completed,
                "total": len(download_actions),
                "local_dir": local_dir,
                "reused": bool(result.get("reused")),
            }
            if progress is not None:
                progress(
                    "downloading",
                    f"Downloaded artifact for {service_name}",
                    None,
                    details,
                )
            elif progress_callback is not None:
                try:
                    progress_callback(
                        "downloading",
                        "item_complete",
                        details,
                    )
                except Exception:
                    pass
        return downloads

    def _existing_download_result(
        self,
        *,
        model: JsonDict,
        repo_id: str,
        revision: str,
        output_dir: Path,
    ) -> JsonDict | None:
        """Reuse a complete local Hub artifact instead of downloading it again."""
        selected_files = [
            str(item) for item in model.get("selected_files", []) if str(item).strip()
        ]
        selected_file = str(model.get("selected_file") or "").strip()
        if not selected_files and selected_file:
            selected_files = [selected_file]
        if not selected_files or not output_dir.is_dir():
            return None

        size_by_path: dict[str, int] = {}
        artifact = model.get("artifact") or model.get("selected_artifact") or {}
        for item in artifact.get("files") or []:
            if isinstance(item, dict) and item.get("path") and item.get("size") is not None:
                try:
                    size_by_path[str(item["path"])] = int(item["size"])
                except (TypeError, ValueError):
                    continue

        downloaded: list[JsonDict] = []
        total_bytes = 0
        root = output_dir.resolve()
        for relative_name in selected_files:
            candidate = (output_dir / Path(relative_name)).resolve()
            if root not in candidate.parents or not candidate.is_file():
                return None
            size = candidate.stat().st_size
            expected = size_by_path.get(relative_name)
            if expected is not None and size != expected:
                return None
            total_bytes += size
            downloaded.append(
                {
                    "path": relative_name,
                    "local_path": str(candidate),
                    "bytes": size,
                    "integrity": "size_validated_existing",
                }
            )
        return {
            "repo_id": repo_id,
            "revision": revision,
            "local_dir": str(output_dir),
            "reused": True,
            "downloaded": downloaded,
            "downloaded_bytes": 0,
            "total_known_bytes": total_bytes,
        }

    def _downloaded_model_path(self, downloaded: JsonDict, model: JsonDict) -> str:
        selected_file = str(model.get("selected_file") or "")
        downloaded_files = downloaded.get("downloaded") or []
        for item in downloaded_files:
            if not isinstance(item, dict):
                continue
            if selected_file and str(item.get("path") or "") == selected_file:
                local_path = Path(str(item.get("local_path") or ""))
                if not local_path.is_file():
                    raise ValueError(f"selected model file is missing after download: {selected_file}")
                return str(local_path)
        local_dir = Path(str(downloaded.get("local_dir") or ""))
        if selected_file:
            candidate = local_dir.joinpath(*Path(selected_file).parts)
            if candidate.is_file():
                return str(candidate)
            raise ValueError(f"selected model file was not materialized: {selected_file}")
        selected_files = [str(item) for item in model.get("selected_files", []) if str(item).strip()]
        if selected_files:
            missing = [item for item in selected_files if not local_dir.joinpath(*Path(item).parts).is_file()]
            if missing:
                raise ValueError(f"selected model files are missing after download: {', '.join(missing[:3])}")
            return str(local_dir)
        if local_dir.is_file():
            return str(local_dir)
        if local_dir.is_dir():
            supported_files = sorted(
                item
                for item in local_dir.iterdir()
                if item.is_file() and item.suffix.lower() in {".gguf", ".safetensors", ".bin"}
            )
            if len(supported_files) == 1:
                return str(supported_files[0])
            if not supported_files:
                return str(local_dir)
            raise ValueError(
                "download contains multiple model files but no selected_file; recreate the plan with an exact artifact"
            )
        raise ValueError(f"downloaded model directory does not exist: {local_dir}")

    @property
    def state_path(self) -> Path:
        return self.rift_dir / "state.json"

    @property
    def state_db_path(self) -> Path:
        return self.rift_dir / "state.db"

    def read_state(self) -> JsonDict:
        return self.state_store.read()

    def write_state(self, state: JsonDict) -> None:
        state["updated_unix_seconds"] = int(time.time())
        self.state_store.write(state)
        self.observability_store.append(
            "state_written",
            details={
                "schema_version": state.get("schema_version"),
                "service_count": len(state.get("services", {})),
                "config_fingerprint": state.get("config_fingerprint"),
            },
        )

    def status(self) -> JsonDict:
        state = self.read_state()
        services = {}
        counts = {
            "healthy": 0,
            "starting": 0,
            "unhealthy": 0,
            "crashed": 0,
            "backoff": 0,
            "degraded": 0,
            "stopped": 0,
            "unknown": 0,
        }
        for name, service in state.get("services", {}).items():
            observation = self._service_observation(name, service)
            phase = str(observation.get("phase") or "unknown")
            counts[phase if phase in counts else "unknown"] += 1
            telemetry = None
            try:
                active = self.telemetry_store.active_session(name)
                if active:
                    samples = self.telemetry_store.series(active["session_id"], limit=1)["samples"]
                    telemetry = {"session": active, "sample": samples[-1] if samples else None}
                elif (service.get("telemetry") or {}).get("last_report"):
                    telemetry = {"report": (service.get("telemetry") or {}).get("last_report")}
            except Exception:
                telemetry = None
            services[name] = {**service, "observation": observation, "health": observation["health"], "telemetry": telemetry}
        return {
            "rift_product": "RIFT",
            "state_path": str(self.state_path),
            "summary": {"service_count": len(services), **counts},
            "gateway": self.gateway_status(),
            "services": services,
        }

    def monitor(
        self,
        *,
        service_name: str | None = None,
        allow_recovery: bool = False,
        interval_seconds: float = 5.0,
        iterations: int = 1,
    ) -> JsonDict:
        if interval_seconds < 0.0:
            raise ValueError("interval_seconds cannot be negative")
        if iterations < 0:
            raise ValueError("iterations cannot be negative; use 0 for continuous monitoring")
        samples: list[JsonDict] = []
        completed = 0
        try:
            while iterations == 0 or completed < iterations:
                samples.append(
                    self.reconcile(
                        service_name=service_name,
                        allow_recovery=allow_recovery,
                    )
                )
                completed += 1
                if iterations != 0 and completed >= iterations:
                    break
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            pass
        return {
            "rift_product": "RIFT",
            "service": service_name,
            "allow_recovery": allow_recovery,
            "iterations_completed": completed,
            "last": samples[-1] if samples else None,
            "samples": samples if iterations != 0 and iterations <= 20 else [],
        }

    def reconcile(
        self,
        *,
        service_name: str | None = None,
        allow_recovery: bool = False,
        now: float | None = None,
    ) -> JsonDict:
        current_time = float(time.time() if now is None else now)
        state = self.read_state()
        services = state.setdefault("services", {})
        names = [service_name] if service_name else list(services.keys())
        results = []
        history_root = state.setdefault("health_history", {})
        for name in names:
            service = services.get(name)
            if service is None:
                results.append({"service": name, "available": False, "reason": "service not found"})
                continue
            monitoring = dict(service.get("monitoring") or self._default_monitoring_policy())
            if not bool(monitoring.get("enabled", True)):
                results.append(
                    {
                        "service": name,
                        "available": True,
                        "status": service.get("status", "unknown"),
                        "recovery": {"action": "monitoring_disabled"},
                    }
                )
                continue
            observation = self._service_observation(name, service, now=current_time)
            telemetry_sample = None
            if observation.get("process_alive") and bool((monitoring.get("resources") or {}).get("enabled", True)):
                try:
                    active_session = self.telemetry_supervisor.attach_service(
                        name,
                        process_id=int((service.get("runtime") or {}).get("pid") or 0) or None,
                    )
                    if active_session is None:
                        self._telemetry_start_service(name, service, backend=str(service.get("backend") or "unknown"))
                    telemetry_sample = self.telemetry_supervisor.sample_once(name)
                except Exception:
                    telemetry_sample = None
            history = history_root.setdefault(name, [])
            history.append(observation)
            del history[: max(0, len(history) - int(monitoring.get("history_limit", 100)))]

            supervisor = service.setdefault("supervisor", self._default_supervisor_state())
            previous_status = str(service.get("status") or "unknown")
            supervisor["last_observation"] = observation
            action: JsonDict = {"action": "observed"}
            if str(service.get("desired_state") or "running") == "stopped":
                service["status"] = "stopped"
                supervisor["consecutive_failures"] = 0
            elif observation["healthy"]:
                service["status"] = "healthy"
                supervisor["consecutive_failures"] = 0
                supervisor["last_healthy_unix_seconds"] = current_time
                service["last_known_good_launch_plan"] = dict(service.get("launch_plan") or {})
                last_restart = supervisor.get("last_restart_unix_seconds")
                reset_after = float(
                    (service.get("recovery") or {}).get("reset_after_healthy_seconds", 300.0)
                )
                if last_restart is not None and current_time - float(last_restart) >= reset_after:
                    supervisor["restart_count"] = 0
                    supervisor["next_retry_unix_seconds"] = 0.0
            elif observation["phase"] == "starting":
                service["status"] = "starting"
                supervisor["consecutive_failures"] = 0
                action = {
                    "action": "waiting_for_startup",
                    "startup_grace_remaining_seconds": observation.get(
                        "startup_grace_remaining_seconds"
                    ),
                }
            else:
                supervisor["consecutive_failures"] = int(supervisor.get("consecutive_failures") or 0) + 1
                service["status"] = observation["phase"]
                if previous_status not in ("unhealthy", "crashed", "degraded", "backoff"):
                    self._record_incident(
                        state,
                        service_name=name,
                        reason="service health failure detected",
                        action="detected",
                        observation=observation,
                        service=service,
                    )
                if allow_recovery:
                    action = self._maybe_recover_service(
                        state,
                        name,
                        service,
                        observation,
                        current_time,
                    )
                else:
                    action = {
                        "action": "recovery_not_authorized",
                        "required_permission": "allow_recovery",
                    }
            service["updated_unix_seconds"] = int(current_time)
            results.append(
                {
                    "service": name,
                    "available": True,
                    "status": service["status"],
                    "observation": observation,
                    "telemetry": telemetry_sample,
                    "supervisor": dict(supervisor),
                    "recovery": action,
                }
            )
            evaluation = service.get("evaluation") or {}
            if (
                service["status"] == "healthy"
                and bool(evaluation.get("enabled", True))
                and str(service.get("desired_state") or "running") != "stopped"
            ):
                fingerprint = self._evaluation_fingerprint(state, service, name)
                previous = service.get("evaluation_state") or {}
                if str(previous.get("fingerprint") or "") != fingerprint:
                    evaluation_result = self.evaluate_service(
                        service_name=name,
                        max_tokens=min(128, int(evaluation.get("max_tokens") or 128)),
                        total_deadline_seconds=float(evaluation.get("deadline_seconds") or 60.0),
                        retain_responses=bool(evaluation.get("retain_responses", False)),
                        required=bool(evaluation.get("required", False)),
                        write=True,
                    )
                    service["evaluation_state"] = {
                        "fingerprint": fingerprint,
                        "run_id": evaluation_result.get("run_id"),
                        "status": evaluation_result.get("status"),
                        "summary": dict(evaluation_result.get("summary") or {}),
                        "completed_unix_seconds": evaluation_result.get("completed_unix_seconds"),
                    }
                    results[-1]["answer_quality"] = {
                        "run_id": evaluation_result.get("run_id"),
                        "status": evaluation_result.get("status"),
                        "summary": evaluation_result.get("summary"),
                        "required": bool(evaluation.get("required", False)),
                    }
        self.write_state(state)
        return {
            "rift_product": "RIFT",
            "created_unix_seconds": current_time,
            "allow_recovery": allow_recovery,
            "results": results,
        }

    def _evaluation_fingerprint(
        self,
        state: JsonDict,
        service: JsonDict,
        service_name: str | None = None,
    ) -> str:
        """Identify the effective deployment revision tested by the smoke suite."""

        return self._fingerprint(
            {
                "config_fingerprint": state.get("config_fingerprint"),
                "service": service_name or service.get("name"),
                "model": service.get("model"),
                "backend": service.get("backend"),
                "launch_plan": service.get("launch_plan"),
                "serving": service.get("serving"),
            }
        )

    def _remember_evaluation_state(
        self,
        state: JsonDict,
        service_name: str,
        evaluation_result: JsonDict,
    ) -> None:
        """Persist a small evaluation index without retaining model responses."""

        if not service_name:
            return
        service = (state.get("services") or {}).get(service_name)
        if not isinstance(service, dict):
            return
        service["evaluation_state"] = {
            "fingerprint": self._evaluation_fingerprint(state, service, service_name),
            "run_id": evaluation_result.get("run_id"),
            "status": evaluation_result.get("status"),
            "summary": dict(evaluation_result.get("summary") or {}),
            "completed_unix_seconds": evaluation_result.get("completed_unix_seconds"),
        }

    def recover(
        self,
        *,
        service_name: str = "chat",
        allow_launch: bool = False,
        force: bool = False,
    ) -> JsonDict:
        if not allow_launch:
            return {
                "recovered": False,
                "reason": "--allow-launch is required for recovery",
                "required_permission": "allow_launch",
                "service": service_name,
            }
        state = self.read_state()
        service = state.get("services", {}).get(service_name)
        if service is None:
            return {"recovered": False, "reason": "service not found", "service": service_name}
        observation = self._service_observation(service_name, service)
        if observation["healthy"] and not force:
            return {
                "recovered": False,
                "reason": "service is already healthy; use --force to restart it",
                "service": service_name,
                "observation": observation,
            }
        now = time.time()
        if force:
            result = self._restart_service(
                state,
                service_name,
                service,
                observation,
                now,
                bypass_limits=True,
            )
        else:
            result = self._maybe_recover_service(
                state,
                service_name,
                service,
                observation,
                now,
            )
        self.write_state(state)
        return {
            "recovered": result.get("action") in ("restarted", "rolled_back"),
            "service": service_name,
            "result": result,
            "state_path": str(self.state_path),
        }

    def _telemetry_start_service(self, service_name: str, service: JsonDict, *, backend: str | None = None) -> None:
        """Start/attach the node supervisor without making telemetry a launch dependency."""
        monitoring = dict(service.get("monitoring") or {})
        resources = self._effective_telemetry_resources(service)
        if not bool(resources.get("enabled", True)):
            return
        pid_value = (service.get("runtime") or {}).get("pid")
        pid = int(pid_value) if pid_value not in (None, "") else None
        try:
            session = self.telemetry_supervisor.start_service(
                service_name,
                process_id=pid,
                metadata={
                    "backend": backend or service.get("backend"),
                    "model": (service.get("model") or {}).get("id"),
                    "scope": (service.get("runtime") or {}).get("resource_scope") or {"kind": "pid", "pid": pid},
                    "electricity_price_per_kwh": resources.get("electricity_price_per_kwh"),
                    "compute_cost_per_node_hour": resources.get("compute_cost_per_node_hour"),
                },
                interval_seconds=float(resources.get("sample_interval_seconds", 2.0)),
            )
            service["telemetry"] = {
                "enabled": True,
                "session_id": session.get("session_id"),
                "started_at": session.get("started_at"),
                "node_id": session.get("node_id", "local"),
            }
        except Exception as exc:
            service["telemetry"] = {"enabled": True, "status": "unavailable", "reason": str(exc)}

    @staticmethod
    def _validate_accounting_rate(name: str, value: Any) -> None:
        if value is None:
            return
        if isinstance(value, bool):
            raise ValueError(f"{name} must be a non-negative finite number or null")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be a non-negative finite number or null") from exc
        if not math.isfinite(number) or number < 0.0:
            raise ValueError(f"{name} must be a non-negative finite number or null")

    def _effective_telemetry_resources(
        self,
        service: JsonDict,
        *,
        config: JsonDict | None = None,
    ) -> JsonDict:
        """Merge global telemetry defaults with a service's explicit overrides."""
        if config is None:
            try:
                loaded = read_yaml(self._resolve_path("rift.yaml"))
                config = loaded if isinstance(loaded, dict) else {}
            except (OSError, ValueError):
                config = {}
        telemetry = (config.get("observability") or {}).get("telemetry") or {}
        global_resources = dict(telemetry) if isinstance(telemetry, dict) else {}
        monitoring = service.get("monitoring") or {}
        service_resources = monitoring.get("resources") or {} if isinstance(monitoring, dict) else {}
        if not isinstance(service_resources, dict):
            service_resources = {}
        effective = dict(global_resources)
        for key, value in service_resources.items():
            if key in ("electricity_price_per_kwh", "compute_cost_per_node_hour") and value is None:
                continue
            effective[key] = value
        return effective

    def service_telemetry_accounting(
        self,
        service_name: str,
        *,
        config: JsonDict | None = None,
    ) -> JsonDict:
        """Return effective and service-scoped resource accounting settings."""
        loaded = config if config is not None else self.load_config()
        services = loaded.get("services") or {}
        service = services.get(service_name)
        if not isinstance(service, dict):
            raise KeyError(f"service not found: {service_name}")
        telemetry = (loaded.get("observability") or {}).get("telemetry") or {}
        global_resources = dict(telemetry) if isinstance(telemetry, dict) else {}
        monitoring = service.get("monitoring") or {}
        service_resources = monitoring.get("resources") or {} if isinstance(monitoring, dict) else {}
        if not isinstance(service_resources, dict):
            service_resources = {}
        effective = self._effective_telemetry_resources(service, config=loaded)
        rates = {
            "electricity_price_per_kwh": effective.get("electricity_price_per_kwh"),
            "compute_cost_per_node_hour": effective.get("compute_cost_per_node_hour"),
        }
        sources = {
            "electricity_price_source": (
                "service" if service_resources.get("electricity_price_per_kwh") is not None
                else "global" if global_resources.get("electricity_price_per_kwh") is not None
                else "unconfigured"
            ),
            "compute_cost_source": (
                "service" if service_resources.get("compute_cost_per_node_hour") is not None
                else "global" if global_resources.get("compute_cost_per_node_hour") is not None
                else "unconfigured"
            ),
        }
        return {
            "api_version": "2",
            "service": service_name,
            "config_path": str(self._resolve_path("rift.yaml")),
            **rates,
            **sources,
            "configured": any(value is not None for value in rates.values()),
            "currency": None,
            "service_overrides": {
                key: service_resources.get(key)
                for key in ("electricity_price_per_kwh", "compute_cost_per_node_hour")
            },
            "global_defaults": {
                key: global_resources.get(key)
                for key in ("electricity_price_per_kwh", "compute_cost_per_node_hour")
            },
        }

    def update_service_telemetry_accounting(
        self,
        service_name: str,
        *,
        updates: dict[str, Any],
    ) -> JsonDict:
        """Persist service accounting overrides and refresh any live session."""
        if not str(service_name).strip():
            raise ValueError("service name is required")
        if not isinstance(updates, dict) or not updates:
            raise ValueError("at least one accounting setting is required")
        allowed = {"electricity_price_per_kwh", "compute_cost_per_node_hour"}
        unknown = sorted(set(updates) - allowed)
        if unknown:
            raise ValueError(f"unsupported accounting setting: {unknown[0]}")
        normalized: dict[str, float | None] = {}
        for key, value in updates.items():
            self._validate_accounting_rate(key, value)
            normalized[key] = None if value is None else float(value)

        config_path = self._resolve_path("rift.yaml")
        config = self.load_config(config_path)
        services = config.get("services") or {}
        service = services.get(service_name)
        if not isinstance(service, dict):
            raise KeyError(f"service not found: {service_name}")
        monitoring = service.setdefault("monitoring", {})
        if not isinstance(monitoring, dict):
            raise ValueError(f"service {service_name} monitoring must be an object")
        resources = monitoring.setdefault("resources", {})
        if not isinstance(resources, dict):
            raise ValueError(f"service {service_name} monitoring.resources must be an object")
        resources.update(normalized)
        self.validate_config(config)
        self._write_yaml_atomic(config_path, config)

        state = self.read_state()
        state_service = (state.get("services") or {}).get(service_name)
        if isinstance(state_service, dict):
            state_monitoring = state_service.setdefault("monitoring", {})
            if isinstance(state_monitoring, dict):
                state_resources = state_monitoring.setdefault("resources", {})
                if isinstance(state_resources, dict):
                    state_resources.update(normalized)
            state["config_fingerprint"] = self._fingerprint(config)
            self.write_state(state)

        snapshot = self.service_telemetry_accounting(service_name, config=config)
        active = self.telemetry_store.active_session(service_name)
        if active is not None:
            self.telemetry_store.update_session_metadata(
                str(active["session_id"]),
                {
                    "electricity_price_per_kwh": snapshot["electricity_price_per_kwh"],
                    "compute_cost_per_node_hour": snapshot["compute_cost_per_node_hour"],
                },
            )
        self.observability_store.append(
            "telemetry_accounting_updated",
            details={"service": service_name, "settings": normalized},
        )
        return snapshot

    def _telemetry_finish_service(self, service_name: str) -> JsonDict | None:
        try:
            report = self.telemetry_supervisor.stop_service(service_name)
            if not report:
                return None
            gateway_path = self.rift_dir / "gateway" / "metrics.json"
            try:
                gateway = json.loads(gateway_path.read_text(encoding="utf-8")) if gateway_path.is_file() else {}
            except (OSError, json.JSONDecodeError):
                gateway = {}
            if isinstance(gateway, dict):
                report["traffic"] = {
                    "requests_total": int(gateway.get("requests_total") or 0),
                    "requests_succeeded": int(gateway.get("requests_succeeded") or 0),
                    "requests_failed": int(gateway.get("requests_failed") or 0),
                    "input_tokens_observed": int(gateway.get("tokens_input_observed") or 0),
                    "output_tokens_observed": int(gateway.get("tokens_output_observed") or 0),
                    "coverage": "measured" if int(gateway.get("requests_with_usage") or 0) else "unknown",
                }
            self.telemetry_store.update_report(report)
            return report
        except (KeyError, OSError, RuntimeError):
            return None

    def telemetry_latest(self, *, service_name: str | None = None, node_id: str | None = None) -> JsonDict:
        sessions = self.telemetry_store.list_sessions(service_name=service_name, node_id=node_id, limit=100)["sessions"]
        latest: list[JsonDict] = []
        for session in sessions:
            if str(session.get("status") or "") != "running":
                continue
            series = self.telemetry_store.series(str(session["session_id"]), limit=1)["samples"]
            if series:
                latest.append({"session": session, "sample": series[-1]})
        latest.sort(key=lambda item: float((item.get("sample") or {}).get("observed_at") or 0), reverse=True)
        return {"api_version": "1", "updated_at": time.time(), "samples": latest}

    def telemetry_series(self, *, session_id: str | None = None, service_name: str | None = None, since: float | None = None, until: float | None = None) -> JsonDict:
        if session_id:
            result = self.telemetry_store.series(session_id, since=since, until=until)
            result["api_version"] = "1"
            return result
        sessions = self.telemetry_store.list_sessions(service_name=service_name, limit=100)["sessions"]
        return {
            "api_version": "1",
            "sessions": [self.telemetry_store.series(str(item["session_id"]), since=since, until=until) for item in sessions],
        }

    def telemetry_sessions(self, *, service_name: str | None = None, node_id: str | None = None, limit: int = 100) -> JsonDict:
        return {"api_version": "1", **self.telemetry_store.list_sessions(service_name=service_name, node_id=node_id, limit=limit)}

    def telemetry_reports(self, *, service_name: str | None = None, node_id: str | None = None, limit: int = 100) -> JsonDict:
        return {"api_version": "1", **self.telemetry_store.list_reports(service_name=service_name, node_id=node_id, limit=limit)}

    def telemetry_signals(self, *, service_name: str | None = None, session_id: str | None = None, limit: int = 100) -> JsonDict:
        return {"api_version": "1", **self.telemetry_store.list_signals(service_name=service_name, session_id=session_id, limit=limit)}

    def telemetry_report(self, report_id: str) -> JsonDict:
        report = self.telemetry_store.get_report(report_id)
        if report is None:
            raise KeyError(report_id)
        return {"api_version": "1", "report": report}

    def stop_service(self, *, service_name: str) -> JsonDict:
        """Stop a service while retaining its desired configuration and model."""

        state = self.read_state()
        service = state.get("services", {}).get(service_name)
        if service is None:
            return {"stopped": False, "service": service_name, "reason": "service not found"}
        pid_value = (service.get("runtime") or {}).get("pid")
        pid = int(pid_value) if pid_value not in (None, "") else None
        termination = self._terminate_pid(pid) if pid is not None and self._process_alive(pid) else {
            "stopped": True,
            "status": "not_running",
            "pid": pid,
        }
        telemetry_report = self._telemetry_finish_service(service_name)
        if telemetry_report:
            service["telemetry"] = {"last_report": telemetry_report}
        service["desired_state"] = "stopped"
        service["status"] = "stopped"
        service["updated_unix_seconds"] = int(time.time())
        self._set_deployment_record_status(
            service_name=service_name,
            service=service,
            status="stopped",
        )
        self.write_state(state)
        return {
            "stopped": bool(termination.get("stopped")),
            "service": service_name,
            "termination": termination,
            "resource_report": telemetry_report,
        }

    def rollback_service(self, *, service_name: str, allow_launch: bool = False) -> JsonDict:
        """Re-launch the persisted last-known-good command when available."""

        if not allow_launch:
            return {
                "rolled_back": False,
                "service": service_name,
                "reason": "--allow-launch is required for rollback",
                "required_permission": "allow_launch",
            }
        state = self.read_state()
        service = state.get("services", {}).get(service_name)
        if service is None:
            return {"rolled_back": False, "service": service_name, "reason": "service not found"}
        known_good = service.get("last_known_good_launch_plan") or service.get("launch_plan") or {}
        if not known_good.get("command"):
            return {"rolled_back": False, "service": service_name, "reason": "no last-known-good launch plan is recorded"}
        service["launch_plan"] = dict(known_good)
        observation = self._service_observation(service_name, service)
        result = self._restart_service(state, service_name, service, observation, time.time(), bypass_limits=True)
        self.write_state(state)
        return {
            "rolled_back": result.get("action") in ("restarted", "rolled_back"),
            "service": service_name,
            "result": {**result, "used_last_known_good": True},
            "state_path": str(self.state_path),
        }

    def incidents(self, *, limit: int = 50) -> JsonDict:
        if limit <= 0:
            raise ValueError("limit must be positive")
        state = self.read_state()
        entries = list(state.get("incidents", []))[-limit:]
        entries.reverse()
        return {
            "rift_product": "RIFT",
            "incident_count": len(state.get("incidents", [])),
            "incidents": entries,
        }

    def _service_observation(
        self,
        name: str,
        service: JsonDict,
        *,
        now: float | None = None,
    ) -> JsonDict:
        observed_at = float(time.time() if now is None else now)
        runtime = service.get("runtime") or {}
        launch_plan = service.get("launch_plan") or {}
        pid_value = runtime.get("pid")
        pid = int(pid_value) if pid_value not in (None, "") else None
        process_alive = self._process_alive(pid) if pid is not None else None
        desired_state = str(service.get("desired_state") or "running")
        backend = str(service.get("backend") or "")
        provider = self.providers.get(backend)
        api_base = runtime.get("api_base") or launch_plan.get("api_base")
        monitoring = dict(service.get("monitoring") or self._default_monitoring_policy())
        if desired_state == "stopped":
            health: JsonDict = {"healthy": False, "reason": "service desired state is stopped"}
        elif provider is None:
            health = {"healthy": False, "reason": f"provider is not registered: {backend}"}
        elif not api_base:
            health = {"healthy": False, "reason": "service has no api_base"}
        else:
            try:
                health = provider.health(
                    base_url=str(api_base),
                    timeout_seconds=float(monitoring.get("health_timeout_seconds", 2.0)),
                )
            except Exception as exc:
                health = {"healthy": False, "reason": "health probe raised", "error": str(exc)}
        process_ok = process_alive is not False
        healthy = desired_state == "running" and process_ok and bool(health.get("healthy"))
        started_value = runtime.get("started_unix_seconds")
        started_at = float(started_value) if started_value not in (None, "") else None
        startup_grace = float(monitoring.get("startup_grace_seconds", 180.0))
        startup_age = observed_at - started_at if started_at is not None else None
        inside_startup_grace = (
            desired_state == "running"
            and process_alive is not False
            and not bool(health.get("healthy"))
            and started_at is not None
            and startup_age is not None
            and startup_age < startup_grace
        )
        if desired_state == "stopped":
            phase = "stopped"
        elif str(service.get("status") or "") == "degraded" and not healthy:
            phase = "degraded"
        elif pid is not None and process_alive is False:
            phase = "crashed"
        elif healthy:
            phase = "healthy"
        elif inside_startup_grace:
            phase = "starting"
        elif provider is None or not api_base:
            phase = "unknown"
        else:
            phase = "unhealthy"
        return {
            "service": name,
            "observed_unix_seconds": observed_at,
            "desired_state": desired_state,
            "phase": phase,
            "healthy": healthy,
            "backend": backend,
            "pid": pid,
            "process_alive": process_alive,
            "liveness": {
                "healthy": process_alive is not False,
                "source": "process",
            },
            "readiness": {
                "healthy": bool(health.get("healthy")),
                "source": "backend_http",
            },
            "startup_grace_remaining_seconds": (
                max(0.0, startup_grace - float(startup_age))
                if startup_age is not None
                else None
            ),
            "api_base": api_base,
            "health": health,
        }

    def _maybe_recover_service(
        self,
        state: JsonDict,
        name: str,
        service: JsonDict,
        observation: JsonDict,
        now: float,
    ) -> JsonDict:
        policy = {**self._default_recovery_policy(), **dict(service.get("recovery") or {})}
        supervisor = service.setdefault("supervisor", self._default_supervisor_state())
        if not bool(policy.get("enabled", True)):
            return {"action": "disabled", "reason": "recovery policy is disabled"}
        restart_count = int(supervisor.get("restart_count") or 0)
        max_restarts = int(policy.get("max_restarts", 3))
        if restart_count >= max_restarts:
            was_degraded = str(service.get("status") or "") == "degraded"
            service["status"] = "degraded"
            if not was_degraded:
                self._record_incident(
                    state,
                    service_name=name,
                    reason="automatic restart limit exhausted",
                    action="marked_degraded",
                    observation=observation,
                    service=service,
                )
            return {
                "action": "marked_degraded",
                "restart_count": restart_count,
                "max_restarts": max_restarts,
            }
        next_retry = float(supervisor.get("next_retry_unix_seconds") or 0.0)
        if now < next_retry:
            service["status"] = "backoff"
            return {
                "action": "backoff",
                "retry_after_seconds": round(next_retry - now, 3),
                "next_retry_unix_seconds": next_retry,
            }
        failure_threshold = int(
            (service.get("monitoring") or {}).get("failure_threshold", 3)
        )
        consecutive_failures = int(supervisor.get("consecutive_failures") or 0)
        if observation.get("phase") != "crashed" and consecutive_failures < failure_threshold:
            return {
                "action": "waiting_failure_threshold",
                "consecutive_failures": consecutive_failures,
                "failure_threshold": failure_threshold,
            }
        return self._restart_service(state, name, service, observation, now)

    def _restart_service(
        self,
        state: JsonDict,
        name: str,
        service: JsonDict,
        observation: JsonDict,
        now: float,
        *,
        bypass_limits: bool = False,
    ) -> JsonDict:
        backend = str(service.get("backend") or "")
        provider = self.providers.get(backend)
        launch_plan = service.get("launch_plan") or {}
        last_known_good = service.get("last_known_good_launch_plan") or {}
        use_rollback = (
            bool((service.get("recovery") or {}).get("rollback_to_last_known_good", True))
            and bool(last_known_good.get("command"))
            and self._fingerprint(last_known_good) != self._fingerprint(launch_plan)
        )
        recovery_plan = dict(last_known_good if use_rollback else launch_plan)
        if provider is None or not recovery_plan.get("command"):
            service["status"] = "degraded"
            reason = "provider or persisted launch plan is unavailable"
            self._record_incident(
                state,
                service_name=name,
                reason=reason,
                action="restart_failed",
                observation=observation,
                service=service,
            )
            return {"action": "restart_failed", "reason": reason}

        # Container launch plans intentionally use a backend-relative model
        # reference during the initial apply. Reconstruct the host-backed plan
        # from the persisted download before recovery so a restart never passes
        # that relative placeholder (for example, ".") to the backend.
        try:
            recovery_plan = self._rebuild_launch_plan(
                provider=provider,
                service=service,
                launch_plan=recovery_plan,
                hardware=self.engine.hardware_profile(),
                tuning=dict(recovery_plan.get("tuning") or {}),
            )
        except Exception as exc:
            service["status"] = "degraded"
            self._record_incident(
                state,
                service_name=name,
                reason="could not rebuild backend launch plan for recovery",
                action="restart_failed",
                observation=observation,
                service=service,
                details={"error": str(exc)},
            )
            return {"action": "restart_failed", "reason": str(exc)}

        old_pid_value = (service.get("runtime") or {}).get("pid")
        old_pid = int(old_pid_value) if old_pid_value not in (None, "") else None
        old_runtime = dict(service.get("runtime") or {})
        old_launch_plan = dict(service.get("launch_plan") or {})
        old_container_termination = self._stop_container(old_launch_plan, old_runtime)
        termination = {"status": "not_running", "pid": old_pid}
        if old_pid is not None and self._process_alive(old_pid):
            termination = self._terminate_pid(old_pid)
            if not bool(termination.get("stopped")):
                service["status"] = "degraded"
                self._record_incident(
                    state,
                    service_name=name,
                    reason="existing process could not be stopped before recovery",
                    action="restart_failed",
                    observation=observation,
                    service=service,
                    details={
                        "termination": termination,
                        "container_termination": old_container_termination,
                    },
                )
                return {
                    "action": "restart_failed",
                    "reason": "existing process is still alive",
                    "termination": termination,
                    "container_termination": old_container_termination,
                }
        try:
            launched = provider.launch(
                recovery_plan,
                log_path=str(self.rift_dir / "logs" / f"{name}.log"),
            )
        except Exception as exc:
            service["status"] = "degraded"
            self._record_incident(
                state,
                service_name=name,
                reason="backend relaunch failed",
                action="restart_failed",
                observation=observation,
                service=service,
                details={
                    "error": str(exc),
                    "termination": termination,
                    "container_termination": old_container_termination,
                },
            )
            return {
                "action": "restart_failed",
                "error": str(exc),
                "termination": termination,
                "container_termination": old_container_termination,
            }

        policy = {**self._default_recovery_policy(), **dict(service.get("recovery") or {})}
        supervisor = service.setdefault("supervisor", self._default_supervisor_state())
        restart_count = int(supervisor.get("restart_count") or 0) + 1
        base_backoff = float(policy.get("backoff_seconds", 2.0))
        max_backoff = float(policy.get("max_backoff_seconds", 60.0))
        backoff = min(max_backoff, base_backoff * (2 ** max(0, restart_count - 1)))
        supervisor.update(
            {
                "restart_count": restart_count,
                "consecutive_failures": 0,
                "last_restart_unix_seconds": now,
                "next_retry_unix_seconds": now + backoff,
                "last_restart_reason": observation.get("phase"),
            }
        )
        service["runtime"] = launched
        service["launch_plan"] = recovery_plan
        service["desired_state"] = "running"
        service["status"] = "restarting"
        recovery_action = "rolled_back" if use_rollback else "restarted"
        incident = self._record_incident(
            state,
            service_name=name,
            reason="service restarted by RIFT supervisor",
            action=recovery_action,
            observation=observation,
            service=service,
            details={
                "old_pid": old_pid,
                "new_pid": launched.get("pid"),
                "restart_count": restart_count,
                "backoff_seconds": backoff,
                "bypass_limits": bypass_limits,
                "used_last_known_good": use_rollback,
            },
        )
        return {
            "action": recovery_action,
            "old_pid": old_pid,
            "new_pid": launched.get("pid"),
            "restart_count": restart_count,
            "next_retry_unix_seconds": now + backoff,
            "termination": termination,
            "container_termination": old_container_termination,
            "incident": incident,
        }

    def _record_incident(
        self,
        state: JsonDict,
        *,
        service_name: str,
        reason: str,
        action: str,
        observation: JsonDict,
        service: JsonDict,
        details: JsonDict | None = None,
    ) -> JsonDict:
        incident_id = f"{time.time_ns()}-{service_name}"
        payload = {
            "incident_id": incident_id,
            "created_unix_seconds": time.time(),
            "service": service_name,
            "reason": reason,
            "action": action,
            "backend": service.get("backend"),
            "model": (service.get("model") or {}).get("id"),
            "status": service.get("status"),
            "observation": observation,
            "supervisor": dict(service.get("supervisor") or {}),
            "details": details or {},
            "log_tail": self._log_tail(service_name),
        }
        path = self.rift_dir / "incidents" / f"{incident_id}.json"
        self._write_json(path, payload)
        summary = {
            "incident_id": incident_id,
            "created_unix_seconds": payload["created_unix_seconds"],
            "service": service_name,
            "reason": reason,
            "action": action,
            "path": str(path),
        }
        incidents = state.setdefault("incidents", [])
        incidents.append(summary)
        del incidents[: max(0, len(incidents) - 500)]
        return summary

    def _log_tail(self, service_name: str, *, lines: int = 40) -> list[str]:
        path = self.rift_dir / "logs" / f"{service_name}.log"
        if not path.is_file():
            return []
        try:
            return path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
        except OSError:
            return []

    def _process_alive(self, pid: int | None) -> bool:
        if pid is None or pid <= 0:
            return False
        if os.name == "nt":
            try:
                import ctypes
                from ctypes import wintypes

                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                kernel32.OpenProcess.restype = wintypes.HANDLE
                kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
                kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
                handle = kernel32.OpenProcess(0x1000, False, int(pid))
                if not handle:
                    return False
                try:
                    code = wintypes.DWORD()
                    if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                        return False
                    return int(code.value) == 259
                finally:
                    kernel32.CloseHandle(handle)
            except Exception:
                return False
        try:
            os.kill(int(pid), 0)
            return True
        except PermissionError:
            return True
        except (ProcessLookupError, OSError):
            return False

    def _terminate_pid(self, pid: int, *, timeout_seconds: float = 5.0) -> JsonDict:
        if not self._process_alive(pid):
            return {"pid": pid, "stopped": True, "status": "already_stopped"}
        if os.name == "nt":
            native_error = None
            try:
                import ctypes
                from ctypes import wintypes

                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                kernel32.OpenProcess.restype = wintypes.HANDLE
                kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
                kernel32.TerminateProcess.restype = wintypes.BOOL
                kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                kernel32.WaitForSingleObject.restype = wintypes.DWORD
                kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
                handle = kernel32.OpenProcess(0x0001 | 0x00100000, False, int(pid))
                if not handle:
                    raise OSError(
                        ctypes.get_last_error(),
                        "OpenProcess(PROCESS_TERMINATE) failed",
                    )
                try:
                    if not kernel32.TerminateProcess(handle, 1):
                        raise OSError(ctypes.get_last_error(), "TerminateProcess failed")
                    wait_result = int(
                        kernel32.WaitForSingleObject(
                            handle,
                            max(0, int(timeout_seconds * 1000)),
                        )
                    )
                    stopped = wait_result == 0 or not self._process_alive(pid)
                    return {
                        "pid": pid,
                        "stopped": stopped,
                        "status": "terminated" if stopped else "termination_timeout",
                        "method": "TerminateProcess",
                    }
                finally:
                    kernel32.CloseHandle(handle)
            except Exception as exc:
                native_error = str(exc)
            completed = subprocess.run(
                ["taskkill", "/PID", str(int(pid)), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=max(1.0, timeout_seconds),
                check=False,
            )
            stopped = not self._process_alive(pid)
            return {
                "pid": pid,
                "stopped": stopped,
                "status": "terminated" if stopped else "termination_failed",
                "method": "taskkill",
                "native_error": native_error,
                "returncode": completed.returncode,
                "stdout": completed.stdout[-500:],
                "stderr": completed.stderr[-500:],
            }
        try:
            os.kill(int(pid), signal.SIGTERM)
        except Exception as exc:
            return {"pid": pid, "stopped": False, "status": "signal_failed", "error": str(exc)}
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while time.monotonic() < deadline:
            if not self._process_alive(pid):
                return {"pid": pid, "stopped": True, "status": "terminated"}
            time.sleep(0.1)
        return {"pid": pid, "stopped": False, "status": "termination_timeout"}

    @staticmethod
    def _container_name(launch_plan: JsonDict, runtime: JsonDict | None = None) -> str | None:
        runtime = runtime or {}
        explicit = str(runtime.get("container_name") or launch_plan.get("container_name") or "").strip()
        if explicit:
            return explicit
        command = [str(item) for item in launch_plan.get("command") or []]
        if "--name" not in command:
            return None
        index = command.index("--name") + 1
        return command[index].strip() if index < len(command) and command[index].strip() else None

    @staticmethod
    def _stop_container(
        launch_plan: JsonDict,
        runtime: JsonDict | None = None,
        *,
        timeout_seconds: float = 15.0,
    ) -> JsonDict:
        """Stop daemon-owned containers that outlive the Docker client process."""
        name = RiftOrchestrator._container_name(launch_plan, runtime)
        if not name:
            return {"container": None, "stopped": True, "status": "not_a_container"}
        command = [str(item) for item in launch_plan.get("command") or []]
        executable = str(command[0]) if command else "docker"
        stop = subprocess.run(
            [executable, "stop", "--time", "10", name],
            capture_output=True,
            text=True,
            timeout=max(1.0, timeout_seconds),
            check=False,
        )
        remove = subprocess.run(
            [executable, "rm", "-f", name],
            capture_output=True,
            text=True,
            timeout=max(1.0, timeout_seconds),
            check=False,
        )
        already_gone = "no such container" in (stop.stderr + remove.stderr).lower()
        stopped = stop.returncode == 0 or remove.returncode == 0 or already_gone
        return {
            "container": name,
            "stopped": stopped,
            "status": "stopped" if stop.returncode == 0 else ("already_stopped" if already_gone else "stop_failed"),
            "stop_returncode": stop.returncode,
            "remove_returncode": remove.returncode,
            "stdout": (stop.stdout + remove.stdout)[-500:],
            "stderr": (stop.stderr + remove.stderr)[-500:],
        }

    @staticmethod
    def _container_name(launch_plan: JsonDict, runtime: JsonDict | None = None) -> str | None:
        runtime = runtime or {}
        explicit = str(runtime.get("container_name") or launch_plan.get("container_name") or "").strip()
        if explicit:
            return explicit
        command = [str(item) for item in launch_plan.get("command") or []]
        if "--name" not in command:
            return None
        index = command.index("--name") + 1
        return command[index].strip() if index < len(command) and command[index].strip() else None

    @staticmethod
    def _stop_container(
        launch_plan: JsonDict,
        runtime: JsonDict | None = None,
        *,
        timeout_seconds: float = 15.0,
    ) -> JsonDict:
        """Stop daemon-owned containers that outlive the Docker client process."""
        name = RiftOrchestrator._container_name(launch_plan, runtime)
        if not name:
            return {"container": None, "stopped": True, "status": "not_a_container"}
        command = [str(item) for item in launch_plan.get("command") or []]
        executable = str(command[0]) if command else "docker"
        stop = subprocess.run(
            [executable, "stop", "--time", "10", name],
            capture_output=True,
            text=True,
            timeout=max(1.0, timeout_seconds),
            check=False,
        )
        remove = subprocess.run(
            [executable, "rm", "-f", name],
            capture_output=True,
            text=True,
            timeout=max(1.0, timeout_seconds),
            check=False,
        )
        already_gone = "no such container" in (stop.stderr + remove.stderr).lower()
        stopped = stop.returncode == 0 or remove.returncode == 0 or already_gone
        return {
            "container": name,
            "stopped": stopped,
            "status": "stopped" if stop.returncode == 0 else ("already_stopped" if already_gone else "stop_failed"),
            "stop_returncode": stop.returncode,
            "remove_returncode": remove.returncode,
            "stdout": (stop.stdout + remove.stdout)[-500:],
            "stderr": (stop.stderr + remove.stderr)[-500:],
        }

    def _default_monitoring_policy(self) -> JsonDict:
        return {
            "enabled": True,
            "health_timeout_seconds": 2.0,
            "startup_grace_seconds": 180.0,
            "failure_threshold": 3,
            "history_limit": 100,
        }

    def _default_recovery_policy(self) -> JsonDict:
        return {
            "enabled": True,
            "max_restarts": 3,
            "backoff_seconds": 2.0,
            "max_backoff_seconds": 60.0,
            "reset_after_healthy_seconds": 300.0,
            "rollback_to_last_known_good": True,
        }

    def _default_supervisor_state(self) -> JsonDict:
        return {
            "restart_count": 0,
            "consecutive_failures": 0,
            "next_retry_unix_seconds": 0.0,
            "last_restart_unix_seconds": None,
            "last_healthy_unix_seconds": None,
            "last_observation": None,
        }

    def latest_discovery(self) -> JsonDict:
        path = self.rift_dir / "discovery" / "latest.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"available": False}

    def latest_plan(self) -> JsonDict:
        for path in (self.plan_dir / "latest.json", self.rift_dir / "plans" / "latest.json"):
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        return {"available": False}

    def load_plan_by_id(self, plan_id: str) -> JsonDict:
        value = str(plan_id or "").strip()
        if not value or Path(value).name != value or Path(value).suffix:
            raise ValueError("plan_id must be a plan filename stem")
        candidates = [self.rift_dir / "plans" / f"{value}.json", self.plan_dir / f"{value}.json"]
        path = next((candidate for candidate in candidates if candidate.is_file()), None)
        if path is None:
            raise KeyError(f"plan not found: {plan_id}")
        try:
            plan = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"plan is not readable: {plan_id}") from exc
        if not isinstance(plan, dict):
            raise ValueError(f"plan is not an object: {plan_id}")
        plan.setdefault("plan_id", value)
        plan.setdefault("plan_path", str(path))
        plan.setdefault("plan_hash", self._plan_hash(plan))
        return plan

    def generated_config(self, path: str | Path = ".rift/generated/rift.generated.yaml") -> JsonDict:
        target = self._resolve_path(path)
        if not target.exists():
            return {"available": False, "path": str(target)}
        return {"available": True, "path": str(target), "config": read_yaml(target)}

    def reports(self) -> JsonDict:
        root = self.rift_dir / "reports"
        reports = []
        if root.exists():
            for path in sorted(root.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    payload = {}
                reports.append({"path": str(path), "summary": payload})
        return {"reports": reports}

    def evaluations(self, *, service_name: str | None = None, limit: int = 50) -> JsonDict:
        """List persisted answer-evaluation runs without exposing credentials."""

        if limit <= 0:
            raise ValueError("limit must be positive")
        root = self.rift_dir / "reports"
        entries: list[JsonDict] = []
        if root.is_dir():
            for path in sorted(root.glob("*-evaluation.json"), key=lambda item: item.stat().st_mtime_ns, reverse=True):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if not isinstance(payload, dict):
                    continue
                if service_name and str(payload.get("service") or "") != service_name:
                    continue
                entries.append(
                    {
                        "run_id": payload.get("run_id"),
                        "service": payload.get("service"),
                        "status": payload.get("status"),
                        "summary": payload.get("summary", {}),
                        "suite": {
                            "id": (payload.get("suite") or {}).get("id"),
                            "version": (payload.get("suite") or {}).get("version"),
                        },
                        "created_unix_seconds": payload.get("started_unix_seconds"),
                        "path": str(path),
                    }
                )
                if len(entries) >= limit:
                    break
        return {"api_version": "2", "count": len(entries), "evaluations": entries}

    def load_evaluation(self, run_id: str) -> JsonDict:
        value = str(run_id or "").strip()
        if not value or Path(value).name != value or Path(value).suffix:
            raise ValueError("evaluation run id is invalid")
        root = self.rift_dir / "reports"
        for path in root.glob("*-evaluation.json") if root.is_dir() else ():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict) and payload.get("run_id") == value:
                return payload
        raise KeyError(f"evaluation run not found: {value}")

    def backend_status(self) -> JsonDict:
        return {
            "adapter_api_version": self.backend_host.diagnostics().get("adapter_api_version"),
            "providers": {
                name: {
                    "detection": self._provider_probe(provider, name),
                    "manifest": provider.manifest.to_dict() if isinstance(getattr(provider, "manifest", None), AdapterManifest) else None,
                    "install_plan": provider.install_plan(),
                    "lifecycle_gate": provider_lifecycle_gate(provider),
                }
                for name, provider in self.providers.items()
            },
            "overlays": {
                name: {
                    "detection": overlay.detect(search_root=str(self.rift_dir / "overlays" / name)),
                    "install_plan": overlay.install_plan(),
                    "capabilities": overlay.capabilities(),
                }
                for name, overlay in self.overlays.items()
            },
            "registry": self.backend_host.diagnostics(),
        }

    def model_sources(self) -> JsonDict:
        """Return actual configured and managed model sources for the operator UI."""

        sources: list[JsonDict] = [
            {
                "id": "huggingface",
                "kind": "huggingface",
                "endpoint": "https://huggingface.co",
                "configured": True,
                "status": "ready",
                "credentials": "not configured in controller state",
            }
        ]
        managed = self.rift_dir / "models"
        managed_bytes = 0
        managed_files = 0
        if managed.is_dir():
            for item in managed.rglob("*"):
                if item.is_file():
                    try:
                        managed_bytes += item.stat().st_size
                        managed_files += 1
                    except OSError:
                        continue
        sources.append(
            {
                "id": "rift-managed",
                "kind": "local",
                "path": str(managed),
                "configured": True,
                "status": "ready" if managed.is_dir() else "empty",
                "file_count": managed_files,
                "bytes": managed_bytes,
            }
        )
        config_path = self.root / "rift.yaml"
        if config_path.is_file():
            try:
                config = self.load_config(config_path)
            except Exception as exc:
                return {"available": False, "reason": f"rift.yaml could not be read: {exc}", "sources": sources}
            seen: set[str] = set()
            for service in (config.get("services") or {}).values():
                model = (service or {}).get("model") if isinstance(service, dict) else {}
                if not isinstance(model, dict):
                    continue
                path = str(model.get("local_path") or "").strip()
                if path and path not in seen:
                    seen.add(path)
                    candidate = Path(path).expanduser()
                    sources.append(
                        {
                            "id": f"configured-{len(sources)}",
                            "kind": "local",
                            "path": str(candidate),
                            "configured": True,
                            "status": "ready" if candidate.exists() else "missing",
                        }
                    )
        return {"available": True, "sources": sources}

    def settings_snapshot(self) -> JsonDict:
        """Return the redacted settings that are actually backed by RIFT state."""

        config_path = self.root / "rift.yaml"
        config: JsonDict = {}
        config_error: str | None = None
        if config_path.is_file():
            try:
                loaded = self.load_config(config_path)
                if isinstance(loaded, dict):
                    config = loaded
            except Exception as exc:
                config_error = str(exc)
        services: JsonDict = {}
        gateway_configs: list[JsonDict] = []
        exposed_services: list[str] = []
        for name, service in (config.get("services") or {}).items():
            if not isinstance(service, dict):
                continue
            policy = service.get("policy")
            serving = service.get("serving")
            backend_name = service.get("backend")
            gateway_config = service.get("gateway")
            if isinstance(gateway_config, dict):
                gateway_configs.append({"service": str(name), **gateway_config})
            if str(service.get("exposure") or "local").lower() not in ("local", "loopback"):
                exposed_services.append(str(name))
            if not backend_name and isinstance(policy, dict):
                backend_name = policy.get("backend")
            services[str(name)] = {
                "backend": backend_name,
                "exposure": service.get("exposure") or "local",
                "context_length": serving.get("context_length") if isinstance(serving, dict) else None,
                "concurrency": serving.get("concurrency") if isinstance(serving, dict) else None,
                "allow_remote": bool((service.get("permissions") or {}).get("allow_remote", False)) if isinstance(service.get("permissions"), dict) else False,
            }
        gateway = self.gateway_status()
        configured_gateway = gateway_configs[0] if gateway_configs else {}
        gateway_state = gateway.get("state") if isinstance(gateway.get("state"), dict) else {}
        gateway_host = str(
            configured_gateway.get("host")
            or gateway_state.get("host")
            or "127.0.0.1"
        )
        configured_cors = configured_gateway.get("cors_origins") or ()
        if isinstance(configured_cors, str):
            configured_cors = (configured_cors,)
        cors_origins = [str(item) for item in configured_cors if str(item).strip()]
        api_key_env = str(configured_gateway.get("api_key_env") or "RIFT_GATEWAY_API_KEYS")
        environment_keys = [
            item.strip()
            for item in os.environ.get(api_key_env, "").split(",")
            if item.strip()
        ]
        stored_keys = gateway.get("api_keys")
        stored_key_count = (
            int(stored_keys.get("count") or 0)
            if isinstance(stored_keys, dict)
            else len(stored_keys or [])
        )
        api_key_count = stored_key_count + len(environment_keys)
        security_warnings: list[str] = []
        if "*" in cors_origins:
            security_warnings.append(
                "Unrestricted CORS is enabled; any browser origin can call the gateway."
            )
        if gateway_host not in ("127.0.0.1", "localhost", "::1") or exposed_services:
            if api_key_count == 0:
                security_warnings.append(
                    "Gateway exposure is beyond loopback but no API key is configured."
                )
            if not gateway.get("configured", False):
                security_warnings.append(
                    "Gateway security is not active because the gateway has not been started."
                )
        return {
            "api_version": "2",
            "available": config_error is None,
            "config_path": str(config_path),
            "config_error": config_error,
            "model_sources": self.model_sources(),
            "gateway": {
                "configured": gateway.get("configured", False),
                "status": gateway.get("status", "not_started"),
                "process_alive": gateway.get("process_alive", False),
                "state_path": gateway.get("state_path"),
                "metrics_path": gateway.get("metrics_path"),
                "key_count": api_key_count,
                "api_key_env": api_key_env,
                "api_key_protection": "configured" if api_key_count else "not_configured",
                "bound_host": gateway_host,
                "cors_origins": cors_origins,
                "security_warnings": security_warnings,
            },
            "services": services,
            "policies": {
                "apply_requires_explicit_permissions": True,
                "remote_actions_require_allow_remote": True,
                "model_files_deleted_on_destroy": False,
            },
            "mesh": self.mesh_snapshot(),
        }

    def mesh_snapshot(self) -> JsonDict:
        """Expose mesh status without exposing pairing codes or private material."""

        mesh_root = self.rift_dir / "mesh"
        controller_id = None
        state_path = mesh_root / "controller.json"
        if state_path.is_file():
            try:
                value = json.loads(state_path.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    controller_id = value.get("controller_id")
            except (OSError, json.JSONDecodeError):
                pass
        return {
            "controller_id": controller_id,
            "enrollment_window": self._mesh_enrollment_snapshot(),
            "managed_nodes": len((self.read_state().get("nodes") or {})),
        }

    def _mesh_enrollment_snapshot(self) -> JsonDict:
        try:
            return self.mesh_controller().enrollment_window_status()
        except Exception as exc:
            return {"available": False, "reason": str(exc)}

    def recommend_local_models(
        self,
        *,
        task: str = "chat",
        models_dir: str,
        top: int = 10,
    ) -> JsonDict:
        if top <= 0:
            raise ValueError("top must be positive")
        discovery = self.discover(local=True, models_dir=models_dir, write=False)
        hardware = discovery["nodes"][0]["hardware"]
        ranked: list[JsonDict] = []
        for item in self.scan_local_models(models_dir):
            model = {**item, **dict(item.get("artifact") or {})}
            decision = self._select_provider_for_model(
                model=model, hardware=hardware, requested="auto"
            )
            backend = str(decision.get("backend") or "")
            winner = next(
                (candidate for candidate in decision.get("candidates", []) if candidate.get("backend") == backend),
                None,
            )
            if not winner or not winner.get("fits"):
                continue
            size = int(item.get("size") or model.get("total_bytes") or model.get("size") or 0)
            ranked.append(
                {
                    "repo_id": str(item["path"]),
                    "local_path": str(item["path"]),
                    "source": "local",
                    "format": item.get("format"),
                    "quantization": item.get("quantization"),
                    "selected_file": str(item["path"]),
                    "selected_files": [str(item["path"])],
                    "selected_download_bytes": 0,
                    "estimated_download_bytes": size,
                    "parameters_b": model.get("parameters_b"),
                    "model_type": model.get("architecture") or model.get("model_type") or "local artifact",
                    "backend": backend,
                    "license": model.get("license") or "unknown",
                    "gated": False,
                    "final_score": float(winner.get("score") or 0.0),
                    "confidence": 0.5,
                    "scores": {"hardware_fit": float(winner.get("score") or 0.0), "quality_proxy": 0.0},
                    "evidence": [
                        "artifact was inspected from the supplied local path",
                        str(winner.get("reason") or "backend accepted the local artifact"),
                    ],
                    "warnings": [],
                    "artifact_selection": model,
                    "disk_feasibility": {"status": "local_artifact", "required_bytes": 0},
                    "backend_candidates": decision.get("candidates", []),
                }
            )
        ranked.sort(key=lambda item: (-float(item["final_score"]), int(item.get("estimated_download_bytes") or 0), str(item["repo_id"])))
        run_id = f"local-{time.time_ns()}"
        result = {
            "recommendation_run_id": run_id,
            "task": task,
            "source": "local",
            "recommendations": ranked[:top],
            "candidate_counts": {"raw": len(ranked), "after_filters": len(ranked), "enriched": len(ranked), "returned": min(top, len(ranked))},
            "query_arms": [],
            "answer": {"headline": "Local model inventory", "detail": f"Ranked {len(ranked)} compatible local artifacts."},
            "created_unix_seconds": time.time(),
            "recommendation_contract": "v2",
            "hardware_profile": hardware,
        }
        self.recommendation_store.save_recommendation(result)
        return result

    def calibrate_hardware(self, *, sample_bytes: int = 32 * 1024**2, force: bool = False) -> JsonDict:
        from .system_profile import HardwareAnalyzer

        h2d: JsonDict | None = None
        try:
            h2d = self.engine.measure_h2d_bandwidth(
                sample_bytes=max(1024**2, min(sample_bytes, 512 * 1024**2))
            )
        except Exception as exc:
            h2d = {"measurement": "not_measured", "reason": str(exc)}
        result = HardwareAnalyzer(root=self.root).calibrate(
            sample_bytes=sample_bytes,
            force=force,
            h2d_measurement=h2d,
        )
        self.observability_store.append("hardware_calibrated", details=result)
        return result

    def artifact_manifest(
        self,
        *,
        model_path: str,
        hash_mode: str = "model",
        write: bool = True,
    ) -> JsonDict:
        manifest = self.artifacts.build(model_path, hash_mode=hash_mode)
        verification = self.artifacts.verify(manifest)
        result = {"manifest": manifest, "verification": verification}
        if write:
            target = self.rift_dir / "artifacts" / f"{manifest['manifest_sha256']}.json"
            result["path"] = self.artifacts.write(manifest, target)
        return result

    def benchmark_suite(
        self,
        *,
        service_name: str = "chat",
        warmups: int = 1,
        repetitions: int = 3,
        prompt: str | None = None,
        max_tokens: int = 48,
        concurrency: int = 1,
        write: bool = True,
    ) -> JsonDict:
        if warmups < 0 or repetitions <= 0:
            raise ValueError("warmups cannot be negative and repetitions must be positive")
        if max_tokens <= 0 or max_tokens > 128:
            raise ValueError("max_tokens must be between 1 and 128")
        if concurrency <= 0:
            raise ValueError("concurrency must be positive")
        state = self.read_state()
        service = state.get("services", {}).get(service_name)
        if not service:
            return {"available": False, "reason": f"service not found in state: {service_name}"}
        provider = self.providers.get(str(service.get("backend") or ""))
        runtime = service.get("runtime") or {}
        api_base = runtime.get("api_base") or (service.get("launch_plan") or {}).get("api_base")
        if not provider or not api_base:
            return {"available": False, "reason": "service has no benchmarkable provider/api_base"}
        suite = (
            BenchmarkSuite()
            if not str(prompt or "").strip()
            else BenchmarkSuite(
                (
                    {
                        "id": "operator-prompt",
                        "task": "operator",
                        "prompt": str(prompt).strip(),
                        "max_tokens": int(max_tokens),
                    },
                )
            )
        )
        report = suite.run(
            provider.benchmark,
            base_url=str(api_base),
            warmups=warmups,
            repetitions=repetitions,
            concurrency=concurrency,
            metadata={
                "service": service_name,
                "backend": service.get("backend"),
                "model": service.get("model"),
                "launch_plan": service.get("launch_plan"),
                "hardware_fingerprint": (self.engine.hardware_profile() or {}).get("fingerprint"),
                "operator_prompt": bool(str(prompt or "").strip()),
                "max_tokens": int(max_tokens),
            },
        )
        if write:
            target = self._timestamped("reports", f"{service_name}-benchmark-suite")
            self._write_json(target, report)
            report["report_path"] = str(target)
        model = service.get("model") or {}
        repo_id = str(model.get("id") or model.get("repo_id") or "")
        if repo_id and report.get("summary", {}).get("valid"):
            self.evidence_engine.record_local_result(
                repo_id=repo_id,
                task=str(service.get("task") or "chat"),
                metrics=report["summary"],
                artifact=str(model.get("selected_file") or model.get("local_path") or ""),
                backend=str(service.get("backend") or ""),
            )
        self.observability_store.append(
            "benchmark_suite_completed",
            status="ok" if report.get("summary", {}).get("valid") else "error",
            service=service_name,
            details=report.get("summary", {}),
        )
        return report

    def evaluate_service(
        self,
        *,
        service_name: str = "chat",
        suite: JsonDict | None = None,
        max_tokens: int = 128,
        total_deadline_seconds: float = 60.0,
        retain_responses: bool = False,
        required: bool = False,
        write: bool = True,
        judge: JsonDict | None = None,
    ) -> JsonDict:
        """Run explicit, bounded answer checks against one healthy service.

        Evaluation is deliberately independent from service health. A model can
        be reachable while failing a content criterion, and that result must not
        make the backend appear dead to the supervisor.
        """

        from .evaluation import (
            EvaluationCaseResult,
            EvaluationRun,
            EvaluationSuite,
            evaluate_suite,
            invoke_openai_compatible,
            default_evaluation_suite,
            invoke_judge_openai_compatible,
        )

        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if total_deadline_seconds <= 0.0:
            raise ValueError("total_deadline_seconds must be positive")
        state = self.read_state()
        service = state.get("services", {}).get(service_name)
        if not isinstance(service, dict):
            return {
                "available": False,
                "status": "not_run",
                "service": service_name,
                "reason": f"service not found in state: {service_name}",
            }
        selected_suite = default_evaluation_suite() if suite is None else EvaluationSuite.from_mapping(suite)
        runtime = service.get("runtime") or {}
        launch_plan = service.get("launch_plan") or {}
        api_base = str(runtime.get("api_base") or launch_plan.get("api_base") or "").strip()
        backend_name = str(service.get("backend") or "")
        provider = self.providers.get(backend_name)
        health = None
        if provider is not None and api_base:
            try:
                health = provider.health(base_url=api_base, timeout_seconds=2.0)
            except Exception as exc:
                health = {"healthy": False, "reason": str(exc)}
        model = service.get("model") or {}
        model_id = str(
            runtime.get("model")
            or launch_plan.get("model")
            or model.get("id")
            or model.get("selected_file")
            or service_name
        )
        run_id = f"evaluation-{service_name}-{time.time_ns()}"
        configuration = {
            "max_tokens": min(128, int(max_tokens)),
            "deadline_seconds": float(total_deadline_seconds),
            "retain_responses": bool(retain_responses),
            "required": bool(required),
            "context_length": (service.get("serving") or {}).get("context_length"),
            "concurrency": (service.get("serving") or {}).get("concurrency"),
        }
        judge_invoke = None
        if judge is not None:
            if not isinstance(judge, dict):
                raise ValueError("judge must be an object")
            if "token" in judge:
                raise ValueError("judge credentials must use credential_ref, not an inline token")
            if not bool(judge.get("external_data_consent", False)):
                raise PermissionError("judge requires explicit external_data_consent")
            credential_ref = str(judge.get("credential_ref") or "").strip()
            if not credential_ref:
                raise ValueError("judge credential_ref is required")
            token = None
            if credential_ref != "none":
                if not credential_ref.startswith("env:"):
                    raise ValueError("judge credential_ref must be none or env:VARIABLE_NAME")
                env_name = credential_ref[4:].strip()
                if not env_name or not env_name.replace("_", "").isalnum() or not env_name[0].isalpha():
                    raise ValueError("judge environment credential reference is invalid")
                token = os.environ.get(env_name)
                if not token:
                    raise ValueError("judge credential environment variable is not set")
            allowed_hosts = judge.get("allowed_hosts")
            if not isinstance(allowed_hosts, list) or not all(str(host).strip() for host in allowed_hosts):
                raise ValueError("judge allowed_hosts must be a non-empty array")
            judge_endpoint = str(judge.get("endpoint") or "").strip()
            judge_model = str(judge.get("model") or "").strip()
            judge_invoke = invoke_judge_openai_compatible(
                judge_endpoint,
                model=judge_model,
                token=token,
                allowed_hosts=[str(host) for host in allowed_hosts],
                timeout_seconds=min(30.0, float(judge.get("timeout_seconds") or 15.0)),
            )
            configuration["judge"] = {
                "enabled": True,
                "endpoint_host": str(urlsplit(judge_endpoint).hostname or ""),
                "model": judge_model,
                "allowed_hosts": [str(host) for host in allowed_hosts],
                "external_data_consent": True,
                "credential_ref": credential_ref,
            }
        if not api_base or provider is None or not bool((health or {}).get("healthy")):
            reason = (
                "service is not healthy or has no OpenAI-compatible endpoint"
                if not health
                else str(health.get("reason") or "service health check failed")
            )
            run = EvaluationRun(
                run_id=run_id,
                suite=selected_suite,
                status="not_run",
                service=service_name,
                backend=backend_name,
                model={"id": model_id},
                configuration=configuration,
            )
            run.cases = [
                EvaluationCaseResult(case.case_id, "not_assessed", case.kind, reason)
                for case in selected_suite.cases
            ]
            run.completed_unix_seconds = time.time()
            result = run.to_dict()
            result.update({"available": False, "health": health, "required": bool(required)})
        else:
            invoke = invoke_openai_compatible(api_base, model=model_id, timeout_seconds=min(30.0, total_deadline_seconds))
            run = evaluate_suite(
                selected_suite,
                invoke,
                run_id=run_id,
                max_tokens=min(128, int(max_tokens)),
                total_deadline_seconds=total_deadline_seconds,
                retain_responses=retain_responses,
                service=service_name,
                backend=backend_name,
                model={"id": model_id},
                configuration=configuration,
                judge=judge_invoke,
            )
            result = run.to_dict()
            result.update({"available": True, "health": health, "required": bool(required)})
        result["service"] = service_name
        result["model_revision"] = {
            "artifact": model.get("selected_file") or model.get("local_path") or model.get("id"),
            "config_fingerprint": state.get("config_fingerprint"),
        }
        if write:
            target = self._timestamped("reports", f"{service_name}-evaluation")
            self._write_json(target, result)
            result["report_path"] = str(target)
        self.observability_store.append(
            "evaluation_completed",
            status="ok" if result.get("status") == "completed" and result.get("summary", {}).get("fail", 0) == 0 else "warning",
            service=service_name,
            details={
                "run_id": run_id,
                "status": result.get("status"),
                "summary": result.get("summary"),
                "required": bool(required),
            },
        )
        return result

    def logs(self, *, service_name: str = "chat", tail: int = 200) -> JsonDict:
        if tail <= 0:
            raise ValueError("tail must be positive")
        path = self.rift_dir / "logs" / f"{service_name}.log"
        if not path.is_file():
            return {"available": False, "path": str(path), "lines": []}
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-tail:]
        return {"available": True, "path": str(path), "lines": self.observability_store.redact(lines)}

    def observability(self) -> JsonDict:
        snapshot = self.observability_store.snapshot(
            state=self.read_state(),
            gateway=self.gateway_status(),
            incidents=self.incidents(),
        )
        return {
            "snapshot": snapshot,
            "timeline": self.observability_store.timeline(limit=100),
            "retention": {
                "seconds": self.observability_store.retention_seconds,
                "max_events": self.observability_store.max_events,
            },
        }

    def prometheus_metrics(self) -> str:
        body = self.observability_store.prometheus(self.observability()["snapshot"])
        latest = self.telemetry_latest().get("samples") or []
        lines = [body.rstrip()]
        metric_map = {
            "cpu_percent": "rift_telemetry_cpu_utilization_percent",
            "process_cpu_percent": "rift_telemetry_service_cpu_utilization_percent",
            "host_ram_pressure_percent": "rift_telemetry_host_ram_pressure_percent",
            "host_ram_available_bytes": "rift_telemetry_host_ram_available_bytes",
            "cpu_temperature_c": "rift_telemetry_cpu_temperature_celsius",
            "process_rss_bytes": "rift_telemetry_service_memory_bytes",
            "gpu_utilization_percent": "rift_telemetry_gpu_utilization_percent",
            "gpu_temperature_c": "rift_telemetry_gpu_temperature_celsius",
            "gpu_vram_used_bytes": "rift_telemetry_gpu_vram_used_bytes",
            "gpu_vram_pressure_percent": "rift_telemetry_gpu_vram_pressure_percent",
            "gpu_power_watts": "rift_telemetry_gpu_power_watts",
        }
        emitted: set[str] = set()
        for item in latest:
            session = item.get("session") or {}
            sample = item.get("sample") or {}
            service = str(session.get("service_name") or "unknown").replace('"', "")
            node = str(session.get("node_id") or "local").replace('"', "")
            labels = f'service="{service}",node="{node}"'
            for key, metric in metric_map.items():
                value = sample.get(key)
                if not isinstance(value, (int, float)):
                    continue
                if metric not in emitted:
                    lines.append(f"# TYPE {metric} gauge")
                    emitted.add(metric)
                lines.append(f"{metric}{{{labels}}} {float(value)}")
        return "\n".join(line for line in lines if line) + "\n"

    def prune_observability(self) -> JsonDict:
        return self.observability_store.prune()

    def migrate(self, *, config_path: str | Path = "rift.yaml", write: bool = False) -> JsonDict:
        state, state_changes = migrate_state(self.read_state())
        config_target = self._resolve_path(config_path)
        config = read_yaml(config_target) if config_target.is_file() else self.default_config()
        migrated_config, config_changes = migrate_config(config)
        if write:
            self.write_state(state)
            write_yaml(config_target, migrated_config)
        return {
            "written": write,
            "state": state,
            "config": migrated_config,
            "changes": state_changes + config_changes,
        }

    def diagnostics(self, *, output: str | Path | None = None) -> JsonDict:
        return DiagnosticBundle(root=self.root, data_root=self.rift_dir).create(output)

    def backup_state(self, *, output: str | Path | None = None) -> JsonDict:
        target = Path(output) if output else self.rift_dir / "backups" / f"state-{int(time.time())}.db"
        path = self.state_store.backup(target)
        self.observability_store.append(
            "state_backed_up",
            details={"path": str(path), "revision": self.state_store.revision},
        )
        return {
            "created": True,
            "path": str(path),
            "revision": self.state_store.revision,
            "format": "sqlite-wal-backup",
        }

    def restore_state(self, *, source: str | Path) -> JsonDict:
        backup = self.backup_state()
        revision = self.state_store.restore(source)
        self.observability_store.append(
            "state_restored",
            details={"source": str(source), "revision": revision, "pre_restore_backup": backup["path"]},
        )
        return {
            "restored": True,
            "source": str(source),
            "revision": revision,
            "pre_restore_backup": backup["path"],
        }

    def export_deployment(self, *, output: str | Path | None = None) -> JsonDict:
        plan = self.latest_plan()
        state = self.read_state()
        governance = {
            name: service.get("governance", {})
            for name, service in (plan.get("services") or {}).items()
        }
        manifest = deployment_manifest(
            project=str(plan.get("project") or "rift"),
            plan=plan,
            state=state,
            governance=governance,
        )
        target = output or self.rift_dir / "manifests" / f"{int(time.time())}-deployment.json"
        return {"manifest": manifest, "path": write_deployment_manifest(manifest, target)}

    def gateway_status(self) -> JsonDict:
        state_path = self.rift_dir / "gateway" / "state.json"
        metrics_path = self.rift_dir / "gateway" / "metrics.json"
        gateway_state: JsonDict = {}
        metrics: JsonDict = {}
        if state_path.is_file():
            try:
                gateway_state = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                gateway_state = {"status": "invalid", "error": str(exc)}
        if metrics_path.is_file():
            try:
                metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                metrics = {"error": str(exc)}
        pid_value = gateway_state.get("pid")
        pid = int(pid_value) if pid_value not in (None, "") else None
        process_alive = self._process_alive(pid) if pid is not None else False
        recorded_status = str(gateway_state.get("status") or "not_started")
        effective_status = (
            "running"
            if recorded_status == "running" and process_alive
            else "stale"
            if recorded_status == "running"
            else recorded_status
        )
        return {
            "configured": bool(gateway_state),
            "status": effective_status,
            "process_alive": process_alive,
            "state": gateway_state,
            "metrics": metrics,
            "state_path": str(state_path),
            "metrics_path": str(metrics_path),
            "api_keys": self.api_keys.list(),
        }

    def gateway_key_create(self, *, label: str, quota: JsonDict | None = None) -> JsonDict:
        result = self.api_keys.create(label=label, quota=quota)
        self.observability_store.append(
            "gateway_key_created",
            details={"id": result.get("id"), "label": label, "fingerprint": result.get("fingerprint")},
        )
        return result

    def gateway_key_revoke(self, *, key_id: str) -> JsonDict:
        result = self.api_keys.revoke(key_id)
        self.observability_store.append("gateway_key_revoked", details=result)
        return result

    def gateway_key_rotate(self, *, key_id: str) -> JsonDict:
        result = self.api_keys.rotate(key_id)
        self.observability_store.append(
            "gateway_key_rotated",
            details={"old_id": key_id, "new_id": (result.get("new") or {}).get("id")},
        )
        return result

    def benchmark(
        self,
        *,
        service_name: str = "chat",
        prompt: str = "Explain what RIFT does in one sentence.",
        max_tokens: int = 32,
        write: bool = True,
    ) -> JsonDict:
        state = self.read_state()
        service = state.get("services", {}).get(service_name)
        if not service:
            return {"available": False, "reason": f"service not found in state: {service_name}"}
        provider = self.providers.get(str(service.get("backend")))
        runtime = service.get("runtime") or {}
        api_base = runtime.get("api_base") or (service.get("launch_plan") or {}).get("api_base")
        if not provider or not api_base:
            return {"available": False, "reason": "service has no benchmarkable provider/api_base"}
        try:
            result = provider.benchmark(
                base_url=api_base,
                prompt=prompt,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            result = {
                "available": False,
                "backend": service.get("backend"),
                "api_base": api_base,
                "reason": "benchmark request failed",
                "error": str(exc),
            }
        result.update({"service": service_name, "created_unix_seconds": int(time.time())})
        if write:
            self._write_json(self._timestamped("reports", f"{service_name}-benchmark"), result)
        return result

    def tune_service(
        self,
        *,
        service_name: str,
        plan: JsonDict | None = None,
        config_path: str | Path = "rift.yaml",
        write: bool = True,
        live: bool = False,
        allow_restart: bool = False,
        candidate_limit: int = 4,
        warmup_runs: int = 1,
        repeats: int = 2,
        startup_timeout_seconds: float = 180.0,
        prompt: str = "Reply briefly: what is one benefit of local inference?",
        max_tokens: int = 32,
    ) -> JsonDict:
        if candidate_limit <= 0:
            raise ValueError("candidate_limit must be positive")
        if warmup_runs < 0:
            raise ValueError("warmup_runs cannot be negative")
        if repeats <= 0:
            raise ValueError("repeats must be positive")
        if startup_timeout_seconds <= 0.0:
            raise ValueError("startup_timeout_seconds must be positive")
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if live:
            return self._tune_service_live(
                service_name=service_name,
                config_path=config_path,
                write=write,
                allow_restart=allow_restart,
                candidate_limit=candidate_limit,
                warmup_runs=warmup_runs,
                repeats=repeats,
                startup_timeout_seconds=startup_timeout_seconds,
                prompt=prompt,
                max_tokens=max_tokens,
            )
        if plan is None:
            active_state = self.read_state()
            active_value = active_state.get("services", {}).get(service_name)
            active_service = active_value if isinstance(active_value, dict) else {}
            active_backend = str(active_service.get("backend") or "")
            active_launch_plan = active_service.get("launch_plan")
            if active_backend and isinstance(active_launch_plan, dict) and active_launch_plan:
                plan = {
                    "config_path": active_service.get("config_path"),
                    "services": {
                        service_name: {
                            "backend": active_backend,
                            "launch_plan": active_launch_plan,
                        }
                    },
                    "nodes": [{"hardware": self.engine.hardware_profile()}],
                }
            else:
                config_path_resolved = self._resolve_path(config_path)
                plan = self.plan(config_path=config_path_resolved, write=False)
        service = plan.get("services", {}).get(service_name)
        if not service:
            # UI-managed deployments can originate from a saved recommendation
            # plan rather than the starter rift.yaml. If that source config is
            # present but does not describe the active service, tune the
            # materialized service snapshot instead of failing with a misleading
            # "service not found in plan" error.
            active_state = self.read_state()
            active_service = active_state.get("services", {}).get(service_name)
            active_backend = str((active_service or {}).get("backend") or "")
            active_launch_plan = dict((active_service or {}).get("launch_plan") or {})
            if active_backend and active_launch_plan:
                plan = {
                    "services": {
                        service_name: {
                            "backend": active_backend,
                            "launch_plan": active_launch_plan,
                        }
                    },
                    "nodes": [{"hardware": self.engine.hardware_profile()}],
                }
                service = plan["services"][service_name]
        if not service:
            raise ValueError(f"service not found in plan: {service_name}")
        provider = self.providers[str(service["backend"])]
        candidates = self._provider_tuning_space(
            provider,
            launch_plan=service["launch_plan"],
            hardware=plan["nodes"][0]["hardware"],
        )
        report = {
            "service": service_name,
            "created_unix_seconds": int(time.time()),
            "baseline": service["launch_plan"].get("tuning", {}),
            "candidates": candidates,
            "winning_config": candidates[0] if candidates else service["launch_plan"].get("tuning", {}),
            "decision": (
                "Plan-only candidate ordering. Run `rift service tune --live --allow-restart` "
                "to measure candidates and apply the winner."
            ),
            "mode": "plan_only",
        }
        if write:
            config_path_value = plan.get("config_path")
            if config_path_value:
                source_config = self._resolve_path(str(config_path_value))
                if source_config.is_file():
                    optimized_path = self.rift_dir / "generated" / "rift.optimized.yaml"
                    write_yaml(optimized_path, self._optimized_config(plan, report))
                    report["optimized_config_path"] = str(optimized_path)
                else:
                    report["optimized_config_skipped_reason"] = (
                        "the source configuration is no longer available"
                    )
            else:
                report["optimized_config_skipped_reason"] = (
                    "the deployment was recovered from active state without a source configuration"
                )
            self._write_json(self._timestamped("reports", f"{service_name}-tuning"), report)
        return report

    def _tune_service_live(
        self,
        *,
        service_name: str,
        config_path: str | Path,
        write: bool,
        allow_restart: bool,
        candidate_limit: int,
        warmup_runs: int,
        repeats: int,
        startup_timeout_seconds: float,
        prompt: str,
        max_tokens: int,
    ) -> JsonDict:
        if not allow_restart:
            return {
                "available": False,
                "applied": False,
                "service": service_name,
                "reason": "live tuning restarts the backend and requires --allow-restart",
                "required_permission": "allow_restart",
            }
        state = self.read_state()
        service = state.get("services", {}).get(service_name)
        if not service:
            return {
                "available": False,
                "applied": False,
                "service": service_name,
                "reason": "service is not deployed",
            }
        provider = self.providers.get(str(service.get("backend") or ""))
        if provider is None:
            return {
                "available": False,
                "applied": False,
                "service": service_name,
                "reason": "service provider is not registered",
            }
        observation = self._service_observation(service_name, service)
        if not observation.get("healthy"):
            return {
                "available": False,
                "applied": False,
                "service": service_name,
                "reason": "service must be healthy before live tuning",
                "observation": observation,
            }

        hardware = self.engine.hardware_profile()
        baseline_plan = dict(service.get("launch_plan") or {})
        baseline_tuning = dict(baseline_plan.get("tuning") or {})
        normalized_baseline = self._rebuild_launch_plan(
            provider=provider,
            service=service,
            launch_plan=baseline_plan,
            hardware=hardware,
            tuning=baseline_tuning,
        )
        if normalized_baseline:
            baseline_plan = normalized_baseline
        candidates = [baseline_tuning]
        candidates.extend(
            self._provider_tuning_space(provider, launch_plan=baseline_plan, hardware=hardware)
        )
        unique_candidates: list[JsonDict] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized = dict(candidate or {})
            key = json.dumps(normalized, sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            unique_candidates.append(normalized)
            if len(unique_candidates) >= candidate_limit:
                break

        report: JsonDict = {
            "service": service_name,
            "mode": "live_benchmark",
            "created_unix_seconds": int(time.time()),
            "baseline": baseline_tuning,
            "candidate_limit": candidate_limit,
            "warmup_runs": warmup_runs,
            "repeats": repeats,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "candidates": [],
            "applied": False,
        }
        try:
            baseline_measurement = self._benchmark_series(
                provider,
                api_base=str(observation.get("api_base") or ""),
                prompt=prompt,
                max_tokens=max_tokens,
                warmup_runs=warmup_runs,
                repeats=repeats,
            )
            report["candidates"].append(
                {
                    "index": 0,
                    "kind": "baseline",
                    "tuning": baseline_tuning,
                    "launch_plan": baseline_plan,
                    "measurement": baseline_measurement,
                    "status": "passed" if baseline_measurement["valid"] else "failed",
                    "selection_score": baseline_measurement["selection_score"],
                }
            )

            for index, tuning in enumerate(unique_candidates[1:], start=1):
                candidate_plan = self._rebuild_launch_plan(
                    provider=provider,
                    service=service,
                    launch_plan=baseline_plan,
                    hardware=hardware,
                    tuning=tuning,
                )
                entry: JsonDict = {
                    "index": index,
                    "kind": "candidate",
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
                    entry.update(
                        {
                            "status": "failed",
                            "selection_score": 0.0,
                            "reason": "candidate did not become ready",
                        }
                    )
                    report["candidates"].append(entry)
                    continue
                measurement = self._benchmark_series(
                    provider,
                    api_base=str(candidate_plan.get("api_base") or ""),
                    prompt=prompt,
                    max_tokens=max_tokens,
                    warmup_runs=warmup_runs,
                    repeats=repeats,
                )
                entry.update(
                    {
                        "measurement": measurement,
                        "status": "passed" if measurement["valid"] else "failed",
                        "selection_score": measurement["selection_score"],
                    }
                )
                report["candidates"].append(entry)

            passed = [
                item
                for item in report["candidates"]
                if item.get("status") == "passed" and float(item.get("selection_score") or 0.0) > 0.0
            ]
            if not passed:
                raise RuntimeError("no tuning candidate produced a valid benchmark")
            winner = max(
                passed,
                key=lambda item: (
                    float(item.get("selection_score") or 0.0),
                    -int(item.get("index") or 0),
                ),
            )
            winning_plan = dict(winner["launch_plan"])
            if self._fingerprint(service.get("launch_plan") or {}) != self._fingerprint(winning_plan):
                final_startup = self._replace_service_runtime(
                    state=state,
                    service_name=service_name,
                    service=service,
                    provider=provider,
                    launch_plan=winning_plan,
                    startup_timeout_seconds=startup_timeout_seconds,
                )
                if not final_startup.get("ready"):
                    raise RuntimeError("winning tuning configuration failed its final readiness check")
                report["final_startup"] = final_startup
            else:
                report["final_startup"] = {"ready": True, "reused_running_candidate": True}

            service["launch_plan"] = winning_plan
            service["last_known_good_launch_plan"] = winning_plan
            service["status"] = "healthy"
            service["desired_state"] = "running"
            tuning_history = service.setdefault("tuning_history", [])
            tuning_history.append(
                {
                    "created_unix_seconds": report["created_unix_seconds"],
                    "winning_config": winner["tuning"],
                    "selection_score": winner["selection_score"],
                }
            )
            del tuning_history[: max(0, len(tuning_history) - 50)]
            self.write_state(state)

            baseline_score = float(report["candidates"][0].get("selection_score") or 0.0)
            winning_score = float(winner.get("selection_score") or 0.0)
            report.update(
                {
                    "available": True,
                    "applied": True,
                    "winning_index": winner["index"],
                    "winning_config": winner["tuning"],
                    "winning_score": winning_score,
                    "baseline_score": baseline_score,
                    "improvement_percent": (
                        round((winning_score / baseline_score - 1.0) * 100.0, 3)
                        if baseline_score > 0.0
                        else None
                    ),
                    "decision": "Highest median measured decode throughput among valid candidates.",
                }
            )
        except Exception as exc:
            current_observation = self._service_observation(service_name, service)
            if (
                self._fingerprint(service.get("launch_plan") or {})
                == self._fingerprint(baseline_plan)
                and current_observation.get("healthy")
            ):
                restore = {
                    "ready": True,
                    "reused_running_baseline": True,
                    "health": current_observation.get("health"),
                }
            else:
                restore = self._replace_service_runtime(
                    state=state,
                    service_name=service_name,
                    service=service,
                    provider=provider,
                    launch_plan=baseline_plan,
                    startup_timeout_seconds=startup_timeout_seconds,
                )
            service["launch_plan"] = baseline_plan
            if restore.get("ready"):
                service["last_known_good_launch_plan"] = baseline_plan
                service["status"] = "healthy"
            else:
                service["status"] = "degraded"
            self.write_state(state)
            report.update(
                {
                    "available": True,
                    "applied": False,
                    "error": str(exc),
                    "baseline_restored": bool(restore.get("ready")),
                    "restore": restore,
                }
            )

        if write:
            target = self._timestamped("reports", f"{service_name}-live-tuning")
            self._write_json(target, report)
            report["report_path"] = str(target)
            if report.get("applied"):
                try:
                    plan = self.plan(config_path=config_path, write=False)
                    write_yaml(
                        self.rift_dir / "generated" / "rift.optimized.yaml",
                        self._optimized_config(plan, report),
                    )
                except Exception as exc:
                    report["optimized_config_warning"] = str(exc)
        return report

    def _benchmark_series(
        self,
        provider: Any,
        *,
        api_base: str,
        prompt: str,
        max_tokens: int,
        warmup_runs: int,
        repeats: int,
    ) -> JsonDict:
        if not api_base:
            raise ValueError("api_base is required for live benchmarking")
        warmups = []
        for _ in range(warmup_runs):
            warmups.append(
                provider.benchmark(base_url=api_base, prompt=prompt, max_tokens=max_tokens)
            )
        samples = [
            provider.benchmark(base_url=api_base, prompt=prompt, max_tokens=max_tokens)
            for _ in range(repeats)
        ]
        summary = summarize_samples(samples)
        median_throughput = float(summary.get("median_tokens_per_second") or 0.0)
        return {
            **summary,
            "selection_score": round(median_throughput, 6),
            "warmup_count": len(warmups),
            "cache_state": "warm_after_explicit_warmups" if warmups else "unspecified",
            "suite_case": {
                "id": "tuning-fixed-prompt-v1",
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "max_tokens": max_tokens,
            },
            "samples": samples,
        }

    def _rebuild_launch_plan(
        self,
        *,
        provider: Any,
        service: JsonDict,
        launch_plan: JsonDict,
        hardware: JsonDict,
        tuning: JsonDict,
    ) -> JsonDict:
        model_path = self._model_path_from_launch_plan(launch_plan)
        if model_path and not Path(model_path).is_file():
            downloaded = service.get("download") or {}
            model = service.get("model") or {}
            materialized = self._downloaded_model_path(downloaded, model)
            if materialized and Path(materialized).is_file():
                model_path = materialized
        if not model_path:
            model = service.get("model") or {}
            model_path = str(
                model.get("local_path")
                or model.get("selected_file")
                or model.get("id")
                or ""
            )
        if not model_path:
            raise ValueError("could not recover model path from the deployed service")
        serving = service.get("serving") or {}
        return self._provider_launch_spec(
            provider,
            model_path=model_path,
            host=str(launch_plan.get("host") or serving.get("host") or "127.0.0.1"),
            port=int(launch_plan.get("port") or serving.get("port") or 11735),
            context_length=int(
                launch_plan.get("context_length") or serving.get("context_length") or 4096
            ),
            concurrency=int(
                launch_plan.get("concurrency") or serving.get("concurrency") or 1
            ),
            hardware=hardware,
            tuning=tuning,
        )

    def _provider_probe(self, provider: Any, name: str | None = None) -> JsonDict:
        search_root = str(self.rift_dir / "backends" / str(name or getattr(provider, "name", "adapter")))
        probe = getattr(provider, "probe", None)
        if callable(probe):
            return probe(search_root=search_root)
        return provider.detect(search_root=search_root)

    @staticmethod
    def _provider_fit(
        provider: Any,
        *,
        model: JsonDict,
        hardware: JsonDict,
        workload: str,
    ) -> JsonDict:
        evaluate = getattr(provider, "evaluate_fit", None)
        if callable(evaluate):
            return evaluate(artifact=model, hardware=hardware, workload=workload)
        return provider.model_fit(model=model, hardware=hardware)

    def _provider_launch_spec(self, provider: Any, **kwargs: Any) -> JsonDict:
        tuning = dict(kwargs.get("tuning") or {})
        adapter_id = str(
            getattr(getattr(provider, "manifest", None), "adapter_id", None)
            or getattr(provider, "name", "adapter")
        )
        tuning.setdefault("search_root", str(self.rift_dir / "backends" / adapter_id))
        kwargs["tuning"] = tuning
        build = getattr(provider, "build_launch_spec", None)
        if callable(build):
            return build(**kwargs)
        return provider.plan_launch(**kwargs)

    @staticmethod
    def _provider_tuning_space(
        provider: Any,
        *,
        launch_plan: JsonDict,
        hardware: JsonDict,
    ) -> list[JsonDict]:
        tuning = getattr(provider, "tuning_space", None)
        if callable(tuning):
            return tuning(launch_plan=launch_plan, hardware=hardware)
        return provider.tune_candidates(launch_plan=launch_plan, hardware=hardware)

    def _model_path_from_launch_plan(self, launch_plan: JsonDict) -> str:
        explicit = str(launch_plan.get("model_path") or "")
        if explicit:
            return explicit
        command = [str(item) for item in launch_plan.get("command") or []]
        for marker in ("-m", "--model", "--model-path"):
            if marker in command and command.index(marker) + 1 < len(command):
                return command[command.index(marker) + 1]
        if "serve" in command and command.index("serve") + 1 < len(command):
            return command[command.index("serve") + 1]
        return ""

    def _replace_service_runtime(
        self,
        *,
        state: JsonDict,
        service_name: str,
        service: JsonDict,
        provider: Any,
        launch_plan: JsonDict,
        startup_timeout_seconds: float,
    ) -> JsonDict:
        old_pid_value = (service.get("runtime") or {}).get("pid")
        old_pid = int(old_pid_value) if old_pid_value not in (None, "") else None
        old_runtime = dict(service.get("runtime") or {})
        old_launch_plan = dict(service.get("launch_plan") or {})
        old_container_termination = self._stop_container(old_launch_plan, old_runtime)
        termination = {"pid": old_pid, "stopped": True, "status": "not_running"}
        if old_pid is not None and self._process_alive(old_pid):
            termination = self._terminate_pid(old_pid)
            if not termination.get("stopped"):
                return {
                    "ready": False,
                    "reason": "existing service process could not be stopped",
                    "termination": termination,
                    "container_termination": old_container_termination,
                }
        try:
            launched = provider.launch(
                launch_plan,
                log_path=str(self.rift_dir / "logs" / f"{service_name}.log"),
            )
        except Exception as exc:
            return {
                "ready": False,
                "reason": "backend launch failed",
                "error": str(exc),
                "termination": termination,
            }
        service["runtime"] = launched
        service["launch_plan"] = launch_plan
        service["status"] = "starting"
        service["desired_state"] = "running"
        self.write_state(state)
        readiness = self._wait_for_readiness(
            provider=provider,
            runtime=launched,
            launch_plan=launch_plan,
            timeout_seconds=startup_timeout_seconds,
        )
        if readiness.get("ready"):
            service["status"] = "healthy"
        else:
            service["status"] = "unhealthy"
            new_pid_value = launched.get("pid")
            if new_pid_value not in (None, ""):
                readiness["failed_process_termination"] = self._terminate_pid(
                    int(new_pid_value)
                )
            readiness["failed_container_termination"] = self._stop_container(launch_plan, launched)
        self.write_state(state)
        return {
            **readiness,
            "runtime": launched,
            "termination": termination,
            "container_termination": old_container_termination,
        }

    def _wait_for_readiness(
        self,
        *,
        provider: Any,
        runtime: JsonDict,
        launch_plan: JsonDict,
        timeout_seconds: float,
    ) -> JsonDict:
        api_base = str(runtime.get("api_base") or launch_plan.get("api_base") or "")
        deadline = time.monotonic() + timeout_seconds
        attempts = 0
        last_health: JsonDict = {"healthy": False, "reason": "not probed"}
        while time.monotonic() < deadline:
            attempts += 1
            pid_value = runtime.get("pid")
            pid = int(pid_value) if pid_value not in (None, "") else None
            if pid is not None and not self._process_alive(pid):
                return {
                    "ready": False,
                    "reason": "backend process exited during startup",
                    "attempts": attempts,
                    "health": last_health,
                }
            try:
                last_health = provider.health(base_url=api_base, timeout_seconds=2.0)
            except Exception as exc:
                last_health = {"healthy": False, "error": str(exc)}
            if last_health.get("healthy"):
                return {
                    "ready": True,
                    "attempts": attempts,
                    "health": last_health,
                }
            time.sleep(0.25)
        return {
            "ready": False,
            "reason": "startup readiness timeout",
            "attempts": attempts,
            "health": last_health,
        }

    def destroy(self, *, service_name: str | None = None) -> JsonDict:
        state = self.read_state()
        services = state.get("services", {})
        names = [service_name] if service_name else list(services.keys())
        stopped = []
        removed = []
        for name in names:
            service = services.get(name)
            if not service:
                continue
            runtime = dict(service.get("runtime") or {})
            launch_plan = dict(service.get("launch_plan") or {})
            container_termination = self._stop_container(launch_plan, runtime)
            pid = runtime.get("pid")
            if pid:
                termination = self._terminate_pid(int(pid))
                stopped.append(
                    {
                        "service": name,
                        **termination,
                        "container_termination": container_termination,
                    }
                )
            else:
                stopped.append({"service": name, "container_termination": container_termination})
            resource_report = self._telemetry_finish_service(name)
            if resource_report:
                service["telemetry"] = {
                    "last_report": resource_report,
                    "stopped_at": resource_report.get("stopped_at"),
                }
            self._set_deployment_record_status(
                service_name=name,
                service=service,
                status="deleted",
            )
            services.pop(name, None)
            removed.append(name)
        self.write_state(state)
        return {"stopped": stopped, "removed": removed, "state_path": str(self.state_path)}

    @property
    def deployment_records_path(self) -> Path:
        return self.rift_dir / "deployments" / "records.json"

    def list_deployment_records(self) -> list[JsonDict]:
        """Return durable deployment history, newest first.

        Deployment records intentionally outlive service state. They are the
        operator's reusable inventory of successful model/backend pairings,
        while the controller's service map remains the source of truth for
        what is currently running.
        """

        path = self.deployment_records_path
        if not path.is_file():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"deployment records are not readable: {path}") from exc
        if isinstance(payload, dict):
            records = payload.get("records", [])
        else:
            records = payload
        if not isinstance(records, list):
            raise ValueError(f"deployment records must contain a records array: {path}")
        return [dict(item) for item in records if isinstance(item, dict)]

    def load_deployment_record(self, record_id: str) -> JsonDict:
        value = str(record_id or "").strip()
        if not value or Path(value).name != value or "/" in value or "\\" in value:
            raise ValueError("deployment_id is invalid")
        for record in self.list_deployment_records():
            if str(record.get("deployment_id") or "") == value:
                return record
        raise KeyError(f"deployment record not found: {record_id}")

    def relaunch_deployment(
        self,
        *,
        record_id: str,
        allow_launch: bool = False,
        allow_download: bool = False,
        allow_install: bool = False,
        allow_remote: bool = False,
        optimize: bool = False,
        progress: Callable[[str, str, float | None, JsonDict | None], None] | None = None,
    ) -> JsonDict:
        """Recreate a saved deployment through the ordinary plan/apply path."""

        if not allow_launch:
            return {
                "applied": False,
                "deployment_id": record_id,
                "reason": "--allow-launch is required to launch a saved deployment",
                "required_permission": "allow_launch",
            }
        record = self.load_deployment_record(record_id)
        snapshot = record.get("config_snapshot")
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("services"), dict):
            raise ValueError("saved deployment has no reusable configuration snapshot")
        snapshot_path = self.rift_dir / "deployments" / f"{record_id}.yaml"
        write_yaml(snapshot_path, snapshot)
        if progress is not None:
            progress("preparing", "Revalidating the saved deployment configuration", 5.0, {"deployment_id": record_id})
        result = self.apply(
            config_path=snapshot_path,
            permissions=ApplyPermissions(
                allow_download=allow_download,
                allow_install=allow_install,
                allow_launch=allow_launch,
                allow_remote=allow_remote,
                optimize=optimize,
            ),
            deployment_record_id=record_id,
            progress=progress,
        )
        return {**result, "deployment_id": record_id, "relaunch": True}

    def _set_deployment_record_status(
        self,
        *,
        service_name: str,
        service: JsonDict,
        status: str,
    ) -> JsonDict | None:
        record_id = str(service.get("deployment_record_id") or "")
        record: JsonDict | None = None
        if record_id:
            try:
                record = self.load_deployment_record(record_id)
            except (KeyError, ValueError):
                record = None
        if record is None:
            candidates = [
                item
                for item in self.list_deployment_records()
                if str(item.get("service_name") or "") == service_name
            ]
            record = candidates[0] if candidates else None
        if record is None:
            return None
        record["status"] = status
        record["updated_unix_seconds"] = time.time()
        if status == "stopped":
            record["stopped_unix_seconds"] = time.time()
        if status == "deleted":
            record["deleted_unix_seconds"] = time.time()
        records = self.list_deployment_records()
        for index, item in enumerate(records):
            if item.get("deployment_id") == record.get("deployment_id"):
                records[index] = record
                break
        self._write_deployment_records(records)
        return record

    def _upsert_deployment_record(
        self,
        *,
        service_name: str,
        plan: JsonDict,
        service: JsonDict,
        config: JsonDict,
        status: str,
        record_id: str | None = None,
    ) -> JsonDict:
        records = self.list_deployment_records()
        existing: JsonDict | None = None
        if record_id:
            existing = next((item for item in records if item.get("deployment_id") == record_id), None)
        now = time.time()
        deployment_id = record_id or f"dep-{uuid.uuid4().hex[:12]}"
        snapshot = self._deployment_config_snapshot(
            service_name=service_name,
            service=service,
            config=config,
        )
        snapshot_path = self.rift_dir / "deployments" / f"{deployment_id}.yaml"
        write_yaml(snapshot_path, snapshot)
        launch = dict(service.get("launch_plan") or {})
        model = dict(service.get("model") or {})
        serving = dict(service.get("serving") or {})
        runtime = dict(service.get("runtime") or {})
        provider_detection = dict(service.get("provider_detection") or {})
        backend = str(service.get("backend") or "external")
        record = {
            "schema_version": 1,
            "deployment_id": deployment_id,
            "service_name": service_name,
            "display_name": service_name,
            "status": status,
            "model": model,
            "backend": {
                "kind": backend,
                "version": provider_detection.get("version"),
                "executable": provider_detection.get("executable"),
            },
            "node": dict(service.get("placement") or {"node": "local"}),
            "endpoint": {
                "api_base": runtime.get("api_base") or launch.get("api_base"),
                "openai_base": runtime.get("openai_base") or launch.get("openai_base"),
                "host": serving.get("host") or launch.get("host"),
                "port": serving.get("port") or launch.get("port"),
                "path": "/v1",
            },
            "serving": serving,
            "gateway": dict(service.get("gateway") or {}),
            "launch": launch,
            "last_known_good": dict(service.get("last_known_good_launch_plan") or launch),
            "plan": {
                "id": plan.get("plan_id"),
                "hash": plan.get("plan_hash"),
                "config_path": plan.get("config_path"),
            },
            "config_snapshot": snapshot,
            "config_snapshot_path": str(snapshot_path),
            "runtime": runtime,
            "relaunch_count": int((existing or {}).get("relaunch_count") or 0) + (1 if existing else 0),
            "created_unix_seconds": (existing or {}).get("created_unix_seconds", now),
            "updated_unix_seconds": now,
            "last_started_unix_seconds": now if status == "ready" else (existing or {}).get("last_started_unix_seconds"),
        }
        if existing:
            index = next(index for index, item in enumerate(records) if item.get("deployment_id") == deployment_id)
            records[index] = record
        else:
            records.insert(0, record)
        self._write_deployment_records(records)
        return record

    def _deployment_config_snapshot(
        self,
        *,
        service_name: str,
        service: JsonDict,
        config: JsonDict,
    ) -> JsonDict:
        snapshot = json.loads(json.dumps(config, default=str))
        services = snapshot.setdefault("services", {})
        configured = dict(services.get(service_name) or {})
        effective_model = dict(service.get("model") or configured.get("model") or {})
        download = service.get("download")
        if isinstance(download, dict) and download.get("local_dir"):
            try:
                effective_model["local_path"] = self._downloaded_model_path(download, effective_model)
                effective_model["source"] = "local"
            except (OSError, ValueError):
                pass
        configured["model"] = effective_model
        configured["serving"] = dict(service.get("serving") or configured.get("serving") or {})
        configured["placement"] = dict(service.get("placement") or configured.get("placement") or {})
        configured["gateway"] = dict(service.get("gateway") or configured.get("gateway") or {})
        configured.setdefault("policy", {})["backend"] = str(service.get("backend") or "auto")
        services[service_name] = configured
        return snapshot

    def _write_deployment_records(self, records: list[JsonDict]) -> None:
        self._write_json(
            self.deployment_records_path,
            {"schema_version": 1, "records": records},
        )

    def _optimized_config(self, plan: JsonDict, tuning_report: JsonDict) -> JsonDict:
        config = self.load_config(plan["config_path"])
        service = config["services"][tuning_report["service"]]
        service.setdefault("serving", {})["optimized_tuning"] = tuning_report["winning_config"]
        service.setdefault("serving", {})["optimization_decision"] = tuning_report["decision"]
        return config

    def _drift(self, config: JsonDict, services: JsonDict) -> list[JsonDict]:
        state = self.read_state()
        if not state.get("services"):
            return []
        digest = self._fingerprint(config)
        previous = state.get("config_fingerprint")
        return [] if not previous or previous == digest else [{"type": "config_changed", "previous": previous, "current": digest}]

    def _action(self, kind: str, service: str, message: str, **details: Any) -> JsonDict:
        return {"kind": kind, "service": service, "message": message, **details}

    def _hardware_summary(self, hardware: JsonDict) -> JsonDict:
        return {
            "device_name": hardware.get("device_name"),
            "vram_gb": round(int(hardware.get("total_vram_bytes") or 0) / 1024**3, 3),
            "ram_gb": round(int(hardware.get("total_host_ram_bytes") or 0) / 1024**3, 3),
            "cuda_available": bool(hardware.get("cuda_available", False)),
        }

    def _fingerprint(self, payload: Any) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()

    def _plan_hash(self, plan: JsonDict) -> str:
        content = {
            key: value
            for key, value in plan.items()
            if key not in {"plan_hash", "plan_id", "plan_path"}
        }
        return self._fingerprint(content)

    def _timestamped(self, folder: str, stem: str) -> Path:
        return self.rift_dir / folder / f"{time.time_ns()}-{stem}.json"

    @property
    def plan_dir(self) -> Path:
        """Repository-local reviewed deployment intent and plan history."""

        return self.root / "plans"

    def _write_json(self, path: Path, payload: JsonDict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f".{time.time_ns()}.tmp")
        encoded = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        try:
            with temporary.open("wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            try:
                temporary.unlink()
            except OSError:
                pass

    def _write_yaml_atomic(self, path: Path, payload: JsonDict) -> None:
        """Replace a configuration file only after the complete document is written."""
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f".{time.time_ns()}.tmp")
        try:
            write_yaml(temporary, payload)
            with temporary.open("r+b") as stream:
                os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            try:
                temporary.unlink()
            except OSError:
                pass

    def _resolve_path(self, path: str | Path) -> Path:
        target = Path(path)
        return target if target.is_absolute() else self.root / target
