# 🧠 Agentic RAG Framework — Context Engineering with Google ADK

---

## 🚀 Overview

This project implements a **Context-Engineered Agentic RAG System** using **Google Agent Development Kit (ADK)** and open-source vector databases (Chroma / FAISS).

It follows the **Weaviate “Context Engineering”** principles — optimizing the *flow of context* from raw data to LLM reasoning — while demonstrating production-level design patterns.

---

## 🏗️ Architecture Summary

Raw Data → Chunking → Embedding → Retrieval → Context Assembly → Reasoning → Feedback
```pgsql

Each stage is implemented as an **ADK Tool** or **Agent**, forming a modular and traceable system.

### 🔹 Agentic Flow (ReAct-style)

User Query
↓
QueryRewriterTool
↓
VectorRetrieverTool (Chroma / FAISS)
↓
ContextComposerTool
↓
LLM Reasoning (Gemini / GPT-4 / Claude)
↓
MemoryManagerTool (feedback)
```
```ymal

---

## 🧩 Modules Overview

| **Module** | **Concept** | **Agent/Tool** | **Purpose** |
|-------------|--------------|----------------|--------------|
| 1 | Context Engineering Foundations | `ContextPlannerAgent` | Defines the context flow pipeline |
| 2 | Chunking & Context Windows | `ChunkerTool` | Splits large documents into meaningful text blocks |
| 3 | Embeddings & Vector Stores | `EmbedderTool` | Embeds and stores chunks in a vector DB |
| 4 | Query Understanding | `QueryRewriterTool` | Expands and clarifies user queries |
| 5 | Context Assembly | `ContextComposerTool` | Builds optimal context windows for LLM |
| 6 | Agentic RAG Architecture | `ContextOrchestratorAgent` | Orchestrates all tools and reasoning |
| 7 | Feedback & Memory Loops | `MemoryManagerTool` | Stores user feedback for retraining and self-healing |

---

## ⚙️ Installation

### 1️⃣ Prerequisites

- Python 3.9+
- Google ADK installed (see [ADK Quickstart](https://cloud.google.com/agent-builder/docs))
- Vertex AI or OpenAI API access
- Git & pip

### 2️⃣ Clone and Setup

```bash
git clone https://github.com/your-org/agentic-rag-context-engineering.git
cd agentic-rag-context-engineering
pip install -r requirements.txt

```

3️⃣ Configure API Keys
Create a .env file:
```ini
OPENAI_API_KEY=your_key_here
GOOGLE_APPLICATION_CREDENTIALS=/path/to/vertex-ai/credentials.json

```
📦 Project Structure
```bash
agentic-rag/
│
├── README.md
├── requirements.txt
├── chroma_db/                   # Local vector store (Chroma)
│
├── tools/
│   ├── module2_chunker_tool.py
│   ├── module3_embedder_tool.py
│   ├── module4_query_rewriter_tool.py
│   ├── module5_context_composer_tool.py
│   ├── module7_memory_manager_tool.py
│
├── agents/
│   ├── module1_context_planner_agent.py
│   ├── module6_agentic_rag.py
│
└── data/
    ├── sample_docs/
    │   └── company_policy.pdf

