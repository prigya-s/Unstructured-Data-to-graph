"""
Phase 7: Neo4j loader.

Connects to a local Neo4j instance using credentials from .env, creates
uniqueness constraints, and idempotently loads Document/Chunk/Entity
nodes plus HAS_CHUNK / MENTIONS / ontology relationships via batched
MERGE statements (safe to re-run without creating duplicates).
"""

from __future__ import annotations

import logging
import os

from neo4j import GraphDatabase

logger = logging.getLogger("kg_local.neo4j_loader")

# Whitelist of relationship types we allow to be interpolated into Cypher
# (Neo4j does not support parameterized relationship types). This list is
# sourced from ontology.yaml at call time, not from free-form user input.
ALLOWED_RELATIONSHIP_TYPES = {
    "USES",
    "DEPENDS_ON",
    "CONNECTS_TO",
    "OWNS",
    "CONTAINS",
    "IMPLEMENTS",
    "REFERENCES",
}

_CONSTRAINTS = [
    "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
    "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
]

_BATCH_SIZE = 500


class Neo4jLoader:
    def __init__(self, uri: str | None = None, user: str | None = None,
                 password: str | None = None, database: str | None = None):
        self.uri = uri or os.environ["NEO4J_URI"]
        self.user = user or os.environ["NEO4J_USER"]
        self.password = password or os.environ["NEO4J_PASSWORD"]
        self.database = database or os.environ.get("NEO4J_DATABASE", "neo4j")
        self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

    def close(self):
        self._driver.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def verify_connectivity(self):
        self._driver.verify_connectivity()

    def create_constraints(self):
        with self._driver.session(database=self.database) as session:
            for statement in _CONSTRAINTS:
                session.run(statement)
        logger.info("Constraints ensured (document_id, chunk_id, entity_id)")

    def _run_batched(self, session, query: str, rows: list[dict]):
        total = 0
        for i in range(0, len(rows), _BATCH_SIZE):
            batch = rows[i : i + _BATCH_SIZE]
            session.run(query, rows=batch)
            total += len(batch)
        return total

    def load_documents(self, session, documents: list[dict]) -> int:
        query = """
        UNWIND $rows AS row
        MERGE (d:Document {id: row.id})
        SET d.name = row.name,
            d.source_path = row.source_path,
            d.markdown_path = row.markdown_path
        """
        return self._run_batched(session, query, documents)

    def load_chunks(self, session, chunks: list[dict]) -> int:
        query = """
        UNWIND $rows AS row
        MERGE (c:Chunk {id: row.id})
        SET c.document = row.document,
            c.section_path = row.section_path,
            c.content = row.content,
            c.token_count = row.token_count
        """
        return self._run_batched(session, query, chunks)

    def load_entities(self, session, entities: list[dict]) -> int:
        query = """
        UNWIND $rows AS row
        MERGE (e:Entity {id: row.id})
        SET e.name = row.name,
            e.type = row.type,
            e.source_chunk = row.source_chunk
        """
        count = self._run_batched(session, query, entities)

        # Add the ontology type as a secondary label for richer visual
        # grouping in Neo4j Browser (e.g. :Entity:Service). APOC-free.
        by_type: dict[str, list[dict]] = {}
        for entity in entities:
            by_type.setdefault(entity["type"], []).append(entity)

        for entity_type, rows in by_type.items():
            safe_label = "".join(ch for ch in entity_type if ch.isalnum() or ch == "_")
            if not safe_label:
                continue
            label_query = f"""
            UNWIND $rows AS row
            MATCH (e:Entity {{id: row.id}})
            SET e:{safe_label}
            """
            session.run(label_query, rows=[{"id": r["id"]} for r in rows])

        return count

    def load_has_chunk(self, session, has_chunk: list[dict]) -> int:
        query = """
        UNWIND $rows AS row
        MATCH (d:Document {id: row.document_id})
        MATCH (c:Chunk {id: row.chunk_id})
        MERGE (d)-[:HAS_CHUNK]->(c)
        """
        return self._run_batched(session, query, has_chunk)

    def load_mentions(self, session, mentions: list[dict]) -> int:
        query = """
        UNWIND $rows AS row
        MATCH (c:Chunk {id: row.chunk_id})
        MATCH (e:Entity {id: row.entity_id})
        MERGE (c)-[:MENTIONS]->(e)
        """
        return self._run_batched(session, query, mentions)

    def load_entity_relationships(self, session, entity_relationships: list[dict]) -> int:
        by_type: dict[str, list[dict]] = {}
        for rel in entity_relationships:
            rel_type = rel["relationship"]
            if rel_type not in ALLOWED_RELATIONSHIP_TYPES:
                logger.warning("Skipping unknown relationship type: %s", rel_type)
                continue
            by_type.setdefault(rel_type, []).append(rel)

        total = 0
        for rel_type, rows in by_type.items():
            query = f"""
            UNWIND $rows AS row
            MATCH (a:Entity {{id: row.source}})
            MATCH (b:Entity {{id: row.target}})
            MERGE (a)-[r:{rel_type}]->(b)
            SET r.source_chunk = row.source_chunk
            """
            total += self._run_batched(session, query, rows)
        return total

    def load_graph(self, graph: dict) -> dict:
        """Load a full graph JSON document (as produced by graph_builder).
        Returns a stats dict of nodes/relationships loaded."""
        self.create_constraints()

        stats = {}
        with self._driver.session(database=self.database) as session:
            stats["documents_loaded"] = self.load_documents(session, graph["nodes"]["documents"])
            stats["chunks_loaded"] = self.load_chunks(session, graph["nodes"]["chunks"])
            stats["entities_loaded"] = self.load_entities(session, graph["nodes"]["entities"])
            stats["has_chunk_loaded"] = self.load_has_chunk(
                session, graph["relationships"]["has_chunk"]
            )
            stats["mentions_loaded"] = self.load_mentions(
                session, graph["relationships"]["mentions"]
            )
            stats["entity_relationships_loaded"] = self.load_entity_relationships(
                session, graph["relationships"]["entity_relationships"]
            )

        stats["nodes_loaded"] = (
            stats["documents_loaded"] + stats["chunks_loaded"] + stats["entities_loaded"]
        )
        stats["relationships_loaded"] = (
            stats["has_chunk_loaded"]
            + stats["mentions_loaded"]
            + stats["entity_relationships_loaded"]
        )
        return stats
