"""Approved, resumable model artifact downloads with atomic activation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


class ResumableArtifactStore:
    def __init__(self, state_root: Path | str):
        self.state_root = Path(state_root)
        self.state_root.mkdir(parents=True, exist_ok=True)

    def download(
        self,
        url: str,
        destination: Path | str,
        *,
        expected_digest: str,
        expected_size: int | None = None,
        approved: bool = False,
        network: str = "unmetered",
        allow_cellular: bool = False,
        opener: Callable[[Request], Any] = urlopen,
    ) -> dict[str, object]:
        if not approved:
            raise PermissionError("model download requires explicit user approval")
        if network == "cellular" and not allow_cellular:
            raise PermissionError("cellular model downloads require explicit override")
        if not expected_digest.startswith("sha256:") or len(expected_digest) != 71:
            raise ValueError("expected_digest must be sha256:<64 hex characters>")
        try:
            int(expected_digest[7:], 16)
        except ValueError as exc:
            raise ValueError("expected_digest must be sha256:<64 hex characters>") from exc
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".partial")
        state_path = partial.with_suffix(partial.suffix + ".json")
        offset = partial.stat().st_size if partial.is_file() else 0
        headers = {"Accept": "application/octet-stream"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        request = Request(str(url), headers=headers, method="GET")
        with opener(request) as response:
            status = int(getattr(response, "status", 200) or 200)
            if offset and status != 206:
                offset = 0
                partial.write_bytes(b"")
            mode = "ab" if offset else "wb"
            written = offset
            with partial.open(mode) as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    written += len(chunk)
            etag = None
            response_headers = getattr(response, "headers", {})
            if hasattr(response_headers, "get"):
                etag = response_headers.get("ETag") or response_headers.get("etag")
        state_path.write_text(
            json.dumps({"url": str(url), "etag": etag, "bytes": written}, sort_keys=True),
            encoding="utf-8",
        )
        if expected_size is not None and written != int(expected_size):
            raise ValueError(f"download size mismatch: expected {expected_size}, got {written}")
        digest = hashlib.sha256()
        with partial.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        actual = "sha256:" + digest.hexdigest()
        if actual != expected_digest:
            raise ValueError(f"download hash mismatch: expected {expected_digest}, got {actual}")
        partial.replace(target)
        try:
            state_path.unlink()
        except FileNotFoundError:
            pass
        return {"activated": True, "path": str(target), "bytes": written, "sha256": actual, "etag": etag}


__all__ = ["ResumableArtifactStore"]
