# `find_relevant_node` Function - Complete Explanation

## Overview
The `find_relevant_node` function is the core method in `CDPTool` that finds the best DOM element (node) for a given automation step by:
1. Inspecting the web page using Chrome DevTools Protocol (CDP)
2. Searching for elements matching the step description
3. Generating multiple locator strategies
4. Validating locators against the live page
5. Returning the best validated locator

---

## Function Flow Diagram

```
find_relevant_node(step, context, url)
    │
    ├─→ [Step 1] Check for active CDP session
    │   ├─→ If session exists → Reuse cached snapshot
    │   └─→ If no session → Extract URL and start new inspection
    │
    ├─→ [Step 2] Extract URL (if not provided)
    │   ├─→ From step text (regex: http://, https://, localhost:port)
    │   └─→ From context text
    │   └─→ If no URL → Fallback to inference
    │
    ├─→ [Step 3] Inspect Page (if no active session)
    │   ├─→ Launch Chrome headless
    │   ├─→ Connect via CDP
    │   ├─→ Navigate to URL
    │   ├─→ Wait for page load
    │   └─→ Get DOM snapshot (all nodes with properties)
    │
    ├─→ [Step 4] Find Matching Nodes
    │   ├─→ Call find_nodes_by_text_enhanced()
    │   ├─→ Search through all DOM nodes
    │   ├─→ Match step text against:
    │   │   ├─→ textContent
    │   │   ├─→ aria-label
    │   │   ├─→ title
    │   │   └─→ alt text
    │   ├─→ Generate text variations (case-insensitive, i18n)
    │   ├─→ Calculate relevance scores
    │   └─→ Sort by score (best match first)
    │
    ├─→ [Step 5] Generate Locators (if nodes found)
    │   ├─→ Call _generate_enhanced_locators()
    │   ├─→ Create multiple locator strategies:
    │   │   ├─→ data-testid (highest priority)
    │   │   ├─→ Stable ID (non-dynamic)
    │   │   ├─→ name attribute
    │   │   ├─→ aria-label
    │   │   ├─→ role + accessible name
    │   │   ├─→ Stable class (non-hashed)
    │   │   ├─→ XPath
    │   │   └─→ Tag name (fallback)
    │   ├─→ Assign confidence scores (0.0-1.0)
    │   └─→ Assign stability ratings (high/medium/low)
    │
    ├─→ [Step 6] Validate Locators (if requested)
    │   ├─→ Call _validate_locators()
    │   ├─→ For each locator:
    │   │   ├─→ Execute JavaScript: document.querySelector(selector)
    │   │   ├─→ Check if element exists
    │   │   ├─→ Check if element is visible
    │   │   └─→ Mark as validated=True/False
    │   └─→ Prioritize validated locators
    │
    ├─→ [Step 7] Select Best Locator
    │   ├─→ Call _get_best_validated_locator()
    │   ├─→ Priority order:
    │   │   1. Validated locators (highest stability)
    │   │   2. Non-validated locators (highest confidence)
    │   │   3. Highest stability score
    │   └─→ Return best locator
    │
    └─→ [Step 8] Return Result
        ├─→ If node found → Return comprehensive node data
        └─→ If no node found → Fallback to inference
```

---

## Detailed Step-by-Step Explanation

### Step 1: Session Management
```python
if use_session and self.session_active and self.current_snapshot:
    # Reuse existing CDP session (faster for multiple steps)
    snapshot = self.current_snapshot
    url = self.current_url
else:
    # Start new CDP inspection
    snapshot = self.inspect_page(url, keep_open=validate_locators)
```

**Purpose**: Optimize performance by reusing a single CDP session for all steps instead of launching Chrome multiple times.

---

### Step 2: URL Extraction
```python
url = self._extract_url_from_step(step, context)
```

**Regex Pattern**: `r'(https?://[^\s\)]+|www\.[^\s\)]+|localhost:\d+)'`

**Examples**:
- Step: "Navigate to http://localhost:3000/login" → Extracts `http://localhost:3000`
- Step: "Go to example.com" → Extracts `http://example.com`
- Context: "The page at https://app.example.com has a form" → Extracts `https://app.example.com`

**Fallback**: If no URL found, returns inference-based result (no CDP inspection).

---

### Step 3: Page Inspection
```python
snapshot = self.inspect_page(url, keep_open=validate_locators)
```

