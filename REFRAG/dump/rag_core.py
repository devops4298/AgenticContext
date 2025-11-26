#!/usr/bin/env python3
"""
rag_core.py — Core RAG components for indexing and retrieval

This module contains the foundational RAG components:
- RepoLoader: Clone and collect text files
- Chunker: Split text into overlapping chunks
- VertexEmbedder: Embed text using Gemini API
- FaissIndexer: Build and search FAISS index
- VertexSummarizer: Create dense summaries
- ProjectionMLP: REFRAG-style projection network
- Retriever: Retrieve and expand chunks
"""

from __future__ import annotations
import os
import sys
import logging
import pathlib
import shutil
from typing import List, Dict, Tuple, Any, Optional, Iterable
from functools import wraps
from time import sleep

# Fix OpenMP conflict
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

# Third-party libraries
try:
    import faiss
except Exception as e:
    raise RuntimeError("faiss is required. Install with `pip install faiss-cpu`") from e

try:
    import torch
    import torch.nn as nn
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

# Import config and retry from shared utilities
from rag_config import AppConfig
from rag_utils import retry, logger


# -----------------------
# RepoLoader: clone and collect textual files
# -----------------------
class RepoLoader:
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
        """
        Collects text files from a directory tree, skipping binary files.
        Recursively walks through all subdirectories.
        """
        if extensions is None:
            extensions = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".rst", ".ini", ".cfg", ".toml", 
                         ".Dockerfile", ".mdown", ".js", ".ts", ".jsx", ".tsx", ".css", ".html", ".xml", 
                         ".csv", ".sql", ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmake", ".make", ".go",
                         ".rs", ".java", ".cpp", ".c", ".h", ".hpp", ".cc", ".cxx", ".cs", ".php", ".rb",
                         ".swift", ".kt", ".scala", ".lua", ".r", ".m", ".mm", ".dart", ".vue", ".svelte"}
        
        # Common binary file extensions to skip
        binary_extensions = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp", 
                           ".pdf", ".zip", ".tar", ".gz", ".rar", ".7z", ".exe", ".dll", ".so", ".dylib",
                           ".bin", ".dat", ".db", ".sqlite", ".sqlite3", ".mp3", ".mp4", ".avi", ".mov",
                           ".wav", ".flac", ".ogg", ".woff", ".woff2", ".ttf", ".eot", ".otf", ".class",
                           ".pyc", ".pyo", ".pyd", ".o", ".obj", ".a", ".lib", ".dylib", ".egg", ".whl"}
        
        collected: Dict[str, str] = {}
        for dirpath, dirs, files in os.walk(root):
            # skip heavy or binary directories
            if any(x in dirpath for x in ["/.git", "/node_modules", "/venv", "/.venv", "/dist", "/build", 
                                         "/__pycache__", "/.pytest_cache", "/.mypy_cache", "/.idea", "/.vscode",
                                         "/target", "/bin", "/obj", "/.gradle", "/.cache"]):
                continue
            for fname in files:
                path = os.path.join(dirpath, fname)
                ext = pathlib.Path(fname).suffix.lower()
                
                # Skip binary files by extension
                if ext in binary_extensions:
                    self.logger.debug("Skipping binary file: %s", path)
                    continue
                
                # Include text files by extension or common names
                if ext in extensions or fname.lower() in {"readme", "license", "makefile", "dockerfile", 
                                                          "docker-compose", ".gitignore", ".env.example"}:
                    try:
                        # Try to detect binary files by reading first chunk
                        with open(path, "rb") as f:
                            chunk = f.read(8192)  # Read first 8KB
                            # Check for null bytes (common in binary files)
                            if b'\x00' in chunk:
                                self.logger.debug("Skipping binary file (null bytes detected): %s", path)
                                continue
                        
                        # Try to read as text
                        with open(path, "r", encoding="utf-8", errors="ignore") as f:
                            text = f.read()
                            if text and text.strip():
                                collected[path] = text
                    except UnicodeDecodeError:
                        self.logger.debug("Skipping binary file (encoding error): %s", path)
                        continue
                    except Exception as e:
                        self.logger.debug("Skipping %s: %s", path, e)
                        continue
        self.logger.info("Collected %d text files from %s", len(collected), root)
        return collected


# -----------------------
# Chunker: split text into overlapping chunks
# -----------------------
class Chunker:
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
        """
        Returns list of metadata dicts: {"path", "chunk_idx", "text"}
        """
        out = []
        for path, txt in files.items():
            chunks = self.chunk_text(txt)
            for idx, ch in enumerate(chunks):
                out.append({"path": path, "chunk_idx": idx, "text": ch})
        return out


