"""Module 1 — Context Engineering Foundations.

This module introduces the `ContextPlannerAgent`, an ADK agent that
observable reports each stage of the context-engineering supply chain.

Usage
-----
python agents/module1_context_planner_agent.py

The module will iterate through the canonical context pipeline and log
each stage via the ADK tool interface.
"""

from __future__ import annotations

from typing import Iterable

from google.adk import Agent
from google.adk.tools import FunctionTool


def pipeline_logger(stage: str, details: str) -> str:
    """Log a single pipeline stage for observability.

    Parameters
    ----------
    stage
        High-level pipeline stage name (e.g., "Chunking").
    details
        Free-form description of how the stage is configured.

    Returns
    -------
    str
        Confirmation message used by ADK for tracing.
    """

    message = f"[PIPELINE] {stage}: {details}"
    print(message)
    return message


pipeline_logger_tool = FunctionTool(pipeline_logger)


context_planner_agent = Agent(
    name="ContextPlannerAgent",
    description=(
        "Defines and monitors the flow of context through an agentic RAG "
        "pipeline, supporting grounding and context budgeting principles."
    ),
    tools=[pipeline_logger_tool],
)


def log_context_flow(stages: Iterable[tuple[str, str]]) -> None:
    """Iterate through the staged context pipeline and log each step."""

    for stage, details in stages:
        pipeline_logger(stage=stage, details=details)


if __name__ == "__main__":
    default_stages: list[tuple[str, str]] = [
        ("Chunking", "Segment raw data into overlapping semantic chunks."),
        ("Embedding", "Convert chunks to vector embeddings (Chroma store)."),
        (
            "Retrieval",
            "Retrieve top-k chunks using similarity search and optional rerank.",
        ),
        (
            "Context Assembly",
            "Compose ranked chunks into a bounded prompt context window.",
        ),
        ("Reasoning", "Send composed context to Gemini via ADK for response."),
        (
            "Feedback",
            "Log query, retrieved chunk IDs, and feedback for self-healing.",
        ),
    ]

    log_context_flow(default_stages)
    print("ContextPlannerAgent initialized and stages logged.")

