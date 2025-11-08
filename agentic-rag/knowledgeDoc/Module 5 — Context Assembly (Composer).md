📘 Definition
Context assembly combines the most relevant chunks into a coherent context window for the LLM.

🧠 Analogy
Like arranging puzzle pieces so the final picture makes sense.

💼 Production Example
Use Case: Customer Support Summarizer

| Step     | Example                                    |
| -------- | ------------------------------------------ |
| Retrieve | Top 10 chunks from Chroma DB               |
| Sort     | By relevance score                         |
| Merge    | Remove duplicates and conflicting lines    |
| Trim     | Limit to 6,000 tokens (for 8k-token model) |

🧰 ADK Integration
Tool Name: ContextComposerTool
Purpose: Assemble and budget retrieved chunks.

```python
# module5_context_composer_tool.py
from google_adk import Tool
import tiktoken

def compose_context(chunks, max_tokens=6000):
    enc = tiktoken.get_encoding("cl100k_base")
    combined = ""
    total = 0
    for c in chunks:
        tokens = enc.encode(c)
        if total + len(tokens) > max_tokens:
            break
        combined += c + "\n---\n"
        total += len(tokens)
    return combined.strip()

context_composer_tool = Tool(
    name="context_composer_tool",
    description="Combines retrieved text chunks into a single prompt context.",
    func=compose_context
)

```
✅ Key Takeaways
 Sort by relevance before merging.
 Deduplicate or cluster similar chunks.
 Control prompt size (token budgeting).