**What happens**:
1. Launches Chrome in headless mode
2. Connects via CDP on port 9222
3. Navigates to URL
4. Waits for page load event
5. Traverses entire DOM tree (including shadow DOM, iframes)
6. Extracts comprehensive data for each node:
   - Node type, name, attributes
   - Visibility, interactability
   - Computed styles, box model
   - Text content, aria-labels
   - Event listeners
   - Framework hints (React, Angular, Vue)

**Returns**: Dictionary with `{'url': str, 'timestamp': str, 'nodes': [List of node dicts]}`

---

### Step 4: Node Matching
```python
matching_nodes = self.find_nodes_by_text_enhanced(snapshot, step, prefer_interactive=True)
```

**Search Process**:
1. **Text Extraction**: Gets text from each node:
   - `textContent` (visible text)
   - `aria-label` (accessibility label)
   - `title` (tooltip text)
   - `alt` (image alt text)

2. **Text Variations**: Generates variations for flexible matching:
   ```python
   "Login Button" → ["login button", "LOGIN BUTTON", "Login Button", "loginbutton"]
   ```

3. **Matching Logic**:
   - Case-insensitive matching
   - Partial text matching (contains)
   - Exact text matching (highest score)
   - Starts-with matching (medium score)

4. **Scoring System**:
   - Exact match: +100 points
   - Starts with: +50 points
   - Contains: +25 points
   - Short text (<50 chars): +20 points
   - Interactive element (button, input): +30 points
   - Has data-testid: +15 points
   - Has stable ID: +15 points

5. **Filtering**:
   - Skips generic elements (HTML, BODY, HEAD, SCRIPT, STYLE)
   - Prefers interactive elements if `prefer_interactive=True`
   - Sorts by score (highest first)

**Returns**: List of matching nodes, sorted by relevance score.

---

### Step 5: Locator Generation
```python
enhanced_locators = self._generate_enhanced_locators(best_node, snapshot)
```

**Locator Strategies** (in priority order):

1. **Data Attributes** (Stability: High, Confidence: 0.95)
   ```css
   [data-testid="login-button"]
   [data-cy="submit-form"]
   ```

2. **Stable ID** (Stability: High, Confidence: 1.0)
   ```css
   #login-button  /* Only if ID is not dynamic */
   ```
   - Skips dynamic IDs (UUIDs, hashes, React-generated IDs)

3. **Name Attribute** (Stability: High, Confidence: 0.9)
   ```css
   [name="username"]
   ```

4. **Aria-Label** (Stability: High, Confidence: 0.9)
   ```css
   [aria-label="Close dialog"]
   ```
   - Great for icon-only buttons

5. **Role + Accessible Name** (Stability: Medium, Confidence: 0.85)
   ```css
   [role="button"][aria-label="Submit"]
   ```

6. **Stable Class** (Stability: Medium, Confidence: 0.7)
   ```css
   .login-button  /* Only if class is not hashed/minified */
   ```
   - Skips hashed classes (e.g., `_abc123`, `xyz789`)

7. **XPath** (Stability: Low, Confidence: 0.6)
   ```xpath
   /html/body/div[1]/form/button[1]
   ```

8. **Tag Name** (Stability: Low, Confidence: 0.1)
   ```css
   button
   ```

**Edge Case Handling**:
- Detects dynamic IDs (UUIDs, hashes)
- Detects hashed classnames (minified CSS)
- Handles shadow DOM elements
- Handles iframe contexts
- Handles portal-rendered elements

---

### Step 6: Locator Validation
```python
if validate_locators and self.current_tab:
    validated_locators = self._validate_locators(enhanced_locators, url)
```

**Validation Process**:
For each locator:
1. Execute JavaScript on the live page:
   ```javascript
   const element = document.querySelector(selector);
   if (element) {
       const rect = element.getBoundingClientRect();
       return {
           exists: true,
           visible: rect.width > 0 && rect.height > 0,
           inViewport: rect.top >= 0 && rect.left >= 0
       };
   }
   return { exists: false };
   ```

2. Mark locator as:
   - `validated: True` if element exists and is visible
   - `validated: False` if element doesn't exist or is hidden

**Purpose**: Ensure locators actually work on the live page before returning them.

---

### Step 7: Best Locator Selection
```python
best_locator = self._get_best_validated_locator(validated_locators)
```

**Selection Priority**:
1. **Validated locators** with highest stability
2. **Validated locators** with highest confidence
3. **Non-validated locators** with highest stability
4. **Non-validated locators** with highest confidence

**Returns**: Single locator dictionary with:
```python
{
    'type': 'attribute',  # or 'id', 'xpath', 'css', etc.
    'selector': "[data-testid='login-button']",
    'confidence': 0.95,
    'stability': 'high',
    'validated': True
}
```