# -----------------------
# GeminiEmbedder: call Gemini embeddings API with API key
# -----------------------
class VertexEmbedder:
    def __init__(self, config: AppConfig):
        self.cfg = config
        self.logger = logging.getLogger("GeminiEmbedder")
        # Initialize Gemini API client with API key
        if not self.cfg.google_ai_api_key:
            raise ValueError(
                "GOOGLE_AI_API_KEY environment variable is required. "
                "Please set it in your .env file or environment. "
                "Example: GOOGLE_AI_API_KEY=your-api-key"
            )
        self.client = genai.Client(api_key=self.cfg.google_ai_api_key)
        # Cache for query embeddings (to avoid re-embedding identical queries)
        self._query_cache: Dict[str, List[float]] = {}

    @retry(Exception, tries=4, delay=1.0, backoff=2.0, logger=logger)
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a batch of texts using Gemini embeddings API.
        Returns list of vectors (python lists).
        """
        model = self.cfg.embed_model
        vectors = []
        
        for text in texts:
            response = self.client.models.embed_content(
                model=model,
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
            vectors.append(list(response.embeddings[0].values))
        
        return vectors

    def embed_texts(self, texts: List[str], batch_size: int = 64, use_cache: bool = True) -> List[List[float]]:
        """
        Public API: embed a list of texts, with batching and normalization.
        
        Args:
            texts: List of texts to embed
            batch_size: Batch size for processing
            use_cache: If True, cache query embeddings (useful for repeated queries)
        """
        # Check cache for single queries (common case)
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
        # Convert to normalized float32 vectors
        import numpy as np
        arr = np.array(out_vectors, dtype="float32")
        norms = np.linalg.norm(arr, axis=1, keepdims=True) + 1e-12
        arr = arr / norms
        result = arr.tolist()
        
        # Cache single query embeddings
        if use_cache and len(texts) == 1:
            self._query_cache[texts[0]] = result[0]
        
        return result


# -----------------------
# FaissIndexer: build, save, load index; search
# -----------------------
class FaissIndexer:
    def __init__(self, config: AppConfig):
        self.cfg = config
        self.index: Optional[faiss.Index] = None
        self.logger = logging.getLogger("FaissIndexer")

    def build(self, vectors: "np.ndarray", metric: str = "ip"):
        """
        Build a FAISS flat index (inner product). Vectors must already be normalized for cosine with IP.
        """
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


# -----------------------
# ProjectionMLP: enc_dim -> dec_emb_dim (REFRAG-style)
# -----------------------
class ProjectionMLP(nn.Module):
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


# -----------------------
# Summarizer: uses Gemini API to produce a short, dense summary for a chunk
# -----------------------
class VertexSummarizer:
    def __init__(self, config: AppConfig, max_tokens: int = 64):
        self.cfg = config
        self.logger = logging.getLogger("GeminiSummarizer")
        if not self.cfg.google_ai_api_key:
            raise ValueError("GOOGLE_AI_API_KEY is required for summarization")
        self.client = genai.Client(api_key=self.cfg.google_ai_api_key)
        self.model = self.cfg.text_model
        self.max_tokens = max_tokens

    @retry(Exception, tries=3, delay=1.0, backoff=2.0, logger=logger)
    def summarize(self, text: str, prompt_prefix: Optional[str] = None) -> str:
        """
        Create a dense (1-2 sentence) summary of `text` suitable for compression.
        Uses Gemini API with the chosen text model.
        """
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


# -----------------------
# Retriever + selective expansion
# -----------------------
class Retriever:
    def __init__(self, config: AppConfig, indexer: FaissIndexer, metadata: List[Dict[str, Any]], projected_vectors: Optional["np.ndarray"] = None):
        self.cfg = config
        self.indexer = indexer
        self.metadata = metadata  # list of {"path","chunk_idx","text"}
        self.projected_vectors = projected_vectors
        self.logger = logging.getLogger("Retriever")

    def retrieve(self, query: str, embedder: VertexEmbedder, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        top_k = top_k or self.cfg.top_k
        self.logger.info("Embedding query for retrieval...")
        qv = embedder.embed_texts([query])[0]  # normalized vector list
        idxs, scores = self.indexer.search(qv, top_k=top_k)
        hits = []
        for idx, score in zip(idxs, scores):
            meta = self.metadata[idx].copy()
            meta["_index_id"] = idx
            meta["_score"] = float(score)
            hits.append(meta)
        return hits

    def heuristic_expand(self, hits: List[Dict[str, Any]], fraction: float = None) -> Tuple[set, List[str]]:
        """
        Heuristic to choose which hits to expand (return set of local hit indices to expand).
        Also returns the expanded texts list.
        Heuristic used: code-like signal + length + score.
        """
        fraction = fraction or self.cfg.expand_fraction
        scores = []
        for i, h in enumerate(hits):
            txt = h["text"]
            s = len(txt.split())
            # add code-like bonus
            if any(keyword in txt for keyword in ("def ", "class ", "import ", "http", "retry", "requests", "axios", "fetch")):
                s += 50
            # incorporate FAISS score (higher is better for IP)
            s += int(h.get("_score", 0) * 10)
            scores.append((i, s))
        N = max(1, int(len(hits) * fraction))
        topk = sorted(scores, key=lambda x: x[1], reverse=True)[:N]
        expand_indices = set(i for i, _ in topk)
        expanded_texts = [hits[i]["text"] for i in sorted(list(expand_indices))]
        return expand_indices, expanded_texts

