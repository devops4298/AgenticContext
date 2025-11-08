# 🧠 Agentic RAG Framework

A hands-on implementation of a **Context-Engineered Retrieval-Augmented Generation (RAG)** system built with the **Google Agent Development Kit (ADK)** and an open-source vector store (Chroma). The project follows the Weaviate "Context Engineering" methodology: treat context as a managed supply chain—plan it, encode it, retrieve it, assemble it, reason over it, and capture user feedback to keep improving.

---

## 📦 What You Get

- Modular ADK tools for chunking, embedding, query rewriting, context assembly, reasoning, and feedback capture.
- A Streamlit console that visualises the entire pipeline, including vector-store health and memory snapshots.
- Utility scripts and optional ingestion helpers so you can index your own document sets.
- A feedback loop (`memory_log.json`) that records user signals for later reuse.

---

## 🏗️ High-Level Architecture

```
User Query → QueryRewriterTool → VectorRetrieverTool → ContextComposerTool
          → LLM Reasoning (Gemini) → MemoryManagerTool → Feedback Log
```

Each stage is an **ADK Tool** or **Agent**:

| Stage | Module | Tool/Agent | Description |
|-------|--------|------------|-------------|
| 1 | Module 1 | `ContextPlannerAgent` | Plans the context flow (foundational design patterns). |
| 2 | Module 2 | `chunker_tool` | Splits documents into overlapping, token-aware chunks. |
| 3 | Module 3 | `embedder_tool` | Generates Gemini embeddings and persists to Chroma. |
| 4 | Module 4 | `query_rewriter_tool` | Rewrites/expands natural-language queries. |
| 5 | Module 5 | `context_composer_tool` | Creates a constrained context window for the reasoner. |
| 6 | Module 6 | `ContextOrchestratorAgent` | Orchestrates the full RAG pipeline. |
| 7 | Module 7 | `memory_manager_tool` | Stores user feedback in `memory_log.json`. |

---

## ⚙️ Prerequisites

