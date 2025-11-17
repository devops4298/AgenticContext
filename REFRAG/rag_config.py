#!/usr/bin/env python3
"""
rag_config.py — Configuration and constants for RAG pipeline
"""

import os
import pathlib
from dataclasses import dataclass
from typing import Optional

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = lambda *a, **k: None  # no-op if not installed

load_dotenv()  # load .env if present

# -----------------------
# Constants and defaults
# -----------------------
DEFAULT_CACHE_DIR = os.getenv("CACHE_DIR", "./rag_cache")
os.makedirs(DEFAULT_CACHE_DIR, exist_ok=True)
DEFAULT_FAISS_PATH = os.getenv("FAISS_INDEX_PATH", os.path.join(DEFAULT_CACHE_DIR, "faiss.index"))
DEFAULT_METADATA_PATH = os.path.join(DEFAULT_CACHE_DIR, "metadata.pkl")
DEFAULT_RAW_EMB_PATH = os.path.join(DEFAULT_CACHE_DIR, "raw_embeddings.npy")
DEFAULT_PROJECTED_VECS_PATH = os.path.join(DEFAULT_CACHE_DIR, "projected_vectors.npy")
DEFAULT_SUMMARIES_PATH = os.path.join(DEFAULT_CACHE_DIR, "chunk_summaries.pkl")
DEFAULT_INDEX_METADATA_PATH = os.path.join(DEFAULT_CACHE_DIR, "index_metadata.json")

# Gemini API config from env
GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-004")
TEXT_MODEL = os.getenv("TEXT_MODEL", "gemini-1.5-pro")

# Embedding/decoder dims
EMBED_DIM = int(os.getenv("EMBED_DIM", "768"))
DECODER_EMB_DIM = int(os.getenv("DECODER_EMB_DIM", "4096"))

# Default chunking params
DEFAULT_CHUNK_SIZE_WORDS = int(os.getenv("CHUNK_SIZE_WORDS", "200"))
DEFAULT_CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP_WORDS", "30"))

# Retrieval defaults
DEFAULT_TOP_K = int(os.getenv("TOP_K", "40"))
DEFAULT_EXPAND_FRACTION = float(os.getenv("EXPAND_FRACTION", "0.15"))

# Repro
import torch
SEED = int(os.getenv("RANDOM_SEED", "42"))
torch.manual_seed(SEED)


# -----------------------
# Configuration class
# -----------------------
@dataclass
class AppConfig:
    clone_dir: str = "./cloned_repo"
    cache_dir: str = DEFAULT_CACHE_DIR
    faiss_index_path: str = DEFAULT_FAISS_PATH
    metadata_path: str = DEFAULT_METADATA_PATH
    raw_emb_path: str = DEFAULT_RAW_EMB_PATH
    projected_vecs_path: str = DEFAULT_PROJECTED_VECS_PATH
    summaries_path: str = DEFAULT_SUMMARIES_PATH
    index_metadata_path: str = DEFAULT_INDEX_METADATA_PATH

    chunk_size_words: int = DEFAULT_CHUNK_SIZE_WORDS
    chunk_overlap_words: int = DEFAULT_CHUNK_OVERLAP
    embed_model: str = EMBEDDING_MODEL
    text_model: str = TEXT_MODEL
    google_ai_api_key: Optional[str] = GOOGLE_AI_API_KEY
    embed_dim: int = EMBED_DIM
    decoder_emb_dim: int = DECODER_EMB_DIM
    top_k: int = DEFAULT_TOP_K
    expand_fraction: float = DEFAULT_EXPAND_FRACTION
    device: str = "cpu"
    
    # Agentic RAG enhancements
    feedback_enabled: bool = True
    feedback_path: str = os.path.join(DEFAULT_CACHE_DIR, "feedback_log.json")
    query_rewrite_enabled: bool = True
    iterative_refinement_enabled: bool = True
    max_iterations: int = 3
    iteration_confidence_threshold: float = 0.7

    def ensure_dirs(self):
        pathlib.Path(self.cache_dir).mkdir(parents=True, exist_ok=True)

