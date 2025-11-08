"""Module 3 — Embeddings & Vector Stores.

Provides the `embedder_tool`, a Google ADK FunctionTool that embeds text
chunks with Sentence Transformers and persists them in a Chroma DB
collection. This module will be orchestrated by downstream agents for RAG
pipelines.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence
from uuid import uuid4

import chromadb
from chromadb.api.models.Collection import Collection
try:  # Chroma <0.5 compatibility
    from chromadb.errors import NotFoundError
except ImportError:  # pragma: no cover - fallback for older versions
    NotFoundError = Exception  # type: ignore[assignment]
import shutil
from google.genai.types import EmbedContentConfig

from google.adk.tools import FunctionTool
from tools.module4_query_rewriter_tool import (
    _get_client as get_gemini_client,  # type: ignore
)

DEFAULT_MODEL = "text-embedding-004"
DEFAULT_COLLECTION = "docs"
DEFAULT_PERSIST_DIR = Path(__file__).resolve().parents[1] / "chroma_db"


@dataclass(frozen=True)
class EmbedderConfig:
    """Configuration for the embedding + storage workflow."""

    model_name: str = DEFAULT_MODEL
    collection_name: str = DEFAULT_COLLECTION
    persist_directory: Path = DEFAULT_PERSIST_DIR

    def __post_init__(self) -> None:
        if not self.collection_name:
            raise ValueError("collection_name must be a non-empty string")
        if not self.model_name:
            raise ValueError("model_name must be a non-empty string")
        if not self.persist_directory:
            raise ValueError("persist_directory must be provided")


_COLLECTION_CACHE: dict[tuple[str, str], Collection] = {}
_CLIENT_CACHE: dict[str, chromadb.api.client.ClientAPI] = {}


def _get_client(persist_directory: Path) -> chromadb.api.client.ClientAPI:
    persist_key = str(persist_directory.resolve())
    if persist_key not in _CLIENT_CACHE:
        persist_directory.mkdir(parents=True, exist_ok=True)
        _CLIENT_CACHE[persist_key] = chromadb.PersistentClient(path=persist_key)
    return _CLIENT_CACHE[persist_key]


def _get_collection(config: EmbedderConfig) -> Collection:
    cache_key = (config.collection_name, str(config.persist_directory.resolve()))
    if cache_key not in _COLLECTION_CACHE:
        client = _get_client(config.persist_directory)
        _COLLECTION_CACHE[cache_key] = client.get_or_create_collection(
            config.collection_name
        )
    return _COLLECTION_CACHE[cache_key]


def _prepare_metadata(
    chunks: Sequence[str], metadata_list: Optional[Sequence[Optional[dict]]]
) -> list[dict]:
    if metadata_list is None:
        return [{} for _ in chunks]
    if len(metadata_list) != len(chunks):
        raise ValueError("metadata_list length must match chunks length")
    return [m or {} for m in metadata_list]


def embed_texts(
    texts: Sequence[str],
    *,
    model_name: str = DEFAULT_MODEL,
) -> list[list[float]]:
    """Generate embeddings for a batch of texts using Gemini embeddings."""

    if not texts:
        return []

    client = get_gemini_client()
    embeddings: list[list[float]] = []

    for text in texts:
        response = client.models.embed_content(
            model=model_name,
            contents=[
                {
                    "role": "user",
                    "parts": [{"text": text}],
                }
            ],
            config=EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
        )
        if not response.embeddings:
            raise RuntimeError("Gemini embeddings response contained no vectors.")
        embeddings.append(list(response.embeddings[0].values))

    return embeddings


def embed_and_store(
    chunks: Sequence[str],
    metadata_list: Optional[Sequence[Optional[dict]]] = None,
    *,
    model_name: str = DEFAULT_MODEL,
    collection_name: str = DEFAULT_COLLECTION,
    persist_directory: Optional[str | Path] = None,
    id_prefix: str = "chunk",
) -> str:
    """Embed each chunk and persist embeddings + metadata to Chroma DB."""

    if not chunks:
        return "No chunks provided; nothing stored."

    persist_path = Path(persist_directory) if persist_directory else DEFAULT_PERSIST_DIR
    config = EmbedderConfig(
        model_name=model_name,
        collection_name=collection_name,
        persist_directory=persist_path,
    )

    collection = _get_collection(config)

    embeddings = embed_texts(list(chunks), model_name=config.model_name)
    metadatas = _prepare_metadata(chunks, metadata_list)
    for idx, meta in enumerate(metadatas):
        if not meta:
            metadatas[idx] = {"chunk_index": idx}
    ids = [f"{id_prefix}_{uuid4().hex}" for _ in chunks]

    collection.upsert(
        documents=list(chunks),
        embeddings=embeddings,
        metadatas=metadatas,
        ids=ids,
    )

    return (
        f"Stored {len(chunks)} chunks in collection '{config.collection_name}' "
        f"at {config.persist_directory}."
    )


embedder_tool = FunctionTool(embed_and_store)


def _demo() -> None:
    """Manual smoke test when running the module directly."""

    sample_chunks = [
        "Context engineering treats prompts as a managed supply chain.",
        "Embedding converts text chunks into high-dimensional vectors for retrieval.",
    ]
    message = embed_and_store(sample_chunks, id_prefix="demo")
    print(message)


if __name__ == "__main__":
    _demo()


def reset_vector_store(
    *,
    collection_name: str = DEFAULT_COLLECTION,
    persist_directory: Optional[str | Path] = None,
    drop_storage: bool = True,
) -> str:
    """Remove cached clients and optionally delete the persisted Chroma directory."""

    persist_path = Path(persist_directory) if persist_directory else DEFAULT_PERSIST_DIR
    cache_key = (collection_name, str(persist_path.resolve()))
    _COLLECTION_CACHE.pop(cache_key, None)
    client_key = str(persist_path.resolve())
    _CLIENT_CACHE.pop(client_key, None)

    if drop_storage:
        if persist_path.exists():
            shutil.rmtree(persist_path)
        persist_path.mkdir(parents=True, exist_ok=True)
        return (
            f"Reset collection '{collection_name}'. Storage "
            f"recreated at {persist_path}."
        )

    client = chromadb.PersistentClient(path=str(persist_path.resolve()))
    try:
        client.delete_collection(collection_name)
    except NotFoundError:
        pass

    return (
        f"Reset collection '{collection_name}'. Storage retained at {persist_path}."
    )
