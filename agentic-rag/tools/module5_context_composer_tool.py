"""Module 5 — Context Assembly (Composer).

Provides the `context_composer_tool`, responsible for merging retrieved
chunks into a single context window while respecting the downstream
model's token budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import tiktoken
from google.adk.tools import FunctionTool

DEFAULT_MAX_TOKENS = 6000
DEFAULT_SEPARATOR = "\n---\n"
DEFAULT_ENCODING = "cl100k_base"


@dataclass(frozen=True)
class ComposerConfig:
    max_tokens: int = DEFAULT_MAX_TOKENS
    separator: str = DEFAULT_SEPARATOR
    encoding_name: str = DEFAULT_ENCODING

    def __post_init__(self) -> None:
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if not isinstance(self.separator, str):
            raise TypeError("separator must be a string")
        if not self.encoding_name:
            raise ValueError("encoding_name must be provided")


def _get_encoder(name: str) -> tiktoken.Encoding:
    try:
        return tiktoken.get_encoding(name)
    except KeyError as exc:
        raise ValueError(
            "Unknown tiktoken encoding requested. Provide a valid encoding name."
        ) from exc


def compose_context(
    chunks: Sequence[str],
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    separator: str = DEFAULT_SEPARATOR,
    encoding_name: str = DEFAULT_ENCODING,
    include_token_count: bool = False,
) -> str:
    """Combine chunks into a single string capped by ``max_tokens``."""

    if not chunks:
        return ""

    config = ComposerConfig(
        max_tokens=max_tokens,
        separator=separator,
        encoding_name=encoding_name,
    )

    encoder = _get_encoder(config.encoding_name)

    accumulated_tokens = 0
    assembled_parts: list[str] = []

    for chunk in chunks:
        if not chunk:
            continue
        token_length = len(encoder.encode(chunk))
        if token_length > config.max_tokens:
            # Skip oversized chunk but continue evaluating remaining ones.
            continue
        if accumulated_tokens + token_length > config.max_tokens:
            break
        assembled_parts.append(chunk)
        accumulated_tokens += token_length

    context = config.separator.join(assembled_parts)

    if include_token_count:
        return f"{context}{config.separator}[[TOKENS:{accumulated_tokens}]]"
    return context


context_composer_tool = FunctionTool(compose_context)


def _demo() -> None:
    """Simple smoke test for manual verification."""

    sample_chunks = [
        "The agentic RAG pipeline relies on chunking, embedding, retrieval, and reasoning.",
        "Token budgeting ensures the downstream LLM stays within the context window.",
        "Feedback loops capture successful retrievals for continuous improvement.",
    ]

    result = compose_context(sample_chunks, max_tokens=80, separator="\n---\n")
    print(result)


if __name__ == "__main__":
    _demo()
