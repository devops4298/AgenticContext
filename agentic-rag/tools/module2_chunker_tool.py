"""Module 2 — Chunking & Context Windows.

This module defines the `chunker_tool`, a Google ADK FunctionTool that
splits long documents into semantically friendly token windows. The tool
will be registered with the orchestrator agent in later modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

import tiktoken
from google.adk.tools import FunctionTool

DEFAULT_MAX_TOKENS = 400
DEFAULT_OVERLAP = 50


@dataclass(frozen=True)
class ChunkerConfig:
    """Configuration for the adaptive chunker."""

    max_tokens: int = DEFAULT_MAX_TOKENS
    overlap: int = DEFAULT_OVERLAP

    def __post_init__(self) -> None:
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if not 0 <= self.overlap < self.max_tokens:
            raise ValueError("overlap must be in range [0, max_tokens)")


def _get_encoder(model: str = "cl100k_base") -> tiktoken.Encoding:
    """Return a cached tiktoken encoder for the supplied model."""

    try:
        return tiktoken.get_encoding(model)
    except KeyError as exc:
        raise ValueError(
            "Unsupported tiktoken encoding requested. "
            "Install the correct encoding or provide a valid model name."
        ) from exc


def adaptive_chunk(
    text: str,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap: int = DEFAULT_OVERLAP,
    encoding_name: str = "cl100k_base",
) -> list[str]:
    """Split ``text`` into overlapping token windows.

    Parameters
    ----------
    text
        Raw document content to chunk.
    max_tokens
        Maximum tokens per chunk. Defaults to 400 (~300–400 words for Gemini).
    overlap
        Token overlap between sequential chunks to preserve context continuity.
    encoding_name
        Tiktoken encoding identifier. Defaults to ``cl100k_base`` (Gemini/GPT-4).
    """

    if not text:
        return []

    cfg = ChunkerConfig(max_tokens=max_tokens, overlap=overlap)
    encoder = _get_encoder(encoding_name)
    tokens = encoder.encode(text)

    chunks: List[str] = []
    start = 0
    stride = cfg.max_tokens - cfg.overlap

    while start < len(tokens):
        end = min(start + cfg.max_tokens, len(tokens))
        chunk_tokens = tokens[start:end]
        chunk_text = encoder.decode(chunk_tokens)
        chunks.append(chunk_text)
        if end == len(tokens):
            break
        start += stride

    return chunks


chunker_tool = FunctionTool(adaptive_chunk)


def _demo() -> None:
    """Simple local demonstration for manual testing."""

    sample_text = (
        "Context engineering treats prompt construction as a supply chain. "
        "By chunking documents into overlapping semantic windows we maintain "
        "grounding while respecting the model's token limits. "
        "This sample paragraph is duplicated to exercise the chunker. "
        "Context engineering treats prompt construction as a supply chain. "
        "By chunking documents into overlapping semantic windows we maintain "
        "grounding while respecting the model's token limits."
    )

    chunks = adaptive_chunk(sample_text, max_tokens=60, overlap=10)
    print(f"Generated {len(chunks)} chunks:\n")
    for idx, chunk in enumerate(chunks, start=1):
        print(f"--- Chunk {idx} ---")
        print(chunk)
        print()


if __name__ == "__main__":
    _demo()
