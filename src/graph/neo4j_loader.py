"""
Phase 7: Neo4j loader.

Connects to a Neo4j instance (local Desktop/Docker via bolt://, or Neo4j
AuraDB via neo4j+s://, both accepted unchanged - the driver is scheme
agnostic) using credentials from .env, creates uniqueness constraints and
indexes, and idempotently loads Document/Chunk/Entity nodes plus HAS_CHUNK /
MENTIONS / ontology relationships via batched MERGE statements (safe to
re-run without creating duplicates). Also loads the Silver-tier
CandidateEntity/CANDIDATE_RELATIONSHIP subgraph, fully refreshed each run,
under labels retrieval never matches.

Writes go through session.execute_write() and reads through
session.execute_read() (managed transactions) rather than bare session.run(),
so the driver's built-in retry on transient errors (ServiceUnavailable,
SessionExpired - the errors Aura's rolling maintenance/leader elections
raise) applies to every query.
"""

from __future__ import annotations

import logging
import os
import time

from neo4j import GraphDatabase

from ontology.rdf.namespaces import CHUNK_NS, CORE_NS, DOCUMENT_NS, ENTITY_NS

logger = logging.getLogger("kg_local.neo4j_loader")

# Whitelist of relationship types we allow to be interpolated into Cypher
# (Neo4j does not support parameterized relationship types). This is a
# hardcoded, static mirror of the relationship types defined in
# ontology.yaml - it is NOT derived from ontology.yaml at call time, so it
# must be kept in sync by hand if the ontology's relationship types change.
ALLOWED_RELATIONSHIP_TYPES = {
    "USES",
    "DEPENDS_ON",
    "CONNECTS_TO",
    "OWNS",
    "CONTAINS",
    "IMPLEMENTS",
    "REFERENCES",
    "REFERS_TO",
    "ESCALATES_TO",
    "REQUIRES",
    "APPLIES_TO",
}

_CONSTRAINTS = [
    "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
    "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
    "CREATE CONSTRAINT candidate_entity_id IF NOT EXISTS FOR (e:CandidateEntity) REQUIRE e.id IS UNIQUE",
    # Required by neosemantics (n10s) for RDF import/export - every
    # :Resource-labeled (Gold-tier only) node gets a unique `uri`. See
    # docs/architecture/neo4j_n10s_setup.md.
    "CREATE CONSTRAINT n10s_unique_uri IF NOT EXISTS FOR (r:Resource) REQUIRE r.uri IS UNIQUE",
]

_BATCH_SIZE = 500

# Defensive upper bounds on graph expansion, applied regardless of what a
# (config-driven, not user-input-driven) caller passes in - keeps a
# misconfigured retrieval.graph_expansion_hops from turning into an
# unbounded-cost traversal.
_MAX_HOPS = 3
_MAX_NEIGHBOR_LIMIT = 100

# Seconds to wait for the initial connection/handshake to Neo4j before
# failing - the driver has no timeout by default.
_DEFAULT_CONNECTION_TIMEOUT_SECONDS = 10


