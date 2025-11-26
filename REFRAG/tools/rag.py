#!/usr/bin/env python3
"""
rag.py — Consolidated RAG System

A clean, modular implementation of the RAG (Retrieval Augmented Generation) pipeline.
All RAG functionality consolidated into a single, well-organized file.

Sections:
1. Configuration & Constants
2. Utilities
3. Core RAG Components
4. Agentic RAG Components
5. RAG Pipeline Orchestrator
6. RAG Tool Wrapper
"""

from __future__ import annotations
import os
import sys
import json
import logging
import pickle
import argparse
import datetime
import pathlib
import shutil
import time
import tempfile
from typing import List, Dict, Tuple, Any, Optional, Iterable
from functools import wraps
from dataclasses import dataclass
from collections import Counter
from time import sleep

# Fix OpenMP conflict
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

# Third-party imports
try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = lambda *a, **k: None

try:
    import faiss
except Exception as e:
    raise RuntimeError("faiss is required. Install with `pip install faiss-cpu`") from e

try:
    import torch
    import torch.nn as nn
    import torch.utils.data
except Exception as e:
    raise RuntimeError("torch is required. Install with `pip install torch`") from e

try:
    from git import Repo
except Exception as e:
    raise RuntimeError("GitPython is required. Install with `pip install GitPython`") from e

try:
    import google.genai as genai
    from google.genai.types import EmbedContentConfig, GenerateContentConfig
except Exception as e:
    raise RuntimeError("google-genai is required. Install with `pip install google-genai`") from e

try:
    from tqdm import tqdm
except Exception:
    tqdm = lambda x, **k: x

load_dotenv()

# ============================================================================
# SECTION 1: CONFIGURATION & CONSTANTS
# ============================================================================

DEFAULT_CACHE_DIR = os.getenv("CACHE_DIR", "./rag_cache")
os.makedirs(DEFAULT_CACHE_DIR, exist_ok=True)
DEFAULT_FAISS_PATH = os.getenv("FAISS_INDEX_PATH", os.path.join(DEFAULT_CACHE_DIR, "faiss.index"))
DEFAULT_METADATA_PATH = os.path.join(DEFAULT_CACHE_DIR, "metadata.pkl")
DEFAULT_RAW_EMB_PATH = os.path.join(DEFAULT_CACHE_DIR, "raw_embeddings.npy")
DEFAULT_PROJECTED_VECS_PATH = os.path.join(DEFAULT_CACHE_DIR, "projected_vectors.npy")
DEFAULT_SUMMARIES_PATH = os.path.join(DEFAULT_CACHE_DIR, "chunk_summaries.pkl")
DEFAULT_INDEX_METADATA_PATH = os.path.join(DEFAULT_CACHE_DIR, "index_metadata.json")

GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-004")
TEXT_MODEL = os.getenv("TEXT_MODEL", "gemini-1.5-pro")

EMBED_DIM = int(os.getenv("EMBED_DIM", "768"))
DECODER_EMB_DIM = int(os.getenv("DECODER_EMB_DIM", "4096"))

DEFAULT_CHUNK_SIZE_WORDS = int(os.getenv("CHUNK_SIZE_WORDS", "200"))
DEFAULT_CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP_WORDS", "30"))

DEFAULT_TOP_K = int(os.getenv("TOP_K", "40"))
DEFAULT_EXPAND_FRACTION = float(os.getenv("EXPAND_FRACTION", "0.15"))

import torch
SEED = int(os.getenv("RANDOM_SEED", "42"))
torch.manual_seed(SEED)


@dataclass
class AppConfig:
    """Application configuration for RAG pipeline."""
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


# ============================================================================
# SECTION 2: UTILITIES
# ============================================================================

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("rag")

# Suppress httpx HTTP request logging
logging.getLogger("httpx").setLevel(logging.WARNING)


def retry(exceptions, tries=4, delay=1.0, backoff=2.0, logger=logger):
    """Decorator for retrying functions with exponential backoff."""
    def deco_retry(f):
        @wraps(f)
        def f_retry(*args, **kwargs):
            mtries, mdelay = tries, delay
            while mtries > 1:
                try:
                    return f(*args, **kwargs)
                except exceptions as e:
                    msg = f"{f.__name__} failed with {e}, retrying in {mdelay} seconds..."
                    logger.warning(msg)
                    sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
            return f(*args, **kwargs)
        return f_retry
    return deco_retry


# ============================================================================
# SECTION 3: CORE RAG COMPONENTS
# ============================================================================

class RepoLoader:
    """Loads and collects text files from repositories or directories."""
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.logger = logging.getLogger("RepoLoader")

    def clone(self, git_url: str, dest: Optional[str] = None, force: bool = False) -> str:
        dest = dest or self.config.clone_dir
        if os.path.exists(dest):
            if force:
                self.logger.info("Removing existing directory %s due to --force", dest)
                shutil.rmtree(dest)
            else:
                self.logger.info("Using existing clone at %s", dest)
                return dest
        self.logger.info("Cloning %s -> %s", git_url, dest)
        Repo.clone_from(git_url, dest)
        return dest

    def collect_text_files(self, root: str, extensions: Optional[Iterable[str]] = None) -> Dict[str, str]:
        """Collects text files from a directory tree, skipping binary files."""
        if extensions is None:
            extensions = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".rst", ".ini", ".cfg", ".toml", 
                         ".Dockerfile", ".mdown", ".js", ".ts", ".jsx", ".tsx", ".css", ".html", ".xml", 
                         ".csv", ".sql", ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmake", ".make", ".go",
                         ".rs", ".java", ".cpp", ".c", ".h", ".hpp", ".cc", ".cxx", ".cs", ".php", ".rb",
                         ".swift", ".kt", ".scala", ".lua", ".r", ".m", ".mm", ".dart", ".vue", ".svelte"}
        
        binary_extensions = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp", 
                           ".pdf", ".zip", ".tar", ".gz", ".rar", ".7z", ".exe", ".dll", ".so", ".dylib",
                           ".bin", ".dat", ".db", ".sqlite", ".sqlite3", ".mp3", ".mp4", ".avi", ".mov",
                           ".wav", ".flac", ".ogg", ".woff", ".woff2", ".ttf", ".eot", ".otf", ".class",
                           ".pyc", ".pyo", ".pyd", ".o", ".obj", ".a", ".lib", ".dylib", ".egg", ".whl"}
        
        collected: Dict[str, str] = {}
        for dirpath, dirs, files in os.walk(root):
            if any(x in dirpath for x in ["/.git", "/node_modules", "/venv", "/.venv", "/dist", "/build", 
                                         "/__pycache__", "/.pytest_cache", "/.mypy_cache", "/.idea", "/.vscode",
                                         "/target", "/bin", "/obj", "/.gradle", "/.cache"]):
                continue
            for fname in files:
                path = os.path.join(dirpath, fname)
                ext = pathlib.Path(fname).suffix.lower()
                
                if ext in binary_extensions:
                    continue
                
                if ext in extensions or fname.lower() in {"readme", "license", "makefile", "dockerfile", 
                                                          "docker-compose", ".gitignore", ".env.example"}:
                    try:
                        with open(path, "rb") as f:
                            chunk = f.read(8192)
                            if b'\x00' in chunk:
                                continue
                        
                        with open(path, "r", encoding="utf-8", errors="ignore") as f:
                            text = f.read()
                            if text and text.strip():
                                collected[path] = text
                    except (UnicodeDecodeError, Exception):
                        continue
        self.logger.info("Collected %d text files from %s", len(collected), root)
        return collected


