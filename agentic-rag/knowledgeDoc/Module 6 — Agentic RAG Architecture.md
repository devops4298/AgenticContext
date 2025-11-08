📘 Definition
An Agentic RAG System is a multi-agent loop where each stage (retrieve, reason, reflect) is handled by a specialized agent under a coordinator.
🧠 Analogy
Like a newsroom:
Reporter = Retriever Agent
Editor = Composer Agent
Writer = Responder Agent
Chief Editor = Planner/Orchestrator Agent

💼 Production Example
Use Case: Enterprise Q&A Assistant

Flow:
```graphql

User Query → RewriterAgent → RetrieverAgent → ComposerAgent → ResponderAgent → MemoryAgent

```
🧰 ADK Integration
Coordinator: ContextOrchestratorAgent
```python

# module6_agentic_rag.py
from google_adk import Agent, AgentConfig

agent_config = AgentConfig(
    name="ContextOrchestratorAgent",
    description="Coordinates RAG sub-agents for query rewriting, retrieval, and answering."
)

orchestrator_agent = Agent(config=agent_config)

def handle_query(user_query):
    rewritten = orchestrator_agent.call_tool("query_rewriter_tool", user_query)
    hits = orchestrator_agent.call_tool("vector_retriever_tool", rewritten)
    context = orchestrator_agent.call_tool("context_composer_tool", hits)
    answer = orchestrator_agent.call_model(context + f"\n\nUser: {user_query}")
    return answer


```

✅ Key Takeaways
 Decompose RAG into cooperating ADK agents.
 Planner orchestrates the reasoning chain (ReAct pattern).
 Each tool is observable, modular, and replaceable.

 