class Neo4jLoader:
    def __init__(self, uri: str | None = None, user: str | None = None,
                 password: str | None = None, database: str | None = None,
                 connection_timeout: float = _DEFAULT_CONNECTION_TIMEOUT_SECONDS):
        self.uri = uri or os.environ["NEO4J_URI"]
        self.user = user or os.environ["NEO4J_USER"]
        self.password = password or os.environ["NEO4J_PASSWORD"]
        self.database = database or os.environ.get("NEO4J_DATABASE", "neo4j")
        self._driver = GraphDatabase.driver(
            self.uri, auth=(self.user, self.password), connection_timeout=connection_timeout
        )

    def close(self):
        self._driver.close()
        logger.info("graph_operation operation=close uri=%s", self.uri)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def verify_connectivity(self):
        self._driver.verify_connectivity()

    def connect_with_retry(self, attempts: int = 3, base_delay: float = 1.0) -> None:
        """Retries verify_connectivity() with exponential backoff. Runs
        before any session/transaction exists, so it isn't covered by the
        driver's own managed-transaction retry - this is the one place that
        needs an explicit retry loop."""
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                self.verify_connectivity()
                logger.info(
                    "graph_operation operation=connect uri=%s database=%s attempt=%d status=ok",
                    self.uri, self.database, attempt,
                )
                return
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "graph_operation operation=connect uri=%s attempt=%d status=retry error=%s",
                    self.uri, attempt, exc,
                )
                if attempt < attempts:
                    time.sleep(base_delay * (2 ** (attempt - 1)))
        logger.error(
            "graph_operation operation=connect uri=%s attempts=%d status=failed", self.uri, attempts
        )
        raise last_error

    def _run_batched(self, session, query: str, rows: list[dict], **extra_params) -> int:
        total = 0
        start = time.perf_counter()
        for i in range(0, len(rows), _BATCH_SIZE):
            batch = rows[i : i + _BATCH_SIZE]
            session.execute_write(
                lambda tx, q=query, b=batch, p=extra_params: tx.run(q, rows=b, **p).consume()
            )
            total += len(batch)
        logger.info(
            "graph_operation operation=write rows=%d duration_ms=%d",
            total, int((time.perf_counter() - start) * 1000),
        )
        return total

    def _run_read(self, session, query: str, **params):
        start = time.perf_counter()
        result = session.execute_read(lambda tx: list(tx.run(query, **params)))
        logger.info(
            "graph_operation operation=read rows=%d duration_ms=%d",
            len(result), int((time.perf_counter() - start) * 1000),
        )
        return result

    def create_constraints(self):
        with self._driver.session(database=self.database) as session:
            for statement in _CONSTRAINTS:
                session.execute_write(lambda tx, q=statement: tx.run(q).consume())
            self._init_rdf_config(session)
        logger.info("graph_operation operation=create_constraints count=%d", len(_CONSTRAINTS))

    def _init_rdf_config(self, session) -> None:
        """Registers the neosemantics (n10s) graph config and the core/kg
        namespace prefixes, so RDF export can reconstruct full IRIs from
        node labels. Best-effort: if the n10s.* procedures aren't found
        (plugin not installed - see docs/architecture/neo4j_n10s_setup.md),
        this logs a warning and returns rather than failing
        create_constraints() for everyone who hasn't done the one-time
        manual Desktop install yet."""
        try:
            session.execute_write(
                lambda tx: tx.run("CALL n10s.graphconfig.init({handleVocabUris: 'MAP'})").consume()
            )
            session.execute_write(
                lambda tx: tx.run(
                    "CALL n10s.nsprefixes.add('core', $ns)", ns=str(CORE_NS)
                ).consume()
            )
            session.execute_write(
                lambda tx: tx.run(
                    "CALL n10s.nsprefixes.add('kg', $ns)", ns=str(ENTITY_NS)
                ).consume()
            )
            logger.info("graph_operation operation=init_rdf_config status=ok")
        except Exception as exc:
            logger.warning(
                "graph_operation operation=init_rdf_config status=skipped error=%s "
                "(neosemantics plugin not installed? see docs/architecture/neo4j_n10s_setup.md)",
                exc,
            )

    def create_indexes(self, embedding_dimensions: int | None = None) -> None:
        """Idempotently ensures all required indexes exist. Safe to call at
        startup before any chunk has been loaded - if embedding_dimensions
        isn't known yet, the vector index is skipped here and created later
        (see create_vector_index(), still called from load_graph() once a
        chunk with an embedding is seen)."""
        if embedding_dimensions is None:
            logger.info("graph_operation operation=create_indexes status=skipped_no_dimensions")
            return
        with self._driver.session(database=self.database) as session:
            self.create_vector_index(session, embedding_dimensions)

    def _run_batched_unwrapped(self, session, query: str, rows: list[dict]):
        # Used for the very first write on a fresh session where nothing
        # else has run yet; kept identical to _run_batched, isolated for
        # clarity when reading create_constraints/_run_batched together.
        return self._run_batched(session, query, rows)

    def load_documents(self, session, documents: list[dict]) -> int:
        query = """
        UNWIND $rows AS row
        MERGE (d:Document {id: row.id})
        SET d.name = row.name,
            d.source_path = row.source_path,
            d.markdown_path = row.markdown_path,
            d.space_key = row.space_key,
            d.version = row.version,
            d.content_hash = row.content_hash,
            d.parent_page_id = row.parent_page_id,
            d.uri = $ns + row.id
        SET d:Resource
        """
        return self._run_batched(session, query, documents, ns=str(DOCUMENT_NS))

    def load_chunks(self, session, chunks: list[dict]) -> int:
        query = """
        UNWIND $rows AS row
        MERGE (c:Chunk {id: row.id})
        SET c.document = row.document,
            c.section_path = row.section_path,
            c.content = row.content,
            c.token_count = row.token_count,
            c.embedding = row.embedding,
            c.uri = $ns + row.id
        SET c:Resource
        """
        return self._run_batched(session, query, chunks, ns=str(CHUNK_NS))

    def create_vector_index(self, session, dimensions: int) -> None:
        """Idempotent - safe to call on every load_graph(). Only meaningful
        once chunks carry an `embedding` property (see load_chunks)."""
        session.execute_write(
            lambda tx: tx.run(
                """
                CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS
                FOR (c:Chunk) ON c.embedding
                OPTIONS {indexConfig: {
                    `vector.dimensions`: $dimensions,
                    `vector.similarity_function`: 'cosine'
                }}
                """,
                dimensions=dimensions,
            ).consume()
        )
        logger.info("graph_operation operation=create_vector_index dimensions=%d", dimensions)

    def load_entities(self, session, entities: list[dict]) -> int:
        query = """
        UNWIND $rows AS row
        MERGE (e:Entity {id: row.id})
        SET e.name = row.name,
            e.type = row.type,
            e.source_chunk = row.source_chunk,
            e.uri = $ns + row.id
        SET e:Resource
        """
        count = self._run_batched(session, query, entities, ns=str(ENTITY_NS))

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
            self._run_batched(session, label_query, [{"id": r["id"]} for r in rows])

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

    def load_page_hierarchy(self, session, rows: list[dict]) -> int:
        """Loads page-tree lineage/provenance as CHILD_OF_PAGE edges between
        :Document nodes. This is a brand-new relationship type never
        referenced by search_chunks/get_mentioned_entities/get_neighbors -
        those only ever match :Entity/:Chunk nodes and
        ALLOWED_RELATIONSHIP_TYPES, so CHILD_OF_PAGE is retrieval-blind by
        construction, the same governance pattern as :CandidateEntity."""
        query = """
        UNWIND $rows AS row
        MATCH (child:Document {id: row.child_id})
        MATCH (parent:Document {id: row.parent_id})
        MERGE (child)-[:CHILD_OF_PAGE]->(parent)
        """
        return self._run_batched(session, query, rows)

    def load_page_links(self, session, rows: list[dict]) -> int:
        """Loads MYDET's in-text decision-tree links as LEADS_TO edges
        between :Document nodes, with the triggering answer as an edge
        property. Same governance/retrieval-blind pattern as
        load_page_hierarchy: not in ALLOWED_RELATIONSHIP_TYPES, never
        gated by candidate review, never matched by get_neighbors (Entity-
        only). See get_linked_documents for the Document-level traversal
        counterpart to get_neighbors."""
        query = """
        UNWIND $rows AS row
        MATCH (source:Document {id: row.source_id})
        MATCH (target:Document {id: row.target_id})
        MERGE (source)-[r:LEADS_TO {answer_label: row.answer_label}]->(target)
        """
        return self._run_batched(session, query, rows)

    def clear_candidate_graph(self, session) -> None:
        """Fully clears the Silver-tier :CandidateEntity subgraph (and its
        relationships via DETACH DELETE) so each pipeline run's reload
        reflects the current approve/reject/merge state exactly, mirroring
        how the Silver JSON export is fully overwritten each run."""
        session.execute_write(lambda tx: tx.run("MATCH (e:CandidateEntity) DETACH DELETE e").consume())
        logger.info("graph_operation operation=clear_candidate_graph")

    def load_candidate_entities(self, session, entities: list[dict]) -> int:
        query = """
        UNWIND $rows AS row
        MERGE (e:CandidateEntity {id: row.id})
        SET e.name = row.name,
            e.type = row.type,
            e.source_chunk = row.source_chunk
        """
        return self._run_batched(session, query, entities)

    def load_candidate_relationships(self, session, entity_relationships: list[dict]) -> int:
        # A single generic relationship type keeps the candidate tier out of
        # ALLOWED_RELATIONSHIP_TYPES entirely - the real semantic type is
        # stored as a property, not interpolated into Cypher.
        query = """
        UNWIND $rows AS row
        MATCH (a:CandidateEntity {id: row.source})
        MATCH (b:CandidateEntity {id: row.target})
        MERGE (a)-[r:CANDIDATE_RELATIONSHIP]->(b)
        SET r.relationship_type = row.relationship,
            r.source_chunk = row.source_chunk
        """
        return self._run_batched(session, query, entity_relationships)

    def load_candidate_graph(self, graph: dict) -> dict:
        """Load a Silver-tier candidate graph JSON document (as produced by
        review.candidate_graph.build_candidate_graph()). Returns a stats
        dict. No document/chunk nodes - candidate graphs only ever carry
        entities and relationships."""
        stats = {}
        with self._driver.session(database=self.database) as session:
            self.clear_candidate_graph(session)
            stats["candidate_entities_loaded"] = self.load_candidate_entities(
                session, graph["nodes"]["entities"]
            )
            stats["candidate_relationships_loaded"] = self.load_candidate_relationships(
                session, graph["relationships"]["entity_relationships"]
            )
        return stats

    def search_chunks(self, session, query_vector: list[float], top_k: int) -> list[dict]:
        result = self._run_read(
            session,
            """
            CALL db.index.vector.queryNodes('chunk_embedding', $top_k, $query_vector)
            YIELD node, score
            MATCH (d:Document {id: node.document})
            RETURN node.id AS chunk_id, node.content AS content,
                   node.document AS document_id, d.name AS document_name, score
            ORDER BY score DESC
            """,
            top_k=top_k,
            query_vector=query_vector,
        )
        return [dict(record) for record in result]

    def get_mentioned_entities(self, session, chunk_ids: list[str]) -> list[dict]:
        result = self._run_read(
            session,
            """
            MATCH (c:Chunk)-[:MENTIONS]->(e:Entity)
            WHERE c.id IN $chunk_ids
            RETURN DISTINCT e.id AS entity_id, e.name AS name, e.type AS entity_type
            """,
            chunk_ids=chunk_ids,
        )
        return [dict(record) for record in result]

    def get_neighbors(self, session, entity_ids: list[str], hops: int, limit: int) -> dict:
        safe_hops = max(1, min(int(hops), _MAX_HOPS))
        safe_limit = max(1, min(int(limit), _MAX_NEIGHBOR_LIMIT))
        result = self._run_read(
            session,
            """
            MATCH (e:Entity)-[rels*1..%d]-(n:Entity)
            WHERE e.id IN $entity_ids AND NOT n.id IN $entity_ids
            RETURN DISTINCT n.id AS entity_id, n.name AS name, n.type AS entity_type,
                   e.name AS source_name,
                   [rel IN rels | type(rel)] AS relationship_types
            LIMIT $limit
            """
            % safe_hops,
            entity_ids=entity_ids,
            limit=safe_limit,
        )
        entities: dict[str, dict] = {}
        paths: list[dict] = []
        for record in result:
            row = dict(record)
            entities[row["entity_id"]] = {
                "entity_id": row["entity_id"],
                "name": row["name"],
                "entity_type": row["entity_type"],
            }
            paths.append(
                {
                    "source_name": row["source_name"],
                    "relationship_types": row["relationship_types"],
                    "target_name": row["name"],
                }
            )
        return {"entities": list(entities.values()), "paths": paths}

    def get_linked_documents(self, session, document_ids: list[str], hops: int, limit: int) -> dict:
        """Document-level counterpart to get_neighbors: forward-only
        traversal of LEADS_TO edges from the given documents (the pages a
        chunk came from) to the pages they lead to next. Forward-only
        (not undirected like get_neighbors) because retrieval wants "what
        happens next", not "how did we get here". Same defensive bounds
        as get_neighbors."""
        safe_hops = max(1, min(int(hops), _MAX_HOPS))
        safe_limit = max(1, min(int(limit), _MAX_NEIGHBOR_LIMIT))
        result = self._run_read(
            session,
            """
            MATCH (d:Document)-[rels:LEADS_TO*1..%d]->(n:Document)
            WHERE d.id IN $document_ids AND NOT n.id IN $document_ids
            RETURN DISTINCT n.id AS document_id, n.name AS name,
                   d.name AS source_name,
                   [rel IN rels | rel.answer_label] AS answer_labels
            LIMIT $limit
            """
            % safe_hops,
            document_ids=document_ids,
            limit=safe_limit,
        )
        documents: dict[str, dict] = {}
        paths: list[dict] = []
        for record in result:
            row = dict(record)
            documents[row["document_id"]] = {
                "document_id": row["document_id"],
                "name": row["name"],
            }
            paths.append(
                {
                    "source_name": row["source_name"],
                    "answer_labels": row["answer_labels"],
                    "target_name": row["name"],
                }
            )
        return {"documents": list(documents.values()), "paths": paths}

    def query_graph(self, cypher: str, params: dict | None = None) -> list[dict]:
        """Generic parameterized read-only escape hatch. Not used by any
        retrieval path today - callers are responsible for ensuring the
        Cypher they pass is read-only."""
        with self._driver.session(database=self.database) as session:
            result = self._run_read(session, cypher, **(params or {}))
            return [dict(record) for record in result]

    def load_graph(self, graph: dict) -> dict:
        """Load a full graph JSON document (as produced by graph_builder).
        Returns a stats dict of nodes/relationships loaded."""
        self.create_constraints()

        stats = {}
        with self._driver.session(database=self.database) as session:
            stats["documents_loaded"] = self.load_documents(session, graph["nodes"]["documents"])
            stats["chunks_loaded"] = self.load_chunks(session, graph["nodes"]["chunks"])

            embedded_chunk = next(
                (c for c in graph["nodes"]["chunks"] if c.get("embedding")), None
            )
            if embedded_chunk is not None:
                self.create_vector_index(session, len(embedded_chunk["embedding"]))

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
            stats["page_hierarchy_loaded"] = self.load_page_hierarchy(
                session, graph["relationships"].get("page_hierarchy", [])
            )
            stats["page_links_loaded"] = self.load_page_links(
                session, graph["relationships"].get("page_links", [])
            )

        stats["nodes_loaded"] = (
            stats["documents_loaded"] + stats["chunks_loaded"] + stats["entities_loaded"]
        )
        stats["relationships_loaded"] = (
            stats["has_chunk_loaded"]
            + stats["mentions_loaded"]
            + stats["entity_relationships_loaded"]
            + stats["page_hierarchy_loaded"]
            + stats["page_links_loaded"]
        )
        return stats
