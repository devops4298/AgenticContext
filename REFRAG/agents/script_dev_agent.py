#!/usr/bin/env python3
"""
script_dev_agent.py — Script Development Agent for generating automation scripts.

Responsibilities:
- Ask user for automation tool preference
- Generate test script using LLM
- Use context + nodes + steps
- Format and deliver final script
"""

import sys
import logging
import json
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


class ScriptDevelopmentAgent:
    """Sub-agent responsible for generating automation scripts."""
    
    def __init__(self, config: AppConfig):
        self.cfg = config
        self.logger = logging.getLogger("ScriptDevelopmentAgent")
        if not self.cfg.google_ai_api_key:
            raise ValueError("GOOGLE_AI_API_KEY required for ScriptDevelopmentAgent")
        
        self.client = genai.Client(api_key=self.cfg.google_ai_api_key)
        self.model = self.cfg.text_model
    
    def ask_automation_tool(self) -> str:
        """
        Ask user which automation tool to use.
        In production, this would be handled by the UI.
        
        Returns:
            Selected automation tool (e.g., "playwright")
        """
        # For now, default to playwright
        # In production, this would prompt the user via UI
        return "playwright"
    
    def generate_script(self, steps: List[str], step_nodes: Dict[str, Any], 
                       context: Dict[str, Any], automation_tool: str = "playwright") -> str:
        """
        Generate automation script using LLM.
        
        Args:
            steps: List of steps
            step_nodes: Relevant nodes for each step
            context: Context from RAG
            automation_tool: Automation tool to use (e.g., "playwright")
        
        Returns:
            Generated script as string
        """
        # Generating automation script
        
        # Format context for script generation
        context_text = self._format_context_for_script(steps, step_nodes, context)
        
        prompt = f"""Generate a complete {automation_tool} automation script based on the following requirements.

USER REQUEST:
{context.get('user_request', '')}

STEPS TO AUTOMATE:
{chr(10).join(f'{i}. {step}' for i, step in enumerate(steps, 1))}

RELEVANT DOM NODES FOR EACH STEP:
{self._format_nodes_for_script(step_nodes)}

CONTEXT FROM DOCUMENTATION:
{context_text}

CRITICAL REQUIREMENTS - PLAYWRIGHT BEST PRACTICES:

1. **USE SEMANTIC LOCATORS ONLY** - Do NOT use generic `page.locator()` unless absolutely necessary.
   You MUST use Playwright's semantic locator methods based on the node information provided:
   
   - **getByRole()**: For buttons, links, textboxes, etc. with accessible roles
     Example: `page.get_by_role("button", name="Post")`
     Example: `page.get_by_role("link", name="Contact")`
     Example: `page.get_by_role("textbox", name="Email")`
   
   - **getByText()**: For elements with visible text (links, buttons, labels)
     Example: `page.get_by_text("Contact")`
     Example: `page.get_by_text("Post", exact=True)`
   
   - **getByLabel()**: For form inputs with associated labels
     Example: `page.get_by_label("Name")`
     Example: `page.get_by_label("Email address")`
   
   - **getByPlaceholder()**: For inputs with placeholder text
     Example: `page.get_by_placeholder("Enter your email")`
   
   - **getByTestId()**: For elements with data-testid attributes
     Example: `page.get_by_test_id("submit-button")`

2. **MAPPING NODE DATA TO SEMANTIC LOCATORS**:
   - If node has `role` attribute → use `get_by_role(role, name=text_or_label)`
   - If node has visible text content → use `get_by_text(text)`
   - If node has `aria-label` → use `get_by_role(role, name=aria_label)`
   - If node has `placeholder` → use `get_by_placeholder(placeholder)`
   - If node has associated label → use `get_by_label(label_text)`
   - If node has `data-testid` → use `get_by_test_id(testid)`

3. **EXAMPLES - CORRECT USAGE**:
   
   For a link with text "Contact":
   ```python
   await page.get_by_role("link", name="Contact").click()
   # OR
   await page.get_by_text("Contact").click()
   ```
   
   For a button with text "Post":
   ```python
   await page.get_by_role("button", name="Post").click()
   ```
   
   For an input with placeholder "Enter your name":
   ```python
   await page.get_by_placeholder("Enter your name").fill("John Doe")
   ```
   
   For an input with label "Email":
   ```python
   await page.get_by_label("Email").fill("test@example.com")
   ```

4. **FALLBACK TO LOCATOR ONLY IF**:
   - The "Best Locator" provided is a CSS selector or XPath that cannot be converted to semantic locators
   - In this case, use the exact locator provided:
     - XPath: `page.locator("xpath=//button[@class='submit']")`
     - CSS: `page.locator(".bg-primeColor")`

5. **GENERAL REQUIREMENTS**:
   - Use {automation_tool} Python async API
   - Include proper imports: `from playwright.async_api import async_playwright`
   - Use `async def main()` pattern
   - Include error handling with try/except for each action
   - Add print statements after each action for debugging
   - For navigation: `await page.goto("url")`
   - Match exact terminology from documentation context

6. **DO NOT MAKE ASSUMPTIONS**:
   - Use the node information provided to determine the correct semantic locator
   - If unsure, prefer `get_by_text()` or `get_by_role()` over generic selectors
   - Never use `.nth()` or generic `input` selectors if semantic locators are available

Generate ONLY the Python script code, no explanations before or after."""

        config = GenerateContentConfig(
            temperature=0.2,
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
                raise RuntimeError("No response returned")
            
            script = response.candidates[0].content.parts[0].text.strip()
            
            # Clean up markdown code blocks if present
            if "```python" in script:
                script = script.split("```python")[1].split("```")[0].strip()
            elif "```" in script:
                script = script.split("```")[1].split("```")[0].strip()
            
            if not script or len(script) < 50:
                self.logger.warning(f"[ScriptDevelopmentAgent] Generated script seems too short ({len(script)} chars)")
            
            # Script generated successfully
            return script
            
        except Exception as e:
            self.logger.error(f"Script generation failed: {e}")
            return f"# Error generating script: {str(e)}\n# Please provide more details about the automation task."
    
    def _format_context_for_script(self, steps: List[str], step_nodes: Dict[str, Any], 
                                   context: Dict[str, Any]) -> str:
        """Format context for script generation."""
        formatted = []
        
        overall_context = context.get("overall_context", {})
        if overall_context.get("answer"):
            formatted.append(f"# Overall Context:\n{overall_context['answer']}\n")
        
        if overall_context.get("retrieved"):
            formatted.append("\n# Relevant Code/Context Snippets:\n")
            for i, chunk in enumerate(overall_context["retrieved"][:5], 1):
                path = chunk.get("path", "unknown")
                text = chunk.get("text", "")[:500]
                formatted.append(f"## {path}\n```\n{text}\n```\n")
        
        return "\n".join(formatted)
    
    def _format_nodes_for_script(self, step_nodes: Dict[str, Any]) -> str:
        """Format node information for script generation using complete element JSON."""
        formatted = []
        
        for step_key, step_data in step_nodes.items():
            step = step_data.get("step", "")
            node = step_data.get("node", {})
            
            # Get complete element data (ComprehensiveElementData)
            # Handle case where element might be None
            element = node.get("element")
            if element is None:
                element = {}
            
            formatted.append(f"\n## {step_key}: {step}")
            
            # Element basic info - safely handle None element
            if element:
                formatted.append(f"  Node Name: {element.get('nodeName', node.get('node_name', 'N/A'))}")
                formatted.append(f"  Local Name: {element.get('localName', 'N/A')}")
                formatted.append(f"  Node Type: {element.get('nodeType', 'N/A')}")
            else:
                # Fallback to node-level data if element is missing
                formatted.append(f"  Node Name: {node.get('node_name', 'N/A')}")
                formatted.append(f"  Local Name: N/A")
                formatted.append(f"  Node Type: N/A")
            
            # Complete attributes - safely handle None element
            if element:
                attributes = element.get("attributes", node.get("attributes", {}))
            else:
                attributes = node.get("attributes", {})
            
            if attributes:
                formatted.append(f"  Attributes: {json.dumps(attributes, indent=4)}")
            
            # Locators (all strategies, not just one)
            locators = node.get("locators", [])
            if locators:
                formatted.append(f"  Available Locators ({len(locators)} strategies):")
                for i, loc in enumerate(locators, 1):
                    validated = "✓" if loc.get('validated', False) else "✗"
                    formatted.append(f"    {i}. [{loc.get('type', 'unknown')}] {loc.get('selector', 'N/A')} "
                                   f"(confidence: {loc.get('confidence', 0)}, stability: {loc.get('stability', 'unknown')}, validated: {validated})")
            
            # Best locator (for convenience)
            best_locator = node.get("best_locator", {})
            if best_locator:
                formatted.append(f"  Best Locator: [{best_locator.get('type', 'unknown')}] {best_locator.get('selector', 'N/A')}")
            
            # XPath (nodePath) - safely handle None element
            if element:
                xpath = element.get("nodePath", node.get("xpath", ""))
            else:
                xpath = node.get("xpath", "")
            
            if xpath:
                formatted.append(f"  XPath: {xpath}")
            
            # Visibility and interactability
            formatted.append(f"  Visible: {element.get('isVisible', node.get('is_visible', 'N/A'))}")
            formatted.append(f"  Interactable: {element.get('isInteractable', node.get('is_interactable', 'N/A'))}")
            
            # Runtime data (textContent, etc.)
            runtime = element.get("runtime", {})
            if runtime:
                text_content = runtime.get("textContent", "")
                if text_content:
                    formatted.append(f"  Text Content: {text_content[:100]}")
            
            # Computed styles (if available)
            computed_style = element.get("computedStyle", {})
            if computed_style:
                formatted.append(f"  Computed Styles: {json.dumps(computed_style, indent=4)}")
            
            # Framework hints (React, Angular, Vue)
            framework_hints = element.get("frameworkHints", {})
            if framework_hints:
                formatted.append(f"  Framework Hints: {json.dumps(framework_hints, indent=4)}")
            
            # Box model (position/size)
            box_model = element.get("boxModel")
            if box_model:
                formatted.append(f"  Box Model: {json.dumps(box_model, indent=4)}")
            
            # Legacy fields (for backward compatibility)
            if node.get("node_selector"):
                formatted.append(f"  (Legacy) Selector: {node.get('node_selector')}")
        
        return "\n".join(formatted)

