📘 Definition
Query rewriting enhances user input for more accurate retrieval.
It bridges the gap between how humans ask and how data is stored.

🧠 Analogy
Like a librarian interpreting “car policy” into “company vehicle insurance policy 2025 edition.”
💼 Production Example
Use Case: HR Bot
| User Query      | Rewritten Query                                           |
| --------------- | --------------------------------------------------------- |
| “car policy”    | “employee company vehicle insurance and fuel policy 2025” |
| “vacation days” | “employee leave and PTO policy document”                  |

🧰 ADK Integration
Tool Name: QueryRewriterTool
Purpose: Expand or clarify user queries before retrieval.

```python
# module4_query_rewriter_tool.py
from google_adk import Tool
import openai, os

openai.api_key = os.getenv("OPENAI_API_KEY")

def rewrite_query(query: str):
    prompt = f"Rewrite this query for better document search: {query}"
    resp = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=50
    )
    return resp.choices[0].message.content.strip()

query_rewriter_tool = Tool(
    name="query_rewriter_tool",
    description="Expands or clarifies user queries using an LLM.",
    func=rewrite_query
)
```

✅ Key Takeaways
 Use LLMs for semantic expansion of short queries.
 Log rewrites for analysis and continual improvement.
 Combine rewriting with retrieval feedback for precision.