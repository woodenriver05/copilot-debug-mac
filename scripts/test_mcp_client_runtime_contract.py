"""Static guard for the Copilot -> RAG runtime workflow contract.

Run with:
    python3 scripts/test_mcp_client_runtime_contract.py
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
MCP_CLIENT = REPO_ROOT / "backend" / "service" / "mcp_client.py"


def _contract_block(source: str) -> str:
    start = source.index("def _workflow_creation_contract")
    end = source.index("def _extract_json_object_slice", start)
    return source[start:end]


def check(label: str, condition: bool) -> bool:
    marker = "OK  " if condition else "FAIL"
    print(f"[test_mcp_client_runtime_contract] {marker} {label}")
    return condition


def main() -> int:
    source = MCP_CLIENT.read_text(encoding="utf-8")
    contract = _contract_block(source)

    results = [
        check(
            "run_pipeline is the named runtime tool",
            'RUNTIME_PIPELINE_TOOL = "run_pipeline"' in source,
        ),
        check(
            "run_pipeline appears in workflow result tools",
            "RUNTIME_PIPELINE_TOOL,\n    WORKFLOW_RECALL_TOOL" in source,
        ),
        check(
            "CASE 3 primary action is run_pipeline",
            "Primary Action: Use `{RUNTIME_PIPELINE_TOOL}`" in contract,
        ),
        check(
            "candidate-only path stays recall_workflow",
            "Candidate-only Action:" in contract
            and "use `{WORKFLOW_RECALL_TOOL}`" in contract,
        ),
        check(
            "legacy gen_workflow is explicitly forbidden as primary",
            "Do not call `{LEGACY_WORKFLOW_GEN_TOOL}` as the primary generation path"
            in contract,
        ),
        check(
            "old recall+gen hard requirement removed",
            "MUST ALWAYS call BOTH recall_workflow tool AND gen_workflow"
            not in source,
        ),
        check(
            "chat prompt uses runtime contract helper",
            "_workflow_creation_contract()" in source,
        ),
        check(
            "stream tracking includes runtime workflow tools",
            "if tool_name in WORKFLOW_RESULT_TOOLS:" in source,
        ),
        check(
            "run_pipeline result is finalized as workflow output",
            "if RUNTIME_PIPELINE_TOOL in tool_results:" in source
            and "finished = True" in source[source.index("if RUNTIME_PIPELINE_TOOL") :],
        ),
    ]

    passed = sum(results)
    print(f"[test_mcp_client_runtime_contract] {passed}/{len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
