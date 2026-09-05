"""Permissioned agentless remote transports for RIFT nodes."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import shutil
import ssl
import subprocess
from typing import Any, Callable, Protocol
from urllib.request import Request, urlopen


JsonDict = dict[str, Any]
Runner = Callable[..., subprocess.CompletedProcess[str]]


class RemoteTransport(Protocol):
    name: str

    def detect(self) -> JsonDict: ...
    def discovery_plan(self, node: JsonDict) -> JsonDict: ...
    def discover(self, node: JsonDict, *, allow_remote: bool = False) -> JsonDict: ...


@dataclass(frozen=True)
class TransportCommand:
    args: list[str]
    display: str
    destructive: bool = False


class SshTransport:
    name = "ssh"

    def __init__(self, runner: Runner = subprocess.run) -> None:
        self.runner = runner

    def detect(self) -> JsonDict:
        executable = shutil.which("ssh")
        return {
            "transport": self.name,
            "available": bool(executable),
            "executable": executable,
            "authentication": "OpenSSH config/agent; RIFT does not persist private keys",
            "host_key_policy": "strict",
            "verification_status": "implemented_not_remote_verified",
        }

    def discovery_plan(self, node: JsonDict) -> JsonDict:
        host = self._host(node)
        executable = self.detect().get("executable") or "ssh"
        remote = (
            "python3 -c 'import json,os,platform,shutil;"
            "d=shutil.disk_usage(os.getcwd());"
            "print(json.dumps({\"hostname\":platform.node(),\"os\":platform.system(),"
            "\"architecture\":platform.machine(),\"logical_cpu_count\":os.cpu_count(),"
            "\"disk_total_bytes\":d.total,\"disk_free_bytes\":d.free}))'"
        )
        args = [
            str(executable),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "ConnectTimeout=8",
            host,
            remote,
        ]
        return {
            "transport": self.name,
            "node": node.get("name"),
            "host": host,
            "command": args,
            "display": " ".join(args[:-1] + ["<remote hardware probe>"]),
            "requires_permission": "allow_remote",
            "read_only": True,
        }

    def discover(self, node: JsonDict, *, allow_remote: bool = False) -> JsonDict:
        plan = self.discovery_plan(node)
        if not allow_remote:
            return {"executed": False, "reason": "remote discovery requires allow_remote", "plan": plan}
        detection = self.detect()
        if not detection["available"]:
            return {"executed": False, "reason": "ssh executable is unavailable", "plan": plan}
        result = self.runner(plan["command"], capture_output=True, text=True, timeout=15, check=False)
        payload = self._json_output(result.stdout)
        return {
            "executed": True,
            "ok": result.returncode == 0 and payload is not None,
            "returncode": result.returncode,
            "hardware": payload,
            "stderr": result.stderr.strip()[:1000],
            "plan": plan,
        }

    @staticmethod
    def _host(node: JsonDict) -> str:
        host = str(node.get("host") or "").strip()
        user = str(node.get("user") or "").strip()
        if not host:
            raise ValueError("SSH node host is required")
        return f"{user}@{host}" if user else host

    @staticmethod
    def _json_output(output: str) -> JsonDict | None:
        try:
            payload = json.loads(output.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None


class PowerShellRemotingTransport:
    name = "powershell_remoting"

    def __init__(self, runner: Runner = subprocess.run) -> None:
        self.runner = runner

    def detect(self) -> JsonDict:
        executable = shutil.which("pwsh") or shutil.which("powershell")
        return {
            "transport": self.name,
            "available": bool(executable and os.name == "nt"),
            "executable": executable,
            "authentication": "WinRM/PowerShell session policy; credentials are supplied by the OS",
            "verification_status": "implemented_not_remote_verified",
        }

    def discovery_plan(self, node: JsonDict) -> JsonDict:
        host = str(node.get("host") or "").strip()
        if not host:
            raise ValueError("PowerShell remoting node host is required")
        executable = self.detect().get("executable") or "powershell"
        script = (
            "$d=Get-CimInstance Win32_OperatingSystem;"
            "$c=Get-CimInstance Win32_ComputerSystem;"
            "$v=Get-Volume | Where-Object DriveLetter | Sort-Object SizeRemaining -Descending | Select-Object -First 1;"
            "[pscustomobject]@{hostname=$env:COMPUTERNAME;os=$d.Caption;"
            "logical_cpu_count=$c.NumberOfLogicalProcessors;host_ram_bytes=[int64]$c.TotalPhysicalMemory;"
            "disk_total_bytes=[int64]$v.Size;disk_free_bytes=[int64]$v.SizeRemaining}|ConvertTo-Json -Compress"
        )
        args = [
            str(executable),
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"Invoke-Command -ComputerName '{host}' -ScriptBlock {{ {script} }}",
        ]
        return {
            "transport": self.name,
            "node": node.get("name"),
            "host": host,
            "command": args,
            "display": f"{executable} Invoke-Command -ComputerName {host} <hardware probe>",
            "requires_permission": "allow_remote",
            "read_only": True,
        }

    def discover(self, node: JsonDict, *, allow_remote: bool = False) -> JsonDict:
        plan = self.discovery_plan(node)
        if not allow_remote:
            return {"executed": False, "reason": "remote discovery requires allow_remote", "plan": plan}
        detection = self.detect()
        if not detection["available"]:
            return {"executed": False, "reason": "PowerShell remoting is unavailable", "plan": plan}
        result = self.runner(plan["command"], capture_output=True, text=True, timeout=20, check=False)
        try:
            payload = json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            payload = None
        return {
            "executed": True,
            "ok": result.returncode == 0 and isinstance(payload, dict),
            "returncode": result.returncode,
            "hardware": payload,
            "stderr": result.stderr.strip()[:1000],
            "plan": plan,
        }


class RiftAgentTransport:
    """Authenticated controller-to-node transport using the RIFT mTLS agent API."""

    name = "rift_agent"

    def detect(self) -> JsonDict:
        return {
            "transport": self.name,
            "available": True,
            "authentication": "mutual TLS with controller and node certificates",
            "minimum_tls_version": "TLSv1.2",
            "verification_status": "implemented_acceptance_emulated",
        }

    def discovery_plan(self, node: JsonDict) -> JsonDict:
        agent = self._agent_config(node)
        return {
            "transport": self.name,
            "node": node.get("name"),
            "url": f"{agent['url']}/v1/discovery",
            "requires_permission": "allow_remote",
            "read_only": True,
            "mutual_tls": True,
        }

    def discover(self, node: JsonDict, *, allow_remote: bool = False) -> JsonDict:
        plan = self.discovery_plan(node)
        if not allow_remote:
            return {
                "executed": False,
                "reason": "RIFT agent discovery requires allow_remote",
                "plan": plan,
            }
        try:
            payload = self._request(node, method="GET", path="/v1/discovery")
        except Exception as exc:
            return {"executed": True, "ok": False, "error": str(exc), "plan": plan}
        return {
            "executed": True,
            "ok": True,
            "hardware": payload.get("hardware") or {},
            "backends": payload.get("backends") or {},
            "artifact_inventory": payload.get("artifact_inventory") or {},
            "agent": payload.get("agent") or {},
            "plan": plan,
        }

    def submit_desired_state(
        self,
        node: JsonDict,
        *,
        generation: int,
        config: JsonDict,
        allow_remote: bool = False,
    ) -> JsonDict:
        if not allow_remote:
            return {
                "executed": False,
                "reason": "desired-state submission requires allow_remote",
                "required_permission": "allow_remote",
            }
        return self._request(
            node,
            method="POST",
            path="/v1/desired-state",
            payload={"generation": int(generation), "config": config},
        )

    def reconcile(
        self,
        node: JsonDict,
        *,
        permissions: JsonDict,
        allow_remote: bool = False,
    ) -> JsonDict:
        if not allow_remote:
            return {
                "executed": False,
                "reason": "remote reconciliation requires allow_remote",
                "required_permission": "allow_remote",
            }
        return self._request(
            node,
            method="POST",
            path="/v1/reconcile",
            payload={"apply": True, "permissions": permissions},
        )

    def status(self, node: JsonDict, *, allow_remote: bool = False) -> JsonDict:
        if not allow_remote:
            return {"executed": False, "required_permission": "allow_remote"}
        return self._request(node, method="GET", path="/v1/state")

    def inference(
        self,
        node: JsonDict,
        *,
        service: str,
        path: str,
        body: JsonDict,
        allow_remote: bool = False,
    ) -> JsonDict:
        if not allow_remote:
            return {
                "executed": False,
                "reason": "remote inference requires allow_remote",
                "required_permission": "allow_remote",
            }
        return self._request(
            node,
            method="POST",
            path="/v1/inference",
            payload={"service": service, "path": path, "body": body},
        )

    def _request(
        self,
        node: JsonDict,
        *,
        method: str,
        path: str,
        payload: JsonDict | None = None,
    ) -> JsonDict:
        agent = self._agent_config(node)
        context = ssl.create_default_context(cafile=agent["ca_certificate"])
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.check_hostname = True
        context.load_cert_chain(
            certfile=agent["client_certificate"], keyfile=agent["client_key"]
        )
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{agent['url']}{path}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json", "User-Agent": "RIFT-Controller/1"},
        )
        with urlopen(request, context=context, timeout=15) as response:
            decoded = json.loads(response.read().decode("utf-8"))
        if not isinstance(decoded, dict):
            raise ValueError("RIFT node agent returned a non-object response")
        return decoded

    @staticmethod
    def _agent_config(node: JsonDict) -> JsonDict:
        agent = node.get("agent") or node.get("transport_config") or {}
        if not isinstance(agent, dict):
            raise ValueError("RIFT agent configuration must be an object")
        url = str(agent.get("url") or "").rstrip("/")
        if not url.startswith("https://"):
            raise ValueError("RIFT agent URL must use https://")
        result = {
            "url": url,
            "ca_certificate": str(agent.get("ca_certificate") or ""),
            "client_certificate": str(agent.get("client_certificate") or ""),
            "client_key": str(agent.get("client_key") or ""),
        }
        missing = [name for name, value in result.items() if name != "url" and not value]
        if missing:
            raise ValueError(f"RIFT agent TLS configuration is missing: {', '.join(missing)}")
        return result

def transport_registry() -> dict[str, RemoteTransport]:
    return {
        "ssh": SshTransport(),
        "powershell_remoting": PowerShellRemotingTransport(),
        "rift_agent": RiftAgentTransport(),
    }


__all__ = [
    "PowerShellRemotingTransport",
    "RemoteTransport",
    "RiftAgentTransport",
    "SshTransport",
    "TransportCommand",
    "transport_registry",
]
