# Migration Assessment: Local → Databricks

## Summary

Before this refactor, every pipeline stage in `main.py` talked directly to
hardcoded local paths, a local `docs/` folder, and `.env`-based Neo4j
credentials. Moving to Databricks would have meant rewriting each stage's
I/O by hand.

After this refactor, each stage talks only to a provider interface
(`StorageProvider`, `DocumentSource`, `EmbeddingProvider`, `ApprovalProvider`,
`OntologyProvider`, `GraphProvider`). Switching environments is a matter of
changing `config.yaml` and implementing the handful of provider classes that
are currently stubs. **No business logic changed** - `docling_parser.py`,
`semantic_chunker.py`, `entity_extractor.py`, `relationship_extractor.py`,
`graph_builder.py`, `neo4j_loader.py`, and the entire `review/` package keep
their exact pre-refactor internals (verified: zero diff to any function or
class body in those modules).

## Target Architecture Coverage

| Target box | Status | Notes |
|---|---|---|
| Document ingestion (local folder) | **Fully aligned** | `LocalFolderSource` wraps `docling_parser.discover_documents`/`convert_to_markdown` unmodified. |
| Document ingestion (Confluence/SharePoint) | **Stub** | `ConfluenceSource`/`SharePointSource` raise `NotImplementedError`; swap is a config change once implemented. |
| Bronze/Silver/Gold storage (local disk) | **Fully aligned** | `LocalStorageProvider` implements the full `StorageProvider` contract against `lakehouse/bronze\|silver\|gold/`. |
| Bronze/Silver/Gold storage (Databricks Volumes) | **Fully aligned** | `DatabricksVolumesProvider` is a `LocalStorageProvider` subclass - a mounted UC Volume is a POSIX path, so no Volumes-specific I/O code exists or is needed. Selecting it is `storage.provider: databricks_volumes` + a Volume-mounted `storage.root`. |
| Bronze/Silver/Gold storage (Unity Catalog / Delta) | **Implemented, not yet run against a live Warehouse** | `UnityCatalogProvider` delegates every method to the schema-driven `DeltaSqlTableStore`/`BlobStore` (`providers/_delta_sql.py`), generated from `contracts.schemas.TABLE_REGISTRY` - no per-table SQL is hand-written. See `docs/architecture/review_board_assessment.md`. |
| Semantic chunking | **Fully aligned** | `ChunkingStage` calls `semantic_chunker.chunk_markdown` unmodified. |
| Embeddings | **Documented no-op locally; real implementation for Databricks** *(as of this review; `OllamaEmbeddingProvider` was added afterward and is now the local default - see `graphrag_retrieval.md`)* | `LocalEmbeddingProvider` is an intentional pass-through (`embedding_vector: null`) - there is no embedding-generation logic to preserve locally. `DatabricksEmbeddingProvider` calls a Model Serving `/invocations` endpoint via stdlib `urllib`, config-driven via `embedding.databricks.*`. |
| Entity / relationship extraction | **Fully aligned** | `EntityExtractionStage`/`RelationshipExtractionStage` call `entity_extractor`/`relationship_extractor` unmodified. |
| Business review & approval (Streamlit) | **Fully aligned locally; real implementation for OntoBricks** | `ApprovalProvider` is `review.repository.OntologyRepository` - unchanged ABC, now reached via `providers.get_approval_provider(config)`. `FutureOntoBricksRepository` upserts via the same `DeltaSqlTableStore.merge_rows()` (atomic `MERGE INTO`), resolving `LocalOntologyRepository`'s documented cross-process write-safety limitation once selected. |
| Ontology generation | **Fully aligned** | `OntologyStage` calls `review.publisher.publish_ontology`/`ontology_generator` unmodified via `LocalOntologyProvider`. |
| Graph load (Neo4j) | **Fully aligned** | `Neo4jGraphProvider` wraps `graph.neo4j_loader.Neo4jLoader` unmodified; only *which* env var names supply credentials is now config-driven. |
| Graph load (Cosmos DB) | **Stub** | `CosmosGraphProvider` raises `NotImplementedError`. |