```
🧩 Modules (Quick Reference)
🧠 Module 1 — Context Engineering Foundations
Defines your ContextPlannerAgent that orchestrates how context flows through the system.
from google_adk import Agent, Tool, AgentConfig

def log_stage(stage, details): print(f"[PIPELINE] {stage}: {details}")

log_tool = Tool("pipeline_logger", "Logs pipeline stages", func=log_stage)

planner_cfg = AgentConfig(name="ContextPlannerAgent", tools=[log_tool])
agent = Agent(config=planner_cfg)
agent.call_tool("pipeline_logger", "Chunking → Embedding → Retrieval → Assembly → Reasoning")

📏 Module 2 — Chunking & Context Windows

Split large documents into coherent, overlapping text chunks.
from google_adk import Tool
import tiktoken

def adaptive_chunk(text, max_tokens=400, overlap=50):
    enc = tiktoken.get_encoding("cl100k_base")
    tokens, chunks, start = enc.encode(text), [], 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunks.append(enc.decode(tokens[start:end]))
        start += (max_tokens - overlap)
    return chunks

chunker_tool = Tool("chunker_tool", "Splits text into semantic chunks", func=adaptive_chunk)

🔢 Module 3 — Embeddings & Vector Stores

Embed chunks and store them in Chroma DB.
from google_adk import Tool
from sentence_transformers import SentenceTransformer
import chromadb

model = SentenceTransformer("all-MiniLM-L6-v2")
client = chromadb.Client()
collection = client.get_or_create_collection("docs")

def embed_and_store(chunks, metadata=None):
    vectors = model.encode(chunks)
    ids = [f"chunk_{i}" for i in range(len(chunks))]
    collection.upsert(documents=chunks, embeddings=vectors.tolist(), ids=ids, metadatas=metadata or [{}])
    return f"Stored {len(chunks)} chunks."
    
embedder_tool = Tool("embedder_tool", "Embeds and stores chunks in vector DB", func=embed_and_store)

🧠 Module 4 — Query Rewriting

Expand or rephrase user queries to improve retrieval.
from google_adk import Tool
import openai, os
openai.api_key = os.getenv("OPENAI_API_KEY")

def rewrite_query(q):
    prompt = f"Rewrite this query for better semantic retrieval:\n\n{q}"
    resp = openai.ChatCompletion.create(model="gpt-4o-mini", messages=[{"role":"user","content":prompt}])
    return resp.choices[0].message.content.strip()

query_rewriter_tool = Tool("query_rewriter_tool", "Expands user queries via LLM", func=rewrite_query)

🧩 Module 5 — Context Composer

Combine top retrieved chunks into one context window.
from google_adk import Tool
import tiktoken

def compose_context(chunks, max_tokens=6000):
    enc, text, total = tiktoken.get_encoding("cl100k_base"), "", 0
    for c in chunks:
        t = enc.encode(c)
        if total + len(t) > max_tokens: break
        text += c + "\n---\n"
        total += len(t)
    return text.strip()

context_composer_tool = Tool("context_composer_tool", "Combines top chunks into a single context", func=compose_context)

🤖 Module 6 — Agentic RAG Orchestrator

Main agent that connects all tools and produces final answers.
from google_adk import Agent, AgentConfig

agent_cfg = AgentConfig(name="ContextOrchestratorAgent", description="Main RAG pipeline orchestrator")
agent = Agent(config=agent_cfg)

def handle_query(q):
    rw = agent.call_tool("query_rewriter_tool", q)
    docs = agent.call_tool("vector_retriever_tool", rw)
    context = agent.call_tool("context_composer_tool", docs)
    answer = agent.call_model(context + f"\nUser: {q}")
    agent.call_tool("memory_manager_tool", q, docs, feedback="pending")
    return answer

💾 Module 7 — Feedback & Memory

Log successful retrievals for retraining and evaluation.
from google_adk import Tool
import json, os

LOG_PATH = "memory_log.json"

def store_feedback(query, retrieved, feedback="positive"):
    log = {"query": query, "chunks": retrieved, "feedback": feedback}
    existing = json.load(open(LOG_PATH)) if os.path.exists(LOG_PATH) else []
    existing.append(log)
    json.dump(existing, open(LOG_PATH, "w"), indent=2)
    return f"Feedback stored for: {query}"

memory_manager_tool = Tool("memory_manager_tool", "Logs feedback for self-improvement", func=store_feedback)
🧠 Full Context Flow Diagram
┌────────────────────────────────────────────┐
│            ContextOrchestratorAgent        │
│────────────────────────────────────────────│
│ QueryRewriterTool → VectorRetrieverTool    │
│ → ContextComposerTool → MemoryManagerTool  │
└────────────────────────────────────────────┘
               ↓
          LLM Reasoning
               ↓
        Feedback & Learning
🧩 Running the System

python agents/module6_agentic_rag.py
Then type:
User> What is the policy for remote work?
Agent pipeline:
Query rewritten
Chunks retrieved from Chroma
Context composed
LLM generates answer
Feedback logged

📊 Observability Metrics

Metric	Goal
Retrieval Precision	> 0.7
Context Load	≤ 80% of model limit
Latency per Stage	< 500 ms typical
Memory Hit Rate	Improves over time
Feedback Accuracy	Increasing trend
🧩 Example Applications
📚 Internal Knowledgebase Agents
🧾 Legal Policy Bots
🏢 HR Q&A Assistants
🧪 Research Summarization Systems
🔐 Security & Scaling
Store vector DB locally (Chroma/FAISS) or in managed service.
Mask sensitive data before embedding.
Scale via ADK’s cloud-native deployment.

📘 References

Google Agent Development Kit (ADK)
Sentence Transformers
ChromaDB Docs

✅ Summary

You’ve Learned	You Can Now
Context Engineering Foundations	Design context-aware pipelines
Chunking & Context Windows	Optimize document granularity
Embeddings & Vector DB	Store semantic context
Query Understanding	Clarify user intent
Context Assembly	Build effective prompt windows
Agentic Orchestration	Coordinate multi-agent RAG loops
Feedback & Memory	Enable self-learning systems

🧭 Next Steps

Connect Vertex AI or Gemini through ADK model connectors.
Add telemetry (logging, tracing, latency dashboards).
Deploy as REST API or agent endpoint.
Experiment with multi-modal RAG (vision + text).
Author: Chetan Chauhan
Version: 1.0.0
License: Apache 2.0
