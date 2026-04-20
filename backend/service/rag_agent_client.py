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

async def pass_through_rag_agent(query: str, session_id: str = "") -> str:
    """
    Sends the chat query to the external RAG agent via REST API.
    Used exclusively in the main chat route to bypass local tool execution and LLM calls.
    """
    url = f"{RAG_API_URL}/agent"
    payload = {
        "query": query,
        "session_id": session_id
    }
    headers = {"Content-Type": "application/json"}
    if RAG_API_KEY:
        headers["X-API-Key"] = RAG_API_KEY
        
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            logger.info(f"Passing chat to RAG agent at {url}")
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
