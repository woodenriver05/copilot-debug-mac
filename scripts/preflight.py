"""
Copilot preflight: fail-fast validation before ComfyUI launches.

Run standalone before starting ComfyUI. Exits 0 if every check passes,
exits 1 with a clear reason otherwise. Designed to be wired into
autostart_comfyui.bat so a misconfigured machine never silently runs a
broken chat path.

Checks:
  1. All [REQUIRED] environment variables from .env.example are set.
  2. Mac RAG /health is reachable and returns 200.
  3. Mac RAG /agent rejects missing key with 403 (auth plumbing works).
  4. Mac LLM /v1/models is reachable (OpenAI-compatible endpoint alive).
  5. Mac MCP /mcp endpoint emits the initial SSE "endpoint" event
      (streamable-http server responding).
  6. External MCP policy (optional): if enabled, dedicated key must be set.

Each check prints its own line so a failure is immediately obvious in
comfyui-runtime.log. On failure, exit code is 1 and no downstream steps
run.

Usage (from autostart_comfyui.bat):
    python scripts\\preflight.py || exit /b 1
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    print("[preflight] FATAL: python-dotenv not installed in this venv", flush=True)
    sys.exit(1)


REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"

REQUIRED_VARS = [
    "CC_OPENAI_API_KEY",
    "CC_OPENAI_BASE_URL",
    "WORKFLOW_LLM_API_KEY",
    "WORKFLOW_LLM_BASE_URL",
    "WORKFLOW_LLM_MODEL",
    "RAG_API_URL",
    "RAG_API_KEY",
    "COPILOT_MCP_URL",
]

DEFAULT_BING_MCP_URL = "https://mcp.api-inference.modelscope.net/8c9fe550938e4f/sse"


def _log(tag: str, msg: str) -> None:
    print(f"[preflight] {tag} {msg}", flush=True)


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _http_get(url: str, timeout: float = 5.0) -> tuple[int, bytes]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()


def _http_post_json(url: str, body: dict, headers: dict, timeout: float = 5.0) -> tuple[int, bytes]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def check_env() -> list[str]:
    missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
    if missing:
        _log("FAIL", f"missing env vars: {', '.join(missing)}")
        _log("HINT", f"fill them in {ENV_PATH} (see .env.example)")
    else:
        _log("OK  ", f"all {len(REQUIRED_VARS)} required env vars present")
    return missing


def check_rag_health(base: str) -> bool:
    url = base.rstrip("/") + "/health"
    t0 = time.perf_counter()
    try:
        status, _body = _http_get(url, timeout=3.0)
    except Exception as e:
        _log("FAIL", f"RAG /health unreachable: {type(e).__name__}: {e}")
        return False
    dt = (time.perf_counter() - t0) * 1000
    if status != 200:
        _log("FAIL", f"RAG /health returned HTTP {status}")
        return False
    _log("OK  ", f"RAG /health 200 in {dt:.0f}ms")
    return True


def check_rag_auth(base: str) -> bool:
    """Confirm auth plumbing: a request with no X-API-Key must be rejected fast."""
    url = base.rstrip("/") + "/agent"
    t0 = time.perf_counter()
    try:
        status, _body = _http_post_json(
            url, {"query": "preflight"}, {"Content-Type": "application/json"}, timeout=5.0
        )
    except Exception as e:
        _log("FAIL", f"RAG /agent auth probe errored: {type(e).__name__}: {e}")
        return False
    dt = (time.perf_counter() - t0) * 1000
    if status == 403:
        _log("OK  ", f"RAG /agent rejects unauthenticated in {dt:.0f}ms (expected 403)")
        return True
    _log("FAIL", f"RAG /agent returned HTTP {status} (expected 403). Auth plumbing broken — aborting launch.")
    return False


def check_llm(base: str) -> bool:
    url = base.rstrip("/") + "/models"
    t0 = time.perf_counter()
    try:
        status, _body = _http_get(url, timeout=5.0)
    except Exception as e:
        _log("FAIL", f"LLM /v1/models unreachable: {type(e).__name__}: {e}")
        return False
    dt = (time.perf_counter() - t0) * 1000
    if status != 200:
        _log("FAIL", f"LLM /v1/models returned HTTP {status}")
        return False
    _log("OK  ", f"LLM /v1/models 200 in {dt:.0f}ms")
    return True


def check_mcp(url: str, label: str = "MCP") -> bool:
    """Read just the first SSE line to confirm the MCP transport is up."""
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            first = resp.readline()
    except Exception as e:
        _log("FAIL", f"{label} {url} unreachable: {type(e).__name__}: {e}")
        return False
    dt = (time.perf_counter() - t0) * 1000
    if not first.startswith(b"event:"):
        _log("FAIL", f"{label} first line unexpected: {first!r}")
        return False
    _log("OK  ", f"{label} initial event received in {dt:.0f}ms")
    return True


def check_smb_cache() -> bool:
    """Confirm SMB_WIN_ROOT is writable and copilot-cache/ exists.

    diagnose_image stages images under <SMB_WIN_ROOT>/copilot-cache and hands
    the Mac-side equivalent path to RAG. If this directory is not writable,
    large-image diagnose calls will silently degrade to base64 — we'd rather
    fail fast.
    """
    win_root = os.environ.get("SMB_WIN_ROOT")
    mac_root = os.environ.get("SMB_MAC_ROOT")
    if not win_root or not mac_root:
        _log("FAIL", "SMB_WIN_ROOT / SMB_MAC_ROOT not set (required for diagnose_image)")
        return False

    cache = Path(win_root) / "copilot-cache"
    try:
        cache.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        _log("FAIL", f"cannot create {cache}: {type(e).__name__}: {e}")
        return False

    probe = cache / ".preflight_write_probe"
    try:
        probe.write_bytes(b"ok")
        if probe.read_bytes() != b"ok":
            _log("FAIL", f"SMB cache write probe roundtrip mismatch at {probe}")
            return False
        probe.unlink()
    except Exception as e:
        _log("FAIL", f"SMB cache write probe failed at {probe}: {type(e).__name__}: {e}")
        return False

    raw = os.environ.get("IMAGE_PATH_MIN_BYTES", "2097152")
    try:
        threshold = int(raw)
        if threshold < 0:
            raise ValueError("negative")
    except ValueError:
        _log("FAIL", f"IMAGE_PATH_MIN_BYTES not a non-negative integer: {raw!r}")
        return False

    _log("OK  ", f"SMB cache writable ({cache}); threshold={threshold} bytes; mac_root={mac_root}")
    return True


def check_external_mcp_policy() -> bool:
    enabled = _env_flag("BING_MCP_ENABLED", False)
    require_explicit = _env_flag("BING_MCP_REQUIRE_EXPLICIT_WEB_SEARCH", True)
    if not enabled:
        _log("INFO", "External MCP disabled (BING_MCP_ENABLED=false)")
        return True

    _log("INFO", f"External MCP enabled (require_explicit_web_search={require_explicit})")
    api_key = (os.environ.get("BING_MCP_API_KEY") or "").strip()
    if not api_key:
        _log("FAIL", "BING_MCP_ENABLED=true but BING_MCP_API_KEY is missing")
        return False
    _log("OK  ", "BING_MCP_API_KEY is present")

    url = (os.environ.get("BING_MCP_URL") or DEFAULT_BING_MCP_URL).strip()
    if not check_mcp(url, label="External MCP"):
        _log("WARN", "External MCP endpoint unreachable (optional service). Continuing.")
    return True


def main() -> int:
    print("=" * 72, flush=True)
    print("[preflight] ComfyUI-Copilot preflight starting", flush=True)
    print("=" * 72, flush=True)

    if ENV_PATH.exists():
        load_dotenv(ENV_PATH)
        _log("OK  ", f"loaded env from {ENV_PATH}")
    else:
        _log("FAIL", f"missing .env at {ENV_PATH}")
        return 1

    missing = check_env()
    if missing:
        return 1

    skip_rag = _env_flag("PREFLIGHT_SKIP_RAG", False)
    if skip_rag:
        _log("WARN", "PREFLIGHT_SKIP_RAG=1 — RAG /health + /agent checks bypassed. Copilot chat will fail until RAG is back.")
        rag_results = [True, True]
    else:
        rag_results = [
            check_rag_health(os.environ["RAG_API_URL"]),
            check_rag_auth(os.environ["RAG_API_URL"]),
        ]

    skip_llm = _env_flag("PREFLIGHT_SKIP_LLM", False)
    if skip_llm:
        _log("WARN", "PREFLIGHT_SKIP_LLM=1 — LLM check bypassed. Copilot chat needs a working LLM to function.")
        llm_result = True
    else:
        llm_result = check_llm(os.environ["CC_OPENAI_BASE_URL"])

    skip_mcp = _env_flag("PREFLIGHT_SKIP_MCP", False)
    if skip_mcp:
        _log("WARN", "PREFLIGHT_SKIP_MCP=1 — MCP check bypassed. Copilot workflow tools unavailable until MCP is back.")
        mcp_result = True
    else:
        mcp_result = check_mcp(os.environ["COPILOT_MCP_URL"], label="Copilot MCP")

    results = rag_results + [
        llm_result,
        mcp_result,
        check_smb_cache(),
        check_external_mcp_policy(),
    ]

    if all(results):
        print("[preflight] ALL CHECKS PASSED", flush=True)
        return 0
    print("[preflight] ONE OR MORE CHECKS FAILED — ComfyUI launch aborted", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
