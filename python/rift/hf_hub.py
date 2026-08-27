"""Small stdlib Hugging Face Hub downloader used by RIFT."""

from __future__ import annotations

from dataclasses import dataclass
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
from typing import Any, Iterable, Optional
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .runtime_paths import RiftPaths


DEFAULT_ALLOW_PATTERNS = (
    "*.safetensors",
    "*.gguf",
    "*.json",
    "*.model",
    "*.txt",
    "*.md",
    "*.tiktoken",
)
DEFAULT_IGNORE_PATTERNS = (
    "*.bin",
    "*.pt",
    "*.pth",
    "*.onnx",
    "*.h5",
    "*.msgpack",
)


@dataclass(frozen=True)
class HubFile:
    path: str
    size: Optional[int] = None


class HfHubClient:
    """Minimal Hugging Face Hub HTTP client.

    The implementation intentionally mirrors the useful subset of
    huggingface_hub.snapshot_download without depending on that package.
    """

    def __init__(
        self,
        endpoint: str = "https://huggingface.co",
        token: Optional[str] = None,
        cache_dir: Optional[str] = None,
        cache_ttl_seconds: int = 24 * 60 * 60,
        cache_max_bytes: int = 256 * 1024**2,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.token = token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        self.cache_dir = Path(cache_dir) if cache_dir else RiftPaths.from_environment().cache / "hub_cache"
        self.cache_ttl_seconds = cache_ttl_seconds
        self.cache_max_bytes = max(0, int(cache_max_bytes))

    def model_info(
        self,
        repo_id: str,
        revision: str = "main",
        expand: Optional[Iterable[str]] = None,
        refresh: bool = False,
    ) -> dict[str, Any]:
        url = f"{self.endpoint}/api/models/{quote(repo_id, safe='/')}/revision/{quote(revision, safe='')}"
        query = self._query_string({"expand": list(expand or [])})
        if query:
            url = f"{url}?{query}"
        payload = self._request_json(url, refresh=refresh)
        if not isinstance(payload, dict):
            raise ValueError(f"model_info returned non-object payload for {repo_id}")
        return payload

    def search_models(
        self,
        *,
        search: Optional[str] = None,
        pipeline_tag: Optional[str] = None,
        filters: Optional[Iterable[str]] = None,
        sort: Optional[str] = None,
        direction: int = -1,
        limit: int = 50,
        gated: Optional[bool] = None,
        num_parameters: Optional[str] = None,
        expand: Optional[Iterable[str]] = None,
        refresh: bool = False,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        query = self._query_string(
            {
                "search": search,
                "pipeline_tag": pipeline_tag,
                "filter": list(filters or []),
                "sort": sort,
                "direction": direction,
                "limit": limit,
                "gated": str(gated).lower() if gated is not None else None,
                "num_parameters": num_parameters,
                "expand": list(expand or []),
                "full": "true" if expand else None,
                "config": "true" if expand else None,
            }
        )
        url = f"{self.endpoint}/api/models"
        if query:
            url = f"{url}?{query}"
        payload = self._request_json(url, refresh=refresh)
        if not isinstance(payload, list):
            raise ValueError("search_models returned non-list payload")
        return [dict(item) for item in payload if isinstance(item, dict)]

    def list_model_files(
        self,
        repo_id: str,
        revision: str = "main",
        *,
        refresh: bool = False,
        resolve_sizes: bool = True,
    ) -> list[HubFile]:
        info = self.model_info(repo_id, revision=revision, refresh=refresh)
        files: list[HubFile] = []
        for sibling in info.get("siblings", []):
            name = sibling.get("rfilename") or sibling.get("path")
            if not name:
                continue
            size = sibling.get("size")
            files.append(HubFile(str(name), int(size) if isinstance(size, int) else None))
        if resolve_sizes and files and any(file.size is None for file in files):
            try:
                tree = self.list_repo_tree(repo_id, revision=revision, refresh=refresh)
            except Exception:
                return files
            exact = {file.path: file.size for file in tree}
            files = [HubFile(file.path, exact.get(file.path, file.size)) for file in files]
        return files

    def list_repo_tree(
        self,
        repo_id: str,
        revision: str = "main",
        *,
        recursive: bool = True,
        expand: bool = True,
        refresh: bool = False,
    ) -> list[HubFile]:
        """Return exact repository file metadata for an enriched finalist.

        The Hub's model listing commonly exposes sibling names without byte
        sizes. The repository tree endpoint is more expensive, so callers use
        this only after cheap candidate ranking.
        """

        url = (
            f"{self.endpoint}/api/models/{quote(repo_id, safe='/')}/tree/"
            f"{quote(revision, safe='')}"
        )
        query = self._query_string(
            {
                "recursive": str(bool(recursive)).lower(),
                "expand": str(bool(expand)).lower(),
            }
        )
        if query:
            url = f"{url}?{query}"
        payload = self._request_json(url, refresh=refresh)
        if not isinstance(payload, list):
            raise ValueError(f"repository tree returned non-list payload for {repo_id}")
        files: list[HubFile] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("type") or "file").lower()
            if kind not in ("file", "blob"):
                continue
            name = item.get("path") or item.get("rfilename") or item.get("name")
            if not name:
                continue
            size = item.get("size")
            lfs = item.get("lfs")
            if not isinstance(size, int) and isinstance(lfs, dict):
                size = lfs.get("size")
            files.append(HubFile(str(name), int(size) if isinstance(size, int) else None))
        return files

    def snapshot_download(
        self,
        repo_id: str,
        *,
        revision: str = "main",
        local_dir: Optional[str] = None,
        allow_patterns: Optional[Iterable[str]] = None,
        ignore_patterns: Optional[Iterable[str]] = None,
        dry_run: bool = False,
        max_bytes: Optional[int] = None,
        disk_reserve_bytes: int = 2 * 1024**3,
    ) -> dict[str, Any]:
        files = self.list_model_files(repo_id, revision=revision)
        selected = select_hub_files(
            files,
            allow_patterns=allow_patterns or DEFAULT_ALLOW_PATTERNS,
            ignore_patterns=ignore_patterns or DEFAULT_IGNORE_PATTERNS,
        )
        unknown_size_paths = [file.path for file in selected if file.size is None]
        total_known_bytes = sum(file.size or 0 for file in selected)
        if max_bytes is not None and max_bytes > 0 and unknown_size_paths:
            raise ValueError(
                "max_bytes cannot be enforced because selected files have unknown sizes: "
                + ", ".join(unknown_size_paths[:8])
            )
        if max_bytes is not None and max_bytes > 0 and total_known_bytes > max_bytes:
            raise ValueError(
                f"selected files total {total_known_bytes} bytes, exceeding max_bytes={max_bytes}"
            )
        target_dir = (
            Path(local_dir)
            if local_dir
            else RiftPaths.from_environment().models / "hub" / repo_id.replace("/", "--")
        )
        disk = disk_capacity(target_dir, reserve_bytes=max(0, int(disk_reserve_bytes)))
        if total_known_bytes > int(disk["usable_bytes"]):
            raise ValueError(
                "selected files require "
                f"{total_known_bytes} bytes but only {disk['usable_bytes']} bytes are usable "
                f"on {disk['anchor']} after the disk reserve"
            )
        result: dict[str, Any] = {
            "repo_id": repo_id,
            "revision": revision,
            "local_dir": str(target_dir),
            "dry_run": dry_run,
            "file_count": len(selected),
            "total_known_bytes": total_known_bytes,
            "disk": disk,
            "files": [
                {"path": file.path, "size": file.size, "selected": True}
                for file in selected
            ],
        }
        if dry_run:
            return result

        target_dir.mkdir(parents=True, exist_ok=True)
        downloaded: list[dict[str, Any]] = []
        for file in selected:
            local_path = safe_join(target_dir, file.path)
            local_path.parent.mkdir(parents=True, exist_ok=True)
            bytes_written = self._download_file(
                repo_id,
                revision,
                file.path,
                local_path,
                expected_size=file.size,
            )
            downloaded.append(
                {
                    "path": file.path,
                    "local_path": str(local_path),
                    "bytes": bytes_written,
                    "sha256": self._sha256(local_path),
                    "integrity": "size_and_sha256_recorded",
                }
            )
        result["downloaded"] = downloaded
        result["downloaded_bytes"] = sum(item["bytes"] for item in downloaded)
        return result

    def _download_file(
        self,
        repo_id: str,
        revision: str,
        filename: str,
        local_path: Path,
        *,
        expected_size: int | None = None,
    ) -> int:
        url = (
            f"{self.endpoint}/{quote(repo_id, safe='/')}/resolve/"
            f"{quote(revision, safe='')}/{quote(filename, safe='/')}"
        )
        part_path = local_path.with_suffix(local_path.suffix + ".part")
        resume_from = part_path.stat().st_size if part_path.exists() else 0
        # Xet-backed Hub files can stall on an unbounded initial response.
        # A zero-offset range still permits a full download while making the
        # transport use the same resumable path as subsequent requests.
        headers: dict[str, str] = {"Range": f"bytes={resume_from}-"}
        request = self._request(url, headers=headers)
        try:
            response = urlopen(request, timeout=60)
        except HTTPError as exc:
            if exc.code == 416 and part_path.exists():
                part_path.replace(local_path)
                return local_path.stat().st_size
            raise
        mode = "ab" if resume_from > 0 and response.status == 206 else "wb"
        if mode == "wb":
            resume_from = 0
        bytes_written = resume_from
        with response, part_path.open(mode) as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                bytes_written += len(chunk)
        if expected_size is not None and bytes_written != int(expected_size):
            raise IOError(
                f"downloaded size mismatch for {filename}: expected {expected_size}, got {bytes_written}; "
                f"partial file retained at {part_path} for repair/resume"
            )
        part_path.replace(local_path)
        return bytes_written

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(4 * 1024**2), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _request_json(self, url: str, *, refresh: bool = False) -> Any:
        if not refresh:
            cached = self._read_cache(url)
            if cached is not None:
                return cached
        request = self._request(url)
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self._write_cache(url, payload)
        return payload

    def _request(self, url: str, headers: Optional[dict[str, str]] = None) -> Request:
        merged = {"User-Agent": "RIFT/1.0"}
        if headers:
            merged.update(headers)
        if self.token:
            merged["Authorization"] = f"Bearer {self.token}"
        return Request(url, headers=merged)

    def _query_string(self, values: dict[str, Any]) -> str:
        pairs: list[tuple[str, str]] = []
        for key, value in values.items():
            if value is None or value == "":
                continue
            if isinstance(value, (list, tuple, set)):
                for item in value:
                    if item not in (None, ""):
                        pairs.append((key, str(item)))
            else:
                pairs.append((key, str(value)))
        return urlencode(pairs)

    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _read_cache(self, url: str) -> Any | None:
        path = self._cache_path(url)
        if self.cache_ttl_seconds <= 0 or not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        created = float(payload.get("created_unix_seconds") or 0.0)
        if time.time() - created > self.cache_ttl_seconds:
            try:
                path.unlink()
            except OSError:
                pass
            return None
        try:
            os.utime(path, None)
        except OSError:
            pass
        return payload.get("payload")

    def _write_cache(self, url: str, payload: Any) -> None:
        if self.cache_ttl_seconds <= 0:
            return
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            target = self._cache_path(url)
            temporary = target.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(
                    {
                        "created_unix_seconds": time.time(),
                        "url": url,
                        "payload": payload,
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            temporary.replace(target)
            self._prune_cache()
        except OSError:
            return

    def cache_status(self) -> dict[str, Any]:
        files = list(self.cache_dir.glob("*.json")) if self.cache_dir.is_dir() else []
        total = sum(path.stat().st_size for path in files if path.is_file())
        return {
            "path": str(self.cache_dir),
            "entry_count": len(files),
            "bytes": total,
            "maximum_bytes": self.cache_max_bytes,
            "ttl_seconds": self.cache_ttl_seconds,
        }

    def _prune_cache(self) -> None:
        if not self.cache_dir.is_dir():
            return
        entries = []
        now = time.time()
        for path in self.cache_dir.glob("*.json"):
            try:
                stat = path.stat()
            except OSError:
                continue
            if self.cache_ttl_seconds > 0 and now - stat.st_mtime > self.cache_ttl_seconds:
                try:
                    path.unlink()
                except OSError:
                    pass
                continue
            entries.append((stat.st_mtime, stat.st_size, path))
        total = sum(item[1] for item in entries)
        if self.cache_max_bytes <= 0:
            return
        for _, size, path in sorted(entries):
            if total <= self.cache_max_bytes:
                break
            try:
                path.unlink()
                total -= size
            except OSError:
                continue


def normalize_patterns(patterns: Optional[Iterable[str]]) -> tuple[str, ...]:
    if patterns is None:
        return ()
    if isinstance(patterns, str):
        return (patterns,)
    return tuple(str(pattern) for pattern in patterns)


def select_hub_files(
    files: Iterable[HubFile],
    *,
    allow_patterns: Optional[Iterable[str]],
    ignore_patterns: Optional[Iterable[str]],
) -> list[HubFile]:
    allow = normalize_patterns(allow_patterns)
    ignore = normalize_patterns(ignore_patterns)
    selected: list[HubFile] = []
    for file in files:
        if not is_safe_remote_path(file.path):
            continue
        allowed = True if not allow else any(fnmatch.fnmatch(file.path, pattern) for pattern in allow)
        ignored = any(fnmatch.fnmatch(file.path, pattern) for pattern in ignore)
        if allowed and not ignored:
            selected.append(file)
    return selected


def is_safe_remote_path(path: str) -> bool:
    candidate = Path(path)
    return not candidate.is_absolute() and ".." not in candidate.parts


def safe_join(root: Path, relative: str) -> Path:
    if not is_safe_remote_path(relative):
        raise ValueError(f"unsafe remote path: {relative}")
    return root.joinpath(*Path(relative).parts)


def disk_capacity(path: str | Path, *, reserve_bytes: int = 2 * 1024**3) -> dict[str, Any]:
    """Measure download capacity at the nearest existing parent directory."""

    target = Path(path).expanduser()
    anchor = target
    while not anchor.exists() and anchor.parent != anchor:
        anchor = anchor.parent
    usage = shutil.disk_usage(anchor)
    reserve = max(0, int(reserve_bytes))
    return {
        "target": str(target),
        "anchor": str(anchor),
        "total_bytes": int(usage.total),
        "used_bytes": int(usage.used),
        "free_bytes": int(usage.free),
        "reserve_bytes": reserve,
        "usable_bytes": max(0, int(usage.free) - reserve),
    }


__all__ = [
    "DEFAULT_ALLOW_PATTERNS",
    "DEFAULT_IGNORE_PATTERNS",
    "HfHubClient",
    "HubFile",
    "disk_capacity",
    "select_hub_files",
]
