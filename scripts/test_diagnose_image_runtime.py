"""Runtime integration test for diagnose_image function_tool.

Run with the ComfyUI venv python so the full import graph (dotenv, openai-agents,
backend.agent_factory, backend.utils.smb_path) matches the ComfyUI process exactly:

    D:\\share\\ComfyUI\\.venv\\Scripts\\python.exe scripts\\test_diagnose_image_runtime.py

This does NOT test the mcp_client pseudo-call bridge layer (that is covered by
AST checks and the existing bridge pattern for search_workflows). It tests the
tool itself end-to-end against the real Mac /diagnose endpoint.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

from backend.agent_factory import diagnose_image  # noqa: E402
from agents.tool_context import ToolContext  # noqa: E402
from agents.usage import Usage  # noqa: E402


async def invoke(image_path: str, question: str = "") -> str:
    payload = json.dumps({"image_path": image_path, "question": question}, ensure_ascii=False)
    ctx = ToolContext(
        context=None,
        usage=Usage(),
        tool_name="diagnose_image",
        tool_call_id="test-diagnose-image",
        tool_arguments=payload,
    )
    return await diagnose_image.on_invoke_tool(ctx, payload)


async def main() -> int:
    results: list[tuple[str, str, bool]] = []

    # Case 1: small image (<2MB) — expect [mode=base64]
    small = r"D:\share\copilot-cache\warmup.png"
    assert os.path.getsize(small) < 2_097_152, "warmup.png must be <2MB for this test"
    print(f"\n=== CASE 1: small image {small} ({os.path.getsize(small)} B) ===")
    out1 = await invoke(small, "any problem?")
    print(out1)
    results.append(("small -> [mode=base64]", out1, "[mode=base64]" in out1 and "status=success" in out1))

    # Case 2: large image (>2MB) — expect [mode=image_path]
    big = r"D:\share\copilot-cache\big_test.png"
    assert os.path.getsize(big) >= 2_097_152, "big_test.png must be >=2MB for this test"
    print(f"\n=== CASE 2: big image {big} ({os.path.getsize(big)} B) ===")
    out2 = await invoke(big, "what do you see?")
    print(out2)
    results.append(("big -> [mode=image_path]", out2, "[mode=image_path]" in out2 and "status=success" in out2))

    # Case 3: path outside SMB_WIN_ROOT — expect clear error, NO silent fallback
    outside = r"C:\Users\Woodenriver\nonexistent_outside_root.png"
    # We don't even need the file to exist, the smb_path check must fire first for big images.
    # But diagnose_image checks file existence first for small ones. Use a real file outside the root.
    # Pick any file >2MB outside the root to hit the path-branch rejection.
    # Simpler: use a path that doesn't exist — expect "파일이 존재하지 않음".
    print(f"\n=== CASE 3: missing path {outside} ===")
    out3 = await invoke(outside)
    print(out3)
    results.append(("missing path -> clear error", out3, "파일이 존재하지 않음" in out3))

    # Case 3b: real file outside SMB_WIN_ROOT, >2MB, to hit the path-branch rejection
    outside_big = Path(os.environ.get("TEMP", r"C:\Users\Woodenriver\AppData\Local\Temp")) / "w6_outside_big.png"
    if not outside_big.exists() or outside_big.stat().st_size < 2_097_152:
        # Create a >2MB placeholder PNG-ish blob (just bytes, diagnose_image stats size before reading)
        import shutil
        shutil.copyfile(big, outside_big)
    print(f"\n=== CASE 3b: outside-root big file {outside_big} ({outside_big.stat().st_size} B) ===")
    out4 = await invoke(str(outside_big))
    print(out4)
    results.append(
        (
            "outside-root big -> SMB_WIN_ROOT rejection",
            out4,
            "SMB_WIN_ROOT" in out4 and "silent base64 fallback" in out4,
        )
    )

    # Case 4: simulate Mac mount down — override SMB_MAC_ROOT to a bogus
    # path so Mac receives a path it cannot read. Must hit the image_path
    # branch first (file >2MB) then fall back to base64 with a reason.
    prev_mac_root = os.environ.get("SMB_MAC_ROOT")
    os.environ["SMB_MAC_ROOT"] = "/Volumes/share-does-not-exist"
    print(f"\n=== CASE 4: simulated mount-down via SMB_MAC_ROOT override ===")
    try:
        out5 = await invoke(big, "verify fallback")
    finally:
        if prev_mac_root is None:
            os.environ.pop("SMB_MAC_ROOT", None)
        else:
            os.environ["SMB_MAC_ROOT"] = prev_mac_root
    print(out5)
    results.append(
        (
            "mount-down -> [mode=base64 fallback_from=image_path ...]",
            out5,
            "[mode=base64 fallback_from=image_path" in out5
            and "hint:" in out5
            and "mount_smbfs" in out5
            and "status=success" in out5,
        )
    )

    print("\n=== SUMMARY ===")
    all_ok = True
    for label, _, ok in results:
        marker = "OK  " if ok else "FAIL"
        print(f"  {marker}  {label}")
        if not ok:
            all_ok = False
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
