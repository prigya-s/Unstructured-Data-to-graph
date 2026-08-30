"""
ExtractionProvider: the abstraction boundary for turning silver chunks into
candidate entities/relationships. Mirrors EmbeddingProvider/GraphProvider's
ABC + get_*_provider(config) factory convention. Method signatures match
extraction.entity_extractor.extract_entities()/
extraction.relationship_extractor.extract_relationships() exactly, so every
implementation is a drop-in replacement inside
pipeline/stages/entity_extraction_stage.py and relationship_extraction_stage.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class ExtractionProvider(ABC):
    @abstractmethod
    def extract_entities(self, chunks: list[dict], ontology: dict) -> tuple[list[dict], list[dict]]:
        """chunks: DocumentChunkRecord-shaped dicts. Returns (entities, mentions):
        entities: [{"id","name","type","source_chunk", ...}] deduplicated.
        mentions: [{"chunk_id","entity_id"}] one row per (chunk, entity) pair."""

    @abstractmethod
    def extract_relationships(
        self, chunks: list[dict], entities: list[dict], mentions: list[dict], ontology: dict
    ) -> list[dict]:
        """Returns [{"source","relationship","target","source_chunk", ...}]."""

    def get_class_proposals(self) -> list[dict]:
        """NO_FIT class proposals accumulated since the last call, then
        cleared - see review.candidate_builder.build_class_proposals().
        Default: no proposals. Only a provider that can flag "this doesn't
        fit any existing type" (today, just OllamaExtractionProvider)
        overrides this."""
        return []
