"""
IngestionStage: DocumentSource.list_documents() -> StorageProvider.write_documents() (bronze).
"""

from __future__ import annotations

from datetime import datetime, timezone

from pipeline.context import PipelineContext

from .base import PipelineStage


class IngestionStage(PipelineStage):
    name = "ingestion"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        ingested_at = datetime.now(timezone.utc).isoformat()
        documents = [
            {**doc_ref, "ingested_at": ingested_at}
            for doc_ref in ctx.document_source.list_documents()
        ]
        ctx.documents = documents
        ctx.storage.write_documents(documents)
        return ctx
