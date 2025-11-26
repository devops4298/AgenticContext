#!/usr/bin/env python3
"""
rag_tool.py — RAG query interface wrapper.

Provides a clean interface for querying the RAG system.
"""

import sys
import logging
from pathlib import Path
from typing import Dict, Any, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rag import AppConfig


class RAGTool:
    """Wrapper for RAG query operations."""
    
    def __init__(self, config: AppConfig, rag_pipeline):
        self.cfg = config
        self.rag_pipeline = rag_pipeline
        self.logger = logging.getLogger("RAGTool")
    
    def query(self, query_text: str, top_k: Optional[int] = None, 
             use_iterative: bool = False) -> Dict[str, Any]:
        """
        Query the RAG system.
        
        Args:
            query_text: Query string
            top_k: Number of results to return
            use_iterative: Whether to use iterative refinement
        
        Returns:
            RAG query result
        """
        self.logger.info(f"[RAGTool] Querying: {query_text[:50]}")
        
        top_k = top_k or self.cfg.top_k
        
        if use_iterative:
            return self.rag_pipeline.query_iterative(query_text, top_k=top_k)
        else:
            return self.rag_pipeline.query(query_text, top_k=top_k)
    
    def query_multiple(self, queries: list[str], top_k: Optional[int] = None) -> Dict[str, Dict[str, Any]]:
        """
        Query RAG system for multiple queries.
        
        Args:
            queries: List of query strings
            top_k: Number of results per query
        
        Returns:
            Dict mapping query to result
        """
        self.logger.info(f"[RAGTool] Querying {len(queries)} queries")
        
        results = {}
        for query in queries:
            results[query] = self.query(query, top_k=top_k)
        
        return results

