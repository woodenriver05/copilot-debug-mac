"""Regression: create_agent must preserve caller-supplied tools.

Background
----------
Commit 99b665f3 (2026-04-20, "debug/mac: checkpoint 20260420 — Studio-side
Copilot overrides") introduced a silent overwrite where the body of
``create_agent()`` did:

    kwargs["tools"] = [search_workflows, diagnose_image]

This unconditionally replaced any caller-supplied ``tools=[...]`` argument with
just the two factory defaults. Five callers were affected:

- ``backend/service/mcp_client.py`` (Copilot main agent — passes
  ``get_current_workflow``, etc.)
- ``backend/debug_agent.py`` x4 (lines 223 / 263 / 313 / 405)
- ``backend/workflow_rewrite_agent.py``

Symptom
-------
LLM agents were being instructed (via system prompt) that tools like
``get_current_workflow`` existed, called them by name, and the underlying
``agents`` SDK raised:

    agents.exceptions.ModelBehaviorError:
        Tool get_current_workflow not found in agent ComfyUI-Copilot

After 4 SDK retries, the LLM had no data and would hallucinate (e.g. fabricate
"5 nodes to download" from nothing).

Live verification (2026-05-06)
------------------------------
Post-fix log shows
``Associating output with tool 'get_current_workflow'`` (previously
``Tool not found in agent``). User-triggered red-umbrella generation produced a
full SDXL t2i workflow with 4-axis Score4 evaluation, no hallucination.

Test design
-----------
``create_agent`` builds a real ``Agent`` and OpenAI client. To keep these
tests hermetic, we monkey-patch the SDK imports at module scope so that
``Agent(...)`` simply returns a sentinel object that captures the kwargs it
was constructed with. We assert on those captured kwargs.

If the underlying ``agents`` SDK is not installed in the test environment,
the ``backend.agent_factory`` import itself will fail; in that case pytest
will skip these tests with a clear reason rather than silently passing.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


# Make repo root importable as a package root so ``backend.agent_factory``
# resolves regardless of how pytest is invoked.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


@pytest.fixture
def agent_factory(monkeypatch):
    """Import ``backend.agent_factory`` with the heavy SDK calls neutralised.

    ``create_agent`` constructs an ``AsyncOpenAI`` client, an
    ``OpenAIChatCompletionsModel`` and an ``Agent``; for unit-level regression
    coverage we only care about what ends up in ``kwargs["tools"]`` when
    ``Agent`` is finally invoked.
    """
    try:
        af = importlib.import_module("backend.agent_factory")
    except Exception as exc:  # pragma: no cover - depends on env
        pytest.skip(f"backend.agent_factory import failed in this env: {exc!r}")

    captured: dict = {}

    class _FakeAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.__dict__.update(kwargs)

    class _FakeModel:
        def __init__(self, *a, **kw):
            self.args = a
            self.kwargs = kw

    class _FakeAsyncOpenAI:
        def __init__(self, *a, **kw):
            self.args = a
            self.kwargs = kw

    monkeypatch.setattr(af, "Agent", _FakeAgent, raising=True)
    monkeypatch.setattr(af, "OpenAIChatCompletionsModel", _FakeModel, raising=True)
    monkeypatch.setattr(af, "AsyncOpenAI", _FakeAsyncOpenAI, raising=True)
    # Avoid hitting external get_comfyui_copilot_api_key path, just in case.
    if hasattr(af, "get_comfyui_copilot_api_key"):
        monkeypatch.setattr(af, "get_comfyui_copilot_api_key", lambda: "test-key")

    return af, captured


def _name_of(tool) -> str:
    """Best-effort name extraction for both function_tool wrappers and plain callables."""
    return getattr(tool, "name", None) or getattr(tool, "__name__", repr(tool))


def _make_dummy_tool(af, tool_name: str):
    """Build a function_tool-compatible callable that mirrors ``af.search_workflows``."""

    @af.function_tool
    def _t(query: str = "") -> str:  # signature kept simple but non-empty
        return f"dummy_{tool_name}"

    # function_tool returns a FunctionTool-like object; ensure ``name`` attr is set.
    try:
        _t.name = tool_name
    except Exception:
        pass
    return _t


def test_caller_tools_are_preserved(agent_factory):
    """The 99b665f3 regression: caller-supplied tools must NOT be silently dropped."""
    af, captured = agent_factory
    custom = _make_dummy_tool(af, "get_current_workflow")

    af.create_agent(name="test", tools=[custom])

    tool_names = [_name_of(t) for t in captured.get("tools", [])]
    assert "get_current_workflow" in tool_names, (
        f"Caller-supplied tool was dropped. Got: {tool_names}. "
        "This is the 99b665f3 regression returning."
    )


def test_factory_defaults_still_present(agent_factory):
    """Even with no caller tools, the two factory defaults must be added."""
    af, captured = agent_factory
    af.create_agent(name="test", tools=[])

    tool_names = [_name_of(t) for t in captured.get("tools", [])]
    assert "search_workflows" in tool_names, tool_names
    assert "diagnose_image" in tool_names, tool_names


def test_merge_with_dedup_no_double_add(agent_factory):
    """Passing a default tool explicitly must not produce duplicates."""
    af, captured = agent_factory

    af.create_agent(name="test", tools=[af.search_workflows])

    tool_names = [_name_of(t) for t in captured.get("tools", [])]
    assert tool_names.count("search_workflows") == 1, tool_names
    # diagnose_image should still be added by the factory.
    assert "diagnose_image" in tool_names, tool_names


def test_caller_tools_take_precedence_in_order(agent_factory):
    """Caller tools must come first so the LLM sees them with priority."""
    af, captured = agent_factory
    custom = _make_dummy_tool(af, "custom_first")

    af.create_agent(name="test", tools=[custom])

    tool_names = [_name_of(t) for t in captured.get("tools", [])]
    assert tool_names, "No tools captured"
    assert tool_names[0] == "custom_first", (
        f"Expected caller tool 'custom_first' first, got order: {tool_names}"
    )
