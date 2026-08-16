"""
GraphStage: silver markdown/chunks + gold mentions + OntologyProvider's
approved view -> graph.graph_builder.build_graph() (unmodified) ->
StorageProvider.write_graph_export() (gold) +
GraphProvider.build_production_graph() (Neo4j/Neo4j Aura/Cosmos).

Runs as its own process (main.py publish-graph), so it reads its documents/
chunks/mentions back from StorageProvider rather than relying on in-memory
ctx state from the ingest run. This is the only live path from approved
concepts to Neo4j - it goes through GraphProvider/config routing rather than
constructing a Neo4jLoader directly (review.publisher used to have its own
publish_graph() that did that; it had no callers and was removed).
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

        embedding_by_chunk_id = {
            record["chunk_id"]: record["embedding_vector"]
            for record in ctx.storage.read_embeddings()
        }
        chunks = [
            {**chunk, "embedding": embedding_by_chunk_id.get(chunk["chunk_id"])}
            for chunk in chunks
        ]

        entities, mentions, relationships = ctx.ontology_provider.load_for_graph(
            ctx.approval_provider, all_mentions
        )
        if not entities:
            raise ValueError("No approved concepts found. Review and approve candidates first.")

        graph_export = graph_builder.build_graph(documents, chunks, entities, mentions, relationships)
        ctx.storage.write_graph_export(graph_export)
        ctx.graph_export = graph_export

        ctx.publish_stats = ctx.graph_provider.build_production_graph(graph_export)
        return ctx
