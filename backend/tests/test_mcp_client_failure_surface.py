import json
import sys
import types
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _module(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


def _noop(*args, **kwargs):
    return None


class _Dummy:
    def __init__(self, *args, **kwargs):
        pass


class _Logger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


workflow_tools = _module(
    "backend.service.workflow_rewrite_tools",
    get_current_workflow=_noop,
    update_workflow=_noop,
    search_node_local=_noop,
    get_node_infos=_noop,
    remove_node=_noop,
)
workflow_rewrite_agent = _module(
    "backend.service.workflow_rewrite_agent",
    get_rewrite_expert_by_name=_noop,
    create_workflow_rewrite_agent=_noop,
)
agents_root = _module(
    "agents",
    Agent=_Dummy,
    handoff=_noop,
    RunContextWrapper=_Dummy,
    HandoffInputData=_Dummy,
    Runner=_Dummy,
    set_trace_processors=_noop,
    set_tracing_disabled=_noop,
    set_default_openai_api=_noop,
)

sys.modules.update(
    {
        "backend.service.workflow_rewrite_tools": workflow_tools,
        "backend.utils.globals": _module(
            "backend.utils.globals",
            BACKEND_BASE_URL="http://127.0.0.1:7002",
            get_comfyui_copilot_api_key=lambda: None,
            DISABLE_WORKFLOW_GEN=False,
        ),
        "backend.agent_factory": _module(
            "backend.agent_factory",
            create_agent=_noop,
            diagnose_image=_noop,
            search_workflows=_noop,
        ),
        "backend.service.workflow_rewrite_agent": workflow_rewrite_agent,
        "backend.service.message_memory": _module(
            "backend.service.message_memory",
            message_memory_optimize=lambda session_id, messages: messages,
        ),
        "backend.utils.request_context": _module(
            "backend.utils.request_context",
            get_rewrite_context=lambda: types.SimpleNamespace(rewrite_intent=None),
            get_session_id=lambda: "test-session",
            get_config=lambda: {},
        ),
        "backend.utils.logger": _module("backend.utils.logger", log=_Logger()),
        "agents": agents_root,
        "agents._config": _module("agents._config", set_default_openai_api=_noop),
        "agents.agent": _module("agents.agent", Agent=_Dummy),
        "agents.items": _module("agents.items", ItemHelpers=_Dummy),
        "agents.mcp": _module("agents.mcp", MCPServerSse=_Dummy),
        "agents.run": _module("agents.run", Runner=_Dummy),
        "agents.tracing": _module("agents.tracing", set_tracing_disabled=_noop),
        "agents.extensions": _module("agents.extensions", handoff_filters=_Dummy),
        "agents.tool_context": _module("agents.tool_context", ToolContext=_Dummy),
        "agents.usage": _module("agents.usage", Usage=_Dummy),
        "openai": _module("openai", APIError=Exception, RateLimitError=Exception),
        "openai.types": _module("openai.types"),
        "openai.types.responses": _module(
            "openai.types.responses",
            ResponseTextDeltaEvent=_Dummy,
        ),
    }
)

from backend.service import mcp_client


FAILURE_SURFACE_FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "failure_surface_cases.json"
)


def _failure_surface_cases():
    with FAILURE_SURFACE_FIXTURE_PATH.open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)["cases"]


def _minimal_api_workflow():
    return {
        "1": {
            "inputs": {},
            "class_type": "CheckpointLoaderSimple",
        }
    }


def _redacted_workflow_summary():
    return {
        "summary_type": "redacted_workflow_summary",
        "workflow_shape": "unknown_object",
        "node_count": 0,
        "class_types": [],
        "class_type_count": 0,
    }


def _failed_run_data():
    return {
        "selected_workflow": {"nodes": []},
        "workflow_id": "workflow:50904456-e1a8-41a4-97a6-e267d305acf2",
        "execution_status": "failed",
        "failed_stage": "planner",
        "failure_reason": "invalid_choice_retry_suppressed",
        "dispatch_attempted": False,
        "dispatch_status": None,
        "prompt_id": None,
        "image_paths": [],
        "prediction_id": 60,
    }


def _successful_run_data(selected_workflow=None):
    return {
        "selected_workflow": selected_workflow or {
            "nodes": [
                {
                    "id": 1,
                    "type": "SaveImage",
                    "inputs": {"filename_prefix": "red-bicycle"},
                }
            ]
        },
        "workflow_id": "workflow:ok",
        "selected_template_id": "workflow:template-ok",
        "execution_status": "success",
        "trace_id": "trace-ok",
        "prompt_id": "prompt-123",
        "image_paths": ["output/red-bicycle.png"],
        "prediction_id": 61,
        "vision_analysis": {
            "overall_score": 0.839,
            "vision_prompt_source": "user_query",
        },
    }


