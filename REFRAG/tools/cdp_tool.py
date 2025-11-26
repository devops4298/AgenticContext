#!/usr/bin/env python3
"""
cdp_tool.py — Pure Python implementation of CDP Inspector

Replaces the TypeScript inspector.ts with native Python CDP control
"""

import subprocess
import json
import time
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict

# Using pychrome for CDP communication
try:
    import pychrome
except ImportError:
    import sys
    print("Installing pychrome...")
    try:
        # Try pip3 first, then pip
        subprocess.run([sys.executable, "-m", "pip", "install", "pychrome"], check=True)
        import pychrome
    except Exception as e:
        print(f"Failed to install pychrome automatically: {e}")
        print("Please install manually: pip3 install pychrome")
        raise

try:
    import requests
except ImportError:
    import sys
    print("Installing requests...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "requests"], check=True)
        import requests
    except Exception as e:
        print(f"Failed to install requests automatically: {e}")
        print("Please install manually: pip3 install requests")
        raise


@dataclass
class LocatorStrategy:
    """Locator strategy for an element"""
    type: str  # 'id', 'xpath', 'css', 'attribute'
    selector: str
    confidence: float


@dataclass
class FrameworkHints:
    """Detected framework hints"""
    react: bool = False
    angular: bool = False
    vue: bool = False


@dataclass
class ComprehensiveElementData:
    """Complete element data structure"""
    nodeId: int
    backendNodeId: int
    nodeType: int
    nodeName: str
    localName: str
    nodeValue: str
    parentId: Optional[int]
    nodePath: str
    attributes: Dict[str, str]
    isVisible: bool
    isInteractable: bool
    locators: List[LocatorStrategy] = field(default_factory=list)
    computedStyle: Dict[str, str] = field(default_factory=dict)
    boxModel: Optional[Dict] = None
    eventListeners: List[str] = field(default_factory=list)
    frameworkHints: FrameworkHints = field(default_factory=FrameworkHints)
    runtime: Dict[str, Any] = field(default_factory=dict)


class CDPInspector:
    """Pure Python CDP Inspector - replaces TypeScript implementation"""
    
    def __init__(self, chrome_path: str = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
        self.chrome_path = chrome_path
        self.port = 9222
        self.chrome_process = None
        self.browser = None
        self.tab = None
        self._tab_for_validation = None  # Keep tab reference for validation
        self.nodes: List[ComprehensiveElementData] = []
        self.processed_backend_ids = set()
        self.logger = logging.getLogger("CDPInspector")
    
    def _kill_existing_chrome(self):
        """Kill any existing Chrome processes on the debugging port"""
        try:
            subprocess.run(
                ["pkill", "-f", f"remote-debugging-port={self.port}"],
                timeout=5,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1)
        except:
            pass
    
    def launch_chrome(self):
        """Launch Chrome with remote debugging"""
        import tempfile
        
        # Kill any existing Chrome on this port
        self._kill_existing_chrome()
        
        user_data_dir = tempfile.mkdtemp(prefix="chrome-cdp-")
        
        try:
            self.chrome_process = subprocess.Popen(
                [
                    self.chrome_path,
                    # Removed --headless=new to enable HEADED mode (visible browser)
                    f'--remote-debugging-port={self.port}',
                    f'--user-data-dir={user_data_dir}',
                    '--no-first-run',
                    '--no-default-browser-check',
                    '--disable-background-networking',
                    '--disable-client-side-phishing-detection',
                    '--disable-default-apps',
                    '--disable-extensions',
                    # Removed --disable-gpu to allow rendering
                    '--disable-sync',
                    '--window-size=1280,800',  # Set visible window size
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            # Wait for Chrome to start with retries
            max_retries = 10
            for i in range(max_retries):
                time.sleep(0.5)
                try:
                    response = requests.get(f"http://127.0.0.1:{self.port}/json/version", timeout=1)
                    if response.status_code == 200:
                        self.logger.info("Chrome started successfully")
                        return
                except:
                    continue
            
            raise Exception("Chrome failed to start")
            
        except Exception as e:
            if self.chrome_process:
                self.chrome_process.kill()
            raise Exception(f"Failed to launch Chrome: {e}")
    
    def connect(self):
        """Connect to Chrome via CDP"""
        try:
            self.browser = pychrome.Browser(url=f"http://127.0.0.1:{self.port}")
            
            # Get or create tab with retries
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    tabs = self.browser.list_tab()
                    if tabs:
                        self.tab = tabs[0]
                    else:
                        self.tab = self.browser.new_tab()
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    time.sleep(1)
            
            # Start the tab
            self.tab.start()
            
            # Enable necessary domains
            self.tab.DOM.enable()
            self.tab.Page.enable()
            self.tab.Network.enable()
            self.tab.CSS.enable()
            self.tab.Runtime.enable()
            
            # Try to enable Input domain (not always available in all Chrome versions)
            try:
                self.tab.Input.enable()
            except Exception as e:
                self.logger.warning(f"[CDPInspector] Input domain not available: {e}. Actions may not work.")
            
            # Store tab reference for validation
            self._tab_for_validation = self.tab
            
        except Exception as e:
            raise Exception(f"Failed to connect to Chrome: {e}")
    
    def inspect(self, url: str) -> Dict[str, Any]:
        """
        Inspect a URL and return comprehensive DOM snapshot
        
        Args:
            url: URL to inspect
            
        Returns:
            Dict with url, timestamp, and nodes
        """
        try:
            # Set up event listener for page load
            page_loaded = False
            
            def page_load_handler(**kwargs):
                nonlocal page_loaded
                page_loaded = True
            
            self.tab.Page.loadEventFired = page_load_handler
            
            # Navigate to URL
            self.logger.info(f"Navigating to {url}...")
            self.tab.Page.navigate(url=url)
            
            # Wait for page to load (with timeout)
            timeout = 10
            start_time = time.time()
            while not page_loaded and (time.time() - start_time) < timeout:
                time.sleep(0.1)
            
            # Additional wait for network idle
            time.sleep(2)
            
            # Get DOM document
            doc = self.tab.DOM.getDocument(depth=-1, pierce=True)
            root = doc['root']
            
            # Reset state
            self.nodes = []
            self.processed_backend_ids.clear()
            
            # Traverse DOM
            self._traverse(root, None, '')
            
            return {
                'url': url,
                'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime()),
                'nodes': [asdict(node) for node in self.nodes]
            }
            
        except Exception as e:
            self.logger.error(f"Error during inspection: {e}")
            raise
    
    def _traverse(self, node: Dict, parent_id: Optional[int], parent_path: str):
        """Recursively traverse DOM tree"""
        backend_id = node.get('backendNodeId')
        if backend_id in self.processed_backend_ids:
            return
        
        self.processed_backend_ids.add(backend_id)
        
        # Process current node
        node_path = self._get_node_path(node, parent_path)
        element_data = self._process_node(node, parent_id, node_path)
        
        if element_data:
            self.nodes.append(element_data)
        
        # Traverse children
        if 'children' in node:
            for child in node['children']:
                self._traverse(child, node.get('nodeId'), node_path)
        
        # Traverse shadow roots
        if 'shadowRoots' in node:
            for shadow_root in node['shadowRoots']:
                self._traverse(shadow_root, node.get('nodeId'), node_path)
        
        # Traverse iframes
        if node.get('nodeName') == 'IFRAME' and 'contentDocument' in node:
            self._traverse(node['contentDocument'], node.get('nodeId'), node_path)
    
    def _process_node(self, node: Dict, parent_id: Optional[int], node_path: str) -> Optional[ComprehensiveElementData]:
        """Process a single node and extract all data"""
        attributes = self._parse_attributes(node.get('attributes', []))
        
        node_type = node.get('nodeType', 0)
        node_id = node.get('nodeId', 0)
        
        # Basic data for all node types
        if node_type not in [1, 3, 9]:  # Not element, text, or document
            return ComprehensiveElementData(
                nodeId=node_id,
                backendNodeId=node.get('backendNodeId', 0),
                nodeType=node_type,
                nodeName=node.get('nodeName', ''),
                localName=node.get('localName', ''),
                nodeValue=node.get('nodeValue', ''),
                parentId=parent_id,
                nodePath=node_path,
                attributes=attributes,
                isVisible=True,
                isInteractable=False
            )
        
        # Element-specific processing
        is_visible = True
        computed_style = {}
        box_model = None
        event_listeners = []
        
        if node_type == 1:  # Element node
            # Get computed style
            try:
                style_result = self.tab.CSS.getComputedStyleForNode(nodeId=node_id)
                for prop in style_result['computedStyle']:
                    if prop['name'] in ['display', 'visibility', 'opacity', 'z-index', 'position']:
                        computed_style[prop['name']] = prop['value']
                
                # Determine visibility
                if (computed_style.get('display') == 'none' or 
                    computed_style.get('visibility') == 'hidden' or 
                    computed_style.get('opacity') == '0'):
                    is_visible = False
            except:
                pass
            
            # Get box model
            try:
                box_result = self.tab.DOM.getBoxModel(nodeId=node_id)
                box_model = box_result['model']
            except:
                is_visible = False
            
            # Get event listeners
            try:
                obj_result = self.tab.DOM.resolveNode(nodeId=node_id)
                if 'object' in obj_result:
                    # Note: DOMDebugger.getEventListeners might not be available
                    # Skipping for now to avoid errors
                    pass
            except:
                pass
        
        # Framework hints
        framework_hints = FrameworkHints()
        if 'data-reactroot' in attributes or any(k.startswith('data-react') for k in attributes):
            framework_hints.react = True
        if any(k.startswith('ng-') for k in attributes):
            framework_hints.angular = True
        if any(k.startswith('v-') for k in attributes):
            framework_hints.vue = True
        
        # Generate basic locators (will be enhanced later)
        locators = []
        if node_type == 1:
            if 'id' in attributes:
                locators.append(LocatorStrategy('id', f"#{attributes['id']}", 1.0))
            if 'data-testid' in attributes:
                locators.append(LocatorStrategy('attribute', f"[data-testid=\"{attributes['data-testid']}\"]", 1.0))
            locators.append(LocatorStrategy('xpath', node_path, 1.0))
            locators.append(LocatorStrategy('css', node.get('localName', ''), 0.1))
        
        # Get text content
        text_content = None
        if node_type == 1:
            try:
                obj_result = self.tab.DOM.resolveNode(nodeId=node_id)
                if 'object' in obj_result:
                    result = self.tab.Runtime.callFunctionOn(
                        objectId=obj_result['object']['objectId'],
                        functionDeclaration='function() { return this.textContent; }',
                        returnByValue=True
                    )
                    if 'result' in result and 'value' in result['result']:
                        text_content = result['result']['value']
            except Exception as e:
                # Log failure to extract text content
                self.logger.debug(f"Failed to extract text content for node {node_id}: {e}")
                pass
        elif node_type == 3:
            text_content = node.get('nodeValue', '')
            
        # DEBUG: Log text content for specific elements
        if node.get('nodeName') in ['A', 'BUTTON', 'SPAN'] and text_content and 'contact' in text_content.lower():
            self.logger.info(f"[CDPTool] Extracted text for {node.get('nodeName')}: '{text_content}'")
        
        # Determine interactability
        is_interactable = (
            is_visible and 
            (len(event_listeners) > 0 or 
             node.get('nodeName', '') in ['BUTTON', 'A', 'INPUT', 'SELECT'])
        )
        
        return ComprehensiveElementData(
            nodeId=node_id,
            backendNodeId=node.get('backendNodeId', 0),
            nodeType=node_type,
            nodeName=node.get('nodeName', ''),
            localName=node.get('localName', ''),
            nodeValue=node.get('nodeValue', ''),
            parentId=parent_id,
            nodePath=node_path,
            attributes=attributes,
            isVisible=is_visible,
            computedStyle=computed_style,
            boxModel=box_model,
            eventListeners=event_listeners,
            isInteractable=is_interactable,
            frameworkHints=framework_hints,
            locators=locators,
            runtime={'textContent': text_content}
        )
    
    def _parse_attributes(self, attrs: List[str]) -> Dict[str, str]:
        """Parse attribute array into dict"""
        result = {}
        for i in range(0, len(attrs), 2):
            if i + 1 < len(attrs):
                result[attrs[i]] = attrs[i + 1]
        return result
    
    def _get_node_path(self, node: Dict, parent_path: str) -> str:
        """Generate XPath-like node path"""
        if node.get('nodeType') == 9:  # Document
            return ''
        local_name = node.get('localName') or node.get('nodeName')
        return f"{parent_path}/{local_name}"
    
    def close(self):
        """Cleanup resources"""
        if self.tab:
            try:
                self.tab.stop()
            except:
                pass
        
        if self.chrome_process:
            self.chrome_process.terminate()
            self.chrome_process.wait()


class CDPTool:
    """High-level CDP tool interface for finding relevant DOM nodes.
    
    Enhanced with:
    - Locator validation/testing before returning
    - Comprehensive edge case handling (dynamic IDs, shadow DOM, etc.)
    - Stability scoring for locators
    - Multiple locator strategies with validation
    - Session management for reusing CDP connections across multiple steps
    """
    
    def __init__(self, cdp_inspector_path: Optional[str] = None):
        """
        Initialize CDP tool.
        
        Args:
            cdp_inspector_path: Not used in pure Python implementation (kept for compatibility)
        """
        self.logger = logging.getLogger("CDPTool")
        # Ensure logger is configured (if not already)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('%(asctime)s [CDPTool] %(levelname)s: %(message)s'))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
        self.inspector = None
        self.current_tab = None  # Keep tab open for locator testing
        self.current_snapshot = None  # Cache snapshot for session reuse
        self.current_url = None  # Track current URL
        self.session_active = False  # Track if session is active
    
    def start_session(self, url: str) -> bool:
        """
        Start a persistent CDP session for a URL.
        This should be called once before processing multiple steps.
        
        Args:
            url: URL to inspect and keep session open for
        
        Returns:
            True if session started successfully, False otherwise
        """
        try:
            self.logger.info(f"[CDPTool] Starting persistent CDP session for {url}")
            snapshot = self.inspect_page(url, keep_open=True)
            self.current_snapshot = snapshot
            self.current_url = url
            self.session_active = True
            self.logger.info(f"[CDPTool] Session started. Found {len(snapshot.get('nodes', []))} nodes")
            return True
        except Exception as e:
            self.logger.error(f"[CDPTool] Failed to start session: {e}")
            self.session_active = False
            return False
    
    def close_session(self):
        """Close the persistent CDP session."""
        try:
            if self.inspector:
                self.logger.info("[CDPTool] Closing CDP session")
                self.inspector.close()
                self.inspector = None
                self.current_tab = None
                self.current_snapshot = None
                self.current_url = None
                self.session_active = False
                self.logger.info("[CDPTool] Session closed")
        except Exception as e:
            self.logger.warning(f"[CDPTool] Error closing session: {e}")
            self.session_active = False
    
    def find_relevant_node(self, step: str, context: Optional[str] = None, 
                          url: Optional[str] = None, validate_locators: bool = True,
                          use_session: bool = True) -> Dict[str, Any]:
        """
        Use CDP to find relevant DOM node for a specific step.
        Now with locator validation and comprehensive edge case handling.
        Can reuse an active session if available.
        
        Args:
            step: Step description
            context: Optional context about the page
            url: Optional URL to navigate to (only used if no active session)
            validate_locators: Test locators on the page before returning
            use_session: If True, reuse active session if available
        
        Returns:
            Dict with node information including validated locators
        """
        # Log only once (avoid duplicate logs)
        if not hasattr(self, '_last_logged_step') or self._last_logged_step != step:
            self.logger.info("=" * 80)
            self.logger.info(f"[CDPTool] ===== FIND_RELEVANT_NODE START =====")
            self.logger.info(f"[CDPTool] Step: {step[:100]}")
            self.logger.info(f"[CDPTool] Context provided: {bool(context)}")
            self.logger.info(f"[CDPTool] URL provided: {url}")
            self.logger.info(f"[CDPTool] Use session: {use_session}, Session active: {self.session_active}")
            self._last_logged_step = step
        
        # Use active session if available
        if use_session and self.session_active and self.current_snapshot:
            self.logger.info(f"[CDPTool] ✓ Reusing active CDP session for {self.current_url}")
            self.logger.info(f"[CDPTool] Cached snapshot has {len(self.current_snapshot.get('nodes', []))} nodes")
            snapshot = self.current_snapshot
            url = self.current_url
        else:
            # Extract URL from step or context if not provided
            if not url:
                url = self._extract_url_from_step(step, context)
                self.logger.info(f"[CDPTool] Extracted URL from step/context: {url}")
            
            if not url:
                # Fallback to inference if no URL
                self.logger.warning("[CDPTool] No URL found, using inference fallback")
                return self._infer_node_from_step(step, context)
            
            try:
                self.logger.info(f"[CDPTool] Starting CDP inspection of {url}")
                # Inspect the page (keep inspector open for validation)
                snapshot = self.inspect_page(url, keep_open=validate_locators)
                self.logger.info(f"[CDPTool] CDP inspection complete. Found {len(snapshot.get('nodes', []))} nodes")
            except Exception as e:
                import traceback
                error_msg = f"CDP inspection failed: {e}"
                self.logger.error(f"[CDPTool] {error_msg}")
                self.logger.error(f"[CDPTool] Traceback: {traceback.format_exc()}")
                # Return error with fallback inference
                fallback_result = self._infer_node_from_step(step, context)
                fallback_result["error"] = str(e)
                fallback_result["source"] = "cdp_error"
                return fallback_result
        
        try:
            
            # Find nodes matching the step description with enhanced edge case handling
            self.logger.info(f"[CDPTool] Searching for nodes matching step text in {len(snapshot.get('nodes', []))} total nodes...")
            matching_nodes = self.find_nodes_by_text_enhanced(snapshot, step, prefer_interactive=True)
            self.logger.info(f"[CDPTool] ✓ Found {len(matching_nodes)} matching nodes for step")
            
            if matching_nodes:
                # Get the best matching node
                best_node = matching_nodes[0]
                self.logger.info(f"[CDPTool] Best node: {best_node.get('nodeName', 'UNKNOWN')} with text: {best_node.get('runtime', {}).get('textContent', '')[:50]}")
                
                # Generate comprehensive locators with edge case handling
                self.logger.info(f"[CDPTool] Generating locators for best node...")
                enhanced_locators = self._generate_enhanced_locators(best_node, snapshot)
                self.logger.info(f"[CDPTool] ✓ Generated {len(enhanced_locators)} locator strategies")
                for i, loc in enumerate(enhanced_locators, 1):
                    self.logger.info(f"[CDPTool]   Locator {i}: {loc.get('type')} = {loc.get('selector', '')[:60]} (confidence: {loc.get('confidence', 0)}, stability: {loc.get('stability', 'unknown')})")
                
                # Validate locators if requested
                validated_locators = enhanced_locators
                if validate_locators and self.current_tab:
                    self.logger.info(f"[CDPTool] Validating {len(enhanced_locators)} locators against live page...")
                    validated_locators = self._validate_locators(enhanced_locators, url)
                    validated_count = sum(1 for loc in validated_locators if loc.get('validated', False))
                    self.logger.info(f"[CDPTool] ✓ Validation complete: {validated_count}/{len(validated_locators)} locators are valid")
                else:
                    self.logger.info(f"[CDPTool] Skipping validation (validate_locators={validate_locators}, current_tab={bool(self.current_tab)})")
                
                # Get best validated locator
                best_locator = self._get_best_validated_locator(validated_locators)
                self.logger.info(f"[CDPTool] ✓ Selected best locator: {best_locator.get('type')} = {best_locator.get('selector', '')[:60]} (validated: {best_locator.get('validated', False)})")
                
                # Return complete element data (ComprehensiveElementData) along with locators
                # This provides full context about the element, not just xpath/selectors
                result = {
                    "step": step,
                    # Complete element JSON data (ComprehensiveElementData)
                    "element": {
                        "nodeId": best_node.get('nodeId'),
                        "backendNodeId": best_node.get('backendNodeId'),
                        "nodeType": best_node.get('nodeType'),
                        "nodeName": best_node.get('nodeName', ''),
                        "localName": best_node.get('localName', ''),
                        "nodeValue": best_node.get('nodeValue', ''),
                        "parentId": best_node.get('parentId'),
                        "nodePath": best_node.get('nodePath', ''),  # XPath
                        "attributes": best_node.get('attributes', {}),  # All HTML attributes
                        "isVisible": best_node.get('isVisible', True),
                        "isInteractable": best_node.get('isInteractable', False),
                        "computedStyle": best_node.get('computedStyle', {}),  # CSS computed styles
                        "boxModel": best_node.get('boxModel'),  # Bounding box information
                        "eventListeners": best_node.get('eventListeners', []),  # Event listeners
                        "frameworkHints": best_node.get('frameworkHints', {}),  # React/Angular/Vue hints
                        "runtime": best_node.get('runtime', {}),  # textContent, etc.
                    },
                    # Locator strategies (multiple ways to find this element)
                    "locators": validated_locators,  # All locators with validation status
                    "best_locator": best_locator,  # Best validated locator (for convenience)
                    # Legacy fields (kept for backward compatibility, but prefer using element data)
                    "node_selector": best_locator.get('selector', ''),
                    "node_type": best_locator.get('type', 'css'),
                    "node_name": best_node.get('nodeName', ''),
                    "xpath": best_node.get('nodePath', ''),
                    # Metadata
                    "context": context,
                    "source": "cdp_inspector",
                    "url": url,
                    "validation_performed": validate_locators
                }
                self.logger.info(f"[CDPTool] ===== FIND_RELEVANT_NODE SUCCESS =====")
                self.logger.info("=" * 80)
                return result
            else:
                # No matching nodes found, use inference
                self.logger.warning(f"[CDPTool] ⚠ No matching nodes found via CDP for step: {step[:50]}")
                self.logger.warning(f"[CDPTool] Falling back to inference-based node detection")
                self.logger.info(f"[CDPTool] ===== FIND_RELEVANT_NODE FALLBACK (INFERENCE) =====")
                self.logger.info("=" * 80)
                return self._infer_node_from_step(step, context)
                
        except Exception as e:
            import traceback
            error_msg = f"Error finding node: {e}"
            self.logger.error(f"[CDPTool] ❌ {error_msg}")
            self.logger.error(f"[CDPTool] Traceback: {traceback.format_exc()}")
            self.logger.warning(f"[CDPTool] Falling back to inference-based node detection")
            self.logger.info(f"[CDPTool] ===== FIND_RELEVANT_NODE ERROR (FALLBACK) =====")
            self.logger.info("=" * 80)
            # Fallback to inference
            return self._infer_node_from_step(step, context)
    
    def inspect_page(self, url: str, keep_open: bool = False) -> Dict[str, Any]:
        """
        Inspect a page and return DOM snapshot.
        Reuses existing inspector if session is active and URL matches.
        
        Args:
            url: URL to inspect
            keep_open: Keep inspector open for locator validation
            
        Returns:
            Dict with nodes and metadata
        """
        # Reuse existing inspector if session is active and URL matches
        if self.session_active and self.inspector and self.current_url == url:
            self.logger.info(f"[CDPTool] Reusing existing inspector for {url}")
            snapshot = self.inspector.inspect(url)
            return snapshot
        
        # Create new inspector
        self.inspector = CDPInspector()
        
        try:
            self.inspector.launch_chrome()
            self.inspector.connect()
            snapshot = self.inspector.inspect(url)
            
            # Keep tab open for validation if requested
            if keep_open:
                self.current_tab = self.inspector.tab
            
            return snapshot
        except Exception as e:
            # Close on error (unless we're keeping it open for a session)
            if self.inspector and not keep_open:
                try:
                    self.inspector.close()
                    self.inspector = None
                    self.current_tab = None
                except:
                    pass
            raise
    
    def find_nodes_by_text(self, snapshot: Dict, text: str, prefer_interactive: bool = True) -> List[Dict]:
        """
        Find nodes containing specific text
        
        Args:
            snapshot: DOM snapshot
            text: Text to search for
            prefer_interactive: Prioritize interactive elements
            
        Returns:
            List of matching nodes, sorted by relevance
        """
        matching_nodes = []
        text_lower = text.lower()
        
        for node in snapshot.get('nodes', []):
            if node.get('nodeType') != 1:  # Only element nodes
                continue
            
            # Skip generic elements
            node_name = node.get('nodeName', '').upper()
            if node_name in ['HTML', 'BODY', 'HEAD', 'SCRIPT', 'STYLE', 'META', 'LINK']:
                continue
            
            # Get text content
            node_text = node.get('runtime', {}).get('textContent', '')
            if not node_text:
                continue
            
            node_text_lower = node_text.lower().strip()
            
            # Check for match
            if text_lower in node_text_lower:
                # Calculate relevance score
                score = 0
                
                # Exact match gets highest score
                if node_text_lower == text_lower:
                    score += 100
                # Text starts with query
                elif node_text_lower.startswith(text_lower):
                    score += 50
                # Contains query
                else:
                    score += 25
                
                # Prefer shorter text (more specific)
                text_length = len(node_text)
                if text_length < 50:
                    score += 20
                elif text_length < 200:
                    score += 10
                
                # Prefer interactive elements
                if prefer_interactive:
                    if node_name in ['BUTTON', 'A', 'INPUT', 'SELECT', 'TEXTAREA']:
                        score += 30
                    if node.get('isInteractable', False):
                        score += 20
                
                # Prefer elements with IDs or data-testid
                if node.get('attributes', {}).get('id'):
                    score += 15
                if node.get('attributes', {}).get('data-testid'):
                    score += 15
                
                matching_nodes.append({
                    'node': node,
                    'score': score,
                    'text': node_text[:100]  # Truncate for display
                })
        
        # Sort by score (highest first)
        matching_nodes.sort(key=lambda x: x['score'], reverse=True)
        
        # Return just the nodes
        return [item['node'] for item in matching_nodes]
    
    def find_best_locator(self, node: Dict) -> Dict[str, str]:
        """Get the best locator for a node"""
        locators = node.get('locators', [])
        
        # Prioritize: ID > data-testid > xpath
        for loc in locators:
            if loc.get('type') == 'id':
                return loc
        
        for loc in locators:
            if loc.get('type') == 'attribute':
                return loc
        
        for loc in locators:
            if loc.get('type') == 'xpath':
                return loc
        
        return locators[0] if locators else {'type': 'css', 'selector': 'body', 'confidence': 0.1}
    
    def _extract_url_from_step(self, step: str, context: Optional[str] = None) -> Optional[str]:
        """Extract URL from step description or context."""
        import re
        
        # Updated pattern to include localhost
        url_pattern = r'(https?://[^\s\)]+|www\.[^\s\)]+|localhost:\d+)'
        
        # Check step
        urls = re.findall(url_pattern, step)
        if urls:
            url = urls[0]
            if not url.startswith('http'):
                url = f"http://{url}"
            return url
        
        # Check context
        if context:
            urls = re.findall(url_pattern, context)
            if urls:
                url = urls[0]
                if not url.startswith('http'):
                    url = f"http://{url}"
                return url
        
        return None
    
    def _infer_node_from_step(self, step: str, context: Optional[str] = None) -> Dict[str, Any]:
        """
        Infer node information from step description (fallback method).
        
        Args:
            step: Step description
            context: Optional context
        
        Returns:
            Dict with inferred node information (minimal structure, no full element data)
        """
        inferred_selector = self._infer_selector_from_step(step)
        inferred_type = self._infer_node_type(step)
        
        return {
            "step": step,
            # Minimal element structure (since we don't have CDP data)
            "element": {
                "nodeName": inferred_type.upper() if inferred_type else "UNKNOWN",
                "localName": inferred_type.lower() if inferred_type else "unknown",
                "attributes": self._infer_attributes(step),
                "isVisible": True,  # Assumed
                "isInteractable": True,  # Assumed
                "runtime": {
                    "textContent": step  # Use step text as fallback
                }
            },
            # Basic locator
            "locators": [{
                "type": "css",
                "selector": inferred_selector,
                "confidence": 0.3,
                "stability": "low",
                "validated": False
            }],
            "best_locator": {
                "type": "css",
                "selector": inferred_selector,
                "confidence": 0.3,
                "stability": "low",
                "validated": False
            },
            # Legacy fields
            "node_selector": inferred_selector,
            "node_type": "css",
            "node_name": inferred_type.upper() if inferred_type else "UNKNOWN",
            "attributes": self._infer_attributes(step),
            "context": context,
            "source": "inference"
        }
    
    def _infer_selector_from_step(self, step: str) -> str:
        """Infer CSS selector from step description."""
        step_lower = step.lower()
        if "button" in step_lower or "click" in step_lower:
            return "button"
        elif "input" in step_lower or "fill" in step_lower or "enter" in step_lower:
            return "input"
        elif "form" in step_lower:
            return "form"
        elif "link" in step_lower:
            return "a"
        else:
            return "[data-testid]"
    
    def _infer_node_type(self, step: str) -> str:
        """Infer node type from step."""
        step_lower = step.lower()
        if "button" in step_lower or "click" in step_lower:
            return "button"
        elif "input" in step_lower:
            return "input"
        elif "form" in step_lower:
            return "form"
        else:
            return "element"
    
    def _infer_attributes(self, step: str) -> Dict[str, str]:
        """Infer node attributes from step."""
        return {
            "type": "inferred",
            "description": step
        }
    
    # ========== Enhanced Methods with Edge Case Handling ==========
    
    def find_nodes_by_text_enhanced(self, snapshot: Dict, text: str, prefer_interactive: bool = True) -> List[Dict]:
        """
        Enhanced node finding with comprehensive edge case handling.
        Handles: i18n text, casing variations, icon-only SVG, duplicate matches.
        """
        matching_nodes = []
        text_lower = text.lower()
        
        # Generate text variations for i18n and casing
        text_variations = self._generate_text_variations(text)
        
        for node in snapshot.get('nodes', []):
            if node.get('nodeType') != 1:  # Only element nodes
                continue
            
            # Skip generic elements
            node_name = node.get('nodeName', '').upper()
            if node_name in ['HTML', 'BODY', 'HEAD', 'SCRIPT', 'STYLE', 'META', 'LINK']:
                continue
            
            # Get text content from multiple sources
            node_text = node.get('runtime', {}).get('textContent', '')
            attributes = node.get('attributes', {})
            aria_label = attributes.get('aria-label', '') or attributes.get('aria-labelledby', '')
            title = attributes.get('title', '')
            alt_text = attributes.get('alt', '')
            
            # NEW: Also check input attributes for form fields
            name_attr = attributes.get('name', '')
            id_attr = attributes.get('id', '')
            placeholder = attributes.get('placeholder', '')
            value_attr = attributes.get('value', '')
            
            # Check all text sources
            text_sources = [
                node_text.lower().strip() if node_text else '',
                aria_label.lower().strip() if aria_label else '',
                title.lower().strip() if title else '',
                alt_text.lower().strip() if alt_text else '',
                name_attr.lower().strip() if name_attr else '',
                id_attr.lower().strip() if id_attr else '',
                placeholder.lower().strip() if placeholder else '',
                value_attr.lower().strip() if value_attr else ''
            ]
            
            # DEBUG: Log text sources for potential matches or specific elements
            if 'contact' in str(text_sources) or node_name == 'A':
               self.logger.info(f"[CDPTool] Checking node {node_name}: {text_sources}")
            
            # Check against all text variations
            match_found = False
            for source_text in text_sources:
                if not source_text:
                    continue
                
                for text_var in text_variations:
                    if text_var in source_text or source_text in text_var:
                        match_found = True
                        break
                
                if match_found:
                    break
            
            if match_found:
                # Calculate relevance score
                score = self._calculate_node_score(node, text_lower, prefer_interactive)
                
                matching_nodes.append({
                    'node': node,
                    'score': score,
                    'text': node_text[:100] if node_text else (aria_label[:100] if aria_label else '')
                })
        
        # Sort by score (highest first)
        matching_nodes.sort(key=lambda x: x['score'], reverse=True)
        
        # Return just the nodes
        return [item['node'] for item in matching_nodes]
    
    def _generate_text_variations(self, text: str) -> List[str]:
        """Generate text variations for i18n and casing flexibility"""
        if not text:
            return []
        
        variations = []
        text_stripped = text.strip()
        
        # Case variations
        variations.append(text_stripped.lower())
        variations.append(text_stripped.upper())
        variations.append(text_stripped.capitalize())
        variations.append(text_stripped.title())
        
        # Normalized (remove extra spaces)
        normalized = ' '.join(text_stripped.split())
        if normalized != text_stripped:
            variations.append(normalized.lower())
        
        # Remove duplicates
        seen = set()
        unique_variations = []
        for v in variations:
            v_lower = v.lower()
            if v_lower not in seen and v_lower:
                seen.add(v_lower)
                unique_variations.append(v_lower)
        
        return unique_variations
    
    def _calculate_node_score(self, node: Dict, search_text: str, prefer_interactive: bool) -> float:
        """Calculate relevance score for a node"""
        score = 0.0
        
        node_text = node.get('runtime', {}).get('textContent', '').lower()
        node_name = node.get('nodeName', '').upper()
        attributes = node.get('attributes', {})
        
        # Text match quality
        if node_text:
            if node_text.strip() == search_text:
                score += 100  # Exact match
            elif node_text.startswith(search_text):
                score += 50
            elif search_text in node_text:
                score += 25
        
        # Prefer shorter text (more specific)
        if len(node_text) < 50:
            score += 20
        elif len(node_text) < 200:
            score += 10
        
        # Prefer interactive elements
        if prefer_interactive:
            if node_name in ['BUTTON', 'A', 'INPUT', 'SELECT', 'TEXTAREA']:
                score += 30
            if node.get('isInteractable', False):
                score += 20
        
        # Prefer elements with stable identifiers
        if attributes.get('data-testid'):
            score += 15
        if attributes.get('id') and not self._is_dynamic_id(attributes.get('id', '')):
            score += 15
        if attributes.get('name'):
            score += 10
        
        return score
    
    def _is_dynamic_id(self, element_id: str) -> bool:
        """Detect if an ID looks dynamically generated"""
        if not element_id:
            return True
        
        import re
        dynamic_patterns = [
            r'^[a-z0-9]{8}-[a-z0-9]{4}-[a-z0-9]{4}',  # UUID-like
            r'^react-select-\d+',
            r'^rc-\d+',
            r'^__\w+__',
            r'^[a-f0-9]{32}',  # Hash
        ]
        
        for pattern in dynamic_patterns:
            if re.match(pattern, element_id, re.IGNORECASE):
                return True
        
        return False
    
    def _is_hashed_class(self, class_name: str) -> bool:
        """Detect if a class name looks hashed/minified"""
        if not class_name or len(class_name) < 3:
            return False
        
        import re
        if re.match(r'^[a-z0-9]{6,}$', class_name) and len(class_name) < 10:
            return True
        if re.match(r'^_[a-z0-9]+$', class_name):
            return True
        
        return False
    
    def _generate_enhanced_locators(self, node: Dict, snapshot: Dict) -> List[Dict]:
        """
        Generate comprehensive locators with edge case handling.
        Generates multiple locator strategies with stability and confidence scores.
        """
        locators = []
        attributes = node.get('attributes', {})
        node_name = node.get('nodeName', '').upper()
        node_path = node.get('nodePath', '')
        
        # 1. Data attributes (most stable)
        for key in ['data-testid', 'data-test', 'data-cy', 'data-qa', 'data-id']:
            if key in attributes:
                locators.append({
                    'type': 'attribute',
                    'selector': f"[{key}='{attributes[key]}']",
                    'confidence': 0.95,
                    'stability': 'high',
                    'validated': False
                })
        
        # 2. Stable ID (not dynamic)
        if 'id' in attributes and not self._is_dynamic_id(attributes['id']):
            locators.append({
                'type': 'id',
                'selector': f"#{attributes['id']}",
                'confidence': 1.0,
                'stability': 'high',
                'validated': False
            })
        
        # 3. Name attribute
        if 'name' in attributes:
            locators.append({
                'type': 'name',
                'selector': f"[name='{attributes['name']}']",
                'confidence': 0.9,
                'stability': 'high',
                'validated': False
            })
        
        # 4. Aria-label (great for icon-only elements)
        if 'aria-label' in attributes:
            locators.append({
                'type': 'aria-label',
                'selector': f"[aria-label='{attributes['aria-label']}']",
                'confidence': 0.9,
                'stability': 'high',
                'validated': False
            })
        
        # 5. Role + accessible name
        if 'role' in attributes:
            role_selector = f"[role='{attributes['role']}']"
            if 'aria-label' in attributes:
                role_selector += f"[aria-label='{attributes['aria-label']}']"
            locators.append({
                'type': 'role',
                'selector': role_selector,
                'confidence': 0.85,
                'stability': 'medium',
                'validated': False
            })
        
        # 6. Stable class (not hashed) - only if no better options exist
        # Skip class locators as they're often unstable (hashed, dynamic)
        # Only include if we have very few locators and class seems stable
        if 'class' in attributes and len(locators) < 3:
            classes = [c for c in attributes['class'].split() if not self._is_hashed_class(c)]
            # Only add if we have a single, meaningful class name
            if len(classes) == 1 and len(classes[0]) > 3:
                locators.append({
                    'type': 'class',
                    'selector': f".{classes[0]}",
                    'confidence': 0.6,
                    'stability': 'low',  # Classes are generally unstable
                    'validated': False
                })
        
        # 7. Relative XPath (only if absolute path is short and stable)
        # Skip absolute XPath as it's brittle - only use if path is short (< 5 levels)
        path_depth = node_path.count('/')
        if path_depth > 0 and path_depth < 5:
            # Try to generate a more stable relative XPath
            # Only include if we don't have many stable locators
            if len([l for l in locators if l.get('stability') == 'high']) < 2:
                locators.append({
                    'type': 'xpath',
                    'selector': node_path,
                    'confidence': 0.7,
                    'stability': 'low',  # XPath is generally brittle
                    'validated': False
                })
        
        # 7.5 Text content - for links, buttons with visible text
        # This is CRITICAL for elements like "Contact" link
        runtime = node.get('runtime', {})
        text_content = runtime.get('textContent', '').strip()
        
        if text_content and len(text_content) > 0 and len(text_content) < 50:
            # For links and buttons with text
            if node_name.lower() in ['a', 'button', 'span']:
                # XPath with text
                locators.append({
                    'type': 'xpath',
                    'selector': f"//{node_name.lower()}[text()='{text_content}']",
                    'confidence': 0.85,
                    'stability': 'medium',
                    'validated': False
                })
                # CSS with text (Playwright syntax)
                locators.append({
                    'type': 'text',
                    'selector': f"{node_name.lower()}:has-text('{text_content}')",
                    'confidence': 0.80,
                    'stability': 'medium',
                    'validated': False
                })
        
        # 7.5 Text content - for links, buttons, and any element with visible text
        # Generate an XPath that uses contains() to match partial text, handling whitespace variations.
        if text_content and len(text_content) > 0 and len(text_content) < 100:
            # Escape single quotes in text for XPath
            escaped_text = text_content.replace("'", "', \"\", '\"")
            # XPath using contains() on normalized text
            locators.append({
                'type': 'xpath',
                'selector': f"//{node_name.lower()}[contains(normalize-space(.), '{escaped_text}')]",
                'confidence': 0.78,
                'stability': 'medium',
                'validated': False
            })
            # Additionally, a more permissive contains() without normalize-space
            locators.append({
                'type': 'xpath',
                'selector': f"//{node_name.lower()}[contains(text(), '{escaped_text}')]",
                'confidence': 0.70,
                'stability': 'low',
                'validated': False
            })
        
        # 8. Tag name - ONLY as absolute last resort (skip if we have any other locators)
        # Tag locators are too generic and unreliable
        if len(locators) == 0:
            locators.append({
                'type': 'tag',
                'selector': node_name.lower(),
                'confidence': 0.2,
                'stability': 'low',
                'validated': False
            })
        
        return locators
    
    def _validate_locators(self, locators: List[Dict], url: str) -> List[Dict]:
        """
        Test each locator on the page to verify it works.
        Returns locators with validation status.
        """
        if not self.current_tab:
            self.logger.warning("[CDPTool] No active tab for locator validation")
            return locators
        
        validated_locators = []
        
        for locator in locators:
            selector = locator.get('selector', '')
            locator_type = locator.get('type', 'css')
            
            try:
                # Test the locator
                found = self._test_locator(selector, locator_type)
                
                locator['validated'] = found
                if found:
                    locator['validation_message'] = "✅ Locator works on page"
                    self.logger.info(f"[CDPTool] ✅ Validated {locator_type} locator: {selector[:50]}")
                else:
                    locator['validation_message'] = "❌ Locator not found on page"
                    self.logger.warning(f"[CDPTool] ❌ Failed to validate {locator_type} locator: {selector[:50]}")
            except Exception as e:
                locator['validated'] = False
                locator['validation_message'] = f"❌ Validation error: {str(e)[:50]}"
                self.logger.warning(f"[CDPTool] Error validating locator: {e}")
            
            validated_locators.append(locator)
        
        return validated_locators
    
    def _test_locator(self, selector: str, locator_type: str) -> bool:
        """
        Test if a locator actually finds an element on the page.
        
        Args:
            selector: The selector string
            locator_type: Type of selector ('css', 'xpath', 'id', etc.)
        
        Returns:
            True if element found, False otherwise
        """
        if not self.current_tab:
            return False
        
        try:
            # Convert selector to CSS format for querySelector
            css_selector = selector
            
            if locator_type == 'id':
                # Remove # if present, use as ID selector
                css_selector = selector.lstrip('#')
                css_selector = f"#{css_selector}" if css_selector else selector
            elif locator_type == 'xpath':
                # Handle XPath validation separately
                return self._test_xpath_locator(selector)
            elif locator_type == 'text':
                # Handle text pseudo-selector (Playwright style)
                # Convert to XPath for validation
                text_match = selector.split(":has-text('")
                if len(text_match) > 1:
                    text_content = text_match[1].rstrip("')")
                    tag = text_match[0] if text_match[0] else "*"
                    return self._test_xpath_locator(f"//{tag}[contains(text(), '{text_content}')]")
                return False
            elif locator_type == 'class':
                # Remove . if present, use as class selector
                css_selector = selector.lstrip('.')
                css_selector = f".{css_selector}" if css_selector else selector
            
            # Use document.querySelector for CSS selectors
            result = self.current_tab.Runtime.evaluate(
                expression=f"document.querySelector(\"{css_selector}\") !== null"
            )
            
            if result and 'result' in result:
                return result['result'].get('value', False)
            return False
            
        except Exception as e:
            self.logger.warning(f"[CDPTool] Error testing locator '{selector}': {e}")
            return False

    def _test_xpath_locator(self, xpath: str) -> bool:
        """Test if an XPath locator finds an element."""
        if not self.current_tab:
            return False
            
        try:
            # Escape double quotes in XPath for the JS string
            js_xpath = xpath.replace('"', '\\"')
            expression = f"document.evaluate(\"{js_xpath}\", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue !== null"
            
            result = self.current_tab.Runtime.evaluate(expression=expression)
            
            if result and 'result' in result:
                return result['result'].get('value', False)
            return False
        except Exception as e:
            self.logger.warning(f"[CDPTool] Error testing XPath '{xpath}': {e}")
            return False
    
    def _llm_select_best_node_and_generate_locator(self, candidate_nodes: List[Dict], step: str, snapshot: Dict) -> Optional[Dict]:
        """
        Use LLM to analyze candidate nodes from snapshot and select the best match,
        then generate a working locator for it.
        
        Args:
            candidate_nodes: List of candidate nodes from snapshot
            step: Step description
            snapshot: Full DOM snapshot
            
        Returns:
            Best matching node with working_locator attached, or None
        """
        import json
        import os
        
        # Prepare node summaries for LLM
        node_summaries = []
        for idx, node in enumerate(candidate_nodes):
            attrs = node.get('attributes', {})
            summary = {
                'index': idx,
                'tag': node.get('nodeName', '').lower(),
                'id': attrs.get('id', ''),
                'class': attrs.get('class', ''),
                'name': attrs.get('name', ''),
                'type': attrs.get('type', ''),
                'placeholder': attrs.get('placeholder', ''),
                'aria-label': attrs.get('aria-label', ''),
                'role': attrs.get('role', ''),
                'text': node.get('runtime', {}).get('textContent', '')[:100],
                'data-testid': attrs.get('data-testid', ''),
            }
            node_summaries.append(summary)
        
        prompt = f"""You are analyzing a web page DOM snapshot to find the best element for this automation step:

STEP: {step}

CANDIDATE ELEMENTS (JSON format):
{json.dumps(node_summaries, indent=2)}

Your task:
1. Analyze which element best matches the step description
2. Generate the most stable locator for that element

Return ONLY a JSON object with this structure:
{{
  "selected_index": <index of best matching element>,
  "reasoning": "<brief explanation>",
  "locator": {{
    "type": "<css|xpath|attribute|id|name|class|tag>",
    "selector": "<the actual selector string>",
    "stability": "<high|medium|low>",
    "confidence": <0.0-1.0>
  }}
}}

Prioritize locators in this order:
1. data-testid (highest priority)
2. id (if not dynamic)
3. name
4. placeholder
5. aria-label
6. class (if not hashed/dynamic)
7. tag + text
8. xpath (last resort)

Return ONLY the JSON, no markdown or explanation."""

        try:
            import google.genai as genai
            from google.genai.types import GenerateContentConfig
            
            client = genai.Client(api_key=os.getenv('GOOGLE_AI_API_KEY'))
            config = GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=1024,
            )
            
            response = client.models.generate_content(
                model='gemini-2.0-flash-exp',
                contents=[prompt],
                config=config,
            )
            
            if not response.candidates or not response.candidates[0].content:
                self.logger.warning("[CDPTool] LLM returned no response for node selection")
                return None
            
            response_text = response.candidates[0].content.parts[0].text.strip()
            
            # Extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if not json_match:
                self.logger.warning("[CDPTool] Could not extract JSON from LLM response")
                return None
            
            result = json.loads(json_match.group())
            selected_idx = result.get('selected_index')
            
            if selected_idx is None or selected_idx >= len(candidate_nodes):
                self.logger.warning(f"[CDPTool] Invalid selected_index: {selected_idx}")
                return None
            
            best_node = candidate_nodes[selected_idx]
            locator_info = result.get('locator', {})
            
            # Create working locator
            working_locator = {
                'type': locator_info.get('type', 'css'),
                'selector': locator_info.get('selector', ''),
                'stability': locator_info.get('stability', 'medium'),
                'confidence': locator_info.get('confidence', 0.7),
                'source': 'llm_fallback',
                'validated': False,  # Will be validated next
                'reasoning': result.get('reasoning', 'LLM-selected from snapshot')
            }
            
            self.logger.info(f"[CDPTool] LLM selected node {selected_idx}: {working_locator['selector']}")
            
            # Test the locator on live page
            if self._test_locator(working_locator['selector'], working_locator['type']):
                self.logger.info(f"[CDPTool] ✅ LLM-generated locator validated: {working_locator['selector']}")
                working_locator['validated'] = True
                best_node['working_locator'] = working_locator
                return best_node
            else:
                self.logger.warning(f"[CDPTool] ❌ LLM-generated locator failed validation: {working_locator['selector']}")
                return None
                
        except Exception as e:
            self.logger.error(f"[CDPTool] Error in LLM node selection: {e}")
            return None
    
    def find_node_by_locators(self, locators: List[Dict], step: str, snapshot: Optional[Dict] = None) -> Optional[Dict]:
        """
        Try to find a node using provided locators, and if all fail, use CDP snapshot to find alternatives.
        
        Args:
            locators: List of locators to try (from RAG or other sources)
            step: Step description (for fallback matching)
            snapshot: Optional DOM snapshot (if None, uses current_snapshot)
        
        Returns:
            Dict with node data if found, None otherwise
        """
        if snapshot is None:
            snapshot = self.current_snapshot
        
        if not snapshot:
            self.logger.warning("[CDPTool] No snapshot available for locator-based search")
            return None
        
        # Try each locator in order
        for locator in locators:
            selector = locator.get('selector', '')
            locator_type = locator.get('type', 'css')
            
            # Test if locator works
            if self.current_tab:
                if self._test_locator(selector, locator_type):
                    self.logger.info(f"[CDPTool] ✅ Locator works: {locator_type} = {selector[:50]}")
                    # Find the actual node in snapshot
                    node = self._find_node_in_snapshot_by_locator(snapshot, selector, locator_type)
                    if node:
                        # Attach the working locator to the node for reference
                        node['working_locator'] = locator
                        return node
                    else:
                        self.logger.warning(f"[CDPTool] Locator validated but node not found in snapshot")
        
        # All locators failed, use LLM to analyze snapshot and find best node
        self.logger.info(f"[CDPTool] All provided locators failed, using LLM to analyze snapshot for: {step[:50]}")
        matching_nodes = self.find_nodes_by_text_enhanced(snapshot, step, prefer_interactive=True)
        
        if matching_nodes:
            self.logger.info(f"[CDPTool] Found {len(matching_nodes)} candidate nodes, using LLM to select best match")
            
            # Use LLM to analyze nodes and generate locator
            best_node_with_locator = self._llm_select_best_node_and_generate_locator(
                matching_nodes[:10],  # Limit to top 10 candidates
                step,
                snapshot
            )
            
            if best_node_with_locator:
                return best_node_with_locator
        
        return None
    
    def execute_action(self, locator: Dict, step: str) -> Dict[str, Any]:
        """
        Execute the action intended by the step using the provided locator.
        
        Args:
            locator: Locator dict with 'type' and 'selector'
            step: Step description to infer action type
        
        Returns:
            Dict with action result: {'success': bool, 'action': str, 'message': str}
        """
        if not self.current_tab:
            return {
                'success': False,
                'action': 'unknown',
                'message': 'No active CDP session'
            }
        
        # Infer action type from step
        action_type = self._infer_action_type(step)
        selector = locator.get('selector', '')
        locator_type = locator.get('type', 'css')
        
        try:
            # Get element nodeId using the locator
            element_node_id = self._get_element_node_id(selector, locator_type)
            
            if not element_node_id:
                return {
                    'success': False,
                    'action': action_type,
                    'message': f'Element not found with locator: {selector[:50]}'
                }
            
            # Execute the action
            if action_type == 'click':
                return self._perform_click(element_node_id, selector, locator_type)
            elif action_type == 'type' or action_type == 'fill':
                # Extract text to type from step
                text_to_type = self._extract_text_to_type(step)
                return self._perform_type(element_node_id, text_to_type, selector, locator_type)
            elif action_type == 'select':
                # Extract option to select from step
                option = self._extract_select_option(step)
                return self._perform_select(element_node_id, option, selector, locator_type)
            elif action_type == 'navigate':
                # Navigation is handled separately, no action needed
                return {
                    'success': True,
                    'action': 'navigate',
                    'message': 'Navigation step - no element action needed'
                }
            else:
                return {
                    'success': False,
                    'action': action_type,
                    'message': f'Action type "{action_type}" not yet implemented'
                }
                
        except Exception as e:
            self.logger.error(f"[CDPTool] Error executing action: {e}")
            return {
                'success': False,
                'action': action_type,
                'message': f'Error: {str(e)[:100]}'
            }
    
    def _infer_action_type(self, step: str) -> str:
        """Infer action type from step description."""
        step_lower = step.lower()
        
        if any(word in step_lower for word in ['navigate', 'go to', 'open', 'visit']):
            return 'navigate'
        elif any(word in step_lower for word in ['click', 'press', 'tap']):
            return 'click'
        elif any(word in step_lower for word in ['type', 'enter', 'fill', 'input', 'write']):
            return 'type'
        elif any(word in step_lower for word in ['select', 'choose', 'pick']):
            return 'select'
        elif any(word in step_lower for word in ['submit', 'save']):
            return 'click'  # Usually a button click
        else:
            return 'click'  # Default to click
    
    def _extract_text_to_type(self, step: str) -> str:
        """Extract text to type from step description."""
        import re
        # Look for patterns like "enter 'text'", "type 'text'", "fill with 'text'"
        patterns = [
            r"enter\s+['\"]([^'\"]+)['\"]",
            r"type\s+['\"]([^'\"]+)['\"]",
            r"fill\s+.*?with\s+['\"]([^'\"]+)['\"]",
            r"input\s+['\"]([^'\"]+)['\"]",
            r"enter\s+(\w+)",
            r"type\s+(\w+)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, step.lower())
            if match:
                return match.group(1)
        
        # If no explicit text found, try to extract after common keywords
        keywords = ['enter', 'type', 'fill', 'input']
        for keyword in keywords:
            if keyword in step.lower():
                # Get text after the keyword
                parts = step.lower().split(keyword, 1)
                if len(parts) > 1:
                    text = parts[1].strip()
                    # Remove common words
                    text = text.replace('the', '').replace('in', '').replace('field', '').strip()
                    if text and len(text) > 0:
                        return text[:50]  # Limit length
        
        return ""  # Return empty if no text found
    
    def _extract_select_option(self, step: str) -> str:
        """Extract option to select from step description."""
        import re
        patterns = [
            r"select\s+['\"]([^'\"]+)['\"]",
            r"choose\s+['\"]([^'\"]+)['\"]",
            r"pick\s+['\"]([^'\"]+)['\"]",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, step.lower())
            if match:
                return match.group(1)
        
        return ""
    
    def _get_element_node_id(self, selector: str, locator_type: str) -> Optional[int]:
        """Get nodeId of element using selector."""
        if not self.current_tab:
            return None
        
        try:
            # Convert selector based on type
            if locator_type == 'xpath':
                # XPath via JavaScript
                js_code = f"""
                (function() {{
                    try {{
                        var xpath = {json.dumps(selector)};
                        var result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                        return result.singleNodeValue;
                    }} catch(e) {{
                        return null;
                    }}
                }})()
                """
                result = self.current_tab.Runtime.evaluate(expression=js_code)
                if 'result' in result and 'objectId' in result['result']:
                    # Resolve object to node
                    node_result = self.current_tab.DOM.requestNode(objectId=result['result']['objectId'])
                    return node_result.get('nodeId')
                return None
            else:
                # CSS selector
                css_selector = selector
                if locator_type == 'id':
                    css_selector = selector.lstrip('#')
                    css_selector = f"#{css_selector}" if css_selector else selector
                elif locator_type == 'class':
                    css_selector = selector.lstrip('.')
                    css_selector = f".{css_selector}" if css_selector else selector
                
                result = self.current_tab.DOM.querySelector(
                    nodeId=self.current_tab.DOM.getDocument()['root']['nodeId'],
                    selector=css_selector
                )
                return result.get('nodeId') if result and 'nodeId' in result else None
                
        except Exception as e:
            self.logger.debug(f"Error getting element nodeId: {e}")
            return None
    
    def _perform_click(self, node_id: int, selector: str, locator_type: str) -> Dict[str, Any]:
        """Perform click action on element."""
        try:
            # Scroll element into view first
            self.current_tab.DOM.scrollIntoViewIfNeeded(nodeId=node_id)
            time.sleep(0.1)  # Small delay for scroll
            
            # Get element's box model for click coordinates
            box_model = self.current_tab.DOM.getBoxModel(nodeId=node_id)
            if 'model' in box_model:
                # Get center coordinates
                model = box_model['model']
                x = (model['content'][0] + model['content'][2]) / 2
                y = (model['content'][1] + model['content'][3]) / 2
                
                # Perform click using Input domain
                self.current_tab.Input.dispatchMouseEvent(
                    type='mousePressed',
                    x=x,
                    y=y,
                    button='left',
                    clickCount=1
                )
                time.sleep(0.05)
                self.current_tab.Input.dispatchMouseEvent(
                    type='mouseReleased',
                    x=x,
                    y=y,
                    button='left',
                    clickCount=1
                )
            else:
                # Fallback: use JavaScript click
                obj_result = self.current_tab.DOM.resolveNode(nodeId=node_id)
                if 'object' in obj_result:
                    self.current_tab.Runtime.callFunctionOn(
                        objectId=obj_result['object']['objectId'],
                        functionDeclaration='function() { this.click(); }',
                        returnByValue=True
                    )
            
            time.sleep(1.0)  # Wait for action to complete (increased for visibility in headed mode)
            self.logger.info(f"[CDPTool] ✅ Clicked element: {selector[:50]}")
            return {
                'success': True,
                'action': 'click',
                'message': f'Successfully clicked element'
            }
            
        except Exception as e:
            self.logger.error(f"[CDPTool] Error clicking element: {e}")
            return {
                'success': False,
                'action': 'click',
                'message': f'Error: {str(e)[:100]}'
            }
    
    def _perform_type(self, node_id: int, text: str, selector: str, locator_type: str) -> Dict[str, Any]:
        """Perform type/fill action on input element."""
        if not text:
            return {
                'success': False,
                'action': 'type',
                'message': 'No text to type found in step description'
            }
        
        try:
            # Scroll element into view
            self.current_tab.DOM.scrollIntoViewIfNeeded(nodeId=node_id)
            time.sleep(0.1)
            
            # Focus the element
            obj_result = self.current_tab.DOM.resolveNode(nodeId=node_id)
            if 'object' in obj_result:
                # Focus first
                self.current_tab.Runtime.callFunctionOn(
                    objectId=obj_result['object']['objectId'],
                    functionDeclaration='function() { this.focus(); }',
                    returnByValue=True
                )
                time.sleep(0.1)
                
                # Clear existing value
                self.current_tab.Runtime.callFunctionOn(
                    objectId=obj_result['object']['objectId'],
                    functionDeclaration='function() { this.value = ""; }',
                    returnByValue=True
                )
                time.sleep(0.1)
                
                # Type the text
                self.current_tab.Runtime.callFunctionOn(
                    objectId=obj_result['object']['objectId'],
                    functionDeclaration=f'function() {{ this.value = {json.dumps(text)}; this.dispatchEvent(new Event("input", {{ bubbles: true }})); this.dispatchEvent(new Event("change", {{ bubbles: true }})); }}',
                    returnByValue=True
                )
                
                time.sleep(1.0)  # Wait for action to complete (increased for visibility in headed mode)
                self.logger.info(f"[CDPTool] ✅ Typed text into element: {selector[:50]}")
                return {
                    'success': True,
                    'action': 'type',
                    'message': f'Successfully typed "{text[:30]}" into element'
                }
            else:
                return {
                    'success': False,
                    'action': 'type',
                    'message': 'Could not resolve element object'
                }
                
        except Exception as e:
            self.logger.error(f"[CDPTool] Error typing into element: {e}")
            return {
                'success': False,
                'action': 'type',
                'message': f'Error: {str(e)[:100]}'
            }
    
    def _perform_select(self, node_id: int, option: str, selector: str, locator_type: str) -> Dict[str, Any]:
        """Perform select action on select/dropdown element."""
        if not option:
            return {
                'success': False,
                'action': 'select',
                'message': 'No option to select found in step description'
            }
        
        try:
            obj_result = self.current_tab.DOM.resolveNode(nodeId=node_id)
            if 'object' in obj_result:
                # Select option by text
                js_code = f"""
                (function() {{
                    var element = this;
                    var optionText = {json.dumps(option)};
                    for (var i = 0; i < element.options.length; i++) {{
                        if (element.options[i].text.toLowerCase().includes(optionText.toLowerCase())) {{
                            element.selectedIndex = i;
                            element.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            return true;
                        }}
                    }}
                    return false;
                }})()
                """
                result = self.current_tab.Runtime.callFunctionOn(
                    objectId=obj_result['object']['objectId'],
                    functionDeclaration=js_code,
                    returnByValue=True
                )
                
                if result.get('result', {}).get('value', False):
                    self.logger.info(f"[CDPTool] ✅ Selected option '{option}' in element: {selector[:50]}")
                    return {
                        'success': True,
                        'action': 'select',
                        'message': f'Successfully selected "{option}"'
                    }
                else:
                    return {
                        'success': False,
                        'action': 'select',
                        'message': f'Option "{option}" not found in dropdown'
                    }
            else:
                return {
                    'success': False,
                    'action': 'select',
                    'message': 'Could not resolve element object'
                }
                
        except Exception as e:
            self.logger.error(f"[CDPTool] Error selecting option: {e}")
            return {
                'success': False,
                'action': 'select',
                'message': f'Error: {str(e)[:100]}'
            }
    
    def extract_visible_interactable_elements(self, snapshot: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """
        Extract visible and interactable elements from CDP snapshot.
        Returns semantically useful data similar to element-mapper.ts.
        
        Args:
            snapshot: Optional DOM snapshot (if None, uses current_snapshot)
        
        Returns:
            List of simplified element data for LLM processing
        """
        if snapshot is None:
            snapshot = self.current_snapshot
        
        if not snapshot:
            return []
        
        elements = []
        nodes = snapshot.get('nodes', [])
        
        for node in nodes:
            # Only process element nodes (nodeType == 1)
            if node.get('nodeType') != 1:
                continue
            
            # Only include visible and interactable elements
            if not node.get('isVisible', False) or not node.get('isInteractable', False):
                continue
            
            # Skip generic/structural elements
            node_name = node.get('nodeName', '').upper()
            if node_name in ['HTML', 'BODY', 'HEAD', 'SCRIPT', 'STYLE', 'META', 'LINK', 'NOSCRIPT']:
                continue
            
            # Extract semantically useful data
            attributes = node.get('attributes', {})
            runtime = node.get('runtime', {})
            text_content = runtime.get('textContent', '').strip()[:200]  # Limit text length
            
            # Build simplified element data
            element_data = {
                'tagName': node.get('localName', node.get('nodeName', '')).lower(),
                'nodeName': node.get('nodeName', ''),
                'textContent': text_content,
                'attributes': {
                    'id': attributes.get('id', ''),
                    'name': attributes.get('name', ''),
                    'class': attributes.get('class', ''),
                    'data-testid': attributes.get('data-testid', ''),
                    'data-test': attributes.get('data-test', ''),
                    'data-cy': attributes.get('data-cy', ''),
                    'aria-label': attributes.get('aria-label', ''),
                    'aria-labelledby': attributes.get('aria-labelledby', ''),
                    'role': attributes.get('role', ''),
                    'type': attributes.get('type', ''),
                    'placeholder': attributes.get('placeholder', ''),
                    'value': attributes.get('value', ''),
                },
                'isVisible': node.get('isVisible', False),
                'isInteractable': node.get('isInteractable', False),
                'xpath': node.get('nodePath', ''),
            }
            
            # Only include elements with meaningful identifiers or text
            has_identifier = (
                element_data['attributes']['id'] or
                element_data['attributes']['name'] or
                element_data['attributes']['data-testid'] or
                element_data['attributes']['data-test'] or
                element_data['attributes']['data-cy'] or
                element_data['attributes']['aria-label'] or
                element_data['attributes']['role'] or
                text_content
            )
            
            if has_identifier:
                elements.append(element_data)
        
        return elements
    
    def generate_locator_with_llm(self, step: str, rag_locators: List[Dict], 
                                  visible_elements: List[Dict], url: str) -> Optional[Dict]:
        """
        Use LLM to generate a correct locator when RAG locators fail.
        
        Args:
            step: Step description
            rag_locators: List of RAG-generated locators that failed
            visible_elements: List of visible and interactable elements from page
            url: Page URL
        
        Returns:
            Dict with generated locator or None if generation fails
        """
        try:
            import google.genai as genai
            from google.genai.types import GenerateContentConfig
            import re
            import json
            
            # Format visible elements for LLM (limit to top 50 to avoid token limits)
            elements_text = []
            for i, elem in enumerate(visible_elements[:50], 1):
                elem_str = f"{i}. {elem['tagName']}"
                if elem['attributes']['id']:
                    elem_str += f" id='{elem['attributes']['id']}'"
                if elem['attributes']['name']:
                    elem_str += f" name='{elem['attributes']['name']}'"
                if elem['attributes']['data-testid']:
                    elem_str += f" data-testid='{elem['attributes']['data-testid']}'"
                if elem['attributes']['aria-label']:
                    elem_str += f" aria-label='{elem['attributes']['aria-label']}'"
                if elem['textContent']:
                    elem_str += f" text='{elem['textContent'][:50]}'"
                if elem['attributes']['placeholder']:
                    elem_str += f" placeholder='{elem['attributes']['placeholder']}'"
                elements_text.append(elem_str)
            
            # Format RAG locators
            rag_locators_text = []
            for i, loc in enumerate(rag_locators, 1):
                rag_locators_text.append(f"{i}. [{loc.get('type', 'unknown')}] {loc.get('selector', 'N/A')}")
            
            prompt = f"""You are a senior test automation engineer. Your task is to generate a **production-ready, robust locator** for the following step.

STEP TO AUTOMATE:
{step}

RAG-GENERATED LOCATORS (These failed - do not use them):
{chr(10).join(rag_locators_text) if rag_locators_text else 'None provided'}

VISIBLE AND INTERACTABLE ELEMENTS ON THE PAGE:
{chr(10).join(elements_text) if elements_text else 'No elements found'}

PAGE URL: {url}

TASK:
Analyze the step description and find the most appropriate element from the list above.
Generate a locator that is **resilient to UI changes** and follows best practices for test automation.

IMPORTANT - SEMANTIC MATCHING:
- Consider semantic synonyms and similar actions when matching:
  * "Save" = "Post", "Submit", "Store", "Create", "Add"
  * "Cancel" = "Close", "Dismiss", "Back", "Exit"
  * "Delete" = "Remove", "Clear", "Trash"
  * "Edit" = "Modify", "Update", "Change"
  * "Search" = "Find", "Lookup", "Query"
- If the step mentions "Save" but you see a "Post" button, they are semantically equivalent
- Match based on action intent, not just exact text
- Consider button roles and aria-labels that convey similar meaning

REQUIREMENTS FOR PRODUCTION-READY LOCATORS:
1. **Prioritize Stable Attributes**: Always prefer `data-testid`, `data-test`, `data-qa`, `id`, or `name` if available.
2. **Avoid Brittle Selectors**: Do NOT use absolute XPaths (e.g., `/html/body/div[1]/...`) or long CSS chains.
3. **Use Semantic Locators**: If no stable attribute exists, use `aria-label`, `role`, or specific text content that is unlikely to change.
4. **Resilience**: The locator should still work if the layout changes slightly (e.g., a button moves to a different container).
5. **Specificity**: The locator must be specific enough to identify the *exact* element, but generic enough to be stable.

OUTPUT FORMAT:
Return ONLY a JSON object with this exact structure:
{{
  "type": "data-testid|id|name|aria-label|role|text|xpath|css",
  "selector": "the actual selector string",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation including semantic matching if applicable"
}}

Return ONLY the JSON, no other text."""

            # Initialize client if not already done
            if not hasattr(self, '_llm_client'):
                from tools.rag import AppConfig
                cfg = AppConfig()
                self._llm_client = genai.Client(api_key=cfg.google_ai_api_key)
                self._llm_model = cfg.text_model
            
            config = GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=512,
                top_p=0.95,
            )
            
            response = self._llm_client.models.generate_content(
                model=self._llm_model,
                contents=[prompt],
                config=config,
            )
            
            if not response.candidates or not response.candidates[0].content:
                return None
            
            response_text = response.candidates[0].content.parts[0].text.strip()
            
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                locator_data = json.loads(json_match.group())
                # Add validation status
                locator_data['validated'] = False
                locator_data['stability'] = 'high' if locator_data.get('type') in ['data-testid', 'id', 'name'] else 'medium'
                return locator_data
            
            return None
            
        except Exception as e:
            self.logger.error(f"[CDPTool] Error generating locator with LLM: {e}")
            return None
    
    def _find_node_in_snapshot_by_locator(self, snapshot: Dict, selector: str, locator_type: str) -> Optional[Dict]:
        """Find a node in snapshot that matches the given locator."""
        import json
        
        if not self.current_tab:
            return None
        
        try:
            # Get the nodeId from the live page using the locator
            if locator_type == 'xpath':
                js_code = f"""
                (function() {{
                    try {{
                        var xpath = {json.dumps(selector)};
                        var result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                        var node = result.singleNodeValue;
                        if (node) {{
                            return node.textContent || '';
                        }}
                        return '';
                    }} catch(e) {{
                        return '';
                    }}
                }})()
                """
                result = self.current_tab.Runtime.evaluate(expression=js_code)
                if 'result' in result and 'value' in result['result']:
                    text_content = result['result']['value']
                    # Find node in snapshot with matching text
                    for node in snapshot.get('nodes', []):
                        if node.get('runtime', {}).get('textContent', '') == text_content:
                            return node
            else:
                # CSS selector
                result = self.current_tab.DOM.querySelector(
                    nodeId=self.current_tab.DOM.getDocument()['root']['nodeId'],
                    selector=selector
                )
                if 'nodeId' in result and result['nodeId']:
                    # Get node info from CDP
                    node_info = self.current_tab.DOM.describeNode(nodeId=result['nodeId'])
                    backend_id = node_info.get('node', {}).get('backendNodeId')
                    
                    # Find matching node in snapshot
                    for node in snapshot.get('nodes', []):
                        if node.get('backendNodeId') == backend_id:
                            return node
        except Exception as e:
            self.logger.debug(f"Error finding node in snapshot by locator: {e}")
        
        return None
    
    def _get_best_validated_locator(self, validated_locators: List[Dict]) -> Dict:
        """
        Get the best locator from validated locators.
        Prefers validated locators with high stability.
        """
        # First, try to find a validated locator
        validated = [loc for loc in validated_locators if loc.get('validated', False)]
        
        if validated:
            # Sort by stability and confidence
            validated.sort(key=lambda x: (
                {'high': 3, 'medium': 2, 'low': 1}.get(x.get('stability', 'low'), 1),
                x.get('confidence', 0)
            ), reverse=True)
            return validated[0]
        
        # If no validated locators, return best unvalidated one
        validated_locators.sort(key=lambda x: (
            {'high': 3, 'medium': 2, 'low': 1}.get(x.get('stability', 'low'), 1),
            x.get('confidence', 0)
        ), reverse=True)
        
        return validated_locators[0] if validated_locators else {
            'type': 'css',
            'selector': 'body',
            'confidence': 0.1,
            'validated': False
        }