class Chunker:
    """Splits text into overlapping chunks."""
    
    def __init__(self, config: AppConfig):
        self.config = config

    def chunk_text(self, text: str, chunk_size: Optional[int] = None, overlap: Optional[int] = None) -> List[str]:
        chunk_size = chunk_size or self.config.chunk_size_words
        overlap = overlap if overlap is not None else self.config.chunk_overlap_words
        words = text.split()
        if not words:
            return []
        chunks: List[str] = []
        i = 0
        while i < len(words):
            chunk = words[i:i + chunk_size]
            chunks.append(" ".join(chunk))
            i += max(1, chunk_size - overlap)
        return chunks

    def chunk_files(self, files: Dict[str, str]) -> List[Dict[str, Any]]:
        """Returns list of metadata dicts: {"path", "chunk_idx", "text"}"""
        out = []
        for path, txt in files.items():
            chunks = self.chunk_text(txt)
            for idx, ch in enumerate(chunks):
                out.append({"path": path, "chunk_idx": idx, "text": ch})
        return out


class VertexEmbedder:
    """Embeds text using Gemini API."""
    
    def __init__(self, config: AppConfig):
        self.cfg = config
        self.logger = logging.getLogger("VertexEmbedder")
        if not self.cfg.google_ai_api_key:
            raise ValueError("GOOGLE_AI_API_KEY environment variable is required.")
        self.client = genai.Client(api_key=self.cfg.google_ai_api_key)
        self._query_cache: Dict[str, List[float]] = {}

    @retry(Exception, tries=4, delay=1.0, backoff=2.0, logger=logger)
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of texts using Gemini embeddings API."""
        model = self.cfg.embed_model
        vectors = []
        for text in texts:
            response = self.client.models.embed_content(
                model=model,
                contents=[{"role": "user", "parts": [{"text": text}]}],
                config=EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
            )
            if not response.embeddings:
                raise RuntimeError("Gemini embeddings response contained no vectors.")
            vectors.append(list(response.embeddings[0].values))
        return vectors

    def embed_texts(self, texts: List[str], batch_size: int = 64, use_cache: bool = True) -> List[List[float]]:
        """Public API: embed a list of texts, with batching and normalization."""
        if use_cache and len(texts) == 1:
            query_text = texts[0]
            if query_text in self._query_cache:
                self.logger.info("Using cached embedding for query")
                return [self._query_cache[query_text]]
        
        out_vectors: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]
            self.logger.info("Embedding batch %d..%d", i, i+len(batch))
            vs = self.embed_batch(batch)
            out_vectors.extend(vs)
        
        import numpy as np
        arr = np.array(out_vectors, dtype="float32")
        norms = np.linalg.norm(arr, axis=1, keepdims=True) + 1e-12
        arr = arr / norms
        result = arr.tolist()
        
        if use_cache and len(texts) == 1:
            self._query_cache[texts[0]] = result[0]
        
        return result


class FaissIndexer:
    """Builds and searches FAISS index."""
    
    def __init__(self, config: AppConfig):
        self.cfg = config
        self.index: Optional[faiss.Index] = None
        self.logger = logging.getLogger("FaissIndexer")

    def build(self, vectors: "np.ndarray", metric: str = "ip"):
        """Build a FAISS flat index (inner product)."""
        import numpy as np
        vectors = np.array(vectors).astype("float32")
        d = vectors.shape[1]
        if metric == "ip":
            self.index = faiss.IndexFlatIP(d)
        else:
            self.index = faiss.IndexFlatL2(d)
        self.index.add(vectors)
        self.logger.info("FAISS index built with %d vectors (dim=%d)", self.index.ntotal, d)
        return self.index

    def save(self, path: Optional[str] = None):
        path = path or self.cfg.faiss_index_path
        if self.index is None:
            raise RuntimeError("Index is None; cannot save")
        faiss.write_index(self.index, path)
        self.logger.info("Saved FAISS index to %s", path)

    def load(self, path: Optional[str] = None):
        path = path or self.cfg.faiss_index_path
        if not os.path.exists(path):
            raise FileNotFoundError(f"FAISS index file not found at {path}")
        self.index = faiss.read_index(path)
        self.logger.info("Loaded FAISS index from %s", path)
        return self.index

    def search(self, query_vector: List[float], top_k: int = 10) -> Tuple[List[int], List[float]]:
        import numpy as np
        if self.index is None:
            raise RuntimeError("Index not initialized")
        q = np.array(query_vector, dtype="float32").reshape(1, -1)
        D, I = self.index.search(q, top_k)
        return I[0].tolist(), D[0].tolist()


class ProjectionMLP(nn.Module):
    """Projection network for REFRAG-style compression."""
    
    def __init__(self, enc_dim: int, dec_dim: int, hidden: Optional[int] = None):
        super().__init__()
        if hidden is None:
            hidden = dec_dim
        self.net = nn.Sequential(
            nn.Linear(enc_dim, hidden),
            nn.GELU(),
            nn.Linear(hidden, dec_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class VertexSummarizer:
    """Creates dense summaries using Gemini API."""
    
    def __init__(self, config: AppConfig, max_tokens: int = 64):
        self.cfg = config
        self.logger = logging.getLogger("VertexSummarizer")
        if not self.cfg.google_ai_api_key:
            raise ValueError("GOOGLE_AI_API_KEY is required for summarization")
        self.client = genai.Client(api_key=self.cfg.google_ai_api_key)
        self.model = self.cfg.text_model
        self.max_tokens = max_tokens

    @retry(Exception, tries=3, delay=1.0, backoff=2.0, logger=logger)
    def summarize(self, text: str, prompt_prefix: Optional[str] = None) -> str:
        """Create a dense (1-2 sentence) summary of text."""
        prompt_prefix = prompt_prefix or "Summarize the following carefully in 1-2 concise sentences focusing on important facts and functions:"
        prompt = f"{prompt_prefix}\n\n===\n{text}\n===\nSummary:"
        
        config = GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=self.max_tokens,
            top_p=0.95,
        )
        
        response = self.client.models.generate_content(
            model=self.model,
            contents=[prompt],
            config=config,
        )
        
        if not response.candidates or not response.candidates[0].content:
            raise RuntimeError("No prediction from Gemini summarize()")
        
        return response.candidates[0].content.parts[0].text.strip()


class Retriever:
    """Retrieves and expands chunks."""
    
    def __init__(self, config: AppConfig, indexer: FaissIndexer, metadata: List[Dict[str, Any]], 
                 projected_vectors: Optional["np.ndarray"] = None):
        self.cfg = config
        self.indexer = indexer
        self.metadata = metadata
        self.projected_vectors = projected_vectors
        self.logger = logging.getLogger("Retriever")

    def retrieve(self, query: str, embedder: VertexEmbedder, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        top_k = top_k or self.cfg.top_k
        self.logger.info("Embedding query for retrieval...")
        qv = embedder.embed_texts([query])[0]
        idxs, scores = self.indexer.search(qv, top_k=top_k)
        hits = []
        for idx, score in zip(idxs, scores):
            meta = self.metadata[idx].copy()
            meta["_index_id"] = idx
            meta["_score"] = float(score)
            hits.append(meta)
        return hits

    def heuristic_expand(self, hits: List[Dict[str, Any]], fraction: float = None) -> Tuple[set, List[str]]:
        """Heuristic to choose which hits to expand."""
        fraction = fraction or self.cfg.expand_fraction
        scores = []
        for i, h in enumerate(hits):
            txt = h["text"]
            s = len(txt.split())
            if any(keyword in txt for keyword in ("def ", "class ", "import ", "http", "retry", "requests")):
                s += 50
            s += int(h.get("_score", 0) * 10)
            scores.append((i, s))
        N = max(1, int(len(hits) * fraction))
        topk = sorted(scores, key=lambda x: x[1], reverse=True)[:N]
        expand_indices = set(i for i, _ in topk)
        expanded_texts = [hits[i]["text"] for i in sorted(list(expand_indices))]
        return expand_indices, expanded_texts


# ============================================================================
# SECTION 4: AGENTIC RAG COMPONENTS
# ============================================================================

class FeedbackLoop:
    """Stores and learns from user feedback to improve retrieval."""
    
    def __init__(self, config: AppConfig):
        self.cfg = config
        self.logger = logging.getLogger("FeedbackLoop")
        self.feedback_path = config.feedback_path
        self.feedback_data: Dict[str, Any] = {
            "corrections": [],
            "positive_feedback": [],
            "negative_feedback": [],
            "improved_chunks": {},
            "query_patterns": {},
        }
        self._load_feedback()
    
    def _load_feedback(self):
        if os.path.exists(self.feedback_path):
            try:
                with open(self.feedback_path, "r") as f:
                    self.feedback_data = json.load(f)
                self.logger.info("Loaded %d feedback entries", len(self.feedback_data.get("corrections", [])))
            except Exception as e:
                self.logger.warning("Failed to load feedback: %s", e)
    
    def save_feedback(self):
        try:
            with open(self.feedback_path, "w") as f:
                json.dump(self.feedback_data, f, indent=2)
            self.logger.info("Saved feedback to %s", self.feedback_path)
        except Exception as e:
            self.logger.error("Failed to save feedback: %s", e)
    
    def record_correction(self, query: str, original_answer: str, corrected_answer: str, 
                         retrieved_chunks: List[Dict], user_notes: Optional[str] = None):
        correction = {
            "timestamp": time.time(),
            "query": query,
            "original_answer": original_answer,
            "corrected_answer": corrected_answer,
            "retrieved_chunk_ids": [ch.get("_index_id") for ch in retrieved_chunks],
            "user_notes": user_notes,
        }
        self.feedback_data["corrections"].append(correction)
        self.save_feedback()
        self.logger.info("Recorded correction for query: %s", query[:50])
    
    def record_positive_feedback(self, query: str, answer: str, retrieved_chunks: List[Dict]):
        feedback = {
            "timestamp": time.time(),
            "query": query,
            "answer": answer,
            "retrieved_chunk_ids": [ch.get("_index_id") for ch in retrieved_chunks],
        }
        self.feedback_data["positive_feedback"].append(feedback)
        self.save_feedback()
        
        query_key = self._extract_query_pattern(query)
        chunk_ids = [ch.get("_index_id") for ch in retrieved_chunks]
        if query_key not in self.feedback_data["query_patterns"]:
            self.feedback_data["query_patterns"][query_key] = {"preferred_chunks": [], "count": 0}
        self.feedback_data["query_patterns"][query_key]["preferred_chunks"].extend(chunk_ids)
        self.feedback_data["query_patterns"][query_key]["count"] += 1
        self.save_feedback()
    
    def record_negative_feedback(self, query: str, answer: str, retrieved_chunks: List[Dict], reason: Optional[str] = None):
        feedback = {
            "timestamp": time.time(),
            "query": query,
            "answer": answer,
            "retrieved_chunk_ids": [ch.get("_index_id") for ch in retrieved_chunks],
            "reason": reason,
        }
        self.feedback_data["negative_feedback"].append(feedback)
        self.save_feedback()
    
    def get_preferred_chunks_for_query(self, query: str) -> List[int]:
        query_key = self._extract_query_pattern(query)
        pattern_data = self.feedback_data["query_patterns"].get(query_key, {})
        preferred = pattern_data.get("preferred_chunks", [])
        chunk_counts = Counter(preferred)
        return [chunk_id for chunk_id, _ in chunk_counts.most_common(5)]
    
    def _extract_query_pattern(self, query: str) -> str:
        words = query.lower().split()
        stop_words = {"what", "is", "how", "do", "the", "a", "an", "to", "of", "in", "for", "with"}
        keywords = [w for w in words if w not in stop_words and len(w) > 3]
        return " ".join(sorted(set(keywords))[:5])
    
    def boost_chunk_scores(self, hits: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        preferred_ids = set(self.get_preferred_chunks_for_query(query))
        if not preferred_ids:
            return hits
        
        for hit in hits:
            if hit.get("_index_id") in preferred_ids:
                hit["_score"] = hit.get("_score", 0.0) * 1.2
                hit["_feedback_boost"] = True
        
        hits.sort(key=lambda x: x.get("_score", 0.0), reverse=True)
        return hits


class QueryRewriterAgent:
    """Rewrites queries for better retrieval."""
    
    def __init__(self, config: AppConfig):
        self.cfg = config
        self.logger = logging.getLogger("QueryRewriterAgent")
        if not self.cfg.google_ai_api_key:
            raise ValueError("GOOGLE_AI_API_KEY required for query rewriting")
        self.client = genai.Client(api_key=self.cfg.google_ai_api_key)
        self.model = self.cfg.text_model
    
    @retry(Exception, tries=3, delay=1.0, backoff=2.0, logger=logger)
    def rewrite_query(self, query: str, context: Optional[str] = None) -> Dict[str, Any]:
        context_part = f'CONTEXT (from previous retrieval):\n{context}\n' if context else ''
        prompt = f"""You are a query rewriting agent specialized in improving code/documentation search queries.

