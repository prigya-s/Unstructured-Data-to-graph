"""
EmbeddingStage: silver chunks -> EmbeddingProvider.embed_chunks() ->
StorageProvider.write_embeddings() (silver).
"""

from __future__ import annotations

from pipeline.context import PipelineContext

from .base import PipelineStage


class EmbeddingStage(PipelineStage):
    name = "embedding"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        chunks = ctx.storage.read_chunks()
        embeddings = ctx.embedding_provider.embed_chunks(chunks)
        ctx.embeddings = embeddings
        ctx.storage.write_embeddings(embeddings)
        return ctx
