"""
ApprovalStage: gold entities/mentions/relationships + silver chunks ->
review.candidate_builder.build_candidates() (unmodified) -> ApprovalProvider.

build_candidates() persists CandidateEntity/CandidateRelationship rows
directly via the ApprovalProvider it's given - there is no separate
StorageProvider write here.
"""

from __future__ import annotations

from pipeline.context import PipelineContext
from review.candidate_builder import build_candidates

from .base import PipelineStage


class ApprovalStage(PipelineStage):
    name = "approval"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        entities, mentions = ctx.storage.read_entities()
        relationships = ctx.storage.read_relationships()
        chunks = ctx.storage.read_chunks()
        entities_saved, relationships_saved = build_candidates(
            entities, mentions, relationships, chunks, ctx.approval_provider
        )
        ctx.entities_saved = entities_saved
        ctx.relationships_saved = relationships_saved
        return ctx
