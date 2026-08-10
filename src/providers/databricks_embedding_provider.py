"""
DatabricksEmbeddingProvider: EmbeddingProvider backed by a Databricks Model
Serving embedding endpoint.

Calls the endpoint's OpenAI-compatible /serving-endpoints/<name>/invocations
API with {"input": [chunk texts]} and reads back one embedding vector per
input, in order - the standard shape for a Databricks Foundation Model API
embedding endpoint (e.g. databricks-gte-large-en). Uses stdlib urllib only
(no new dependency) since this is a single JSON-in/JSON-out POST.

Batches chunks (default 64 per request - override via
embedding.databricks.batch_size) since serving endpoints cap request size;
callers never see the batching, embed_chunks() always returns one row per
input chunk in the same order.

Endpoint name / workspace host / auth token env var names come from
config.yaml's embedding.databricks block - see config.databricks.example.yaml.
Not exercised by local dev, and not executable without a real Databricks
workspace and a deployed embedding endpoint.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from config.app_config import AppConfig

from .embedding_provider import EmbeddingProvider
from .secrets_provider import get_secrets_provider


class DatabricksEmbeddingProvider(EmbeddingProvider):
    def __init__(self, config: AppConfig) -> None:
        options = config.embedding.options.get("databricks", {})
        secrets = get_secrets_provider(config)
        self.host = secrets.get(options.get("host_env", "DATABRICKS_HOST"))
        self.token = secrets.get(options.get("token_env", "DATABRICKS_TOKEN"))
        self.endpoint = secrets.get(
            options.get("endpoint_env", "DATABRICKS_EMBEDDING_ENDPOINT")
        )
        self.model_name = options.get("model_name", self.endpoint)
        self.batch_size = int(options.get("batch_size", 64))

    def _invoke(self, texts: list[str]) -> list[list[float]]:
        url = f"{self.host.rstrip('/')}/serving-endpoints/{self.endpoint}/invocations"
        payload = json.dumps({"input": texts}).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Databricks embedding endpoint '{self.endpoint}' returned "
                f"{exc.code}: {detail}"
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
                        "embedding_model": self.model_name,
                    }
                )
        return results
