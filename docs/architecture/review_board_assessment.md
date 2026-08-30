# Databricks Architecture Review Board: Component Assessment

Verdicts are grounded in the actual implementation as of this review, not
the target architecture's aspirational shape. "Migration Effort" is the
effort remaining to run that component on Databricks - not the effort
already spent building it.

## Verdict Table

| # | Component | Effort | Refactor performed this pass |
|---|---|---|---|
| 1 | Document Ingestion (local folder) | **CONFIGURATION ONLY** | None needed - see below. |
| 2 | Storage | **LOW** (was HIGH) | Built `providers/_delta_sql.py` (schema-driven generic Delta/SQL helper) + `contracts.schemas.TABLE_REGISTRY`; rewrote `UnityCatalogProvider` and `DatabricksVolumesProvider` against it. |
| 3 | Docling Extraction | **CONFIGURATION ONLY** | None needed - see below. |
| 4 | Chunking | **CONFIGURATION ONLY** | None needed - see below. |
| 5 | Embedding Generation | **LOW** (was HIGH) | Implemented `DatabricksEmbeddingProvider.embed_chunks()` as a real Model Serving REST call. |
| 6 | Entity Extraction | **CONFIGURATION ONLY** | None needed - pure computation, no infra dependency. |
| 7 | Relationship Extraction | **CONFIGURATION ONLY** | None needed - pure computation, no infra dependency. |
| 8 | Approval Workflow | **LOW** (was MEDIUM) | Implemented `FutureOntoBricksRepository` against the same `_delta_sql.py` helper (atomic `MERGE INTO` upserts). |
| 9 | Ontology Generation | **CONFIGURATION ONLY** | None needed - see below. |
| 10 | Neo4j Graph Creation | **CONFIGURATION ONLY** | None needed - already fully env-var-driven. |

No component remains at HIGH or MEDIUM. The two components still at LOW
(Storage/Unity Catalog path, Approval Workflow/OntoBricks path) have real,
complete code - they are not stubs - but have not been exercised against a
live SQL Warehouse, which no amount of further local refactoring can
substitute for; that is execution risk, not design debt.

## HIGH/MEDIUM findings, before and after

### Storage - was HIGH

**Why:** `UnityCatalogProvider` and `DatabricksVolumesProvider` were both
20-method stubs raising `NotImplementedError`. Naively fixing this meant
hand-writing bespoke `CREATE TABLE`/`MERGE`/`SELECT` SQL once per table
across ~11 tables - a large, error-prone, and hard-to-review surface.

**Refactor:** Recognized that every table's shape is already pinned down
in `contracts.schemas.TABLE_REGISTRY` (dataclass + primary key). Built one
generic `DeltaSqlTableStore` (`providers/_delta_sql.py`) that derives
`CREATE TABLE`/`SELECT`/`DELETE+INSERT` (full overwrite)/`MERGE INTO`
(upsert) SQL from a dataclass's fields via `dataclasses.fields()`. Adding a
table is now one `TABLE_REGISTRY` entry, not four new SQL strings.
Separately, recognized that a mounted Unity Catalog Volume is an ordinary
POSIX path from Python's perspective - `DatabricksVolumesProvider` is now
a zero-logic `LocalStorageProvider` subclass pointed at `config.storage_root`.

**Result:** `storage.provider: databricks_volumes` is CONFIGURATION ONLY.
`storage.provider: unity_catalog` is LOW - real, generic code exists;
remaining effort is standing up a SQL Warehouse and running it once against
real credentials, not writing more code.

### Embedding Generation - was HIGH

**Why:** No embedding-generation code existed anywhere in the codebase
(confirmed by search during the original refactor) - `LocalEmbeddingProvider`
is an intentional no-op pass-through, and was the local default at the time
of this review. `DatabricksEmbeddingProvider` raised `NotImplementedError`
unconditionally. `OllamaEmbeddingProvider` was added afterward and is now
the local default; `LocalEmbeddingProvider` remains available as an
explicit opt-in no-op for offline dry runs. See `graphrag_retrieval.md`.

**Refactor:** Implemented `embed_chunks()` as a batched POST to a
Databricks Model Serving `/serving-endpoints/<name>/invocations` endpoint
via stdlib `urllib.request` (no new dependency), mirroring the `*_env`
config-key-name pattern already used by `Neo4jGraphProvider`/
`UnityCatalogProvider` (`embedding.databricks.{host_env,token_env,endpoint_env,model_name,batch_size}`).

**Result:** LOW. The code path is complete and config-driven; what
remains - deploying and selecting an actual embedding model/endpoint - is
a data-science decision, not an engineering one, and is irreducible by
further refactoring.

### Approval Workflow - was MEDIUM

**Why:** Two distinct issues: (a) `FutureOntoBricksRepository` was a
6-method stub raising `NotImplementedError`; (b) `LocalOntologyRepository`
documents a real cross-process write-safety gap (JSON-file-plus-in-process-lock
is "last writer wins" across two separate processes, e.g. a CLI run and a
Streamlit server writing at the same instant).