ORIGINAL QUERY:
{query}

{context_part}

INSTRUCTIONS:
1. Expand abbreviations and clarify ambiguous terms
2. Add relevant technical keywords that might appear in code/docs
3. Break compound questions into clearer sub-questions if needed
4. Preserve the original intent
5. Make the query more specific for code/documentation search

Return ONLY a JSON object with:
{{
  "rewritten_query": "<improved query>",
  "reasoning": "<why these changes improve retrieval>",
  "key_terms": ["<term1>", "<term2>", ...]
}}

Output ONLY the JSON, no markdown or explanation."""

        config = GenerateContentConfig(temperature=0.3, max_output_tokens=256, top_p=0.95)
        response = self.client.models.generate_content(model=self.model, contents=[prompt], config=config)
        
        if not response.candidates or not response.candidates[0].content:
            raise RuntimeError("Query rewriter returned no response")
        
        result_text = response.candidates[0].content.parts[0].text.strip()
        
        try:
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()
            
            result = json.loads(result_text)
            result["original_query"] = query
            self.logger.info("Rewritten query: '%s' -> '%s'", query, result.get("rewritten_query", query))
            return result
        except json.JSONDecodeError:
            self.logger.warning("Failed to parse query rewrite JSON, using original query")
            return {
                "original_query": query,
                "rewritten_query": query,
                "reasoning": "Failed to parse rewrite response",
                "key_terms": query.split(),
            }


class RetrievalAgent:
    """Specialized agent for retrieval stage."""
    
    def __init__(self, config: AppConfig, indexer: FaissIndexer, metadata: List[Dict], 
                 embedder: VertexEmbedder, feedback_loop: Optional[FeedbackLoop] = None):
        self.cfg = config
        self.indexer = indexer
        self.metadata = metadata
        self.embedder = embedder
        self.feedback_loop = feedback_loop
        self.logger = logging.getLogger("RetrievalAgent")
    
    def retrieve(self, query: str, top_k: Optional[int] = None, use_feedback: bool = True) -> List[Dict[str, Any]]:
        top_k = top_k or self.cfg.top_k
        self.logger.info("[RetrievalAgent] Embedding query for retrieval...")
        qv = self.embedder.embed_texts([query])[0]
        idxs, scores = self.indexer.search(qv, top_k=top_k)
        
        hits = []
        for idx, score in zip(idxs, scores):
            meta = self.metadata[idx].copy()
            meta["_index_id"] = idx
            meta["_score"] = float(score)
            hits.append(meta)
        
        if use_feedback and self.feedback_loop:
            hits = self.feedback_loop.boost_chunk_scores(hits, query)
        
        self.logger.info("[RetrievalAgent] Retrieved %d chunks", len(hits))
        return hits


class ContextComposerAgent:
    """Specialized agent for context assembly stage."""
    
    def __init__(self, config: AppConfig, retriever: Retriever):
        self.cfg = config
        self.retriever = retriever
        self.logger = logging.getLogger("ContextComposerAgent")
    
    def compose_context(self, hits: List[Dict[str, Any]], summaries: Dict[int, str], 
                       use_summaries: bool = True) -> Dict[str, Any]:
        compressed = []
        for h in hits:
            idx = h["_index_id"]
            summary = summaries.get(idx, "")
            meta = {
                "_index_id": idx,
                "score": h.get("_score", 0.0),
                "path": h["path"],
                "chunk_idx": h["chunk_idx"],
                "summary": summary,
            }
            compressed.append(meta)
        
        expand_local, expanded_texts = self.retriever.heuristic_expand(hits, fraction=self.cfg.expand_fraction)
        
        expanded_full = []
        for local_idx in sorted(list(expand_local)):
            absolute_idx = hits[local_idx]["_index_id"]
            expanded_full.append(self.retriever.metadata[absolute_idx]["text"])
        
        return {
            "compressed": compressed,
            "expanded_full": expanded_full,
            "expanded_indices": sorted(list(expand_local)),
        }


class AnswerGeneratorAgent:
    """Specialized agent for answer generation stage."""
    
    def __init__(self, config: AppConfig):
        self.cfg = config
        self.logger = logging.getLogger("AnswerGeneratorAgent")
        if not self.cfg.google_ai_api_key:
            raise ValueError("GOOGLE_AI_API_KEY required for answer generation")
        self.client = genai.Client(api_key=self.cfg.google_ai_api_key)
        self.model = self.cfg.text_model
    
    @retry(Exception, tries=3, delay=1.0, backoff=2.0, logger=logger)
    def generate_answer(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        prompt = self._compose_prompt(query, context["compressed"], context["expanded_full"])
        
        config = GenerateContentConfig(temperature=0.0, max_output_tokens=512, top_p=0.95)
        response = self.client.models.generate_content(model=self.model, contents=[prompt], config=config)
        
        if not response.candidates or not response.candidates[0].content:
            raise RuntimeError("Answer generation returned no response")
        
        answer = response.candidates[0].content.parts[0].text.strip()
        citation_count = len(context["expanded_full"])
        confidence = min(0.9, 0.5 + (citation_count / 10) * 0.1)
        
        return {"answer": answer, "confidence": confidence, "prompt": prompt}
    
    def _compose_prompt(self, query: str, compressed: List[Dict[str, Any]], expanded_full_texts: List[str]) -> str:
        comp_lines = []
        for c in compressed:
            comp_lines.append(f"[chunk_id={c['_index_id']} path={c['path']} score={c['score']:.4f}]\n{c['summary']}")
        comp_block = "\n\n".join(comp_lines[:200])
        expanded_block = "\n\n---\n\n".join(expanded_full_texts[:50])
        
        prompt = f"""
