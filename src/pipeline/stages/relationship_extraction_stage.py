"""
RelationshipExtractionStage: gold entities + silver chunks + ontology schema
-> extraction.relationship_extractor.extract_relationships() (unmodified) ->
StorageProvider.write_relationships() (gold).
"""

from __future__ import annotations

from extraction import relationship_extractor
from pipeline.context import PipelineContext

from .base import PipelineStage


class RelationshipExtractionStage(PipelineStage):
    name = "relationship_extraction"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        chunks = ctx.storage.read_chunks()
        entities, mentions = ctx.storage.read_entities()
        relationships = relationship_extractor.extract_relationships(
            chunks, entities, mentions, ctx.ontology_schema
        )
        ctx.relationships = relationships
        ctx.storage.write_relationships(relationships)
        return ctx
