"""Root ADK agent wiring the Agentic RAG pipeline into a single entry point."""

from __future__ import annotations

from typing import Dict, Any
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import requests

from google.adk import Agent
from google.adk.tools import FunctionTool, McpToolset
from google.adk.tools.mcp_tool.mcp_toolset import (
    StdioConnectionParams,
    StdioServerParameters,
)

PROJECT_ROOT = Path(__file__).resolve().parent
ROOT_ENV_PATH = PROJECT_ROOT.parent / ".env"
load_dotenv(ROOT_ENV_PATH, override=False)
load_dotenv(PROJECT_ROOT / ".env", override=False)
if api_key := os.getenv("GOOGLE_AI_API_KEY"):
    os.environ.setdefault("GOOGLE_API_KEY", api_key)
if project := os.getenv("VERTEX_AI_PROJECT_ID"):
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project)
if location := os.getenv("VERTEX_AI_LOCATION") or os.getenv("GOOGLE_CLOUD_REGION"):
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", location)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from agents.module6_agentic_rag import (
    DEFAULT_TOP_K,
    handle_query,
)
from tools.module5_context_composer_tool import (
    DEFAULT_MAX_TOKENS as COMPOSER_DEFAULT_MAX_TOKENS,
)

RETRIEVE_URL = os.getenv(
    "AGENTIC_RETRIEVE_URL",
    "http://localhost:8000/agentic/retrieve",
)
RETRIEVE_TEAM = os.getenv("AGENTIC_RETRIEVE_TEAM", "xRag")
RETRIEVE_COLLECTION = os.getenv("AGENTIC_RETRIEVE_COLLECTION", "xRag_dev_github")
RETRIEVE_INCLUDE_METADATA = os.getenv("AGENTIC_RETRIEVE_INCLUDE_METADATA", "true") != "false"
RETRIEVE_TIMEOUT = float(os.getenv("AGENTIC_RETRIEVE_TIMEOUT", "30"))

AGENT_INSTRUCTIONS = """
<context_gathering>
For every user question, call `rag_answer_tool` exactly once to retrieve context and draft the answer. If the tool returns an empty context, acknowledge that the repository lacks supporting material.
</context_gathering>

<interaction_style>
- Speak directly to the user; keep internal planning private unless they request it.
- Never ask the user to restate their question unless the input is truly ambiguous.
- After the tool call completes, respond in a single message.
</interaction_style>

<mcp_playwright_usage>
- When the user requests UI automation, first produce a Playwright script (TypeScript) grounded in the retrieved context. Share it with the user for confirmation.
- Only after the user confirms (or explicitly asks you to execute) should you call the Playwright MCP tools to run the script. Announce the tool call and summarise the result.
- Prefer high-level interactions (`browser_goto`, `browser_click`, etc.) and keep the run scope minimal. Avoid coordinate-based tools unless unavoidable.
</mcp_playwright_usage>

<playwright_tool_reference>
Use these exact MCP tool names:
- `playwright__browser_navigate` to open a URL (alias for “goto”).
- `playwright__browser_click` to activate a link or button.
- `playwright__browser_type` to fill text inputs.
- `playwright__browser_wait_for` to wait on selectors or text.
- `playwright__browser_take_screenshot` to capture evidence.
- `playwright__browser_close` when the flow is complete.
Do not invent alternative names such as `browser_goto`—they are not registered.
</playwright_tool_reference>

<final_answer>
Return:
Summary: <one-paragraph answer>
Grounding: <“Grounded in retrieved context” or “No supporting context found—answer is extrapolated.”>
Evidence:
- <source or “None”>
</final_answer>
"""

_playwright_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="npx",
            args=["-y", "@playwright/mcp"],
        ),
        timeout=30.0,
    ),
    tool_name_prefix="playwright_",
)


def _call_retrieval_endpoint(
    question: str,
    *,
    top_k: int,
) -> Dict[str, Any]:
    payload = {
        "question": question,
        "team": RETRIEVE_TEAM,
        "collection": RETRIEVE_COLLECTION,
        "top_k": top_k,
        "include_metadata": RETRIEVE_INCLUDE_METADATA,
    }
    response = requests.post(
        RETRIEVE_URL,
        json=payload,
        timeout=RETRIEVE_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def _rag_answer(
    question: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    max_context_tokens: int = COMPOSER_DEFAULT_MAX_TOKENS,
) -> Dict[str, str]:
    """Run the Agentic RAG pipeline and return the answer with supporting context."""

    try:
        payload = _call_retrieval_endpoint(question, top_k=top_k)
    except Exception as exc:  # pragma: no cover - network fallback
        local_payload = handle_query(
            question,
            top_k=top_k,
            max_context_tokens=max_context_tokens,
        )
        answer_payload = {
            "answer": local_payload["answer"],
            "confidence": None,
            "notes": None,
            "agreed_plan": None,
            "playwright_tests": None,
            "manual_plan": None,
            "code_blocks": [],
            "sources": [],
        }
        return {
            "question": local_payload["question"],
            "rewritten_query": local_payload["rewritten_query"],
            "context": local_payload["context"],
            "answer": local_payload["answer"],
            "answer_payload": answer_payload,
            "sources": [],
            "error": f"Retrieval endpoint failed: {exc}",
        }

    answer_section = payload.get("answer_payload") or {}
    fallback_answer = payload.get("answer") or answer_section.get("answer")

    return {
        "question": payload.get("question", question),
        "rewritten_query": payload.get("rewritten_query") or question,
        "chunks": payload.get("chunks", []),
        "context": payload.get("context", ""),
        "answer": fallback_answer or "",
        "answer_payload": answer_section,
        "sources": payload.get("sources", answer_section.get("sources", [])),
    }


rag_answer_tool = FunctionTool(_rag_answer)

root_agent = Agent(
    name="RagAnswerAgent",
    description=(
        "Answers user questions using the Agentic RAG pipeline. "
        "Always call `rag_answer_tool` to gather relevant context before responding."
    ),
    instruction=AGENT_INSTRUCTIONS,
    model="gemini-2.0-flash",
    tools=[rag_answer_tool, _playwright_toolset],
)
