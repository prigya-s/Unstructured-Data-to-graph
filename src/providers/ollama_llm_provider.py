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
        self.num_thread = options.get("num_thread")
        self.temperature = options.get("temperature")
        self.seed = options.get("seed")

    def get_chat_client(self):
        from agent_framework.ollama import OllamaChatClient

        return OllamaChatClient(host=self.base_url, model=self.model)

    def get_chat_options(self) -> dict:
        # CPU-only inference: pin the generation call to all physical cores
        # (see config.yaml llm.ollama.num_thread) rather than relying on
        # Ollama's own thread-count heuristic. temperature/seed (also
        # config.yaml llm.ollama) make identical (prompt, context) pairs
        # reproduce the same answer instead of resampling every call.
        options = {}
        if self.num_thread:
            options["num_thread"] = self.num_thread
        if self.temperature is not None:
            options["temperature"] = self.temperature
        if self.seed is not None:
            options["seed"] = self.seed
        return options
