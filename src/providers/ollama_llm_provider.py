"""
OllamaLLMProvider: constructs the Microsoft Agent Framework OllamaChatClient
for a local Ollama-served chat model (Qwen3 14B by default). Same shape as
AzureOpenAIChatLLMProvider, minus the SecretsProvider indirection - Ollama
runs unauthenticated on localhost, so there is no secret to resolve.
Nothing downstream (agents/graphrag_agent.py, retrieval/graphrag_service.py,
app/pages/chat.py) changes when this provider is selected instead of Azure -
proving the "config change only" migration path in both directions.
"""

from __future__ import annotations

from config.app_config import AppConfig
from providers.llm_provider import LLMProvider


class OllamaLLMProvider(LLMProvider):
    def __init__(self, config: AppConfig) -> None:
        options = config.llm.options.get("ollama", {})
        self.base_url = options.get("base_url", "http://localhost:11434")
        self.model = options.get("model", "qwen3:14b")

    def get_chat_client(self):
        from agent_framework.ollama import OllamaChatClient

        return OllamaChatClient(host=self.base_url, model=self.model)
