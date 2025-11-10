# Agentic RAG + Playwright Control  

<p align="center">
  <img src="https://img.shields.io/badge/Google%20ADK-ready-success?style=for-the-badge" alt="Google ADK Ready" />
  <img src="https://img.shields.io/badge/Gemini-embeddings-5f9ea0?style=for-the-badge" alt="Gemini Embeddings" />
  <img src="https://img.shields.io/badge/Playwright-MCP-blueviolet?style=for-the-badge" alt="Playwright MCP" />
  <img src="https://img.shields.io/badge/Streamlit-dashboard-ff4b4b?style=for-the-badge" alt="Streamlit Dashboard" />
</p>

> **A production-ready context-engineering workspace.**  
> Blend Gemini-powered retrieval, ADK agents, and Playwright automation—controlled either from a Streamlit console or the ADK CLI.

---

## 📌 Quick Links

- [Why This Stack](#-why-this-stack)
- [Architecture](#-architecture)
- [Key Capabilities](#-key-capabilities)
- [Prerequisites](#-prerequisites)
- [Setup Guide](#-setup-guide)
- [Embedding Pipeline](#-embedding-pipeline)
- [Streamlit Agent Chat](#-streamlit-agent-chat)
- [Troubleshooting](#-troubleshooting)
- [Repository Map](#-repository-map)
- [Roadmap & Credits](#-roadmap--credits)

---

## 🤖 Why This Stack

| Need | How it’s solved |
|------|-----------------|
| High-quality RAG | Gemini `text-embedding-004` + ChromaDB |
| Multi-tool orchestration | Google ADK agents & instructions |
| Rich UI for ops teams | Streamlit console & agent chat |
| UI automation | Playwright MCP (`npx -y @playwright/mcp`) baked into the agent |

---

## 🗺️ Architecture

```
User Request
   ├─▶ Module 4 · Query Rewriter (Gemini)
   ├─▶ Module 3 · Vector Retrieval (Chroma)
   ├─▶ Module 5 · Context Composer (token budget aware)
   ├─▶ Module 6 · LLM Reasoning (Gemini)
   └─▶ Module 7 · Feedback Logger (optional audit trail)

Optional Toolsets
   ├─▶ Playwright MCP Toolset (browser automation via `npx -y @playwright/mcp`)
   └─▶ Extend with additional ADK toolsets as needed
```

- Root ADK agent: [`agentic-rag/agent.py`](agentic-rag/agent.py)
- Embedding & ingestion: [`tools/module3_embedder_tool.py`](agentic-rag/tools/module3_embedder_tool.py)
- Query rewrite with typo support: [`tools/module4_query_rewriter_tool.py`](agentic-rag/tools/module4_query_rewriter_tool.py)
- Full pipeline orchestrator: [`agents/module6_agentic_rag.py`](agentic-rag/agents/module6_agentic_rag.py)

---

## ✨ Key Capabilities

| Capability | What you get |
|------------|--------------|
| **Streamlit Console** | Rebuild embeddings, inspect retrieved chunks, monitor vector health, capture feedback. |
| **Agent Chat** | Fully agent-driven workflow (RAG → script draft → user confirmation → Playwright MCP run). |
| **Gemini Embeddings** | Document ingestion + query embeddings through Gemini `text-embedding-004`; typo-tolerant rewrites. |
| **Playwright MCP** | Launches `npx -y @playwright/mcp`, executes `browser_*` functions, returns JSON responses + screenshots. |
| **Programmatic Access** | Import `root_agent` or the RAG modules directly for integration tests or pipelines. |

---

## 🛠️ Prerequisites

- macOS / Linux (ARM64 tested on macOS Sequoia).
- Python 3.10 or 3.11.
- Node.js ≥ 18.
- Google ADK installed (`pip install google-adk`).
- Gemini credentials via API key *or* Vertex AI project.

---

## 🚀 Setup Guide

### 1. Clone & Install
```bash
git clone https://github.com/your-org/agentic-rag-context-engineering.git AgenticContext
cd AgenticContext

pip install --upgrade pip setuptools wheel
pip install -r agentic-rag/requirements.txt
```

### 2. Configure Environment
```ini
# agentic-rag/.env
GOOGLE_AI_API_KEY=your_gemini_key
# OR
VERTEX_AI_PROJECT_ID=your_project
GOOGLE_CLOUD_REGION=us-central1

# Optional extras
OPENAI_API_KEY=...
```

### 3. Verify Playwright MCP (one-time)
```bash
npx -y @playwright/mcp --help
```

### 4. Streamlit Control Plane
```bash
cd agentic-rag
streamlit run app.py
```
Choose your source folder in the sidebar (e.g. `/Users/.../orebishopping/src`) and click **Rebuild Vector Store**.

### 5. ADK CLI Agent
```bash
adk run agentic-rag
```
The CLI follows the same instruction flow as the Streamlit chat.

### 6. Programmatic Usage
```python
from agentic_rag.agent import root_agent
from google.adk.runners import InMemoryRunner

runner = InMemoryRunner(agent=root_agent)
events = await runner.run_debug(
    "create a playwright script for ...",
    user_id="dev",
    session_id="dev_session",
    quiet=True,
)
```
`root_agent` bundles:
- `rag_answer_tool` (Gemini-driven RAG flow)
- Playwright MCP toolset (`playwright__*` functions)

Instructions in `agent.py` enforce the order: RAG first → script draft → explicit user approval → MCP execution.

---

## 🧬 Embedding Pipeline

- **Model**: Gemini `text-embedding-004`.
- **Persistence**: ChromaDB (`agentic-rag/chroma_db`).
- **Ingestion**: `_ingest_directory()` handles Markdown, code, CSV, JSON, PDF (`pypdf`), PPTX (`python-pptx`), notebooks, etc. Binary assets trigger a logged warning and are skipped.
- **Query Flow**: `handle_query()` rewrites the question, embeds it, retrieves top-K matches, composes context, and reasons with Gemini.
- **Credentials**: Make sure `GOOGLE_AI_API_KEY` or `VERTEX_AI_*` env vars are set before running ingestion or queries.

---

## 💬 Streamlit Agent Chat

- Uses a cached `InMemoryRunner` to keep ADK session state across chat turns. “Clear conversation” resets both UI and agent state.
- Agent output includes:
  1. RAG summary + evidence.
  2. Drafted Playwright TypeScript (with selectors derived from context).
  3. Awaiting user confirmation (“run it”, “execute”, etc.).
  4. Playwright MCP tool calls/responses (navigate, click, fill, screenshot).
- Tool events are rendered with their JSON payloads for easy debugging.

---

## 🛟 Troubleshooting

| Issue | Fix |
|-------|-----|
| Streamlit spinner never ends | Large folders can take minutes; watch the terminal logs. To iterate faster, set `st.session_state["_ingest_file_limit"]`. |
| “No supporting context found” | Rebuild the vector store and confirm the rewriter appended typo corrections (`Jornl (Journal)`). |
| Playwright MCP warnings (`cancel scope`) | Known anyio behaviour—noise only. |
| `npx` can’t find the package | Use `@playwright/mcp` (not `@microsoft/...`). Ensure Node ≥ 18. |
| ARM vs x86 wheels | Reinstall with `pip install --force-reinstall <pkg> --platform=macosx-11.0-arm64`. |

---

## 🗂️ Repository Map

```
agentic-rag/
├── agent.py                  # Root ADK agent (Gemini + Playwright MCP)
├── app.py                    # Streamlit console & agent chat
├── agents/
│   └── module6_agentic_rag.py
├── tools/
│   ├── module2_chunker_tool.py
│   ├── module3_embedder_tool.py
│   ├── module4_query_rewriter_tool.py
│   ├── module5_context_composer_tool.py
│   └── module7_memory_manager_tool.py
├── chroma_db/                # Vector persistence
├── data/sample_docs/
└── memory_log.json
```

---

## 🔭 Roadmap & Credits

**Next up**
- Feed positive feedback back into retrieval.
- Automated evaluation suites (OpenAI Evals, Playwright metrics).
- Package as an ADK app for Cloud Run / GKE deployment.
- Extend to multimodal ingestion and cross-lingual embeddings.

**Credits**
- Google ADK team for the agent framework.
- ChromaDB for the vector store backbone.
- Playwright MCP (`@playwright/mcp`) for browser automation.
- Inspiration from Weaviate Context Engineering & OpenAI Cookbook examples.

---

**Maintainer**: Chetan Chauhan  
**License**: Apache-2.0  
Questions or suggestions? Open an issue or start a discussion. Happy building! 🚀
