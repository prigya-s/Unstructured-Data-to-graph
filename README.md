# kg-local — Enterprise Document Knowledge Graph (Local, No Docker)

Converts unstructured enterprise documents (PDF, DOCX, PPTX, TXT, HTML,
Markdown) into a Neo4j knowledge graph, fully locally — with a mandatory
business review and approval gate between extraction and the graph:

```
Documents -> Docling Extraction -> Markdown -> Semantic Chunking ->
Entity Extraction -> Relationship Extraction -> Candidate Business Concepts ->
Business Review & Approval (Streamlit) -> Approved Concepts ->
Ontology Generation -> Neo4j Graph Build -> Neo4j Visualization
```

Nothing reaches the ontology or the graph until a business reviewer has
approved it. Rejected, pending, or still-ambiguous concepts never appear
in Neo4j.

## Project structure

Every pipeline stage talks to a **provider interface**, not a hardcoded
path or environment variable. `config.yaml` selects which implementation of
each provider is used - today that's always the local one; a Databricks
deployment is a config change plus implementing the corresponding stub. See
[docs/architecture/](docs/architecture/) for the full picture.

```
kg-local/
├── config.yaml                     # execution_mode + provider selection (see below)
├── config.databricks.example.yaml  # documents the future Databricks-mode values (not loaded by anything)
├── docs/                    # source documents to ingest
├── data/
│   └── samples/               # sample candidate/review JSON for testing the
│                               # approval workflow without running the pipeline
├── lakehouse/                 # local storage root (StorageProvider), medallion layout:
│   ├── bronze/raw_documents/    # documents.json (discovered documents)
│   ├── silver/
│   │   ├── markdown/             # per-document .md files + markdown.json manifest
│   │   ├── chunks/                # chunks.json
│   │   └── embeddings/             # embeddings.json (no-op locally - see Embeddings below)
│   └── gold/
│       ├── entities/               # entities.json, mentions.json (raw extraction output)
│       ├── relationships/           # relationships.json (raw extraction output)
│       ├── review/                   # candidate_entities.json, candidate_relationships.json
│       │                              # - the business review workflow's state
│       ├── ontology/                  # ontology.json (published approved ontology)
│       └── graph_exports/              # graph_export.json (graph_builder output, pre-Neo4j)
├── logs/                       # ingestion/publish run logs
├── src/
│   ├── config/                  # AppConfig dataclass + load_config()
│   ├── contracts/                 # table-contract dataclasses (documentation/shape only)
│   ├── providers/                  # provider interfaces + local impls + Databricks/cloud stubs
│   │   ├── storage_provider.py / local_storage_provider.py / databricks_volumes_provider.py / unity_catalog_provider.py
│   │   ├── document_source.py / local_folder_source.py / confluence_source.py / sharepoint_source.py
│   │   ├── embedding_provider.py / local_embedding_provider.py / databricks_embedding_provider.py
│   │   ├── approval_provider.py           # re-exports review.repository.OntologyRepository
│   │   ├── ontology_provider.py / local_ontology_provider.py
│   │   └── graph_provider.py / neo4j_graph_provider.py / cosmos_graph_provider.py
│   ├── pipeline/
│   │   ├── context.py             # PipelineContext (providers + in-memory run state)
│   │   ├── runner.py                # PipelineRunner: run_all()/run_stage()
│   │   └── stages/                   # one thin stage per pipeline phase (see below)
│   ├── extract/docling_parser.py         # UNCHANGED business logic
│   ├── chunking/semantic_chunker.py       # UNCHANGED business logic
│   ├── ontology/ontology.yaml
│   ├── extraction/entity_extractor.py       # UNCHANGED business logic
│   ├── extraction/relationship_extractor.py  # UNCHANGED business logic
│   ├── graph/graph_builder.py                 # UNCHANGED business logic
│   ├── graph/neo4j_loader.py                   # UNCHANGED business logic
│   ├── review/                    # business review/approval workflow (see below) - UNCHANGED business logic
│   │   ├── models.py                # CandidateEntity, CandidateRelationship, WorkflowStatus
│   │   ├── repository.py             # OntologyRepository abstraction + get_repository()
│   │   ├── local_repository.py        # LocalOntologyRepository (JSON files, used today)
│   │   ├── ontobricks_stub.py           # FutureOntoBricksRepository (not implemented yet)
│   │   ├── ambiguity_terms.py            # known-ambiguous business term dictionary
│   │   ├── candidate_builder.py           # raw extraction output -> candidates
│   │   ├── ontology_generator.py           # approved-only ontology view
│   │   └── publisher.py                     # approved ontology -> Neo4j (legacy path-based helper; superseded by OntologyStage/GraphStage, kept for reference)
│   └── main.py                    # thin CLI: load config -> build providers -> build PipelineRunner -> dispatch
├── app/                        # Streamlit business review UI
│   ├── streamlit_app.py
│   ├── common.py               # get_repo() -> providers.get_approval_provider(load_config())
│   └── pages/
│       ├── dashboard.py
│       ├── entity_review.py
│       ├── relationship_review.py
│       ├── ambiguity_resolution.py
│       ├── ontology_preview.py
│       └── publish.py
├── docs/architecture/           # migration assessment + mermaid diagrams + local->Databricks mapping
├── requirements.txt
├── .env
└── README.md
```

