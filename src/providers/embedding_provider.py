"""
EmbeddingProvider: the abstraction boundary for turning chunks into
DocumentEmbeddingRecord rows. See LocalEmbeddingProvider for why the local
implementation is a documented no-op rather than a real embedding model.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed_chunks(self, chunks: list[dict]) -> list[dict]:
        """chunks: DocumentChunkRecord-shaped dicts. Returns
        DocumentEmbeddingRecord-shaped dicts, one per input chunk."""
