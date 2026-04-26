import asyncio
import httpx
import logging
from typing import Optional
from dotenv import load_dotenv
import os

logger = logging.getLogger(__name__)

# Load local env for RAG API URL
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))

RAG_API_URL = os.getenv("RAG_API_URL", "http://192.168.10.2:7001")
RAG_API_KEY = os.getenv("RAG_API_KEY", "")

async def pass_through_rag_agent(
    query: str,
    session_id: str = "",
    mode: str = "search_only",
    auto_analyze: bool = True,
    client_id: str = "",
) -> str:
    """
    Send the chat query to the RAG /agent/pipeline endpoint (canonical contract).

    Returns the AgentPipelineResponse.answer text. Callers that need workflow_id /
    selected_workflow / vision_analysis should call /agent/pipeline directly via
    the MCP run_pipeline tool path so the full envelope (ext, image_paths, etc.)
    is preserved.
    """
    url = f"{RAG_API_URL}/agent/pipeline"
    payload = {
        "query": query,
        "session_id": session_id,
        "mode": mode,
        "auto_analyze": auto_analyze,
        "client_id": client_id,
    }
    headers = {"Content-Type": "application/json"}
    if RAG_API_KEY:
        headers["X-API-Key"] = RAG_API_KEY

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            logger.info(f"Passing chat to RAG /agent/pipeline at {url} (mode={mode})")
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()

            result = response.json()
            return result.get("answer", "No answer received from RAG agent.")

    except httpx.HTTPStatusError as e:
        logger.error(f"RAG API HTTP Error: {e.response.status_code} - {e.response.text}")
        return f"Error from RAG agent: {e.response.status_code}"
    except Exception as e:
        logger.error(f"Failed to connect to RAG API: {e}")
        return f"Could not reach the remote RAG agent. {str(e)[:100]}"
