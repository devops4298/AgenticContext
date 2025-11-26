#!/usr/bin/env python3
"""
rag_agent.py — RAG Agent for querying RAG system and building precise context.

Responsibilities:
- Query RAG system for domain knowledge
- Build context for all test steps
- Return precise, relevant context
"""

import sys
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.rag import AppConfig


class RagAgent:
    """Sub-agent responsible for querying RAG system and building precise context."""
    
    def __init__(self, config: AppConfig, rag_pipeline):
        self.cfg = config
        self.rag_pipeline = rag_pipeline
        self.logger = logging.getLogger("RagAgent")
    
    def get_context_for_steps(self, user_request: str, steps: List[str], 
                             formatted_request: Optional[str] = None) -> Dict[str, Any]:
        """
        Query RAG system for all steps in one go and build precise context for each step.
        
        Args:
            user_request: Original user request (kept for reference)
            steps: List of steps extracted from user request (rewritten/formatted)
            formatted_request: Optional cleaned-up version of user request (preferred for RAG query)
        
        Returns:
            Dict with context for each step and overall context
        """
        self.logger.info(f"[RagAgent] Getting context for {len(steps)} steps")
        
        # Use formatted_request if available (cleaner, more structured), otherwise fall back to user_request
        overall_query = formatted_request if formatted_request else user_request
        self.logger.info(f"[RagAgent] Querying RAG for overall context using: {overall_query[:100]}...")
        
        # Query RAG for the overall request using formatted/cleaned version
        overall_result = self.rag_pipeline.query(overall_query, top_k=40)
        
        # Query RAG for each step to get step-specific context
        step_contexts = {}
        for i, step in enumerate(steps, 1):
            step_result = self.rag_pipeline.query(step, top_k=20)
            step_contexts[f"step_{i}"] = {
                "step": step,
                "context": step_result,
                "retrieved_chunks": step_result.get("retrieved", []),  # Store actual chunks, not just count
                "retrieved_chunks_count": len(step_result.get("retrieved", [])),
                "answer": step_result.get("answer", "")
            }
        
        return {
            "overall_context": overall_result,
            "step_contexts": step_contexts,
            "steps": steps,
            "user_request": user_request
        }

