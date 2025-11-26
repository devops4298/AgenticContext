#!/usr/bin/env python3
"""
orchestrator_agent.py — Root Orchestrator Agent

Responsibilities:
- Parse user request
- Format multi-step test scenarios
- Coordinate sub-agent execution
- Handle errors and retries
"""

import logging
import json
import re
from typing import Dict, Any, Optional, List

try:
    import google.genai as genai
    from google.genai.types import GenerateContentConfig
except Exception as e:
    raise RuntimeError("google-genai is required. Install with `pip install google-genai`") from e

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.rag import AppConfig, retry, logger
from agents.rag_agent import RagAgent
from agents.scripter_agent import ScripterAgent
from agents.script_dev_agent import ScriptDevelopmentAgent


class OrchestratorAgent:
    """
    Root orchestrator agent that coordinates the entire agentic system.
    Delegates to RagAgent, ScripterAgent, and ScriptDevelopmentAgent.
    """
    
    def __init__(self, config: AppConfig, cdp_inspector_path: str = None):
        """
        Initialize OrchestratorAgent.
        
        Args:
            config: App configuration
            cdp_inspector_path: Optional path to Node.js CDP Inspector
        """
        self.cfg = config
        self.logger = logging.getLogger("OrchestratorAgent")
        if not self.cfg.google_ai_api_key:
            raise ValueError("GOOGLE_AI_API_KEY required for orchestrator agent")
        
        self.client = genai.Client(api_key=self.cfg.google_ai_api_key)
        self.model = self.cfg.text_model
        self.cdp_inspector_path = cdp_inspector_path
        
        # Initialize sub-agents (will be set when rag_pipeline is available)
        self.rag_agent: Optional[RagAgent] = None
        self.scripter_agent: Optional[ScripterAgent] = None
        self.script_dev_agent: Optional[ScriptDevelopmentAgent] = None
    
    def initialize_sub_agents(self, rag_pipeline):
        """Initialize sub-agents with required dependencies."""
        self.rag_agent = RagAgent(self.cfg, rag_pipeline)
        self.scripter_agent = ScripterAgent(self.cfg, self.cdp_inspector_path)
        self.script_dev_agent = ScriptDevelopmentAgent(self.cfg)
        self.logger.info("[OrchestratorAgent] Sub-agents initialized")
    
    def format_request_for_llm(self, user_query: str) -> Dict[str, Any]:
        """
        Format user request to be LLM-friendly and extract multi-step request.
        
        Args:
            user_query: Raw user query
        
        Returns:
            Dict with formatted request and extracted steps
        """
        # Format request for structured output
        system_instruction_QueryNormalization = """
            # ============================================
            # SYSTEM ROLE: QueryNormalizationAgent
            # PURPOSE: Rewrite user requests and decompose tasks
            # ============================================

            You are the **Query Normalization & Task Decomposition Agent** inside a
            multi-agent test-automation system.

            Your responsibilities:
            - Interpret and normalize natural-language user queries
            - Rewrite them into a clear, structured, automation-ready specification
            - Break the request into atomic, deterministic steps
            - Infer the underlying intent
            - Produce a strict JSON response that downstream agents can execute

            ====================================================
            ## CAPABILITIES
            You can:
            - Interpret ambiguous or underspecified user input
            - Resolve pronouns and unclear references
            - Normalize human language into machine-executable instructions
            - Decompose high-level queries into step-by-step task plans
            - Make safe assumptions when data is missing
            - Produce deterministic JSON outputs for orchestration pipelines

            You cannot:
            - Execute automation
            - Generate code
            - Interact directly with browser sessions or tools

            ====================================================
            ## INPUT FORMAT
            You will receive messages containing:

            "user_query": A user's natural-language request.
            It may be vague, conversational, emotional, incomplete, or disorganized.

            Example:
            "Can you test the login maybe? I think the button is broken or something."

            ====================================================
            ## OUTPUT FORMAT (STRICT)
            Respond **only** with the following JSON schema:

            {
            "formatted_request": "A clean rewritten version of the user query, fully explicit and automation-friendly.",
            "steps": [
                "Step 1 as a clear, atomic action",
                "Step 2",
                "Step 3"
            ],
            "intent": "Short sentence describing the overall goal."
            }

            Rules:
            - All fields are REQUIRED.
            - Steps must be atomic, imperative, and sequenced.
            - Never ask clarifying questions.
            - Make safe assumptions and note them explicitly in `formatted_request`.
            - Never include explanations outside the JSON.
            - Never include comments, markdown, or prose.

            ====================================================
            ## REWRITING RULES
            When producing "formatted_request":
            - Convert all vague or casual language into explicit, unambiguous instructions.
            - Replace pronouns (“it”, “that button”, “the thing”) with inferred explicit references.
            - Use declarative, automation-friendly descriptions.
            - Expand incomplete actions (“test login”) into explicit actions (“navigate to login page, enter credentials…”).
            - Preserve user's meaning while giving structure.

            ====================================================
            ## STEP GENERATION RULES
            When producing "steps":
            - **PRESERVE the user's action verbs** when they are clear (e.g., "click", "go to", "open")
            - **IMPORTANT**: Distinguish between:
              * URL navigation: "Navigate to http://..." or "Go to https://..." (use "Navigate to")
              * Clicking UI elements: "Click on Contacts", "Go to Contacts page" (use "Click" or preserve user's verb)
            - Use imperative verbs: "navigate" (for URLs only), "click", "enter", "fill", "verify", "extract"
            - Avoid grouped tasks; split compound actions into individual steps
            - Maintain correct sequence
            - If something is missing, add placeholders
            e.g., "<ENTER_USERNAME_HERE>"
            - Ensure every step is executable by an automation agent.
            
            EXAMPLES:
            - User: "Go to Contacts" → Step: "Click on the 'Contacts' link" (NOT "Navigate to the 'Contacts' page")
            - User: "Navigate to http://example.com" → Step: "Navigate to http://example.com"
            - User: "Open the settings menu" → Step: "Click on the 'Settings' menu"

            ====================================================
            ## INTENT EXTRACTION RULES
            "intent" must be:
            - A single sentence
            - High-level but exact
            - Describing the purpose of the workflow
            Examples:
            - "Automate login verification flow"
            - "Generate an automation plan for product data extraction"

            ====================================================
            ## ERROR HANDLING
            If the user query is empty or non-text:
            - Produce:
            {
            "formatted_request": "Invalid or empty input received.",
            "steps": [],
            "intent": "Unable to determine intent due to invalid input."
            }

            ====================================================
            ## PRIMARY OBJECTIVE
            Enable downstream agents (Planner, Generator, Healer, CDP Inspector, RAG Contextualizer)
            to receive clean, structured task plans even when the user provides
            messy or ambiguous instructions.

            ====================================================
            ## BEGIN PROCESSING USER QUERY
            The user input to normalize is:

            {user_query}
            """
        prompt = (
        f"{system_instruction_QueryNormalization}\n\n"
        f"Original Query: {user_query.strip()}\n")

        config = GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=1024,
            top_p=0.95,
        )
        
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[prompt],
                config=config,
            )
            
            if not response.candidates or not response.candidates[0].content:
                raise RuntimeError("LLM returned no response")
            
            response_text = response.candidates[0].content.parts[0].text.strip()
            
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                return parsed
            else:
                # Fallback: create simple steps
                return {
                    "formatted_request": user_query,
                    "steps": [user_query],
                    "intent": "Automate user request"
                }
                
        except Exception as e:
            self.logger.error(f"Error formatting request: {e}")
            # Fallback
            return {
                "formatted_request": user_query,
                "steps": [user_query],
                "intent": "Automate user request"
            }
    
    def correct_steps_based_on_chunks(self, steps: List[str], rag_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Correct steps based on RAG chunks. If step says "Save" but chunks mention "Post",
        correct the step to "Post".
        
        Args:
            steps: Original steps
            rag_result: RAG result with step contexts and chunks
        
        Returns:
            List of corrected steps (or original if no corrections needed)
        """
        corrected_steps = []
        step_corrections = {}
        step_contexts = rag_result.get("step_contexts", {})
        
        for i, step in enumerate(steps, 1):
            step_key = f"step_{i}"
            step_context = step_contexts.get(step_key, {})
            
            # Skip navigation steps - they don't need correction
            step_lower = step.lower()
            if any(word in step_lower for word in ['navigate', 'go to', 'open', 'visit', 'navigate to']):
                self.logger.debug(f"[OrchestratorAgent] Step {i}: Navigation step, skipping correction")
                corrected_steps.append(step)
                continue
            
            # Get retrieved chunks for this step
            # Try multiple locations where chunks might be stored
            retrieved_chunks = []
            if "retrieved_chunks" in step_context and isinstance(step_context["retrieved_chunks"], list):
                retrieved_chunks = step_context["retrieved_chunks"]
            elif "context" in step_context:
                context_data = step_context.get("context", {})
                retrieved_chunks = context_data.get("retrieved", [])
            
            if not retrieved_chunks:
                # No chunks, keep original step
                self.logger.debug(f"[OrchestratorAgent] Step {i}: No chunks found, keeping original")
                corrected_steps.append(step)
                continue
            
            # Build context from chunks - using same format as script generation
            chunks_text_parts = []
            for chunk in retrieved_chunks[:8]:  # Use top 8 chunks for better context
                # Handle different chunk formats (same as script generation)
                if isinstance(chunk, dict):
                    path = chunk.get('path', chunk.get('file_path', chunk.get('source', 'unknown')))
                    text = chunk.get('text', chunk.get('content', chunk.get('chunk_text', chunk.get('chunk', ''))))
                    if text:
                        # Format like script generation: path + code snippet
                        chunks_text_parts.append(f"## {path}\n```\n{text[:800]}\n```")
                elif isinstance(chunk, str):
                    chunks_text_parts.append(f"```\n{chunk[:800]}\n```")
            
            chunks_text = "\n\n".join(chunks_text_parts)
            
            if not chunks_text.strip():
                # No chunks text, keep original step
                self.logger.debug(f"[OrchestratorAgent] Step {i}: Chunks found but no text content, keeping original")
                corrected_steps.append(step)
                continue
            
            # Log what chunks we're analyzing
            self.logger.info(f"[OrchestratorAgent] Step {i}: Analyzing {len(retrieved_chunks)} chunks for step correction")
            print(f"   🔍 Analyzing {len(retrieved_chunks)} chunks to correct step: '{step}'")
            
            # Debug: Show first chunk preview
            if retrieved_chunks:
                first_chunk = retrieved_chunks[0]
                if isinstance(first_chunk, dict):
                    chunk_preview = first_chunk.get('text', first_chunk.get('content', ''))[:200]
                    if chunk_preview:
                        print(f"   📄 First chunk preview: {chunk_preview}...")
            
            # Use LLM to correct the step - using same approach as script generation
            try:
                prompt = f"""
                    You are an LLM-based Step Correction Agent. Your job is to rewrite automation steps so they strictly match terminology from RAG-retrieved chunks. Chunks may contain code, documentation, API schemas, configuration files, text files, spreadsheets, or any other reference material.

                    Your output must be a corrected step that uses the exact terminology found in the chunks.

                    ---

                    ORIGINAL_STEP:
                    {step}

                    RAG_CHUNKS (authoritative source of truth):
                    {chunks_text}

                    ---

                    CORRECTION LOGIC:
                    You must correct the step by aligning it with exact terminology found in the chunks. Apply all corrections that are supported by the RAG content:

                    1. **Singular/Plural**  
                    Match the exact form used in chunks.  
                    Example: "Users" → "User" if chunks show "User".

                    2. **Terminology / Domain Vocabulary**  
                    Replace generic terms with domain-accurate ones from chunks.  
                    Example: "Submit" → "Publish" if chunks contain "Publish button".

                    3. **Field / Property / Column Names**  
                    Use exact identifiers or labels from chunks (case-sensitive).  
                    Example: "Full Name" → "fullName".

                    4. **UI Labels, Button Names, Menu Items, Text Strings**  
                    Replace step text with exact UI labels from chunks.  
                    Example: "Close" → "Dismiss" if chunks show "Dismiss".

                    5. **Values / Options / Status Terms**  
                    Correct based on values shown in chunks.  
                    Example: "Active" → "Enabled".

                    6. **File Names, Sheet Names, Document Titles**  
                    Match exact names found in chunks.  
                    Example: "Report" → "Sales Report.xlsx".

                    7. **Any Other Text or Content**  
                    Excel cells, config values, text files, markdown, JSON paths, routing paths, etc.  
                    You must align to the exact representation used in the chunks.

                    ---

                    EXAMPLES:
                    (These show the type of transformations but must NOT influence the final output unless supported by chunks.)

                    - "Select Users from dropdown" → "Select User from dropdown"
                    - "Enter Full Name" → "Enter fullName"
                    - "Click Submit" → "Click Publish"
                    - "Select Active status" → "Select Enabled status"
                    - "Open Report" → "Open Sales Report file"
                    - "Fill Email Address" → "Fill email"
                    - "Click Close" → "Click Dismiss"
                    - "Navigate to Dashboard" → "Navigate to Main Dashboard"

                    ---

                    OUTPUT REQUIREMENTS:
                    1. Return **ONLY** the corrected step.  
                    2. No commentary, no explanation, no markdown.  
                    3. Maintain the action verb (click, type, select, open, navigate, etc.).  
                    4. Use only terminology that appears in the RAG chunks.

                    ---

                    CORRECTED_STEP:
                    """


                config = GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=256,
                    top_p=0.95,
                )
                
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=[prompt],
                    config=config,
                )
                
                if response.candidates and response.candidates[0].content:
                    corrected_step = response.candidates[0].content.parts[0].text.strip()
                    # Clean up any markdown, code blocks, or extra formatting
                    corrected_step = corrected_step.replace("```", "").replace("```python", "").replace("```javascript", "").strip()
                    # Remove common prefixes like "Corrected step:" or "Step:"
                    for prefix in ["Corrected step:", "Step:", "CORRECTED STEP:", "The corrected step is:", "Corrected:", "CORRECTED:"]:
                        if corrected_step.lower().startswith(prefix.lower()):
                            corrected_step = corrected_step[len(prefix):].strip()
                    # Remove quotes if the entire response is quoted
                    if (corrected_step.startswith('"') and corrected_step.endswith('"')) or \
                       (corrected_step.startswith("'") and corrected_step.endswith("'")):
                        corrected_step = corrected_step[1:-1].strip()
                    
                    # Check if we have options available (no exact match but options found)
                    options_info = self._extract_available_options_from_chunks(step, retrieved_chunks)
                    
                    # Skip auto-correction for navigation/link steps (e.g., "Go to Contacts", "Navigate to Dashboard")
                    # These should be handled by locator generation, not text replacement
                    step_lower = step.lower()
                    is_navigation_step = any(phrase in step_lower for phrase in ['navigate to', 'go to', 'open', 'visit']) and \
                                       not any(url in step_lower for url in ['http://', 'https://', 'localhost:', 'www.'])
                    
                    # ALSO skip auto-correction for Enter/Fill steps that contain user data
                    # (e.g., "Enter 'Chetan Chauhan' into the 'Name' field")
                    # These steps have quoted data that should NOT be replaced
                    is_data_entry_step = any(word in step_lower for word in ['enter', 'fill', 'type']) and "'" in step
                    
                    # If no exact match but options are available, auto-select the first/best option
                    # BUT skip for navigation steps and data entry steps
                    if not is_navigation_step and not is_data_entry_step and not options_info["has_exact_match"] and options_info["available_options"]:
                        # Automatically use the first available option
                        selected_option = options_info["available_options"][0]
                        selected_value = selected_option.get("value", "")
                        target_term = options_info.get("target_term", "")
                        
                        # Replace target term with selected value in the step
                        if target_term and selected_value:
                            auto_corrected_step = step.replace(target_term, selected_value)
                            # Also try case-insensitive replacement
                            if auto_corrected_step == step:
                                import re
                                auto_corrected_step = re.sub(
                                    re.escape(target_term), 
                                    selected_value, 
                                    step, 
                                    flags=re.IGNORECASE
                                )
                            
                            self.logger.info(f"[OrchestratorAgent] ✅ Auto-selected option for step {i}: '{target_term}' -> '{selected_value}'")
                            print(f"   🔄 Step {i} auto-corrected: '{step}' → '{auto_corrected_step}' (selected: '{selected_value}')")
                            
                            # Find referenced chunks for the selected option
                            referenced_chunks = self._find_referenced_chunk_portions(step, auto_corrected_step, retrieved_chunks)
                            
                            corrected_steps.append(auto_corrected_step)
                            step_corrections[i] = {
                                "original": step,
                                "corrected": auto_corrected_step,
                                "referenced_chunks": referenced_chunks
                            }
                            continue
                    
                    # Find referenced chunk portions based on corrected terms
                    referenced_chunks = self._find_referenced_chunk_portions(step, corrected_step, retrieved_chunks)
                    
                    # Only use correction if it's different and meaningful
                    if corrected_step and len(corrected_step) > 5:
                        # Check if it's actually different (case-insensitive comparison)
                        step_lower = step.lower().strip()
                        corrected_lower = corrected_step.lower().strip()
                        
                        # More lenient comparison - accept if there are any word differences
                        # This allows singular/plural corrections (Contacts -> Contact)
                        step_words = set(step_lower.split())
                        corrected_words = set(corrected_lower.split())
                        
                        # Check if there are meaningful differences (different words or different order)
                        # Allow singular/plural changes (Contacts/Contact, Users/User, etc.)
                        has_differences = (
                            step_lower != corrected_lower and  # Different text
                            len(corrected_step) >= len(step) * 0.5 and  # Not too short
                            (step_words != corrected_words or step_lower != corrected_lower)  # Different words or order
                        )
                        
                        if has_differences:
                            self.logger.info(f"[OrchestratorAgent] ✅ Corrected step {i}: '{step}' -> '{corrected_step}'")
                            print(f"   🔄 Step {i} corrected: '{step}' → '{corrected_step}'")
                            corrected_steps.append(corrected_step)
                            step_corrections[i] = {
                                "original": step,
                                "corrected": corrected_step,
                                "referenced_chunks": referenced_chunks
                            }
                        else:
                            self.logger.debug(f"[OrchestratorAgent] Step {i} correction too similar, keeping original: '{step}' vs '{corrected_step}'")
                            corrected_steps.append(step)
                            step_corrections[i] = {
                                "original": step,
                                "corrected": step,
                                "referenced_chunks": []
                            }
                    else:
                        self.logger.debug(f"[OrchestratorAgent] Step {i} correction invalid (too short or empty), keeping original")
                        corrected_steps.append(step)
                        step_corrections[i] = {
                            "original": step,
                            "corrected": step,
                            "referenced_chunks": []
                        }
                else:
                    self.logger.debug(f"[OrchestratorAgent] Step {i} no LLM response, keeping original")
                    corrected_steps.append(step)
                    step_corrections[i] = {
                        "original": step,
                        "corrected": step,
                        "referenced_chunks": []
                    }
                    
            except Exception as e:
                self.logger.warning(f"[OrchestratorAgent] Error correcting step {i}: {e}")
                print(f"   ⚠️  Error correcting step {i}: {e}")
                corrected_steps.append(step)
                step_corrections[i] = {
                    "original": step,
                    "corrected": step,
                    "referenced_chunks": []
                }
        
        return {
            "corrected_steps": corrected_steps if corrected_steps else steps,
            "step_corrections": step_corrections
        }
    
    def _extract_available_options_from_chunks(self, step: str, retrieved_chunks: List[Dict]) -> Dict[str, Any]:
        """
        Extract available options (buttons, fields, etc.) from chunks when exact match not found.
        
        Args:
            step: Step description
            retrieved_chunks: List of retrieved chunks
        
        Returns:
            Dict with:
                - has_exact_match: bool
                - available_options: List of options found in chunks
                - option_type: Type of options (button, field, etc.)
        """
        step_lower = step.lower()
        
        # Detect what we're looking for
        looking_for_button = any(word in step_lower for word in ['button', 'click', 'press', 'tap'])
        looking_for_field = any(word in step_lower for word in ['field', 'input', 'enter', 'fill', 'type'])
        looking_for_link = any(word in step_lower for word in ['link', 'tab', 'menu', 'navigate'])
        
        # Extract the target term from step (e.g., "Save" from "Click Save button")
        import re
        # Try to extract quoted text or capitalized words
        quoted = re.findall(r'["\']([^"\']+)["\']', step)
        if quoted:
            target_term = quoted[0]
        else:
            # Extract capitalized words (likely the button/field name)
            words = step.split()
            capitalized = [w for w in words if w[0].isupper() and len(w) > 2]
            target_term = capitalized[0] if capitalized else ""
        
        target_term_lower = target_term.lower() if target_term else ""
        
        # Search chunks for buttons, fields, links
        available_options = []
        option_type = "unknown"
        
        for chunk in retrieved_chunks[:10]:  # Check top 10 chunks
            if isinstance(chunk, dict):
                text = chunk.get('text', chunk.get('content', chunk.get('chunk_text', chunk.get('chunk', ''))))
                path = chunk.get('path', chunk.get('file_path', chunk.get('source', 'unknown')))
                
                if not text:
                    continue
                
                text_lower = text.lower()
                
                # Extract buttons
                if looking_for_button:
                    # Look for button text, onClick handlers, button elements
                    button_patterns = [
                        r'<button[^>]*>([^<]+)</button>',
                        r'button[^>]*>([^<]+)</button',
                        r'onClick[^=]*=.*["\']([^"\']+)["\']',
                        r'["\']([^"\']+button[^"\']*)["\']',
                        r'button.*text[^=]*=.*["\']([^"\']+)["\']',
                    ]
                    
                    for pattern in button_patterns:
                        matches = re.findall(pattern, text, re.IGNORECASE)
                        for match in matches:
                            if match and len(match.strip()) > 1 and match.strip().lower() != target_term_lower:
                                # Check if it's a meaningful button name (not just "button")
                                if any(char.isalpha() for char in match) and len(match.strip()) < 50:
                                    available_options.append({
                                        "value": match.strip(),
                                        "type": "button",
                                        "path": path,
                                        "context": text[max(0, text.lower().find(match.lower())-50):text.lower().find(match.lower())+len(match)+50]
                                    })
                
                # Extract input fields
                if looking_for_field:
                    field_patterns = [
                        r'<input[^>]*name=["\']([^"\']+)["\']',
                        r'<input[^>]*placeholder=["\']([^"\']+)["\']',
                        r'name[^=]*=.*["\']([^"\']+)["\']',
                        r'field[^=]*=.*["\']([^"\']+)["\']',
                    ]
                    
                    for pattern in field_patterns:
                        matches = re.findall(pattern, text, re.IGNORECASE)
                        for match in matches:
                            if match and len(match.strip()) > 1 and match.strip().lower() != target_term_lower:
                                available_options.append({
                                    "value": match.strip(),
                                    "type": "field",
                                    "path": path,
                                    "context": text[max(0, text.lower().find(match.lower())-50):text.lower().find(match.lower())+len(match)+50]
                                })
        
        # Remove duplicates
        seen = set()
        unique_options = []
        for opt in available_options:
            key = (opt["value"].lower(), opt["type"])
            if key not in seen:
                seen.add(key)
                unique_options.append(opt)
        
        # Determine if exact match exists
        has_exact_match = target_term_lower in [opt["value"].lower() for opt in unique_options] if target_term_lower else False
        
        if unique_options:
            option_type = unique_options[0]["type"] if unique_options else "unknown"
        
        return {
            "has_exact_match": has_exact_match,
            "available_options": unique_options[:10],  # Limit to top 10
            "option_type": option_type,
            "target_term": target_term
        }
    
    def _find_referenced_chunk_portions(self, original_step: str, corrected_step: str, retrieved_chunks: List[Dict]) -> List[Dict[str, Any]]:
        """
        Find chunk portions that were likely referenced for the correction.
        
        Args:
            original_step: Original step text
            corrected_step: Corrected step text
            retrieved_chunks: List of retrieved chunks
        
        Returns:
            List of chunk portions with path and relevant text snippet
        """
        referenced = []
        
        # Find words that changed between original and corrected
        original_words = set(original_step.lower().split())
        corrected_words = set(corrected_step.lower().split())
        changed_words = corrected_words - original_words
        
        if not changed_words:
            return referenced
        
        # Search through chunks for these changed words
        for chunk in retrieved_chunks[:5]:  # Check top 5 chunks
            if isinstance(chunk, dict):
                path = chunk.get('path', chunk.get('file_path', chunk.get('source', 'unknown')))
                text = chunk.get('text', chunk.get('content', chunk.get('chunk_text', chunk.get('chunk', ''))))
                
                if not text:
                    continue
                
                text_lower = text.lower()
                
                # Check if any changed word appears in this chunk
                found_words = []
                for word in changed_words:
                    if len(word) > 3 and word in text_lower:  # Only check meaningful words
                        found_words.append(word)
                
                if found_words:
                    # Extract a relevant snippet around the found words (200 chars before/after)
                    snippets = []
                    for word in found_words:
                        idx = text_lower.find(word)
                        if idx != -1:
                            start = max(0, idx - 200)
                            end = min(len(text), idx + len(word) + 200)
                            snippet = text[start:end]
                            snippets.append(snippet)
                    
                    # Use the first meaningful snippet
                    if snippets:
                        referenced.append({
                            "path": path,
                            "snippet": snippets[0],
                            "matched_terms": found_words
                        })
        
        return referenced
    
    @retry(Exception, tries=3, delay=1.0, backoff=2.0, logger=logger)
    def generate_plan(self, user_query: str, rag_pipeline=None) -> Dict[str, Any]:
        """
        Phase 1 of orchestration: Parse request, get RAG context, and correct steps.
        Returns a plan that can be reviewed by a human before execution.
        
        Args:
            user_query: User's query
            rag_pipeline: RAGPipeline instance
            
        Returns:
            Dict with plan details (steps, rag_result, etc.)
        """
        self.logger.info("[OrchestratorAgent] Generating plan for request: '%s'", user_query[:100])
        
        if not rag_pipeline:
            raise ValueError("rag_pipeline is required for orchestration")
        
        # Initialize sub-agents if not already done
        if not self.rag_agent:
            self.initialize_sub_agents(rag_pipeline)
            
        try:
            # Step 1: Format request and extract steps
            formatted_request = self.format_request_for_llm(user_query)
            self.logger.info(f"[OrchestratorAgent] Formatted request: {formatted_request}")
            steps = formatted_request.get("steps", [])
            
            if not steps:
                return {
                    "user_query": user_query,
                    "error": "No steps extracted",
                    "formatted_request": formatted_request
                }
            
            # Step 2: Delegate to RagAgent
            self.logger.info(f"[OrchestratorAgent] Step 2: Delegating to RagAgent for {len(steps)} steps")
            # Use formatted_request for RAG query (cleaner, more structured than raw user_query)
            formatted_request_text = formatted_request.get("formatted_request", user_query)
            rag_result = self.rag_agent.get_context_for_steps(
                user_query,  # Keep original for reference
                steps,  # Use rewritten steps for step-specific queries
                formatted_request=formatted_request_text  # Use formatted version for overall context
            )
            
            # Step 2.5: Correct steps based on RAG chunks
            self.logger.info(f"[OrchestratorAgent] Step 2.5: Correcting steps based on RAG chunks")
            correction_result = self.correct_steps_based_on_chunks(steps, rag_result)
            corrected_steps = correction_result.get("corrected_steps", steps)
            step_corrections = correction_result.get("step_corrections", {})
            
            # GUARD: Forcefully revert steps that contain specific user intent keywords
            # This prevents the LLM from hallucinating "Post" tab instead of "Contact" tab, etc.
            final_steps = []
            for i, original_step in enumerate(steps):
                # Check if we have a corrected version
                current_step = corrected_steps[i] if i < len(corrected_steps) else original_step
                
                # Check for protected keywords in the ORIGINAL step
                original_lower = original_step.lower()
                if any(keyword in original_lower for keyword in ['contact', 'post', 'click on', 'enter']):
                    self.logger.info(f"[OrchestratorAgent] 🛡️ GUARD: Reverting step {i+1} to original: '{original_step}' (was corrected to '{current_step}')")
                    final_steps.append(original_step)
                    # Remove correction info if it exists
                    if i+1 in step_corrections:
                        del step_corrections[i+1]
                else:
                    final_steps.append(current_step)
            
            corrected_steps = final_steps
            
            if corrected_steps:
                steps = corrected_steps
                # Update steps in rag_result
                rag_result["steps"] = steps
                rag_result["step_corrections"] = step_corrections
                # Update step in each step_context
                for i, corrected_step in enumerate(corrected_steps, 1):
                    step_key = f"step_{i}"
                    if step_key in rag_result.get("step_contexts", {}):
                        rag_result["step_contexts"][step_key]["step"] = corrected_step
            
            return {
                "user_query": user_query,
                "formatted_request": formatted_request,
                "steps": steps,
                "rag_result": rag_result,
                "step_corrections": step_corrections
            }
            
        except Exception as e:
            self.logger.error(f"Plan generation failed: {e}")
            raise

    def execute_plan(self, plan: Dict[str, Any], automation_tool: Optional[str] = None) -> Dict[str, Any]:
        """
        Phase 2 of orchestration: Generate scripts based on the (potentially reviewed) plan.
        
        Args:
            plan: Output from generate_plan
            automation_tool: Optional automation tool preference
            
        Returns:
            Dict with final results including generated script
        """
        self.logger.info("[OrchestratorAgent] Executing plan")
        
        # Extract data from plan
        steps = plan.get("steps", [])
        rag_result = plan.get("rag_result", {})
        user_query = plan.get("user_query", "")
        formatted_request = plan.get("formatted_request", {})
        step_corrections = plan.get("step_corrections", {})
        
        if not steps:
            return {
                "user_query": user_query,
                "response": "No steps to execute.",
                "error": "No steps in plan"
            }
            
        try:
            # Step 3: Delegate to ScripterAgent
            self.logger.info(f"[OrchestratorAgent] Step 3: Delegating to ScripterAgent")
            # Ensure scripter agent is initialized
            if not self.scripter_agent:
                # We need the config to init scripter agent, assuming self.cfg is available
                self.scripter_agent = ScripterAgent(self.cfg, self.cdp_inspector_path)

            scripter_result = self.scripter_agent.get_nodes_for_steps(
                steps,
                rag_result
            )
            
            # Debug: Log the steps being executed
            self.logger.info(f"[OrchestratorAgent] Executing {len(steps)} steps:")
            for i, step in enumerate(steps, 1):
                self.logger.info(f"[OrchestratorAgent]   Step {i}: {step}")
            
            # Step 4: Delegate to ScriptDevelopmentAgent (only if automation_tool is provided)
            generated_script = None
            response_msg = ""
            
            if automation_tool:
                self.logger.info(f"[OrchestratorAgent] Step 4: Delegating to ScriptDevelopmentAgent with {automation_tool}")
                # Ensure script dev agent is initialized
                if not self.script_dev_agent:
                    self.script_dev_agent = ScriptDevelopmentAgent(self.cfg)

                try:
                    generated_script = self.script_dev_agent.generate_script(
                        steps=steps,
                        step_nodes=scripter_result.get("step_nodes", {}),
                        context=rag_result,
                        automation_tool=automation_tool
                    )
                    if generated_script:
                        response_msg = f"Generated {automation_tool} automation script with {len(steps)} steps."
                    else:
                        response_msg = f"Script generation returned empty result for {automation_tool}."
                        self.logger.warning("[OrchestratorAgent] Script generation returned empty result")
                except Exception as e:
                    self.logger.error(f"[OrchestratorAgent] Script generation failed: {e}", exc_info=True)
                    response_msg = f"Failed to generate {automation_tool} script: {str(e)}"
            else:
                # Just provide analysis without generating script
                response_msg = f"Analyzed request and extracted {len(steps)} steps. Enable 'Generate Playwright Script' to create automation script."
            
            # Return comprehensive result
            result = {
                "user_query": user_query,
                "formatted_request": formatted_request,
                "steps": steps,
                "rag_result": rag_result,
                "scripter_result": scripter_result,
                "step_corrections": step_corrections,
                "response": response_msg
            }
            
            if generated_script:
                result["generated_script"] = generated_script
                result["automation_tool"] = automation_tool
            
            return result
            
        except Exception as e:
            self.logger.error(f"Plan execution failed: {e}")
            raise

    @retry(Exception, tries=3, delay=1.0, backoff=2.0, logger=logger)
    def orchestrate(self, user_query: str, rag_pipeline=None, 
                   automation_tool: Optional[str] = None) -> Dict[str, Any]:
        """
        Main orchestration method that delegates to sub-agents.
        Now uses generate_plan and execute_plan sequence.
        
        Args:
            user_query: User's query or request
            rag_pipeline: RAGPipeline instance for querying
            automation_tool: Optional automation tool preference (e.g., "playwright")
        
        Returns:
            Dict with orchestration result including generated script
        """
        # Phase 1: Generate Plan
        plan = self.generate_plan(user_query, rag_pipeline)
        
        if plan.get("error"):
            return {
                "user_query": user_query,
                "response": plan.get("response", "Error generating plan"),
                "error": plan.get("error")
            }
            
        # Phase 2: Execute Plan
        return self.execute_plan(plan, automation_tool)