You are an assistant answering developer questions by consulting only the evidence provided below.

QUESTION:
{query}

COMPRESSED EVIDENCE (short summaries of retrieved chunks):
{comp_block}

EXPANDED EVIDENCE (selected full chunks; use these in preference if they are relevant):
{expanded_block}

INSTRUCTIONS:
- Answer concisely and only using the evidence above.
- If the evidence does not answer the question, say "I don't know from the repository evidence."
- When citing specifics (function names, file paths, line numbers), include the chunk_id or file path.
- Keep the answer short (max 400 words) and factual.
Answer:
"""
        return prompt.strip()


class IterativeRefinerAgent:
    """Agent that iteratively refines retrieval and answers."""
    
    def __init__(self, config: AppConfig, retrieval_agent: RetrievalAgent,
                 context_composer: ContextComposerAgent, answer_generator: AnswerGeneratorAgent):
        self.cfg = config
        self.retrieval_agent = retrieval_agent
        self.context_composer = context_composer
        self.answer_generator = answer_generator
        self.logger = logging.getLogger("IterativeRefinerAgent")
    
    @retry(Exception, tries=2, delay=0.5, backoff=1.5, logger=logger)
    def _analyze_answer_quality(self, query: str, answer: str, context: Dict[str, Any]) -> Dict[str, Any]:
        if not self.cfg.google_ai_api_key:
            return {"needs_refinement": False, "confidence": 0.5, "reasoning": "API key missing"}
        
        client = genai.Client(api_key=self.cfg.google_ai_api_key)
        prompt = f"""You are an answer quality analyzer for RAG systems.

