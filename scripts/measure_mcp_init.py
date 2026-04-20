"""
W1 실측 도구: Mac Copilot MCP 세션 초기화 시간을 구간별로 측정.

기존 코드가 8초로 wrap하는 `enter_async_context(server)` 내부에서
무슨 일이 일어나는지 보기 위한 것:
  - SSE endpoint event 수신
  - initialize RPC 왕복
  - tools/list RPC 왕복

여러 번 돌려 분산 확인.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from urllib import request as urlreq

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parent.parent
load_dotenv(REPO / ".env")

MCP_URL = os.environ.get("COPILOT_MCP_URL")
if not MCP_URL:
    print("COPILOT_MCP_URL is not set in env", flush=True)
    sys.exit(2)


def _http_read_first_line() -> tuple[float, bytes]:
    t0 = time.perf_counter()
    req = urlreq.Request(MCP_URL, method="GET")
    with urlreq.urlopen(req, timeout=10) as resp:
        first = resp.readline()
    return time.perf_counter() - t0, first


async def _timed_session() -> dict:
    from agents.mcp import MCPServerSse

    timings: dict = {}
    t_total = time.perf_counter()

    server = MCPServerSse(
        params={
            "url": MCP_URL,
            "timeout": 300.0,
            "headers": {},
        },
        cache_tools_list=False,
        client_session_timeout_seconds=300.0,
    )

    t_enter = time.perf_counter()
    try:
        await server.connect()
    except AttributeError:
        # Older API: use context manager semantics
        await server.__aenter__()
    timings["enter_ms"] = (time.perf_counter() - t_enter) * 1000

    t_tools = time.perf_counter()
    try:
        tools = await server.list_tools()
        timings["list_tools_ms"] = (time.perf_counter() - t_tools) * 1000
        timings["tool_count"] = len(tools)
    except Exception as e:
        timings["list_tools_ms"] = (time.perf_counter() - t_tools) * 1000
        timings["tool_count"] = f"error: {type(e).__name__}: {e}"

    try:
        await server.cleanup()
    except Exception:
        try:
            await server.__aexit__(None, None, None)
        except Exception:
            pass

    timings["total_ms"] = (time.perf_counter() - t_total) * 1000
    return timings


async def amain() -> int:
    print(f"[mcp-measure] target = {MCP_URL}", flush=True)
    print("[mcp-measure] stage 1: raw SSE first-line read (no SDK)", flush=True)
    for i in range(3):
        try:
            dt, first = _http_read_first_line()
            print(f"  run {i+1}: first line in {dt*1000:.1f}ms | {first[:80]!r}", flush=True)
        except Exception as e:
            print(f"  run {i+1}: FAIL {type(e).__name__}: {e}", flush=True)

    print("[mcp-measure] stage 2: MCPServerSse.connect + list_tools", flush=True)
    for i in range(3):
        try:
            timings = await _timed_session()
            print(
                f"  run {i+1}: connect={timings['enter_ms']:.0f}ms  "
                f"list_tools={timings['list_tools_ms']:.0f}ms  "
                f"total={timings['total_ms']:.0f}ms  tools={timings['tool_count']}",
                flush=True,
            )
        except Exception as e:
            print(f"  run {i+1}: FAIL {type(e).__name__}: {e}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
