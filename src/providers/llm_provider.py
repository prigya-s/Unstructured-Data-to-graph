"""
LLMProvider: the abstraction boundary for the chat-completion backend behind
the GraphRAG conversational layer. Mirrors EmbeddingProvider/GraphProvider's
ABC + get_*_provider(config) factory convention. Returns a Microsoft Agent
Framework chat client (a ChatClientProtocol implementation), not raw text -
src/agents/graphrag_agent.py wires that client into a ChatAgent.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    @abstractmethod
    def get_chat_client(self) -> Any:
        """Returns a Microsoft Agent Framework ChatClientProtocol
        implementation, e.g. agent_framework.azure.AzureOpenAIChatClient."""

    def get_chat_options(self) -> dict[str, Any]:
        """Provider-specific per-request options to pass to get_response()
        (e.g. Ollama's num_thread). Empty by default - most providers need
        none."""
        return {}
