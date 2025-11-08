"""Module 7 — Context Feedback & Memory Loops.

Implements the `memory_manager_tool`, responsible for logging retrieval
outcomes and user feedback to a JSON file for later analysis or retraining.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from google.adk.tools import FunctionTool

DEFAULT_LOG_PATH = Path(__file__).resolve().parents[1] / "memory_log.json"


@dataclass
class FeedbackEntry:
    timestamp: str
    query: str
    retrieved_chunks: list[str]
    feedback: str
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def _load_existing(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text("utf-8"))
    except json.JSONDecodeError:
        return []


def store_feedback(
    query: str,
    retrieved_chunks: Optional[Iterable[str]] = None,
    *,
    feedback: str = "positive",
    notes: Optional[str] = None,
    log_path: str | Path = DEFAULT_LOG_PATH,
) -> str:
    """Persist feedback about a retrieval session."""

    if not query or not query.strip():
        raise ValueError("Query must be a non-empty string")

    log_file = Path(log_path)
    existing = _load_existing(log_file)

    entry = FeedbackEntry(
        timestamp=datetime.utcnow().isoformat() + "Z",
        query=query.strip(),
        retrieved_chunks=list(retrieved_chunks or []),
        feedback=feedback,
        notes=notes,
    )

    existing.append(entry.to_dict())
    log_file.write_text(json.dumps(existing, indent=2), "utf-8")
    return f"Feedback stored for query: {entry.query}"


memory_manager_tool = FunctionTool(store_feedback)


def _demo() -> None:
    response = store_feedback(
        "What is the policy for remote work?",
        ["Remote work policy requires manager approval.", "Employees must log availability."],
        feedback="pending",
        notes="Awaiting user confirmation",
    )
    print(response)
    print("Log written to:", DEFAULT_LOG_PATH)


if __name__ == "__main__":
    _demo()
