"""Re-audit the 100 supplied NL workloads against RIFT's serving boundary.

This audit is capability-level, not a workstation benchmark.  RIFT verifies
the exact model/backend tool-call capability when required; it does not own a
business-tool broker, tool permissions, sandboxed harness, or side effects.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


AUTOSCALE_TERMS = ("auto-scale", "autoscale", "auto scale")
CLUSTER_TERMS = ("cluster", "load balancing across")
EDGE_TERMS = (
    "jetson", "automotive arm", "rugged tablet", "raspberry pi", "edge ipc",
    "space-grade", "satellite onboard", "subsea",
    "wearable medical device", "battery-powered", "handheld barcode", "drone navigation",
    "aircraft cockpit", "substation controller", "tractor autonomous steering",
    "off-grid solar",
)
GRAMMAR_TERMS = ("gbnf", "pydantic grammar", "custom grammar")
ACTUATION_TERMS = (
    "emergency stop", "can-bus actions", "flight path adjustment", "zigbee device control",
    "sonar control", "circuit breaker isolation", "inverter settings", "gps course correction",
    "sensor positioning",
)
SLO_PATTERNS = (
    r"\b\d+(?:\.\d+)?\s*(?:tok(?:en)?s?\s*(?:/|per)\s*s(?:ec(?:ond)?)?|tokens?\s+per\s+second)\b",
    r"\b\d+(?:\.\d+)?\s*(?:req(?:uests?)?\s*(?:/|per)\s*(?:s(?:ec(?:ond)?)?|min(?:ute)?|h(?:our)?)|requests?\s+per\s+(?:second|minute|hour))\b",
    r"\b(?:p\d{2}|under|below|less than|sub-?)\s*\d+(?:\.\d+)?\s*(?:ms|milliseconds?)\b",
    r"\b(?:first\s+answer|first\s+response|ttft).{0,35}\b(?:under|within|below|less than|sub-?)\s*\d+(?:\.\d+)?\s*(?:s|sec(?:ond)?s?|ms|milliseconds?)\b",
    r"\b\d+(?:\.\d+)?\s*(?:ms|milliseconds?)\s*(?:ttft|latency)\b",
    r"\b(?:sub-?)\s*\d+(?:\.\d+)?[- ]?(?:s|sec(?:ond)?s?|ms|milliseconds?)\s*(?:ttft|latency)?\b",
    r"\b(?:max(?:imum)?\s*)?(?:ttft|latency|first\s+(?:answer|response|token)).{0,30}\b\d+(?:\.\d+)?\s*(?:s|sec(?:ond)?s?|ms|milliseconds?)\b",
    r"\b\d+(?:\.\d+)?\s*%\s*(?:uptime|availability|target\s+sla|slo)?\b",
    r"\b(?:less than|under|below)\s*\d+(?:\.\d+)?\s*(?:w|watts?)\b",
    r"\b(?:max(?:imum)?\s+)?power\s+limit\s*[:=]?\s*\d+(?:\.\d+)?\s*(?:w|watts?)\b",
    r"\b(?:high reliability|high accuracy|high precision quality|99\.9+%\s*(?:target\s*)?(?:availability|uptime|sla))\b",
    r"\b\d+\s*(?:concurrent|parallel)\s+(?:users?|agents?|streams?|requests?|sessions?|workflows?|tenants?)\b",
)


def classify(text: str) -> tuple[str, str, str]:
    value = text.casefold()
    missing_autoscaling = any(term in value for term in AUTOSCALE_TERMS)
    notes: list[str] = []
    categories: list[str] = []
    if missing_autoscaling:
        notes.append("RIFT Mesh has manual replica control and routing primitives, but no automatic scale-out/scale-in controller driven by workload demand")
        categories.append("automatic_cluster_autoscaling")
    tool_required = bool(re.search(r"(?<!no )(?<!without )\b(?:tool calling|tool-calling|function calling)\b", value))
    if tool_required:
        notes.append(
            "RIFT verifies core tool-call emission for the exact model/backend/template/runtime; the user's harness executes real tools and owns permissions/side effects"
        )
        categories.append("tool_capability_verified_external_execution")
    if any(term in value for term in ACTUATION_TERMS):
        notes.append("physical actuation and safety interlocks remain the user's control-system responsibility; RIFT serves the model and verifies only the capabilities requested of that model/backend")
    if "sandbox" in value:
        notes.append("the requested application/code sandbox is an external harness responsibility and is not provided by this model-serving audit")
    if any(term in value for term in GRAMMAR_TERMS):
        notes.append("a grammar workload needs a compatible grammar artifact and backend-specific translation; llama.cpp has a native grammar path, while equivalent grammar behavior must be verified for other selected backends")
        categories.append("grammar_translation")
    if "structured output" in value or "strict json" in value or "json schema" in value or "ehr schema" in value or "fhir" in value:
        notes.append("RIFT can pass the approved schema into supported backends and validate responses against it; this verifies conformance, not the clinical/business correctness of the generated values")
        categories.append("structured_output")
    if any(re.search(pattern, value) for pattern in SLO_PATTERNS):
        notes.append("deployment settings can be selected, but the requested latency, throughput, power, or availability target needs matching end-to-end measurements; configuration alone is not proof")
        categories.append("slo_evidence")

    if any(term in value for term in EDGE_TERMS):
        notes.append("the exact edge CPU/GPU architecture and backend installation/runtime path need target-specific qualification")
        categories.append("edge_runtime_qualification")

    if any(term in value for term in CLUSTER_TERMS):
        notes.append("RIFT Mesh provides enrollment, capability-aware route selection, replica state, manual scaling, and reconciliation primitives; end-to-end deployment and load evidence for this topology still need qualification")
        categories.append("mesh_topology_qualification")

    if missing_autoscaling:
        return "GAP", "; ".join(notes), "+".join(categories)

    if categories and set(categories).issubset({"tool_capability_verified_external_execution", "structured_output"}):
        return (
            "PASS",
            "RIFT can deploy the serving endpoint, enforce the approved schema when present, and verify core tool-call emission for the exact model/backend/template/runtime; the user's harness executes real tools and owns permissions/side effects",
            "+".join(categories),
        )
    if notes:
        # These are serviceable through RIFT with an explicit evidence boundary;
        # they are not missing serving primitives.
        return "CONDITIONAL", "; ".join(notes), "+".join(categories)
    return "PASS", "ordinary model serving requirements map to the current deployment and backend contracts", "core_serving"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    lines = []
    for raw in args.input.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*(\d+)\.\s+\"(.*)\"\s*$", raw)
        if match:
            lines.append({"workload_id": int(match.group(1)), "request": match.group(2)})
    if len(lines) != 100:
        raise SystemExit(f"expected exactly 100 numbered workloads, found {len(lines)}")
    records: list[dict[str, Any]] = []
    for item in lines:
        status, reason, category = classify(item["request"])
        records.append({**item, "status": status, "reason": reason, "category": category})
    counts = Counter(item["status"] for item in records)
    categories = Counter(item["category"] for item in records)
    payload = {
        "schema_version": 3,
        "audit_id": "rift-workload-capability-audit-v3-serving-boundary-review",
        "source": "user-supplied 100-workload NL corpus (attachment)",
        "scope": "capability-level RIFT serving audit; compute availability is assumed",
        "boundary": {
            "rift_verifies": "exact model/backend/template/runtime core tool-call emission",
            "user_harness_owns": "business tool execution, broker permissions, application sandbox, side effects, ingestion, and output consumers",
            "edge_actuation": "physical action execution and safety interlocks belong to the user's application/control system; this audit evaluates only RIFT's model-serving and capability-verification responsibilities",
            "mesh_scope": "RIFT Mesh includes enrollment, capability-aware route selection, replica desired state, manual scale, and reconciliation primitives; full workload-specific topology qualification remains conditional",
            "supersedes_audit": "rift-workload-capability-audit-v2-tool-capability-boundary",
        },
        "method": [
            "Preserve all 100 supplied NL requests as provenance.",
            "Do not classify user-harness tool execution or physical actuation as a RIFT gap.",
            "Classify only explicit automatic cluster autoscaling as a missing RIFT serving-control capability; single-node multi-GPU and mesh requests are assessed against existing tensor-parallel and Mesh primitives.",
            "Treat tool calling as a capability gate with an exact synthetic probe, not a tool-execution feature.",
            "Assume requested schema artifacts are available as directed; retain backend grammar translation as a qualification item.",
        "Treat explicit quantitative latency, throughput, concurrency, power, and availability claims as conditional until the matching measured acceptance exists. Context length is a backend launch setting in this capability audit; resource sufficiency is assumed, with near-capacity completion left to deployment acceptance.",
            "Treat named edge architectures and mesh topologies as conditional where the exact runtime/deployment combination lacks target-specific qualification.",
        ],
        "summary": {"total": len(records), **dict(counts), "categories": dict(categories)},
        "workloads": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown = [
        "# RIFT 100-NL Workload Capability Re-audit (serving boundary review)",
        "",
        "> This is a capability audit, not a hardware benchmark. Compute, compatible artifacts, and required schema/evaluator inputs are assumed available.",
        "",
        "## Product boundary",
        "",
        "RIFT deploys the model-serving endpoint and verifies model/backend capabilities such as tool-call emission. The surrounding application owns ingestion, real tool execution, business permissions, output consumption, application sandboxing, physical actuation, and safety interlocks. RIFT Mesh has enrollment, capability-aware routing, replica desired-state, manual scaling, and reconciliation primitives. This audit treats only automatic workload-driven autoscaling as a missing RIFT capability. It assumes compute and requested schema artifacts are available.",
        "",
        "## Result",
        "",
        f"- Total workloads: **{len(records)}**",
        f"- PASS: **{counts['PASS']}**",
        f"- CONDITIONAL: **{counts['CONDITIONAL']}**",
        f"- GAP: **{counts['GAP']}**",
        "",
        "| Audit | PASS | CONDITIONAL | GAP |",
        "|---|---:|---:|---:|",
        "| Historical capability audit | 23 | 39 | 38 |",
        "| Previous tool-capability audit (overbroad safety/cluster tags) | 50 | 34 | 16 |",
        f"| Revised serving-boundary audit | {counts['PASS']} | {counts['CONDITIONAL']} | {counts['GAP']} |",
        "",
        "The prior report incorrectly treated physical-control wording as a RIFT-owned safety-controller requirement and treated tensor-parallel, mesh-routing, and multi-agent wording as proof of a missing cluster lifecycle. This pass removes those false GAPs. The remaining GAP is automatic workload-driven cluster autoscaling. Numerical targets and exact edge/mesh deployments are CONDITIONAL until evidence exists. Tool calling is evaluated at the model/backend capability boundary; application code executes the actual tools. The former 11-row safety/edge bucket was too coarse: these workloads differ in serving, tool-capability, hardware-qualification, and SLO needs, so they are not a blanket RIFT gap. Physical actuators, safety interlocks, and application-owned execution remain outside RIFT.",
        "",
        "## Recurring categories",
        "",
        "| Category | Count | Interpretation |",
        "|---|---:|---|",
    ]
    category_interpretations = {
        "core_serving": "ordinary serving maps directly to current contracts",
        "tool_capability_verified_external_execution": "RIFT verifies emission; external harness executes tools",
        "structured_output": "RIFT enforces/validates the supplied schema; application-level correctness remains separate",
        "grammar_translation": "raw grammar portability depends on backend translation",
        "slo_evidence": "the requested SLO needs matching load, latency, power, or soak evidence",
        "structured_output+slo_evidence": "structured-output artifact plus measured SLO evidence",
        "tool_capability_verified_external_execution+slo_evidence": "tool capability plus measured SLO evidence",
        "tool_capability_verified_external_execution+edge_runtime_qualification": "tool capability plus target edge runtime qualification",
        "tool_capability_verified_external_execution+slo_evidence+edge_runtime_qualification": "tool capability, measured SLO, and target edge runtime qualification",
        "tool_capability_verified_external_execution+mesh_topology_qualification": "tool capability plus mesh topology qualification",
        "tool_capability_verified_external_execution+slo_evidence+mesh_topology_qualification": "tool capability, measured SLO, and mesh topology qualification",
        "slo_evidence+edge_runtime_qualification": "measured SLO plus target edge runtime qualification",
        "structured_output+edge_runtime_qualification": "structured output plus target edge runtime qualification",
        "structured_output+slo_evidence+edge_runtime_qualification": "structured output, measured SLO, and target edge runtime qualification",
        "slo_evidence+mesh_topology_qualification": "measured SLO plus mesh topology qualification",
        "mesh_topology_qualification": "existing RIFT Mesh primitives need end-to-end topology qualification",
        "tool_capability_verified_external_execution+structured_output+edge_runtime_qualification": "tool capability, structured output, and target edge runtime qualification",
        "tool_capability_verified_external_execution+structured_output+slo_evidence+edge_runtime_qualification": "tool capability, structured output, measured SLO, and target edge runtime qualification",
        "tool_capability_verified_external_execution+structured_output+mesh_topology_qualification": "tool capability, structured output, and mesh topology qualification",
        "tool_capability_verified_external_execution+structured_output": "tool capability plus structured-output artifact",
        "tool_capability_verified_external_execution+structured_output+slo_evidence": "tool capability, schema, and measured SLO evidence",
        "grammar_translation+structured_output+slo_evidence": "backend-specific grammar translation, schema conformance, and measured SLO evidence",
        "grammar_translation+slo_evidence": "backend-specific grammar translation and measured SLO evidence",
        "automatic_cluster_autoscaling+mesh_topology_qualification+slo_evidence": "automatic demand-driven scaling is missing; existing Mesh routing/scaling primitives and availability/performance claims still need deployment evidence",
        "automatic_cluster_autoscaling+slo_evidence+mesh_topology_qualification": "automatic demand-driven scaling is missing; existing Mesh routing/scaling primitives and availability/performance claims still need deployment evidence",
        "structured_output+grammar_translation": "structured output plus backend-specific grammar translation",
        "structured_output+grammar_translation+slo_evidence": "schema/grammar plus measured SLO evidence",
    }
    for category, count in sorted(categories.items(), key=lambda pair: (-pair[1], pair[0])):
        markdown.append(f"| `{category}` | {count} | {category_interpretations.get(category, 'multiple reviewed conditions') } |")
    markdown.extend(["", "## Workload matrix", "", "| # | Status | Category | Request | RIFT finding |", "|---:|---|---|---|---|"])
    for item in records:
        request = item["request"].replace("|", "\\|")
        reason = item["reason"].replace("|", "\\|")
        markdown.append(f"| {item['workload_id']} | **{item['status']}** | `{item['category']}` | {request} | {reason} |")
    markdown.extend([
        "",
        "## Evidence boundary",
        "",
        "A PASS means the requested serving function is supported by RIFT's current interfaces under the stated assumptions. A CONDITIONAL result means RIFT has the serving primitive, but an artifact, exact runtime/topology, or quantitative acceptance measurement still needs verification. A GAP means an explicitly requested RIFT serving-control feature is absent. Context is considered configurable and compute sufficiency is assumed here; a real deployment must still verify near-capacity requests. User-owned ingestion, business tool execution, application sandboxes, physical actuation, and safety interlocks are outside the RIFT serving contract. The exact model/backend tool-call probe records deployment identity and synthetic case results and explicitly marks real tool execution as not evaluated.",
        "",
        "The JSON companion is the machine-readable source for this report and should be used for future diffs.",
        "",
    ])
    md_path = args.output.with_suffix(".md")
    md_path.write_text("\n".join(markdown), encoding="utf-8")
    print(json.dumps({"summary": payload["summary"], "json": str(args.output), "markdown": str(md_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
