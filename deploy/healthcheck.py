"""Dependency-free health probe shared by RIFT OCI roles."""

from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.request


def _target(role: str) -> tuple[str, ssl.SSLContext | None]:
    if role == "controller":
        port = os.environ.get("RIFT_CONTROLLER_PORT", "8777")
        return f"http://127.0.0.1:{port}/health", None
    if role == "gateway":
        port = os.environ.get("RIFT_GATEWAY_PORT", "11734")
        return f"http://127.0.0.1:{port}/health", None
    if role == "emulator":
        port = os.environ.get("RIFT_EMULATOR_PORT", "8788")
        return f"http://127.0.0.1:{port}/health", None
    if role == "node":
        port = os.environ.get("RIFT_NODE_PORT", "11750")
        context = ssl.create_default_context(
            cafile=os.environ.get("RIFT_NODE_HEALTH_CA", "/run/secrets/rift/controller-ca.crt")
        )
        context.load_cert_chain(
            certfile=os.environ.get("RIFT_NODE_HEALTH_CERT", "/run/secrets/rift/health-client.crt"),
            keyfile=os.environ.get("RIFT_NODE_HEALTH_KEY", "/run/secrets/rift/health-client.key"),
        )
        return f"https://127.0.0.1:{port}/v1/health", context
    raise ValueError(f"unknown RIFT role: {role}")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: healthcheck.py controller|node|gateway|emulator", file=sys.stderr)
        return 2
    try:
        url, context = _target(sys.argv[1])
        with urllib.request.urlopen(url, timeout=3.0, context=context) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return 0 if response.status == 200 and payload.get("ok", True) is not False else 1
    except Exception as exc:
        print(f"RIFT health check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
