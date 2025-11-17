#!/usr/bin/env python3
"""
rag_prod.py — Production-ready RAG pipeline (refactored to use modular components)

This is the main pipeline orchestrator that uses modular components from:
- rag_core.py: Core RAG components
- rag_agents.py: Agentic RAG components
- rag_config.py: Configuration
- rag_utils.py: Utilities

Usage:
    python rag_prod.py --clone-url https://github.com/psf/requests.git --query "How are retries implemented?" --reindex
"""

from __future__ import annotations
import os
import sys
import json
import logging
import pickle
import argparse
import datetime
from typing import List, Dict, Tuple, Any, Optional

# Fix OpenMP conflict
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

# Import modular components
from rag_config import AppConfig, SEED
from rag_utils import retry, logger
from rag_core import (
    RepoLoader, Chunker, VertexEmbedder, FaissIndexer, 
    VertexSummarizer, ProjectionMLP, Retriever
)
from rag_agents import (
    FeedbackLoop, QueryRewriterAgent, RetrievalAgent,
    ContextComposerAgent, AnswerGeneratorAgent, IterativeRefinerAgent
)

try:
    import torch
    import torch.nn as nn
    import torch.utils.data
except Exception as e:
    raise RuntimeError("torch is required. Install with `pip install torch`") from e

try:
    import google.genai as genai
    from google.genai.types import GenerateContentConfig
except Exception as e:
    raise RuntimeError("google-genai is required. Install with `pip install google-genai`") from e

try:
    from tqdm import tqdm
except Exception:
    tqdm = lambda x, **k: x


# -----------------------
# RAGPipeline: orchestrates everything
# -----------------------
class RAGPipeline:
    def __init__(self, config: AppConfig):
        self.cfg = config
        self.cfg.ensure_dirs()
        self.repo_loader = RepoLoader(config)
        self.chunker = Chunker(config)
        self.embedder = VertexEmbedder(config)
        self.indexer = FaissIndexer(config)
        self.summarizer = VertexSummarizer(config)
        self.projection_model = ProjectionMLP(self.cfg.embed_dim, self.cfg.decoder_emb_dim)
        # caches
        self.metadata: List[Dict[str, Any]] = []
        self.raw_embeddings: Optional["np.ndarray"] = None
        self.projected_vectors: Optional["np.ndarray"] = None
        self.chunk_summaries: Dict[int, str] = {}
        
        # Initialize logger early
        self.logger = logging.getLogger("RAGPipeline")
        
        # Agentic RAG enhancements
        self.feedback_loop: Optional[FeedbackLoop] = None
        if self.cfg.feedback_enabled:
            self.feedback_loop = FeedbackLoop(config)
        
        self.query_rewriter: Optional[QueryRewriterAgent] = None
        if self.cfg.query_rewrite_enabled:
            self.query_rewriter = QueryRewriterAgent(config)
        
        # Multi-agent system
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
                self.logger.warning(
                    "Cache metadata not found (old cache format). Expected folder '%s'. Skipping cache.",
                    expected_folder_path
                )
                return False
            
            try:
                with open(self.cfg.index_metadata_path, "r") as f:
                    index_metadata = json.load(f)
                cached_folder = index_metadata.get("indexed_folder_path", "")
                cached_abs = os.path.abspath(cached_folder) if cached_folder else ""
                
                if cached_abs != expected_abs:
                    self.logger.warning(
                        "Cached index is for folder '%s', but expected '%s'. Skipping cache.",
                        cached_folder, expected_folder_path
                    )
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
        config = GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            top_p=0.95,
        )
        response = client.models.generate_content(
            model=self.cfg.text_model,
            contents=[prompt],
            config=config,
        )
        if not response.candidates or not response.candidates[0].content:
            raise RuntimeError("Gemini generation returned no predictions")
        return response.candidates[0].content.parts[0].text.strip()
    
    def _initialize_multi_agents(self):
        if not self.feedback_loop:
            self.feedback_loop = FeedbackLoop(self.cfg)
        retr = Retriever(self.cfg, self.indexer, self.metadata, self.projected_vectors)
        self.retrieval_agent = RetrievalAgent(
            self.cfg, self.indexer, self.metadata, self.embedder, self.feedback_loop
        )
        self.context_composer = ContextComposerAgent(self.cfg, retr)
        self.answer_generator = AnswerGeneratorAgent(self.cfg)
        if self.cfg.iterative_refinement_enabled:
            self.iterative_refiner = IterativeRefinerAgent(
                self.cfg, self.retrieval_agent, self.context_composer, self.answer_generator
            )
        self.logger.info("Initialized multi-agent system")
    
    def query_with_rewrite(self, query_text: str, top_k: Optional[int] = None, 
                          use_summaries: bool = True) -> Dict[str, Any]:
        if not self.query_rewriter:
            return self.query(query_text, top_k, use_summaries)
        rewrite_result = self.query_rewriter.rewrite_query(query_text)
        rewritten_query = rewrite_result.get("rewritten_query", query_text)
        result = self.query(rewritten_query, top_k, use_summaries)
        result["query_rewrite"] = rewrite_result
        result["original_query"] = query_text
        result["used_query"] = rewritten_query
        return result
    
    def query_iterative(self, query_text: str, top_k: Optional[int] = None,
                       use_summaries: bool = True, max_iterations: Optional[int] = None) -> Dict[str, Any]:
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
            query_text, 
            initial_top_k=initial_top_k,
            max_iterations=max_iterations,
            use_summaries=use_summaries,
            summaries_dict=self.chunk_summaries
        )
        
        if use_summaries and result.get("retrieved"):
            hit_indices = [h["_index_id"] for h in result["retrieved"]]
            missing_indices = [i for i in hit_indices if i not in self.chunk_summaries]
            if missing_indices:
                self.ensure_summaries(indices=missing_indices)
            retr = Retriever(self.cfg, self.indexer, self.metadata, self.projected_vectors)
            context = self.context_composer.compose_context(
                result["retrieved"], self.chunk_summaries, use_summaries
            )
            result["compressed"] = context["compressed"]
            result["expanded_indices_local"] = context["expanded_indices"]
        
        return result
    
    def record_feedback(self, query: str, answer: str, feedback_type: str, 
                       retrieved_chunks: List[Dict], corrected_answer: Optional[str] = None,
                       notes: Optional[str] = None):
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


