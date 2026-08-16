"""
OllamaEmbeddingProvider: real embeddings via a local Ollama-served embedding
model (BGE-M3 by default). Same batched, stdlib-urllib, config-driven shape
as AzureOpenAIEmbeddingProvider/DatabricksEmbeddingProvider - no auth
required since Ollama runs unauthenticated on localhost, so no
SecretsProvider indirection is needed here.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from config.app_config import AppConfig
from providers.embedding_provider import EmbeddingProvider


class OllamaEmbeddingProvider(EmbeddingProvider):
    def __init__(self, config: AppConfig) -> None:
        options = config.embedding.options.get("ollama", {})
        self.base_url = options.get("base_url", "http://localhost:11434")
        self.model = options.get("model", "bge-m3")
        self.batch_size = int(options.get("batch_size", 64))
        self.request_timeout_seconds = float(options.get("request_timeout_seconds", 60))

    def _invoke(self, texts: list[str]) -> list[list[float]]:
        payload = json.dumps({"model": self.model, "input": texts}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/api/embed",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Ollama embedding model '{self.model}' at {self.base_url} returned {exc.code}: {detail}"
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(
                f"Could not reach Ollama at {self.base_url} for embedding model '{self.model}': {exc}"
            ) from exc
        return body["embeddings"]

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
                        "embedding_model": self.model,
                    }
                )
        return results
