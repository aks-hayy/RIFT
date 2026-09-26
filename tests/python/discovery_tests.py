import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))

from rift.discovery import assess_metadata_capabilities, model_family_matches, normalize_workload
from rift.rift import RiftEngine
from rift.adapters.registry import BackendAdapterHost
from rift.workload_compiler import compile_workload


def test_normalized_profile_preserves_compiled_workload_constraints():
    contract = compile_workload(
        {
            "task": "rag",
            "objective": "speed",
            "performance": {
                "context_tokens": 32768,
                "concurrency": 4,
                "min_decode_tps": 24,
                "max_ttft_ms": 1200,
                "ttft_percentile": 95,
            },
            "quality": {
                "suite_id": "suite",
                "suite_version": "1",
                "minimum_score": 0.8,
                "required_cases": [],
            },
            "capabilities": {"tool_calling": True, "structured_output": False},
            "policies": {
                "network": "approved_sources",
                "backend": "vllm",
                "model_family": "qwen",
            },
        },
        confirm_default_quality=True,
    )["contract"]

    profile = normalize_workload(workload_contract=contract)

    assert profile.task == "rag"
    assert profile.objective == "speed"
    assert profile.context_length == 32768
    assert profile.concurrency == 4
    assert profile.minimum_decode_tokens_per_second == 24
    assert profile.maximum_ttft_seconds == 1.2
    assert profile.minimum_quality == 0.8
    assert profile.tool_calling is True
    assert profile.backend_preference == "vllm"
    assert profile.model_family_preference == "qwen"


def test_legacy_task_normalization_maps_document_and_retrieval_intents():
    assert normalize_workload(task="documents").task == "documents"
    assert normalize_workload(task="retrieval").task == "rag"
    assert normalize_workload(task="vision-language").task == "vision-language"


def test_documents_and_rag_search_text_generation_without_family_allowlist():
    engine = RiftEngine()
    for task in ("documents", "rag"):
        arms = engine._recommendation_query_arms(
            task, {"gguf"}, include_format_arms=True, include_family_arms=True
        )
        assert all(arm.get("pipeline_tag") == "text-generation" for arm in arms)
        assert all("qwen" not in arm.get("name", "") for arm in arms)


def test_model_family_preference_adds_only_a_discovery_hint():
    engine = RiftEngine()
    arms = engine._recommendation_query_arms(
        "chat", {"gguf"}, include_family_arms=True, family_preference="Mamba-2"
    )
    family_arms = [arm for arm in arms if arm["name"].startswith("family_")]
    assert len(family_arms) == 1
    assert family_arms[0]["search"] == "Mamba-2"


def test_capability_metadata_distinguishes_unknown_from_unsupported():
    assert assess_metadata_capabilities(
        repo_id="org/general-instruct", tags=[], tool_calling=True, structured_output=True
    ) == {"tool_calling": "unknown", "structured_output": "unknown"}
    assert assess_metadata_capabilities(
        repo_id="org/no-tool-model", tags=[], tool_calling=True, structured_output=False
    )["tool_calling"] == "unsupported"


def test_document_and_rag_requests_are_text_generation_backend_workloads():
    assert BackendAdapterHost._task_supported(("chat",), "documents")
    assert BackendAdapterHost._task_supported(("completion",), "rag")


def test_family_preference_matches_punctuated_local_model_names():
    assert model_family_matches("Qwen 7B", "Qwen2.5-7B-Instruct-Q4_K_M.gguf")
    assert not model_family_matches("Mamba-2", "Qwen2.5-7B-Instruct.gguf")
