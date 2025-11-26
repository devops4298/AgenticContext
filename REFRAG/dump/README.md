# Dump Folder

This folder contains files that are not used in production but are kept for reference.

## CDP Files:

1. **cdp.py** - Standalone browser automation framework (not used in production)
   - Comprehensive CDP browser automation solution
   - Alternative implementation to `tools/cdp_tool.py`
   - Includes full browser management, element tracking, and actions

2. **test_cdp_edge_cases.py** - Test file for cdp.py
   - Tests various edge cases for the standalone CDP framework
   - Validates handling of dynamic IDs, shadow DOM, iframes, etc.

3. **test_cdp_tool_validation.py** - Test file for cdp_tool.py
   - Tests locator validation functionality
   - Validates that CDPTool correctly tests locators on the page

## RAG Files (Consolidated into rag.py):

These files were consolidated into a single `rag.py` file for better organization:

1. **rag_config.py** - Configuration and constants (now in rag.py Section 1)
2. **rag_utils.py** - Utility functions (now in rag.py Section 2)
3. **rag_core.py** - Core RAG components (now in rag.py Section 3)
4. **rag_agents.py** - Agentic RAG components (now in rag.py Section 4)
5. **rag_prod.py** - RAG Pipeline orchestrator (now in rag.py Section 5)
6. **tools/rag_tool.py** - RAG Tool wrapper (now in rag.py Section 6)

## Note:
These files were moved here to clean up the repository while preserving them for reference.

## Other Files:

1. **main.py** - CLI (command-line) entry point
   - Terminal-based interface for the multi-agent system
   - Interactive loop for automation requests
   - Useful for automation/scripting, but redundant if using Streamlit GUI
   - Moved here since `rag_streamlit_app.py` provides the web interface

## Production Files:
- `tools/rag.py` - Consolidated RAG system with all functionality in one clean, modular file
- `tools/cdp_tool.py` - The actual CDP tool used in production by ScripterAgent
- `rag_streamlit_app.py` - Web GUI frontend (Streamlit) - **Main entry point for users**

