"""
LocalFolderSource: DocumentSource backed by a local folder. Thin wrapper
around the existing, unmodified extract.docling_parser.discover_documents -
it does not reimplement file discovery.
"""

from __future__ import annotations

from pathlib import Path

from extract import docling_parser

from .document_source import DocumentSource


class LocalFolderSource(DocumentSource):
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def list_documents(self) -> list[dict]:
        return [
            {
                "document_id": file_path.stem,
                "document_name": file_path.name,
                "source_path": str(file_path),
            }
            for file_path in docling_parser.discover_documents(self.path)
        ]

    def read_document(self, doc_ref: dict) -> Path:
        return Path(doc_ref["source_path"])
