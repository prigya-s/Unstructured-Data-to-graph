# Local → Databricks Mapping

| Local today | Databricks tomorrow | Encapsulated by | Config change |
|---|---|---|---|
| Local folder (`./docs`) | Databricks Volume / Confluence / SharePoint connector | `LocalFolderSource` → `ConfluenceSource` / `SharePointSource` (currently `NotImplementedError` stubs) | `document_source.provider: confluence` (or `sharepoint`) |
| Local JSON files (`lakehouse/bronze\|silver\|gold/**/*.json`) | Delta tables in Unity Catalog | `LocalStorageProvider` → `UnityCatalogProvider` (currently a `NotImplementedError` stub) | `storage.provider: unity_catalog`, `storage.root: <UC path>` |
| No embedding generation (documented no-op) *(as of this review; `OllamaEmbeddingProvider` now provides real local embeddings by default, and `DatabricksEmbeddingProvider` has since been fully implemented - see `migration_assessment.md`)* | Databricks Foundation Model API / model-serving embedding endpoint | `LocalEmbeddingProvider` → `DatabricksEmbeddingProvider` | `embedding.provider: databricks` |
| `config.yaml` (file on disk) + `.env` (plaintext) | Databricks secret scopes, injected as environment variables | No provider swap needed - `Neo4jGraphProvider`/future providers already read credential *values* from `os.environ`; only *how* those env vars are populated changes. | n/a (deployment-level change) |
| Manual CLI (`python src/main.py ingest ...`) | Databricks Workflow, one task per pipeline stage | `PipelineRunner.run_stage(name, ctx)` - each stage is already an independent, individually-invocable unit; a Workflow task would call `run_stage("chunking", ctx)` etc. | n/a (orchestration-level change; `PipelineStage` subclasses need no changes) |
| `uvicorn api.main:app` (local process, serving the React build) | Databricks App | *(as of this review; the app was originally built with Streamlit specifically so it would deploy as a Databricks App unmodified - it has since been rebuilt as a React frontend + FastAPI backend, so this row now needs re-verifying against a FastAPI-on-Databricks-Apps deployment target rather than assumed unmodified.)* Its provider dependency, `deps.get_agent()`/`deps.get_approval_provider()` etc., already goes through `providers.get_approval_provider(config)` and friends. | n/a, plus optionally `approval.provider: ontobricks` if the review store itself also moves |
| Local Neo4j (`bolt://127.0.0.1:7687` via `.env`) | Managed Neo4j Aura / Cosmos DB for Apache Gremlin | `Neo4jGraphProvider` (already config-routed for env var names) / `CosmosGraphProvider` (currently a `NotImplementedError` stub) | `graph.provider: cosmos` (or keep `neo4j` pointed at a managed instance - no provider change needed, just new env var values) |
| `ONTOLOGY_REPOSITORY_BACKEND=local` review store (JSON files) | OntoBricks-backed review store | `LocalOntologyRepository` → `FutureOntoBricksRepository` (pre-existing stub, unmodified by this refactor) | `approval.provider: ontobricks` |

## Effort shape

For every row above, the "Databricks tomorrow" column is a single class to
implement (already scaffolded as a `NotImplementedError` stub with a
docstring identifying exactly what it needs to do) plus a one-line config
change. None of these rows require touching `docling_parser.py`,
`semantic_chunker.py`, `entity_extractor.py`, `relationship_extractor.py`,
`graph_builder.py`, `neo4j_loader.py`, or `review/*.py` - see
[migration_assessment.md](migration_assessment.md) for the verification
that confirms this.
