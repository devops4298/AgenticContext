📘 Definition
Chunking is the process of dividing large documents into semantically meaningful pieces small enough for an LLM’s context window.
⚙️ Why It Matters
| **Without Chunking**                       | **With Chunking**                             |
| ------------------------------------------ | --------------------------------------------- |
| Model loses context beyond token limit     | Every chunk is self-contained and retrievable |
| Retrieval returns partial or noisy results | Relevant content is isolated precisely        |
| Costly re-tokenization                     | Efficient vector storage and retrieval        |

🧱 Chunking Strategies
| **Type**                        | **Description**                                                | **Best For**           |
| ------------------------------- | -------------------------------------------------------------- | ---------------------- |
| **Fixed Window**                | Split text by token count (e.g., 300 tokens)                   | Simple use-cases       |
| **Recursive Semantic Chunking** | Break at semantic boundaries (paragraphs, headings, sentences) | High-quality retrieval |
| **Dynamic Context Windows**     | Adjust chunk size depending on model’s token budget            | Large-context models   |

🧠 Analogy
Like slicing a loaf of bread: if slices are too thick, they don’t fit the toaster (LLM); too thin, they crumble (loss of meaning). Chunking finds the “just right” slice.

💼 Production Example

Use Case: Product Manual Chatbot
| Step        | Implementation                                        |
| ----------- | ----------------------------------------------------- |
| Pre-chunk   | Split PDF by section titles & paragraphs              |
| Token limit | 400 tokens per chunk, 50 overlap                      |
| Metadata    | `{"doc":"manual.pdf", "page":12, "section":"safety"}` |
| Store       | Chroma DB for fast semantic retrieval                 |

🧰 ADK Integration
Tool Name: ChunkerTool
Purpose: Split text documents into context-optimized chunks.

```python

# module2_chunker_tool.py
from google_adk import Tool
import tiktoken

def adaptive_chunk(text: str, max_tokens=400, overlap=50):
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunk = enc.decode(tokens[start:end])
        chunks.append(chunk)
        start += (max_tokens - overlap)
    return chunks

chunker_tool = Tool(
    name="chunker_tool",
    description="Splits text into semantically coherent, overlapping chunks for embedding.",
    func=adaptive_chunk
)
```
✅ Key Takeaways
 Always chunk by semantic boundaries when possible.
 Maintain token overlap (10-20%) to preserve context flow.
 Store metadata like filename, page, section.
 Use chunk size tuned to LLM’s max tokens (e.g., 8K → ~400-800 tokens).