## Remaining Migration Effort

See `docs/architecture/review_board_assessment.md` for the full
component-by-component effort rating (Document Ingestion, Storage, Docling
Extraction, Chunking, Embedding Generation, Entity Extraction, Relationship
Extraction, Approval Workflow, Ontology Generation, Neo4j Graph Creation)
and the refactors performed to drive each toward CONFIGURATION ONLY.
Only `ConfluenceSource`/`SharePointSource`/`CosmosGraphProvider` remain
genuine stubs - net-new connector integrations outside the scope of the
"run the existing pipeline on Databricks" migration goal (which only
requires a Volume-mounted `LocalFolderSource` and Neo4j on managed
infrastructure, both already working).

## Migration Risks and Mitigations (carried over from the pre-refactor design review)

| Risk | Mitigation |
|---|---|
| Hidden path coupling | All `Path` construction from a root now lives in exactly one place: `LocalStorageProvider`. No stage, provider factory, or `main.py` function computes a path from `PROJECT_ROOT` anymore. |
| `.env`/plaintext secrets | `Neo4jGraphProvider` reads *which* env var names to use from config; the actual secret values still come from `os.environ`, so a Databricks deployment only changes how those env vars are populated (secret-scope-backed), not the code reading them. |
| Silent business-logic drift | Out of scope by construction - the refactor only touched call sites, config, and provider glue. Verified via static diff (see Verification below). |
| Data loss on the `output/` → `lakehouse/` restructure | Accepted: `output/` was local dev/demo data, not migrated. New data materializes under `lakehouse/` on the next `ingest` + review pass. Neo4j itself is untouched (separate system). |
| Config drift between local/Databricks schemas | Single `AppConfig` dataclass and `config.yaml` schema for both modes; `config.databricks.example.yaml` documents the production values without being loaded by anything. |
| Over-abstracting embeddings | `LocalEmbeddingProvider` explicitly sets `embedding_vector: null` with a docstring - not a placeholder that could be mistaken for a real vector. |

## Verification Performed

1. **Static**: `docling_parser.py`, `semantic_chunker.py`, `entity_extractor.py`,
   `relationship_extractor.py`, `graph_builder.py`, `neo4j_loader.py`,
   `review/models.py`, `review/candidate_builder.py`, `review/ontology_generator.py`,
   `review/publisher.py` - zero edits. `review/local_repository.py` - zero
   edits (it already accepted an optional `review_dir` override).
   `review/repository.py` - one additive optional parameter (`review_dir`)
   on `get_repository()`, default preserves prior behavior exactly.
2. **CLI parity**: `python src/main.py ingest ./docs` run against the new
   pipeline - 2 files processed, 11 chunks, 24 entities / 42 mentions, 15
   relationships extracted, 24 candidate entities + 15 candidate
   relationships saved, all materialized under `lakehouse/bronze|silver|gold/`.
3. **Streamlit parity**: approved 5 entities and 1 relationship via the
   `ApprovalProvider` interface (the same interface every Streamlit page
   already used); `streamlit run app/streamlit_app.py` boots cleanly
   (HTTP 200) with `app/common.py` routed through
   `providers.get_approval_provider(load_config())`.
4. **End-to-end with live Neo4j**: `publish-ontology` produced 5 approved
   concepts / 1 relationship; `publish-graph` loaded 18 nodes / 23
   relationships into the local Neo4j instance via `Neo4jGraphProvider`.
5. **Config-switch smoke test**: setting `storage.provider: databricks_volumes`
   in `config.yaml` and re-running `ingest` failed fast with:
   `NotImplementedError: Databricks Volumes storage is not yet implemented. Set storage.provider: local in config.yaml to use the local lakehouse, or implement this class against a Unity Catalog Volume.`
   Reverting the config restored working `ingest` immediately - no code
   change required either direction.
