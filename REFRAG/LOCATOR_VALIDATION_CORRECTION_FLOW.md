# Locator Validation & Correction Flow

## Complete Flow Diagram

```
RAG Locator Generation
    ↓
ScripterAgent.get_nodes_for_steps()
    ↓
For Each Step:
    ├─→ Get RAG locators for step
    ├─→ find_node_by_locators() [VALIDATION POINT 1]
    │   ├─→ Test each RAG locator on live page
    │   ├─→ If ANY locator works → Find node in snapshot
    │   └─→ If ALL locators fail → Fallback to text matching
    │
    ├─→ IF RAG Locators Worked:
    │   ├─→ Generate enhanced locators from found node
    │   ├─→ _validate_locators() [VALIDATION POINT 2]
    │   │   ├─→ Test each enhanced locator
    │   │   └─→ Mark validated=True/False
    │   └─→ Select best validated locator
    │
    └─→ IF RAG Locators Failed:
        ├─→ find_relevant_node() [CORRECTION POINT]
        │   ├─→ Search snapshot by step text
        │   ├─→ Find matching nodes
        │   ├─→ Generate comprehensive locators
        │   └─→ Validate all locators
        └─→ Mark rag_locators_worked=False
```

## Detailed Code Flow

### Step 1: RAG Locator Generation
**File**: `agents/locator_generator_agent.py`
**Method**: `generate_locators_for_steps()`
**Lines**: 48-108

- Generates initial locators from RAG context
- Prints results (you see this output)
- Returns: `{"step_1": [locators...], "step_2": [locators...]}`

---

### Step 2: Validation Point 1 - Testing RAG Locators
**File**: `agents/scripter_agent.py`
**Method**: `get_nodes_for_steps()`
**Lines**: 141-147

```python
# Line 143: Test RAG locators on live page
node = self.cdp_tool.find_node_by_locators(
    rag_locators_for_step,  # RAG-generated locators
    step,
    snapshot
)
```

**What happens here** (`cdp_tool.py`, lines 1260-1303):
1. **For each RAG locator**:
   - Calls `_test_locator()` (line 1286)
   - Tests on live page using CDP:
     - CSS selectors: `DOM.querySelector()`
     - XPath: `document.evaluate()`
   - If locator works → Finds node in snapshot
   - If locator fails → Tries next locator

2. **If ALL RAG locators fail**:
   - Falls back to text-based matching (line 1296)
   - Uses `find_nodes_by_text_enhanced()` to search snapshot by step text

**Validation happens at**: `cdp_tool.py` line 1286 - `_test_locator()`

---

### Step 3A: If RAG Locators Worked - Enhanced Validation
**File**: `agents/scripter_agent.py`
**Lines**: 149-184

```python
if node:  # RAG locator found a node
    # Line 152: Generate comprehensive locators from found node
    enhanced_locators = self.cdp_tool._generate_enhanced_locators(node, snapshot)
    
    # Line 154: VALIDATE all enhanced locators
    validated_locators = self.cdp_tool._validate_locators(enhanced_locators, url)
    
    # Line 155: Select best validated locator
    best_locator = self.cdp_tool._get_best_validated_locator(validated_locators)
```

**What `_validate_locators()` does** (`cdp_tool.py`, lines 1166-1199):
- **For each locator**:
  - Calls `_test_locator()` (line 1183)
  - Tests on live page
  - Marks `validated: True` if found, `False` if not found
  - Adds `validation_message`

**What `_test_locator()` does** (`cdp_tool.py`, lines 1201-1258):
- Tests CSS selectors: `DOM.querySelector()`
- Tests XPath: `document.evaluate()` via JavaScript
- Returns `True` if element found, `False` otherwise

---

### Step 3B: If RAG Locators Failed - Correction
**File**: `agents/scripter_agent.py`
**Lines**: 185-195

```python
else:  # RAG locators failed
    # Line 188: CORRECTION - Use CDP snapshot to find correct locators
    node_info = self.cdp_tool.find_relevant_node(
        step,
        context=None,
        url=url,
        use_session=session_started
    )
    node_info["rag_locators_worked"] = False
    node_info["source"] = "cdp_corrected"
```

**What `find_relevant_node()` does** (`cdp_tool.py`, lines 495-599):
1. **Searches snapshot by step text** (line 563):
   - Uses `find_nodes_by_text_enhanced()`
   - Matches step description against node text content
   - Scores and ranks matching nodes

2. **Generates comprehensive locators** (line 573):
   - Calls `_generate_enhanced_locators()`
   - Creates multiple locator strategies:
     - data-testid, stable ID, name, aria-label, role, class, XPath, tag

3. **Validates all locators** (line 582):
   - Calls `_validate_locators()`
   - Tests each on live page
   - Marks validation status

4. **Selects best locator** (line 589):
   - Calls `_get_best_validated_locator()`
   - Prioritizes: validated + high stability

---

## Key Methods Summary

### 1. `find_node_by_locators()` - RAG Locator Testing
**File**: `tools/cdp_tool.py`
**Lines**: 1260-1303

