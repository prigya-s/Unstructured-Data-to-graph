"""
ExtractionStage: bronze raw docs -> extract.docling_parser.convert_to_markdown
(unmodified) -> StorageProvider.write_markdown() (silver).

Reads its input from StorageProvider rather than trusting ctx.documents to
have been populated by a prior stage in the same process - this is what
makes the stage callable standalone as an isolated Databricks Workflow task.
"""

from __future__ import annotations

import logging

from extract import docling_parser
from pipeline.context import PipelineContext

from .base import PipelineStage

logger = logging.getLogger("kg_local.extraction_stage")


class ExtractionStage(PipelineStage):
    name = "extraction"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        documents = ctx.storage.read_documents()
        markdown_documents = []
        for doc_ref in documents:
            file_path = ctx.document_source.read_document(doc_ref)
            try:
                markdown = docling_parser.convert_to_markdown(file_path)
            except Exception:
                logger.exception("Failed to extract %s", file_path)
                continue

            markdown_documents.append(
                {
                    "document_id": doc_ref["document_id"],
                    "document_name": doc_ref["document_name"],
                    "source_path": doc_ref["source_path"],
                    "markdown_path": "",
                    "markdown": markdown,
                }
            )

        ctx.markdown_documents = markdown_documents
        ctx.storage.write_markdown(markdown_documents)
        return ctx