QUERY:
{query}

ANSWER:
{answer}

CONTEXT SOURCES: {len(context['compressed'])} chunks retrieved, {len(context['expanded_full'])} expanded

Analyze if the answer is sufficient or if more retrieval is needed.

Return ONLY a JSON object:
{{
  "needs_refinement": <true/false>,
  "confidence": <0.0-1.0>,
  "reasoning": "<why refinement is/isn't needed>",
  "missing_aspects": ["<aspect1>", "<aspect2>"],
  "suggested_query_modifications": "<how to improve query for next iteration>"
}}

Output ONLY the JSON, no markdown."""

        config = GenerateContentConfig(temperature=0.0, max_output_tokens=256, top_p=0.95)
        
        try:
            response = client.models.generate_content(model=self.cfg.text_model, contents=[prompt], config=config)
            if not response.candidates or not response.candidates[0].content:
                return {"needs_refinement": False, "confidence": 0.5, "reasoning": "Analysis failed"}
            
            result_text = response.candidates[0].content.parts[0].text.strip()
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()
            
            return json.loads(result_text)
        except Exception as e:
            self.logger.warning("Answer quality analysis failed: %s", e)
            return {"needs_refinement": False, "confidence": 0.5, "reasoning": str(e)}
    
    def refine_iteratively(self, query: str, initial_top_k: int = 20, 
                          max_iterations: Optional[int] = None,
                          use_summaries: bool = True, summaries_dict: Optional[Dict[int, str]] = None) -> Dict[str, Any]:
        max_iterations = max_iterations or self.cfg.max_iterations
        threshold = self.cfg.iteration_confidence_threshold
        
        all_hits = []
        all_iterations = []
        current_query = query
        
        for iteration in range(max_iterations):
            hits = self.retrieval_agent.retrieve(current_query, top_k=initial_top_k + (iteration * 10))
            all_hits.extend(hits)
            
            seen_ids = set()
            unique_hits = []
            for hit in sorted(all_hits, key=lambda x: x.get("_score", 0.0), reverse=True):
                if hit["_index_id"] not in seen_ids:
                    seen_ids.add(hit["_index_id"])
                    unique_hits.append(hit)
            
            summaries = summaries_dict or {}
            context = self.context_composer.compose_context(unique_hits[:initial_top_k + (iteration * 10)], 
                                                           summaries, use_summaries)
            
            result = self.answer_generator.generate_answer(current_query, context)
            
            if iteration < max_iterations - 1:
                analysis = self._analyze_answer_quality(current_query, result["answer"], context)
                result.update(analysis)
                
                all_iterations.append({
                    "iteration": iteration + 1,
                    "query": current_query,
                    "retrieved_chunks": len(unique_hits),
                    "answer": result["answer"],
                    "confidence": result.get("confidence", 0.5),
                    "needs_refinement": result.get("needs_refinement", False),
                })
                
                if result.get("confidence", 0.0) >= threshold and not result.get("needs_refinement", False):
                    break
                
                if result.get("needs_refinement", False) and result.get("suggested_query_modifications"):
                    current_query = f"{current_query} {result['suggested_query_modifications']}"
            else:
                all_iterations.append({
                    "iteration": iteration + 1,
                    "query": current_query,
                    "retrieved_chunks": len(unique_hits),
                    "answer": result["answer"],
                    "confidence": result.get("confidence", 0.5),
                })
        
        return {
            "answer": result["answer"],
            "confidence": result.get("confidence", 0.5),
            "prompt": result.get("prompt", ""),
            "retrieved": unique_hits[:initial_top_k + max_iterations * 10],
            "iterations": all_iterations,
            "total_iterations": len(all_iterations),
        }


# ============================================================================
# SECTION 5: RAG PIPELINE ORCHESTRATOR
# ============================================================================

class RAGPipeline:
    """Main RAG pipeline orchestrator."""
    
    def __init__(self, config: AppConfig):
        self.cfg = config
        self.cfg.ensure_dirs()
        self.repo_loader = RepoLoader(config)
        self.chunker = Chunker(config)
        self.embedder = VertexEmbedder(config)
        self.indexer = FaissIndexer(config)
        self.summarizer = VertexSummarizer(config)
        self.projection_model = ProjectionMLP(self.cfg.embed_dim, self.cfg.decoder_emb_dim)
        
        self.metadata: List[Dict[str, Any]] = []
        self.raw_embeddings: Optional["np.ndarray"] = None
        self.projected_vectors: Optional["np.ndarray"] = None
        self.chunk_summaries: Dict[int, str] = {}
        
        self.logger = logging.getLogger("RAGPipeline")
        
        # Agentic RAG enhancements
        self.feedback_loop: Optional[FeedbackLoop] = None
        if self.cfg.feedback_enabled:
            self.feedback_loop = FeedbackLoop(config)
        
        self.query_rewriter: Optional[QueryRewriterAgent] = None
        if self.cfg.query_rewrite_enabled:
            self.query_rewriter = QueryRewriterAgent(config)
        
        self.retrieval_agent: Optional[RetrievalAgent] = None
        self.context_composer: Optional[ContextComposerAgent] = None
        self.answer_generator: Optional[AnswerGeneratorAgent] = None
        self.iterative_refiner: Optional[IterativeRefinerAgent] = None
        
        if self.cfg.iterative_refinement_enabled:
            self._initialize_multi_agents()

    def ingest_repo(self, git_url: str, force_clone: bool = False, reindex: bool = False):
        clone_dir = self.repo_loader.clone(git_url, dest=self.cfg.clone_dir, force=force_clone)
        files = self.repo_loader.collect_text_files(clone_dir)
        chunks_meta = self.chunker.chunk_files(files)
        self.metadata = chunks_meta
        self.logger.info("Total chunks to embed: %d", len(self.metadata))
        
        texts = [m["text"] for m in self.metadata]
        vecs = self.embedder.embed_texts(texts, batch_size=64)
        import numpy as np
        arr = np.array(vecs, dtype="float32")
        np.save(self.cfg.raw_emb_path, arr)
        self.raw_embeddings = arr
        
        idx = self.indexer.build(arr, metric="ip")
        self.indexer.save(self.cfg.faiss_index_path)
        
        with open(self.cfg.metadata_path, "wb") as f:
            pickle.dump(self.metadata, f)
        
        index_metadata = {
            "indexed_source": "github_repo",
            "repo_url": git_url,
            "indexed_folder_path": os.path.abspath(clone_dir),
            "indexed_at": datetime.datetime.now().isoformat(),
            "num_chunks": len(self.metadata)
        }
        with open(self.cfg.index_metadata_path, "w") as f:
            json.dump(index_metadata, f, indent=2)
        
        self.logger.info("Ingest complete and persisted (index + metadata).")
        return True

    def ingest_folder(self, folder_path: str, reindex: bool = False):
        if not os.path.exists(folder_path):
            raise ValueError(f"Folder path does not exist: {folder_path}")
        if not os.path.isdir(folder_path):
            raise ValueError(f"Path is not a directory: {folder_path}")
        
        self.logger.info("Collecting files from folder: %s", folder_path)
        files = self.repo_loader.collect_text_files(folder_path)
        
        if not files:
            raise ValueError(f"No text files found in folder: {folder_path}")
        
        chunks_meta = self.chunker.chunk_files(files)
        self.metadata = chunks_meta
        self.logger.info("Total chunks to embed: %d", len(self.metadata))
        
        texts = [m["text"] for m in self.metadata]
        vecs = self.embedder.embed_texts(texts, batch_size=64)
        import numpy as np
        arr = np.array(vecs, dtype="float32")
        np.save(self.cfg.raw_emb_path, arr)
        self.raw_embeddings = arr
        
        idx = self.indexer.build(arr, metric="ip")
        self.indexer.save(self.cfg.faiss_index_path)
        
        with open(self.cfg.metadata_path, "wb") as f:
            pickle.dump(self.metadata, f)
        
        index_metadata = {
            "indexed_source": "local_folder",
            "indexed_folder_path": os.path.abspath(folder_path),
            "indexed_at": datetime.datetime.now().isoformat(),
            "num_files": len(files),
            "num_chunks": len(self.metadata)
        }
        with open(self.cfg.index_metadata_path, "w") as f:
            json.dump(index_metadata, f, indent=2)
        
        self.logger.info("Ingest complete: %d files -> %d chunks (index + metadata persisted)", 
                        len(files), len(self.metadata))
        return True

    def load_from_cache(self, expected_folder_path: Optional[str] = None) -> bool:
        if expected_folder_path:
            expected_abs = os.path.abspath(expected_folder_path)
            if not os.path.exists(self.cfg.index_metadata_path):
                self.logger.warning("Cache metadata not found. Expected folder '%s'. Skipping cache.", expected_folder_path)
                return False
            
            try:
                with open(self.cfg.index_metadata_path, "r") as f:
                    index_metadata = json.load(f)
                cached_folder = index_metadata.get("indexed_folder_path", "")
                cached_abs = os.path.abspath(cached_folder) if cached_folder else ""
                
                if cached_abs != expected_abs:
                    self.logger.warning("Cached index is for folder '%s', but expected '%s'. Skipping cache.", cached_folder, expected_folder_path)
                    return False
            except Exception as e:
                self.logger.warning("Failed to read index metadata: %s. Skipping cache.", e)
                return False
        
        if not os.path.exists(self.cfg.metadata_path):
            return False
        if not os.path.exists(self.cfg.raw_emb_path):
            return False
        if not os.path.exists(self.cfg.faiss_index_path):
            return False
        
        with open(self.cfg.metadata_path, "rb") as f:
            self.metadata = pickle.load(f)
        self.logger.info("Loaded metadata (%d chunks)", len(self.metadata))
        
        import numpy as np
        self.raw_embeddings = np.load(self.cfg.raw_emb_path)
        self.logger.info("Loaded raw embeddings shape %s", str(self.raw_embeddings.shape))
        
        try:
            self.indexer.load(self.cfg.faiss_index_path)
        except Exception as e:
            self.logger.warning("FAISS index load failed: %s", e)
            return False
        
        if os.path.exists(self.cfg.summaries_path):
            with open(self.cfg.summaries_path, "rb") as f:
                self.chunk_summaries = pickle.load(f)
            self.logger.info("Loaded %d chunk summaries", len(self.chunk_summaries))
        
        if os.path.exists(self.cfg.projected_vecs_path):
            self.projected_vectors = np.load(self.cfg.projected_vecs_path)
            self.logger.info("Loaded projected vectors shape %s", str(self.projected_vectors.shape))
        
        return True

    def ensure_summaries(self, indices: Optional[List[int]] = None, force: bool = False):
        if indices is None:
            indices = list(range(len(self.metadata)))
        missing = [i for i in indices if i not in self.chunk_summaries or force]
        self.logger.info("Summaries to compute: %d", len(missing))
        for i in tqdm(missing):
            try:
                txt = self.metadata[i]["text"]
                s = self.summarizer.summarize(txt)
                self.chunk_summaries[i] = s.strip()
            except Exception as e:
                self.logger.warning("Failed to summarize chunk %d: %s", i, e)
                fallback = " ".join(self.metadata[i]["text"].split()[:64])
                self.chunk_summaries[i] = fallback
        with open(self.cfg.summaries_path, "wb") as f:
            pickle.dump(self.chunk_summaries, f)
        self.logger.info("Saved summaries (%d)", len(self.chunk_summaries))
        return True

    def ensure_projected_vectors(self, batch_size: int = 128, force: bool = False):
        import numpy as np
        if self.projected_vectors is not None and not force:
            return self.projected_vectors
        if self.raw_embeddings is None:
            if os.path.exists(self.cfg.raw_emb_path):
                self.raw_embeddings = np.load(self.cfg.raw_emb_path)
            else:
                raise RuntimeError("Raw embeddings not present; run ingest_repo() first.")
        self.projection_model.eval()
        with torch.no_grad():
            all_proj = []
            for i in range(0, self.raw_embeddings.shape[0], batch_size):
                batch = torch.from_numpy(self.raw_embeddings[i:i+batch_size]).float()
                proj = self.projection_model(batch).numpy()
                all_proj.append(proj)
            proj_arr = np.vstack(all_proj).astype("float32")
            self.projected_vectors = proj_arr
            np.save(self.cfg.projected_vecs_path, proj_arr)
            self.logger.info("Saved projected vectors shape %s", str(proj_arr.shape))
            return proj_arr

    def query(self, query_text: str, top_k: Optional[int] = None, use_summaries: bool = True) -> Dict[str, Any]:
        top_k = top_k or self.cfg.top_k
        retr = Retriever(self.cfg, self.indexer, self.metadata, projected_vectors=self.projected_vectors)
        hits = retr.retrieve(query_text, embedder=self.embedder, top_k=top_k)
        hit_indices = [h["_index_id"] for h in hits]
        if use_summaries:
            self.ensure_summaries(indices=hit_indices)
        compressed = []
        for h in hits:
            idx = h["_index_id"]
            summary = self.chunk_summaries.get(idx, "")
            meta = {"_index_id": idx, "score": h.get("_score", 0.0), "path": h["path"], "chunk_idx": h["chunk_idx"], "summary": summary}
            compressed.append(meta)
        expand_local, expanded_texts = retr.heuristic_expand(hits, fraction=self.cfg.expand_fraction)
        expanded_full = []
        for local_idx in sorted(list(expand_local)):
            absolute_idx = hits[local_idx]["_index_id"]
            expanded_full.append(self.metadata[absolute_idx]["text"])
        prompt = self.compose_prompt(query_text, compressed, expanded_full)
        final_answer = self.vertex_generate(prompt)
        return {
            "answer": final_answer,
            "prompt": prompt,
            "retrieved": hits,
            "compressed": compressed,
            "expanded_indices_local": sorted(list(expand_local))
        }

    def compose_prompt(self, query: str, compressed: List[Dict[str, Any]], expanded_full_texts: List[str]) -> str:
        comp_lines = []
        for c in compressed:
            comp_lines.append(f"[chunk_id={c['_index_id']} path={c['path']} score={c['score']:.4f}]\n{c['summary']}")
        comp_block = "\n\n".join(comp_lines[:200])
        expanded_block = "\n\n---\n\n".join(expanded_full_texts[:50])
        prompt = f"""