**Purpose**: Test RAG-generated locators on live page

**Process**:
```python
for locator in locators:
    if _test_locator(selector, type):  # Test on live page
        node = _find_node_in_snapshot_by_locator()  # Find in snapshot
        if node:
            return node  # ✅ RAG locator worked!

# All failed → Fallback to text matching
return find_nodes_by_text_enhanced(snapshot, step)
```

---

### 2. `_validate_locators()` - Comprehensive Validation
**File**: `tools/cdp_tool.py`
**Lines**: 1166-1199

**Purpose**: Test all locators (RAG + CDP-generated) on live page

**Process**:
```python
for locator in locators:
    found = _test_locator(selector, type)  # Test on live page
    locator['validated'] = found  # Mark True/False
    locator['validation_message'] = "✅ Works" or "❌ Failed"
```

---

### 3. `_test_locator()` - Actual Testing
**File**: `tools/cdp_tool.py`
**Lines**: 1201-1258

**Purpose**: Test a single locator on the live page

**Process**:
- **CSS selectors**: `DOM.querySelector(selector)`
- **XPath**: `document.evaluate(xpath)` via JavaScript
- Returns: `True` if element found, `False` otherwise

---

### 4. `find_relevant_node()` - Correction Mechanism
**File**: `tools/cdp_tool.py`
**Lines**: 495-599

**Purpose**: Find correct locators when RAG locators fail

**Process**:
1. Search snapshot by step text
2. Find best matching node
3. Generate comprehensive locators from node
4. Validate all locators
5. Return with corrected locators

---

## Validation & Correction Points

### ✅ Validation Point 1: RAG Locator Testing
**Location**: `scripter_agent.py` line 143 → `cdp_tool.py` line 1286
- **What**: Tests each RAG-generated locator on live page
- **Method**: `find_node_by_locators()` → `_test_locator()`
- **Result**: If any locator works, node is found

### ✅ Validation Point 2: Enhanced Locator Validation
**Location**: `scripter_agent.py` line 154 → `cdp_tool.py` line 1166
- **What**: Validates all comprehensive locators generated from found node
- **Method**: `_validate_locators()` → `_test_locator()`
- **Result**: All locators marked as validated=True/False

### 🔧 Correction Point: CDP Snapshot Search
**Location**: `scripter_agent.py` line 188 → `cdp_tool.py` line 495
- **What**: When RAG locators fail, searches snapshot by step text
- **Method**: `find_relevant_node()` → `find_nodes_by_text_enhanced()`
- **Result**: Finds correct node and generates new locators

---

## Example Flow

### Scenario: RAG Locator Works

```
Step: "Click the Login button"

1. RAG generates: [data-testid='login-btn']
2. find_node_by_locators() tests it → ✅ Works!
3. Finds node in snapshot
4. Generates enhanced locators:
   - [data-testid='login-btn'] (validated: True)
   - #login-button (validated: True)
   - button[aria-label='Login'] (validated: True)
5. Selects best: [data-testid='login-btn']
6. Result: rag_locators_worked=True, source="rag_locators_validated"
```

### Scenario: RAG Locator Fails

```
Step: "Click the Submit button"

1. RAG generates: [data-testid='submit-btn']  ❌ Not found
2. find_node_by_locators() tests it → ❌ Fails
3. Falls back to text matching: "Submit button"
4. find_relevant_node() searches snapshot → ✅ Finds node
5. Generates new locators:
   - button:has-text('Submit') (validated: True)
   - //button[contains(text(), 'Submit')] (validated: True)
6. Result: rag_locators_worked=False, source="cdp_corrected"
```

---

## Where to See Validation Logs

### RAG Locator Testing
```
[ScripterAgent] Testing 3 RAG-generated locators on live page...
[CDPTool] ✅ Locator works: attribute = [data-testid='login-btn']
[CDPTool] ✅ Found node using RAG locators for step 2
```

### Enhanced Locator Validation
```
[CDPTool] Validating 5 locators against live page...
[CDPTool] ✅ Validated attribute locator: [data-testid='login-btn']
[CDPTool] ✅ Validated id locator: #login-button
[CDPTool] ❌ Failed to validate class locator: .btn-primary
[CDPTool] ✓ Validation complete: 3/5 locators are valid
```

### Correction (RAG Locators Failed)
```
[ScripterAgent] ⚠ RAG locators failed for step 2, using CDP snapshot to find correct locators
[CDPTool] All provided locators failed, searching snapshot by step text: Click the Submit button
[CDPTool] Found 2 nodes matching step text
[CDPTool] ✓ Generated 4 locator strategies
[CDPTool] ✓ Validation complete: 2/4 locators are valid
```

---

## Summary

1. **RAG Locator Validation**: `find_node_by_locators()` tests RAG locators (line 143 in scripter_agent.py)
2. **Enhanced Locator Validation**: `_validate_locators()` tests all locators (line 154 in scripter_agent.py)
3. **Correction**: `find_relevant_node()` finds correct locators when RAG fails (line 188 in scripter_agent.py)

All validation happens via `_test_locator()` which uses CDP to test selectors on the live page.