## 1. Prerequisites

- Python 3.10+
- Neo4j Desktop running locally with a database started:
  - Bolt endpoint: `neo4j://127.0.0.1:7687`
  - Username: `neo4j`
  - Password: `password123`

## 2. Create a virtual environment

```powershell
cd kg-local
python -m venv .venv
.venv\Scripts\Activate.ps1
```

(macOS/Linux: `python3 -m venv .venv && source .venv/bin/activate`)

## 3. Install requirements

```powershell
pip install -r requirements.txt
```

> Note: Docling downloads its layout/OCR models on first use for PDF/DOCX/PPTX
> parsing, which can take a few minutes the first time you process a binary
> document. `.txt` and `.md` files are handled directly without Docling.

## 4. Configure `.env`

`.env` is already set up for the local Neo4j Desktop defaults described in
the prerequisites:

```
NEO4J_URI=neo4j://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password123
NEO4J_DATABASE=kg-dev
```

Edit these values if your local instance uses different credentials or a
different database name.

Optionally set `ONTOLOGY_REPOSITORY_BACKEND=local` (the default) to select
the storage backend for the review workflow. `ontobricks` is reserved for a
future OntoBricks integration and currently raises `NotImplementedError` if
selected — see [Repository abstraction](#repository-abstraction) below.

All of the above is now also mirrored in `config.yaml` at the repo root:
`approval.provider` (`local` | `ontobricks`), `graph.provider` (`neo4j` |
`cosmos`) plus `graph.neo4j.uri_env`/`user_env`/`password_env`/`database_env`
naming *which* environment variables to read (still populated by `.env`
locally). `config.yaml` is what actually gets read at runtime; the `.env`
variables above are the values it points at. See
[docs/architecture/](docs/architecture/) for the full provider/config
picture.

## 5. Add documents

Drop your PDF / DOCX / PPTX / TXT / HTML / Markdown files into `docs/`.
Two sample documents (`network_architecture.md`, `payment_platform.txt`)
are included so you can run the pipeline immediately.

## 6. Run ingestion

```powershell
python src/main.py ingest ./docs
```

Each step below runs as its own `PipelineStage`, wired together by
`PipelineRunner` and reading/writing exclusively through the configured
`StorageProvider`/`DocumentSource` (`LocalStorageProvider`/`LocalFolderSource`
by default — see [Project structure](#project-structure)):

1. Discover documents (`IngestionStage`) → `lakehouse/bronze/raw_documents/documents.json`
2. Extract structured Markdown (Docling, `ExtractionStage`) → `lakehouse/silver/markdown/`
3. Semantically chunk the Markdown (500-800 tokens, 100-token overlap,
   `ChunkingStage`) → `lakehouse/silver/chunks/chunks.json`
4. Pass chunks through the embedding stage (`EmbeddingStage`) →
   `lakehouse/silver/embeddings/embeddings.json` — locally this is a
   documented no-op pass-through (`embedding_vector: null`); there is no
   embedding-generation logic in this codebase today.
5. Extract ontology entities (Application, System, Service, Database, API,
   Process, Team, Technology, Policy, `EntityExtractionStage`) →
   `lakehouse/gold/entities/{entities,mentions}.json`
6. Extract ontology relationships (USES, DEPENDS_ON, CONNECTS_TO, OWNS,
   CONTAINS, IMPLEMENTS, REFERENCES, `RelationshipExtractionStage`) →
   `lakehouse/gold/relationships/relationships.json`
7. Turn extracted entities/relationships into reviewable candidate business
   concepts (definitions, business meaning, confidence, evidence, ambiguity
   detection, `ApprovalStage`) → stored via the `ApprovalProvider`, i.e.
   `lakehouse/gold/review/candidate_{entities,relationships}.json` locally
8. Print a summary of files/chunks/entities/relationships/candidates created

**Ingestion stops here.** It no longer builds the graph or touches Neo4j —
that only happens after a business reviewer approves concepts (see below).
A per-run log is written to `logs/ingest_<timestamp>.log`.

## 7. Review and approve business concepts

Launch the Streamlit review app:

```powershell
streamlit run app/streamlit_app.py
```

This opens a non-technical business interface (no "Node", "Edge", "Cypher",
or "Ontology Class" anywhere) with six pages:

- **Dashboard** — documents processed, and candidate/approved/rejected counts
  for both concepts and relationships.
- **Business Concepts** (entity review) — Business Term, Suggested
  Definition, Confidence Score, Business Meaning, Evidence, Related Terms,
  Status, with **Approve**, **Reject**, **Edit Definition**, and **Merge
  With Existing Concept** actions.
- **Relationships** (relationship review) — Source Term, Relationship,
  Target Term, Confidence, Evidence, with **Approve**/**Reject** actions.
- **Ambiguity Resolution** — for terms with more than one possible meaning
  (e.g. "Bank" → *Financial Institution* vs *River Bank*), pick the correct
  interpretation for this organization.
- **Ontology Preview** — read-only view of exactly what will be published:
  approved concepts and relationships only.
- **Publish** — see below.

Every approve/reject/edit/merge action records who made it and when, and the
full history is visible on each concept and relationship.

Re-running `python src/main.py ingest ./docs` later (e.g. after adding new
documents) never overwrites concepts you've already approved, rejected, or
merged — only `NEW`/`PENDING_REVIEW` candidates are refreshed.

### Testing the review workflow without running the pipeline

Sample data in `data/samples/` lets you exercise the whole workflow locally
without Docling/Neo4j:

- `sample_candidates.json` / `sample_relationships.json` — raw extractor
  output shape, useful for calling `review.candidate_builder.build_candidates`
  directly.
- `sample_review_data.json` — a fully pre-reviewed set covering every status
  (`NEW`, `PENDING_REVIEW`, `APPROVED`, `REJECTED`, `MERGED`), including the
  "Bank" ambiguity example and a merged duplicate concept.

To seed the local repository from the pre-reviewed sample set:

```powershell
python -c "import json,sys; sys.path.insert(0,'src'); import providers; from config import load_config; from review import CandidateEntity, CandidateRelationship; data=json.load(open('data/samples/sample_review_data.json')); repo=providers.get_approval_provider(load_config()); [repo.save_candidate_entity(CandidateEntity.from_dict(e)) for e in data['entities']]; [repo.save_candidate_relationship(CandidateRelationship.from_dict(r)) for r in data['relationships']]; print('seeded')"
```

(`providers.get_approval_provider(load_config())` resolves the same provider
`config.yaml`'s `approval.provider` selects — `get_repository()` from
`review.repository` still exists and works standalone, but going through the
config-aware factory here keeps the seeded data pointed at the same
`lakehouse/gold/review/` location the rest of the pipeline uses.)

Then run `streamlit run app/streamlit_app.py` to explore the UI immediately.

## 8. Publish the approved ontology and graph

Once a batch of concepts has been reviewed, publish them either from the
**Publish** page in the Streamlit app or from the CLI:

```powershell
python src/main.py publish-ontology
python src/main.py publish-graph
```

- `publish-ontology` (`OntologyStage`) writes the approved, human-readable
  business ontology (concepts + relationships, `MERGED` concepts resolved to
  their surviving concept) to `lakehouse/gold/ontology/ontology.json`. Prints
  a friendly message if nothing has been approved yet.
- `publish-graph` (`GraphStage`) re-reads the manifests written by `ingest`
  (`lakehouse/bronze/raw_documents/documents.json`,
  `lakehouse/gold/entities/mentions.json`,
  `lakehouse/silver/chunks/chunks.json`), builds the graph JSON from
  **approved concepts only** (written to
  `lakehouse/gold/graph_exports/graph_export.json`), and loads it into Neo4j
  via `GraphProvider` (`Neo4jGraphProvider` wraps the existing, unchanged
  `graph_builder`/`Neo4jLoader` — idempotent, safe to re-run).

> **Known limitation:** publishing is additive/idempotent (`MERGE`-based).
> If a concept is rejected *after* it was already published, its node is
> not automatically deleted from Neo4j. Removing it is a deliberate,
> separate action left for a future pass rather than an automatic
> destructive operation.

## 9. Open Neo4j Browser

In Neo4j Desktop, click the running database → **Open** → **Neo4j Browser**
(or navigate to `http://localhost:7474`). Log in with `neo4j` / `password123`.

## 10. Visualize the graph

Run these queries in Neo4j Browser:

```cypher
MATCH (n) RETURN count(n);

MATCH (d:Document) RETURN d;

MATCH (c:Chunk) RETURN c LIMIT 25;

MATCH (e:Entity) RETURN e LIMIT 25;

MATCH p=()-[]->() RETURN p LIMIT 100;
```

The graph view should show:

```
Document -[:HAS_CHUNK]-> Chunk -[:MENTIONS]-> Entity -[:USES|:DEPENDS_ON|:CONNECTS_TO|:OWNS|:CONTAINS|:IMPLEMENTS|:REFERENCES]-> Entity
```

Entity nodes also carry a secondary label matching their ontology type
(e.g. `:Entity:Service`, `:Entity:Database`) so Neo4j Browser can color
and group them automatically.

## Re-running

`ingest` is idempotent for candidates: concepts are upserted by `id`, and
reviewed decisions (`APPROVED`/`REJECTED`/`MERGED`) are never overwritten by
a later `ingest` run — only `NEW`/`PENDING_REVIEW` candidates are refreshed.
`publish-graph` is also idempotent: nodes are `MERGE`d on their `id`
(enforced by uniqueness constraints on `Document.id`, `Chunk.id`,
`Entity.id`), and relationships are `MERGE`d on their endpoints + type, so
re-running it multiple times will not create duplicate nodes or edges.

## Repository abstraction

The review workflow never talks to storage directly — everything goes
through `review.repository.OntologyRepository`, an abstract base class with
exactly six methods: `save_candidate_entity`, `save_candidate_relationship`,
`get_candidate_entities`, `get_candidate_relationships`,
`get_approved_entities`, `get_approved_relationships`. `save_*` are plain
upserts by `id`; all state-machine logic (status transitions, history) is
owned by the caller (the Streamlit pages and `candidate_builder`), not the
repository. This ABC is also what the pipeline's `ApprovalProvider` concept
refers to — no separate class, no rename, just the existing interface
reached through one more layer of indirection (see below).

Two equivalent entry points resolve to the same repository today:

- `providers.get_approval_provider(config)` (in `src/providers/approval_provider.py`)
  — what `app/common.py` and every pipeline stage use. Reads
  `config.yaml`'s `approval.provider` (`local` | `ontobricks`) and passes a
  `lakehouse/gold/review/` path down.
- `review.repository.get_repository()` — the original factory, keyed off
  `ONTOLOGY_REPOSITORY_BACKEND` (`local` | `ontobricks`) instead of
  `config.yaml`, still works standalone (e.g. the sample-seeding one-liner
  above could use either).

Today, both resolve to `LocalOntologyRepository`, which stores everything as
two flat JSON arrays under `lakehouse/gold/review/`. When a real OntoBricks
environment becomes available, integration is limited to implementing
`review.ontobricks_stub.FutureOntoBricksRepository` against the same six
methods and setting `approval.provider: ontobricks` in `config.yaml` — no
other file in the pipeline, UI, or publisher needs to change.

## Extending

- Add new source documents to `docs/` and re-run `ingest`.
- Extend entity/relationship types and keyword/trigger lists in
  `src/ontology/ontology.yaml` — no code changes required for new keywords.
- Extend the known-ambiguous-term dictionary in
  `src/review/ambiguity_terms.py` to flag more terms for disambiguation.

## Deploying to Databricks

The Streamlit app under `app/` has no local-filesystem assumptions beyond
`LocalOntologyRepository`'s JSON files (reached through
`providers.get_approval_provider(config)`), so it — and the rest of the
pipeline — can move to Databricks as a **config change**, not a rewrite. See
[docs/architecture/](docs/architecture/) for the full picture
(`migration_assessment.md`, `architecture_diagram.md`,
`dependency_diagram.md`, `local_to_databricks_mapping.md`); in short:

1. Add an `app.yaml` at the repo root (or inside `app/`) pointing at the
   Streamlit entry point, e.g.:
   ```yaml
   command: ["streamlit", "run", "app/streamlit_app.py"]
   ```
2. Set `execution_mode: databricks` plus the relevant `provider:` values in
   `config.yaml` (see `config.databricks.example.yaml`), and inject
   `NEO4J_*`/etc. as Databricks App/Workflow environment variables backed by
   secret scopes instead of a local `.env` file.
3. Implement the specific `NotImplementedError` stub class(es) for whichever
   seam is moving (`UnityCatalogProvider`, `ConfluenceSource`,
   `DatabricksEmbeddingProvider`, `FutureOntoBricksRepository`,
   `CosmosGraphProvider`) — each is scaffolded with a docstring describing
   exactly what it needs to do. No other file needs to change, since every
   stage, page, and CLI command only depends on the provider interfaces.
4. Deploy with the Databricks CLI (`databricks apps deploy` /
   `databricks bundle deploy`) or the Workspace UI, following your
   workspace's standard deployment process.