def test_failed_run_pipeline_is_not_promoted_to_workflow_update():
    ext = mcp_client._build_run_pipeline_ext({"data": _failed_run_data()})

    assert ext
    assert [item["type"] for item in ext] == ["run_pipeline_failure"]
    assert ext[0]["data"]["run_id"] == 60
    assert ext[0]["data"]["run_id_label"] == "failed run evidence"
    assert ext[0]["data"]["prompt_id"] is None
    assert ext[0]["data"]["image_paths"] == []


def test_failed_run_pipeline_summary_suppresses_recovery_hallucinations():
    summary = mcp_client._canonical_run_pipeline_failure_answer(_failed_run_data())

    assert "invalid_choice_retry_suppressed" in summary
    assert "run_id: `60` (failed run evidence" in summary
    assert "apply_patch" not in summary
    assert "transfer_to_workflow_rewrite_agent" not in summary
    assert "generate_sketch.py" not in summary
    assert "rate_image" not in summary


def test_failed_run_pipeline_surface_promotes_typed_failure_when_top_level_missing():
    data = {
        "execution_status": "failed",
        "typed_failure": {
            "stage": "search",
            "typed_reason": "no_execution_ready_workflow",
            "failure_reason": "no_execution_ready_workflow",
        },
        "dispatch_attempted": False,
        "dispatch_status": "not_attempted",
        "prompt_id": None,
        "image_paths": [],
        "run_id": 148,
    }

    surface = mcp_client._run_pipeline_failure_surface_data(data)
    summary = mcp_client._canonical_run_pipeline_failure_answer(data)

    assert surface["failed_stage"] == "search"
    assert surface["failure_reason"] == "no_execution_ready_workflow"
    assert "failed_stage: `search`" in summary
    assert "failure_reason: `no_execution_ready_workflow`" in summary
    assert "unknown" not in summary


def test_failed_run_pipeline_surface_uses_runtime_path_when_failure_reason_missing():
    data = {
        "execution_status": "skipped",
        "runtime_path_type": "no_execution_ready_fail_closed",
        "closure_eligible": False,
        "closure_blocker_reason": "no_execution_ready_workflow",
        "runtime_path_evidence": {
            "retrieval_fail_reason": "no_execution_ready_workflow",
        },
        "dispatch_attempted": False,
        "dispatch_status": "not_applicable",
        "prompt_id": None,
        "image_paths": [],
    }

    surface = mcp_client._run_pipeline_failure_surface_data(data)
    summary = mcp_client._canonical_run_pipeline_failure_answer(data)

    assert surface["failed_stage"] == "search"
    assert surface["failure_reason"] == "no_execution_ready_workflow"
    assert "runtime_path_type: `no_execution_ready_fail_closed`" in summary
    assert "closure_blocker_reason: `no_execution_ready_workflow`" in summary
    assert "unknown" not in summary


def test_failed_run_pipeline_surface_uses_top_level_retrieval_fail_reason():
    data = {
        "execution_status": "skipped",
        "retrieval_fail_reason": "no_execution_ready_workflow",
        "dispatch_attempted": False,
        "dispatch_status": "not_applicable",
        "prompt_id": None,
        "image_paths": [],
        "run_id": "run-skipped",
    }

    surface = mcp_client._run_pipeline_failure_surface_data(data)
    summary = mcp_client._canonical_run_pipeline_failure_answer(data)

    assert surface["failed_stage"] == "search"
    assert surface["failure_reason"] == "no_execution_ready_workflow"
    assert surface["retrieval_fail_reason"] == "no_execution_ready_workflow"
    assert "failed_stage: `search`" in summary
    assert "failure_reason: `no_execution_ready_workflow`" in summary
    assert "retrieval_fail_reason: `no_execution_ready_workflow`" in summary
    assert "unknown" not in summary


def test_failed_run_pipeline_shared_fixture_matrix():
    for case in _failure_surface_cases():
        data = case["data"]
        expected = case["expected"]

        surface = mcp_client._run_pipeline_failure_surface_data(data)
        summary = mcp_client._canonical_run_pipeline_failure_answer(data)

        assert surface["failed_stage"] == expected["failed_stage"], case["name"]
        assert surface["failure_reason"] == expected["failure_reason"], case["name"]
        assert surface["retrieval_fail_reason"] == expected["retrieval_fail_reason"], case["name"]
        assert f"failed_stage: `{expected['failed_stage']}`" in summary, case["name"]
        assert f"failure_reason: `{expected['failure_reason']}`" in summary, case["name"]
        if expected["retrieval_fail_reason"] is not None:
            assert (
                f"retrieval_fail_reason: `{expected['retrieval_fail_reason']}`" in summary
            ), case["name"]
        if expected.get("detects_direct_data"):
            assert mcp_client._run_pipeline_has_typed_failure(data) is True, case["name"]
        if expected.get("builds_failure_ext"):
            ext = mcp_client._build_run_pipeline_ext({"data": data})
            assert ext is not None, case["name"]
            assert ext[0]["type"] == "run_pipeline_failure", case["name"]
        if expected.get("no_unknown"):
            assert "unknown" not in summary, case["name"]


