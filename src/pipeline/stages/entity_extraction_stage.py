"""
EntityExtractionStage: silver chunks + ontology schema ->
ctx.extraction_provider.extract_entities() -> StorageProvider.write_entities()
(gold). Provider defaults to OntologyRulesExtractionProvider (unmodified
rule-based behavior); ai.mode/extraction.provider can swap in
OllamaExtractionProvider without touching this stage.
"""

from __future__ import annotations

from pipeline.context import PipelineContext

from .base import PipelineStage


class EntityExtractionStage(PipelineStage):
    name = "entity_extraction"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        chunks = ctx.storage.read_chunks()
        entities, mentions = ctx.extraction_provider.extract_entities(chunks, ctx.ontology_schema)
        ctx.entities = entities
        ctx.mentions = mentions
        ctx.storage.write_entities(entities, mentions)
        return ctx