- macOS / Linux (ARM64 or x86_64; instructions below assume ARM64 macOS).
- Python 3.10 or 3.11.
- Google ADK (see [ADK Quickstart](https://cloud.google.com/agent-builder/docs)).
- Gemini API Key (`GOOGLE_AI_API_KEY`) or Vertex AI credentials.
- (Optional) OpenAI key if you want to experiment with OpenAI models.

---

## 🚀 Getting Started

### 1. Clone & Install

```bash
# Clone the repository
cd /Users/chetanchauhan/Agentic
git clone https://github.com/your-org/agentic-rag-context-engineering.git AgenticContext
cd AgenticContext

# Install Python dependencies (ARM-compatible wheels)
pip install --upgrade pip setuptools wheel
pip install -r agentic-rag/requirements.txt
```

The requirements include:

- `google-adk`
- `chromadb`
- `google-genai` (Gemini client)
- `python-pptx`, `lxml` (for slide ingestion)
- `streamlit`

> **Note:** If you see architecture mismatches (x86_64 vs arm64), reinstall the offending packages with `pip install --force-reinstall {package-name} --platform=macosx-11.0-arm64`.

### 2. Environment Variables (.env)

The app reads credentials from `agentic-rag/.env`. Create it if it does not exist:

```ini
# agentic-rag/.env
GOOGLE_AI_API_KEY=your_gemini_key
# Optional Vertex AI credentials
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/vertex/key.json

# Optional: OpenAI if you experiment with other LLMs
OPENAI_API_KEY=your_openai_key
```

Ensure `.env` files stay out of git—the repository now includes a root `.gitignore` covering them.

### 3. Prepare Documents (Optional)

The Streamlit console can ingest any text/PDF/Markdown/CSV/notebook folder. For a large sample, download the [OpenAI Cookbook](https://github.com/openai/openai-cookbook) and point the UI to `examples/`. To test quickly, keep the default sample documents under `agentic-rag/data/sample_docs/`.

---

## 🖥️ Running the Streamlit Console

```bash
cd agentic-rag
streamlit run app.py
```

The UI contains three tabs:

1. **Pipeline Console** – run the RAG workflow on any query, inspect the rewritten query, retrieved chunks, assembled context, and final answer, then log feedback.
2. **Vector Store** – observe vector counts, collection totals, last update, and rebuild embeddings from the sidebar.
3. **Feedback Memory** – review logged interactions (`memory_log.json`) with aggregated sentiment counts.

### Sidebar Controls

- **Top-K Retrieval / Context Token Budget** sliders tune the pipeline before each run.
- **Source Folder** + **Rebuild Vector Store** trigger ingestion. The console supports:
  - `.txt`, `.md`, `.markdown`, `.json`, `.jsonl`, `.csv`, `.py`, `.yaml`, `.yml`, `.ts`, `.tsx`, `.js`, `.jsx`, `.html`, `.css`
  - `.ipynb` (Markdown + code cells concatenated)
  - `.pdf` (requires `pypdf`)
  - `.pptx` (requires `python-pptx`)
  - Binary assets such as `.png`, `.jpg`, `.mp4` are skipped automatically.

While rebuilding, the spinner stays visible until embedding completes. For very large folders, consider pre-ingesting via a script (see below).

---

## 🛠️ Command-Line Utilities

### Manual Mini-Ingest (sample snippets)

```python
from pathlib import Path
from tools.module2_chunker_tool import adaptive_chunk
from tools.module3_embedder_tool import embed_and_store, reset_vector_store

SOURCE_DIR = Path('/path/to/folder')
texts = []
metas = []
for file_path in SOURCE_DIR.rglob('*.md'):
    text = file_path.read_text('utf-8')
    for idx, chunk in enumerate(adaptive_chunk(text)):
        texts.append(chunk)
        metas.append({'source_path': str(file_path), 'chunk_index': idx})

reset_vector_store(drop_storage=True)
embed_and_store(texts, metadata_list=metas)
```

### Running the Orchestrator Agent Directly

```bash
python agents/module6_agentic_rag.py
```
This performs a demo query (`"What is the policy for remote work?"`) and prints the retrieved chunks, context, and answer.

---

## 📁 Repository Layout

```
agentic-rag/
├── app.py                     # Streamlit dashboard
├── agents/
│   ├── module1_context_planner_agent.py
│   └── module6_agentic_rag.py
├── tools/
│   ├── module2_chunker_tool.py
│   ├── module3_embedder_tool.py
│   ├── module4_query_rewriter_tool.py
│   ├── module5_context_composer_tool.py
│   └── module7_memory_manager_tool.py
├── data/
│   └── sample_docs/
├── memory_log.json            # Feedback log (JSON)
├── chroma_db/                 # Persistent Chroma vector store
└── requirements.txt
```

---

## 🧠 Feedback & Memory Loop

- Each console run optionally writes an entry to `memory_log.json` via `store_feedback`.
- Feedback is currently an **audit trail**; the live pipeline does not yet re-inject these memories.
- To leverage them, you can load the positive entries in `handle_query` before invoking the reasoner.

---

## 🧪 Troubleshooting

| Issue | Fix |
|-------|-----|
| **Streamlit shows architecture mismatch (`x86_64` vs `arm64`)** | Reinstall the package with an ARM wheel, e.g. `pip install --force-reinstall lxml==5.4.0 --platform=macosx_11_0_arm64` |
| **`pyarrow` ImportError** | The UI now avoids `st.dataframe`; if you still need `pyarrow`, install the ARM version explicitly. |
| **Ingestion Spinner Never Stops** | Large folders can take minutes. Check the terminal logs for Gemini rate limits or use a smaller subset via `_ingest_file_limit`. |
| **Empty results (`I cannot find relevant information`)** | Verify Chroma contains vectors (Vector Store tab). Rebuild embeddings if the count is zero. |
| **`python-pptx` missing** | Install with `pip install python-pptx` and ensure `lxml` uses the correct architecture. |

---

## 🧭 Roadmap / Ideas

- Reuse positive feedback as supplemental context during retrieval.
- Add automated evaluator (e.g., OpenAI Evals) to grade responses.
- Integrate telemetry dashboards (latency, recall/precision).
- Package as an ADK endpoint or Docker image.
- Extend to multi-modal (image/PDF embeddings) or cross-lingual retrieval.

---

## 📚 References & Credits

- [Google Agent Development Kit](https://cloud.google.com/agent-builder/docs)
- [ChromaDB](https://docs.trychroma.com/)
- [Weaviate Context Engineering Guide](https://weaviate.io/blog/context-engineering)
- [Streamlit](https://streamlit.io/)
- [OpenAI Cookbook](https://github.com/openai/openai-cookbook)

> Author: **Chetan Chauhan** · Version 1.0.0 · License: Apache-2.0

Happy building! Feel free to file issues or suggestions as you explore the Agentic RAG framework. ✨
