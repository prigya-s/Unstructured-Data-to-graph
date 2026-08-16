"""
AzureOpenAIExtractionProvider: placeholder ExtractionProvider backed by an
Azure OpenAI chat deployment.

Not implemented yet. Select via extraction.provider: ontology_rules (the
deterministic default) or extraction.provider: ollama (local Qwen3 14B) in
config.yaml until this is implemented - list of allowed types/business logic
in the extraction stages does not change once it is.
"""

from __future__ import annotations

from typing import ClassVar

from config.app_config import AppConfig
from providers.extraction_provider import ExtractionProvider


class AzureOpenAIExtractionProvider(ExtractionProvider):
    _MSG: ClassVar[str] = (
        "Azure OpenAI extraction provider is not yet implemented. Set "
        "extraction.provider: ontology_rules (rule-based, default) or "
        "extraction.provider: ollama (local Qwen3 14B) in config.yaml, or "
        "implement this class against an Azure OpenAI chat deployment."
    )

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def extract_entities(self, chunks: list[dict], ontology: dict) -> tuple[list[dict], list[dict]]:
        raise NotImplementedError(self._MSG)

    def extract_relationships(
        self, chunks: list[dict], entities: list[dict], mentions: list[dict], ontology: dict
    ) -> list[dict]:
        raise NotImplementedError(self._MSG)
