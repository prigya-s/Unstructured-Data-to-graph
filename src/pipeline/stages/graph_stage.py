"""
GraphStage: silver markdown/chunks + gold mentions + OntologyProvider's
approved view -> graph.graph_builder.build_graph() (unmodified) ->
StorageProvider.write_graph_export() (gold) + GraphProvider.publish()
(Neo4j/Cosmos).

Runs as its own process (main.py publish-graph), so it reads its documents/
chunks/mentions back from StorageProvider rather than relying on in-memory
ctx state from the ingest run. Deliberately does not call
review.publisher.publish_graph(): that function constructs its own
Neo4jLoader() with no arguments (reading NEO4J_* from os.environ directly),
which would bypass GraphProvider/config routing entirely. The "no approved
concepts" guard it applies is reproduced here for the same reason.
"""

from __future__ import annotations

from graph import graph_builder
from pipeline.context import PipelineContext

from .base import PipelineStage


class GraphStage(PipelineStage):
    name = "graph"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        documents = ctx.storage.read_markdown()
        chunks = ctx.storage.read_chunks()
        _, all_mentions = ctx.storage.read_entities()

        entities, mentions, relationships = ctx.ontology_provider.load_for_graph(
            ctx.approval_provider, all_mentions
        )
        if not entities:
            raise ValueError("No approved concepts found. Review and approve candidates first.")

        graph_export = graph_builder.build_graph(documents, chunks, entities, mentions, relationships)
        ctx.storage.write_graph_export(graph_export)
        ctx.graph_export = graph_export

        ctx.publish_stats = ctx.graph_provider.publish(graph_export)
        return ctx
