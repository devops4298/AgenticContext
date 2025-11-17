# RAG Production Pipeline - Complete Training Manual

## 📖 Table of Contents

1. [Introduction](#introduction)
2. [Architecture Overview](#architecture-overview)
3. [Step-by-Step Execution Flow](#step-by-step-execution-flow)
4. [Module-by-Module Breakdown](#module-by-module-breakdown)
5. [Complete End-to-End Example](#complete-end-to-end-example)
6. [Installation & Setup](#installation--setup)
7. [Troubleshooting](#troubleshooting)

---

## Introduction

This training manual explains how the **Agentic RAG System with Playwright Script Generation** works, step-by-step, from when you start the Streamlit app until you receive your query response. You'll learn how each Python file interacts with others and how data flows through the system.

### System Components

The system is modularly structured across **7 Python files**:

1. **`rag_streamlit_app.py`** - Frontend user interface (Streamlit)
2. **`rag_config.py`** - Configuration and constants
3. **`rag_utils.py`** - Utility functions (logging, retry decorators)
4. **`rag_core.py`** - Core RAG components (loading, chunking, embedding, indexing)
5. **`rag_agents.py`** - Agentic RAG components (feedback, query rewriting, multi-agent)
6. **`orchestrator_agent.py`** - Root orchestrator agent (coordinates everything)
7. **`rag_prod.py`** - Main RAG pipeline orchestrator

---

## Architecture Overview

### High-Level Data Flow

```
User (Browser)
    ↓
[rag_streamlit_app.py] - Streamlit Frontend
    ↓
[orchestrator_agent.py] - Root Orchestrator Agent (root_agent)
    ↓
[rag_prod.py] - RAG Pipeline
    ↓
[rag_agents.py] - Specialized Agents
    ↓
[rag_core.py] - Core Components
    ↓
[rag_config.py] + [rag_utils.py] - Support Modules
    ↓
Response back to User
```

### Module Dependencies

```
rag_streamlit_app.py
  ├── imports: rag_prod.py (RAGPipeline, AppConfig)
  ├── imports: orchestrator_agent.py (OrchestratorAgent)
  └── uses: rag_config.py (via AppConfig)

orchestrator_agent.py
  ├── imports: rag_config.py (AppConfig)
  ├── imports: rag_utils.py (retry, logger)
  └── uses: rag_prod.py (RAGPipeline instance)

rag_prod.py
  ├── imports: rag_config.py (AppConfig)
  ├── imports: rag_utils.py (retry, logger)
  ├── imports: rag_core.py (all core components)
  └── imports: rag_agents.py (all agentic components)

rag_core.py
  ├── imports: rag_config.py (AppConfig)
  └── imports: rag_utils.py (retry, logger)

rag_agents.py
  ├── imports: rag_config.py (AppConfig)
  ├── imports: rag_utils.py (retry, logger)
  └── imports: rag_core.py (VertexEmbedder, FaissIndexer, Retriever)
```

---

## Step-by-Step Execution Flow

### Scenario: User wants to query indexed documents and generate a Playwright script

Let's trace through what happens when you run the application and make a query.

---

## STEP 1: Starting the Application

### Action: `streamlit run rag_streamlit_app.py`

**File**: `rag_streamlit_app.py`  
**Lines**: 1-36

#### What Happens:

```python
# Lines 13-20: Fix OpenMP conflicts before imports
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

# Lines 22-28: Import modules and load environment
from rag_prod import RAGPipeline, AppConfig
from orchestrator_agent import OrchestratorAgent
from dotenv import load_dotenv

load_dotenv()  # Loads .env file
```

**Example**:
```python
# If .env contains:
# GOOGLE_AI_API_KEY=your-api-key-here
# EMBEDDING_MODEL=text-embedding-004
# TEXT_MODEL=gemini-1.5-pro

# These values are now available via os.getenv()
```

#### Import Chain:

1. `rag_streamlit_app.py` imports `rag_prod.py`
2. `rag_prod.py` imports `rag_core.py`, `rag_agents.py`, `rag_config.py`, `rag_utils.py`
3. `rag_core.py` imports `rag_config.py`, `rag_utils.py`
4. `rag_agents.py` imports `rag_config.py`, `rag_utils.py`, `rag_core.py`

**Result**: All modules are loaded into memory, but no RAG pipeline is created yet.

---

## STEP 2: Initializing Session State

**File**: `rag_streamlit_app.py`  
**Lines**: 38-52

#### What Happens:

```python
# Lines 38-52: Initialize Streamlit session state
if 'pipeline' not in st.session_state:
    st.session_state.pipeline = None  # Will hold RAGPipeline instance
if 'orchestrator' not in st.session_state:
    st.session_state.orchestrator = None  # Will hold OrchestratorAgent instance
if 'folder_path' not in st.session_state:
    st.session_state.folder_path = None
if 'index_loaded' not in st.session_state:
    st.session_state.index_loaded = False
if 'query_history' not in st.session_state:
    st.session_state.query_history = []
if 'generated_scripts' not in st.session_state:
    st.session_state.generated_scripts = []
```

**Explanation**: Streamlit uses session state to persist data across re-runs. This ensures the pipeline and orchestrator aren't recreated on every interaction.

**Example**:
```python
# User loads page → session_state initialized
# User indexes folder → session_state.pipeline = RAGPipeline instance
# User queries → session_state.pipeline still exists (not recreated)
```

---

## STEP 3: User Selects Input Mode and Indexes Folder

**File**: `rag_streamlit_app.py`  
**Lines**: 194-221

### User Action:
1. User selects "📁 Local Folder" radio button
2. User enters folder path: `/Users/john/my_project`
3. User clicks "📂 Index Folder" button

### What Happens:

#### 3a. Button Click Handler (Lines 210-221)

```python
if load_btn or reindex_btn:
    st.session_state.pipeline = None  # Reset pipeline
    st.session_state.index_loaded = False
    if folder_path:
        st.session_state.folder_path = folder_path
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            initialize_pipeline_from_folder(folder_path, force_reindex=reindex_btn)
```

**Flow**: Button click → calls `initialize_pipeline_from_folder()`

---

#### 3b. Initialize Pipeline Function (Lines 55-100)

**File**: `rag_streamlit_app.py`  
**Function**: `initialize_pipeline_from_folder()`

```python
def initialize_pipeline_from_folder(folder_path: str, force_reindex: bool = False):
    # Step 3b.1: Create AppConfig
    cfg = AppConfig()  # From rag_config.py
    
    # Step 3b.2: Create RAGPipeline instance
    pipeline = RAGPipeline(cfg)  # From rag_prod.py
```

**Example**:
```python
# cfg contains:
# cfg.chunk_size_words = 200
# cfg.chunk_overlap_words = 30
# cfg.google_ai_api_key = "your-api-key-here"
# cfg.cache_dir = "./rag_cache"
```

**What `AppConfig()` does**:
- **File**: `rag_config.py`
- **Lines**: 48-89
- Reads environment variables from `.env`
- Sets default paths (cache_dir, faiss_index_path, etc.)
- Sets default parameters (chunk_size_words, top_k, etc.)

**What `RAGPipeline(cfg)` does**:
- **File**: `rag_prod.py`
- **Lines**: 70-105

```python
class RAGPipeline:
    def __init__(self, config: AppConfig):
        self.cfg = config
        self.cfg.ensure_dirs()  # Creates ./rag_cache directory
        
        # Create core components
        self.repo_loader = RepoLoader(config)      # From rag_core.py
        self.chunker = Chunker(config)             # From rag_core.py
        self.embedder = VertexEmbedder(config)     # From rag_core.py
        self.indexer = FaissIndexer(config)        # From rag_core.py
        self.summarizer = VertexSummarizer(config) # From rag_core.py
        self.projection_model = ProjectionMLP(...) # From rag_core.py
        
        # Create agentic components (if enabled)
        self.feedback_loop = FeedbackLoop(config)       # From rag_agents.py
        self.query_rewriter = QueryRewriterAgent(config) # From rag_agents.py
        
        # Initialize multi-agent system
        self._initialize_multi_agents()
```

**What each component does**:

1. **`RepoLoader(config)`** - **File**: `rag_core.py`, **Lines**: 65-142
   - Will collect text files from folder
   - Example: Given `/Users/john/my_project`, it will recursively find all `.py`, `.md`, `.txt` files

2. **`Chunker(config)`** - **File**: `rag_core.py`, **Lines**: 148-175
   - Will split files into overlapping chunks
   - Example: 1000-word file → chunks of 200 words with 30-word overlap

3. **`VertexEmbedder(config)`** - **File**: `rag_core.py`, **Lines**: 181-255
   - Will embed chunks using Gemini API
   - Example: Chunk text → 768-dimensional vector

4. **`FaissIndexer(config)`** - **File**: `rag_core.py`, **Lines**: 261-303
   - Will build FAISS index for similarity search
   - Example: 1000 chunks → FAISS index with 1000 vectors

5. **`VertexSummarizer(config)`** - **File**: `rag_core.py`, **Lines**: 327-361
   - Will create short summaries of chunks
   - Example: 200-word chunk → "Implements retry logic with exponential backoff"

---

#### 3c. Cache Check and Indexing (Lines 68-85)

```python
# Try to load from cache first
cache_loaded = pipeline.load_from_cache(expected_folder_path=folder_path)

if cache_loaded and pipeline.metadata and pipeline.indexer.index:
    st.success(f"✅ Loaded cache: {len(pipeline.metadata)} chunks")
else:
    # Cache doesn't exist or doesn't match - re-index
    pipeline.ingest_folder(folder_path, reindex=True)
```

**What `load_from_cache()` does**:
- **File**: `rag_prod.py`
- **Lines**: 178-233

```python
def load_from_cache(self, expected_folder_path: Optional[str] = None) -> bool:
    # Step 1: Validate cache matches expected folder
    if expected_folder_path:
        # Read index_metadata.json
        with open(self.cfg.index_metadata_path, "r") as f:
            index_metadata = json.load(f)
        
        cached_folder = index_metadata.get("indexed_folder_path", "")
        if os.path.abspath(cached_folder) != os.path.abspath(expected_folder_path):
            return False  # Cache doesn't match
    
    # Step 2: Load cache files
    with open(self.cfg.metadata_path, "rb") as f:
        self.metadata = pickle.load(f)  # Load chunk metadata
    
    self.raw_embeddings = np.load(self.cfg.raw_emb_path)  # Load embeddings
    
    self.indexer.load(self.cfg.faiss_index_path)  # Load FAISS index
    
    return True
```

**Example**:
```python
# If cache exists for /Users/john/my_project:
# - Loads metadata.pkl (list of chunks)
# - Loads raw_embeddings.npy (numpy array)
# - Loads faiss.index (FAISS index)

# If cache doesn't exist or folder changed:
# - Returns False → triggers ingest_folder()
```

---

#### 3d. Ingest Folder (If Cache Miss)

**File**: `rag_prod.py`  
**Lines**: 129-174  
**Function**: `ingest_folder()`

```python
def ingest_folder(self, folder_path: str, reindex: bool = False):
    # Step 3d.1: Validate folder
    if not os.path.exists(folder_path):
        raise ValueError(f"Folder path does not exist: {folder_path}")
    
    # Step 3d.2: Collect text files
    files = self.repo_loader.collect_text_files(folder_path)
    # Returns: {"path/to/file1.py": "file contents...", "path/to/file2.md": "..."}
```

**What `collect_text_files()` does**:
- **File**: `rag_core.py`
- **Lines**: 83-142
- Recursively walks through folder tree
- Skips binary files (images, executables, etc.)
- Skips common directories (`.git`, `node_modules`, `venv`, etc.)

**Example**:
```python
# Folder structure:
# /Users/john/my_project/
#   ├── main.py
#   ├── utils.py
#   ├── README.md
#   └── images/
#       └── logo.png  # Skipped (binary)

# Returns:
# {
#   "/Users/john/my_project/main.py": "def main(): ...",
#   "/Users/john/my_project/utils.py": "def helper(): ...",
#   "/Users/john/my_project/README.md": "# My Project\n..."
# }
```

```python
    # Step 3d.3: Chunk files
    chunks_meta = self.chunker.chunk_files(files)
    # Returns: [{"path": "...", "chunk_idx": 0, "text": "..."}, ...]
```

**What `chunk_files()` does**:
- **File**: `rag_core.py`
- **Lines**: 166-175

```python
def chunk_files(self, files: Dict[str, str]) -> List[Dict[str, Any]]:
    out = []
    for path, txt in files.items():
        chunks = self.chunk_text(txt)  # Split into overlapping chunks
        for idx, ch in enumerate(chunks):
            out.append({"path": path, "chunk_idx": idx, "text": ch})
    return out
```

**Example**:
```python
# Input file: main.py (600 words)
# Chunk size: 200 words, Overlap: 30 words

# Output chunks:
# [
#   {"path": "main.py", "chunk_idx": 0, "text": "words 1-200"},
#   {"path": "main.py", "chunk_idx": 1, "text": "words 171-370"},  # 30-word overlap
#   {"path": "main.py", "chunk_idx": 2, "text": "words 341-540"},
#   {"path": "main.py", "chunk_idx": 3, "text": "words 511-600"}
# ]
```

```python
    # Step 3d.4: Embed chunks
    texts = [m["text"] for m in chunks_meta]
    vecs = self.embedder.embed_texts(texts, batch_size=64)
    # Returns: [[0.1, 0.2, ...], [0.3, 0.4, ...], ...]  # 768-dimensional vectors
```

**What `embed_texts()` does**:
- **File**: `rag_core.py`
- **Lines**: 222-255

```python
def embed_texts(self, texts: List[str], batch_size: int = 64, use_cache: bool = True):
    out_vectors = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        vs = self.embed_batch(batch)  # Call Gemini API
        out_vectors.extend(vs)
    
    # Normalize vectors
    arr = np.array(out_vectors, dtype="float32")
    norms = np.linalg.norm(arr, axis=1, keepdims=True) + 1e-12
    arr = arr / norms  # Unit vectors for cosine similarity
    
    return arr.tolist()
```

**Example**:
```python
# Input: ["def main(): ...", "import requests ..."]
# Process:
# 1. Batch 1: Embed first 64 chunks → API call to Gemini
# 2. Batch 2: Embed next 64 chunks → API call to Gemini
# 3. Normalize all vectors → Unit length for cosine similarity
# Output: [[0.1, 0.2, ..., 0.9], [0.3, 0.1, ..., 0.5], ...]
```

```python
    # Step 3d.5: Build FAISS index
    import numpy as np
    arr = np.array(vecs, dtype="float32")
    idx = self.indexer.build(arr, metric="ip")  # Inner product (cosine similarity)
    self.indexer.save(self.cfg.faiss_index_path)
```

**What `build()` does**:
- **File**: `rag_core.py`
- **Lines**: 267-280

```python
def build(self, vectors: "np.ndarray", metric: str = "ip"):
    vectors = np.array(vectors).astype("float32")
    d = vectors.shape[1]  # 768 dimensions
    self.index = faiss.IndexFlatIP(d)  # Inner product index
    self.index.add(vectors)  # Add all vectors
    return self.index
```

**Example**:
```python
# Input: numpy array of shape (1000, 768)
# - 1000 chunks
# - Each chunk has 768-dimensional embedding

# Process:
# 1. Create FAISS IndexFlatIP index (768 dimensions)
# 2. Add all 1000 vectors to index
# 3. Index is ready for similarity search

# Output: self.index.ntotal = 1000
```

```python
    # Step 3d.6: Save metadata
    with open(self.cfg.metadata_path, "wb") as f:
        pickle.dump(self.metadata, f)
    
    # Save index metadata
    index_metadata = {
        "indexed_source": "local_folder",
        "indexed_folder_path": os.path.abspath(folder_path),
        "indexed_at": datetime.datetime.now().isoformat(),
        "num_files": len(files),
        "num_chunks": len(self.metadata)
    }
    with open(self.cfg.index_metadata_path, "w") as f:
        json.dump(index_metadata, f, indent=2)
```

**What gets saved**:
- `./rag_cache/metadata.pkl` - List of chunk dictionaries
- `./rag_cache/raw_embeddings.npy` - Numpy array of embeddings
- `./rag_cache/faiss.index` - FAISS index file
- `./rag_cache/index_metadata.json` - Metadata about what was indexed

**Example `index_metadata.json`**:
```json
{
  "indexed_source": "local_folder",
  "indexed_folder_path": "/Users/john/my_project",
  "indexed_at": "2024-01-15T10:30:00.123456",
  "num_files": 45,
  "num_chunks": 127
}
```

---

#### 3e. Initialize Orchestrator Agent

**File**: `rag_streamlit_app.py`  
**Lines**: 90-94

```python
# Initialize orchestrator agent (root_agent)
if not st.session_state.orchestrator:
    with st.spinner("Initializing orchestrator agent..."):
        st.session_state.orchestrator = OrchestratorAgent(cfg)
        st.success("✅ Orchestrator agent ready")
```

**What `OrchestratorAgent(cfg)` does**:
- **File**: `orchestrator_agent.py`
- **Lines**: 31-65

```python
class OrchestratorAgent:
    def __init__(self, config: AppConfig):
        self.cfg = config
        self.client = genai.Client(api_key=self.cfg.google_ai_api_key)
        self.model = self.cfg.text_model  # "gemini-1.5-pro"
        
        # System instruction for orchestrator
        self.system_instruction = """You are a root orchestrator agent...
        Your responsibilities:
        1. Understand user queries and context
        2. Coordinate specialized agents
        3. Generate Playwright scripts
        ..."""
        
        # Function descriptions (prompt-based function calling)
        self.function_descriptions = {
            "query_rag_system": "...",
            "generate_playwright_script": "...",
            "analyze_context_understanding": "..."
        }
```

**Result**: Orchestrator agent is ready to coordinate queries and script generation.

---

## STEP 4: User Enters Query and Submits

**File**: `rag_streamlit_app.py`  
**Lines**: 309-332

### User Action:
1. User enters query: "How do I implement authentication? Generate a Playwright script to test it."
2. User checks "Generate Playwright Script" checkbox
3. User clicks "🚀 Query" button

### What Happens:

#### 4a. Button Click Handler (Lines 329-332)

```python
if submit_btn and query:
    if not st.session_state.pipeline:
        st.warning("⚠️ Pipeline not initialized...")
        st.stop()
    
    if st.session_state.pipeline and st.session_state.orchestrator:
        result = query_with_orchestrator(query, generate_script=generate_script)
```

**Flow**: Button click → calls `query_with_orchestrator()`

---

#### 4b. Query with Orchestrator Function

**File**: `rag_streamlit_app.py`  
**Lines**: 149-180  
**Function**: `query_with_orchestrator()`

```python
def query_with_orchestrator(user_query: str, generate_script: bool = False):
    # Step 4b.1: Check if RAG context needed
    rag_context = None
    if generate_script or "automate" in user_query.lower() or "playwright" in user_query.lower():
        # Query RAG for relevant context
        with st.spinner("Retrieving context from indexed documents..."):
            rag_result = st.session_state.pipeline.query(user_query, top_k=40)
            rag_context = rag_result
```

**What `pipeline.query()` does**:
- **File**: `rag_prod.py`
- **Lines**: 277-313

```python
def query(self, query_text: str, top_k: Optional[int] = None, use_summaries: bool = True):
    top_k = top_k or self.cfg.top_k  # Default: 40
    
    # Step 4b.1a: Retrieve chunks
    retr = Retriever(self.cfg, self.indexer, self.metadata, self.projected_vectors)
    hits = retr.retrieve(query_text, embedder=self.embedder, top_k=top_k)
```

**What `retrieve()` does**:
- **File**: `rag_core.py`
- **Lines**: 375-386

```python
def retrieve(self, query: str, embedder: VertexEmbedder, top_k: Optional[int] = None):
    top_k = top_k or self.cfg.top_k
    
    # Step 1: Embed query
    qv = embedder.embed_texts([query])[0]  # [0.1, 0.2, ..., 0.9]  # 768-dim vector
    
    # Step 2: Search FAISS index (LOCAL, no API call)
    idxs, scores = self.indexer.search(qv, top_k=top_k)
    # Returns: ([123, 456, 789], [0.95, 0.92, 0.89])
    
    # Step 3: Get chunk metadata
    hits = []
    for idx, score in zip(idxs, scores):
        meta = self.metadata[idx].copy()
        meta["_index_id"] = idx
        meta["_score"] = float(score)
        hits.append(meta)
    
    return hits
```

**Example**:
```python
# Query: "How do I implement authentication?"
# Step 1: Embed query → [0.1, 0.2, ..., 0.9] (API call: 1)
# Step 2: Search FAISS → top 40 chunks with highest similarity (LOCAL)
# Step 3: Enrich with metadata

# Returns:
# [
#   {
#     "path": "/Users/john/my_project/auth.py",
#     "chunk_idx": 0,
#     "text": "def authenticate(username, password): ...",
#     "_index_id": 45,
#     "_score": 0.95
#   },
#   {
#     "path": "/Users/john/my_project/auth.py",
#     "chunk_idx": 1,
#     "text": "class AuthMiddleware: ...",
#     "_index_id": 46,
#     "_score": 0.92
#   },
#   ...
# ]
```

```python
    # Step 4b.1b: Ensure summaries exist
    hit_indices = [h["_index_id"] for h in hits]
    if use_summaries:
        self.ensure_summaries(indices=hit_indices)
```

**What `ensure_summaries()` does**:
- **File**: `rag_prod.py`
- **Lines**: 235-258

```python
def ensure_summaries(self, indices: Optional[List[int]] = None, force: bool = False):
    missing = [i for i in indices if i not in self.chunk_summaries]
    
    for i in missing:
        txt = self.metadata[i]["text"]
        s = self.summarizer.summarize(txt)  # API call per chunk
        self.chunk_summaries[i] = s.strip()
    
    # Save to disk
    with open(self.cfg.summaries_path, "wb") as f:
        pickle.dump(self.chunk_summaries, f)
```

**Example**:
```python
# Chunk: "def authenticate(username, password):\n    if user_exists(username):\n        return verify_password(password)"
# Summary: "Implements user authentication by checking username existence and verifying password."

# Stored in: self.chunk_summaries[45] = "Implements user authentication..."
```

```python
    # Step 4b.1c: Heuristic expansion
    compressed = []
    for h in hits:
        idx = h["_index_id"]
        summary = self.chunk_summaries.get(idx, "")
        meta = {"_index_id": idx, "score": h.get("_score", 0.0), "path": h["path"], 
                "chunk_idx": h["chunk_idx"], "summary": summary}
        compressed.append(meta)
    
    expand_local, expanded_texts = retr.heuristic_expand(hits, fraction=self.cfg.expand_fraction)
    expanded_full = []
    for local_idx in sorted(list(expand_local)):
        absolute_idx = hits[local_idx]["_index_id"]
        expanded_full.append(self.metadata[absolute_idx]["text"])
```

**What `heuristic_expand()` does**:
- **File**: `rag_core.py`
- **Lines**: 388-409

```python
def heuristic_expand(self, hits: List[Dict[str, Any]], fraction: float = None):
    fraction = fraction or self.cfg.expand_fraction  # 0.15 = 15%
    
    scores = []
    for i, h in enumerate(hits):
        txt = h["text"]
        s = len(txt.split())  # Base score: word count
        
        # Bonus for code-like content
        if any(keyword in txt for keyword in ("def ", "class ", "import ")):
            s += 50
        
        # Bonus from FAISS score
        s += int(h.get("_score", 0) * 10)
        scores.append((i, s))
    
    # Select top 15% for expansion
    N = max(1, int(len(hits) * fraction))
    topk = sorted(scores, key=lambda x: x[1], reverse=True)[:N]
    expand_indices = set(i for i, _ in topk)
    expanded_texts = [hits[i]["text"] for i in sorted(list(expand_indices))]
    
    return expand_indices, expanded_texts
```

**Example**:
```python
# Input: 40 hits
# Fraction: 0.15 → Expand top 6 chunks

# Scoring:
# - Hit 0: 200 words + code bonus (50) + high FAISS score (9.5) = 259.5
# - Hit 1: 150 words + code bonus (50) + medium FAISS score (9.2) = 209.2
# - Hit 5: 100 words + no code + low FAISS score (7.0) = 107.0

# Top 6 selected: [0, 1, 2, 3, 4, 5]
# expand_indices = {0, 1, 2, 3, 4, 5}
# expanded_texts = [full text of chunks 0, 1, 2, 3, 4, 5]
```

```python
    # Step 4b.1d: Compose prompt and generate answer
    prompt = self.compose_prompt(query_text, compressed, expanded_full)
    final_answer = self.vertex_generate(prompt)
    
    return {
        "answer": final_answer,
        "prompt": prompt,
        "retrieved": hits,
        "compressed": compressed,
        "expanded_indices_local": sorted(list(expand_local))
    }
```

**What `compose_prompt()` does**:
- **File**: `rag_prod.py`
- **Lines**: 315-341

```python
def compose_prompt(self, query: str, compressed: List[Dict[str, Any]], expanded_full_texts: List[str]):
    comp_lines = []
    for c in compressed:
        comp_lines.append(f"[chunk_id={c['_index_id']} path={c['path']} score={c['score']:.4f}]\n{c['summary']}")
    comp_block = "\n\n".join(comp_lines[:200])
    expanded_block = "\n\n---\n\n".join(expanded_full_texts[:50])
    
    prompt = f"""
You are an assistant answering developer questions by consulting only the evidence provided below.

QUESTION:
{query}

COMPRESSED EVIDENCE (short summaries of retrieved chunks):
{comp_block}

EXPANDED EVIDENCE (selected full chunks; use these in preference if they are relevant):
{expanded_block}

INSTRUCTIONS:
- Answer concisely and only using the evidence above.
- If the evidence does not answer the question, say "I don't know from the repository evidence."
- When citing specifics (function names, file paths, line numbers), include the chunk_id or file path.
- Keep the answer short (max 400 words) and factual.
Answer:
"""
    return prompt.strip()
```

**Example Prompt**:
```
You are an assistant answering developer questions...

QUESTION:
How do I implement authentication?

COMPRESSED EVIDENCE:
[chunk_id=45 path=/Users/john/my_project/auth.py score=0.9500]
Implements user authentication by checking username existence and verifying password.

[chunk_id=46 path=/Users/john/my_project/auth.py score=0.9200]
Defines AuthMiddleware class for request authentication.

EXPANDED EVIDENCE:
def authenticate(username, password):
    if user_exists(username):
        return verify_password(password)
    return None

---
class AuthMiddleware:
    def __init__(self, secret_key):
        self.secret_key = secret_key
    ...
Answer:
```

**What `vertex_generate()` does**:
- **File**: `rag_prod.py`
- **Lines**: 343-360

```python
@retry(Exception, tries=3, delay=1.0, backoff=2.0, logger=logger)
def vertex_generate(self, prompt: str, max_output_tokens: int = 512, temperature: float = 0.0):
    client = genai.Client(api_key=self.cfg.google_ai_api_key)
    config = GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        top_p=0.95,
    )
    response = client.models.generate_content(
        model=self.cfg.text_model,  # "gemini-1.5-pro"
        contents=[prompt],
        config=config,
    )
    return response.candidates[0].content.parts[0].text.strip()
```

**Example Response**:
```
To implement authentication, you can use the `authenticate()` function from auth.py.
This function checks if the username exists and verifies the password. You can also
use the AuthMiddleware class for request-level authentication. [chunk_id=45, chunk_id=46]
```

**Result**: `rag_context` now contains the answer and retrieved chunks.

---

#### 4c. Orchestrator Coordinates Agents

**File**: `rag_streamlit_app.py`  
**Lines**: 170-174

```python
# Use orchestrator to coordinate agents and generate script if needed
result = st.session_state.orchestrator.orchestrate(
    user_query=user_query,
    rag_context=rag_context,
    rag_pipeline=st.session_state.pipeline
)
```

**What `orchestrate()` does**:
- **File**: `orchestrator_agent.py`
- **Lines**: 67-232

```python
def orchestrate(self, user_query: str, rag_context: Optional[Dict[str, Any]] = None,
               rag_pipeline=None) -> Dict[str, Any]:
    # Step 4c.1: Build orchestrator prompt
    context_part = ""
    if rag_context:
        context_summary = self._summarize_rag_context(rag_context)
        context_part = f"""
CONTEXT FROM RAG SYSTEM:
{context_summary}
"""
```

**What `_summarize_rag_context()` does**:
- **File**: `orchestrator_agent.py`
- **Lines**: 234-246

```python
def _summarize_rag_context(self, rag_context: Dict[str, Any]) -> str:
    summary_parts = []
    if "answer" in rag_context:
        summary_parts.append(f"Answer: {rag_context['answer']}")
    if "retrieved" in rag_context:
        summary_parts.append(f"Retrieved {len(rag_context['retrieved'])} chunks")
        for i, chunk in enumerate(rag_context['retrieved'][:3], 1):
            summary_parts.append(f"\nChunk {i} ({chunk.get('path', 'unknown')}):\n{chunk.get('text', '')[:300]}...")
    return "\n".join(summary_parts)
```

**Example**:
```
CONTEXT FROM RAG SYSTEM:
Answer: To implement authentication, you can use the `authenticate()` function...
Retrieved 40 chunks

Chunk 1 (/Users/john/my_project/auth.py):
def authenticate(username, password):
    if user_exists(username):
        return verify_password(password)
    return None

Chunk 2 (/Users/john/my_project/auth.py):
class AuthMiddleware:
    ...
```

```python
    # Step 4c.2: Build enhanced prompt with function descriptions
    prompt = f"""You are the root orchestrator agent...

USER REQUEST:
{user_query}

{context_part}

TASK:
1. Understand the user's request and the provided context
2. Determine if this requires:
   - Querying the RAG system for more context (use query_rag_system)
   - Generating a Playwright automation script (use generate_playwright_script)
   - Analyzing the context (use analyze_context_understanding)
3. Coordinate appropriate actions"""

    # Add function descriptions
    functions_text = "\n".join([f"- {name}: {desc}" for name, desc in self.function_descriptions.items()])
    enhanced_prompt = f"""{prompt}

AVAILABLE FUNCTIONS:
{functions_text}

INSTRUCTIONS:
- If you need to query the RAG system, respond with: "FUNCTION: query_rag_system(query='...', top_k=40)"
- If you need to generate a Playwright script, respond with: "FUNCTION: generate_playwright_script(user_request='...', script_type='interaction')"
- After calling functions, use the results to provide the final response or generate the script.
"""
```

**Example Enhanced Prompt**:
```
You are the root orchestrator agent...

USER REQUEST:
How do I implement authentication? Generate a Playwright script to test it.

CONTEXT FROM RAG SYSTEM:
Answer: To implement authentication, you can use the `authenticate()` function...
Retrieved 40 chunks

Chunk 1 (/Users/john/my_project/auth.py):
def authenticate(username, password): ...

AVAILABLE FUNCTIONS:
- query_rag_system: Query the RAG system to retrieve relevant context...
- generate_playwright_script: Generate a Playwright automation script...
- analyze_context_understanding: Analyze and understand the context...

INSTRUCTIONS:
- If you need to generate a Playwright script, respond with: "FUNCTION: generate_playwright_script(user_request='...', script_type='interaction')"
...
```

```python
    # Step 4c.3: Call Gemini API with orchestrator prompt
    config = GenerateContentConfig(
        temperature=0.3,
        max_output_tokens=2048,
        top_p=0.95,
        system_instruction=self.system_instruction,
    )
    
    response = self.client.models.generate_content(
        model=self.model,
        contents=[enhanced_prompt],
        config=config,
    )
    
    response_text = response.candidates[0].content.parts[0].text.strip()
```

**Example Gemini Response**:
```
Based on the context, I'll generate a Playwright script to test the authentication function.

FUNCTION: generate_playwright_script(user_request='Generate a Playwright script to test authentication', script_type='testing', target_url='http://localhost:8000/login', context='...')
```

```python
    # Step 4c.4: Parse function calls from response
    import re
    function_pattern = r"FUNCTION:\s*(\w+)\((.*?)\)"
    matches = re.findall(function_pattern, response_text, re.DOTALL)
    
    result = {
        "user_query": user_query,
        "response": response_text,
        "function_calls": [],
        "generated_script": None,
    }
    
    for func_name, func_args_str in matches:
        # Parse arguments
        args = {}
        arg_pattern = r"(\w+)=['\"]([^'\"]+)['\"]"
        arg_matches = re.findall(arg_pattern, func_args_str)
        for arg_name, arg_value in arg_matches:
            args[arg_name] = arg_value
        
        result["function_calls"].append({"name": func_name, "args": args})
```

**Example Parsed Function Calls**:
```python
result["function_calls"] = [
    {
        "name": "generate_playwright_script",
        "args": {
            "user_request": "Generate a Playwright script to test authentication",
            "script_type": "testing",
            "target_url": "http://localhost:8000/login",
            "context": "..."
        }
    }
]
```

```python
    # Step 4c.5: Execute function calls
    if any(fc["name"] == "generate_playwright_script" for fc in result["function_calls"]):
        script_result = self._generate_playwright_script_from_function_call(
            user_query, result.get("enhanced_context", context_part), result["function_calls"]
        )
        result["generated_script"] = script_result
```

**What `_generate_playwright_script_from_function_call()` does**:
- **File**: `orchestrator_agent.py`
- **Lines**: 288-363

```python
def _generate_playwright_script_from_function_call(self, user_request: str, context: str, function_calls: List[Dict]):
    script_call = None
    for fc in function_calls:
        if fc["name"] == "generate_playwright_script":
            script_call = fc
            break
    
    args = script_call["args"]
    script_type = args.get("script_type", "interaction")
    target_url = args.get("target_url", "")
    steps = args.get("steps", [])
    
    # Build prompt for script generation
    prompt = f"""Generate a complete Playwright Python automation script based on the following requirements.

USER REQUEST:
{user_request}

CONTEXT FROM DOCUMENTATION/CODE:
{context}

SCRIPT TYPE: {script_type}
TARGET: {target_url}

REQUIREMENTS:
1. Use Playwright Python API (from playwright.sync_api import sync_playwright)
2. Include proper imports and setup
3. Use stable selectors (prefer data-testid, role, text over CSS)
4. Include error handling with try/except
5. Add appropriate waits (wait_for_load_state, wait_for_selector)
6. Include comments explaining each major step
7. Handle dynamic content loading
8. Make the script production-ready and maintainable

Generate ONLY the Python script code, no explanations before or after."""

    # Call Gemini API to generate script
    response = self.client.models.generate_content(
        model=self.model,
        contents=[prompt],
        config=GenerateContentConfig(temperature=0.2, max_output_tokens=4096),
    )
    
    script = response.candidates[0].content.parts[0].text.strip()
    
    # Clean markdown code blocks if present
    if "```python" in script:
        script = script.split("```python")[1].split("```")[0].strip()
    elif "```" in script:
        script = script.split("```")[1].split("```")[0].strip()
    
    return script
```

**Example Generated Script**:
```python
from playwright.sync_api import sync_playwright

def test_authentication():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        # Navigate to login page
        page.goto("http://localhost:8000/login")
        page.wait_for_load_state("networkidle")
        
        # Fill username
        page.fill('input[name="username"]', "testuser")
        
        # Fill password
        page.fill('input[name="password"]', "testpass123")
        
        # Click login button
        page.click('button[type="submit"]')
        
        # Wait for authentication result
        page.wait_for_selector(".dashboard", timeout=5000)
        
        # Verify successful login
        assert page.locator(".dashboard").is_visible()
        
        browser.close()

if __name__ == "__main__":
    test_authentication()
```

**Result**: `result["generated_script"]` contains the complete Playwright script.

---

#### 4d. Display Results to User

**File**: `rag_streamlit_app.py`  
**Lines**: 338-404

```python
if result:
    # Display orchestrator response
    if result.get("response"):
        st.header("📝 Orchestrator Response")
        st.markdown(result["response"])
    
    # Display RAG answer
    if result.get("rag_result"):
        st.header("📚 Context from RAG System")
        st.markdown(rag_result.get("answer", ""))
    
    # Display generated Playwright script
    if result.get("generated_script"):
        st.header("🎭 Generated Playwright Script")
        script = result["generated_script"]
        st.code(script, language="python")
        
        # Download button
        st.download_button(
            label="📥 Download Script",
            data=script,
            file_name="playwright_script.py",
            mime="text/x-python"
        )
```

**User sees**:
1. Orchestrator's reasoning and coordination steps
2. RAG system's answer based on indexed documents
3. Generated Playwright script ready to download and run

---

## Complete End-to-End Example

Let's trace through a complete example from start to finish.

### Scenario: User wants to understand how authentication works and generate a test script

#### Step 1: Start Application

```bash
cd /Users/john/Agentic/AgenticContext/REFRAG
streamlit run rag_streamlit_app.py
```

**What happens**:
- Python loads `rag_streamlit_app.py`
- Imports trigger loading of all modules:
  - `rag_prod.py` → `rag_core.py`, `rag_agents.py`, `rag_config.py`, `rag_utils.py`
  - `orchestrator_agent.py` → `rag_config.py`, `rag_utils.py`
- Session state initialized (all values = None)
- Streamlit app starts on `http://localhost:8501`

#### Step 2: User Indexes Folder

**User Action**: 
- Selects "📁 Local Folder"
- Enters: `/Users/john/my_project`
- Clicks "📂 Index Folder"

**Execution Flow**:

1. **`rag_streamlit_app.py:210`** → `initialize_pipeline_from_folder("/Users/john/my_project")`

2. **`rag_streamlit_app.py:59`** → `cfg = AppConfig()`
   - **`rag_config.py:48-89`** → Reads `.env`, sets defaults

3. **`rag_streamlit_app.py:60`** → `pipeline = RAGPipeline(cfg)`
   - **`rag_prod.py:70-105`** → Creates all components:
     - `RepoLoader` (from `rag_core.py:65`)
     - `Chunker` (from `rag_core.py:148`)
     - `VertexEmbedder` (from `rag_core.py:181`)
     - `FaissIndexer` (from `rag_core.py:261`)
     - `VertexSummarizer` (from `rag_core.py:327`)
     - `FeedbackLoop` (from `rag_agents.py:23`)
     - `QueryRewriterAgent` (from `rag_agents.py:113`)

4. **`rag_streamlit_app.py:68`** → `pipeline.load_from_cache(expected_folder_path="/Users/john/my_project")`
   - **`rag_prod.py:178-233`** → Checks `index_metadata.json`
   - If cache exists and matches → Loads `metadata.pkl`, `faiss.index`, `raw_embeddings.npy`
   - If cache doesn't exist → Calls `pipeline.ingest_folder()`

5. **`rag_prod.py:129`** → `pipeline.ingest_folder("/Users/john/my_project")`
   - **`rag_core.py:83`** → `RepoLoader.collect_text_files()` → Finds 45 files
   - **`rag_core.py:166`** → `Chunker.chunk_files()` → Creates 127 chunks
   - **`rag_core.py:222`** → `VertexEmbedder.embed_texts()` → API calls to embed 127 chunks
   - **`rag_core.py:267`** → `FaissIndexer.build()` → Creates FAISS index
   - **`rag_prod.py:156`** → Saves to disk: `metadata.pkl`, `faiss.index`, `raw_embeddings.npy`, `index_metadata.json`

6. **`rag_streamlit_app.py:93`** → `OrchestratorAgent(cfg)`
   - **`orchestrator_agent.py:31`** → Initializes orchestrator with Gemini API client

**Result**: Pipeline and orchestrator ready, folder indexed.

#### Step 3: User Queries

**User Action**:
- Query: "How do I implement authentication? Generate a Playwright script to test it."
- Checkbox: "Generate Playwright Script" = ✓
- Clicks "🚀 Query"

**Execution Flow**:

1. **`rag_streamlit_app.py:329`** → `query_with_orchestrator(query, generate_script=True)`

2. **`rag_streamlit_app.py:166`** → `pipeline.query(query, top_k=40)`
   - **`rag_prod.py:277`** → `RAGPipeline.query()`
   - **`rag_core.py:375`** → `Retriever.retrieve()`:
     - **`rag_core.py:222`** → `embedder.embed_texts([query])` → Query embedding (API call 1)
     - **`rag_core.py:297`** → `indexer.search(query_vector, top_k=40)` → FAISS search (LOCAL)
     - Returns 40 chunks with scores
   - **`rag_prod.py:235`** → `ensure_summaries()` → Creates summaries for 40 chunks (API calls 2-41)
   - **`rag_core.py:388`** → `heuristic_expand()` → Selects top 6 chunks for full text
   - **`rag_prod.py:315`** → `compose_prompt()` → Builds prompt with summaries + expanded chunks
   - **`rag_prod.py:343`** → `vertex_generate()` → Generates answer (API call 42)

3. **`rag_streamlit_app.py:170`** → `orchestrator.orchestrate(user_query, rag_context, pipeline)`
   - **`orchestrator_agent.py:67`** → `OrchestratorAgent.orchestrate()`
   - **`orchestrator_agent.py:234`** → `_summarize_rag_context()` → Formats RAG context
   - **`orchestrator_agent.py:115`** → Builds enhanced prompt with function descriptions
   - **`orchestrator_agent.py:137`** → Calls Gemini API → Orchestrator decides to generate script (API call 43)
   - **`orchestrator_agent.py:157`** → Parses function call: `generate_playwright_script(...)`
   - **`orchestrator_agent.py:288`** → `_generate_playwright_script_from_function_call()`:
     - Builds script generation prompt with context
     - Calls Gemini API → Generates Playwright script (API call 44)
     - Returns script code

4. **`rag_streamlit_app.py:338`** → Display results:
   - Shows orchestrator response
   - Shows RAG answer
   - Shows generated Playwright script with download button

**Result**: User receives answer and downloadable Playwright script.

**Total API Calls**: 44
- 1 query embedding
- 40 chunk summaries (on-demand, cached for future queries)
- 1 answer generation
- 1 orchestrator coordination
- 1 script generation

**Future Queries**: Only 2-3 API calls (query embedding + answer generation + optional script generation)

---

## Module-by-Module Breakdown

### 1. `rag_config.py` - Configuration Module

**Purpose**: Central configuration and constants

**Key Components**:
- **`AppConfig` dataclass** (Lines 48-89): All pipeline settings
- **Constants**: Default paths, model names, parameters

**Functions**:
```python
# Example usage
cfg = AppConfig()
# cfg.chunk_size_words = 200
# cfg.google_ai_api_key = "your-key"
# cfg.cache_dir = "./rag_cache"
```

**Used by**: All other modules

---

### 2. `rag_utils.py` - Utilities Module

**Purpose**: Shared utility functions

**Key Components**:
- **`retry()` decorator** (Lines 17-33): Exponential backoff retry logic
- **`logger`**: Shared logger instance

**Functions**:
```python
@retry(Exception, tries=4, delay=1.0, backoff=2.0, logger=logger)
def api_call():
    # Will retry up to 4 times: 1s, 2s, 4s delays
    pass
```

**Used by**: `rag_core.py`, `rag_agents.py`, `orchestrator_agent.py`, `rag_prod.py`

---

### 3. `rag_core.py` - Core RAG Components

**Purpose**: Foundation RAG functionality

**Key Classes**:

#### `RepoLoader` (Lines 65-142)
- **`clone()`**: Clones GitHub repositories
- **`collect_text_files()`**: Recursively collects text files, skips binary

#### `Chunker` (Lines 148-175)
- **`chunk_text()`**: Splits text into overlapping chunks
- **`chunk_files()`**: Chunks multiple files with metadata

#### `VertexEmbedder` (Lines 181-255)
- **`embed_batch()`**: Embeds texts using Gemini API
- **`embed_texts()`**: Public API with batching and caching

#### `FaissIndexer` (Lines 261-303)
- **`build()`**: Creates FAISS index from vectors
- **`save()` / `load()`**: Persists index to disk
- **`search()`**: Searches for nearest neighbors (LOCAL, no API)

#### `VertexSummarizer` (Lines 327-361)
- **`summarize()`**: Creates short summaries using Gemini API

#### `ProjectionMLP` (Lines 309-321)
- **Neural network**: Projects embeddings (research feature)

#### `Retriever` (Lines 367-409)
- **`retrieve()`**: Retrieves chunks from FAISS index
- **`heuristic_expand()`**: Selects chunks for full text expansion

**Used by**: `rag_prod.py`, `rag_agents.py`

---

### 4. `rag_agents.py` - Agentic RAG Components

**Purpose**: Advanced agentic RAG features

**Key Classes**:

#### `FeedbackLoop` (Lines 23-116)
- **`record_correction()`**: Records user corrections
- **`record_positive_feedback()`**: Records thumbs up
- **`record_negative_feedback()`**: Records thumbs down
- **`boost_chunk_scores()`**: Boosts preferred chunks

#### `QueryRewriterAgent` (Lines 113-195)
- **`rewrite_query()`**: Expands/clarifies queries using Gemini API

#### `RetrievalAgent` (Lines 200-229)
- **`retrieve()`**: Specialized retrieval with feedback boosting

#### `ContextComposerAgent` (Lines 234-277)
- **`compose_context()`**: Assembles compressed and expanded context

#### `AnswerGeneratorAgent` (Lines 282-357)
- **`generate_answer()`**: Generates answers from context
- **`_compose_prompt()`**: Builds prompts for answer generation

#### `IterativeRefinerAgent` (Lines 362-502)
- **`refine_iteratively()`**: Iteratively refines retrieval and answers
- **`_analyze_answer_quality()`**: Analyzes if answer is sufficient

**Used by**: `rag_prod.py`

---

### 5. `orchestrator_agent.py` - Root Orchestrator Agent

**Purpose**: Coordinates entire agentic system and generates Playwright scripts

**Key Class**:

#### `OrchestratorAgent` (Lines 25-363)
- **`__init__()`**: Initializes with Gemini API client and function descriptions
- **`orchestrate()`**: Main orchestration method
  - Understands user requests
  - Coordinates RAG queries
  - Generates Playwright scripts
- **`generate_playwright_script()`**: Direct method to generate scripts
- **`_summarize_rag_context()`**: Formats RAG context for orchestrator
- **`_generate_playwright_script_from_function_call()`**: Generates scripts from function calls

**Example**:
```python
orchestrator = OrchestratorAgent(cfg)
result = orchestrator.orchestrate(
    user_query="Generate a Playwright script to test login",
    rag_context=rag_result,
    rag_pipeline=pipeline
)
# Returns: {"response": "...", "generated_script": "from playwright...", ...}
```

**Used by**: `rag_streamlit_app.py`

---

### 6. `rag_prod.py` - Main RAG Pipeline

**Purpose**: Orchestrates all components, provides main API

**Key Class**:

#### `RAGPipeline` (Lines 70-417)
- **`__init__()`**: Initializes all components
- **`ingest_repo()`**: Indexes GitHub repository
- **`ingest_folder()`**: Indexes local folder
- **`load_from_cache()`**: Loads cached index
- **`ensure_summaries()`**: Creates summaries on-demand
- **`query()`**: Main query method
  - Retrieves chunks
  - Ensures summaries
  - Expands chunks
  - Generates answer
- **`query_with_rewrite()`**: Query with query rewriting
- **`query_iterative()`**: Query with iterative refinement
- **`record_feedback()`**: Records user feedback

**Example**:
```python
pipeline = RAGPipeline(AppConfig())
pipeline.ingest_folder("/path/to/project")
result = pipeline.query("How do I implement X?")
print(result["answer"])
```

**Used by**: `rag_streamlit_app.py`

---

### 7. `rag_streamlit_app.py` - Frontend Interface

**Purpose**: Streamlit web interface for users

**Key Functions**:

#### `initialize_pipeline_from_folder()` (Lines 55-100)
- Initializes RAG pipeline from local folder
- Handles cache validation
- Creates orchestrator agent

#### `initialize_pipeline()` (Lines 103-146)
- Initializes RAG pipeline from GitHub repository
- Handles cloning and indexing

#### `query_with_orchestrator()` (Lines 149-180)
- Coordinates query flow
- Calls RAG pipeline if needed
- Calls orchestrator agent
- Returns combined results

**UI Components**:
- Sidebar: Configuration, input mode, query settings, status
- Main area: Query input, results display, script download

---

## Installation & Setup

### 1. Install Dependencies

```bash
pip install faiss-cpu google-genai gitpython torch python-dotenv requests tqdm streamlit
```

### 2. Set Up Environment Variables

Create `.env` file in project root:

```bash
# Required
GOOGLE_AI_API_KEY=your-gemini-api-key-here

# Optional - Model Configuration
EMBEDDING_MODEL=text-embedding-004
TEXT_MODEL=gemini-1.5-pro

# Optional - Paths
CACHE_DIR=./rag_cache

# Optional - Parameters
CHUNK_SIZE_WORDS=200
CHUNK_OVERLAP_WORDS=30
TOP_K=40
EXPAND_FRACTION=0.15
```

### 3. Get API Key

Visit: https://makersuite.google.com/app/apikey

---

## Troubleshooting

### Error: `GOOGLE_AI_API_KEY not set`

**Solution**: Set `GOOGLE_AI_API_KEY` in `.env` file

### Error: `ModuleNotFoundError: No module named 'rag_prod'`

**Solution**: Ensure you're running from the `REFRAG/` directory:
```bash
cd REFRAG
streamlit run rag_streamlit_app.py
```

### Error: Cache doesn't match folder

**Solution**: This is expected behavior. The system automatically re-indexes when folder changes.

### Slow Queries

**Causes**:
- Generating summaries on-demand (many API calls)
- Large `top_k` value

**Solutions**:
- Pre-generate summaries: Query once to cache summaries
- Reduce `top_k`: Use sidebar slider to lower value

---

## Summary

This training manual explained how the Agentic RAG System works:

1. **Frontend** (`rag_streamlit_app.py`) - User interface
2. **Orchestrator** (`orchestrator_agent.py`) - Coordinates agents and generates scripts
3. **RAG Pipeline** (`rag_prod.py`) - Main pipeline orchestrator
4. **Agents** (`rag_agents.py`) - Specialized agentic components
5. **Core** (`rag_core.py`) - Foundation RAG components
6. **Config & Utils** - Support modules

**Key Flow**:
- User indexes folder → Core components process files → FAISS index created
- User queries → RAG retrieves relevant chunks → Orchestrator coordinates → Script generated → Response displayed

**API Calls**:
- **Indexing**: ~N calls (one per chunk, cached forever)
- **Query**: 2-3 calls (query embedding + answer generation + optional script generation)
- **Summaries**: Created on-demand, cached for future queries

The system is designed for efficiency: documents are embedded **once**, queries can be made **unlimited times** using the local FAISS index!
