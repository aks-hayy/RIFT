"""Concrete, consent-aware discovery transports for RIFT nodes."""

from __future__ import annotations

import hashlib
import ipaddress
import json
from pathlib import Path
import socket
import ssl
import subprocess
import time
import threading
from typing import Callable, Iterable, Sequence
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .contracts import NodeSighting


BootstrapRecord = dict[str, object]
Probe = Callable[[str, str], BootstrapRecord | None]


def _decode_property(properties: dict[bytes, bytes | None], name: str, fallback: str = "") -> str:
    value = properties.get(name.encode("utf-8"))
    return value.decode("utf-8", errors="strict") if isinstance(value, bytes) else fallback


def _resolve_mdns(timeout_seconds: float) -> list[BootstrapRecord]:
    try:
        from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
    except ImportError as exc:
        raise RuntimeError(
            "mDNS discovery requires the 'zeroconf' package; install the RIFT mesh dependencies"
        ) from exc

    names: set[str] = set()
    changed = threading.Event()

    class Listener(ServiceListener):
        def add_service(self, zeroconf, service_type, name):
            names.add(name)
            changed.set()

        def update_service(self, zeroconf, service_type, name):
            names.add(name)
            changed.set()

        def remove_service(self, zeroconf, service_type, name):
            names.discard(name)

    service_type = "_rift-node._tcp.local."
    zeroconf = Zeroconf()
    browser = ServiceBrowser(zeroconf, service_type, Listener())
    try:
        changed.wait(timeout_seconds)
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            time.sleep(min(0.05, deadline - time.monotonic()))
        records: list[BootstrapRecord] = []
        for name in sorted(names):
            info = zeroconf.get_service_info(service_type, name, timeout=500)
            if info is None:
                continue
            addresses = info.parsed_addresses()
            if not addresses:
                continue
            properties = dict(info.properties)
            fingerprint = _decode_property(properties, "fingerprint")
            if not fingerprint:
                continue
            records.append(
                {
                    "endpoint": f"https://{addresses[0]}:{info.port}",
                    "node_hint": _decode_property(properties, "node", name.removesuffix(service_type)),
                    "api_version": _decode_property(properties, "api", "2"),
                    "bootstrap_fingerprint": fingerprint,
                    "ttl_seconds": 120,
                    "interface_id": _decode_property(properties, "interface", "mdns"),
                }
            )
        return records
    finally:
        browser.cancel()
        zeroconf.close()


def _sighting_from_record(
    record: BootstrapRecord,
    *,
    provider: str,
    interface_id: str,
    observed_at: float,
) -> NodeSighting:
    required = ("endpoint", "node_hint", "api_version", "bootstrap_fingerprint")
    missing = [key for key in required if not str(record.get(key) or "").strip()]
    if missing:
        raise ValueError(f"bootstrap record is missing: {', '.join(missing)}")
    return NodeSighting.create(
        provider=provider,
        endpoint=str(record["endpoint"]),
        node_hint=str(record["node_hint"]),
        api_version=str(record["api_version"]),
        bootstrap_fingerprint=str(record["bootstrap_fingerprint"]),
        ttl_seconds=float(record.get("ttl_seconds") or 120),
        observed_at=observed_at,
        interface_id=interface_id,
        metadata=dict(record.get("metadata") or {}),
    )


def probe_https_bootstrap(endpoint: str, interface_id: str, *, timeout: float = 0.35) -> BootstrapRecord | None:
    """Read an untrusted bootstrap record while binding identity to the TLS certificate hash."""

    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("discovery probe endpoint must be HTTPS")
    port = parsed.port or 443
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with socket.create_connection((parsed.hostname, port), timeout=timeout) as raw:
        with context.wrap_socket(raw, server_hostname=parsed.hostname) as tls:
            certificate = tls.getpeercert(binary_form=True)
    fingerprint = "sha256:" + hashlib.sha256(certificate).hexdigest()
    url = endpoint.rstrip("/") + "/.well-known/rift-node"
    with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=timeout, context=context) as response:
        if response.status != 200:
            return None
        record = json.loads(response.read(64 * 1024).decode("utf-8"))
    if not isinstance(record, dict):
        raise ValueError("node bootstrap response must be an object")
    advertised = str(record.get("bootstrap_fingerprint") or "")
    if advertised and advertised != fingerprint:
        raise ValueError("advertised bootstrap fingerprint does not match the TLS certificate")
    record["bootstrap_fingerprint"] = fingerprint
    record.setdefault("endpoint", endpoint)
    record.setdefault("metadata", {})
    record["metadata"] = {**dict(record["metadata"]), "interface_id": interface_id}
    return record


