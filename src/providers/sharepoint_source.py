"""
SharePointSource: placeholder DocumentSource backed by a SharePoint
document library.

Not implemented yet. Select via document_source.provider: sharepoint in
config.yaml once implemented - list_documents()/read_document() need a
Microsoft Graph API-backed implementation (drive item listing + download).
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from config.app_config import AppConfig

from .document_source import DocumentSource


class SharePointSource(DocumentSource):
    _MSG: ClassVar[str] = (
        "SharePoint document source is not yet implemented. Set "
        "document_source.provider: local_folder in config.yaml to use a "
        "local folder, or implement this class against the Microsoft Graph API."
    )

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def list_documents(self) -> list[dict]:
        raise NotImplementedError(self._MSG)

    def read_document(self, doc_ref: dict) -> Path:
        raise NotImplementedError(self._MSG)