# -----------------------
# CLI and main
# -----------------------
def parse_args():
    p = argparse.ArgumentParser(description="Production RAG pipeline CLI")
    p.add_argument("--clone-url", type=str, help="GitHub repo URL to clone", required=True)
    p.add_argument("--clone-dir", type=str, help="Local clone directory (overrides config)", default=None)
    p.add_argument("--reindex", action="store_true", help="Force reindex / re-ingest repo")
    p.add_argument("--query", type=str, help="Query to run against repo", default=None)
    p.add_argument("--top-k", type=int, default=None, help="Top-K retrieval")
    p.add_argument("--force-summarize", action="store_true", help="Force re-summarization of chunks")
    p.add_argument("--train-projection", action="store_true", help="(Optional) Train Projection MLP locally on reconstruction objective (stub)")
    p.add_argument("--no-summaries", action="store_true", help="Do not use summaries (use full text retrieval)")
    p.add_argument("--force-clone", action="store_true", help="Force reclone of repo")
    p.add_argument("--iterative", action="store_true", help="Use iterative refinement (retrieve → analyze → retrieve more)")
    p.add_argument("--no-rewrite", action="store_true", help="Disable query rewriting")
    p.add_argument("--no-feedback", action="store_true", help="Disable feedback loop")
    p.add_argument("--feedback", type=str, choices=["positive", "negative", "correction"], 
                   help="Record feedback (requires --query)")
    p.add_argument("--corrected-answer", type=str, help="Corrected answer for feedback (use with --feedback correction)")
    return p.parse_args()


def train_projection_demo(pipeline: RAGPipeline, epochs: int = 3, lr: float = 1e-4, batch_size: int = 128):
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
    logger.info("Projection training demo complete (note: this was a placeholder loss).")


def main():
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
        logger.info("Train projection requested — launching a short demo training routine.")
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
            print(f"\n=== ITERATIONS ===")
            for it in res.get("iterations", []):
                print(f"\nIteration {it['iteration']}:")
                print(f"  Query: {it['query']}")
                print(f"  Retrieved: {it['retrieved_chunks']} chunks")
                print(f"  Confidence: {it.get('confidence', 0.0):.2f}")
                if it.get('needs_refinement'):
                    print(f"  Needs refinement: Yes")
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
            print(f"\nAPI Calls:")
            print(f"  - Query embedding: 1 call (text-embedding-004)")
            if cfg.query_rewrite_enabled:
                print(f"  - Query rewriting: 1 call ({cfg.text_model})")
            print(f"  - Answer generation: 1 call ({cfg.text_model})")
            print(f"  - Summaries: {'Cached' if not args.force_summarize else 'Generated on-demand'}")
        
        if args.feedback and res.get("retrieved"):
            feedback_type = args.feedback
            corrected = args.corrected_answer if feedback_type == "correction" else None
            pipeline.record_feedback(
                args.query, res.get("answer", ""), feedback_type,
                res.get("retrieved", []), corrected
            )
            print(f"\n=== FEEDBACK RECORDED ===\n")
            print(f"Feedback type: {feedback_type}")
            if feedback_type == "correction":
                print(f"Correction saved for future learning")
            elif feedback_type == "positive":
                print(f"Positive feedback recorded - preferred chunks saved")
            elif feedback_type == "negative":
                print(f"Negative feedback recorded - will help improve future queries")


if __name__ == "__main__":
    main()
