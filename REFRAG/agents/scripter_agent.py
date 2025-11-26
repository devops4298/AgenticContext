#!/usr/bin/env python3
"""
scripter_agent.py — Scripter Agent for using CDP to find relevant DOM nodes.

Responsibilities:
- Execute each step using CDP Inspector (pure Python implementation)
- Use CDP tool to inspect pages and find DOM nodes
- Collect relevant DOM nodes for each step
- Return step-to-node mapping
"""

import logging
from typing import Dict, Any, List

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.rag import AppConfig
from tools.cdp_tool import CDPTool
from agents.locator_generator_agent import LocatorGeneratorAgent


class ScripterAgent:
    """Sub-agent responsible for using CDP to find relevant DOM nodes for each step."""
    
    def __init__(self, config: AppConfig, cdp_inspector_path: str = None):
        """
        Initialize ScripterAgent.
        
        Args:
            config: App configuration
            cdp_inspector_path: Not used (kept for compatibility, CDP is pure Python now)
        """
        self.cfg = config
        self.cdp_tool = CDPTool(cdp_inspector_path=cdp_inspector_path)
        self.locator_generator = LocatorGeneratorAgent(config)
        self.logger = logging.getLogger("ScripterAgent")
        # Note: CDPTool now validates locators and handles all edge cases
    
    def get_nodes_for_steps(self, steps: List[str], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute each step using CDP tool with RAG-generated locators.
        Process:
        1. Generate initial locators from RAG context for all steps
        2. Start CDP session
        3. For each step:
           a. Try RAG-generated locators
           b. If they fail, use CDP snapshot to find correct locators
           c. Update locators for the step
        4. Return nodes with validated/corrected locators
        
        Args:
            steps: List of steps
            context: Context from RagAgent (includes step_contexts with RAG answers)
        
        Returns:
            Dict with relevant nodes for each step, including validated locators
        """
        self.logger.info(f"[ScripterAgent] Getting nodes for {len(steps)} steps with RAG-generated locators")
        
        # Step 1: Generate initial locators from RAG context
        self.logger.info("[ScripterAgent] Step 1: Generating initial locators from RAG context")
        rag_locators = self.locator_generator.generate_locators_for_steps(steps, context)
        self.logger.info(f"[ScripterAgent] Generated locators for {len(rag_locators)} steps")
        
        # Extract URL from context - try multiple sources
        url = self._extract_url_from_context(context, steps)
        self.logger.info(f"[ScripterAgent] Extracted URL: {url if url else 'None'}")
        
        if not url:
            self.logger.warning("[ScripterAgent] No URL found in context or steps. CDP inspection will be skipped.")
            # Process without CDP session
            step_nodes = {}
            for i, step in enumerate(steps, 1):
                step_context = context.get("step_contexts", {}).get(f"step_{i}", {})
                # Note: We don't pass RAG answer to find_relevant_node because:
                # 1. URL is already extracted above
                # 2. RAG answer is documentation context, not page context
                # 3. find_relevant_node only uses context for URL extraction (which we already have)
                # The step description itself is sufficient for DOM node matching
                node_info = self.cdp_tool.find_relevant_node(step, context=None, url=url, use_session=True)
                step_nodes[f"step_{i}"] = {
                    "step": step,
                    "node": node_info,
                    "context": step_context  # Keep RAG context in result for script generation
                }
            return {
                "steps": steps,
                "step_nodes": step_nodes,
                "overall_context": context.get("overall_context", {}),
                "url_used": url
            }
        
        # Start a single CDP session for all steps
        session_started = False
        try:
            self.logger.info(f"[ScripterAgent] Starting single CDP session for all {len(steps)} steps")
            session_started = self.cdp_tool.start_session(url)
            
            if not session_started:
                self.logger.warning("[ScripterAgent] Failed to start CDP session, falling back to per-step inspection")
            
            step_nodes = {}
            snapshot = self.cdp_tool.current_snapshot
            
            for i, step in enumerate(steps, 1):
                step_key = f"step_{i}"
                step_context = context.get("step_contexts", {}).get(step_key, {})
                
                # Get RAG-generated locators for this step
                rag_locators_for_step = rag_locators.get(step_key, [])
                self.logger.info(f"[ScripterAgent] Processing step {i}/{len(steps)}: {step[:50]}...")
                
                # Skip navigation steps (no DOM locators needed)
                if not rag_locators_for_step:
                    self.logger.info(f"[ScripterAgent] Step {i} is navigation or has no locators, skipping CDP node finding")
                    step_nodes[step_key] = {
                        "step": step,
                        "node": {
                            "step": step,
                            "source": "navigation",
                            "element": None,
                            "locators": [],
                            "best_locator": None,
                            "rag_locators_used": [],
                            "rag_locators_worked": False
                        },
                        "context": step_context,
                        "rag_locators": []
                    }
                    continue
                
                self.logger.info(f"[ScripterAgent] Trying {len(rag_locators_for_step)} RAG-generated locators")
                print(f"\n{'='*80}")
                print(f"🔍 STEP {i}: {step}")
                print(f"{'='*80}")
                print(f"📋 RAG-Generated Locators ({len(rag_locators_for_step)}):")
                for j, loc in enumerate(rag_locators_for_step, 1):
                    print(f"   {j}. [{loc.get('type', 'unknown')}] {loc.get('selector', 'N/A')[:60]}")
                
                try:
                    # Step 2a: VALIDATION POINT 1 - Try to find node using RAG-generated locators
                    node = None
                    if rag_locators_for_step and session_started and snapshot:
                        print(f"\n🧪 VALIDATING RAG Locators on live page...")
                        self.logger.info(f"[ScripterAgent] Testing {len(rag_locators_for_step)} RAG-generated locators on live page...")
                        node = self.cdp_tool.find_node_by_locators(
                            rag_locators_for_step,
                            step,
                            snapshot
                        )
                    
                    if node:
                        print(f"✅ RAG Locators VALIDATED - Found node on page!")
                        self.logger.info(f"[ScripterAgent] ✅ Found node using RAG locators for step {i}")
                        
                        # Use RAG locators directly - no need to generate comprehensive locators
                        # Validate the RAG locators that worked
                        validated_rag_locators = []
                        
                        # Check if CDPTool returned the specific working locator
                        working_locator = node.get('working_locator')
                        
                        if working_locator:
                            print(f"   ✅ Identified specific working locator: {working_locator.get('selector')}")
                            validated_loc = working_locator.copy()
                            validated_loc['validated'] = True
                            validated_loc['validation_message'] = "✅ Found node on page"
                            validated_rag_locators.append(validated_loc)
                            best_rag_locator = validated_loc
                        else:
                            # Fallback: Mark all as validated (legacy behavior, risky)
                            for rag_loc in rag_locators_for_step:
                                validated_loc = rag_loc.copy()
                                validated_loc['validated'] = True
                                validated_loc['validation_message'] = "✅ Found node on page"
                                validated_rag_locators.append(validated_loc)
                            # Select best RAG locator
                            best_rag_locator = self._select_best_rag_locator(validated_rag_locators)
                            
                        print(f"\n⭐ Using RAG Locator: [{best_rag_locator.get('type', 'unknown')}] {best_rag_locator.get('selector', 'N/A')[:60]}")
                        print(f"   Validated: True | Stability: {best_rag_locator.get('stability', 'unknown')}")
                        
                        # Execute the action intended by the step
                        # CRITICAL: Use the EXACT locator that was validated by CDP
                        print(f"\n🎬 Executing action for step...")
                        print(f"   Using validated locator: [{best_rag_locator.get('type')}] {best_rag_locator.get('selector')[:60]}")
                        action_result = self.cdp_tool.execute_action(best_rag_locator, step)
                        if action_result.get('success'):
                            print(f"   ✅ {action_result.get('action', 'action').upper()}: {action_result.get('message', 'Success')}")
                        else:
                            print(f"   ⚠️  {action_result.get('action', 'action').upper()}: {action_result.get('message', 'Failed')}")
                        
                        node_info = {
                            "step": step,
                            "element": {
                                "nodeId": node.get('nodeId'),
                                "backendNodeId": node.get('backendNodeId'),
                                "nodeType": node.get('nodeType'),
                                "nodeName": node.get('nodeName', ''),
                                "localName": node.get('localName', ''),
                                "nodeValue": node.get('nodeValue', ''),
                                "parentId": node.get('parentId'),
                                "nodePath": node.get('nodePath', ''),
                                "attributes": node.get('attributes', {}),
                                "isVisible": node.get('isVisible', True),
                                "isInteractable": node.get('isInteractable', False),
                                "computedStyle": node.get('computedStyle', {}),
                                "boxModel": node.get('boxModel'),
                                "eventListeners": node.get('eventListeners', []),
                                "frameworkHints": node.get('frameworkHints', {}),
                                "runtime": node.get('runtime', {}),
                            },
                            "locators": validated_rag_locators,
                            "best_locator": best_rag_locator,
                            "rag_locators_used": rag_locators_for_step,
                            "rag_locators_worked": True,
                            "source": "rag_locators_validated",
                            "url": url,
                            "validation_performed": True,
                            "action_result": action_result  # Store action execution result
                        }
                        
                        # SELF-HEALING: If action failed, try to recover
                        if not action_result.get('success'):
                            print(f"\n🩹 SELF-HEALING: Action failed, attempting to recover...")
                            self.logger.info(f"[ScripterAgent] Action failed for step {i} (RAG path), attempting self-healing")
                            
                            # 1. Refresh snapshot
                            print(f"   📸 Refreshing page snapshot...")
                            snapshot = self.cdp_tool.inspect_page(url, keep_open=True)
                            
                            # 2. Re-verify locator on new snapshot
                            print(f"   🔍 Re-verifying locator on refreshed page...")
                            node = self.cdp_tool._find_node_in_snapshot_by_locator(
                                snapshot,
                                best_rag_locator.get('selector', ''),
                                best_rag_locator.get('type', 'css')
                            )
                            
                            if node:
                                print(f"   ✅ Node found after refresh!")
                                # 3. Retry action
                                print(f"   🔄 Retrying action...")
                                retry_result = self.cdp_tool.execute_action(best_rag_locator, step)
                                
                                if retry_result.get('success'):
                                    print(f"   ✅ RETRY SUCCESS: {retry_result.get('message', 'Success')}")
                                    node_info["action_result"] = retry_result
                                    node_info["self_healing_performed"] = True
                                    node_info["self_healing_success"] = True
                                else:
                                    print(f"   ❌ RETRY FAILED: {retry_result.get('message', 'Failed')}")
                                    node_info["self_healing_performed"] = True
                                    node_info["self_healing_success"] = False
                            else:
                                print(f"   ❌ Node NOT found after refresh. Locator might be stale.")
                                node_info["self_healing_performed"] = True
                                node_info["self_healing_success"] = False
                    else:
                        # Step 2b: CORRECTION POINT - RAG locators failed, use LLM to generate correct locator
                        print(f"\n❌ RAG Locators FAILED - All {len(rag_locators_for_step)} locators did not work on page")
                        print(f"🤖 Using LLM to generate correct locator from page elements...")
                        self.logger.warning(f"[ScripterAgent] ⚠ RAG locators failed for step {i}, using LLM to generate correct locator")
                        
                        # Extract visible and interactable elements from snapshot
                        visible_elements = self.cdp_tool.extract_visible_interactable_elements(snapshot)
                        print(f"   📊 Found {len(visible_elements)} visible and interactable elements on page")
                        
                        # Print the extracted elements for debugging
                        if visible_elements:
                            print(f"\n   📋 Extracted Elements:")
                            for i, elem in enumerate(visible_elements[:20], 1):  # Show first 20
                                elem_info = f"   {i}. {elem.get('tagName', 'unknown')}"
                                attrs = elem.get('attributes', {})
                                if attrs.get('id'):
                                    elem_info += f" id='{attrs['id']}'"
                                if attrs.get('name'):
                                    elem_info += f" name='{attrs['name']}'"
                                if attrs.get('data-testid'):
                                    elem_info += f" data-testid='{attrs['data-testid']}'"
                                if attrs.get('aria-label'):
                                    elem_info += f" aria-label='{attrs['aria-label']}'"
                                if attrs.get('placeholder'):
                                    elem_info += f" placeholder='{attrs['placeholder']}'"
                                if elem.get('textContent'):
                                    elem_info += f" text='{elem['textContent'][:40]}'"
                                print(elem_info)
                            if len(visible_elements) > 20:
                                print(f"   ... and {len(visible_elements) - 20} more elements")
                        
                        # Generate locator using LLM
                        llm_locator = self.cdp_tool.generate_locator_with_llm(
                            step,
                            rag_locators_for_step,
                            visible_elements,
                            url
                        )
                        
                        if llm_locator:
                            print(f"   ✅ LLM Generated Locator: [{llm_locator.get('type', 'unknown')}] {llm_locator.get('selector', 'N/A')[:60]}")
                            print(f"   💭 Reasoning: {llm_locator.get('reasoning', 'N/A')[:100]}")
                            
                            # Test the LLM-generated locator on active CDP session
                            if session_started and self.cdp_tool.current_tab:
                                print(f"   🧪 Testing LLM-generated locator on live page...")
                                locator_works = self.cdp_tool._test_locator(
                                    llm_locator.get('selector', ''),
                                    llm_locator.get('type', 'css')
                                )
                                
                                if locator_works:
                                    llm_locator['validated'] = True
                                    print(f"   ✅ Locator VALIDATED - Works on live page!")
                                    
                                    # Find the node using the validated locator
                                    node = self.cdp_tool._find_node_in_snapshot_by_locator(
                                        snapshot,
                                        llm_locator.get('selector', ''),
                                        llm_locator.get('type', 'css')
                                    )
                                    
                                    if node:
                                        # Use the LLM-generated locator directly since it was validated
                                        # Don't generate new locators - use what works!
                                        best_locator = llm_locator.copy()
                                        best_locator['validated'] = True
                                        
                                        node_info = {
                                            "step": step,
                                            "element": {
                                                "nodeId": node.get('nodeId'),
                                                "backendNodeId": node.get('backendNodeId'),
                                                "nodeType": node.get('nodeType'),
                                                "nodeName": node.get('nodeName', ''),
                                                "localName": node.get('localName', ''),
                                                "nodeValue": node.get('nodeValue', ''),
                                                "parentId": node.get('parentId'),
                                                "nodePath": node.get('nodePath', ''),
                                                "attributes": node.get('attributes', {}),
                                                "isVisible": node.get('isVisible', True),
                                                "isInteractable": node.get('isInteractable', False),
                                                "computedStyle": node.get('computedStyle', {}),
                                                "boxModel": node.get('boxModel'),
                                                "eventListeners": node.get('eventListeners', []),
                                                "frameworkHints": node.get('frameworkHints', {}),
                                                "runtime": node.get('runtime', {}),
                                            },
                                            "locators": [best_locator],  # Only the validated locator
                                            "best_locator": best_locator,
                                            "rag_locators_used": rag_locators_for_step,
                                            "rag_locators_worked": False,
                                            "llm_locator": llm_locator,
                                            "source": "llm_generated",
                                            "url": url,
                                            "validation_performed": True
                                        }
                                        
                                        # Execute the action with the validated LLM locator
                                        print(f"\n🎬 Executing action for step...")
                                        print(f"   Using LLM-validated locator: [{best_locator.get('type')}] {best_locator.get('selector')[:60]}")
                                        action_result = self.cdp_tool.execute_action(best_locator, step)
                                        if action_result.get('success'):
                                            print(f"   ✅ {action_result.get('action', 'action').upper()}: {action_result.get('message', 'Success')}")
                                        else:
                                            print(f"   ⚠️  {action_result.get('action', 'action').upper()}: {action_result.get('message', 'Failed')}")
                                        
                                        node_info["action_result"] = action_result
                                        
                                        # SELF-HEALING: If action failed, try to recover
                                        if not action_result.get('success'):
                                            print(f"\n🩹 SELF-HEALING: Action failed, attempting to recover...")
                                            self.logger.info(f"[ScripterAgent] Action failed for step {i} (LLM path), attempting self-healing")
                                            
                                            # 1. Refresh snapshot
                                            print(f"   📸 Refreshing page snapshot...")
                                            snapshot = self.cdp_tool.inspect_page(url, keep_open=True)
                                            
                                            # 2. Re-verify locator on new snapshot
                                            print(f"   🔍 Re-verifying locator on refreshed page...")
                                            node = self.cdp_tool._find_node_in_snapshot_by_locator(
                                                snapshot,
                                                best_locator.get('selector', ''),
                                                best_locator.get('type', 'css')
                                            )
                                            
                                            if node:
                                                print(f"   ✅ Node found after refresh!")
                                                # 3. Retry action
                                                print(f"   🔄 Retrying action...")
                                                retry_result = self.cdp_tool.execute_action(best_locator, step)
                                                
                                                if retry_result.get('success'):
                                                    print(f"   ✅ RETRY SUCCESS: {retry_result.get('message', 'Success')}")
                                                    node_info["action_result"] = retry_result
                                                    node_info["self_healing_performed"] = True
                                                    node_info["self_healing_success"] = True
                                                else:
                                                    print(f"   ❌ RETRY FAILED: {retry_result.get('message', 'Failed')}")
                                                    node_info["self_healing_performed"] = True
                                                    node_info["self_healing_success"] = False
                                            else:
                                                print(f"   ❌ Node NOT found after refresh. Locator might be stale.")
                                                node_info["self_healing_performed"] = True
                                                node_info["self_healing_success"] = False
                                    else:
                                        # Node not found in snapshot, use LLM locator directly
                                        node_info = {
                                            "step": step,
                                            "element": None,
                                            "locators": [llm_locator],
                                            "best_locator": llm_locator,
                                            "rag_locators_used": rag_locators_for_step,
                                            "rag_locators_worked": False,
                                            "llm_locator": llm_locator,
                                            "source": "llm_generated",
                                            "url": url,
                                            "validation_performed": True
                                        }
                                else:
                                    print(f"   ⚠️  Locator FAILED validation - does not work on live page")
                                    # Fall back to CDP snapshot search
                                    node_info = self.cdp_tool.find_relevant_node(
                                        step,
                                        context=None,
                                        url=url,
                                        use_session=session_started
                                    )
                                    if isinstance(node_info, dict):
                                        node_info["rag_locators_used"] = rag_locators_for_step
                                        node_info["rag_locators_worked"] = False
                                        node_info["llm_locator"] = llm_locator
                                        node_info["source"] = "llm_failed_cdp_fallback"
                            else:
                                # No active session, use LLM locator as-is
                                node_info = {
                                    "step": step,
                                    "element": None,
                                    "locators": [llm_locator],
                                    "best_locator": llm_locator,
                                    "rag_locators_used": rag_locators_for_step,
                                    "rag_locators_worked": False,
                                    "llm_locator": llm_locator,
                                    "source": "llm_generated",
                                    "url": url,
                                    "validation_performed": False
                                }
                        else:
                            # LLM generation failed, fall back to CDP snapshot search
                            print(f"   ⚠️  LLM locator generation failed, falling back to CDP snapshot search")
                            node_info = self.cdp_tool.find_relevant_node(
                                step,
                                context=None,
                                url=url,
                                use_session=session_started
                            )
                            if isinstance(node_info, dict):
                                node_info["rag_locators_used"] = rag_locators_for_step
                                node_info["rag_locators_worked"] = False
                                node_info["source"] = "cdp_corrected"
                                
                                # Show corrected locators
                                corrected_locators = node_info.get("locators", [])
                                if corrected_locators:
                                    print(f"\n✅ CORRECTED: Found {len(corrected_locators)} new locators from CDP snapshot")
                                    validated_count = sum(1 for loc in corrected_locators if loc.get('validated', False))
                                    print(f"   ✅ {validated_count}/{len(corrected_locators)} locators validated")
                                    best_corrected = node_info.get("best_locator", {})
                                    if best_corrected:
                                        print(f"   ⭐ Best Corrected Locator: [{best_corrected.get('type', 'unknown')}] {best_corrected.get('selector', 'N/A')[:60]}")
                                        
                                        # Execute the action intended by the step
                                        print(f"\n🎬 Executing action for step...")
                                        action_result = self.cdp_tool.execute_action(best_corrected, step)
                                        if action_result.get('success'):
                                            print(f"   ✅ {action_result.get('action', 'action').upper()}: {action_result.get('message', 'Success')}")
                                        else:
                                            print(f"   ⚠️  {action_result.get('action', 'action').upper()}: {action_result.get('message', 'Failed')}")
                                        
                                        # Store action result in node_info
                                        node_info["action_result"] = action_result
                                        
                                        # SELF-HEALING: If action failed, try to recover
                                        if not action_result.get('success'):
                                            print(f"\n🩹 SELF-HEALING: Action failed, attempting to recover...")
                                            self.logger.info(f"[ScripterAgent] Action failed for step {i}, attempting self-healing")
                                            
                                            # 1. Refresh snapshot
                                            print(f"   📸 Refreshing page snapshot...")
                                            snapshot = self.cdp_tool.inspect_page(url, keep_open=True)
                                            
                                            # 2. Re-verify locator on new snapshot
                                            print(f"   🔍 Re-verifying locator on refreshed page...")
                                            node = self.cdp_tool._find_node_in_snapshot_by_locator(
                                                snapshot,
                                                best_corrected.get('selector', ''),
                                                best_corrected.get('type', 'css')
                                            )
                                            
                                            if node:
                                                print(f"   ✅ Node found after refresh!")
                                                # 3. Retry action
                                                print(f"   🔄 Retrying action...")
                                                retry_result = self.cdp_tool.execute_action(best_corrected, step)
                                                
                                                if retry_result.get('success'):
                                                    print(f"   ✅ RETRY SUCCESS: {retry_result.get('message', 'Success')}")
                                                    node_info["action_result"] = retry_result
                                                    node_info["self_healing_performed"] = True
                                                    node_info["self_healing_success"] = True
                                                else:
                                                    print(f"   ❌ RETRY FAILED: {retry_result.get('message', 'Failed')}")
                                                    node_info["self_healing_performed"] = True
                                                    node_info["self_healing_success"] = False
                                            else:
                                                print(f"   ❌ Node NOT found after refresh. Locator might be stale.")
                                                node_info["self_healing_performed"] = True
                                                node_info["self_healing_success"] = False
                    
                    self.logger.info(f"[ScripterAgent] Step {i} node found: {node_info.get('source', 'unknown')}")
                    
                except Exception as e:
                    self.logger.error(f"[ScripterAgent] Error finding node for step {i}: {e}")
                    node_info = {
                        "step": step,
                        "error": str(e),
                        "source": "error",
                        "rag_locators_used": rag_locators_for_step,
                        "rag_locators_worked": False
                    }
                
                step_nodes[step_key] = {
                    "step": step,
                    "node": node_info,
                    "context": step_context,
                    "rag_locators": rag_locators_for_step  # Keep original RAG locators for reference
                }
            
            return {
                "steps": steps,
                "step_nodes": step_nodes,
                "overall_context": context.get("overall_context", {}),
                "url_used": url
            }
        
        finally:
            # Always close the session when done
            if session_started:
                self.logger.info("[ScripterAgent] Closing CDP session after processing all steps")
                self.cdp_tool.close_session()
    
    def _extract_url_from_context(self, context: Dict[str, Any], steps: List[str] = None) -> str:
        """Extract URL from context, steps, or user request."""
        import re
        
        url_pattern = r'(https?://[^\s\)]+|www\.[^\s\)]+|localhost:\d+)'
        
        # First, check steps (most likely to have URL)
        if steps:
            for step in steps:
                urls = re.findall(url_pattern, step)
                if urls:
                    url = urls[0]
                    if not url.startswith('http'):
                        url = f"http://{url}"
                    self.logger.info(f"[ScripterAgent] Found URL in step: {url}")
                    return url
        
        # Check user request
        user_request = context.get("user_request", "")
        if user_request:
            urls = re.findall(url_pattern, user_request)
            if urls:
                url = urls[0]
                if not url.startswith('http'):
                    url = f"http://{url}"
                self.logger.info(f"[ScripterAgent] Found URL in user_request: {url}")
                return url
        
        # Check overall context
        overall_context = context.get("overall_context", {})
        if overall_context.get("answer"):
            urls = re.findall(url_pattern, overall_context["answer"])
            if urls:
                url = urls[0]
                if not url.startswith('http'):
                    url = f"https://{url}"
                self.logger.info(f"[ScripterAgent] Found URL in overall_context: {url}")
                return url
        
        return ""
    
    def _select_best_rag_locator(self, locators: List[Dict]) -> Dict:
        """
        Select the best locator from RAG-generated locators.
        Prioritizes stable locators (data-testid, id, name, aria-label) over unstable ones (class, xpath, tag).
        """
        if not locators:
            return {}
        
        # Priority order: data-testid > id > name > aria-label > role > xpath > class > tag
        priority_map = {
            'attribute': 1,  # data-testid, etc.
            'id': 2,
            'name': 3,
            'aria-label': 4,
            'role': 5,
            'xpath': 6,
            'class': 7,
            'tag': 8
        }
        
        # Sort by priority, then by confidence, then by stability
        def sort_key(loc):
            loc_type = loc.get('type', 'tag')
            priority = priority_map.get(loc_type, 9)
            confidence = loc.get('confidence', 0)
            stability_score = {'high': 3, 'medium': 2, 'low': 1}.get(loc.get('stability', 'low'), 0)
            return (priority, -confidence, -stability_score)
        
        sorted_locators = sorted(locators, key=sort_key)
        return sorted_locators[0] if sorted_locators else locators[0]

