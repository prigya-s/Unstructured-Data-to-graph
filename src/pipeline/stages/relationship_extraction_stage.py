"""
RelationshipExtractionStage: gold entities + silver chunks + ontology schema
-> ctx.extraction_provider.extract_relationships() ->
StorageProvider.write_relationships() (gold). Provider defaults to
OntologyRulesExtractionProvider (unmodified rule-based behavior);
ai.mode/extraction.provider can swap in OllamaExtractionProvider without
touching this stage.
"""

from __future__ import annotations

from pipeline.context import PipelineContext

from .base import PipelineStage


class RelationshipExtractionStage(PipelineStage):
    name = "relationship_extraction"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        chunks = ctx.storage.read_chunks()
        entities, mentions = ctx.storage.read_entities()
        relationships = ctx.extraction_provider.extract_relationships(
            chunks, entities, mentions, ctx.ontology_schema
        )
        ctx.relationships = relationships
        ctx.storage.write_relationships(relationships)
        return ctx
