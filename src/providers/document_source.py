"""
DocumentSource: the abstraction boundary between the pipeline and wherever
source documents live. list_documents() returns lightweight references;
read_document() resolves one reference to a local file path that
extract.docling_parser.convert_to_markdown() (unmodified) can read.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class DocumentSource(ABC):
    @abstractmethod
    def list_documents(self) -> list[dict]:
        """Return [{"document_id", "document_name", "source_path"}] for every
        document available from this source."""

    @abstractmethod
    def read_document(self, doc_ref: dict) -> Path:
        """Resolve a reference from list_documents() to a local file path
        (downloading/caching first if the source is remote)."""
