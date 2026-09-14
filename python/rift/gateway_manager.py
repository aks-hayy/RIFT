"""Controller-owned lifecycle for the shared RIFT gateway listeners."""

from __future__ import annotations

from dataclasses import dataclass, asdict
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any
from .rift_yaml import read_yaml

try:
    import psutil  # type: ignore
except ImportError:  # pragma: no cover - optional on minimal installs
    psutil = None


JsonDict = dict[str, Any]


@dataclass(frozen=True)
class GatewayTarget:
    kind: str = "main"
    group_id: str | None = None
    host: str = "127.0.0.1"
    port: int = 11734
    config_path: str = "rift.yaml"
    service_name: str = "chat"

    def to_dict(self) -> JsonDict:
        return asdict(self)


class GatewayManager:
    """Start, stop, and inspect detached gateway processes safely."""

    def __init__(self, root: str | Path, runtime_root: str | Path, *, python_executable: str | None = None) -> None:
        self.root = Path(root).expanduser().resolve()
        self.runtime_root = Path(runtime_root).expanduser().resolve()
        self.gateway_root = self.runtime_root / "gateway"
        self.python_executable = python_executable or sys.executable

    @property
    def state_path(self) -> Path:
        return self.gateway_root / "state.json"

    @property
    def metrics_path(self) -> Path:
        return self.gateway_root / "metrics.json"

    def start_main(
        self,
        config_path: str | Path | None = None,
        *,
        service_name: str = "chat",
        host: str | None = None,
        port: int | None = None,
    ) -> JsonDict:
        config = self._resolve_config(config_path)
        target = GatewayTarget(
            kind="main",
            host=host or self._configured_gateway(config, service_name).get("host") or "127.0.0.1",
            port=int(port or self._configured_gateway(config, service_name).get("port") or 11734),
            config_path=str(config),
            service_name=service_name,
        )
        existing = self._read_state(self.state_path)
        if self._state_matches(existing, target) and self._process_alive(existing.get("pid")):
            return {**existing, "started": False, "status": "running", "process_alive": True, "state_path": str(self.state_path)}
        if existing.get("status") == "running" and self._process_alive(existing.get("pid")):
            raise RuntimeError(
                f"gateway already running on {existing.get('host')}:{existing.get('port')} "
                f"for {existing.get('service_name') or 'another configuration'}"
            )
        pid = self._spawn(target)
        state = {
            **target.to_dict(),
            "pid": pid,
            "status": "running",
            "process_alive": True,
            "started_unix_seconds": time.time(),
        }
        self._write_state(state, self.state_path)
        return {**state, "started": True, "state_path": str(self.state_path)}

    def stop_main(self) -> JsonDict:
        state = self._read_state(self.state_path)
        if not state:
            return {"kind": "main", "status": "not_started", "process_alive": False, "stopped": False, "state_path": str(self.state_path)}
        pid = self._int_pid(state.get("pid"))
        alive = self._process_alive(pid)
        if alive and pid is not None:
            self._terminate(pid)
        state.update({"status": "stopped", "process_alive": False, "stopped_unix_seconds": time.time()})
        self._write_state(state, self.state_path)
        return {**state, "stopped": bool(alive), "state_path": str(self.state_path)}

    def status(self) -> JsonDict:
        state = self._read_state(self.state_path)
        if not state:
            return {
                "kind": "main",
                "status": "not_started",
                "configured": False,
                "process_alive": False,
                "metrics_path": str(self.metrics_path),
                "state_path": str(self.state_path),
                "groups": self.group_statuses(),
            }
        alive = self._process_alive(state.get("pid"))
        recorded = str(state.get("status") or "not_started")
        effective = "running" if recorded == "running" and alive else "stale" if recorded == "running" else recorded
        result = {**state, "status": effective, "configured": True, "process_alive": alive, "state_path": str(self.state_path), "metrics_path": str(self.metrics_path)}
        metrics = self._read_state(self.metrics_path)
        if metrics:
            result["metrics"] = metrics
        result["groups"] = self.group_statuses()
        return result

    def start_group(
        self,
        group_id: str,
        config_path: str | Path | None = None,
        *,
        host: str | None = None,
        port: int | None = None,
    ) -> JsonDict:
        group = str(group_id or "").strip()
        if not group or "/" in group or "\\" in group or group in {".", ".."}:
            raise ValueError("group id must be a path-safe identifier")
        config = self._resolve_config(config_path)
        configured = self._group_config(config, group)
        target = GatewayTarget(
            kind="group",
            group_id=group,
            host=host or configured.get("host") or "127.0.0.1",
            port=int(port or configured.get("port") or 0),
            config_path=str(config),
            service_name=str(configured.get("service_name") or "chat"),
        )
        if target.port <= 0:
            raise ValueError("dedicated group gateway requires a positive port")
        path = self._group_state_path(group)
        existing = self._read_state(path)
        if self._state_matches(existing, target) and self._process_alive(existing.get("pid")):
            return {**existing, "started": False, "status": "running", "process_alive": True, "state_path": str(path)}
        if existing.get("status") == "running" and self._process_alive(existing.get("pid")):
            raise RuntimeError(f"group gateway {group} is already running on {existing.get('host')}:{existing.get('port')}")
        pid = self._spawn(target)
        state = {**target.to_dict(), "pid": pid, "status": "running", "process_alive": True, "started_unix_seconds": time.time()}
        self._write_group_state(group, state)
        return {**state, "started": True, "state_path": str(path)}

    def stop_group(self, group_id: str) -> JsonDict:
        group = str(group_id or "").strip()
        path = self._group_state_path(group)
        state = self._read_state(path)
        if not state:
            return {"kind": "group", "group_id": group, "status": "not_started", "process_alive": False, "stopped": False, "state_path": str(path)}
        pid = self._int_pid(state.get("pid"))
        alive = self._process_alive(pid)
        if alive and pid is not None:
            self._terminate(pid)
        state.update({"status": "stopped", "process_alive": False, "stopped_unix_seconds": time.time()})
        self._write_group_state(group, state)
        return {**state, "stopped": bool(alive), "state_path": str(path)}

    def group_status(self, group_id: str) -> JsonDict:
        group = str(group_id or "").strip()
        path = self._group_state_path(group)
        state = self._read_state(path)
        if not state:
            return {
                "kind": "group",
                "group_id": group,
                "status": "not_started",
                "process_alive": False,
                "state_path": str(path),
                "metrics_path": str(path.parent / "metrics.json"),
            }
        alive = self._process_alive(state.get("pid"))
        recorded = str(state.get("status") or "not_started")
        result = {
            **state,
            "status": "running" if recorded == "running" and alive else "stale" if recorded == "running" else recorded,
            "process_alive": alive,
            "state_path": str(path),
            "metrics_path": str(path.parent / "metrics.json"),
        }
        metrics = self._read_state(path.parent / "metrics.json")
        if metrics:
            result["metrics"] = metrics
        return result

    def group_statuses(self) -> list[JsonDict]:
        root = self.gateway_root / "groups"
        if not root.is_dir():
            return []
        return [self.group_status(path.name) for path in sorted(root.iterdir()) if path.is_dir()]

    def _spawn(self, target: GatewayTarget) -> int:
        # Keep the child invocation compatible with older installed RIFT
        # launchers; the service-gateway command defaults to foreground run.
        command = [self.python_executable, "-m", "rift.cli", "service", "gateway", "--config", target.config_path, "--service", target.service_name, "--host", target.host, "--port", str(target.port)]
        if target.group_id:
            command.extend(["--group", target.group_id])
        log_name = "gateway.log" if target.kind == "main" else f"gateway-{target.group_id}.log"
        log_path = self.runtime_root / "logs" / log_name
        log_path.parent.mkdir(parents=True, exist_ok=True)
        flags = 0
        if os.name == "nt":
            flags = (
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NO_WINDOW", 0)
                | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
            )
        with log_path.open("ab", buffering=0) as output:
            environment = os.environ.copy()
            environment["RIFT_HOME"] = str(self.runtime_root)
            try:
                process = subprocess.Popen(
                    command,
                    cwd=str(self.root),
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    env=environment,
                    creationflags=flags,
                    start_new_session=os.name != "nt",
                )
            except OSError:
                process = subprocess.Popen(
                    command,
                    cwd=str(self.root),
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    env=environment,
                    start_new_session=os.name != "nt",
                )
        return int(process.pid)

    def _terminate(self, pid: int) -> None:
        if os.name == "nt":
            if psutil is not None:
                try:
                    process = psutil.Process(pid)
                    process.terminate()
                    return
                except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                    pass
            try:
                os.kill(pid, signal.SIGTERM)
                return
            except (OSError, ValueError):
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True, text=True)
                return
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return

    def _process_alive(self, pid: Any) -> bool:
        value = self._int_pid(pid)
        if value is None:
            return False
        if psutil is not None:
            try:
                return bool(psutil.pid_exists(value))
            except (OSError, ValueError):
                return False
        if os.name == "nt":
            try:
                os.kill(value, 0)
                return True
            except ProcessLookupError:
                return False
            except PermissionError:
                return True
        try:
            os.kill(value, 0)
            return True
        except OSError:
            return False

    @staticmethod
    def _int_pid(pid: Any) -> int | None:
        try:
            value = int(pid)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    @staticmethod
    def _state_matches(state: JsonDict, target: GatewayTarget) -> bool:
        return all(state.get(key) == value for key, value in target.to_dict().items())

    @staticmethod
    def _read_state(path: Path) -> JsonDict:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _write_state(value: JsonDict, path: Path | None = None) -> None:
        if path is None:
            raise ValueError("state path is required")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(path)

    def _write_group_state(self, group_id: str, value: JsonDict) -> None:
        self._write_state(value, self._group_state_path(group_id))

    def _group_state_path(self, group_id: str) -> Path:
        return self.gateway_root / "groups" / group_id / "state.json"

    def _resolve_config(self, config_path: str | Path | None) -> Path:
        if config_path:
            path = Path(config_path)
            if not path.is_absolute():
                path = self.root / path
            return path.resolve()
        candidate = self.root / "rift.yaml"
        if candidate.is_file():
            return candidate.resolve()
        plans = sorted(self.runtime_root.glob("deployments/*.yaml"))
        if plans:
            return plans[-1].resolve()
        raise FileNotFoundError("no active RIFT configuration found; pass --config")

    @staticmethod
    def _configured_gateway(config: Path, service_name: str) -> JsonDict:
        try:
            payload = read_yaml(config)
        except (OSError, ValueError):
            payload = {}
        service = ((payload.get("services") or {}).get(service_name) or {}) if isinstance(payload, dict) else {}
        gateway = service.get("gateway") if isinstance(service, dict) else {}
        return dict(gateway) if isinstance(gateway, dict) else {}

    def _group_config(self, config: Path, group_id: str) -> JsonDict:
        try:
            payload = read_yaml(config)
        except (OSError, ValueError):
            payload = {}
        groups = payload.get("groups") if isinstance(payload, dict) else None
        group = groups.get(group_id) if isinstance(groups, dict) else None
        if not isinstance(group, dict):
            # Mesh catalog groups are persisted beside the runtime state.
            catalog_path = self.runtime_root / "mesh" / "services.json"
            catalog = self._read_state(catalog_path)
            group = next((item for item in catalog.get("groups", []) if isinstance(item, dict) and item.get("group_id") == group_id), None)
        if not isinstance(group, dict):
            raise KeyError(f"unknown service group: {group_id}")
        dedicated = group.get("dedicated_listener") if isinstance(group.get("dedicated_listener"), dict) else group
        return dict(dedicated)


__all__ = ["GatewayManager", "GatewayTarget"]
