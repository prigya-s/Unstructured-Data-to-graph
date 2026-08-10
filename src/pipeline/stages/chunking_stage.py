"""
ChunkingStage: silver markdown -> chunking.semantic_chunker.chunk_markdown
(unmodified) -> StorageProvider.write_chunks() (silver).
"""

from __future__ import annotations

from chunking import semantic_chunker
from pipeline.context import PipelineContext

from .base import PipelineStage


class ChunkingStage(PipelineStage):
    name = "chunking"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        markdown_documents = ctx.storage.read_markdown()
        all_chunks: list[dict] = []
        for doc in markdown_documents:
            chunks = semantic_chunker.chunk_markdown(doc["markdown"], doc["document_id"])
            all_chunks.extend(chunks)

        ctx.chunks = all_chunks
        ctx.storage.write_chunks(all_chunks)
        return ctx