def test_successful_run_pipeline_keeps_workflow_update_surface():
    ext = mcp_client._build_run_pipeline_ext(
        {"data": _successful_run_data()}
    )

    assert ext
    assert [item["type"] for item in ext] == ["workflow_update"]
    assert ext[0]["data"]["prompt_id"] == "prompt-123"
    assert ext[0]["data"]["image_paths"] == ["output/red-bicycle.png"]
    assert ext[0]["data"]["workflow_data_source"] == "selected_workflow"
    assert ext[0]["data"]["has_generated_image"] is True


def test_successful_run_pipeline_recovers_workflow_from_history():
    original = mcp_client._workflow_from_comfyui_history
    history_workflow = _minimal_api_workflow()
    try:
        mcp_client._workflow_from_comfyui_history = lambda prompt_id: history_workflow
        ext = mcp_client._build_run_pipeline_ext(
            {"data": _successful_run_data(_redacted_workflow_summary())}
        )
    finally:
        mcp_client._workflow_from_comfyui_history = original

    assert ext
    assert [item["type"] for item in ext] == ["workflow_update"]
    assert ext[0]["data"]["workflow_data"] == history_workflow
    assert ext[0]["data"]["workflow_data_source"] == "comfyui_history_prompt"


def test_successful_run_pipeline_skips_unrenderable_workflow_update():
    original = mcp_client._workflow_from_comfyui_history
    try:
        mcp_client._workflow_from_comfyui_history = lambda prompt_id: None
        ext = mcp_client._build_run_pipeline_ext(
            {"data": _successful_run_data(_redacted_workflow_summary())}
        )
    finally:
        mcp_client._workflow_from_comfyui_history = original

    assert ext is None


def test_successful_run_pipeline_summary_is_evidence_only():
    summary = mcp_client._canonical_run_pipeline_success_answer(_successful_run_data())

    assert "Image Generation Complete" in summary
    assert "trace_id: `trace-ok`" in summary
    assert "run_id: `61`" in summary
    assert "prompt_id: `prompt-123`" in summary
    assert "image_paths: `1`" in summary
    assert "output/red-bicycle.png" in summary
    assert "vision_overall_score: `0.839`" in summary
    assert "vision_prompt_source: `user_query`" in summary
    assert "8K" not in summary
    assert "FPS" not in summary
    assert "camera" not in summary.lower()
    assert "rate_image" not in summary
    assert "apply_patch" not in summary


def test_successful_run_pipeline_replaces_existing_freeform_text():
    text = mcp_client._ground_run_pipeline_final_text(
        "Workflow Updated Successfully\n\nA cinematic 8K video was generated.",
        {"data": _successful_run_data(), "answer": "Pipeline complete"},
    )

    assert "Image Generation Complete" in text
    assert "trace_id: `trace-ok`" in text
    assert "8K" not in text
    assert "video" not in text.lower()
    assert "Workflow Updated Successfully" not in text


def test_failed_run_pipeline_ext_suppresses_later_workflow_updates():
    run_pipeline_ext = [{"type": "run_pipeline_failure", "data": {"run_id": 60}}]
    workflow_update_ext = [
        {"type": "workflow_update", "data": {"version_id": 99}},
        {"type": "workflow_rewrite_complete", "data": {"version_id": 99}},
    ]

    ext = mcp_client._merge_final_workflow_ext(
        run_pipeline_ext,
        workflow_update_ext,
        suppress_workflow_update_ext=True,
    )

    assert ext == run_pipeline_ext


def test_successful_run_pipeline_ext_keeps_workflow_updates():
    run_pipeline_ext = [{"type": "workflow_update", "data": {"prompt_id": "ok"}}]

    ext = mcp_client._merge_final_workflow_ext(
        run_pipeline_ext,
        run_pipeline_ext,
        suppress_workflow_update_ext=False,
    )

    assert ext == run_pipeline_ext


if __name__ == "__main__":
    tests = sorted(
        (name, value)
        for name, value in globals().items()
        if name.startswith("test_") and callable(value)
    )
    for _, test in tests:
        test()
    print(f"{len(tests)} mcp_client failure surface tests passed")
