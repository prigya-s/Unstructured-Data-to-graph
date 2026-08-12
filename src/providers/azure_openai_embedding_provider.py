"""
AzureOpenAIEmbeddingProvider: real embeddings via the Azure OpenAI embeddings
REST API. Same batched, stdlib-urllib, config-driven shape as
DatabricksEmbeddingProvider - see that class for the pattern being mirrored.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from config.app_config import AppConfig
from providers.embedding_provider import EmbeddingProvider
from providers.secrets_provider import get_secrets_provider


class AzureOpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, config: AppConfig) -> None:
        options = config.embedding.options.get("azure_openai", {})
        secrets = get_secrets_provider(config)
        self.endpoint = secrets.get(options.get("endpoint_env", "AZURE_OPENAI_ENDPOINT"))
        self.api_key = secrets.get(options.get("api_key_env", "AZURE_OPENAI_API_KEY"))
        self.deployment = options.get("deployment", "text-embedding-3-large")
        self.api_version = options.get("api_version", "2024-06-01")
        self.batch_size = int(options.get("batch_size", 64))
        self.request_timeout_seconds = float(options.get("request_timeout_seconds", 30))

        missing = [
            name
            for name, value in (("endpoint", self.endpoint), ("api_key", self.api_key))
            if not value
        ]
        if missing:
            raise ValueError(
                f"AzureOpenAIEmbeddingProvider is missing secrets: {', '.join(missing)}. "
                "Set them via the configured SecretsProvider (e.g. .env for EnvSecretsProvider)."
            )

    def _invoke(self, texts: list[str]) -> list[list[float]]:
        url = (
            f"{self.endpoint.rstrip('/')}/openai/deployments/{self.deployment}/embeddings"
            f"?api-version={self.api_version}"
        )
        payload = json.dumps({"input": texts}).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={"api-key": self.api_key, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Azure OpenAI embedding deployment '{self.deployment}' returned {exc.code}: {detail}"
            ) from exc
        return [row["embedding"] for row in body["data"]]

    def embed_chunks(self, chunks: list[dict]) -> list[dict]:
        results: list[dict] = []
        for start in range(0, len(chunks), self.batch_size):
            batch = chunks[start : start + self.batch_size]
            vectors = self._invoke([chunk["content"] for chunk in batch])
            for chunk, vector in zip(batch, vectors):
                results.append(
                    {
                        "chunk_id": chunk["chunk_id"],
                        "document": chunk["document"],
                        "embedding_vector": vector,
                        "embedding_model": self.deployment,
                    }
                )
        return results
