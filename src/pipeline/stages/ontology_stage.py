"""
OntologyStage: ApprovalProvider -> OntologyProvider.generate() ->
StorageProvider.write_ontology() + write_approved_entities() +
write_approved_relationships() (gold).

Runs as its own process (main.py publish-ontology) - it only depends on the
ApprovalProvider, not on any in-memory state from earlier stages.
"""

from __future__ import annotations

from pipeline.context import PipelineContext

from .base import PipelineStage


class OntologyStage(PipelineStage):
    name = "ontology"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        ontology_result = ctx.ontology_provider.generate(ctx.approval_provider)
        ctx.ontology_result = ontology_result
        ctx.storage.write_ontology(ontology_result)
        ctx.storage.write_approved_entities(ontology_result["entities"])
        ctx.storage.write_approved_relationships(ontology_result["relationships"])
        return ctx
