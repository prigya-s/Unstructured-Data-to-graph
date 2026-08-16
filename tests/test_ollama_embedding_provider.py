"""OllamaEmbeddingProvider must batch chunks into /api/embed calls and map
each returned vector back onto its chunk - no real Ollama server required,
the HTTP layer is mocked."""

from __future__ import annotations

import json
import urllib.error

import pytest

from config.app_config import AppConfig, EmbeddingConfig
from providers.ollama_embedding_provider import OllamaEmbeddingProvider


class _FakeResponse:
    def __init__(self, body: dict) -> None:
        self._body = json.dumps(body).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def _config(**options) -> AppConfig:
    return AppConfig(embedding=EmbeddingConfig(provider="ollama", options={"ollama": options}))


def test_embed_chunks_batches_and_maps_vectors(monkeypatch):
    provider = OllamaEmbeddingProvider(_config(batch_size=2))
    chunks = [
        {"chunk_id": "c1", "document": "d1", "content": "hello"},
        {"chunk_id": "c2", "document": "d1", "content": "world"},
        {"chunk_id": "c3", "document": "d1", "content": "again"},
    ]
    requests_made = []

    def fake_urlopen(request, timeout):
        requests_made.append(json.loads(request.data.decode("utf-8")))
        n = len(requests_made[-1]["input"])
        return _FakeResponse({"embeddings": [[0.1 * n, 0.2 * n]] * n})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    results = provider.embed_chunks(chunks)

    assert len(requests_made) == 2  # batch_size=2 over 3 chunks
    assert [r["chunk_id"] for r in results] == ["c1", "c2", "c3"]
    assert all(r["embedding_model"] == "bge-m3" for r in results)
    assert all(isinstance(r["embedding_vector"], list) for r in results)


def test_embed_chunks_raises_runtime_error_on_http_error(monkeypatch):
    provider = OllamaEmbeddingProvider(_config())

    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            "http://localhost:11434/api/embed", 500, "boom", {}, None
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    # HTTPError.read() requires a file-like fp; patch it after construction.

    def fake_urlopen_with_body(request, timeout):
        error = urllib.error.HTTPError(
            "http://localhost:11434/api/embed", 500, "boom", {}, None
        )
        error.read = lambda: b"server error"
        raise error

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen_with_body)

    with pytest.raises(RuntimeError, match="bge-m3"):
        provider.embed_chunks([{"chunk_id": "c1", "document": "d1", "content": "hello"}])


def test_embed_chunks_raises_runtime_error_on_url_error(monkeypatch):
    provider = OllamaEmbeddingProvider(_config())

    def fake_urlopen(request, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="Could not reach Ollama"):
        provider.embed_chunks([{"chunk_id": "c1", "document": "d1", "content": "hello"}])
