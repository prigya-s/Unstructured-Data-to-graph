"""
EntityExtractionStage: silver chunks + ontology schema ->
extraction.entity_extractor.extract_entities() (unmodified) ->
StorageProvider.write_entities() (gold).
"""

from __future__ import annotations

from extraction import entity_extractor
from pipeline.context import PipelineContext

from .base import PipelineStage


class EntityExtractionStage(PipelineStage):
    name = "entity_extraction"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        chunks = ctx.storage.read_chunks()
        entities, mentions = entity_extractor.extract_entities(chunks, ctx.ontology_schema)
        ctx.entities = entities
        ctx.mentions = mentions
        ctx.storage.write_entities(entities, mentions)
        return ctx
