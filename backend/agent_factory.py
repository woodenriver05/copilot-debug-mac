"""
Author: ai-business-hql qingli.hql@alibaba-inc.com
Date: 2025-07-31 19:38:08
LastEditors: ai-business-hql ai.bussiness.hql@gmail.com
LastEditTime: 2026-01-12 11:11:53
FilePath: /comfyui_copilot/backend/agent_factory.py
Description: 这是默认设置,请设置`customMade`, 打开koroFileHeader查看配置 进行设置: https://github.com/OBKoro1/koro1FileHeader/wiki/%E9%85%8D%E7%BD%AE
"""

try:
    from agents import (
        Agent,
        OpenAIChatCompletionsModel,
        ModelSettings,
        Runner,
        set_tracing_disabled,
        set_default_openai_api,
    )

    if not hasattr(__import__("agents"), "Agent"):
        raise ImportError
except Exception:
    # Give actionable guidance without crashing obscurely
    raise ImportError(
        "Detected incorrect or missing 'agents' package. "
        "Please uninstall legacy RL 'agents' (and tensorflow/gym if pulled transitively) and install openai-agents. "
        "Commands:\n"
        "  python -m pip uninstall -y agents gym tensorflow\n"
        "  python -m pip install -U openai-agents\n\n"
        "Alternatively, keep both by setting COMFYUI_COPILOT_PREFER_OPENAI_AGENTS=1 so this plugin prefers openai-agents."
    )
from dotenv import dotenv_values
from .utils.globals import (
    LLM_DEFAULT_BASE_URL,
    LMSTUDIO_DEFAULT_BASE_URL,
    get_comfyui_copilot_api_key,
    is_lmstudio_url,
    WORKFLOW_LLM_MODEL,
)
from openai import AsyncOpenAI
from agents.tool import (
    function_tool,
)  # Required: plain functions are rejected by ChatCompletions API tool converter


from agents._config import set_default_openai_api
from agents.tracing import set_tracing_disabled
import asyncio
# from .utils.logger import log

# def load_env_config():
#     """Load environment variables from .env.llm file"""
#     from dotenv import load_dotenv

#     env_file_path = os.path.join(os.path.dirname(__file__), '.env.llm')
#     if os.path.exists(env_file_path):
#         load_dotenv(env_file_path)
#         log.info(f"Loaded environment variables from {env_file_path}")
#     else:
#         log.warning(f"Warning: .env.llm not found at {env_file_path}")


# # Load environment configuration
# load_env_config()

set_default_openai_api("chat_completions")
set_tracing_disabled(False)


def _rag_env() -> tuple[str, str] | None:
    import os

    base = os.environ.get("RAG_API_URL")
    key = os.environ.get("RAG_API_KEY")
    if not base or not key:
        return None
    return base.rstrip("/"), key


@function_tool
def search_workflows(query: str) -> str:
    """Fast keyword/tag search over the ComfyUI workflow catalog (Korean supported).

    Prefer this tool for concrete lookups like:
      - "find an anime upscale workflow"
      - "video interpolation with controlnet"
      - "SDXL character consistency"
    Typical latency is ~100-300ms. Returns up to 5 matching workflows with
    name, description, tags, models, and workflow_id.

    Use search_rag_agent instead only when the user asks for multi-step
    planning, design suggestions, or when this tool returns zero results.
    """
    import urllib.request
    import json

    env = _rag_env()
    if env is None:
        return "검색 설정 누락: RAG_API_URL / RAG_API_KEY 가 환경에 없습니다."
    base, key = env

    url = f"{base}/search"
    body = json.dumps({"query": query, "limit": 5}).encode("utf-8")
    headers = {"Content-Type": "application/json", "X-API-Key": key}
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return f"워크플로우 검색 실패: {type(e).__name__}: {e}"

    results = data.get("results", [])
    if not results:
        return f"'{query}' 검색 결과 없음. 복잡한 요청이라면 search_rag_agent 를 시도하세요."

    latency = data.get("latency_ms")
    lines = [f"'{query}' 검색 결과 {len(results)}개 (latency {latency}ms):"]
    for i, r in enumerate(results, 1):
        name = r.get("name") or "(untitled)"
        desc = (r.get("description") or "").strip().replace("\n", " ")
        if len(desc) > 220:
            desc = desc[:220] + "…"
        tags = ", ".join((r.get("tags") or [])[:6])
        models = ", ".join((r.get("models") or [])[:4]) or "—"
        wid = r.get("id") or r.get("workflow_id") or "?"
        lines.append(f"{i}. {name}")
        if desc:
            lines.append(f"   설명: {desc}")
        if tags:
            lines.append(f"   태그: {tags}")
        lines.append(f"   models: {models}")
        lines.append(f"   workflow_id: {wid}")
    return "\n".join(lines)


