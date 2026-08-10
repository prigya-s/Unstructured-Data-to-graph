"""
LocalEmbeddingProvider: documented no-op pass-through.

There is no embedding-generation code anywhere in kg-local today. This
class exists to complete the pipeline shape (Chunking -> Embeddings ->
Entity Extraction) without inventing new ML business logic: it copies each
chunk into the DocumentEmbeddingRecord contract with embedding_vector left
as None, rather than fabricating a placeholder vector that could be
mistaken for a real one. A future Databricks embedding model implementation
(see DatabricksEmbeddingProvider) only has to populate embedding_vector/
embedding_model - nothing downstream needs to change, since
entity_extraction_stage.py reads chunks, not embeddings.
"""

from __future__ import annotations

from .embedding_provider import EmbeddingProvider


class LocalEmbeddingProvider(EmbeddingProvider):
    def embed_chunks(self, chunks: list[dict]) -> list[dict]:
        return [
            {
                "chunk_id": chunk["chunk_id"],
                "document": chunk["document"],
                "embedding_vector": None,
                "embedding_model": None,
            }
            for chunk in chunks
        ]
