# kg-local — Enterprise Document Knowledge Graph (Local, No Docker)

This project turns a folder of enterprise documents (PDF, DOCX, PPTX, TXT,
HTML, Markdown) into a knowledge graph in Neo4j — a map of the important
things mentioned in those documents (systems, teams, processes, products...)
and how they connect. Everything runs locally, and nothing goes live until a
person has reviewed and approved it:

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

Think of it as two graphs sharing one database:

- A **draft graph** ("Candidate Graph") that updates every time you run the
  pipeline — this is the computer's best current guess at what's in the
  documents. It's useful to look at, but nothing that answers a question is
  ever drawn from it.
- A **published graph** ("Production Graph") that only contains what a
  business reviewer has explicitly approved. This is the only graph that
  "Ask the Knowledge Graph" and any Cypher query in the review app can ever
  see.

Business users can explore the draft graph before approving anything, using
**Graph Impact Analysis** and **Graph Difference View** to see exactly what
would change if the currently-pending items were approved. See
[Graph Governance](#graph-governance-silvergold-layers) below.

Once a graph is published, anyone can ask it questions in plain English —
**Ask the Knowledge Graph** finds the relevant passages, follows the graph
out to related things, and answers with a citation back to the source
document, always grounded in the approved graph only. See
[GraphRAG Retrieval Layer](#graphrag-retrieval-layer) below.

## Project structure

Every step of the pipeline talks to a small interface (a **provider**)
instead of a hardcoded file path or environment variable — so swapping, say,
"where documents live" or "which AI model does extraction" is a one-line
config change, not a code change. `config.yaml` picks which real
implementation is used for each one; by default that's a mix of local tools
(Neo4j, plain files on disk) and Ollama (a free, local AI model) for
embeddings/extraction/chat, with Azure OpenAI available as a drop-in swap. A
future move to Databricks is the same idea taken one step further — a config
change plus filling in a few remaining stubs. See
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
│   ├── ontology/ontology.yaml                 # the 17 entity types + 11 relationship types, +domain_gazetteer (typed acronyms)
│   ├── ontology/rdf/                           # NEW - OWL/Turtle generated core.ttl + hand-authored domain/*.ttl modules (opt-in, see docs/architecture/owl_turtle_ontology.md)
│   ├── extraction/entity_extractor.py       # +domain_gazetteer lookups
│   ├── extraction/relationship_extractor.py  # +REQUIRES/APPLIES_TO trigger-based relationship types
│   ├── graph/graph_builder.py                 # +optional embedding passthrough on Chunk nodes, +page-link (LEADS_TO) extraction
│   ├── graph/neo4j_loader.py                   # +vector index + search_chunks/get_mentioned_entities/get_neighbors/get_linked_documents, +CHILD_OF_PAGE/LEADS_TO structural edges, +uri/:Resource on Gold-tier nodes (neosemantics, see docs/architecture/neo4j_n10s_setup.md)
│   ├── retrieval/                              # NEW - GraphRAG service layer
│   │   ├── graphrag_service.py                   # retrieve_context() -> RetrievalResult, format_context_for_llm()
│   │   └── query_cache.py                         # QueryCache - similarity-match cache of past (query, answer, RetrievalResult)
│   ├── agents/                                 # NEW - Agent orchestration layer (Microsoft Agent Framework)
│   │   └── graphrag_agent.py                     # GraphRAGAgent - retrieves context and calls the chat client directly (no tool-call turn), run()/run_stream()
│   ├── review/                    # business review/approval workflow (see below) - UNCHANGED business logic
│   │   ├── models.py                # CandidateEntity, CandidateRelationship, WorkflowStatus
│   │   ├── repository.py             # OntologyRepository abstraction + get_repository()
│   │   ├── local_repository.py        # LocalOntologyRepository (JSON files, used today)
│   │   ├── ontobricks_stub.py           # FutureOntoBricksRepository (not implemented yet)
│   │   ├── ambiguity_terms.py            # known-ambiguous business term dictionary
│   │   ├── candidate_builder.py           # raw extraction output -> candidates, with a minimum-mentions floor before a candidate is even created (see step 7 below)
│   │   ├── merge_resolution.py             # shared MERGED-entity resolution helpers
│   │   ├── ontology_generator.py           # approved-only (Gold) ontology view
│   │   ├── candidate_graph.py               # full-candidate-set (Silver) graph view
│   │   ├── graph_diff.py                     # Graph Change Analysis: Gold baseline vs proposed
│   │   └── publisher.py                       # approved ontology -> Neo4j (legacy path-based helper; superseded by OntologyStage/GraphStage, kept for reference)
│   └── main.py                    # thin CLI: load config -> build providers -> build PipelineRunner -> dispatch (+ `chat` subcommand)
├── docs/architecture/           # migration assessment + mermaid diagrams + local->Databricks mapping
│   ├── graph_governance.md        # Silver/Gold artifact map, diff algorithm, gating invariant
│   ├── graphrag_retrieval.md      # retrieval/agent architecture, sequence diagram, implementation plan
│   └── owl_turtle_ontology.md     # NEW - OWL/Turtle ontology-authoring layer (namespaces, core.ttl, domain modules, local_turtle provider)
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

**`config.yaml`'s `ai.mode: local` is the real default AI stack.** It runs on
[Ollama](https://ollama.com/), a free tool that runs AI models on your own
machine — nothing is a placeholder. Install Ollama, then pull the three
models the default config points at:

```powershell
ollama pull bge-m3        # embedding.ollama.model
ollama pull qwen3:14b      # extraction.ollama.model (hybrid extraction's LLM fallback)
ollama pull llama3.2:3b    # llm.ollama.model (chat/GraphRAG agent)
```

Ollama's own `base_url`/`model` come from `config.yaml` (`embedding.ollama`,
`extraction.ollama`, `llm.ollama`), not `.env` — no `OLLAMA_*` environment
variables are needed. With Ollama running, ingestion produces real
embedding vectors and hybrid (rule-based + AI-fallback) entity extraction out
of the box, and `python src/main.py chat` / the **Ask the Knowledge Graph**
page work without any Azure setup.

`llm.ollama` also sets `num_thread` (how many CPU threads Ollama uses for
chat), plus `temperature` and `seed` — pinned by default (`0.1` and `42`) so
asking the same question against the same graph gives the same answer every
time, instead of a slightly different phrasing on each run.

**Azure OpenAI is a real, swap-in alternative**, not a fallback path. Set
`ai.mode: azure` in `config.yaml` (or override `embedding.provider`/
`extraction.provider`/`llm.provider` individually to `azure_openai`), then
set:

```
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com/
AZURE_OPENAI_API_KEY=<your-key>
```

These are read through the same secrets abstraction as everything else —
never hardcoded in `config.yaml`.

A third option, `embedding.provider: local_noop` /
`extraction.provider: ontology_rules`, remains available for a fully offline
dry run with no model downloads at all: embeddings become
`embedding_vector: null` pass-throughs and extraction falls back to plain
keyword matching against `ontology.yaml`.

Optionally set `ONTOLOGY_REPOSITORY_BACKEND=local` (the default) to choose
where the review workflow stores its data. `ontobricks` is reserved for a
future integration and currently isn't implemented yet — see
[Repository abstraction](#repository-abstraction) below.

All of the above is now also mirrored in `config.yaml` at the repo root:
`embedding.provider` (`local_noop` | `ollama` | `azure_openai` |
`databricks`), `extraction.provider` (`ontology_rules` | `ollama` |
`azure_openai` | `hybrid`), `llm.provider` (`ollama` | `azure_openai`),
`ai.mode` (`local` | `azure`, a shortcut that fills in the three provider
values above unless a section overrides it explicitly), `approval.provider`
(`local` | `ontobricks`), `graph.provider` (`neo4j` | `neo4j_aura` |
`cosmos` | `mock`) plus `graph.neo4j.uri_env`/`user_env`/`password_env`/
`database_env` — naming *which* environment variables to read (still coming
from `.env` locally). `config.yaml` is what actually gets read at runtime;
the `.env` variables above are the values it points at. See
[docs/architecture/](docs/architecture/) for the full picture.

## 5. Add documents

Drop your PDF / DOCX / PPTX / TXT / HTML / Markdown files into `docs/`.

## 6. Run ingestion

```powershell
python src/main.py ingest ./docs
```

Each numbered step below is its own stage, run in order, reading and writing
only through the configured storage/document-source providers — by default
that's plain local files and a pre-exported Confluence page tree under
`docs/MYDET` (set `document_source.provider: local_folder` in `config.yaml`
to read plain files from `docs/` instead — see
[Project structure](#project-structure)):

1. Find the documents (`IngestionStage`) → `lakehouse/bronze/raw_documents/documents.json`
2. Turn each one into clean Markdown (Docling, `ExtractionStage`) → `lakehouse/silver/markdown/`
3. Split the Markdown into readable chunks (500–800 words with some overlap,
   `ChunkingStage`) → `lakehouse/silver/chunks/chunks.json`
4. Turn each chunk into a vector embedding (`EmbeddingStage`) →
   `lakehouse/silver/embeddings/embeddings.json` — real vectors by default
   (Ollama `bge-m3` locally, or Azure OpenAI/Databricks if configured); set
   `embedding.provider: local_noop` to skip this and store `null` instead.
5. Pull out the things being talked about — entities like `Document,
   Application, System, Service, Database, API, Process, Team, Technology,
   Policy, Role, Product, ExternalPartner, Tool, Check, Party, Channel`
   (`EntityExtractionStage`) → `lakehouse/gold/entities/{entities,mentions}.json`.
   `extraction.provider: hybrid` (the default) tries plain rule-based
   matching first — including a lookup table for bare acronyms (e.g.
   `IVR`→`Channel`, `SAMM`→`System`) — and only asks the AI model (Ollama
   `qwen3:14b` by default) for chunks where the rules alone found too little.
6. Pull out how those things relate to each other — relationships like
   `USES, DEPENDS_ON, CONNECTS_TO, OWNS, CONTAINS, IMPLEMENTS, REFERENCES,
   REFERS_TO, ESCALATES_TO, REQUIRES, APPLIES_TO`
   (`RelationshipExtractionStage`) →
   `lakehouse/gold/relationships/relationships.json`. If a domain/range rule
   exists for a relationship type (e.g. "`OWNS` should go from a Team to a
   System/Service/Application"), a relationship that breaks it is *not*
   thrown away — it's still created and shown to a reviewer with a warning
   attached, so a person makes the final call.
7. Turn all of that into reviewable draft entities (with a plain-English
   definition, business meaning, confidence score, and supporting evidence,
   `ApprovalStage`) → stored via the approval provider, i.e.
   `lakehouse/gold/review/candidate_{entities,relationships}.json` locally.
   A one-off phrase that only shows up once in the whole document set never
   even reaches this list — a candidate needs at least two separate mentions
   before it's worth putting in front of a reviewer.
8. Build the **draft graph (Silver-layer Candidate Graph)** from everything
   still in play (`CandidateGraphStage`) →
   `lakehouse/silver/candidate_graph/candidate_graph.json`, **and** load the
   same draft entities into Neo4j under their own labels
   (`:CandidateEntity`/`:CANDIDATE_RELATIONSHIP`) — viewable by business
   users before anything is approved, and never mixed into an answer (see
   [Graph Governance](docs/architecture/graph_governance.md)). This step
   also figures out how pages link to each other (`CHILD_OF_PAGE` for the
   page hierarchy, `LEADS_TO` for in-page "see also" style links), which
   never needs review.
9. Print a summary of what was found, plus a comparison against the previous
   run (pages added/changed/removed, entities/relationships gained/lost,
   pages with no incoming link from anywhere else).

**The published (Gold) graph is untouched until a reviewer approves entities
and someone runs publish** (see below) — ingestion only ever touches the
draft graph. A per-run log is written to `logs/ingest_<timestamp>.log`.

## 7. Review and approve entities

Start the backend API and the React dev server (two terminals):

```powershell
uvicorn api.main:app --reload --port 8000
```

```powershell
cd web
npm run dev
```

Open `http://localhost:5173`. This is a plain-language business interface —
no "Node", "Edge", "Cypher", or "Ontology Class" anywhere — with seven pages:

- **Dashboard** — documents processed, and candidate/approved/rejected counts
  for both entities and relationships.
- **Review** — three sections on one page:
  - **Entity Review** — Business Term, Suggested Definition, Confidence
    Score, Business Meaning, Evidence, Related Terms, Status, with
    **Approve**, **Reject**, **Edit Definition**, and **Merge With Existing
    Entity** actions, plus an **Approve all filtered** bulk action (behind a
    confirmation checkbox) for approving everything currently pending in the
    filtered view at once.
  - **Relationship Review** — Source Term, Relationship, Target Term,
    Confidence, Evidence, with **Approve**/**Reject** actions. A
    relationship flagged with a domain/range warning (see step 6 above)
    shows that warning right here, so the reviewer can decide with full
    context — it's a heads-up, never an automatic block.
  - **Ambiguity Resolution** — for terms with more than one possible meaning
    (e.g. "Bank" → *Financial Institution* vs *River Bank*), pick the
    correct interpretation for this organization.
- **Candidate Graph** *(Silver)* — the draft graph, computed live from
  everything not yet rejected, plus **Graph Impact Analysis** (a summary of
  how the published graph would change if every pending item were approved)
  and **Graph Difference View** (the same comparison as full
  added/removed/modified/merged lists), on the same page. Nothing here is
  gated on approval — this is what business users explore *before* anything
  is approved. See [Graph Governance](#graph-governance-silvergold-layers).
- **Ontology Preview** — a read-only look at exactly what will be published:
  approved entities and relationships only.
- **Publish** — see below.
- **Production Graph** *(Gold)* — the approved-only graph that is (or will
  be) live in Neo4j. Anything still pending review never shows up here.
- **Ask the Knowledge Graph** — ask a question in plain English and get an
  answer drawn only from the published graph. The answer streams in as
  ordinary prose (no chunk IDs, node/edge jargon, or Cypher) and ends with a
  **References** line naming the source documents it drew from. See
  [GraphRAG Retrieval Layer](#graphrag-retrieval-layer) below.

Every approve/reject/edit/merge action records who did it and when, and the
full history is visible on each entity and relationship. Approving an entity
on Entity Review is reflected immediately the next time Candidate Graph,
Graph Impact Analysis, or Graph Difference View load — no manual refresh or
background job required (the "Refresh" button on Candidate Graph just
re-fetches the same live computation).

Re-running `python src/main.py ingest ./docs` later (e.g. after adding new
documents) never overwrites entities you've already approved, rejected, or
merged — only brand-new or still-pending candidates are refreshed.

### Testing the review workflow without running the pipeline

Sample data in `data/samples/` lets you try out the whole workflow locally
without Docling or Neo4j:

- `sample_candidates.json` / `sample_relationships.json` — raw extractor
  output shape, useful for calling `review.candidate_builder.build_candidates`
  directly.
- `sample_review_data.json` — a fully pre-reviewed set covering every status
  (`NEW`, `PENDING_REVIEW`, `APPROVED`, `REJECTED`, `MERGED`), including the
  "Bank" ambiguity example and a merged duplicate entity.

To load the local repository with this pre-reviewed sample data:

```powershell
python -c "import json,sys; sys.path.insert(0,'src'); import providers; from config import load_config; from review import CandidateEntity, CandidateRelationship; data=json.load(open('data/samples/sample_review_data.json')); repo=providers.get_approval_provider(load_config()); [repo.save_candidate_entity(CandidateEntity.from_dict(e)) for e in data['entities']]; [repo.save_candidate_relationship(CandidateRelationship.from_dict(r)) for r in data['relationships']]; print('seeded')"
```

(`providers.get_approval_provider(load_config())` picks the same backend
`config.yaml`'s `approval.provider` selects — `get_repository()` from
`review.repository` still exists and works on its own, but going through
this config-aware version keeps the sample data pointed at the same
`lakehouse/gold/review/` location the rest of the pipeline uses.)

Then start the backend/frontend as in step 7 to explore the UI right away.

## 8. Publish the approved ontology and graph

Once a batch of entities has been reviewed, publish them either from the
**Publish** page in the React app or from the CLI:

```powershell
python src/main.py publish-ontology
python src/main.py publish-graph
```

- `publish-ontology` (`OntologyStage`) writes the approved, plain-English
  business ontology (entities + relationships, with `MERGED` entities
  resolved to whichever entity survived the merge) to
  `lakehouse/gold/ontology/ontology.json`, and also writes
  `approved_entities`/`approved_relationships` separately. It prints a
  friendly message if nothing has been approved yet.
- `publish-graph` (`GraphStage`) re-reads what `ingest` already produced
  (`lakehouse/bronze/raw_documents/documents.json`,
  `lakehouse/gold/entities/mentions.json`,
  `lakehouse/silver/chunks/chunks.json`), builds the graph from **approved
  entities only** — the published **Production Graph** — writes it to
  `lakehouse/gold/graph_exports/graph_export.json`, and loads it into Neo4j.
  Safe to re-run.

Publishing is the only step that ever writes the published (Gold) graph.
The draft (Silver) graph is also loaded into the same Neo4j database during
ingestion, but under its own labels — so retrieval and the review UI's
Production Graph page only ever see the published graph, even though both
live in the same database. See
[Graph Governance](#graph-governance-silvergold-layers) for exactly how that
separation is enforced.

> **Known limitation:** publishing never deletes. If an entity is rejected
> *after* it was already published, its node stays in Neo4j — removing it is
> a deliberate, separate action, not something that happens automatically.

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

Entity nodes also carry a second label matching their type (e.g.
`:Entity:Service`, `:Entity:Database`) so Neo4j Browser can color and group
them automatically.

## 11. Ask the Knowledge Graph

Once a graph has been published (step 8), ask it questions from the
terminal:

```powershell
python src/main.py chat
```

or from the React app's **Ask the Knowledge Graph** page. Both use the same
underlying setup, whichever embedding/AI provider is configured — Ollama by
default (no extra setup beyond step 4), or Azure OpenAI if `ai.mode: azure`
is set. See [GraphRAG Retrieval Layer](#graphrag-retrieval-layer) below for
how a question turns into a grounded, cited answer — including a "Next
steps in this process" pointer to any pages the answer's source documents
link onward to.

## Graph Governance (Silver/Gold layers)

The path from extraction to a published graph is split into two clearly
separate layers, so anyone looking at the app always knows whether they're
looking at "the computer's current best guess" or "what's actually been
approved and is (or is about to be) live in Neo4j":

- **Silver — Candidate Graph.** Built from everything that hasn't been
  rejected (`NEW`, `PENDING_REVIEW`, `APPROVED`), with duplicates already
  resolved to whichever entity survived a merge. Rebuilt on every `ingest`
  run and shown live (not from a stale snapshot) on the **Candidate Graph**
  page. Nothing here is gated on approval — it's the graph as the extraction
  engine currently understands it, safe to explore before anything is
  approved.
- **Gold — Production Graph.** Built from approved content only: the
  approved entities and relationships, the **Approved Ontology**
  (`ontology.json`), and the **Production Graph** itself
  (`graph_export.json`) — loaded into Neo4j as plain, unlabeled nodes and
  relationships, the only ones any query in the review UI or retrieval ever
  matches.

**The rule that keeps them separate:** both graphs can live in the same
Neo4j database, but under different labels, and only one of them is ever
used to answer a question. The draft graph is loaded under its own
`:CandidateEntity`/`:CANDIDATE_RELATIONSHIP` labels; publishing is a
completely separate step that writes plain, unlabeled nodes. Every query the
Production Graph page and the retrieval layer run explicitly excludes the
candidate labels — the draft graph isn't hidden because it's unreachable,
it's hidden because nothing is written to look at it.

**Graph Change Analysis.** Compares the currently-published graph against
what it would look like if every pending item right now were approved,
producing a list of entities/relationships that would be added, removed,
modified, or merged. This one comparison backs both the **Graph Impact
Analysis** page (summary counts) and the **Graph Difference View** page
(the full detail lists) — see
[docs/architecture/graph_governance.md](docs/architecture/graph_governance.md)
for the technical detail.

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

Extends the pipeline one step further: once a graph is published, anyone can
ask it questions without writing Cypher. This is purely additive — nothing
about extraction, chunking, review, or publishing changes:

```
Neo4j (Production Graph) -> GraphRAG Service Layer -> Agent Orchestration
Layer (Microsoft Agent Framework) -> Conversational UI ("Ask the Knowledge
Graph" / `chat` CLI)
```

- **GraphRAG service layer** (`src/retrieval/graphrag_service.py`) — turns
  the question into a vector and searches for the most relevant chunks in
  Neo4j, follows the graph from those chunks to the entities they mention,
  expands out to neighboring entities, and follows any "see also"-style
  links from the source documents to build a "Next steps in this process"
  list. All of that — chunks, entities, readable graph paths, citations, and
  next steps — is assembled into text the AI model reads before answering.
- **Agent** (`src/agents/graphrag_agent.py`) — every turn, the relevant
  context is looked up and handed to the AI model directly along with the
  question; the model is instructed to answer only from that context and to
  say plainly when it doesn't have enough approved information, rather than
  guessing.
- **Conversational UI** — the **Ask the Knowledge Graph** page and the
  `python src/main.py chat` terminal both stream the answer in as it's
  generated, rather than waiting for the full response. The answer itself
  never mentions chunk/document IDs, nodes, edges, or Cypher — graph
  connections are phrased as plain sentences (e.g. "Billing Service USES
  Payment Gateway"), and it closes with a **References** line naming just
  the source documents used.
- **Query cache** (`src/retrieval/query_cache.py`) — remembers past
  questions and answers. A new question close enough to one already asked
  gets the cached answer back immediately instead of re-running the whole
  lookup, so repeated or slightly-rephrased questions come back fast.

**The same separation rule applies here: only the published graph is ever
used to answer a question.** The draft graph can live in the same Neo4j
database, but nothing in the retrieval or agent code has any path to read
the draft-only labels or data at all — it isn't filtered out at query time,
it's simply never queried.

Chunks need an embedding vector for search to work — this is filled in
automatically during publishing with the default Ollama/Azure OpenAI setup,
and only stays empty if `embedding.provider: local_noop` is explicitly
chosen.

See [docs/architecture/graphrag_retrieval.md](docs/architecture/graphrag_retrieval.md)
for the full technical detail — architecture diagram, sequence diagram, and
implementation notes.

## Cross-cutting design concerns

These five properties aren't one module each — they're handled by small,
specific mechanisms spread across the pipeline. The table below defines
each one in plain terms, then explains how this project actually handles it.

| Concern | Definition | How it's handled here |
|---|---|---|
| **Idempotency** | Running the same operation more than once gives the same end result as running it once. | Re-running `ingest` skips anything already `APPROVED`/`REJECTED`/`MERGED`, and every Neo4j write updates-or-creates rather than always creating new — so replaying ingestion or publishing never produces duplicate nodes, edges, or candidates. |
| **Cardinality** | The rule for how many relationships of a given type can exist between two things. | Before a relationship becomes a candidate, every mention of the same "X relates to Y this way" is collapsed into one row — and once in Neo4j, there can only ever be one edge of a given type between the same ordered pair, no matter how many chunks or ingestion runs mentioned it. |
| **Constraints & domain rules** | The fixed list of entity/relationship types and business-specific matching rules that decide what gets pulled out at all. | `ontology.yaml` is the single source of truth: entity types (with keyword lists), relationship types (with trigger phrases), and a lookup table of acronyms (like `IVR`→`Channel`) are all read from this one file — nothing is hardcoded in Python. As a second, independent check, the Neo4j loader keeps its own allow-list of relationship types and silently drops anything not on it, plus uniqueness rules so the same document/chunk/entity can never be written twice. |
| **Supersession** | When one record is replaced by another, the system needs to know which one is now the real one. | A duplicate entity is marked "merged" with a pointer to the entity it was merged into. Every place a graph gets built follows that pointer, so a merged entity's mentions and relationships always end up attributed to the entity that survived, never left pointing at the one that got merged away. Once merged, an entity is frozen the same way approved/rejected ones are — a later `ingest` run never brings it back. |
| **Temporality** | Tracking not just what something is right now, but when it changed and what it looked like before. | Every approve/reject/edit/merge action is recorded with a timestamp, so an entity's full history — not just its current status — is always visible. Across runs, ingestion also compares this run's documents, entities, and relationships against the previous run and reports what was added, changed, or removed — so you always know what changed since last time, not just what exists now. |

## Re-running

`ingest` is safe to run again and again: entities are matched by their id,
and reviewed decisions (approved/rejected/merged) are never overwritten by a
later run — only brand-new or still-pending candidates get refreshed.
`publish-graph` is the same way — nodes and relationships are matched on
their id/endpoints rather than always created fresh, so running it multiple
times never produces duplicates.

## Repository abstraction

The review workflow never talks to storage directly — everything goes
through one small interface with exactly six operations: save an entity,
save a relationship, get candidate entities, get candidate relationships,
get approved entities, get approved relationships. Saving is always an
upsert by id; all the status-change logic (approve, reject, history) lives
in the caller (the API and the candidate builder), not in storage itself.

Two equivalent ways to get this interface resolve to the same storage today:

- `providers.get_approval_provider(config)` — what the API and every
  pipeline stage use. Reads `config.yaml`'s `approval.provider`
  (`local` | `ontobricks`) and points it at `lakehouse/gold/review/`.
- `review.repository.get_repository()` — the original way of getting it,
  keyed off an environment variable instead of `config.yaml`, still works on
  its own (e.g. the sample-seeding command above could use either).

Today, both point at the same JSON-file storage under
`lakehouse/gold/review/`. When a real OntoBricks environment becomes
available, plugging it in only means implementing the same six operations
against it and flipping `approval.provider: ontobricks` in `config.yaml` —
nothing else in the pipeline, UI, or publisher needs to change.

## Extending

- Add new source documents to `docs/` and re-run `ingest`.
- Add new entity/relationship types and keyword/trigger lists in
  `src/ontology/ontology.yaml` — no code changes required for new keywords.
- Add more known-ambiguous terms in `src/review/ambiguity_terms.py` to flag
  more terms for disambiguation.
- Onboard a new business area without touching `ontology.yaml` at all, by
  adding an OWL/Turtle file under `src/ontology/rdf/domains/` that builds on
  the shared vocabulary — see
  [docs/architecture/owl_turtle_ontology.md](docs/architecture/owl_turtle_ontology.md).
  The published Neo4j graph is RDF-native under the hood (using
  neosemantics/n10s for RDF import/export — retrieval itself stays plain
  Cypher) — see
  [docs/architecture/neo4j_n10s_setup.md](docs/architecture/neo4j_n10s_setup.md)
  for the one-time manual plugin install this requires.

## Deploying to Databricks

The FastAPI + React app (`api/`, `web/`) has no assumptions baked in about
running on a local filesystem beyond the review workflow's JSON files
(reached through the same provider interface as everything else), so it —
and the rest of the pipeline — can move to Databricks as a **config
change**, not a rewrite. See [docs/architecture/](docs/architecture/) for
the full picture (`migration_assessment.md`, `architecture_diagram.md`,
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
3. The Databricks-flavored storage/embedding/repository implementations are
   already real and complete, not placeholders — see
   `migration_assessment.md`/`review_board_assessment.md` for the review
   that confirmed this. What's still genuinely unimplemented is reading
   documents from Confluence/SharePoint directly and the Cosmos DB graph
   option — implement whichever one the target deployment actually needs;
   each is scaffolded with a docstring describing exactly what it needs to
   do. Nothing else needs to change, since every stage, page, and CLI
   command only depends on the provider interfaces.
4. Deploy with the Databricks CLI (`databricks apps deploy` /
   `databricks bundle deploy`) or the Workspace UI, following your
   workspace's standard deployment process.
