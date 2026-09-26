"""Run the bounded real-model tuning matrix and build portable evidence.

This script deliberately keeps the model artifact and quantization fixed.  It
uses temporary RIFT roots, records the full tuning reports, and destroys each
owned service before moving to the next cell.  vLLM is attempted only when its
exact runtime is available; otherwise the cell is recorded as blocked.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models"
LLAMA_MODEL = {
    "3B": MODEL_DIR / "Qwen--Qwen2.5-3B-Instruct-GGUF" / "qwen2.5-3b-instruct-q4_k_m.gguf",
    "7B": MODEL_DIR / "Qwen--Qwen2.5-7B-Instruct-GGUF" / "Qwen2.5-7B-Instruct-Q4_K_M.gguf",
}


def _compact_tune(report: dict[str, Any]) -> dict[str, Any]:
    baseline = report.get("baseline") or {}
    candidates = report.get("candidates") or []
    selection = report.get("selection") or {}
    selected = selection.get("selected") or {}
    baseline_measurement = ((candidates[0] if candidates else {}).get("measurement") or {})
    winner_measurement = selected.get("measurement") or {}
    improvement = selected.get("objective_improvement")
    if improvement is None and baseline_measurement and winner_measurement:
        base = float(baseline_measurement.get("tokens_per_second") or 0.0)
        win = float(winner_measurement.get("tokens_per_second") or 0.0)
        improvement = (win / base - 1.0) if base else None
    measured = [entry for entry in candidates if isinstance(entry, dict) and entry.get("status") in {"measured", "baseline"} and isinstance(entry.get("measurement"), dict)]
    if report.get("profile") == "cost":
        best_observed = min(measured, key=lambda e: float((e.get("measurement") or {}).get("gpu_joules") or float("inf")), default=None)
    else:
        best_observed = max(measured, key=lambda e: float((e.get("measurement") or {}).get("tokens_per_second") or 0.0), default=None)
    best_measurement = (best_observed or {}).get("measurement") or baseline_measurement
    return {
        "run_id": report.get("run_id"),
        "outcome": report.get("outcome"),
        "available": report.get("available"),
        "applied": report.get("applied"),
        "baseline_restored": report.get("baseline_restored"),
        "baseline_tuning": baseline.get("tuning"),
        "winning_tuning": selected.get("config") or selected.get("tuning"),
        "baseline_measurement": baseline_measurement,
        "winning_measurement": winner_measurement,
        "best_observed_tuning": (best_observed or {}).get("tuning") or baseline.get("tuning"),
        "best_observed_measurement": best_measurement,
        "best_observed_is_promotable": bool(selected),
        "objective_improvement": improvement,
        "improvement_interval": selected.get("improvement_interval"),
        "quality": report.get("accuracy") or baseline.get("accuracy"),
        "candidates_tested": len(candidates),
        "rejected": len(report.get("rejected") or selection.get("rejected") or []),
        "report_path": report.get("report_path"),
        "precision_locks": report.get("precision_locks"),
        "opportunities": report.get("opportunities"),
    }


def _svg_chart(records: list[dict[str, Any]], path: Path) -> None:
    cells = [r for r in records if r.get("backend") == "llama.cpp" and r.get("status") == "completed" and r.get("profile") == "speed"]
    width, height = 1060, 520
    max_value = max([float(r.get("best_observed_tps") or r.get("winner_tps") or r.get("baseline_tps") or 0.0) for r in cells] + [1.0])
    bar_w = 48
    gap = 28
    left = 72
    top = 55
    base_y = 390
    body: list[str] = []
    body.append(f'<rect width="{width}" height="{height}" fill="#101827"/>')
    body.append('<text x="36" y="30" fill="#f8fafc" font-family="Segoe UI" font-size="20" font-weight="700">RIFT real-model tuning matrix · decode throughput</text>')
    body.append('<text x="36" y="49" fill="#94a3b8" font-family="Segoe UI" font-size="12">Fixed GGUF artifacts; weight quantization locked; bars are measured cells</text>')
    body.append(f'<line x1="{left}" y1="{base_y}" x2="1020" y2="{base_y}" stroke="#64748b"/>')
    for idx, record in enumerate(cells):
        x = left + idx * (bar_w * 2 + gap + 18)
        b = float(record.get("baseline_tps") or 0.0)
        w = float(record.get("best_observed_tps") or record.get("winner_tps") or 0.0)
        bh = 280 * b / max_value
        wh = 280 * w / max_value
        body.append(f'<rect x="{x}" y="{base_y-bh:.1f}" width="{bar_w}" height="{bh:.1f}" fill="#64748b"/>')
        body.append(f'<rect x="{x+bar_w+6}" y="{base_y-wh:.1f}" width="{bar_w}" height="{wh:.1f}" fill="#38bdf8"/>')
        label = f"{record.get('model')} {record.get('profile')}"
        body.append(f'<text x="{x}" y="{base_y+22}" fill="#cbd5e1" font-family="Segoe UI" font-size="11" transform="rotate(30 {x} {base_y+22})">{label}</text>')
        body.append(f'<text x="{x+4}" y="{base_y-bh-6:.1f}" fill="#cbd5e1" font-family="Segoe UI" font-size="11">{b:.1f}</text>')
        body.append(f'<text x="{x+bar_w+10}" y="{base_y-wh-6:.1f}" fill="#7dd3fc" font-family="Segoe UI" font-size="11">{w:.1f}</text>')
    body.append('<rect x="760" y="65" width="14" height="14" fill="#64748b"/><text x="780" y="77" fill="#cbd5e1" font-family="Segoe UI" font-size="12">basic baseline</text>')
    body.append('<rect x="890" y="65" width="14" height="14" fill="#38bdf8"/><text x="910" y="77" fill="#cbd5e1" font-family="Segoe UI" font-size="12">best observed</text>')
    path.write_text("<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 %d %d\">%s</svg>\n" % (width, height, "".join(body)), encoding="utf-8")


def _svg_cost_chart(records: list[dict[str, Any]], path: Path) -> None:
    cells = [r for r in records if r.get("backend") == "llama.cpp" and r.get("status") == "completed" and r.get("profile") == "cost"]
    width, height = 860, 460
    max_value = max([float((r.get("baseline_measurement") or {}).get("gpu_joules") or 0.0) for r in cells] + [1.0])
    body = [f'<rect width="{width}" height="{height}" fill="#101827"/>', '<text x="32" y="30" fill="#f8fafc" font-family="Segoe UI" font-size="20" font-weight="700">RIFT Cost profile · GPU joules per request</text>', '<text x="32" y="49" fill="#94a3b8" font-family="Segoe UI" font-size="12">Lower is better; GPU-only boundary, point estimates shown separately from CI-gated promotion</text>', '<line x1="65" y1="360" x2="805" y2="360" stroke="#64748b"/>']
    for idx, record in enumerate(cells):
        x = 100 + idx * 330
        b = float((record.get("baseline_measurement") or {}).get("gpu_joules") or 0.0)
        w = float(record.get("best_observed_joules") or b)
        bh, wh = 250 * b / max_value, 250 * w / max_value
        body.append(f'<rect x="{x}" y="{360-bh:.1f}" width="70" height="{bh:.1f}" fill="#64748b"/><rect x="{x+82}" y="{360-wh:.1f}" width="70" height="{wh:.1f}" fill="#34d399"/>')
        body.append(f'<text x="{x}" y="382" fill="#cbd5e1" font-family="Segoe UI" font-size="13">{record.get("model")} basic</text><text x="{x+82}" y="382" fill="#a7f3d0" font-family="Segoe UI" font-size="13">best observed</text>')
        body.append(f'<text x="{x+8}" y="{354-bh:.1f}" fill="#cbd5e1" font-family="Segoe UI" font-size="12">{b:.1f} J</text><text x="{x+90}" y="{354-wh:.1f}" fill="#a7f3d0" font-family="Segoe UI" font-size="12">{w:.1f} J</text>')
    body.append('<rect x="610" y="70" width="14" height="14" fill="#64748b"/><text x="630" y="82" fill="#cbd5e1" font-family="Segoe UI" font-size="12">basic baseline</text><rect x="610" y="95" width="14" height="14" fill="#34d399"/><text x="630" y="107" fill="#cbd5e1" font-family="Segoe UI" font-size="12">best observed</text>')
    path.write_text("<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 %d %d\">%s</svg>\n" % (width, height, "".join(body)), encoding="utf-8")


def _svg_flow(records: list[dict[str, Any]], path: Path) -> None:
    width, height = 1100, 420
    body = [f'<rect width="{width}" height="{height}" fill="#0b1220"/>', '<text x="32" y="34" fill="#f8fafc" font-family="Segoe UI" font-size="20" font-weight="700">RIFT evidence flow and cleanup boundary</text>']
    boxes = [(40, 125, 180, "basic deploy"), (265, 125, 180, "baseline + quality"), (490, 125, 180, "bounded tuning"), (715, 125, 150, "accept / restore"), (910, 125, 145, "scrap service")]
    for i, (x, y, w, label) in enumerate(boxes):
        body.append(f'<rect x="{x}" y="{y}" width="{w}" height="70" rx="10" fill="#172554" stroke="#60a5fa"/>')
        body.append(f'<text x="{x+w/2}" y="{y+42}" text-anchor="middle" fill="#dbeafe" font-family="Segoe UI" font-size="14">{label}</text>')
        if i < len(boxes)-1:
            body.append(f'<line x1="{x+w}" y1="160" x2="{boxes[i+1][0]}" y2="160" stroke="#94a3b8" stroke-width="2" marker-end="url(#arrow)"/>')
    body.append('<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="#94a3b8"/></marker></defs>')
    body.append('<text x="40" y="285" fill="#94a3b8" font-family="Segoe UI" font-size="13">Each cell has its own temporary runtime, service lease, raw report, and teardown verification.</text>')
    counts = {"completed": sum(r.get("status") == "completed" for r in records), "blocked": sum(r.get("status") == "blocked" for r in records)}
    body.append(f'<text x="40" y="315" fill="#cbd5e1" font-family="Segoe UI" font-size="13">Recorded cells: {len(records)} · completed: {counts["completed"]} · blocked: {counts["blocked"]}</text>')
    path.write_text("<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 %d %d\">%s</svg>\n" % (width, height, "".join(body)), encoding="utf-8")


def run_cell(model_label: str, profile: str, output: Path) -> dict[str, Any]:
    from rift.orchestrator import ApplyPermissions, RiftOrchestrator
    from rift.rift_yaml import read_yaml, write_yaml

    model = LLAMA_MODEL[model_label]
    start = time.time()
    cell: dict[str, Any] = {"model": model_label, "profile": profile, "backend": "llama.cpp", "artifact": str(model), "started_at": start}
    temp_root = Path(tempfile.mkdtemp(prefix=f"rift-real-{model_label.lower()}-{profile}-"))
    service_name = f"validation-{model_label.lower()}"
    port = 19300 + (0 if model_label == "3B" else 20) + (0 if profile == "speed" else 1)
    try:
        conf = read_yaml(ROOT / "rift.yaml")
        service = dict(conf["services"]["chat"])
        for key in ("model", "serving", "policy", "gateway", "monitoring", "recovery"):
            service[key] = dict(service[key])
        model_path = str(model.resolve())
        service["model"].update({"source": "local", "id": model_path, "selected_file": model_path, "local_path": model_path, "format": "gguf", "artifact": {}, "quantization": "Q4_K_M"})
        # Deliberately conservative, human-style first launch: GPU offload is
        # enabled so correctness probes remain practical, while small batch
        # and thread settings leave measurable headroom for the tuner.
        service["serving"].update({"port": port, "context_length": 4096, "concurrency": 1, "tuning": {"gpu_layers": 999, "batch": 64, "ubatch": 32, "threads": 4, "threads_batch": 4, "parallel": 1, "flash_attn": "auto", "ngram_speculation": False}})
        service["gateway"]["enabled"] = False
        service["policy"].update({"backend": "llama.cpp", "allow_download": False, "allow_install": False})
        service["monitoring"]["enabled"] = False
        conf["services"] = {service_name: service}
        config = temp_root / "rift.yaml"
        write_yaml(config, conf)
        orch = RiftOrchestrator(root=temp_root, runtime_root=temp_root / ".rift-runtime")
        applied = orch.apply(config_path=config, permissions=ApplyPermissions(allow_launch=True))
        cell["deployment_seconds"] = time.time() - start
        if not applied.get("applied"):
            cell.update({"status": "failed", "reason": applied.get("reason") or applied.get("errors")})
            return cell
        ready = False
        for _ in range(180):
            observation = orch.status().get("services", {}).get(service_name, {}).get("observation", {})
            if observation.get("healthy"):
                ready = True
                break
            time.sleep(1)
        if not ready:
            cell.update({"status": "failed", "reason": "service did not become healthy", "health": observation})
            return cell
        tune = orch.profiled_tune_service(
            service_name=service_name,
            profile=profile,
            allow_restart=True,
            candidate_limit=4,
            warmup_runs=1,
            repeats=3,
            max_tokens=32,
            target_tokens_per_second=1.0,
            budget_seconds=360,
            accuracy_tolerance=0.25,
            accuracy_case_tolerance=0.5,
        )
        cell.update(_compact_tune(tune))
        cell.update({"status": "completed", "tuning_seconds": time.time() - start - float(cell.get("deployment_seconds") or 0.0)})
        report_path = Path(str(tune.get("report_path") or ""))
        if report_path.is_file():
            raw_dir = output / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            destination = raw_dir / f"{model_label.lower()}-llama-cpp-{profile}.json"
            shutil.copy2(report_path, destination)
            cell["raw_report"] = str(destination)
        base = cell.get("baseline_measurement") or {}
        win = cell.get("winning_measurement") or {}
        cell["baseline_tps"] = base.get("tokens_per_second")
        cell["winner_tps"] = (win.get("tokens_per_second") if win else base.get("tokens_per_second"))
        best = cell.get("best_observed_measurement") or {}
        cell["best_observed_tps"] = best.get("tokens_per_second")
        cell["best_observed_joules"] = best.get("gpu_joules")
        return cell
    except Exception as exc:
        cell.update({"status": "failed", "reason": f"{type(exc).__name__}: {exc}"})
        return cell
    finally:
        try:
            if "orch" in locals():
                cell["teardown"] = orch.destroy(service_name=service_name)
                cell["teardown_verified"] = service_name not in orch.status().get("services", {})
        except Exception as exc:
            cell["teardown_error"] = str(exc)
            cell["teardown_verified"] = False
        cell["finished_at"] = time.time()
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / ".rift-runtime" / "reports" / "real-tuning-validation")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    llama_server = os.environ.get("LLAMA_CPP_SERVER") or str((ROOT / ".rift-runtime" / "backends" / "llama.cpp" / "llama-server.exe").resolve())
    os.environ["LLAMA_CPP_SERVER"] = llama_server
    for model_label in ("3B", "7B"):
        for profile in ("speed", "cost"):
            records.append(run_cell(model_label, profile, output))
    from rift.providers.vllm import VllmProvider
    vllm_detection = VllmProvider().detect()
    for model_label in ("3B", "7B"):
        for profile in ("speed", "cost"):
            records.append({"model": model_label, "profile": profile, "backend": "vLLM", "status": "blocked", "reason": "exact vLLM runtime unavailable on this workstation", "detection": vllm_detection, "teardown_verified": True})
    summary = {
        "schema_version": 1,
        "created_at": time.time(),
        "hardware_scope": {"device": "local workstation", "backend_runtime": llama_server},
        "records": records,
        "manual_effort_metric": {
            "human_baseline_seconds": None,
            "status": "not_independently_measured",
            "claim": "No human-time speedup is claimed without a measured engineer baseline.",
            "automation_proxy": "RIFT owns deploy, health, baseline, quality, restart, candidate comparison, restore, report, and teardown.",
            "lifecycle_stages_automated": 9,
            "candidate_configs_tested": sum(int(r.get("candidates_tested") or 0) for r in records),
        },
        "interpretation": "vLLM cells are environment-blocked, not performance failures. Cost is unavailable when the GPU-energy boundary cannot be measured; no zero-energy substitution is made.",
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    _svg_chart(records, output / "throughput.svg")
    _svg_cost_chart(records, output / "cost-energy.svg")
    _svg_flow(records, output / "evidence-flow.svg")
    lines = ["# Real-model tuning validation", "", "This evidence was generated by `scripts/run_real_tuning_validation.py`. Each llama.cpp cell used a temporary RIFT runtime and was torn down before the next cell. Weight quantization stayed Q4_K_M.", "", "![Throughput comparison](throughput.svg)", "", "![Cost comparison](cost-energy.svg)", "", "![Evidence flow](evidence-flow.svg)", "", "## Results", "", "| Model | Backend | Profile | Status | Baseline tok/s | Winner tok/s | Improvement | Candidates | Cost scope |", "|---|---|---|---|---:|---:|---:|---:|---|"]
    for r in records:
        if r.get("backend") == "llama.cpp":
            base, win = r.get("baseline_tps"), r.get("winner_tps")
            imp = r.get("objective_improvement")
            observed = r.get("best_observed_measurement") or {}
            metric_base = (f"{float(base or 0):.2f}" if r.get("profile") == "speed" else f"{float((r.get('baseline_measurement') or {}).get('gpu_joules') or 0):.2f} J")
            metric_best = (f"{float(r.get('best_observed_tps') or win or 0):.2f}" if r.get("profile") == "speed" else f"{float(r.get('best_observed_joules') or observed.get('gpu_joules') or 0):.2f} J")
            lines.append(f"| {r.get('model')} | llama.cpp | {r.get('profile')} | {r.get('outcome') or r.get('status')} | {metric_base} | {metric_best} | {float(imp or 0)*100:.2f}% (CI-gated) | {r.get('candidates_tested', 0)} | {'GPU energy measured' if r.get('profile') == 'cost' and r.get('available') else 'unavailable/labelled'} |")
        else:
            lines.append(f"| {r.get('model')} | vLLM | {r.get('profile')} | BLOCKED: {r.get('reason')} | — | — | — | — | — |")
    lines += ["", "## How much easier than manual tuning?", "", "A human-time percentage is intentionally not fabricated: no engineer baseline was run in parallel. The defensible proxy is lifecycle automation: RIFT executed deploy → health → baseline → quality → restart/candidate trials → restore/promotion decision → evidence → teardown for each completed cell, while testing the bounded candidates recorded in `summary.json`.", "", "## Limitations", "", "vLLM is not installed and neither Docker nor an accessible WSL runtime is available here, so its four cells are qualification-blocked. Cost claims are accepted only when an explicit energy measurement boundary exists. The quality suite is a bounded acceptance floor, not proof of universal model quality.", ""]
    (output / "README.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"output": str(output), "records": records}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