@function_tool
def diagnose_image(image_path: str, question: str = "") -> str:
    """Diagnose a local image via the Mac RAG /diagnose endpoint.

    Pass a Windows absolute path; small images (<2MB by default) are sent
    as base64 inline, larger ones are handed to Mac as an SMB-mounted path
    reference so the HTTP body stays tiny. The returned text is prefixed
    with [mode=base64] or [mode=image_path] so the caller can see which
    transport was actually used.

    image_path must live under SMB_WIN_ROOT (D:\\share by default). Paths
    outside that root are rejected — this does NOT fall back to base64 for
    outside-root paths, because silently copying arbitrary files into the
    share is a worse failure mode than a clear error.

    question is optional free-form text describing what to look for.
    """
    import base64
    import json
    import os
    import urllib.request
    from pathlib import Path

    from .utils.smb_path import win_to_mac

    env = _rag_env()
    if env is None:
        return "diagnose_image 실패: RAG_API_URL / RAG_API_KEY 가 환경에 없습니다."
    base, key = env

    try:
        path = Path(image_path)
    except Exception as e:
        return f"diagnose_image 실패: 경로 파싱 오류 ({type(e).__name__}: {e})"
    if not path.is_file():
        return f"diagnose_image 실패: 파일이 존재하지 않음: {image_path}"
    try:
        size = path.stat().st_size
    except OSError as e:
        return f"diagnose_image 실패: stat 오류 ({e})"

    try:
        threshold = int(os.environ.get("IMAGE_PATH_MIN_BYTES", "2097152"))
    except ValueError:
        threshold = 2097152

    url = f"{base}/diagnose"
    headers = {"Content-Type": "application/json", "X-API-Key": key}

    def _post(body: dict, timeout: float) -> tuple[int, dict | str]:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw

    # Mac mount /Volumes/share has manual persistence — every reboot it needs a
    # fresh mount_smbfs. When it's down, the Mac side of a diagnose image_path
    # call will fail with a file-not-found style error. The tool retries as
    # base64 so the user still gets a diagnosis, but the [mode=...] prefix
    # MUST announce that a fallback happened and tell the user how to fix the
    # root cause — otherwise the mount can quietly stay down for weeks.
    remount_hint = (
        "Mac 쪽에서 아래 한 줄로 다시 mount 하세요: "
        "mkdir -p /Volumes/share && mount_smbfs //Woodenriver@192.168.10.100/share /Volumes/share"
    )

    def _format(
        mode: str, payload: dict | str, fallback_reason: str | None = None
    ) -> str:
        header = f"[mode={mode}]"
        if fallback_reason:
            header = (
                f'[mode={mode} fallback_from=image_path reason="{fallback_reason}"]'
            )
        if isinstance(payload, str):
            body = f"{header} {payload[:2000]}"
            if fallback_reason:
                body += f"\n  hint: {remount_hint}"
            return body
        status = payload.get("status", "?")
        issues = (
            payload.get("diagnosis_report", {}).get("image", {}).get("issues", [])
        ) or []
        lines = [f"{header} status={status}"]
        for i, issue in enumerate(issues, 1):
            desc = (issue.get("description") or "").strip()
            if desc:
                lines.append(f"  {i}. {desc}")
        if len(lines) == 1:
            lines.append("  (no image issues reported)")
        if fallback_reason:
            lines.append(f"  hint: {remount_hint}")
        return "\n".join(lines)

    fallback_reason: str | None = None

    prefer_path = size >= threshold
    if prefer_path:
        mac_path = win_to_mac(image_path)
        if mac_path is None:
            return (
                f"diagnose_image 실패: 경로가 SMB_WIN_ROOT 밖입니다 ({image_path}). "
                "큰 이미지는 D:\\share\\ 아래로 옮긴 뒤 다시 시도하세요. "
                "(silent base64 fallback은 의도적으로 비활성화되어 있습니다.)"
            )
        body = {"image_path": mac_path}
        if question:
            body["question"] = question
        try:
            _, payload = _post(body, timeout=120.0)
        except Exception as e:
            # Network/timeout error on the image_path branch. Treat as a
            # fallback-worthy condition (Mac mount down, RAG restart, flaky
            # link) rather than hard-failing — base64 still works for
            # small-ish images. Larger ones will just OOM the HTTP layer
            # and that's a more informative failure than an opaque timeout.
            fallback_reason = (
                f"POST to /diagnose raised {type(e).__name__}: {str(e)[:200]}"
            )
            payload = None

        # Load-failure detection. Empirically, when the Mac mount is down or
        # the SMB path is otherwise unreadable from the RAG process, Mac's
        # /diagnose still returns status=success but embeds the OS error into
        # the first vision issue's description. So we must scan:
        #   1) top-level `answer` field (older failure shape)
        #   2) `status == "error"` (explicit error envelope)
        #   3) `diagnosis_report.image.issues[].description` for load-failure
        #      markers ("이미지 로드 실패", "No such file", "cannot read",
        #      "file not found", "Errno 2", "Permission denied")
        # If the heuristic over-fires, the only cost is an extra base64 retry
        # that produces the same answer, so we bias toward false positives.
        looks_broken = False
        if fallback_reason is None and isinstance(payload, dict):
            ans = str(payload.get("answer") or "")
            if ans.startswith("Error") or "file not found" in ans.lower():
                looks_broken = True
                fallback_reason = f"Mac responded with error in answer: {ans[:200]}"
            if payload.get("status") == "error":
                looks_broken = True
                if not fallback_reason:
                    fallback_reason = "Mac responded with status=error"

            if not looks_broken:
                load_markers = (
                    "이미지 로드 실패",
                    "no such file",
                    "cannot read",
                    "file not found",
                    "errno 2",
                    "permission denied",
                )
                issues = (
                    payload.get("diagnosis_report", {})
                    .get("image", {})
                    .get("issues", [])
                ) or []
                for issue in issues:
                    desc = str(issue.get("description") or "").lower()
                    if any(m in desc for m in load_markers):
                        looks_broken = True
                        fallback_reason = (
                            f"Mac reported load failure in issue description: "
                            f"{str(issue.get('description') or '')[:200]}"
                        )
                        break
        if fallback_reason is None and not looks_broken:
            return _format("image_path", payload)
        # Fall through to base64 retry — fallback_reason is populated.

    try:
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError as e:
        return f"diagnose_image 실패: 파일 읽기 오류 ({e})"
    body = {"image_base64": b64}
    if question:
        body["question"] = question
    try:
        _, payload = _post(body, timeout=120.0)
    except Exception as e:
        return f"diagnose_image 실패 (base64): {type(e).__name__}: {e}"
    return _format("base64", payload, fallback_reason=fallback_reason)


