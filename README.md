# kg-local — Enterprise Document Knowledge Graph (Local, No Docker)

Converts unstructured enterprise documents (PDF, DOCX, PPTX, TXT, HTML,
Markdown) into a Neo4j knowledge graph, fully locally — with a mandatory
business review and approval gate between extraction and the graph:

```
Documents -> Docling Extraction -> Markdown -> Semantic Chunking ->
Entity Extraction -> Relationship Extraction ->
Candidate Entities & Candidate Graph (Silver) ->
Business Review & Approval (Streamlit) ->
Approved Entities & Approved Ontology ->
Production Graph (Gold) -> Neo4j -> Neo4j Visualization
                                        |
                                        v
                        GraphRAG Retrieval Layer -> Conversational Agent
                        (Microsoft Agent Framework) -> "Ask the Knowledge
                        Graph" (Streamlit / CLI)
```

Nothing reaches the Production Graph or Neo4j until a business reviewer has
approved it. Rejected, pending, or still-ambiguous entities never appear in
Neo4j. Before approval, business users can already explore the Silver-layer
**Candidate Graph** — the graph as the extraction engine currently
understands it — and see exactly what would change if pending items were
approved, via **Graph Impact Analysis** and **Graph Difference View**. See
[Graph Governance](#graph-governance-silvergold-layers) below.

Once a graph is published, business users can ask it questions directly —
**Ask the Knowledge Graph** retrieves relevant chunks, expands through the
graph to related entities, and answers with citations, always grounded in
the approved Production Graph only. See
[GraphRAG Retrieval Layer](#graphrag-retrieval-layer) below.

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
│   │   ├── embeddings/             # embeddings.json (no-op locally - see Embeddings below)
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
├── src/
│   ├── config/                  # AppConfig dataclass + load_config()
│   ├── contracts/                 # table-contract dataclasses (documentation/shape only)
│   ├── providers/                  # provider interfaces + local impls + Databricks/cloud stubs
│   │   ├── storage_provider.py / local_storage_provider.py / databricks_volumes_provider.py / unity_catalog_provider.py
│   │   ├── document_source.py / local_folder_source.py / confluence_source.py / sharepoint_source.py
│   │   ├── embedding_provider.py / local_embedding_provider.py / databricks_embedding_provider.py / azure_openai_embedding_provider.py
│   │   ├── llm_provider.py / azure_openai_llm_provider.py    # NEW - chat client for the GraphRAG agent
│   │   ├── approval_provider.py           # re-exports review.repository.OntologyRepository
│   │   ├── ontology_provider.py / local_ontology_provider.py
│   │   └── graph_provider.py / neo4j_graph_provider.py / cosmos_graph_provider.py   # +search_chunks/get_mentioned_entities/get_neighbors
│   ├── pipeline/
│   │   ├── context.py             # PipelineContext (providers + in-memory run state)
│   │   ├── runner.py                # PipelineRunner: run_all()/run_stage()
│   │   └── stages/                   # one thin stage per pipeline phase (see below)
│   ├── extract/docling_parser.py         # UNCHANGED business logic
│   ├── chunking/semantic_chunker.py       # UNCHANGED business logic
│   ├── ontology/ontology.yaml
│   ├── extraction/entity_extractor.py       # UNCHANGED business logic
│   ├── extraction/relationship_extractor.py  # UNCHANGED business logic
│   ├── graph/graph_builder.py                 # +optional embedding passthrough on Chunk nodes
│   ├── graph/neo4j_loader.py                   # +vector index + search_chunks/get_mentioned_entities/get_neighbors
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
├── app/                        # Streamlit business review UI
│   ├── streamlit_app.py
│   ├── common.py               # get_repo() / get_storage() -> provider factories from config.yaml
│   └── pages/
│       ├── dashboard.py
│       ├── entity_review.py
│       ├── relationship_review.py
│       ├── ambiguity_resolution.py
│       ├── candidate_graph.py          # NEW - Silver: live candidate graph, pre-approval
│       ├── graph_impact_analysis.py     # NEW - Gold baseline vs Silver-proposed, summary metrics
│       ├── graph_difference_view.py      # NEW - same diff, full added/removed/modified detail
│       ├── ontology_preview.py
│       ├── publish.py
│       ├── production_graph.py          # NEW - Gold: approved-only graph, what is/will be in Neo4j
│       └── chat.py                       # NEW - "Ask the Knowledge Graph": conversational retrieval, Gold-only
├── docs/architecture/           # migration assessment + mermaid diagrams + local->Databricks mapping
│   ├── graph_governance.md        # Silver/Gold artifact map, diff algorithm, gating invariant
│   └── graphrag_retrieval.md      # NEW - retrieval/agent architecture, sequence diagram, implementation plan
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

To use **Ask the Knowledge Graph** (the GraphRAG retrieval + conversational
layer — see [GraphRAG Retrieval Layer](#graphrag-retrieval-layer) below) or
real embeddings instead of the local no-op provider, also set:

```
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com/
AZURE_OPENAI_API_KEY=<your-key>
```

These are read through the same `SecretsProvider` abstraction as everything
else — never hardcoded in `config.yaml` — and back both `embedding.provider:
azure_openai` and `llm.provider: azure_openai` in `config.yaml`. Without
them, ingestion still works with the local no-op embedding provider, but
`python src/main.py chat` and the **Ask the Knowledge Graph** page will
raise a clear configuration error instead of silently failing.

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
7. Turn extracted entities/relationships into reviewable candidate entities
   (definitions, business meaning, confidence, evidence, ambiguity
   detection, `ApprovalStage`) → stored via the `ApprovalProvider`, i.e.
   `lakehouse/gold/review/candidate_{entities,relationships}.json` locally
8. Build the **Silver-layer Candidate Graph** from the full candidate set
   (`CandidateGraphStage`) → `lakehouse/silver/candidate_graph/candidate_graph.json`
   — the graph as currently understood by the extraction engine, explorable
   by business users before anything is approved
9. Print a summary of files/chunks/entities/relationships/candidates/candidate-graph
   created

**Ingestion stops here.** It no longer builds the Production Graph or touches
Neo4j — that only happens after a business reviewer approves entities (see
below). A per-run log is written to `logs/ingest_<timestamp>.log`.

## 7. Review and approve entities

Launch the Streamlit review app:

```powershell
streamlit run app/streamlit_app.py
```

This opens a non-technical business interface (no "Node", "Edge", "Cypher",
or "Ontology Class" anywhere) with eleven pages:

- **Dashboard** — documents processed, and candidate/approved/rejected counts
  for both entities and relationships.
- **Entity Review** — Business Term, Suggested Definition, Confidence Score,
  Business Meaning, Evidence, Related Terms, Status, with **Approve**,
  **Reject**, **Edit Definition**, and **Merge With Existing Entity** actions.
- **Relationships** (relationship review) — Source Term, Relationship,
  Target Term, Confidence, Evidence, with **Approve**/**Reject** actions.
- **Ambiguity Resolution** — for terms with more than one possible meaning
  (e.g. "Bank" → *Financial Institution* vs *River Bank*), pick the correct
  interpretation for this organization.
- **Candidate Graph** *(Silver, new)* — the graph as currently understood by
  the extraction engine, computed live from every non-rejected candidate.
  Not gated on approval — this is what business users explore *before*
  anything is approved. See [Graph Governance](#graph-governance-silvergold-layers).
- **Graph Impact Analysis** *(new)* — summary metrics comparing the current
  Production Graph to what it would look like if every pending entity and
  relationship were approved (new entities, new relationships, merges,
  removals, net deltas).
- **Graph Difference View** *(new)* — the same comparison as full detail
  lists: added/removed/modified/merged entities, added/removed relationships.
- **Ontology Preview** — read-only view of exactly what will be published:
  approved entities and relationships only.
- **Publish** — see below.
- **Production Graph** *(Gold, new)* — the approved-only graph that is (or
  will be) live in Neo4j. Candidates still pending review never appear here.
- **Ask the Knowledge Graph** *(new)* — conversational retrieval over the
  published Production Graph. Answers cite source chunk, source document,
  and graph path used, and are always grounded in the Gold graph only. See
  [GraphRAG Retrieval Layer](#graphrag-retrieval-layer) below.

Every approve/reject/edit/merge action records who made it and when, and the
full history is visible on each entity and relationship. Because every page
above computes from the current repository/storage state on each Streamlit
rerun, approving an entity on Entity Review is immediately reflected the next
time Candidate Graph, Graph Impact Analysis, or Graph Difference View render
— no manual refresh or background job required (the "Refresh" button on
Candidate Graph just forces an early rerun of the same live computation).

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

Then run `streamlit run app/streamlit_app.py` to explore the UI immediately.

## 8. Publish the approved ontology and graph

Once a batch of entities has been reviewed, publish them either from the
**Publish** page in the Streamlit app or from the CLI:

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

Only this Gold-layer output ever reaches `publish-graph`/`GraphProvider`. The
Silver-layer Candidate Graph (`lakehouse/silver/candidate_graph/`) is built by
a separate, disjoint code path (`review.candidate_graph.build_candidate_graph`)
that has no reference to any `GraphProvider` and cannot reach Neo4j — see
[Graph Governance](#graph-governance-silvergold-layers).

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

or from the Streamlit app's **Ask the Knowledge Graph** page. Both build the
same agent and require `AZURE_OPENAI_ENDPOINT`/`AZURE_OPENAI_API_KEY` to be
set (step 4). See [GraphRAG Retrieval Layer](#graphrag-retrieval-layer)
below for how a question turns into a grounded, cited answer.

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
  from the snapshot) by the **Candidate Graph** Streamlit page. Not gated on
  approval — this is the graph as the extraction engine currently
  understands it, safe for business users to explore before anything is
  approved.
- **Gold — Production Graph.** Built from approved content only:
  `approved_entities`/`approved_relationships` (written by `OntologyStage`),
  the **Approved Ontology** (`ontology.json`), and the **Production Graph**
  itself (`graph_export.json`, written by `GraphStage` and loaded into Neo4j
  by `GraphProvider`). This is the only layer ever loaded into
  `Neo4jGraphProvider` or a future `CosmosGraphProvider`.

**Gating invariant:** the Candidate Graph is built by
`review.candidate_graph.build_candidate_graph()`, which writes only through
`StorageProvider.write_candidate_graph()` and never touches a `GraphProvider`.
Production publishing is a completely separate code path —
`GraphStage` → `ontology_generator.load_approved_for_graph()` (approved-only)
→ `GraphProvider`. There is no shared function or code path between the two,
so the Candidate Graph structurally cannot reach Neo4j/Cosmos.

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
   (same live computation, Streamlit's rerun-on-interaction model).
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
  `retrieve_context()` embeds the question (`EmbeddingProvider`, reusing the
  same abstraction ingestion uses for chunks), runs a Neo4j native vector
  search over chunk embeddings (`GraphProvider.search_chunks()`), follows
  the existing `(Chunk)-[:MENTIONS]->(Entity)` relationship to the entities
  those chunks reference (`get_mentioned_entities()`), expands to
  neighboring entities (`get_neighbors()`), and assembles the result —
  chunks, entities, human-readable graph paths, citations — into text for
  the LLM.
- **Agent orchestration layer** (`src/agents/graphrag_agent.py`) — a
  Microsoft Agent Framework `ChatAgent` ("Knowledge Graph Assistant") with a
  single tool, `graph_context_tool`, that calls `retrieve_context()`. The
  agent is instructed to answer only from that tool's results and to say
  plainly when it doesn't have enough approved information, rather than
  guessing.
- **Conversational UI** — the **Ask the Knowledge Graph** Streamlit page and
  the `python src/main.py chat` terminal REPL both build the same agent and
  render the same citations: source chunk, source document, and the graph
  path used, phrased as entity-relationship sentences (e.g. "Billing
  Service USES Payment Gateway") — never "Node", "Edge", or "Cypher".

**Gating invariant (extends the Silver/Gold separation above): only the
Gold Production Graph is ever used to answer a question. The Candidate
Graph is never queried by anything in `src/retrieval/` or `src/agents/`.**
This falls out of the same structural guarantee Graph Governance already
relies on — `GraphProvider.publish()` is the only code path that ever
writes to Neo4j, fed exclusively by approved content, and the new
`search_chunks`/`get_mentioned_entities`/`get_neighbors` read methods live
on that same `GraphProvider`/`Neo4jGraphProvider`. There is no code path
from `src/retrieval/graphrag_service.py` to `ApprovalProvider`'s
candidate-side methods or `StorageProvider.read_candidate_graph()` at all.

Chunk nodes need an embedding vector for the vector search to work:
`GraphStage` now joins `silver/embeddings/embeddings.json` onto chunks by
`chunk_id` before building the graph, and `Neo4jLoader.load_graph()`
idempotently creates the `chunk_embedding` vector index once real
embeddings are present (a no-op with the local no-op embedding provider,
same as before this feature existed).

See [docs/architecture/graphrag_retrieval.md](docs/architecture/graphrag_retrieval.md)
for the full architecture diagram, sequence diagram, and implementation
plan.

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
