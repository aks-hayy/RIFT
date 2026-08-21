"""Container entrypoint for the RIFT controller API."""

from __future__ import annotations

import os

from rift.server import serve_rift


def main() -> None:
    serve_rift(
        host=os.environ.get("RIFT_CONTROLLER_HOST", "0.0.0.0"),
        port=int(os.environ.get("RIFT_CONTROLLER_PORT", "8777")),
        model_path=os.environ.get("RIFT_MODEL_PATH") or None,
        plan_path=os.environ.get("RIFT_PLAN_PATH") or None,
    )


if __name__ == "__main__":
    main()
