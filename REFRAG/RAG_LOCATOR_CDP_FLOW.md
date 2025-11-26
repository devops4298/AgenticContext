# RAG Locator + CDP Validation Flow

## Overview

This document describes the enhanced flow where RAG generates initial locators from documentation context, and CDP validates/corrects them iteratively.

## Architecture

```
User Request
    ↓
Orchestrator Agent
    ↓
RAG Agent (gets context)
    ↓
Locator Generator Agent (NEW) ← generates locators from RAG context
    ↓
Scripter Agent (enhanced)
    ├─→ Start CDP session
    ├─→ For each step:
    │   ├─→ Try RAG-generated locators
    │   ├─→ If fail → Use CDP snapshot to find correct locators
    │   └─→ Update locators for step
    └─→ Return nodes with validated locators
    ↓
Script Development Agent (uses validated locators)
```

## Components

### 1. LocatorGeneratorAgent (NEW)

**File**: `agents/locator_generator_agent.py`

**Responsibilities**:
- Uses LLM to analyze RAG context and step descriptions
- Generates initial locators (CSS selectors, XPath, etc.) for each step
- Prioritizes stable locators (data-testid, stable IDs, aria-labels)
- Returns structured locator suggestions

**Input**:
- Steps list
- RAG context (step_contexts with answers and retrieved chunks)

**Output**:
```python
{
    "step_1": [
        {
            "type": "attribute",
            "selector": "[data-testid='login-button']",
            "confidence": 0.9,
            "stability": "high",
            "source": "rag_generated",
            "validated": False,
            "reasoning": "Documentation mentions data-testid for login button"
        },
        ...
    ],
    "step_2": [...],
    ...
}
```

### 2. Enhanced ScripterAgent

**File**: `agents/scripter_agent.py`

**New Flow**:
1. **Generate RAG Locators**: Call `LocatorGeneratorAgent` to get initial locators for all steps
2. **Start CDP Session**: Launch Chrome and get DOM snapshot
3. **For Each Step**:
   - **Try RAG Locators**: Test each RAG-generated locator on the live page
   - **If Success**: Use the locator, generate comprehensive locators from the found node, validate them
   - **If Failure**: Use CDP snapshot to find correct locators via text matching
   - **Update Locators**: Store both RAG locators (for reference) and validated locators (for use)

**Key Methods**:
- `get_nodes_for_steps()`: Main orchestration method
- Uses `cdp_tool.find_node_by_locators()` to test RAG locators
- Falls back to `cdp_tool.find_relevant_node()` if RAG locators fail

### 3. Enhanced CDPTool

**File**: `tools/cdp_tool.py`

**New Methods**:

#### `find_node_by_locators(locators, step, snapshot)`
- Tests each provided locator on the live page
- If a locator works, finds the corresponding node in the snapshot
- If all locators fail, falls back to text-based matching using the step description

#### `_find_node_in_snapshot_by_locator(snapshot, selector, locator_type)`
- Helper method to find a node in the snapshot that matches a validated locator
- Uses CDP to get node info from the live page, then matches it to snapshot nodes

## Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ 1. RAG Agent                                                │
│    - Queries RAG for each step                              │
│    - Returns context with answers and retrieved chunks      │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Locator Generator Agent (NEW)                            │
│    - Analyzes RAG context using LLM                         │
│    - Generates 2-5 locators per step                        │
│    - Prioritizes: data-testid > stable ID > aria-label > ...│
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Scripter Agent                                           │
│    - Starts CDP session (single session for all steps)      │
│    - Gets DOM snapshot                                      │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. For Each Step:                                           │
│                                                              │
│    ┌──────────────────────────────────────────┐            │
│    │ 4a. Try RAG Locators                      │            │
│    │     - Test each locator on live page      │            │
│    │     - If found → Use it                   │            │
│    └───────────────┬──────────────────────────┘            │
│                    ↓                                         │
│    ┌──────────────────────────────────────────┐            │
│    │ 4b. Generate Comprehensive Locators       │            │
│    │     - From found node                     │            │
│    │     - Multiple strategies (data-testid,   │            │
│    │       ID, aria-label, XPath, etc.)        │            │
│    └───────────────┬──────────────────────────┘            │
│                    ↓                                         │
│    ┌──────────────────────────────────────────┐            │
│    │ 4c. Validate All Locators                │            │
│    │     - Test each on live page             │            │
│    │     - Mark as validated=True/False       │            │
│    └───────────────┬──────────────────────────┘            │
│                    ↓                                         │
│    ┌──────────────────────────────────────────┐            │
│    │ 4d. Select Best Locator                  │            │
│    │     - Prefer validated + high stability   │            │
│    └──────────────────────────────────────────┘            │
│                                                              │
│    ┌──────────────────────────────────────────┐            │
│    │ IF RAG Locators Failed:                   │            │
│    │     - Use CDP snapshot                    │            │
│    │     - Match by step text                  │            │
│    │     - Generate locators from found node   │            │
│    │     - Mark rag_locators_worked=False      │            │
│    └──────────────────────────────────────────┘            │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Return Results                                           │
│    - Complete element JSON for each step                    │
│    - All locators (RAG + CDP-generated)                     │
│    - Validation status                                      │
│    - Best locator selected                                  │
└─────────────────────────────────────────────────────────────┘
```

## Example Execution

### Input
```python
steps = [
    "Navigate to http://localhost:3000",
    "Click the Login button",
    "Fill in the username field"
]

