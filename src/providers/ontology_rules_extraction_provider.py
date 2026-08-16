"""
OntologyRulesExtractionProvider: the default ExtractionProvider - delegates
straight to the existing deterministic, offline extraction.entity_extractor/
extraction.relationship_extractor modules. Zero logic change from the
pre-provider behavior; this class exists only to put that behavior behind
the ExtractionProvider seam alongside the new Ollama/Azure implementations.
"""

from __future__ import annotations

from extraction import entity_extractor, relationship_extractor
from providers.extraction_provider import ExtractionProvider


class OntologyRulesExtractionProvider(ExtractionProvider):
    def extract_entities(self, chunks: list[dict], ontology: dict) -> tuple[list[dict], list[dict]]:
        return entity_extractor.extract_entities(chunks, ontology)

    def extract_relationships(
        self, chunks: list[dict], entities: list[dict], mentions: list[dict], ontology: dict
    ) -> list[dict]:
        return relationship_extractor.extract_relationships(chunks, entities, mentions, ontology)
