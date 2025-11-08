📘 Definition
Embeddings convert text into high-dimensional numerical vectors representing meaning.
A vector store indexes these vectors for fast semantic similarity search.

⚙️ Why It Matters
| **Without Embeddings**       | **With Embeddings**              |
| ---------------------------- | -------------------------------- |
| Search is keyword-based only | Search is meaning-based          |
| Irrelevant results           | Contextually precise matches     |
| Inflexible scaling           | Can handle millions of documents |

🧠 Analogy
Think of each text chunk as a coordinate in a “semantic galaxy.”
Similar ideas orbit close together — embeddings are their coordinates.

💼 Production Example
Use Case: Knowledge Base Search
| Stage    | Implementation                                            |
| -------- | --------------------------------------------------------- |
| Model    | `sentence-transformers/all-MiniLM-L6-v2`                  |
| Storage  | **Chroma DB** or **FAISS**                                |
| Metadata | `{"source": "policy.pdf", "section": "benefits"}`         |
| Search   | Cosine similarity between query vector and stored vectors |

🧰 ADK Integration
Tool Name: EmbedderTool
Purpose: Embed text chunks and store them in a vector database.

```python

# module3_embedder_tool.py
from google_adk import Tool
from sentence_transformers import SentenceTransformer
import chromadb

embed_model = SentenceTransformer("all-MiniLM-L6-v2")
client = chromadb.Client()
collection = client.get_or_create_collection("docs")

def embed_and_store(chunks, metadata_list=None):
    vectors = embed_model.encode(chunks, show_progress_bar=False)
    ids = [f"chunk_{i}" for i in range(len(chunks))]
    collection.upsert(
        embeddings=vectors.tolist(),
        documents=chunks,
        metadatas=metadata_list or [{}],
        ids=ids
    )
    return f"Stored {len(chunks)} chunks in vector DB."

embedder_tool = Tool(
    name="embedder_tool",
    description="Embeds text chunks and stores vectors in Chroma DB.",
    func=embed_and_store
)
```

✅ Key Takeaways
 Choose lightweight models (MiniLM, E5) for speed.
 Keep metadata rich — enables traceability.
 Vector DB choice: Chroma (simple) or FAISS (fast local).
 Persist embeddings after ingestion.