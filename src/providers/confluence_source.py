"""
ConfluenceSource: placeholder DocumentSource backed by a Confluence space.

Not implemented yet. Select via document_source.provider: confluence in
config.yaml once implemented - list_documents()/read_document() need a
Confluence REST API-backed implementation (page listing + export-to-file),
using document_source.confluence.base_url_env/token_env/space_key from
AppConfig.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from config.app_config import AppConfig

from .document_source import DocumentSource


class ConfluenceSource(DocumentSource):
    _MSG: ClassVar[str] = (
        "Confluence document source is not yet implemented. Set "
        "document_source.provider: local_folder in config.yaml to use a "
        "local folder, or implement this class against the Confluence API."
    )

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def list_documents(self) -> list[dict]:
        raise NotImplementedError(self._MSG)

    def read_document(self, doc_ref: dict) -> Path:
        raise NotImplementedError(self._MSG)
