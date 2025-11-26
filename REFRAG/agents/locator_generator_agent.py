#!/usr/bin/env python3
"""
locator_generator_agent.py — Locator Generator Agent using LLM to generate locators from RAG context.

Responsibilities:
- Generate initial locators for each step based on RAG context
- Use LLM to understand documentation and suggest locators
- Return structured locator suggestions for CDP validation
"""

import sys
import logging
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import google.genai as genai
    from google.genai.types import GenerateContentConfig
except Exception as e:
    raise RuntimeError("google-genai is required. Install with `pip install google-genai`") from e

from tools.rag import AppConfig


class LocatorGeneratorAgent:
    """Sub-agent responsible for generating locators from RAG context using LLM."""
    
    def __init__(self, config: AppConfig):
        """
        Initialize LocatorGeneratorAgent.
        
        Args:
            config: App configuration
        """
        self.cfg = config
        self.logger = logging.getLogger("LocatorGeneratorAgent")
        if not self.cfg.google_ai_api_key:
            raise ValueError("GOOGLE_AI_API_KEY required for LocatorGeneratorAgent")
        
        self.client = genai.Client(api_key=self.cfg.google_ai_api_key)
        self.model = self.cfg.text_model
    
    def generate_locators_for_steps(self, steps: List[str], rag_context: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Generate initial locators for each step based on RAG context.
        
        Args:
            steps: List of steps
            rag_context: Context from RagAgent (includes step_contexts with retrieved chunks)
        
        Returns:
            Dict mapping step keys to list of suggested locators
            Format: {
                "step_1": [
                    {"type": "css", "selector": "...", "confidence": 0.9, "source": "rag_context"},
                    {"type": "xpath", "selector": "...", "confidence": 0.8, "source": "rag_context"}
                ],
                ...
            }
        """
        self.logger.info(f"[LocatorGeneratorAgent] Generating locators for {len(steps)} steps from RAG context")
        print("\n" + "=" * 80)
        print("📋 RAG LOCATOR GENERATION RESULTS")
        print("=" * 80)
        
        step_locators = {}
        skipped_steps = 0
        
        for i, step in enumerate(steps, 1):
            step_key = f"step_{i}"
            
            # Skip navigation steps (they don't need DOM locators)
            if self._is_navigation_step(step):
                self.logger.info(f"[LocatorGeneratorAgent] Skipping navigation step: {step[:50]}...")
                step_locators[step_key] = []  # Empty list for navigation steps
                print(f"\n🔹 STEP {i}: {step}")
                print(f"   ⏭️  SKIPPED (Navigation step - no locator needed)")
                skipped_steps += 1
                continue
            
            step_context = rag_context.get("step_contexts", {}).get(step_key, {})
            retrieved_chunks = step_context.get("context", {}).get("retrieved", [])
            
            # Generate locators for this step
            locators = self._generate_locators_for_step(step, retrieved_chunks)
            step_locators[step_key] = locators
            
            # Print step and its locators
            print(f"\n🔹 STEP {i}: {step}")
            print(f"   Generated {len(locators)} locator(s):")
            for j, loc in enumerate(locators, 1):
                loc_type = loc.get('type', 'unknown')
                selector = loc.get('selector', 'N/A')
                confidence = loc.get('confidence', 0)
                stability = loc.get('stability', 'unknown')
                reasoning = loc.get('reasoning', 'No reasoning provided')
                
                print(f"      {j}. [{loc_type}] {selector[:70]}{'...' if len(selector) > 70 else ''}")
                print(f"         Confidence: {confidence:.2f} | Stability: {stability}")
                print(f"         Reasoning: {reasoning[:80]}{'...' if len(reasoning) > 80 else ''}")
            
            self.logger.info(f"[LocatorGeneratorAgent] Generated {len(locators)} locators for {step_key}")
        
        print("\n" + "=" * 80)
        total_locators = sum(len(locs) for locs in step_locators.values())
        print(f"✅ Total: {len(steps)} steps ({skipped_steps} navigation skipped), {total_locators} locators generated")
        print("=" * 80 + "\n")
        
        return step_locators
    
    def _is_navigation_step(self, step: str) -> bool:
        """
        Check if a step is a navigation step (doesn't need DOM locators).
        
        Args:
            step: Step description
        
        Returns:
            True if it's a navigation step, False otherwise
        """
        step_lower = step.lower().strip()
        
        import re
        # Check if step contains URL (actual navigation)
        url_pattern = r'(https?://|www\.|localhost:\d+)'
        has_url = re.search(url_pattern, step_lower)
        
        if has_url:
            # This is actual URL navigation
            return True
        
        # If no URL, it's not navigation even if it says "navigate to" or "go to"
        # (e.g., "Navigate to the Contacts page" means click the Contacts link)
        return False
    
    def _generate_locators_for_step(self, step: str, retrieved_chunks: List[Dict]) -> List[Dict[str, Any]]:
        """
        Use LLM to generate locators from step description and RAG context.
        
        Args:
            step: Step description
            retrieved_chunks: Retrieved code/documentation chunks
        
        Returns:
            List of suggested locators
        """
        # Build context from retrieved chunks (raw code/documentation snippets)
        # These contain actual selectors, IDs, class names, etc.
        context_text = ""
        if retrieved_chunks:
            context_text = "\n\n".join([
                f"[From {chunk.get('path', 'unknown')}]\n{chunk.get('text', '')[:800]}"
                for chunk in retrieved_chunks[:8]  # Use top 8 chunks for more context
            ])
        
        system_instruction = """
            # ============================================
            # SYSTEM ROLE: LocatorGeneratorAgent
            # PURPOSE: Generate web element locators from documentation context
            # ============================================

            You are the **Locator Generation Agent** inside a multi-agent test-automation system.
            Your role is to analyze step descriptions and documentation/code snippets to generate
            accurate, stable CSS selectors, XPath, or other locators for web automation.

            ====================================================
            ## CAPABILITIES
            You can:
            - Extract locator information from code/documentation snippets
            - Identify stable selectors (data-testid, stable IDs, aria-labels)
            - Generate multiple locator strategies for redundancy
            - Infer locators from step descriptions when documentation is unclear
            - Prioritize locators by stability and reliability
            - Produce structured JSON outputs for downstream CDP validation

            You cannot:
            - Execute automation or interact with browsers
            - Validate locators on live pages (done by CDP tool)
            - Generate test scripts (done by ScriptDevelopmentAgent)

            ====================================================
            ## SEMANTIC MATCHING GUIDELINES
            When generating locators, consider semantic synonyms and similar actions:
            - "Save" = "Post", "Submit", "Store", "Create", "Add", "Publish"
            - "Cancel" = "Close", "Dismiss", "Back", "Exit", "Discard"
            - "Delete" = "Remove", "Clear", "Trash", "Erase"
            - "Edit" = "Modify", "Update", "Change", "Alter"
            - "Search" = "Find", "Lookup", "Query", "Filter"
            - "Login" = "Sign In", "Authenticate", "Enter"
            - "Logout" = "Sign Out", "Exit", "Leave"
            
            If documentation mentions "Post" button but step says "Save", generate locators for "Post" 
            as they are semantically equivalent actions.
            
            ====================================================
            ## INPUT FORMAT
            You will receive:
            - STEP: A clear, atomic automation step description
            - CODE/DOCUMENTATION SNIPPETS: Raw code/documentation containing actual selectors, IDs, class names

            ====================================================
            ## OUTPUT FORMAT (STRICT)
            Respond **only** with a JSON array of locator objects:

            [
              {{
                "type": "attribute|id|name|aria-label|role|class|xpath|tag|text",
                "selector": "the exact selector string (e.g., '[data-testid=\"login-btn\"]', '#login-button', '//button[text()=\"Login\"]')",
                "confidence": 0.0-1.0,
                "stability": "high|medium|low",
                "reasoning": "brief explanation of why this locator might work"
              }},
              ...
            ]

            Rules:
            - Generate 2-5 locators per step
            - All fields are REQUIRED
            - Never include explanations outside the JSON
            - Never include markdown, code blocks, or prose
            - Selectors must be valid and ready to use

            ====================================================
            ## LOCATOR TYPE DEFINITIONS
            - "attribute": CSS attribute selector (e.g., '[data-testid="login"]', '[name="username"]')
            - "id": CSS ID selector (e.g., '#login-button')
            - "name": Name attribute selector (e.g., '[name="email"]')
            - "aria-label": Aria-label selector (e.g., '[aria-label="Close dialog"]')
            - "role": Role-based selector (e.g., '[role="button"]')
            - "class": CSS class selector (e.g., '.btn-primary')
            - "xpath": XPath expression (e.g., '//button[contains(text(), "Login")]')
            - "tag": HTML tag selector (e.g., 'button', 'input')
            - "text": Text-based selector (e.g., 'button:has-text("Login")')

            ====================================================
            ## LOCATOR PRIORITY RULES
            When generating locators, prioritize in this order:
            1. **data-testid attributes** (highest priority - most stable)
            2. **Stable IDs** (not dynamic/UUID/hashed)
            3. **Name attributes** (for form fields)
            4. **Aria-labels** (for accessibility, icon-only elements)
            5. **Role + accessible name** (semantic selectors)
            6. **Stable classes** (not hashed/minified)
            7. **XPath** (structural, but fragile)
            8. **Text-based** (fragile, use as fallback)
            9. **Tag name** (last resort, very fragile)

            ====================================================
            ## STABILITY ASSESSMENT
            Assign stability based on:
            - **high**: data-testid, stable IDs, name attributes, aria-labels
            - **medium**: stable classes, role-based, well-structured XPath
            - **low**: dynamic IDs, hashed classes, tag names, generic text

            ====================================================
            ## CONFIDENCE SCORING
            Confidence (0.0-1.0) should reflect:
            - 0.9-1.0: Locator explicitly mentioned in documentation/code
            - 0.7-0.8: Strong inference from code structure/documentation
            - 0.5-0.6: Moderate inference from step description
            - 0.3-0.4: Weak inference, generic selector
            - 0.1-0.2: Last resort fallback selector

            ====================================================
            ## ANALYSIS PROCESS
            1. **Parse Step Description**: Identify target element type (button, input, link, etc.)
            2. **Search Code Snippets**: Look for:
               - Exact selectors mentioned (data-testid, IDs, class names)
               - Component definitions with test IDs
               - Test files with selector examples
               - Form field names, button labels
            3. **Extract Patterns**: Identify naming conventions, structure patterns
            4. **Generate Strategies**: Create multiple locator approaches
            5. **Prioritize**: Order by stability and confidence

            ====================================================
            ## ERROR HANDLING
            If no clear locators can be inferred:
            - Generate generic locators based on step text
            - Use low confidence (0.2-0.4)
            - Mark stability as "low"
            - Still return valid JSON array (minimum 1 locator)

            ====================================================
            ## PRIMARY OBJECTIVE
            Enable the CDP validation agent to test locators on live pages by providing
            well-structured, prioritized locator suggestions based on documentation evidence.

            ====================================================
            ## BEGIN PROCESSING
            """
        
        prompt = f"""{system_instruction}

            STEP TO AUTOMATE:
            {step}

            RAW CODE/DOCUMENTATION SNIPPETS (PRIMARY SOURCE):
            {context_text[:3000] if context_text else "No code snippets available"}


            Generate locators for the step above. Return ONLY the JSON array, no markdown or explanation."""

        # ADK-aligned configuration for structured output
        config = GenerateContentConfig(
            temperature=0.2,  # Lower temperature for more deterministic, structured output
            max_output_tokens=2048,  # Increased for comprehensive locator generation
            top_p=0.95,
        )
        
        try:
            print(f"   🤖 Calling LLM for step: {step[:50]}...")
            response = self.client.models.generate_content(
                model=self.model,
                contents=[prompt],
                config=config,
            )
            print("   ✅ LLM response received")
            
            if not response.candidates or not response.candidates[0].content:
                print("   ❌ No candidates in response")
                raise RuntimeError("No response returned")
            
            response_text = response.candidates[0].content.parts[0].text.strip()
            print(f"   📄 Response text preview: {response_text[:100]}...")
            
            # Extract JSON from response
            json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if json_match:
                locators = json.loads(json_match.group())
                
                # Add source and ensure all required fields
                for loc in locators:
                    loc["source"] = "rag_generated"
                    loc["validated"] = False  # Will be validated by CDP
                    loc.setdefault("stability", "medium")
                    loc.setdefault("confidence", 0.5)
                
                # Locators generated successfully
                return locators
            else:
                # Fallback: generate basic locators from step text
                self.logger.warning(f"[LocatorGeneratorAgent] Failed to parse response, using fallback locators")
                return self._generate_fallback_locators(step)
                
        except Exception as e:
            self.logger.error(f"[LocatorGeneratorAgent] Error generating locators: {e}")
            return self._generate_fallback_locators(step)
    
    def _generate_fallback_locators(self, step: str) -> List[Dict[str, Any]]:
        """Generate basic fallback locators from step text."""
        step_lower = step.lower()
        locators = []
        
        # Extract potential element text
        if "button" in step_lower or "click" in step_lower:
            # Try to extract button text
            text_match = re.search(r'(?:click|press|select)\s+(?:the\s+)?["\']?([^"\']+)["\']?', step_lower)
            if text_match:
                button_text = text_match.group(1).strip()
                locators.append({
                    "type": "text",
                    "selector": f"button:has-text('{button_text}')",
                    "confidence": 0.6,
                    "stability": "medium",
                    "source": "fallback",
                    "validated": False,
                    "reasoning": "Generated from step text"
                })
            locators.append({
                "type": "tag",
                "selector": "button",
                "confidence": 0.3,
                "stability": "low",
                "source": "fallback",
                "validated": False,
                "reasoning": "Generic button selector"
            })
        elif "input" in step_lower or "fill" in step_lower or "enter" in step_lower:
            locators.append({
                "type": "tag",
                "selector": "input",
                "confidence": 0.4,
                "stability": "low",
                "source": "fallback",
                "validated": False,
                "reasoning": "Generic input selector"
            })
        elif "link" in step_lower or "navigate" in step_lower:
            locators.append({
                "type": "tag",
                "selector": "a",
                "confidence": 0.4,
                "stability": "low",
                "source": "fallback",
                "validated": False,
                "reasoning": "Generic link selector"
            })
        else:
            # Generic fallback
            locators.append({
                "type": "css",
                "selector": "[data-testid]",
                "confidence": 0.2,
                "stability": "low",
                "source": "fallback",
                "validated": False,
                "reasoning": "Generic test ID selector"
            })
        
        return locators