You are an assistant answering developer questions by consulting only the evidence provided below.

QUESTION:
{query}

COMPRESSED EVIDENCE (short summaries of retrieved chunks):
{comp_block}

EXPANDED EVIDENCE (selected full chunks; use these in preference if they are relevant):
{expanded_block}

INSTRUCTIONS:
- Answer concisely and only using the evidence above.
- If the evidence does not answer the question, say "I don't know from the repository evidence."
- When citing specifics (function names, file paths, line numbers), include the chunk_id or file path.
- Keep the answer short (max 400 words) and factual.
Answer:
"""
        return prompt.strip()

    @retry(Exception, tries=3, delay=1.0, backoff=2.0, logger=logger)
    def vertex_generate(self, prompt: str, max_output_tokens: int = 512, temperature: float = 0.0) -> str:
        if not self.cfg.google_ai_api_key:
            raise ValueError("GOOGLE_AI_API_KEY is required for text generation")
        client = genai.Client(api_key=self.cfg.google_ai_api_key)
        config = GenerateContentConfig(temperature=temperature, max_output_tokens=max_output_tokens, top_p=0.95)
        response = client.models.generate_content(model=self.cfg.text_model, contents=[prompt], config=config)
        if not response.candidates or not response.candidates[0].content:
            raise RuntimeError("Gemini generation returned no predictions")
        return response.candidates[0].content.parts[0].text.strip()
    
    def _initialize_multi_agents(self):
        if not self.feedback_loop:
            self.feedback_loop = FeedbackLoop(self.cfg)
        retr = Retriever(self.cfg, self.indexer, self.metadata, self.projected_vectors)
        self.retrieval_agent = RetrievalAgent(self.cfg, self.indexer, self.metadata, self.embedder, self.feedback_loop)
        self.context_composer = ContextComposerAgent(self.cfg, retr)
        self.answer_generator = AnswerGeneratorAgent(self.cfg)
        if self.cfg.iterative_refinement_enabled:
            self.iterative_refiner = IterativeRefinerAgent(self.cfg, self.retrieval_agent, self.context_composer, self.answer_generator)
        self.logger.info("Initialized multi-agent system")
    
    def query_with_rewrite(self, query_text: str, top_k: Optional[int] = None, use_summaries: bool = True) -> Dict[str, Any]:
        if not self.query_rewriter:
            return self.query(query_text, top_k, use_summaries)
        rewrite_result = self.query_rewriter.rewrite_query(query_text)
        rewritten_query = rewrite_result.get("rewritten_query", query_text)
        result = self.query(rewritten_query, top_k, use_summaries)
        result["query_rewrite"] = rewrite_result
        result["original_query"] = query_text
        result["used_query"] = rewritten_query
        return result
    
    def query_iterative(self, query_text: str, top_k: Optional[int] = None, use_summaries: bool = True, 
                       max_iterations: Optional[int] = None) -> Dict[str, Any]:
        if not self.iterative_refiner:
            self._initialize_multi_agents()
            if not self.iterative_refiner:
                self.logger.warning("Iterative refinement not available, using regular query")
                return self.query(query_text, top_k, use_summaries)
        
        if self.query_rewriter:
            rewrite_result = self.query_rewriter.rewrite_query(query_text)
            query_text = rewrite_result.get("rewritten_query", query_text)
        
        initial_top_k = top_k or self.cfg.top_k
        result = self.iterative_refiner.refine_iteratively(
            query_text, initial_top_k=initial_top_k, max_iterations=max_iterations,
            use_summaries=use_summaries, summaries_dict=self.chunk_summaries
        )
        
        if use_summaries and result.get("retrieved"):
            hit_indices = [h["_index_id"] for h in result["retrieved"]]
            missing_indices = [i for i in hit_indices if i not in self.chunk_summaries]
            if missing_indices:
                self.ensure_summaries(indices=missing_indices)
            retr = Retriever(self.cfg, self.indexer, self.metadata, self.projected_vectors)
            context = self.context_composer.compose_context(result["retrieved"], self.chunk_summaries, use_summaries)
            result["compressed"] = context["compressed"]
            result["expanded_indices_local"] = context["expanded_indices"]
        
        return result
    
    def record_feedback(self, query: str, answer: str, feedback_type: str, 
                       retrieved_chunks: List[Dict], corrected_answer: Optional[str] = None, notes: Optional[str] = None):
        if not self.feedback_loop:
            self.logger.warning("Feedback loop not enabled")
            return
        if feedback_type == "correction" and corrected_answer:
            self.feedback_loop.record_correction(query, answer, corrected_answer, retrieved_chunks, notes)
        elif feedback_type == "positive":
            self.feedback_loop.record_positive_feedback(query, answer, retrieved_chunks)
        elif feedback_type == "negative":
            self.feedback_loop.record_negative_feedback(query, answer, retrieved_chunks, notes)
        else:
            self.logger.warning("Unknown feedback type: %s", feedback_type)


# ============================================================================
# SECTION 6: RAG TOOL WRAPPER
# ============================================================================

class RAGTool:
    """Wrapper for RAG query operations."""
    
    def __init__(self, config: AppConfig, rag_pipeline):
        self.cfg = config
        self.rag_pipeline = rag_pipeline
        self.logger = logging.getLogger("RAGTool")
    
    def query(self, query_text: str, top_k: Optional[int] = None, use_iterative: bool = False) -> Dict[str, Any]:
        """Query the RAG system."""
        self.logger.info(f"[RAGTool] Querying: {query_text[:50]}")
        top_k = top_k or self.cfg.top_k
        if use_iterative:
            return self.rag_pipeline.query_iterative(query_text, top_k=top_k)
        else:
            return self.rag_pipeline.query(query_text, top_k=top_k)
    
    def query_multiple(self, queries: list[str], top_k: Optional[int] = None) -> Dict[str, Dict[str, Any]]:
        """Query RAG system for multiple queries."""
        self.logger.info(f"[RAGTool] Querying {len(queries)} queries")
        results = {}
        for query in queries:
            results[query] = self.query(query, top_k=top_k)
        return results


# ============================================================================
# CLI Support (for backward compatibility)
# ============================================================================

def parse_args():
    """Parse command-line arguments."""
    p = argparse.ArgumentParser(description="Production RAG pipeline CLI")
    p.add_argument("--clone-url", type=str, help="GitHub repo URL to clone", required=True)
    p.add_argument("--clone-dir", type=str, help="Local clone directory", default=None)
    p.add_argument("--reindex", action="store_true", help="Force reindex")
    p.add_argument("--query", type=str, help="Query to run", default=None)
    p.add_argument("--top-k", type=int, default=None, help="Top-K retrieval")
    p.add_argument("--force-summarize", action="store_true", help="Force re-summarization")
    p.add_argument("--train-projection", action="store_true", help="Train Projection MLP")
    p.add_argument("--no-summaries", action="store_true", help="Do not use summaries")
    p.add_argument("--force-clone", action="store_true", help="Force reclone")
    p.add_argument("--iterative", action="store_true", help="Use iterative refinement")
    p.add_argument("--no-rewrite", action="store_true", help="Disable query rewriting")
    p.add_argument("--no-feedback", action="store_true", help="Disable feedback loop")
    p.add_argument("--feedback", type=str, choices=["positive", "negative", "correction"], help="Record feedback")
    p.add_argument("--corrected-answer", type=str, help="Corrected answer for feedback")
    return p.parse_args()


def train_projection_demo(pipeline: RAGPipeline, epochs: int = 3, lr: float = 1e-4, batch_size: int = 128):
    """Demo training for projection model."""
    import numpy as np
    if pipeline.raw_embeddings is None:
        if os.path.exists(pipeline.cfg.raw_emb_path):
            pipeline.raw_embeddings = np.load(pipeline.cfg.raw_emb_path)
        else:
            raise RuntimeError("No raw embeddings to train on")
    X = pipeline.raw_embeddings
    device = torch.device("cpu")
    model = pipeline.projection_model.to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    np.random.seed(SEED)
    Y = np.random.randn(X.shape[0], pipeline.cfg.decoder_emb_dim).astype("float32")
    dataset = torch.utils.data.TensorDataset(torch.from_numpy(X).float(), torch.from_numpy(Y).float())
    loader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=True)
    model.train()
    for epoch in range(epochs):
        tot = 0.0
        for xb, yb in loader:
            xb = xb.to(device)
            yb = yb.to(device)
            opt.zero_grad()
            pred = model(xb)
            loss = nn.functional.mse_loss(pred, yb)
            loss.backward()
            opt.step()
            tot += loss.item() * xb.size(0)
        logger.info("Projection training epoch %d loss=%.6f", epoch+1, tot / len(dataset))
    pipeline.ensure_projected_vectors(force=True)
    logger.info("Projection training demo complete.")


def main():
    """Main CLI entry point."""
    args = parse_args()
    cfg = AppConfig()
    if args.clone_dir:
        cfg.clone_dir = args.clone_dir
    cfg.ensure_dirs()

    pipeline = RAGPipeline(cfg)

    if args.reindex:
        pipeline.ingest_repo(args.clone_url, force_clone=args.force_clone, reindex=True)
    else:
        pipeline.load_from_cache()
        if not pipeline.metadata:
            pipeline.ingest_repo(args.clone_url, force_clone=args.force_clone, reindex=True)

    if args.force_summarize:
        pipeline.ensure_summaries(indices=None, force=True)

    if args.train_projection:
        logger.info("Train projection requested — launching demo training routine.")
        train_projection_demo(pipeline)
        logger.info("Projection training complete.")

    if args.query:
        if args.no_rewrite:
            cfg.query_rewrite_enabled = False
        if args.no_feedback:
            cfg.feedback_enabled = False
        
        if args.no_rewrite or args.no_feedback:
            pipeline = RAGPipeline(cfg)
            if args.reindex:
                pipeline.ingest_repo(args.clone_url, force_clone=args.force_clone, reindex=True)
            else:
                pipeline.load_from_cache()
                if not pipeline.metadata:
                    pipeline.ingest_repo(args.clone_url, force_clone=args.force_clone, reindex=True)
        
        if args.iterative:
            res = pipeline.query_iterative(args.query, top_k=args.top_k, use_summaries=(not args.no_summaries))
            print("\n=== ITERATIVE REFINEMENT RESULT ===\n")
            print(f"Total iterations: {res.get('total_iterations', 1)}")
            print(f"Confidence: {res.get('confidence', 0.0):.2f}")
            print(f"\n=== FINAL ANSWER ===\n")
            print(res["answer"])
        else:
            if cfg.query_rewrite_enabled:
                res = pipeline.query_with_rewrite(args.query, top_k=args.top_k, use_summaries=(not args.no_summaries))
                print("\n=== QUERY REWRITE ===\n")
                if res.get("query_rewrite"):
                    rewrite = res["query_rewrite"]
                    print(f"Original: {rewrite.get('original_query')}")
                    print(f"Rewritten: {rewrite.get('rewritten_query')}")
                    print(f"Reasoning: {rewrite.get('reasoning')}")
                    print(f"Key terms: {', '.join(rewrite.get('key_terms', []))}")
                print()
            else:
                res = pipeline.query(args.query, top_k=args.top_k, use_summaries=(not args.no_summaries))
            
            print("\n=== ANSWER ===\n")
            print(res["answer"])
            print("\n=== METADATA ===")
            print(f"Retrieved: {len(res['retrieved'])} chunks. Expanded local indices: {res['expanded_indices_local']}")
        
        if args.feedback and res.get("retrieved"):
            feedback_type = args.feedback
            corrected = args.corrected_answer if feedback_type == "correction" else None
            pipeline.record_feedback(args.query, res.get("answer", ""), feedback_type, res.get("retrieved", []), corrected)
            print(f"\n=== FEEDBACK RECORDED ===\n")
            print(f"Feedback type: {feedback_type}")


if __name__ == "__main__":
    main()

