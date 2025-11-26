#!/usr/bin/env python3
"""
rag_agents.py — Agentic RAG components

This module contains specialized agents for advanced RAG functionality:
- FeedbackLoop: Learn from user corrections
- QueryRewriterAgent: Expand/clarify queries before retrieval
- RetrievalAgent: Specialized retrieval with feedback
- ContextComposerAgent: Compose context from chunks
- AnswerGeneratorAgent: Generate answers from context
- IterativeRefinerAgent: Iteratively refine retrieval and answers
"""

from __future__ import annotations
import os
import json
import time
import logging
from typing import List, Dict, Tuple, Any, Optional
from collections import Counter

try:
    import google.genai as genai
    from google.genai.types import GenerateContentConfig
except Exception as e:
    raise RuntimeError("google-genai is required. Install with `pip install google-genai`") from e

from rag_config import AppConfig
from rag_core import VertexEmbedder, FaissIndexer, Retriever
from rag_utils import retry, logger


# -----------------------
# Feedback Loop System: Learn from user corrections
# -----------------------
class FeedbackLoop:
    """Stores and learns from user feedback to improve retrieval and generation."""
    
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
        """Load feedback history from disk."""
        if os.path.exists(self.feedback_path):
            try:
                with open(self.feedback_path, "r") as f:
                    self.feedback_data = json.load(f)
                self.logger.info("Loaded %d feedback entries", len(self.feedback_data.get("corrections", [])))
            except Exception as e:
                self.logger.warning("Failed to load feedback: %s", e)
    
    def save_feedback(self):
        """Save feedback history to disk."""
        try:
            with open(self.feedback_path, "w") as f:
                json.dump(self.feedback_data, f, indent=2)
            self.logger.info("Saved feedback to %s", self.feedback_path)
        except Exception as e:
            self.logger.error("Failed to save feedback: %s", e)
    
    def record_correction(self, query: str, original_answer: str, corrected_answer: str, 
                         retrieved_chunks: List[Dict], user_notes: Optional[str] = None):
        """Record a user correction to learn from."""
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
        """Record positive feedback (thumbs up)."""
        feedback = {
            "timestamp": time.time(),
            "query": query,
            "answer": answer,
            "retrieved_chunk_ids": [ch.get("_index_id") for ch in retrieved_chunks],
        }
        self.feedback_data["positive_feedback"].append(feedback)
        self.save_feedback()
        
        # Learn: these chunks worked well for this query pattern
        query_key = self._extract_query_pattern(query)
        chunk_ids = [ch.get("_index_id") for ch in retrieved_chunks]
        if query_key not in self.feedback_data["query_patterns"]:
            self.feedback_data["query_patterns"][query_key] = {"preferred_chunks": [], "count": 0}
        self.feedback_data["query_patterns"][query_key]["preferred_chunks"].extend(chunk_ids)
        self.feedback_data["query_patterns"][query_key]["count"] += 1
        self.save_feedback()
    
    def record_negative_feedback(self, query: str, answer: str, retrieved_chunks: List[Dict], reason: Optional[str] = None):
        """Record negative feedback (thumbs down)."""
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
        """Get chunk IDs that worked well for similar queries."""
        query_key = self._extract_query_pattern(query)
        pattern_data = self.feedback_data["query_patterns"].get(query_key, {})
        preferred = pattern_data.get("preferred_chunks", [])
        chunk_counts = Counter(preferred)
        return [chunk_id for chunk_id, _ in chunk_counts.most_common(5)]
    
    def _extract_query_pattern(self, query: str) -> str:
        """Extract query pattern (keywords) for matching."""
        words = query.lower().split()
        stop_words = {"what", "is", "how", "do", "the", "a", "an", "to", "of", "in", "for", "with"}
        keywords = [w for w in words if w not in stop_words and len(w) > 3]
        return " ".join(sorted(set(keywords))[:5])
    
    def boost_chunk_scores(self, hits: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """Boost scores of chunks that worked well for similar queries."""
        preferred_ids = set(self.get_preferred_chunks_for_query(query))
        if not preferred_ids:
            return hits
        
        for hit in hits:
            if hit.get("_index_id") in preferred_ids:
                hit["_score"] = hit.get("_score", 0.0) * 1.2
                hit["_feedback_boost"] = True
        
        hits.sort(key=lambda x: x.get("_score", 0.0), reverse=True)
        return hits


# -----------------------
# Query Rewriter Agent: Expand/clarify queries before retrieval
# -----------------------
class QueryRewriterAgent:
    """Specialized agent that rewrites queries for better retrieval."""
    
    def __init__(self, config: AppConfig):
        self.cfg = config
        self.logger = logging.getLogger("QueryRewriterAgent")
        if not self.cfg.google_ai_api_key:
            raise ValueError("GOOGLE_AI_API_KEY required for query rewriting")
        self.client = genai.Client(api_key=self.cfg.google_ai_api_key)
        self.model = self.cfg.text_model
    
    @retry(Exception, tries=3, delay=1.0, backoff=2.0, logger=logger)
    def rewrite_query(self, query: str, context: Optional[str] = None) -> Dict[str, Any]:
        """Rewrite query to improve retrieval quality."""
        context_part = f'CONTEXT (from previous retrieval):\n{context}\n' if context else ''
        prompt = f"""You are a query rewriting agent specialized in improving code/documentation search queries.

Your task: Rewrite the user's query to improve retrieval from a code repository.

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

        config = GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=256,
            top_p=0.95,
        )
        
        response = self.client.models.generate_content(
            model=self.model,
            contents=[prompt],
            config=config,
        )
        
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


# -----------------------
# Multi-Agent Orchestrator: Specialized agents per stage
# -----------------------
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
    
    def retrieve(self, query: str, top_k: Optional[int] = None, 
                use_feedback: bool = True) -> List[Dict[str, Any]]:
        """Retrieve chunks with optional feedback-based boosting."""
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
        """Compose compressed and expanded context."""
        self.logger.info("[ContextComposerAgent] Composing context from %d chunks", len(hits))
        
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
        
        expand_local, expanded_texts = self.retriever.heuristic_expand(
            hits, fraction=self.cfg.expand_fraction
        )
        
        expanded_full = []
        for local_idx in sorted(list(expand_local)):
            absolute_idx = hits[local_idx]["_index_id"]
            expanded_full.append(self.retriever.metadata[absolute_idx]["text"])
        
        self.logger.info("[ContextComposerAgent] Expanded %d/%d chunks to full text", 
                        len(expanded_full), len(hits))
        
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
        """Generate answer from query and composed context."""
        self.logger.info("[AnswerGeneratorAgent] Generating answer...")
        
        prompt = self._compose_prompt(query, context["compressed"], context["expanded_full"])
        
        config = GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=512,
            top_p=0.95,
        )
        
        response = self.client.models.generate_content(
            model=self.model,
            contents=[prompt],
            config=config,
        )
        
        if not response.candidates or not response.candidates[0].content:
            raise RuntimeError("Answer generation returned no response")
        
        answer = response.candidates[0].content.parts[0].text.strip()
        
        citation_count = len(context["expanded_full"])
        confidence = min(0.9, 0.5 + (citation_count / 10) * 0.1)
        
        self.logger.info("[AnswerGeneratorAgent] Generated answer (confidence: %.2f)", confidence)
        
        return {
            "answer": answer,
            "confidence": confidence,
            "prompt": prompt,
        }
    
    def _compose_prompt(self, query: str, compressed: List[Dict[str, Any]], 
                       expanded_full_texts: List[str]) -> str:
        """Compose prompt for answer generation."""
        comp_lines = []
        for c in compressed:
            comp_lines.append(
                f"[chunk_id={c['_index_id']} path={c['path']} score={c['score']:.4f}]\n{c['summary']}"
            )
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
        """Analyze if the answer is sufficient or needs more retrieval."""
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

        config = GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=256,
            top_p=0.95,
        )
        
        try:
            response = client.models.generate_content(
                model=self.cfg.text_model,
                contents=[prompt],
                config=config,
            )
            
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
        """Iteratively refine retrieval and answer until confidence threshold is met."""
        max_iterations = max_iterations or self.cfg.max_iterations
        threshold = self.cfg.iteration_confidence_threshold
        
        all_hits = []
        all_iterations = []
        current_query = query
        
        self.logger.info("[IterativeRefinerAgent] Starting iterative refinement (max %d iterations)", 
                        max_iterations)
        
        for iteration in range(max_iterations):
            self.logger.info("[IterativeRefinerAgent] Iteration %d/%d: '%s'", 
                           iteration + 1, max_iterations, current_query)
            
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
                    self.logger.info("[IterativeRefinerAgent] Confidence threshold met (%.2f >= %.2f), stopping", 
                                   result["confidence"], threshold)
                    break
                
                if result.get("needs_refinement", False) and result.get("suggested_query_modifications"):
                    current_query = f"{current_query} {result['suggested_query_modifications']}"
                    self.logger.info("[IterativeRefinerAgent] Refining query: '%s'", current_query)
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

