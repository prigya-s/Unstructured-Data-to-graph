"""
AzureOpenAIChatLLMProvider: constructs the Microsoft Agent Framework
AzureOpenAIChatClient, secrets resolved via the existing SecretsProvider
abstraction - same indirection Neo4jGraphProvider/AzureOpenAIEmbeddingProvider
already use, so no plaintext keys ever live in config.yaml.
"""

from __future__ import annotations

from config.app_config import AppConfig
from providers.llm_provider import LLMProvider
from providers.secrets_provider import get_secrets_provider


class AzureOpenAIChatLLMProvider(LLMProvider):
    def __init__(self, config: AppConfig) -> None:
        options = config.llm.options.get("azure_openai", {})
        secrets = get_secrets_provider(config)
        self.endpoint = secrets.get(options.get("endpoint_env", "AZURE_OPENAI_ENDPOINT"))
        self.api_key = secrets.get(options.get("api_key_env", "AZURE_OPENAI_API_KEY"))
        self.deployment = options.get("deployment", "gpt-4o")
        self.api_version = options.get("api_version", "2024-06-01")

        missing = [
            name
            for name, value in (("endpoint", self.endpoint), ("api_key", self.api_key))
            if not value
        ]
        if missing:
            raise ValueError(
                f"AzureOpenAIChatLLMProvider is missing secrets: {', '.join(missing)}. "
                "Set them via the configured SecretsProvider (e.g. .env for EnvSecretsProvider)."
            )

    def get_chat_client(self):
        from agent_framework.azure import AzureOpenAIChatClient

        return AzureOpenAIChatClient(
            endpoint=self.endpoint,
            api_key=self.api_key,
            deployment_name=self.deployment,
            api_version=self.api_version,
        )