**Refactor:** Implemented `FutureOntoBricksRepository` against the same
`DeltaSqlTableStore` used by `UnityCatalogProvider` (`candidate_entities`/
`candidate_relationships` were already in `TABLE_REGISTRY`), with
`save_candidate_entity`/`save_candidate_relationship` as `merge_rows()`
upserts-by-id. Deliberately did **not** touch `review/local_repository.py`
- the write-safety gap is a documented, accepted local-only limitation, and
Delta's `MERGE INTO` is atomic across concurrent writers/processes/nodes by
construction. The fix lives in *which* repository is selected, not in
patching the local one.

**Result:** LOW. Real code exists; remaining effort is running it against
a live Warehouse, same caveat as Storage/Unity Catalog.

## CONFIGURATION ONLY findings and why they needed no refactor

- **Document Ingestion (local folder):** `LocalFolderSource` wraps
  `docling_parser.discover_documents`/`convert_to_markdown` unmodified and
  reads its folder path from `document_source.local_folder.path` in
  config. Pointing that path at a Volume-mounted folder (instead of a
  Databricks-native connector) is sufficient for the "run the existing
  pipeline on Databricks" goal - no code change.
- **Docling Extraction:** `docling_parser.py` takes folder paths as
  function arguments only, with no hardcoded paths of its own.
  `DocumentConverter()` resolves its OCR/layout models via
  `huggingface_hub`, which natively honors the `HF_HOME` environment
  variable - persisting model downloads across ephemeral Databricks
  clusters is a cluster/App environment-variable setting, not a code
  change.
- **Chunking:** `semantic_chunker.py` is pure computation (regex-based
  markdown splitting, `tiktoken`-based token counting) with zero file I/O
  and zero local-path assumptions. The only external touchpoint is
  `tiktoken.get_encoding("cl100k_base")`'s one-time vocabulary-file
  download on first use - addressed the same way as Docling, via a cache
  directory environment variable (`TIKTOKEN_CACHE_DIR`) rather than code.
- **Entity Extraction / Relationship Extraction:** `entity_extractor.py`
  and `relationship_extractor.py` use only `re`/`hashlib`/builtins - no
  model loading, no file I/O, no network calls, no local-path assumptions
  of any kind. There is nothing to configure or migrate.
- **Ontology Generation:** `LocalOntologyProvider` has no I/O of its own
  beyond calling the unmodified `review.ontology_generator` functions and
  writing a scratch file under `config.storage_root` - which already
  resolves correctly whether `storage.root` is a local path or a
  Volume/DBFS path (`AppConfig.storage_root` already special-cases
  absolute paths). No Databricks-specific class exists or is needed.
- **Neo4j Graph Creation:** `Neo4jGraphProvider`/`Neo4jLoader` read
  connection details purely from env-var *names* that are themselves
  config-driven (`graph.neo4j.{uri_env,user_env,password_env,database_env}`);
  the actual secret values come from `os.environ` at runtime. Pointing at
  Neo4j Aura or a VPC-peered instance reachable from Databricks changes
  only which environment variables are populated (Databricks secret
  scopes vs. `.env`), never the code that reads them.

## Explicitly irreducible items (out of scope for this migration goal)

Not part of the verdict table above (none of the 10 requested components),
but worth flagging so they aren't mistaken for oversights:

- **`ConfluenceSource`/`SharePointSource`** (`document_source.provider`):
  genuinely net-new connector code (auth, pagination, API-specific
  document models). Not reducible by architecture alone - it's new
  integration work if/when those sources are needed. The core migration
  goal does not require them; a Volume-mounted `LocalFolderSource` is
  sufficient.
- **`CosmosGraphProvider`** (`graph.provider: cosmos`): genuinely net-new
  Gremlin-API code. Not required for the migration goal - managed Neo4j
  (Aura or self-hosted, reachable from Databricks) already satisfies
  "Neo4j Graph Creation" at CONFIGURATION ONLY via `Neo4jGraphProvider`.
- **Embedding model selection/quality**: choosing and tuning *which*
  Databricks Foundation Model or custom endpoint to call is a
  data-science decision, not a code-architecture one - see Embedding
  Generation above.

## Verification

- `python src/main.py ingest ./docs` re-run after every code change in
  this pass (config parsing change, new provider bodies) - still succeeds:
  6 files processed, 22 chunks, 31 entities / 51 mentions, 15
  relationships, 26 candidate entities / 14 candidate relationships saved
  under `lakehouse/`.
- All six provider factories (`get_storage_provider`, `get_document_source`,
  `get_embedding_provider`, `get_approval_provider`, `get_ontology_provider`,
  `get_graph_provider`) resolve to their local implementations correctly
  against the unmodified `config.yaml`.
- Databricks-only code paths (`UnityCatalogProvider`, `FutureOntoBricksRepository`,
  `DatabricksEmbeddingProvider`) are not executable in this environment (no
  live SQL Warehouse/Model Serving endpoint) and were reviewed by static
  inspection against `_delta_sql.py`'s existing, tested-by-construction SQL
  generation, not run end-to-end.
