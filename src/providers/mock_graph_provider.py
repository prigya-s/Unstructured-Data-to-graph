"""
MockGraphProvider: pure in-memory GraphProvider. Select via
graph.provider: mock in config.yaml (or pass directly in tests) to run the
app/pipeline with zero live Neo4j - useful for local development without
Desktop/Docker running and for tests that shouldn't depend on a real
database.

Mirrors the real providers' semantics closely enough to be a faithful
stand-in: Gold (:Entity-equivalent) and Silver (:CandidateEntity-equivalent)
data are kept in separate dicts, build_candidate_graph() fully replaces the
candidate set each call (matching the real DETACH DELETE + reload
behavior), and get_neighbors clamps hops/limit the same way
graph.neo4j_loader does.
"""

from __future__ import annotations

from config.app_config import AppConfig

from .graph_provider import GraphProvider

_MAX_HOPS = 3
_MAX_NEIGHBOR_LIMIT = 100


class MockGraphProvider(GraphProvider):
    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config
        self.connected = False
        self.constraints_created = False
        self.indexes_created = False
        self.entities: dict[str, dict] = {}
        self.chunks: dict[str, dict] = {}
        self.relationships: list[dict] = []
        self.documents: dict[str, dict] = {}
        self.page_links: list[dict] = []
        self.candidate_entities: dict[str, dict] = {}
        self.candidate_relationships: list[dict] = []
        self.closed = False

    def connect(self) -> None:
        self.connected = True

    def create_constraints(self) -> None:
        self.constraints_created = True

    def create_indexes(self) -> None:
        self.indexes_created = True

    def save_entity(self, entities: list[dict]) -> int:
        for entity in entities:
            self.entities[entity["id"]] = entity
        return len(entities)

    def save_relationship(self, relationships: list[dict]) -> int:
        self.relationships.extend(relationships)
        return len(relationships)

    def save_chunk(self, chunks: list[dict]) -> int:
        for chunk in chunks:
            self.chunks[chunk["id"]] = chunk
        return len(chunks)

    def build_candidate_graph(self, graph: dict) -> dict:
        self.candidate_entities = {e["id"]: e for e in graph["nodes"]["entities"]}
        self.candidate_relationships = list(graph["relationships"]["entity_relationships"])
        return {
            "candidate_entities_loaded": len(self.candidate_entities),
            "candidate_relationships_loaded": len(self.candidate_relationships),
        }

    def build_production_graph(self, graph: dict) -> dict:
        self.create_constraints()
        self.create_indexes()
        self.documents = {d["id"]: d for d in graph["nodes"]["documents"]}
        self.save_chunk(graph["nodes"]["chunks"])
        self.save_entity(graph["nodes"]["entities"])
        self.save_relationship(graph["relationships"]["entity_relationships"])
        self.page_links = list(graph["relationships"].get("page_links", []))
        return {
            "nodes_loaded": len(graph["nodes"]["documents"])
            + len(graph["nodes"]["chunks"])
            + len(graph["nodes"]["entities"]),
            "relationships_loaded": len(graph["relationships"]["has_chunk"])
            + len(graph["relationships"]["mentions"])
            + len(graph["relationships"]["entity_relationships"])
            + len(graph["relationships"].get("page_hierarchy", []))
            + len(self.page_links),
        }

    def search_chunks(self, query_vector: list[float], top_k: int) -> list[dict]:
        results = [
            {
                "chunk_id": chunk["id"],
                "content": chunk.get("content"),
                "document_id": chunk.get("document"),
                "score": 1.0,
            }
            for chunk in self.chunks.values()
        ]
        return results[:top_k]

    def get_mentioned_entities(self, chunk_ids: list[str]) -> list[dict]:
        chunk_id_set = set(chunk_ids)
        return [
            {"entity_id": entity["id"], "name": entity["name"], "entity_type": entity["type"]}
            for entity in self.entities.values()
            if entity.get("source_chunk") in chunk_id_set
        ]

    def get_neighbors(self, entity_ids: list[str], hops: int, limit: int) -> dict:
        safe_hops = max(1, min(int(hops), _MAX_HOPS))
        safe_limit = max(1, min(int(limit), _MAX_NEIGHBOR_LIMIT))
        seed_ids = set(entity_ids)
        frontier = set(seed_ids)
        visited = set(seed_ids)
        entities: dict[str, dict] = {}
        paths: list[dict] = []

        for _ in range(safe_hops):
            next_frontier = set()
            for rel in self.relationships:
                source, target = rel["source"], rel["target"]
                for a, b in ((source, target), (target, source)):
                    if a in frontier and b not in visited:
                        target_entity = self.entities.get(b)
                        source_entity = self.entities.get(a)
                        if target_entity is None or source_entity is None:
                            continue
                        entities[b] = {
                            "entity_id": target_entity["id"],
                            "name": target_entity["name"],
                            "entity_type": target_entity["type"],
                        }
                        paths.append(
                            {
                                "source_name": source_entity["name"],
                                "relationship_types": [rel["relationship"]],
                                "target_name": target_entity["name"],
                            }
                        )
                        next_frontier.add(b)
                        visited.add(b)
                        if len(entities) >= safe_limit:
                            break
                if len(entities) >= safe_limit:
                    break
            frontier = next_frontier
            if not frontier or len(entities) >= safe_limit:
                break

        return {
            "entities": list(entities.values())[:safe_limit],
            "paths": paths[:safe_limit],
        }

    def get_linked_documents(self, document_ids: list[str], hops: int, limit: int) -> dict:
        safe_hops = max(1, min(int(hops), _MAX_HOPS))
        safe_limit = max(1, min(int(limit), _MAX_NEIGHBOR_LIMIT))
        seed_ids = set(document_ids)
        frontier = set(seed_ids)
        visited = set(seed_ids)
        documents: dict[str, dict] = {}
        paths: list[dict] = []

        for _ in range(safe_hops):
            next_frontier = set()
            for link in self.page_links:
                source, target = link["source_id"], link["target_id"]
                if source in frontier and target not in visited:
                    source_doc = self.documents.get(source)
                    target_doc = self.documents.get(target)
                    if source_doc is None or target_doc is None:
                        continue
                    documents[target] = {
                        "document_id": target_doc["id"],
                        "name": target_doc["name"],
                    }
                    paths.append(
                        {
                            "source_name": source_doc["name"],
                            "answer_labels": [link.get("answer_label")],
                            "target_name": target_doc["name"],
                        }
                    )
                    next_frontier.add(target)
                    visited.add(target)
                    if len(documents) >= safe_limit:
                        break
            frontier = next_frontier
            if not frontier or len(documents) >= safe_limit:
                break

        return {
            "documents": list(documents.values())[:safe_limit],
            "paths": paths[:safe_limit],
        }

    def query_graph(self, cypher: str, params: dict | None = None) -> list[dict]:
        raise NotImplementedError(
            "MockGraphProvider does not execute arbitrary Cypher; use the "
            "named methods (save_entity, get_neighbors, etc.) instead."
        )

    def close(self) -> None:
        self.closed = True
