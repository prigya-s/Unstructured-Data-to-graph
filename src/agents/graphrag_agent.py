"""
GraphRAG agent orchestration: wires an agent_framework.Agent to a single
tool, graph_context_tool, that runs the retrieval pipeline
(retrieval.graphrag_service.retrieve_context) and hands the assembled,
Gold-only context back to the LLM. Implements the required flow literally:

    User Query -> Agent -> Vector Search -> Relevant Chunks -> Graph
    Expansion -> Gold Graph Traversal -> Context Assembly -> LLM -> Response

The agent itself never touches GraphProvider/EmbeddingProvider directly -
only graph_context_tool does, so retrieval stays swappable/testable
independent of the agent runtime.
"""

from __future__ import annotations

import asyncio

from config.app_config import AppConfig
from prompts.graphrag_answer import INSTRUCTIONS
from retrieval.graphrag_service import RetrievalResult, format_context_for_llm, retrieve_context


class GraphRAGAgent:
    """Wraps an agent_framework Agent plus a mutable holder for the last
    retrieval result, so a caller (CLI/Streamlit) can render citations
    (source chunk, source document, graph path used) after each turn."""

    def __init__(self, chat_agent, config: AppConfig) -> None:
        self._chat_agent = chat_agent
        self.config = config
        self.last_result: RetrievalResult = RetrievalResult()

    def get_new_thread(self):
        return self._chat_agent.create_session()

    async def run(self, message: str, thread=None):
        max_length = self.config.retrieval.max_query_length
        if not message or not message.strip():
            raise ValueError("Query must not be empty.")
        if len(message) > max_length:
            raise ValueError(f"Query exceeds the maximum allowed length of {max_length} characters.")

        coro = self._chat_agent.run(message) if thread is None else self._chat_agent.run(message, session=thread)
        return await asyncio.wait_for(coro, timeout=self.config.retrieval.agent_timeout_seconds)


def build_agent(llm_provider, embedding_provider, graph_provider, config: AppConfig) -> GraphRAGAgent:
    from agent_framework import Agent

    holder = GraphRAGAgent(chat_agent=None, config=config)

    def graph_context_tool(query: str) -> str:
        """Retrieves approved knowledge-graph context relevant to `query`:
        matching document excerpts, mentioned entities, and the
        relationships between them. Use this before answering any question
        about the knowledge graph's content."""
        safe_query = query[: config.retrieval.max_query_length]
        result = retrieve_context(safe_query, embedding_provider, graph_provider, config)
        holder.last_result = result
        return format_context_for_llm(result)

    holder._chat_agent = Agent(
        client=llm_provider.get_chat_client(),
        name="Knowledge Graph Assistant",
        instructions=INSTRUCTIONS,
        tools=[graph_context_tool],
    )
    return holder