# search_rag_agent has been removed for direct pass-through in mcp_client.py


def create_agent(**kwargs) -> Agent:
    # Fast path first — LLM should prefer search_workflows for simple lookups.
    kwargs["tools"] = [search_workflows, diagnose_image]
    # 通过用户配置拿/环境变量
    config = kwargs.pop("config") if "config" in kwargs else {}
    # 避免将 None 写入 headers
    session_id = (config or {}).get("session_id")
    default_headers = {}
    if session_id:
        default_headers["X-Session-ID"] = session_id

    # Determine base URL and API key
    base_url = LLM_DEFAULT_BASE_URL
    api_key = get_comfyui_copilot_api_key() or ""

    if config:
        if config.get("openai_base_url") and config.get("openai_base_url") != "":
            base_url = config.get("openai_base_url")
        if config.get("openai_api_key") and config.get("openai_api_key") != "":
            api_key = config.get("openai_api_key")

    # Check if this is LMStudio and adjust API key handling
    is_lmstudio = is_lmstudio_url(base_url)
    if is_lmstudio and not api_key:
        # LMStudio typically doesn't require an API key, use a placeholder
        api_key = "lmstudio-local"

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        default_headers=default_headers,
    )

    # Determine model with proper precedence:
    # 1) Explicit selection from config (model_select from frontend)
    # 2) Explicit kwarg 'model' (call-site override)
    model_from_config = (config or {}).get("model_select")
    model_from_kwargs = kwargs.pop("model", None)

    model_name = (
        model_from_config
        or model_from_kwargs
        or WORKFLOW_LLM_MODEL
        or "gemini-2.5-flash"
    )
    model = OpenAIChatCompletionsModel(model_name, openai_client=client)

    # Safety: ensure no stray 'model' remains in kwargs to avoid duplicate kwarg errors
    kwargs.pop("model", None)

    if config.get("max_tokens"):
        return Agent(
            model=model,
            model_settings=ModelSettings(max_tokens=config.get("max_tokens") or 8192),
            **kwargs,
        )
    return Agent(model=model, **kwargs)