---

### Step 8: Result Construction
```python
result = {
    "step": step,  # Original step description
    "node_selector": best_locator.get('selector', ''),
    "node_type": best_locator.get('type', 'css'),
    "node_name": best_node.get('nodeName', ''),  # e.g., "BUTTON"
    "attributes": best_node.get('attributes', {}),  # All HTML attributes
    "xpath": best_node.get('nodePath', ''),  # XPath to element
    "is_visible": best_node.get('isVisible', True),
    "is_interactable": best_node.get('isInteractable', False),
    "locators": validated_locators,  # All locators with validation status
    "best_locator": best_locator,  # Selected best locator
    "context": context,
    "source": "cdp_inspector",  # or "inference" if fallback
    "url": url,
    "validation_performed": validate_locators
}
```

---

## Fallback Behavior

If any step fails, the function falls back to **inference-based node detection**:

```python
def _infer_node_from_step(self, step: str, context: Optional[str] = None):
    # Simple keyword-based inference
    if "button" in step.lower() or "click" in step.lower():
        return {"node_selector": "button", "source": "inference"}
    elif "input" in step.lower() or "fill" in step.lower():
        return {"node_selector": "input", "source": "inference"}
    # ... etc
```

**Inference is used when**:
- No URL found in step/context
- CDP inspection fails
- No matching nodes found
- Exception occurs during processing

---

## Why You Might Not See Logs

### Possible Reasons:
1. **Logging Level**: Logger might be set to WARNING or ERROR instead of INFO
2. **Logger Name**: Logger name is "CDPTool" - ensure it's configured in your logging setup
3. **Stream Handler**: Logs might be going to a file instead of console
4. **Exception Handling**: Errors might be caught and logged at DEBUG level

### How to Enable Logs:

Add this to your code (e.g., in `rag_streamlit_app.py` or `main.py`):
```python
import logging

# Configure CDPTool logger
cdp_logger = logging.getLogger("CDPTool")
cdp_logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s [CDPTool] %(levelname)s: %(message)s'))
cdp_logger.addHandler(handler)
```

Or set root logger to INFO:
```python
logging.basicConfig(level=logging.INFO)
```

---

## Example Execution Flow

**Input**:
```python
step = "Click the Login button"
context = "The login page at http://localhost:3000 has a blue login button"
url = "http://localhost:3000"
```

**Execution**:
1. ✅ Session check: No active session
2. ✅ URL extraction: `http://localhost:3000` (from context)
3. ✅ CDP inspection: Launches Chrome, navigates, gets 500+ nodes
4. ✅ Node matching: Finds 3 buttons with "login" text
   - Button 1: "Login" (exact match, score: 130)
   - Button 2: "Login to Account" (contains match, score: 55)
   - Button 3: "User Login Form" (contains match, score: 45)
5. ✅ Best node: Button 1 selected
6. ✅ Locator generation: Creates 5 locators:
   - `[data-testid="login-btn"]` (confidence: 0.95, stability: high)
   - `#login-button` (confidence: 1.0, stability: high)
   - `button[aria-label="Login"]` (confidence: 0.9, stability: high)
   - `/html/body/div/button[1]` (confidence: 0.6, stability: low)
   - `button` (confidence: 0.1, stability: low)
7. ✅ Validation: Tests all 5 locators, 3 are valid
8. ✅ Best locator: `[data-testid="login-btn"]` (validated, high stability)
9. ✅ Return result with all locators and best one selected

**Output**:
```python
{
    "step": "Click the Login button",
    "node_selector": "[data-testid='login-btn']",
    "node_type": "attribute",
    "node_name": "BUTTON",
    "source": "cdp_inspector",
    "validation_performed": True,
    "locators": [...],  # All 5 locators with validation status
    "best_locator": {...}  # Selected best locator
}
```

---

## Performance Considerations

- **First call**: ~3-5 seconds (Chrome launch + page load + DOM traversal)
- **Subsequent calls (with session)**: ~0.1-0.5 seconds (reuses snapshot)
- **Validation**: Adds ~0.5-1 second per locator (JavaScript execution)

**Optimization**: Use `start_session()` before processing multiple steps to reuse the CDP connection.

---

## Error Handling

The function has multiple fallback layers:
1. **URL missing** → Inference fallback
2. **CDP inspection fails** → Inference fallback
3. **No matching nodes** → Inference fallback
4. **Exception during processing** → Inference fallback

All errors are logged at ERROR level with full tracebacks.