rag_context = {
    "step_contexts": {
        "step_1": {
            "answer": "Navigate to the application URL...",
            "retrieved": [...]
        },
        "step_2": {
            "answer": "The login button has data-testid='login-btn'...",
            "retrieved": [...]
        },
        ...
    }
}
```

### Step 1: Locator Generation
```python
rag_locators = {
    "step_1": [],  # Navigation step, no locator needed
    "step_2": [
        {
            "type": "attribute",
            "selector": "[data-testid='login-btn']",
            "confidence": 0.95,
            "source": "rag_generated"
        },
        {
            "type": "xpath",
            "selector": "//button[contains(text(), 'Login')]",
            "confidence": 0.7,
            "source": "rag_generated"
        }
    ],
    ...
}
```

### Step 2: CDP Validation
```python
# For step_2:
# 1. Test [data-testid='login-btn'] → ✅ Works!
# 2. Find node in snapshot
# 3. Generate comprehensive locators:
#    - [data-testid='login-btn'] (validated: True)
#    - #login-button (validated: True)
#    - button[aria-label='Login'] (validated: True)
#    - //button[1] (validated: True)
# 4. Select best: [data-testid='login-btn'] (validated, high stability)
```

### Output
```python
{
    "step_2": {
        "step": "Click the Login button",
        "node": {
            "element": {
                "nodeName": "BUTTON",
                "attributes": {
                    "data-testid": "login-btn",
                    "id": "login-button",
                    "aria-label": "Login"
                },
                ...
            },
            "locators": [
                {
                    "type": "attribute",
                    "selector": "[data-testid='login-btn']",
                    "validated": True,
                    "stability": "high",
                    "confidence": 0.95
                },
                ...
            ],
            "best_locator": {
                "type": "attribute",
                "selector": "[data-testid='login-btn']",
                "validated": True
            },
            "rag_locators_used": [...],
            "rag_locators_worked": True,
            "source": "rag_locators_validated"
        }
    }
}
```

## Benefits

1. **Documentation-Driven**: Uses RAG context to suggest locators based on documentation
2. **Validated**: All locators are tested on the live page before use
3. **Self-Correcting**: If RAG locators fail, CDP automatically finds correct ones
4. **Comprehensive**: Generates multiple locator strategies for each element
5. **Stable**: Prioritizes stable locators (data-testid, stable IDs) over fragile ones (XPath, classes)
6. **Iterative**: Updates locators as steps are processed

## Error Handling

- **RAG Locator Generation Fails**: Falls back to basic locators from step text
- **All RAG Locators Fail**: Uses CDP snapshot to find correct locators
- **CDP Session Fails**: Falls back to inference-based locators
- **No Matching Nodes**: Returns inference-based result with low confidence

## Performance

- **Single CDP Session**: All steps processed in one session (faster)
- **Parallel Locator Testing**: All locators tested in sequence (could be parallelized)
- **Cached Snapshot**: DOM snapshot reused for all steps

## Future Enhancements

1. **Parallel Locator Testing**: Test multiple locators simultaneously
2. **Locator Learning**: Store successful locators for future use
3. **Context-Aware Correction**: Use page context to improve locator suggestions
4. **Multi-Page Support**: Handle navigation between pages
5. **Locator Stability Tracking**: Track which locators remain stable over time

