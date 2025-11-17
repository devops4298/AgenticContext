#!/usr/bin/env python3
"""
orchestrator_agent.py — Root Orchestrator Agent using Google ADK (genai SDK)

This module implements a root orchestrator agent that coordinates the agentic RAG system
and generates Playwright automation scripts based on context understanding.
"""

from __future__ import annotations
import os
import json
import logging
from typing import Dict, Any, Optional, List

try:
    import google.genai as genai
    from google.genai.types import GenerateContentConfig
except Exception as e:
    raise RuntimeError("google-genai is required. Install with `pip install google-genai`") from e

from rag_config import AppConfig
from rag_utils import retry, logger


class OrchestratorAgent:
    """
    Root orchestrator agent that coordinates the entire agentic RAG system.
    Uses Google ADK (genai SDK) with function calling to orchestrate specialized agents.
    """
    
    def __init__(self, config: AppConfig):
        self.cfg = config
        self.logger = logging.getLogger("OrchestratorAgent")
        if not self.cfg.google_ai_api_key:
            raise ValueError("GOOGLE_AI_API_KEY required for orchestrator agent")
        
        self.client = genai.Client(api_key=self.cfg.google_ai_api_key)
        self.model = self.cfg.text_model
        
        # Initialize with system instruction for orchestrator role
        self.system_instruction = """You are a root orchestrator agent for an Agentic RAG system.

Your responsibilities:
1. Understand user queries and context from retrieved documents
2. Coordinate specialized agents (retrieval, context composition, answer generation)
3. Generate Playwright-based automation scripts when users request browser automation
4. Break down complex tasks into steps
5. Provide clear reasoning for your decisions

When generating Playwright scripts:
- Use modern Playwright Python API
- Include proper error handling and wait strategies
- Use selectors that are stable (prefer data-testid, role, text over CSS selectors)
- Include comments explaining each step
- Handle dynamic content loading appropriately
- Include page.wait_for_load_state('networkidle') when needed"""
        
        # Define function tools for agent coordination (simplified for Gemini API)
        # Note: Using prompt-based function calling instead of formal function declarations
        # as Google genai SDK may not support function calling in the same way as OpenAI
        self.function_descriptions = {
            "query_rag_system": "Query the RAG system to retrieve relevant context from indexed documents. Parameters: query (string, required), top_k (integer, optional, default 40), use_iterative_refinement (boolean, optional, default false).",
            "generate_playwright_script": "Generate a Playwright automation script based on user requirements and context. Parameters: user_request (string, required), context (string, optional), script_type (enum: web_scraping|form_filling|navigation|testing|interaction, optional), target_url (string, optional), steps (array of strings, optional).",
            "analyze_context_understanding": "Analyze and understand the context retrieved from documents. Parameters: context (string, required), user_query (string, required), analysis_focus (enum: structure|flow|apis|ui_elements|patterns, optional)."
        }
    
    @retry(Exception, tries=3, delay=1.0, backoff=2.0, logger=logger)
    def orchestrate(self, user_query: str, rag_context: Optional[Dict[str, Any]] = None,
                   rag_pipeline=None) -> Dict[str, Any]:
        """
        Main orchestration method that coordinates the agentic system.
        
        Args:
            user_query: User's query or request
            rag_context: Optional pre-retrieved context from RAG system
            rag_pipeline: Optional RAGPipeline instance for querying
        
        Returns:
            Dict with orchestration result, including any generated scripts
        """
        self.logger.info("[OrchestratorAgent] Orchestrating request: '%s'", user_query[:100])
        
        # Build prompt for orchestrator
        context_part = ""
        if rag_context:
            context_summary = self._summarize_rag_context(rag_context)
            context_part = f"""
CONTEXT FROM RAG SYSTEM:
{context_summary}

"""
        
        prompt = f"""You are the root orchestrator agent for an Agentic RAG system.

USER REQUEST:
{user_query}

{context_part}

TASK:
1. Understand the user's request and the provided context
2. Determine if this requires:
   - Querying the RAG system for more context (use query_rag_system)
   - Generating a Playwright automation script (use generate_playwright_script)
   - Analyzing the context (use analyze_context_understanding)
3. Coordinate appropriate actions

If the user wants browser automation, web scraping, or UI interaction scripts:
- Analyze the context to understand the application structure
- Generate a complete Playwright Python script
- Include imports, proper setup, and clear steps

Think step by step and coordinate the agents appropriately."""

        # Use prompt-based function calling (adapted for Gemini API)
        functions_text = "\n".join([f"- {name}: {desc}" for name, desc in self.function_descriptions.items()])
        enhanced_prompt = f"""{prompt}

AVAILABLE FUNCTIONS:
{functions_text}

INSTRUCTIONS:
- If you need to query the RAG system, respond with: "FUNCTION: query_rag_system(query='...', top_k=40)"
- If you need to generate a Playwright script, respond with: "FUNCTION: generate_playwright_script(user_request='...', script_type='interaction')"
- If you need to analyze context, respond with: "FUNCTION: analyze_context_understanding(context='...', user_query='...')"
- After calling functions, use the results to provide the final response or generate the script.
"""
        
        config = GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=2048,
            top_p=0.95,
            system_instruction=self.system_instruction,
        )
        
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[enhanced_prompt],
                config=config,
            )
            
            if not response.candidates or not response.candidates[0].content:
                raise RuntimeError("Orchestrator returned no response")
            
            # Parse response for function calls (text-based parsing)
            response_text = response.candidates[0].content.parts[0].text if response.candidates[0].content.parts else ""
            
            result = {
                "user_query": user_query,
                "response": response_text,
                "function_calls": [],
                "generated_script": None,
                "reasoning": "",
            }
            
            # Parse function calls from response text (simple regex-based)
            import re
            function_pattern = r"FUNCTION:\s*(\w+)\((.*?)\)"
            matches = re.findall(function_pattern, response_text, re.DOTALL)
            for func_name, func_args_str in matches:
                # Simple parsing of arguments (can be improved)
                args = {}
                # Try to extract key-value pairs from function args string
                arg_pattern = r"(\w+)=['\"]([^'\"]+)['\"]"
                arg_matches = re.findall(arg_pattern, func_args_str)
                for arg_name, arg_value in arg_matches:
                    # Try to convert to appropriate types
                    if arg_value.lower() in ['true', 'false']:
                        args[arg_name] = arg_value.lower() == 'true'
                    elif arg_value.isdigit():
                        args[arg_name] = int(arg_value)
                    else:
                        args[arg_name] = arg_value
                
                result["function_calls"].append({
                    "name": func_name,
                    "args": args
                })
            
            # If RAG query was requested and pipeline provided, execute it
            if rag_pipeline and result["function_calls"]:
                for func_call in result["function_calls"]:
                    if func_call["name"] == "query_rag_system":
                        query = func_call["args"].get("query", user_query)
                        top_k = func_call["args"].get("top_k", 40)
                        use_iterative = func_call["args"].get("use_iterative_refinement", False)
                        
                        if use_iterative:
                            rag_result = rag_pipeline.query_iterative(query, top_k=top_k)
                        else:
                            rag_result = rag_pipeline.query(query, top_k=top_k)
                        
                        result["rag_result"] = rag_result
                        # Use RAG result to enhance context
                        enhanced_context = self._format_rag_result_for_script_generation(rag_result)
                        result["enhanced_context"] = enhanced_context
                        # Update rag_context for script generation
                        rag_context = rag_result
            
            # Auto-generate script if user explicitly requests it and we have context
            should_generate_script = (
                any(fc["name"] == "generate_playwright_script" for fc in result["function_calls"]) or
                ("playwright" in user_query.lower() or "script" in user_query.lower() or "automate" in user_query.lower())
            )
            
            # Generate Playwright script if requested
            if should_generate_script:
                # Prepare context for script generation
                script_context = result.get("enhanced_context", "")
                if rag_context:
                    if not script_context:
                        script_context = self._format_rag_result_for_script_generation(rag_context)
                
                # If we have function call with args, use them; otherwise infer from query
                script_call = None
                for fc in result["function_calls"]:
                    if fc["name"] == "generate_playwright_script":
                        script_call = fc
                        break
                
                if script_call:
                    # Use function call arguments
                    script_result = self._generate_playwright_script_from_function_call(
                        user_query, script_context, result["function_calls"]
                    )
                else:
                    # Generate script directly with inferred parameters
                    script_result = self._generate_playwright_script_direct(
                        user_query, script_context
                    )
                
                result["generated_script"] = script_result
                
                # If orchestrator only analyzed without generating, update response
                if not result.get("response") or "FUNCTION:" in result.get("response", ""):
                    result["response"] = f"Generated Playwright script based on your request and the application context."
            else:
                # Get text response
                result["response"] = response.candidates[0].content.parts[0].text if response.candidates[0].content.parts else ""
            
            return result
            
        except Exception as e:
            self.logger.error("Orchestration failed: %s", e)
            raise
    
    def _summarize_rag_context(self, rag_context: Dict[str, Any]) -> str:
        """Summarize RAG context for orchestrator."""
        if not rag_context:
            return "No context available"
        
        summary_parts = []
        if "answer" in rag_context:
            summary_parts.append(f"Answer: {rag_context['answer']}")
        if "retrieved" in rag_context:
            summary_parts.append(f"Retrieved {len(rag_context['retrieved'])} chunks")
            # Include top chunks
            for i, chunk in enumerate(rag_context['retrieved'][:3], 1):
                summary_parts.append(f"\nChunk {i} ({chunk.get('path', 'unknown')}):\n{chunk.get('text', '')[:300]}...")
        
        return "\n".join(summary_parts)
    
    def _format_rag_result_for_script_generation(self, rag_result: Dict[str, Any]) -> str:
        """Format RAG result for Playwright script generation."""
        formatted = []
        
        if "answer" in rag_result:
            formatted.append(f"# Context Understanding:\n{rag_result['answer']}\n")
        
        if "retrieved" in rag_result:
            formatted.append("\n# Relevant Code/Context Snippets:\n")
            for i, chunk in enumerate(rag_result["retrieved"][:5], 1):
                path = chunk.get("path", "unknown")
                text = chunk.get("text", "")[:500]
                formatted.append(f"## {path}\n```\n{text}\n```\n")
        
        return "\n".join(formatted)
    
    def _generate_playwright_script_from_function_call(self, user_request: str, 
                                                      context: str,
                                                      function_calls: List[Dict]) -> str:
        """Generate Playwright script based on function call and context."""
        script_call = None
        for fc in function_calls:
            if fc["name"] == "generate_playwright_script":
                script_call = fc
                break
        
        if not script_call:
            # Generate script without function call
            return self._generate_playwright_script_direct(user_request, context)
        
        args = script_call["args"]
        script_type = args.get("script_type", "interaction")
        target_url = args.get("target_url", "")
        steps = args.get("steps", [])
        
        # Extract URL from context if not provided
        if not target_url and context:
            import re
            url_pattern = r'(https?://[^\s\)]+|www\.[^\s\)]+|[a-zA-Z0-9\-]+\.[a-zA-Z]{2,}[^\s\)]*)'
            urls = re.findall(url_pattern, context)
            if urls:
                target_url = urls[0] if not urls[0].startswith('http') else urls[0]
        
        # Build context summary for script generation
        context_summary = context
        if len(context) > 2000:
            # Truncate context but keep important parts
            context_summary = context[:1500] + "\n\n[Additional context truncated...]"
        
        prompt = f"""Generate a complete Playwright Python automation script based on the following requirements.

USER REQUEST:
{user_request}

CONTEXT FROM DOCUMENTATION/CODE:
{context_summary}

SCRIPT TYPE: {script_type}
TARGET: {target_url}
STEPS TO PERFORM:
{chr(10).join(f'- {step}' for step in steps) if steps else 'Derive from user request and context'}

REQUIREMENTS:
1. Use Playwright Python API (from playwright.sync_api import sync_playwright)
2. Include proper imports and setup
3. Use stable selectors (prefer data-testid, role, text over CSS)
4. Include error handling with try/except
5. Add appropriate waits (wait_for_load_state, wait_for_selector)
6. Include comments explaining each major step
7. Handle dynamic content loading
8. Make the script production-ready and maintainable

Generate ONLY the Python script code, no explanations before or after."""

        config = GenerateContentConfig(
            temperature=0.2,  # Lower temperature for code generation
            max_output_tokens=4096,
            top_p=0.95,
        )
        
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[prompt],
                config=config,
            )
            
            if not response.candidates or not response.candidates[0].content:
                raise RuntimeError("Script generation returned no response")
            
            script = response.candidates[0].content.parts[0].text.strip()
            
            # Clean up markdown code blocks if present
            if "```python" in script:
                script = script.split("```python")[1].split("```")[0].strip()
            elif "```" in script:
                script = script.split("```")[1].split("```")[0].strip()
            
            self.logger.info("[OrchestratorAgent] Generated Playwright script (%d chars)", len(script))
            return script
            
        except Exception as e:
            self.logger.error("Script generation failed: %s", e)
            return f"# Error generating script: {str(e)}\n# Please provide more details about the automation task."
    
    def _generate_playwright_script_direct(self, user_request: str, context: str) -> str:
        """Generate Playwright script directly from user request."""
        # Infer script type from user request
        script_type = "interaction"
        if "test" in user_request.lower() or "testing" in user_request.lower():
            script_type = "testing"
        elif "scrape" in user_request.lower() or "scraping" in user_request.lower():
            script_type = "web_scraping"
        elif "form" in user_request.lower() or "fill" in user_request.lower():
            script_type = "form_filling"
        elif "navigate" in user_request.lower() or "navigation" in user_request.lower():
            script_type = "navigation"
        
        return self._generate_playwright_script_from_function_call(
            user_request, context, 
            [{"name": "generate_playwright_script", "args": {"user_request": user_request, "script_type": script_type}}]
        )
    
    def generate_playwright_script(self, user_request: str, context: Optional[str] = None,
                                   script_type: str = "interaction",
                                   target_url: Optional[str] = None,
                                   steps: Optional[List[str]] = None) -> str:
        """
        Direct method to generate Playwright script.
        
        Args:
            user_request: User's automation request
            context: Optional context from RAG or documentation
            script_type: Type of script (web_scraping, form_filling, navigation, testing, interaction)
            target_url: Target URL if applicable
            steps: List of steps to perform
        
        Returns:
            Complete Playwright Python script as string
        """
        return self._generate_playwright_script_from_function_call(
            user_request,
            context or "",
            [{
                "name": "generate_playwright_script",
                "args": {
                    "user_request": user_request,
                    "context": context or "",
                    "script_type": script_type,
                    "target_url": target_url or "",
                    "steps": steps or []
                }
            }]
        )