class PrivateSubnetDiscoveryProvider:
    name = "private-subnet"

    def __init__(
        self,
        *,
        networks: Sequence[str],
        authorized: bool,
        port: int = 11749,
        max_hosts: int = 256,
        interface_id: str = "lan",
        probe: Probe | None = None,
        clock: Callable[[], float] = time.time,
        provider_name: str | None = None,
    ) -> None:
        if max_hosts <= 0 or max_hosts > 4096:
            raise ValueError("max_hosts must be between 1 and 4096")
        parsed = tuple(ipaddress.ip_network(value, strict=False) for value in networks)
        if any(not network.is_private for network in parsed):
            raise ValueError("automatic subnet discovery is restricted to private address ranges")
        self.networks = parsed
        self.authorized = bool(authorized)
        self.port = int(port)
        self.max_hosts = int(max_hosts)
        self.interface_id = interface_id
        self.probe = probe or probe_https_bootstrap
        self.clock = clock
        if provider_name:
            self.name = provider_name

    def discover(self) -> Iterable[NodeSighting]:
        if not self.authorized:
            raise PermissionError("private subnet scanning requires explicit user consent")
        observed_at = float(self.clock())
        attempted = 0
        for network in self.networks:
            for address in network.hosts():
                if attempted >= self.max_hosts:
                    return
                attempted += 1
                endpoint = f"https://{address}:{self.port}"
                try:
                    record = self.probe(endpoint, self.interface_id)
                    if record is None:
                        continue
                    record.setdefault("endpoint", endpoint)
                    yield _sighting_from_record(
                        record,
                        provider=self.name,
                        interface_id=self.interface_id,
                        observed_at=observed_at,
                    )
                except (OSError, TimeoutError, ValueError, json.JSONDecodeError):
                    continue


class MdnsDiscoveryProvider:
    name = "mdns"

    def __init__(
        self,
        *,
        resolver: Callable[[], Iterable[BootstrapRecord]] | None = None,
        timeout_seconds: float = 1.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if timeout_seconds <= 0 or timeout_seconds > 10:
            raise ValueError("mDNS discovery timeout must be between 0 and 10 seconds")
        self.timeout_seconds = float(timeout_seconds)
        self.resolver = resolver or (lambda: _resolve_mdns(self.timeout_seconds))
        self.clock = clock

    def discover(self) -> Iterable[NodeSighting]:
        observed_at = float(self.clock())
        for record in self.resolver():
            interface_id = str(record.get("interface_id") or "mdns")
            yield _sighting_from_record(
                record,
                provider=self.name,
                interface_id=interface_id,
                observed_at=observed_at,
            )


class UsbNetworkDiscoveryProvider(PrivateSubnetDiscoveryProvider):
    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("provider_name", "usb-network")
        kwargs.setdefault("interface_id", "usb-network")
        super().__init__(**kwargs)


class MassStorageBootstrapProvider:
    name = "mass-storage"

    def __init__(
        self,
        *,
        roots: Iterable[Path | str],
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.roots = tuple(Path(root) for root in roots)
        self.clock = clock

    def discover(self) -> Iterable[NodeSighting]:
        observed_at = float(self.clock())
        for root in self.roots:
            marker = root / ".rift" / "rift-node.json"
            if not marker.is_file():
                continue
            try:
                record = json.loads(marker.read_text(encoding="utf-8"))
                if not isinstance(record, dict):
                    continue
                yield _sighting_from_record(
                    record,
                    provider=self.name,
                    interface_id=str(root.resolve()),
                    observed_at=observed_at,
                )
            except (OSError, ValueError, json.JSONDecodeError):
                continue


def _run_command(command: list[str]) -> str:
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return completed.stdout


class AdbBootstrapProvider:
    name = "adb"
    marker_path = "/sdcard/Android/data/dev.rift.node/files/rift-node.json"

    def __init__(
        self,
        *,
        adb_path: str = "adb",
        runner: Callable[[list[str]], str] = _run_command,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.adb_path = adb_path
        self.runner = runner
        self.clock = clock

    def discover(self) -> Iterable[NodeSighting]:
        observed_at = float(self.clock())
        try:
            output = self.runner([self.adb_path, "devices"])
        except (OSError, subprocess.SubprocessError):
            return
        serials = []
        for line in output.splitlines()[1:]:
            fields = line.strip().split()
            if len(fields) == 2 and fields[1] == "device":
                serials.append(fields[0])
        for serial in serials:
            try:
                raw = self.runner(
                    [self.adb_path, "-s", serial, "shell", "cat", self.marker_path]
                )
                record = json.loads(raw)
                if not isinstance(record, dict):
                    continue
                yield _sighting_from_record(
                    record,
                    provider=self.name,
                    interface_id=f"adb:{serial}",
                    observed_at=observed_at,
                )
            except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
                continue


__all__ = [
    "AdbBootstrapProvider",
    "MassStorageBootstrapProvider",
    "MdnsDiscoveryProvider",
    "PrivateSubnetDiscoveryProvider",
    "UsbNetworkDiscoveryProvider",
    "probe_https_bootstrap",
]
