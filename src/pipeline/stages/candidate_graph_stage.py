"""
CandidateGraphStage: ApprovalProvider -> review.candidate_graph.build_candidate_graph()
-> StorageProvider.write_candidate_graph() (silver) +
GraphProvider.build_candidate_graph() (silver, written into the same graph
database under distinct :CandidateEntity/:CANDIDATE_RELATIONSHIP labels so
retrieval - which only ever matches :Entity/:Chunk/:Document and the
whitelisted relationship types - stays blind to it).

Runs immediately after ApprovalStage, since it depends on the candidates
ApprovalStage just created/refreshed.
"""

from __future__ import annotations

from pipeline.context import PipelineContext
from review.candidate_graph import build_candidate_graph

from .base import PipelineStage


class CandidateGraphStage(PipelineStage):
    name = "candidate_graph"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        candidate_graph = build_candidate_graph(ctx.approval_provider)
        ctx.storage.write_candidate_graph(candidate_graph)
        ctx.graph_provider.build_candidate_graph(candidate_graph)
        ctx.candidate_graph = candidate_graph
        return ctx
