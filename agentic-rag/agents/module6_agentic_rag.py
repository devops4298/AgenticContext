"""Module 6 — Agentic RAG Architecture.

Defines the `ContextOrchestratorAgent`, an ADK agent that wires the
query rewriter, vector retriever, context composer, and Gemini reasoning
into a single callable pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Sequence

import sys
import sqlite3

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import chromadb
from google.genai.types import GenerateContentConfig
from google.adk import Agent
from google.adk.tools import FunctionTool

from tools import module3_embedder_tool as embedder_module
from tools import module4_query_rewriter_tool as rewriter_module
from tools.module5_context_composer_tool import (
    DEFAULT_MAX_TOKENS as COMPOSER_DEFAULT_MAX_TOKENS,
    context_composer_tool,
)

DEFAULT_REASONER_MODEL = rewriter_module.DEFAULT_MODEL
DEFAULT_TOP_K = 5


@dataclass(frozen=True)
class RetrievalConfig:
    collection_name: str = embedder_module.DEFAULT_COLLECTION
    persist_directory: Path = embedder_module.DEFAULT_PERSIST_DIR
    embedding_model: str = embedder_module.DEFAULT_MODEL

    def __post_init__(self) -> None:
        if not self.collection_name:
            raise ValueError("collection_name must be provided")
        if not self.embedding_model:
            raise ValueError("embedding_model must be provided")


_COLLECTION_CACHE: Dict[tuple[str, str], chromadb.api.models.Collection] = {}
_CLIENT_CACHE: Dict[str, chromadb.api.client.ClientAPI] = {}
def _get_client(path: Path) -> chromadb.api.client.ClientAPI:
    key = str(path.resolve())
    if key not in _CLIENT_CACHE:
        path.mkdir(parents=True, exist_ok=True)
        _CLIENT_CACHE[key] = chromadb.PersistentClient(path=key)
    return _CLIENT_CACHE[key]


def _get_collection(config: RetrievalConfig) -> chromadb.api.models.Collection:
    cache_key = (config.collection_name, str(config.persist_directory.resolve()))
    if cache_key not in _COLLECTION_CACHE:
        client = _get_client(config.persist_directory)
        try:
            _COLLECTION_CACHE[cache_key] = client.get_or_create_collection(
                config.collection_name
            )
        except sqlite3.OperationalError as exc:
            raise RuntimeError(
                "Chroma persisting state is incompatible with the current version. "
                "Delete the directory at 'chroma_db/' and re-run ingestion."
            ) from exc
    return _COLLECTION_CACHE[cache_key]


def retrieve_relevant_chunks(
    query: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    collection_name: str = embedder_module.DEFAULT_COLLECTION,
    persist_directory: str | Path | None = None,
    embedding_model: str = embedder_module.DEFAULT_MODEL,
    include_metadata: bool = True,
) -> List[str]:
    """Retrieve the top-k chunks matching the rewritten query."""

    if not query or not query.strip():
        raise ValueError("Query must be a non-empty string")

    config = RetrievalConfig(
        collection_name=collection_name,
        persist_directory=Path(persist_directory)
        if persist_directory
        else embedder_module.DEFAULT_PERSIST_DIR,
        embedding_model=embedding_model,
    )

    try:
        collection = _get_collection(config)
    except RuntimeError as exc:
        print(f"[Retriever] {exc}")  # pragma: no cover - diagnostic output
        return []

    query_embeddings = embedder_module.embed_texts(
        [query],
        model_name=config.embedding_model,
    )
    if not query_embeddings:
        return []
    query_vector = query_embeddings[0]

    try:
        results = collection.query(
            query_embeddings=[query_vector],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
    except ValueError:
        return []

    documents = results.get("documents", [[]])[0] or []
    metadatas = results.get("metadatas", [[]])[0] or []

    assembled: List[str] = []
    for doc, metadata in zip(documents, metadatas):
        if not doc:
            continue
        if include_metadata and metadata:
            meta_str = ", ".join(f"{k}={v}" for k, v in metadata.items())
            assembled.append(f"{doc}\n[metadata: {meta_str}]")
        else:
            assembled.append(doc)
    return assembled


vector_retriever_tool = FunctionTool(retrieve_relevant_chunks)
query_rewriter_tool = rewriter_module.query_rewriter_tool

_context_orchestrator_agent = Agent(
    name="ContextOrchestratorAgent",
    description=(
        "Coordinates query rewriting, vector retrieval, and context assembly "
        "as part of the agentic RAG pipeline."
    ),
    tools=[query_rewriter_tool, vector_retriever_tool, context_composer_tool],
)


def _call_reasoner(
    *,
    question: str,
    context: str,
    model_name: str = DEFAULT_REASONER_MODEL,
    temperature: float = 0.2,
    max_output_tokens: int = 512,
) -> str:
    client = rewriter_module._get_client()  # pylint: disable=protected-access

    prompt = (
        "You are a helpful enterprise assistant. Answer the user question using the "
        "provided context. If the context is empty, say you cannot find relevant "
        "information."
    )

    contents = (
        f"{prompt}\n\nContext:\n{context or 'N/A'}\n\n"
        f"Question: {question}\nAnswer:"
    )

    response = client.models.generate_content(
        model=model_name,
        contents=[contents],
        config=GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        ),
    )

    if not response.candidates:
        raise RuntimeError("Reasoner returned no candidates.")
    return response.candidates[0].content.parts[0].text.strip()


def handle_query(
    query: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    max_context_tokens: int = COMPOSER_DEFAULT_MAX_TOKENS,
    answer_model: str = DEFAULT_REASONER_MODEL,
) -> Dict[str, Any]:
    """Execute the full RAG pipeline for the incoming query."""

    rewritten = query_rewriter_tool.func(query)
    chunks = vector_retriever_tool.func(rewritten, top_k=top_k)

    context = context_composer_tool.func(
        chunks,
        max_tokens=max_context_tokens,
    )

    try:
        answer = _call_reasoner(
            question=query,
            context=context,
            model_name=answer_model,
        )
    except Exception as exc:  # pragma: no cover - surfaced during manual runs
        answer = f"Reasoner unavailable: {exc}"

    return {
        "question": query,
        "rewritten_query": rewritten,
        "chunks": chunks,
        "context": context,
        "answer": answer,
    }


def _demo() -> None:
    payload = handle_query("What is the policy for remote work?", top_k=3)
    print("Rewritten Query:\n", payload["rewritten_query"], "\n", sep="")
    print("Retrieved Chunks:\n", "\n---\n".join(payload["chunks"]) or "None", sep="")
    print("\nFinal Answer:\n", payload["answer"], sep="")


if __name__ == "__main__":
    _demo()
