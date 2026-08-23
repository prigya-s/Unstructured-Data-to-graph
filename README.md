# kg-local — Enterprise Document Knowledge Graph (Local, No Docker)

Converts unstructured enterprise documents (PDF, DOCX, PPTX, TXT, HTML,
Markdown) into a Neo4j knowledge graph, fully locally — with a mandatory
business review and approval gate between extraction and the graph:

```
Documents -> Docling Extraction -> Markdown -> Semantic Chunking ->
Entity Extraction -> Relationship Extraction ->
Candidate Entities & Candidate Graph (Silver) ->
Business Review & Approval (React UI) ->
Approved Entities & Approved Ontology ->
Production Graph (Gold) -> Neo4j -> Neo4j Visualization
                                        |
                                        v
                        GraphRAG Retrieval Layer -> Conversational Agent
                        (Microsoft Agent Framework) -> "Ask the Knowledge
                        Graph" (React UI / CLI)
```

Nothing reaches the **Production Graph** (the unlabeled Gold nodes/
relationships that answers are ever drawn from) until a business reviewer
has approved it. Rejected, pending, or still-ambiguous entities never
appear there. Before approval, business users can already explore the
Silver-layer **Candidate Graph** — the graph as the extraction engine
currently understands it, loaded into the same Neo4j instance under
distinct `:CandidateEntity`/`:CANDIDATE_RELATIONSHIP` labels that retrieval
and the Production Graph page never query — and see exactly what would
change if pending items were approved, via **Graph Impact Analysis** and
**Graph Difference View**. See
[Graph Governance](#graph-governance-silvergold-layers) below.

Once a graph is published, business users can ask it questions directly —
**Ask the Knowledge Graph** retrieves relevant chunks, expands through the
graph to related entities, and answers with citations, always grounded in
the approved Production Graph only. See
[GraphRAG Retrieval Layer](#graphrag-retrieval-layer) below.

## Project structure

Every pipeline stage talks to a **provider interface**, not a hardcoded
path or environment variable. `config.yaml` selects which implementation of
each provider is used - by default a mix of local (Neo4j, local storage)
and real local-AI (Ollama for embeddings/extraction/chat) implementations,
with Azure OpenAI available as a drop-in alternative; a Databricks
deployment is a config change plus implementing the remaining stubs. See
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
│   │   ├── embeddings/             # embeddings.json (real vectors via Ollama/Azure OpenAI by default - see Embeddings below)
│   │   └── candidate_graph/         # candidate_graph.json - the SILVER graph: every
│   │       │                          # non-rejected candidate entity/relationship,
│   │       │                          # merges resolved, built by graph_builder from the
│   │       │                          # full candidate set. Not gated on approval. See
│   │       │                          # Graph Governance below.
│   │       └── candidate_graph.json
│   └── gold/
│       ├── entities/               # entities.json, mentions.json (raw extraction output,
│       │                            # pre-review - not yet Silver or Gold)
│       ├── relationships/           # relationships.json (raw extraction output, pre-review)
│       ├── review/                   # candidate_entities.json, candidate_relationships.json
│       │                              # - the business review workflow's state (Silver)
│       ├── ontology/                  # ontology.json - the GOLD approved ontology
│       │                               # (approved_entities/approved_relationships also
│       │                               # written standalone by OntologyStage)
│       └── graph_exports/              # graph_export.json - the GOLD Production Graph
│                                         # (graph_builder output over approved-only
│                                         # content, pre-Neo4j)
├── logs/                       # ingestion/publish run logs
├── api/                        # FastAPI backend for the React review app
│   ├── main.py                    # app factory, CORS, router registration, static-file mount
│   ├── deps.py                     # provider singletons + get_current_reviewer()
│   ├── schemas.py                    # Pydantic request/response models
│   ├── review_helpers.py              # now_iso/add_history/entity_display_name/etc.
│   └── routers/                        # one router per domain (dashboard, entities,
│                                          # relationships, ambiguity, candidate_graph,
│                                          # production_graph, graph_diff, ontology,
│                                          # publish, chat, health)
├── web/                        # React + TypeScript frontend (Vite)
│   ├── vite.config.ts             # dev-server proxy (/api/* -> api/main.py)
│   └── src/
│       ├── App.tsx                  # router + 7-page nav
│       ├── api/client.ts             # typed fetch wrappers, one per endpoint
│       ├── pages/                     # Dashboard, Review, CandidateGraph,
│       │                                # ProductionGraph, OntologyPreview, Publish, Chat
│       └── components/                 # shared UI (MetricTile, HistoryLog, etc.)
├── src/
│   ├── config/                  # AppConfig dataclass + load_config()
│   ├── contracts/                 # table-contract dataclasses (documentation/shape only)
│   ├── providers/                  # provider interfaces + local impls + Databricks/cloud stubs
│   │   ├── storage_provider.py / local_storage_provider.py / databricks_volumes_provider.py / unity_catalog_provider.py
│   │   ├── document_source.py / local_folder_source.py / confluence_export_source.py / confluence_source.py (stub) / sharepoint_source.py (stub)
│   │   ├── embedding_provider.py / local_embedding_provider.py (no-op) / ollama_embedding_provider.py / azure_openai_embedding_provider.py / databricks_embedding_provider.py
│   │   ├── extraction_provider.py / ontology_rules_extraction_provider.py / ollama_extraction_provider.py / azure_openai_extraction_provider.py / hybrid_extraction_provider.py
│   │   ├── llm_provider.py / ollama_llm_provider.py / azure_openai_llm_provider.py    # chat client for the GraphRAG agent
│   │   ├── approval_provider.py           # re-exports review.repository.OntologyRepository
│   │   ├── ontology_provider.py / local_ontology_provider.py
│   │   ├── secrets_provider.py / auth_provider.py
│   │   └── graph_provider.py / neo4j_graph_provider.py / neo4j_aura_graph_provider.py / cosmos_graph_provider.py (stub) / mock_graph_provider.py   # +get_linked_documents/build_candidate_graph/build_production_graph
│   ├── pipeline/
│   │   ├── context.py             # PipelineContext (providers + in-memory run state)
│   │   ├── runner.py                # PipelineRunner: run_all()/run_stage()
│   │   └── stages/                   # one thin stage per pipeline phase (see below)
│   ├── extract/docling_parser.py         # UNCHANGED business logic
│   ├── chunking/semantic_chunker.py       # UNCHANGED business logic
│   ├── ontology/ontology.yaml                 # +Check/Party/Channel/Topic entity types, +domain_gazetteer (typed acronyms), +REQUIRES/APPLIES_TO
│   ├── extraction/entity_extractor.py       # +domain_gazetteer lookups, +heading-to-Topic promotion
│   ├── extraction/relationship_extractor.py  # +REQUIRES/APPLIES_TO trigger-based relationship types
│   ├── graph/graph_builder.py                 # +optional embedding passthrough on Chunk nodes, +page-link (LEADS_TO) extraction
│   ├── graph/neo4j_loader.py                   # +vector index + search_chunks/get_mentioned_entities/get_neighbors/get_linked_documents, +CHILD_OF_PAGE/LEADS_TO structural edges
│   ├── retrieval/                              # NEW - GraphRAG service layer
│   │   └── graphrag_service.py                   # retrieve_context() -> RetrievalResult, format_context_for_llm()
│   ├── agents/                                 # NEW - Agent orchestration layer (Microsoft Agent Framework)
│   │   └── graphrag_agent.py                     # build_agent() -> ChatAgent + graph_context_tool
│   ├── review/                    # business review/approval workflow (see below) - UNCHANGED business logic
│   │   ├── models.py                # CandidateEntity, CandidateRelationship, WorkflowStatus
│   │   ├── repository.py             # OntologyRepository abstraction + get_repository()
│   │   ├── local_repository.py        # LocalOntologyRepository (JSON files, used today)
│   │   ├── ontobricks_stub.py           # FutureOntoBricksRepository (not implemented yet)
│   │   ├── ambiguity_terms.py            # known-ambiguous business term dictionary
│   │   ├── candidate_builder.py           # raw extraction output -> candidates
│   │   ├── merge_resolution.py             # shared MERGED-entity resolution helpers
│   │   ├── ontology_generator.py           # approved-only (Gold) ontology view
│   │   ├── candidate_graph.py               # full-candidate-set (Silver) graph view
│   │   ├── graph_diff.py                     # Graph Change Analysis: Gold baseline vs proposed
│   │   └── publisher.py                       # approved ontology -> Neo4j (legacy path-based helper; superseded by OntologyStage/GraphStage, kept for reference)
│   └── main.py                    # thin CLI: load config -> build providers -> build PipelineRunner -> dispatch (+ `chat` subcommand)
├── docs/architecture/           # migration assessment + mermaid diagrams + local->Databricks mapping
│   ├── graph_governance.md        # Silver/Gold artifact map, diff algorithm, gating invariant
│   └── graphrag_retrieval.md      # NEW - retrieval/agent architecture, sequence diagram, implementation plan
├── requirements.txt
├── .env
└── README.md
```

## 1. Prerequisites

- Python 3.10+
- Node.js 18+ (for the React review app under `web/`)
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

Install the React app's frontend dependencies (one-time):

```powershell
cd web
npm install
cd ..
```

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
different database name. That's the only `.env` setup required for a fully
working default install — see below.

**`config.yaml`'s `ai.mode: local` is the real default AI stack**, backed by
[Ollama](https://ollama.com/) running locally, not a placeholder. Install
Ollama, then pull the three models the default config points at:

```powershell
ollama pull bge-m3        # embedding.ollama.model
ollama pull qwen3:14b      # extraction.ollama.model (hybrid extraction's LLM fallback)
ollama pull llama3.1:8b    # llm.ollama.model (chat/GraphRAG agent)
```

Ollama's own `base_url`/`model` come from `config.yaml` (`embedding.ollama`,
`extraction.ollama`, `llm.ollama`), not `.env` — no `OLLAMA_*` environment
variables are needed. With Ollama running, ingestion produces real
embedding vectors and hybrid (rule-based + LLM-fallback) entity extraction
out of the box, and `python src/main.py chat` / the **Ask the Knowledge
Graph** page work without any Azure setup.

**Azure OpenAI is a real, swap-in alternative**, not a fallback path.
Set `ai.mode: azure` in `config.yaml` (or override `embedding.provider`/
`extraction.provider`/`llm.provider` individually to `azure_openai`), then
set:

```
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com/
AZURE_OPENAI_API_KEY=<your-key>
```

These are read through the same `SecretsProvider` abstraction as everything
else — never hardcoded in `config.yaml`.

A third option, `embedding.provider: local_noop` /
`extraction.provider: ontology_rules`, remains available for a fully
offline dry run with no model downloads at all: embeddings become
`embedding_vector: null` pass-throughs and extraction falls back to pure
keyword/gazetteer matching against `ontology.yaml`.

Optionally set `ONTOLOGY_REPOSITORY_BACKEND=local` (the default) to select
the storage backend for the review workflow. `ontobricks` is reserved for a
future OntoBricks integration and currently raises `NotImplementedError` if
selected — see [Repository abstraction](#repository-abstraction) below.

All of the above is now also mirrored in `config.yaml` at the repo root:
`embedding.provider` (`local_noop` | `ollama` | `azure_openai` |
`databricks`), `extraction.provider` (`ontology_rules` | `ollama` |
`azure_openai` | `hybrid`), `llm.provider` (`ollama` | `azure_openai`),
`ai.mode` (`local` | `azure`, sugar that fills in the three provider values
above unless a section overrides it explicitly), `approval.provider`
(`local` | `ontobricks`), `graph.provider` (`neo4j` | `neo4j_aura` |
`cosmos` | `mock`) plus `graph.neo4j.uri_env`/`user_env`/`password_env`/
`database_env` naming *which* environment variables to read (still
populated by `.env` locally). `config.yaml` is what actually gets read at
runtime; the `.env` variables above are the values it points at. See
[docs/architecture/](docs/architecture/) for the full provider/config
picture.

## 5. Add documents

Drop your PDF / DOCX / PPTX / TXT / HTML / Markdown files into `docs/`.

## 6. Run ingestion

```powershell
python src/main.py ingest ./docs
```

Each step below runs as its own `PipelineStage`, wired together by
`PipelineRunner` and reading/writing exclusively through the configured
`StorageProvider`/`DocumentSource` — by default `LocalStorageProvider` and
`ConfluenceExportSource` reading the pre-exported page tree under
`docs/MYDET` (set `document_source.provider: local_folder` in
`config.yaml` to read plain files from `docs/` instead — see
[Project structure](#project-structure)):

1. Discover documents (`IngestionStage`) → `lakehouse/bronze/raw_documents/documents.json`
2. Extract structured Markdown (Docling, `ExtractionStage`) → `lakehouse/silver/markdown/`
3. Semantically chunk the Markdown (500-800 tokens, 100-token overlap,
   `ChunkingStage`) → `lakehouse/silver/chunks/chunks.json`
4. Pass chunks through the embedding stage (`EmbeddingStage`) →
   `lakehouse/silver/embeddings/embeddings.json` — real vectors by default
   (Ollama `bge-m3` locally, or Azure OpenAI/Databricks if configured); set
   `embedding.provider: local_noop` for an offline `embedding_vector: null`
   pass-through instead.
5. Extract ontology entities (`Document, Application, System, Service,
   Database, API, Process, Team, Technology, Policy, Role, Product,
   ExternalPartner, Tool, Check, Party, Channel, Topic`,
   `EntityExtractionStage`) → `lakehouse/gold/entities/{entities,mentions}.json`.
   `extraction.provider: hybrid` (the default) runs the deterministic
   rule-based pass first — including `domain_gazetteer` lookups for bare
   acronyms (e.g. `IVR`→`Channel`, `SAMM`→`System`) and promoting document
   section headings to `Topic` entities — and only falls back to the
   configured LLM (Ollama `qwen3:14b` by default) for chunks where that
   pass found too few entities.
6. Extract ontology relationships (`USES, DEPENDS_ON, CONNECTS_TO, OWNS,
   CONTAINS, IMPLEMENTS, REFERENCES, REFERS_TO, ESCALATES_TO, REQUIRES,
   APPLIES_TO`, `RelationshipExtractionStage`) →
   `lakehouse/gold/relationships/relationships.json`
7. Turn extracted entities/relationships into reviewable candidate entities
   (definitions, business meaning, confidence, evidence, ambiguity
   detection, `ApprovalStage`) → stored via the `ApprovalProvider`, i.e.
   `lakehouse/gold/review/candidate_{entities,relationships}.json` locally
8. Build the **Silver-layer Candidate Graph** from the full candidate set
   (`CandidateGraphStage`) → `lakehouse/silver/candidate_graph/candidate_graph.json`,
   **and** load the same candidates into the configured `GraphProvider`
   (Neo4j by default) under distinct `:CandidateEntity`/
   `:CANDIDATE_RELATIONSHIP` labels — explorable by business users before
   anything is approved, and excluded from retrieval by label (see
   [Graph Governance](docs/architecture/graph_governance.md)). This stage
   also extracts and loads the structural `CHILD_OF_PAGE` page-hierarchy
   and `LEADS_TO` page-link relationships (parsed from in-page "see also"
   style references), which are never gated by review.
9. Print a summary of files/chunks/entities/relationships/candidates/candidate-graph
   created, plus an **ingestion diff report** comparing this run's document/
   entity/relationship snapshot against the previous run (pages added/
   changed/removed, entities/relationships gained/lost, orphan pages with
   no incoming `CHILD_OF_PAGE`/`LEADS_TO` edge).

**The Production (Gold) Graph is untouched until a reviewer approves
entities and publishes** (see below) — only the Candidate Graph, under its
own Candidate-only labels, is loaded during ingestion. A per-run log is
written to `logs/ingest_<timestamp>.log`.

## 7. Review and approve entities

Start the backend API and the React dev server (two terminals):

```powershell
uvicorn api.main:app --reload --port 8000
```

```powershell
cd web
npm run dev
```

Open `http://localhost:5173`. This opens a non-technical business interface
(no "Node", "Edge", "Cypher", or "Ontology Class" anywhere) with seven pages:

- **Dashboard** — documents processed, and candidate/approved/rejected counts
  for both entities and relationships.
- **Review** — three stacked sections on one page:
  - **Entity Review** — Business Term, Suggested Definition, Confidence
    Score, Business Meaning, Evidence, Related Terms, Status, with
    **Approve**, **Reject**, **Edit Definition**, and **Merge With Existing
    Entity** actions, plus an **Approve all filtered** bulk action (gated
    behind a confirmation checkbox) for approving every pending entity in
    the current filter view at once.
  - **Relationship Review** — Source Term, Relationship, Target Term,
    Confidence, Evidence, with **Approve**/**Reject** actions.
  - **Ambiguity Resolution** — for terms with more than one possible meaning
    (e.g. "Bank" → *Financial Institution* vs *River Bank*), pick the
    correct interpretation for this organization.
- **Candidate Graph** *(Silver)* — the graph as currently understood by
  the extraction engine, computed live from every non-rejected candidate,
  plus **Graph Impact Analysis** (summary metrics comparing the current
  Production Graph to what it would look like if every pending entity and
  relationship were approved) and **Graph Difference View** (the same
  comparison as full added/removed/modified/merged detail lists), as
  additional sections on the same page. Not gated on approval — this is
  what business users explore *before* anything is approved. See
  [Graph Governance](#graph-governance-silvergold-layers).
- **Ontology Preview** — read-only view of exactly what will be published:
  approved entities and relationships only.
- **Publish** — see below.
- **Production Graph** *(Gold)* — the approved-only graph that is (or
  will be) live in Neo4j. Candidates still pending review never appear here.
- **Ask the Knowledge Graph** — conversational retrieval over the
  published Production Graph. Answers cite source chunk, source document,
  and graph path used, and are always grounded in the Gold graph only. See
  [GraphRAG Retrieval Layer](#graphrag-retrieval-layer) below.

Every approve/reject/edit/merge action records who made it and when, and the
full history is visible on each entity and relationship. Approving an entity
on Entity Review is immediately reflected the next time Candidate Graph,
Graph Impact Analysis, or Graph Difference View are fetched — no manual
refresh or background job required (the "Refresh" button on Candidate Graph
just re-fetches the same live computation).

Re-running `python src/main.py ingest ./docs` later (e.g. after adding new
documents) never overwrites entities you've already approved, rejected, or
merged — only `NEW`/`PENDING_REVIEW` candidates are refreshed.

### Testing the review workflow without running the pipeline

Sample data in `data/samples/` lets you exercise the whole workflow locally
without Docling/Neo4j:

- `sample_candidates.json` / `sample_relationships.json` — raw extractor
  output shape, useful for calling `review.candidate_builder.build_candidates`
  directly.
- `sample_review_data.json` — a fully pre-reviewed set covering every status
  (`NEW`, `PENDING_REVIEW`, `APPROVED`, `REJECTED`, `MERGED`), including the
  "Bank" ambiguity example and a merged duplicate entity.

To seed the local repository from the pre-reviewed sample set:

```powershell
python -c "import json,sys; sys.path.insert(0,'src'); import providers; from config import load_config; from review import CandidateEntity, CandidateRelationship; data=json.load(open('data/samples/sample_review_data.json')); repo=providers.get_approval_provider(load_config()); [repo.save_candidate_entity(CandidateEntity.from_dict(e)) for e in data['entities']]; [repo.save_candidate_relationship(CandidateRelationship.from_dict(r)) for r in data['relationships']]; print('seeded')"
```

(`providers.get_approval_provider(load_config())` resolves the same provider
`config.yaml`'s `approval.provider` selects — `get_repository()` from
`review.repository` still exists and works standalone, but going through the
config-aware factory here keeps the seeded data pointed at the same
`lakehouse/gold/review/` location the rest of the pipeline uses.)

Then start the backend/frontend as in step 7 to explore the UI immediately.

## 8. Publish the approved ontology and graph

Once a batch of entities has been reviewed, publish them either from the
**Publish** page in the React app or from the CLI:

```powershell
python src/main.py publish-ontology
python src/main.py publish-graph
```

- `publish-ontology` (`OntologyStage`) writes the approved, human-readable
  business ontology (entities + relationships, `MERGED` entities resolved to
  their surviving entity) to `lakehouse/gold/ontology/ontology.json`, and
  also writes `approved_entities`/`approved_relationships` standalone via
  `StorageProvider`. Prints a friendly message if nothing has been approved
  yet.
- `publish-graph` (`GraphStage`) re-reads the manifests written by `ingest`
  (`lakehouse/bronze/raw_documents/documents.json`,
  `lakehouse/gold/entities/mentions.json`,
  `lakehouse/silver/chunks/chunks.json`), builds the graph JSON from
  **approved entities only** — the Gold-layer **Production Graph**, written
  to `lakehouse/gold/graph_exports/graph_export.json` — and loads it into
  Neo4j via `GraphProvider` (`Neo4jGraphProvider` wraps the existing,
  unchanged `graph_builder`/`Neo4jLoader` — idempotent, safe to re-run).

`publish-graph`/`GraphProvider.build_production_graph()` is the only path
that ever writes **Gold** (approved-only, unlabeled/production) nodes and
relationships. The Silver-layer Candidate Graph is also loaded into the
same graph database during ingestion (`CandidateGraphStage`, step 8 above)
but under distinct `:CandidateEntity`/`:CANDIDATE_RELATIONSHIP` labels —
retrieval and Cypher queries used by the review UI's Production Graph page
only ever match the unlabeled Gold nodes, so Candidate data never leaks
into an answer even though both live in the same Neo4j instance. See
[Graph Governance](#graph-governance-silvergold-layers) for exactly how
that label-based exclusion is enforced.

> **Known limitation:** publishing is additive/idempotent (`MERGE`-based).
> If an entity is rejected *after* it was already published, its node is
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

## 11. Ask the Knowledge Graph

Once a graph has been published (step 8), ask it questions from the
terminal:

```powershell
python src/main.py chat
```

or from the React app's **Ask the Knowledge Graph** page. Both build the
same agent against whichever `embedding.provider`/`llm.provider` are
configured — Ollama by default (no extra setup beyond step 4), or Azure
OpenAI if `ai.mode: azure`/`AZURE_OPENAI_ENDPOINT`/`AZURE_OPENAI_API_KEY`
are set. See [GraphRAG Retrieval Layer](#graphrag-retrieval-layer)
below for how a question turns into a grounded, cited answer — including a
"Next steps in this process" pointer to any pages the answer's source
documents link onward to.

## Graph Governance (Silver/Gold layers)

The flow from extraction to a published graph is split into two explicit
layers, so business users always know whether what they're looking at is
"the extraction engine's current best guess" or "what's actually approved
and (about to be) live in Neo4j":

- **Silver — Candidate Graph.** Built from the full candidate set —
  every entity/relationship that hasn't been rejected (`NEW`,
  `PENDING_REVIEW`, `APPROVED`), with `MERGED` entities resolved to their
  surviving entity. Produced by `review.candidate_graph.build_candidate_graph()`
  (pure function, reuses the unmodified `graph_builder.build_graph()`),
  written to `lakehouse/silver/candidate_graph/candidate_graph.json` by
  `CandidateGraphStage` on every `ingest` run, and computed live (not read
  from the snapshot) by the **Candidate Graph** page. Not gated on
  approval — this is the graph as the extraction engine currently
  understands it, safe for business users to explore before anything is
  approved.
- **Gold — Production Graph.** Built from approved content only:
  `approved_entities`/`approved_relationships` (written by `OntologyStage`),
  the **Approved Ontology** (`ontology.json`), and the **Production Graph**
  itself (`graph_export.json`, written by `GraphStage` and loaded into Neo4j
  by `GraphProvider.build_production_graph()`) — unlabeled `:Entity`/
  relationship nodes, the only ones any retrieval or Cypher query in the
  review UI ever matches.

**Gating invariant:** both graphs can live in the same Neo4j instance, but
under different labels, and only one of them is ever queried for answers.
`CandidateGraphStage` loads the full candidate set via
`GraphProvider.build_candidate_graph()` under distinct
`:CandidateEntity`/`:CANDIDATE_RELATIONSHIP` labels (in addition to writing
the Silver-layer JSON snapshot via `StorageProvider.write_candidate_graph()`
for the Candidate Graph page). Production publishing is a separate stage —
`GraphStage` → `ontology_generator.load_approved_for_graph()` (approved-only)
→ `GraphProvider.build_production_graph()` — that writes unlabeled Gold
nodes. Retrieval blindness is enforced by label exclusion in every query the
Production Graph page and the GraphRAG retrieval layer run, not by the
Candidate Graph being unable to reach Neo4j at all.

**Graph Change Analysis.** `review.graph_diff.compute_graph_diff()` compares
the current Gold baseline (`storage.read_graph_export()`) against the
proposed graph if every currently pending entity/relationship were approved,
returning a `GraphDiff` with `entities_added`, `entities_removed`,
`entities_modified`, `entities_merged`, `relationships_added`, and
`relationships_removed` (plus `entity_count_delta`/`relationship_count_delta`
properties). This one object backs both the **Graph Impact Analysis** page
(summary counts) and the **Graph Difference View** page (full detail lists)
— see [docs/architecture/graph_governance.md](docs/architecture/graph_governance.md)
for the full artifact map and diff definition.

**Demo walkthrough** (after step 6/7 above have produced candidates):

1. Open **Candidate Graph** — confirm it already shows entities/relationships
   from the latest `ingest`, none of it approved yet.
2. Go to **Entity Review**, approve a handful of entities (and optionally
   merge a duplicate).
3. Return to **Candidate Graph** — the tables reflect the approval instantly
   (same live computation, re-fetched after the save).
4. Open **Graph Impact Analysis** — see non-zero "New Entities"/"New
   Relationships" deltas for what you just approved.
5. Open **Graph Difference View** — see the same change as explicit
   added/modified/merged lists.
6. Run `python src/main.py publish-ontology` then `publish-graph` (or use the
   **Publish** page).
7. Open **Production Graph** — now shows only the approved content, live in
   Neo4j.
8. Re-check **Graph Impact Analysis** — deltas shrink to reflect the new Gold
   baseline.

## GraphRAG Retrieval Layer

Extends the pipeline one step further: once a graph is published, business
users can ask it questions directly, without writing Cypher. This is purely
additive — nothing about extraction, chunking, entity/relationship
extraction, approval, ontology generation, or Neo4j publishing changed:

```
Neo4j (Production Graph) -> GraphRAG Service Layer -> Agent Orchestration
Layer (Microsoft Agent Framework) -> Conversational UI ("Ask the Knowledge
Graph" / `chat` CLI)
```

- **GraphRAG service layer** (`src/retrieval/graphrag_service.py`) —
  `retrieve_context()` embeds the question (`EmbeddingProvider` — Ollama
  `bge-m3` by default, reusing the same abstraction ingestion uses for
  chunks), runs a Neo4j native vector search over chunk embeddings
  (`GraphProvider.search_chunks()`), follows the existing
  `(Chunk)-[:MENTIONS]->(Entity)` relationship to the entities those chunks
  reference (`get_mentioned_entities()`), expands to neighboring entities
  (`get_neighbors()`), and follows outgoing `LEADS_TO` page-links from the
  cited documents (`get_linked_documents()`, up to `retrieval.page_link_hops`
  hops) to surface a "Next steps in this process" list. The result —
  chunks, entities, human-readable graph paths, citations, and next
  steps — is assembled into text for the LLM by
  `format_context_for_llm()`.
- **Agent orchestration layer** (`src/agents/graphrag_agent.py`) — a
  Microsoft Agent Framework `ChatAgent` ("Knowledge Graph Assistant") with a
  single tool, `graph_context_tool`, that calls `retrieve_context()`. The
  agent is instructed to answer only from that tool's results and to say
  plainly when it doesn't have enough approved information, rather than
  guessing.
- **Conversational UI** — the **Ask the Knowledge Graph** page and
  the `python src/main.py chat` terminal REPL both build the same agent and
  render the same citations: source chunk, source document, and the graph
  path used, phrased as entity-relationship sentences (e.g. "Billing
  Service USES Payment Gateway") — never "Node", "Edge", or "Cypher".

**Gating invariant (extends the Silver/Gold separation above): only the
Gold Production Graph is ever used to answer a question. The Candidate
Graph is never queried by anything in `src/retrieval/` or `src/agents/`.**
Both graphs can live in the same Neo4j instance — `CandidateGraphStage` also
loads candidates under `:CandidateEntity`/`:CANDIDATE_RELATIONSHIP` labels
(see Graph Governance above) — but `search_chunks`, `get_mentioned_entities`,
`get_neighbors`, and `get_linked_documents` all match only the unlabeled
Gold nodes/relationships that `GraphProvider.build_production_graph()`
writes. There is no code path from `src/retrieval/graphrag_service.py` to
`ApprovalProvider`'s candidate-side methods, `StorageProvider.read_candidate_graph()`,
or the `:CandidateEntity`/`:CANDIDATE_RELATIONSHIP` labels at all.

Chunk nodes need an embedding vector for the vector search to work:
`GraphStage` joins `silver/embeddings/embeddings.json` onto chunks by
`chunk_id` before building the graph, and `Neo4jLoader.load_graph()`
idempotently creates the `chunk_embedding` vector index once real
embeddings are present. With the default `ollama`/`azure_openai` embedding
providers this is populated on every run; it remains a no-op only if
`embedding.provider: local_noop` is explicitly selected.

See [docs/architecture/graphrag_retrieval.md](docs/architecture/graphrag_retrieval.md)
for the full architecture diagram, sequence diagram, and implementation
plan.

## Cross-cutting design concerns

These five properties aren't one module each - they're addressed by small,
specific mechanisms spread across the pipeline. The table below defines
each in one sentence, then explains in plain words how this codebase
actually handles it.

| Concern | Definition | How it's handled here |
|---|---|---|
| **Idempotency** | Running the same operation more than once produces the same end state as running it once. | Re-running `ingest` skips any entity/relationship whose status is already `APPROVED`/`REJECTED`/`MERGED` (`candidate_builder.py`'s `existing_entities` check), and every Neo4j write uses `MERGE`, not `CREATE` (`neo4j_loader.py`) - so replaying ingestion or publishing never creates duplicate nodes, edges, or candidates. |
| **Cardinality** | The rule for how many relationships of a given type can exist between two entities. | Before a relationship becomes a candidate, everything found for the same `(source, relationship_type, target)` triple is collapsed into one row (`candidate_builder.py`'s `deduped` dict) - and once in Neo4j, `MERGE (a)-[r:TYPE]->(b)` means there can only ever be one edge of a given type between the same ordered pair, no matter how many chunks or ingestion runs mentioned it. |
| **Constraints & domain rules** | The fixed set of entity/relationship types and business-specific matching rules that decide what gets extracted and loaded at all. | `ontology.yaml` is the single source of truth: `entity_types` (with keyword lists), `relationship_types` (with trigger phrases), and `domain_gazetteer` (typed acronyms like `IVR`→`Channel`) are all read from this one file by the extractors at runtime - nothing is hardcoded in Python. As a second, independent gate, `neo4j_loader.py` keeps its own `ALLOWED_RELATIONSHIP_TYPES` allowlist and silently drops anything not on it before it reaches Neo4j, plus uniqueness constraints on `Document.id`/`Chunk.id`/`Entity.id` so bad data can't even be written twice. |
| **Supersession** | When one record is replaced by another, the system must know which one is now authoritative. | A duplicate entity is marked `status: MERGED` with a `merged_into` pointer to the surviving entity's id (`review/models.py`). `merge_resolution.py`'s `build_merge_map()`/`resolve_entity_id()` follow that pointer everywhere a graph is built, so a merged entity's mentions and relationships are always attributed to its survivor, never left pointing at the superseded id. Once `MERGED`, an entity is also frozen the same way `APPROVED`/`REJECTED` ones are - a later `ingest` run will never resurrect it. |
| **Temporality** | Tracking not just the current state of something, but when it changed and what it looked like before. | Every approve/reject/edit/merge action is appended as a timestamped `HistoryEntry` (`review/models.py`/`candidate_builder.py`'s `_now_iso()`) - so an entity's full history, not just its current status, is always visible. Across runs, `main.py`'s `_read_previous_snapshot()`/`_log_ingestion_diff_report()` compare this `ingest` run's documents (by content hash), entities, and relationships against the previous run and log what was added, changed, or removed - so an ingestion run always knows what changed since last time, not just what exists now. |

## Re-running

`ingest` is idempotent for candidates: entities are upserted by `id`, and
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
owned by the caller (the API routers and `candidate_builder`), not the
repository. This ABC is also what the pipeline's `ApprovalProvider` concept
refers to — no separate class, no rename, just the existing interface
reached through one more layer of indirection (see below).

Two equivalent entry points resolve to the same repository today:

- `providers.get_approval_provider(config)` (in `src/providers/approval_provider.py`)
  — what `api/deps.py` and every pipeline stage use. Reads
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

The FastAPI + React app (`api/`, `web/`) has no local-filesystem assumptions
beyond `LocalOntologyRepository`'s JSON files (reached through
`providers.get_approval_provider(config)`), so it — and the rest of the
pipeline — can move to Databricks as a **config change**, not a rewrite. See
[docs/architecture/](docs/architecture/) for the full picture
(`migration_assessment.md`, `architecture_diagram.md`,
`dependency_diagram.md`, `local_to_databricks_mapping.md`); in short:

1. Run `npm run build` in `web/` (outputs `web/dist/`, which `api/main.py`
   mounts as static files so one process serves both the API and the UI —
   the shape Databricks Apps expects), then add an `app.yaml` at the repo
   root pointing at the FastAPI entry point, e.g.:
   ```yaml
   command: ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
   ```
2. Set `execution_mode: databricks` plus the relevant `provider:` values in
   `config.yaml` (see `config.databricks.example.yaml`), and inject
   `NEO4J_*`/etc. as Databricks App/Workflow environment variables backed by
   secret scopes instead of a local `.env` file.
3. `UnityCatalogProvider`, `DatabricksEmbeddingProvider`, and
   `FutureOntoBricksRepository` are already real, complete implementations
   (not stubs) — see `migration_assessment.md`/`review_board_assessment.md`
   for the verification that closed those out. The seams still genuinely
   unimplemented (`NotImplementedError` stubs) are `ConfluenceSource`,
   `SharePointSource`, and `CosmosGraphProvider`; implement whichever one
   the target deployment actually needs — each is scaffolded with a
   docstring describing exactly what it needs to do. No other file needs to
   change, since every stage, page, and CLI command only depends on the
   provider interfaces.
4. Deploy with the Databricks CLI (`databricks apps deploy` /
   `databricks bundle deploy`) or the Workspace UI, following your
   workspace's standard deployment process.
