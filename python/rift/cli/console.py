"""Dependency-free terminal presentation for RIFT."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from typing import Any, Iterable, Sequence


JsonDict = dict[str, Any]
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _enable_terminal_color(*, disabled: bool) -> bool:
    if disabled or "NO_COLOR" in os.environ:
        return False
    if not getattr(sys.stdout, "isatty", lambda: False)():
        return False
    if os.name != "nt":
        return True
    try:
        import ctypes
        import msvcrt

        kernel32 = ctypes.windll.kernel32
        for stream in (sys.stdout, sys.stderr):
            handle = msvcrt.get_osfhandle(stream.fileno())
            mode = ctypes.c_uint()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        return True
    except (AttributeError, OSError, ValueError):
        return False


class RiftConsole:
    """Render operator-friendly output while preserving a stable JSON mode."""

    _APPLY_PHASES = (
        ("planning", "Plan deployment"),
        ("installing", "Prepare backend"),
        ("downloading", "Materialize model"),
        ("launching", "Launch service"),
        ("persisting", "Persist state"),
    )

    def __init__(self, *, json_output: bool = False, no_color: bool = False) -> None:
        self.json_output = bool(json_output)
        self.color = _enable_terminal_color(disabled=no_color)
        self._progress_line_active = False

    def banner(self, command: str) -> None:
        if self.json_output or os.environ.get("RIFT_NO_BANNER") == "1":
            return
        width = min(88, max(58, shutil.get_terminal_size((100, 24)).columns - 2))
        context = command.upper().replace("_", " ")
        print(self._paint("=" * width, "38;5;27"))
        print(
            f"{self._paint('RIFT', '38;5;51;1')}  "
            f"{self._paint('LLM INFRASTRUCTURE CONTROL PLANE', '38;5;39;1')}  "
            f"{self._paint('// ' + context, '38;5;75')}"
        )
        print(self._paint("hardware-aware deployment / operations / recovery", "38;5;67"))
        print(self._paint("=" * width, "38;5;27"))

    def render(self, payload: Any, *, view: str = "result", title: str | None = None) -> None:
        if self.json_output:
            print(json.dumps(payload, indent=2, sort_keys=True, default=str))
            return
        renderer = getattr(self, f"_render_{view}", None)
        if callable(renderer):
            renderer(payload, title=title)
        else:
            self._render_result(payload, title=title)

    def error(self, message: str, *, hint: str | None = None) -> None:
        print(f"{self._paint('[FAIL]', '38;5;203;1')} {message}", file=sys.stderr)
        if hint:
            print(f"  {self._paint('[HINT]', '38;5;45')} {hint}", file=sys.stderr)

    def warning(self, message: str) -> None:
        print(f"{self._paint('[WARN]', '38;5;220;1')} {message}", file=sys.stderr)

    def success(self, message: str) -> None:
        print(f"{self._paint('[ OK ]', '38;5;84;1')} {message}")

    def apply_progress(
        self,
        phase: str,
        status: str,
        details: JsonDict | None = None,
    ) -> None:
        """Render one apply update without affecting structured/JSON output."""
        if self.json_output:
            return

        details = details or {}
        phase_index = next(
            (index for index, item in enumerate(self._APPLY_PHASES) if item[0] == phase),
            len(self._APPLY_PHASES) - 1,
        )
        phase_label = next(
            (item[1] for item in self._APPLY_PHASES if item[0] == phase),
            phase.replace("_", " ").title(),
        )
        terminal_statuses = {"complete", "item_complete", "skipped"}
        if status in terminal_statuses:
            within_phase = 1.0
        elif status in {"failed", "blocked"}:
            within_phase = 1.0
        else:
            try:
                completed = float(details.get("completed") or 0)
                total = float(details.get("total") or 0)
                within_phase = completed / total if total > 0 else 0.35
            except (TypeError, ValueError):
                within_phase = 0.35
            within_phase = min(max(within_phase, 0.0), 0.95)
        fraction = (phase_index + within_phase) / len(self._APPLY_PHASES)
        percent = int(round(min(max(fraction, 0.0), 1.0) * 100))
        width = 24
        filled = int(round(width * percent / 100))
        bar = self._paint("=" * filled, "38;5;51;1") + self._paint("." * (width - filled), "38;5;27")
        marker = {
            "complete": "OK",
            "item_complete": "OK",
            "skipped": "SKIP",
            "failed": "FAIL",
            "blocked": "BLOCK",
        }.get(status, "RUN")
        marker_color = "38;5;203;1" if marker in {"FAIL", "BLOCK"} else "38;5;84;1" if marker == "OK" else "38;5;220;1" if marker == "SKIP" else "38;5;51;1"
        detail = str(details.get("service") or details.get("backend") or details.get("reason") or "").strip()
        if details.get("reused"):
            detail = f"{detail} (cached)" if detail else "cached artifact"
        line = f"  {self._paint('[' + marker + ']', marker_color)} [{bar}] {percent:3d}% {phase_label}"
        if detail:
            line += f"  {self._dim(detail)}"
        interactive = bool(getattr(sys.stdout, "isatty", lambda: False)())
        if interactive:
            print("\r" + line, end="", flush=True)
            self._progress_line_active = True
            if status in terminal_statuses or status in {"failed", "blocked"} or phase == "complete":
                print()
                self._progress_line_active = False
        else:
            print(line)

    def _render_result(self, payload: Any, *, title: str | None = None) -> None:
        if title:
            self._heading(title)
        if not isinstance(payload, dict):
            print(payload)
            return
        scalars: list[tuple[str, str]] = []
        collections: list[tuple[str, Any]] = []
        for key, value in payload.items():
            if isinstance(value, (dict, list)):
                collections.append((key, value))
            elif value is not None:
                scalars.append((self._label(key), self._format(value)))
        if scalars:
            self._key_values(scalars)
        for key, value in collections:
            if key in {"reason", "reasons", "warnings", "next_actions", "notes"}:
                self._bullets(self._label(key), value if isinstance(value, list) else [value])
            elif isinstance(value, list) and value and all(not isinstance(item, dict) for item in value):
                self._bullets(self._label(key), value)
        if collections:
            print(self._dim("Full structured details are available with --json."))

    def _render_init(self, payload: JsonDict, *, title: str | None = None) -> None:
        if payload.get("created"):
            self.success(f"Created {payload.get('path')}")
        else:
            self.warning(str(payload.get("reason") or "Configuration was not changed."))
            if payload.get("path"):
                print(self._dim(f"Path: {payload['path']}"))

    def _render_discover(self, payload: JsonDict, *, title: str | None = None) -> None:
        self._heading(title or "Discovered infrastructure")
        rows = []
        for node in payload.get("nodes", []):
            hardware = node.get("hardware") or {}
            capacity = hardware.get("capacity") or {}
            identity = hardware.get("identity") or {}
            detection = node.get("backends") or {}
            if "providers" in detection:
                detection = detection["providers"]
            available = []
            for name, details in detection.items() if isinstance(detection, dict) else []:
                detected = details.get("detection", details) if isinstance(details, dict) else {}
                if detected.get("available"):
                    available.append(name)
            rows.append(
                [
                    node.get("name") or node.get("host") or "unknown",
                    identity.get("gpu") or hardware.get("device_name") or "CPU only",
                    self._bytes(capacity.get("vram_bytes") or hardware.get("total_vram_bytes")),
                    self._bytes(capacity.get("host_ram_bytes") or hardware.get("total_host_ram_bytes")),
                    ", ".join(available) or "none detected",
                    self._state(node.get("status") or "ready"),
                ]
            )
        self._table(["NODE", "ACCELERATOR", "VRAM", "RAM", "BACKENDS", "STATUS"], rows)
        print(self._dim("Run `rift model recommend --source local --models-dir PATH` to create an explainable deployment config."))

    def _render_recommend(self, payload: JsonDict, *, title: str | None = None) -> None:
        answer = payload.get("answer") or {}
        self._heading(title or "Hardware-fitted model recommendation")
        headline = answer.get("headline")
        if headline:
            print(self._paint(str(headline), "36;1"))
        why = answer.get("why") or []
        if why:
            self._bullets("Why", why)
        rows = []
        for item in (payload.get("recommendations") or [])[:10]:
            artifact = item.get("selected_artifact") or item.get("artifact") or {}
            file_name = artifact.get("filename") or item.get("selected_file") or "auto"
            rows.append(
                [
                    item.get("rank") or len(rows) + 1,
                    item.get("repo_id") or item.get("id") or "unknown",
                    self._paint(
                        f"{float(item.get('final_score') or item.get('score') or 0):.2f}",
                        "38;5;51;1",
                    ),
                    item.get("format") or "unknown",
                    item.get("backend") or item.get("recommended_backend") or "advice only",
                    file_name,
                    self._evidence_label(item),
                ]
            )
        self._table(["#", "MODEL", "SCORE", "FORMAT", "BACKEND", "ARTIFACT", "EVIDENCE"], rows)
        categories = payload.get("categories") or {}
        category_rows = []
        for key in (
            "best_published_quality",
            "best_estimated_fit",
            "best_verified_local",
            "fastest_verified_local",
            "best_deployment",
        ):
            item = categories.get(key)
            category_rows.append(
                [
                    key,
                    (item or {}).get("repo_id") or "none",
                    (item or {}).get("backend") or "-",
                    self._evidence_label(item or {}),
                ]
            )
        if category_rows:
            print()
            self._table(["CATEGORY", "MODEL", "BACKEND", "EVIDENCE"], category_rows)
        notes = payload.get("notes") or []
        if notes:
            self._bullets("Evidence boundary", notes[:3])
        automatic = payload.get("automatic_pull") or {}
        if automatic:
            selected = automatic.get("selected_repo_id") or "no viable candidate"
            if automatic.get("dry_run"):
                if automatic.get("selected_repo_id"):
                    self.success(f"Dry run selected {selected}; no files were downloaded.")
                    print(self._dim("Run the same command without --dry-run to download the winner."))
                else:
                    self.warning("Automatic discovery did not produce a viable model; nothing was downloaded.")
            elif automatic.get("downloaded"):
                pulled = payload.get("pull_best") or {}
                self.success(f"RIFT selected and downloaded {selected}.")
                self._key_values(
                    [
                        ("Repository", str(selected)),
                        ("Artifact", str(automatic.get("selected_file") or "selected snapshot")),
                        ("Destination", str(pulled.get("local_dir") or pulled.get("output_dir") or "RIFT model cache")),
                    ]
                )
        run_id = str(payload.get("recommendation_run_id") or "").strip()
        if run_id:
            print()
            print(self._dim(f"Recommendation run: {run_id}"))
            print(self._dim(f"Next: rift plan --recommendation-run {run_id}"))

    @staticmethod
    def _evidence_label(item: JsonDict) -> str:
        quality = item.get("quality_evidence") or {}
        if quality.get("local_records", 0):
            return "MEASURED_LOCAL"
        if quality.get("published_records", 0):
            return "PUBLISHED"
        if item.get("support_level") == "UNSUPPORTED":
            return "BLOCKED"
        return "ESTIMATED"

    def _render_plan(self, payload: JsonDict, *, title: str | None = None) -> None:
        self._heading(title or "Deployment plan")
        actions = payload.get("actions") or []
        rows = []
        for index, action in enumerate(actions, 1):
            rows.append(
                [
                    index,
                    self._action(action.get("kind") or "action"),
                    action.get("service") or "-",
                    action.get("summary") or action.get("reason") or "",
                    action.get("permission") or "none",
                ]
            )
        self._table(["#", "ACTION", "SERVICE", "DETAIL", "REQUIRES"], rows)
        if payload.get("plan_path"):
            print(self._dim(f"Plan file: {payload['plan_path']}"))
        if any(action.get("kind") == "error" for action in actions):
            self.warning("The plan contains blockers and cannot be applied safely.")
        else:
            self.success("Plan is read-only. Review it before running `rift apply`.")

    def _render_plans(self, payload: JsonDict, *, title: str | None = None) -> None:
        self._heading(title or "Saved deployment plans")
        plans = payload.get("plans") or []
        rows = []
        for index, item in enumerate(plans, 1):
            created = item.get("created_unix_seconds")
            try:
                created_label = time.strftime("%Y-%m-%d %H:%M", time.localtime(float(created)))
            except (TypeError, ValueError, OverflowError, OSError):
                created_label = "unknown"
            rows.append(
                [
                    index,
                    item.get("plan_id") or "unknown",
                    self._short_model(item.get("model")),
                    item.get("backend") or "-",
                    item.get("service_count") or 0,
                    item.get("blocker_count") or 0,
                    self._state(item.get("status") or "unknown"),
                    created_label,
                ]
            )
        self._table(
            ["#", "PLAN", "MODEL", "BACKEND", "SERVICES", "BLOCKERS", "STATUS", "CREATED"],
            rows,
        )
        if not plans:
            print(self._dim("No saved plans. Run `rift plan` to create one."))
        else:
            print(self._dim("Use `rift apply --plan N` to select a plan without prompting."))
        if payload.get("root"):
            print(self._dim(f"Plan directory: {payload['root']}"))

    def _render_plan_clear(self, payload: JsonDict, *, title: str | None = None) -> None:
        self._heading(title or "Saved plans cleared")
        removed = payload.get("removed") or []
        skipped = payload.get("skipped") or []
        self.success(f"Removed {payload.get('removed_count', len(removed))} generated plan artifact(s).")
        if payload.get("plan_directory"):
            print(self._dim(f"Plan directory: {payload['plan_directory']}"))
        if removed:
            rows = [[item.get("source", "-"), item.get("path", "-")] for item in removed]
            self._table(["SOURCE", "REMOVED"], rows)
        if skipped:
            print()
            self._bullets("Preserved unrecognized files", skipped)
            print(self._dim("Models, services, runtime state, logs, and backend installations were not changed."))

    def _render_plan_candidates(self, payload: JsonDict, *, title: str | None = None) -> None:
        self._heading(title or "Choose a model to plan")
        rows = []
        candidates = payload.get("candidates") or []
        for index, item in enumerate(candidates, 1):
            rows.append(
                [
                    index,
                    item.get("repo_id") or item.get("name") or item.get("path") or "unknown",
                    item.get("task") or payload.get("task") or "chat",
                    item.get("format") or "unknown",
                    item.get("quantization") or "-",
                    item.get("backend") or "none",
                    self._bytes(item.get("size_bytes") or item.get("size")),
                    f"{float(item.get('score') or item.get('final_score') or 0.0):.2f}",
                    "FIT" if item.get("fits", True) else "BLOCKED",
                    item.get("evidence") or "ESTIMATED",
                ]
            )
        self._table(
            ["#", "MODEL", "TASK", "FORMAT", "QUANT", "BACKEND", "SIZE", "SCORE", "FIT", "EVIDENCE"],
            rows,
        )
        for index, item in enumerate(candidates, 1):
            reasons = [str(reason) for reason in item.get("reasons") or [] if str(reason).strip()]
            if reasons:
                print(self._dim(f"{index}. " + " | ".join(reasons[:3])))
        if candidates:
            print()
            print(self._dim("Choose a number, path, repository ID, or artifact ID with --select to skip prompting."))

    def _render_apply(self, payload: JsonDict, *, title: str | None = None) -> None:
        self._heading(title or "Apply result")
        if payload.get("applied"):
            self.success("Desired state was applied.")
        else:
            self.warning(str(payload.get("reason") or "No changes were applied."))
        blocked = payload.get("blocked_actions") or []
        if blocked:
            self._table(
                ["ACTION", "SERVICE", "PERMISSION"],
                [[item.get("kind"), item.get("service"), item.get("permission")] for item in blocked],
            )
        self._render_result(
            {key: value for key, value in payload.items() if key not in {"blocked_actions", "plan"}},
            title=None,
        )

    def _render_status(self, payload: JsonDict, *, title: str | None = None) -> None:
        self._heading(title or "RIFT services")
        services = payload.get("services") or {}
        rows = []
        for name, service in services.items():
            runtime = service.get("runtime") or {}
            observation = service.get("observation") or {}
            model = service.get("model") or {}
            rows.append(
                [
                    name,
                    service.get("backend") or runtime.get("backend") or "unknown",
                    self._short_model(model.get("id") or model.get("selected_file")),
                    runtime.get("pid") or "-",
                    self._state(observation.get("phase") or service.get("status") or "unknown"),
                    runtime.get("openai_base") or runtime.get("api_base") or "-",
                ]
            )
        self._table(["SERVICE", "BACKEND", "MODEL", "PID", "STATE", "ENDPOINT"], rows)
        summary = payload.get("summary") or {}
        if summary:
            self._key_values([(self._label(key), self._format(value)) for key, value in summary.items()])

    def _render_backends(self, payload: JsonDict, *, title: str | None = None) -> None:
        self._heading(title or "Backend providers")
        providers = payload.get("providers", payload)
        rows = []
        for name, details in providers.items() if isinstance(providers, dict) else []:
            detection = details.get("detection", details) if isinstance(details, dict) else {}
            gate = details.get("lifecycle_gate", {}) if isinstance(details, dict) else {}
            capabilities = gate.get("capabilities") or {}
            rows.append(
                [
                    name,
                    self._state("available" if detection.get("available") else "not detected"),
                    detection.get("version") or "-",
                    self._state(
                        gate.get("advertised_status")
                        or capabilities.get("status")
                        or "unknown"
                    ),
                    ", ".join(capabilities.get("formats") or []) or "-",
                ]
            )
        self._table(["BACKEND", "DETECTED", "VERSION", "SUPPORT", "FORMATS"], rows)

    def _render_hardware(self, payload: JsonDict, *, title: str | None = None) -> None:
        self._heading(title or "Local hardware")
        identity = payload.get("identity") or {}
        capacity = payload.get("capacity") or {}
        pressure = payload.get("pressure") or {}
        managed = payload.get("rift_managed_occupancy") or {}
        self._key_values(
            [
                ("Host", identity.get("hostname") or "unknown"),
                ("OS", f"{identity.get('os', 'unknown')} {identity.get('os_release', '')}".strip()),
                ("CPU", identity.get("cpu_model") or "unknown"),
                ("Logical CPUs", identity.get("logical_cpu_count") or 0),
                ("GPU", identity.get("gpu") or payload.get("device_name") or "none"),
                ("VRAM", self._bytes(capacity.get("vram_bytes"))),
                ("Host RAM", self._bytes(capacity.get("host_ram_bytes"))),
                ("Disk free", self._bytes(pressure.get("disk_free_bytes"))),
                ("RIFT services", managed.get("running_service_count") or 0),
            ]
        )
        calibration = payload.get("calibration") or {}
        print(
            self._dim(
                "Calibration: "
                + ("stale" if calibration.get("stale") else "fresh")
                + (" (available)" if calibration.get("available") else " (not run)")
            )
        )

    def _render_benchmark(self, payload: JsonDict, *, title: str | None = None) -> None:
        self._heading(title or "Benchmark result")
        summary = payload.get("summary") or payload.get("metrics") or payload
        preferred = [
            "median_tokens_per_second",
            "p95_latency_seconds",
            "tokens_per_second",
            "prompt_tokens_per_second",
            "decode_tokens_per_second",
            "elapsed_seconds",
            "usability_verdict",
            "backend",
            "model",
        ]
        values = [(self._label(key), self._format(summary.get(key))) for key in preferred if summary.get(key) is not None]
        if values:
            self._key_values(values)
        else:
            self._render_result(payload, title=None)
        if payload.get("report_path"):
            print(self._dim(f"Report: {payload['report_path']}"))

    def _heading(self, text: str) -> None:
        print()
        print(self._paint(f"// {text.upper()}", "38;5;51;1"))
        print(self._paint("-" * min(max(len(text) + 3, 16), 72), "38;5;27"))

    def _key_values(self, rows: Sequence[tuple[str, Any]]) -> None:
        if not rows:
            return
        width = min(24, max(len(str(key)) for key, _ in rows))
        for key, value in rows:
            print(f"{self._paint(str(key).ljust(width), '38;5;75')}  {value}")

    def _bullets(self, title: str, items: Iterable[Any]) -> None:
        print(self._paint(f"{title}:", "38;5;39;1"))
        for item in items:
            print(f"  {self._paint('>', '38;5;51;1')} {item}")

    def _table(self, headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
        if not rows:
            print(self._dim("No entries."))
            return
        terminal = shutil.get_terminal_size((120, 24)).columns
        values = [[self._format(cell) for cell in row] for row in rows]
        widths = []
        for index, header in enumerate(headers):
            width = max(len(str(header)), *(len(_ANSI.sub("", row[index])) for row in values))
            widths.append(min(width, 42))
        total = sum(widths) + 3 * (len(widths) - 1)
        if total > terminal:
            overflow = total - terminal
            for index in sorted(range(len(widths)), key=lambda item: widths[item], reverse=True):
                reducible = max(0, widths[index] - 10)
                reduction = min(reducible, overflow)
                widths[index] -= reduction
                overflow -= reduction
                if overflow <= 0:
                    break
        print(
            "  ".join(
                self._paint(str(header).ljust(widths[index]), "38;5;75;1")
                for index, header in enumerate(headers)
            )
        )
        for row in values:
            print("  ".join(self._cell(cell, widths[index]) for index, cell in enumerate(row)))

    def _paint(self, value: str, code: str) -> str:
        return f"\x1b[{code}m{value}\x1b[0m" if self.color else value

    def _dim(self, value: str) -> str:
        return self._paint(value, "38;5;67")

    def _state(self, value: Any) -> str:
        text = str(value or "unknown")
        key = text.lower().replace("_", " ")
        if any(
            marker in key
            for marker in ("ready", "healthy", "running", "available", "complete", "verified", "passed")
        ) and not any(marker in key for marker in ("unavailable", "not ", "pending")):
            return self._paint(text, "38;5;84;1")
        if any(
            marker in key
            for marker in ("fail", "error", "crash", "unhealthy", "blocked", "rejected")
        ):
            return self._paint(text, "38;5;203;1")
        if any(
            marker in key
            for marker in ("pending", "warning", "stale", "missing", "not detected", "degraded", "unknown")
        ):
            return self._paint(text, "38;5;220")
        return self._paint(text, "38;5;45")

    def _action(self, value: Any) -> str:
        text = str(value or "action")
        key = text.lower()
        if key in {"error", "destroy", "stop", "delete"}:
            return self._paint(text, "38;5;203;1")
        if key in {"launch", "apply", "create", "download", "install"}:
            return self._paint(text, "38;5;51;1")
        return self._paint(text, "38;5;75")

    @staticmethod
    def _label(value: str) -> str:
        return value.replace("_", " ").strip().capitalize()

    @staticmethod
    def _format(value: Any) -> str:
        if value is None:
            return "-"
        if isinstance(value, bool):
            return "yes" if value else "no"
        if isinstance(value, float):
            return f"{value:.3f}".rstrip("0").rstrip(".")
        return str(value)

    @staticmethod
    def _bytes(value: Any) -> str:
        try:
            count = int(value or 0)
        except (TypeError, ValueError):
            return "unknown"
        if count <= 0:
            return "none"
        for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
            if count < 1024 or unit == "TiB":
                return f"{count:.2f} {unit}" if isinstance(count, float) else f"{count} {unit}"
            count = count / 1024
        return str(value)

    @staticmethod
    def _short_model(value: Any) -> str:
        text = str(value or "unknown").replace("\\", "/")
        return text.rstrip("/").split("/")[-1]

    @staticmethod
    def _cell(value: str, width: int) -> str:
        plain = _ANSI.sub("", value)
        if len(plain) > width:
            plain = plain[: max(1, width - 3)] + "..."
            return plain
        return value + " " * (width - len(plain))


__all__ = ["RiftConsole"]
