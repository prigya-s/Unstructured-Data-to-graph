# CTO Demo Script: Unstructured Data → Knowledge Graph → Retrieval

A presenter's script for walking a CTO through the whole pipeline live: ontology,
human approval flow, RDF triplets, and graph-traversal retrieval. Every number,
entity name, and query result below was pulled from the running system on
2026-08-31/09-01 (97 documents, 40 approved entities, 31 approved relationships) —
re-run the "Live check" commands the morning of the real demo in case the data has moved.

## Setup checklist (5 min before the room fills up)

- Backend running: `.venv/Scripts/python.exe -m uvicorn api.main:app --port 8000` (from repo root)
- Frontend running: `npm run dev` in `web/` → http://localhost:5173
- Have three terminal/browser tabs ready: the app in a browser, a text editor open to the three ontology files below, and a terminal for the one live Cypher query in Step 4.
- One-sentence framing to open with: *"Everything you're about to see runs against our own local Neo4j graph, built from 97 real Confluence pages about our Change-of-Address process — no synthetic demo data."*

## The one-slide mental model

```
Unstructured docs (Confluence/PDF)
        │  ingest + chunk + embed
        ▼
Rule-based + LLM extraction  ──── constrained to a fixed ontology (17 entity types, 11 relationship types)
        │
        ▼
Candidate Graph  ("Silver" — unreviewed, nothing here can be queried by an end user)
        │  human approves / edits / rejects  ← the only door into Gold
        ▼
Production Graph ("Gold" — approved-only, RDF-identified nodes)
        │  vector search → graph traversal
        ▼
Grounded answer with citations  (GraphRAG chat)
```

The through-line for the whole demo: **nothing reaches an answer unless a human approved it**, and **nothing extracted can invent a new type of thing without a human approving that too**. Say this once at the top; you'll refer back to it in Steps 3 and 5.

---

## Step 1 — Ontology: the rulebook (Dashboard page, then editor)

**Say:** "Before we ingest anything, we define what kinds of things and relationships are allowed to exist in this graph. This isn't a free-for-all LLM extraction — it's constrained."

1. Open `src/ontology/ontology.yaml`. Point out `entity_types:` (17 types: Document, Application, System, Service, Database, API, Process, Team, Technology, Policy, Role, Product, ExternalPartner, Tool, Check, Party, Channel) and `relationship_types:` (11 types). Each carries a keyword list the rule-based extractor matches against.
2. Open `src/ontology/rdf/core.ttl` — this is the same vocabulary expressed as OWL/RDF (`owl:Class`, `owl:ObjectProperty`, `rdfs:label`). This is the file that becomes the live graph's schema.
3. Open `src/ontology/rdf/domains/change_of_address.ttl` — a **worked example of extending the ontology without touching core.ttl**: it declares `coa:ChangeOfAddressProcess rdfs:subClassOf core:Process`. Say: "A new business domain ships its own file and subclasses the shared vocabulary — core.ttl never has to change."
4. Navigate to http://localhost:5173/ontology-preview and click **Regenerate Preview** — shows the same structure as a live, generated table (entities/relationships currently defined), proving the YAML and the running system agree.

---

## Step 2 — Ingestion + extraction (narrate only, ~1 min, no clicking)

**Say:** "97 Confluence pages went through this. Extraction has three layers, in order, and every layer is boxed in by the ontology from Step 1:"

1. **Deterministic rules** — keyword/pattern matches against the 17 types. Cannot invent a new type.
2. **LLM fallback** — only runs on chunks the rules found too few entities in; the LLM is still given the same fixed vocabulary and told to choose from it.
3. **`NO_FIT`** — if the LLM genuinely can't fit something into an existing type, it doesn't invent one. It creates a **Class Proposal** — visible and actionable in Step 3, never silently added to the ontology.

Full detail is written up in [`entity_type_governance.md`](entity_type_governance.md) if anyone wants to dig in after the demo.

---

## Step 3 — Approval flow: the Review page (the centerpiece)

Navigate to http://localhost:5173/review. **Say:** "Everything the model extracts lands here first — nothing skips this."

The four sections are now collapsible cards (this UI just shipped) so a reviewer can see all four counts on one screen without endless scrolling:

1. **Entity Review** — expand it. Filter to "Pending Review" and open **"parental responsibility"** (type `Role`) — a real pending item right now. Show the edit fields: name, definition, *and* business meaning are all editable before approval — a business reviewer can rename a term the model got half-right.
2. **Relationship Review** — expand it, open the pending relationship **`parental responsibility —REFERENCES→ MD1.50.33`** — same approve/edit/reject pattern, plus a domain/range advisory check (warns if a relationship type doesn't usually connect those two entity types — advisory only, never blocking, reviewer decides).
3. **Ambiguity Resolution** — expand it (currently empty — 0 pending right now, which is itself worth saying: *"this queue is empty because reviewers have already cleared it — I'll explain what it's for even though there's nothing in it today"*). This is where the system asks a human to disambiguate when it can't confidently merge/split entities on its own.
4. **Class Proposals** — expand it, open **"No Trace Marker (NTM)"** (confidence 0.70, suggested parent `Technology`). This is a live `NO_FIT` result from Step 2's Layer 3. Walk through the actual approval choice:
   - *Approve with the suggested parent* → writes `coa:NoTraceMarker rdfs:subClassOf core:Technology` into a domain `.ttl` file — a governed ontology extension, not a schema-less blob.
   - *Clear the suggested parent first* → still approvable, written as an **orphan class** (no subclass edge) — a valid, audited outcome, not a dead end.
   - *Reject* → discarded, nothing written.

**Key line to land here:** "There is no code path where an extracted entity, relationship, or new concept reaches the graph everyone else queries without a named human approving it in this screen."

---

## Step 4 — RDF triplets: static schema and the live graph

**Say:** "The ontology isn't just documentation — it's real RDF, and the live graph is RDF-identified too."

**4a. Static triples** — show `core.ttl` again, this time reading a snippet as actual triples:
```turtle
core:Process a owl:Class ;
    rdfs:label "Process" .

core:ESCALATES_TO a owl:ObjectProperty ;
    rdfs:domain core:Role ;
    rdfs:range core:Process .
```
Say: "Subject, predicate, object — this is the schema layer (T-box). No individual records live in this file, just the vocabulary."

**4b. Live triples from the actual Neo4j graph** — every Gold node carries a real `https://kg.local/ontology/...` URI and an `:Resource` label (enforced by a uniqueness constraint), which is what makes the *live graph* RDF-exportable, not just the static files. Run this against `kg-dev` (verified working this session):

```cypher
CALL n10s.rdf.export.cypher('MATCH (n:Entity) RETURN n LIMIT 3', {})
YIELD subject, predicate, object
RETURN subject, predicate, object
```

Real output from this exact query today:
```
subject: https://kg.local/ontology/entity/entity_role_account_managing_adult
predicate: neo4j://graph.schema#name       object: Account Managing Adult
predicate: neo4j://graph.schema#type       object: Role
predicate: http://www.w3.org/1999/02/22-rdf-syntax-ns#type   object: neo4j://graph.schema#Role
```
**Be upfront about one nuance if asked:** the *subject* IRIs are our real `kg.local` namespace; the *predicate* namespace currently falls back to Neo4j's internal `neo4j://graph.schema#` rather than our registered `core:` prefix, because n10s only honors a custom base schema namespace if it's set at initial graph-config time on an empty graph. Framing: "the graph is genuinely RDF-native and exportable today; pinning the predicate namespace to `core:` is a one-time config change on the next fresh load, not a re-architecture." (Detail in [`neo4j_n10s_setup.md`](neo4j_n10s_setup.md).)

---

## Step 5 — Retrieval: watch it traverse the graph

Navigate to http://localhost:5173/chat ("Ask the Knowledge Graph"). **Say:** "This only ever reads the Gold/approved graph — Candidate Graph data is structurally unreachable from this code path."

Ask, live: **"What is required for a Change of Address request?"**

Real answer returned this session (grounded, with citations — do not need to re-verify unless something changed):
> To initiate a Change of Address request... use the Postal Address Finder (PAF) to verify the accuracy of the new address (MD1.50.55)... confirm the reason for the request... select the account(s) that need a new card...
> **References:** MD1.50 - Q138, MD1.50.26, MD1.50.55, MD1.50.73, MD1.50.65, MD1.50.3, MD1.50.23, MD1.50.27, MD1.50.2

Then narrate the five real steps that just ran, each backed by an actual Cypher query in `src/graph/neo4j_loader.py`:

1. **Embed the question** into a vector.
2. **`search_chunks`** — `CALL db.index.vector.queryNodes('chunk_embedding', $top_k, $query_vector)` — vector similarity search over chunk embeddings, returns the most relevant document excerpts.
3. **`get_mentioned_entities`** — `MATCH (c:Chunk)-[:MENTIONS]->(e:Entity) WHERE c.id IN $chunk_ids` — which real entities (Role, Process, Document types...) those excerpts mention.
4. **`get_neighbors`** — `MATCH (e:Entity)-[rels*1..N]-(n:Entity)` — graph expansion outward from those entities (e.g. real relationship in this graph: `Postal Address Finder —REQUIRES→ COA [Change of Address] Process`), surfacing connected entities the vector search alone wouldn't have found.
5. **`get_linked_documents`** — forward-only `LEADS_TO` traversal between the source pages, producing "next step" suggestions.

All five results get assembled into one grounded context block and handed to the LLM in a single pass — say: "the model isn't guessing or deciding whether to look something up; retrieval is unconditional, every turn."

**Key line to land here:** "The citations aren't decoration — they're literally the chunk IDs and document names the graph traversal returned. You can click through and verify every claim against a real Confluence page."

---

## Step 5b — bonus, time permitting: show the receipts (Retrieval Trace)

Under the answer's sources, click **"View retrieval trace"** (or navigate the
sidebar to **Retrieval Trace** directly). **Say:** "Everything I just
narrated — the query, the entities, the traversal — isn't a black box. Here
it is, literally."

- The Cypher block is copy-pasteable straight into Neo4j Browser — offer to
  paste it live if the room wants proof.
- The graph snapshot below it is the actual chunks/entities/documents this
  answer's retrieval touched, colored to match Neo4j Browser's own palette.
- If a question happens to produce a disconnected result (multiple
  clusters), that's shown honestly rather than hidden — a good moment to say
  "we don't paper over messy retrieval, we surface it."

Skip this step if the room is short on time — Step 5's narration already
covers the same ground; this just makes it literal and clickable.

---

## Anticipated questions and how to answer them

- **"How do you stop hallucination?"** → Retrieval only reads the approved (Gold) graph; the LLM answer is always grounded in the assembled context and cites real source chunks (Step 5). Document content is wrapped in explicit untrusted-data delimiters so injected instructions inside a document can't hijack the model.
- **"What stops the model from inventing new categories of data?"** → The three-layer governance model in Step 2/3: rules and LLM extraction are both scoped to the fixed ontology; anything that doesn't fit becomes a reviewable Class Proposal, never an automatic schema change.
- **"Is this vendor-locked to local Neo4j?"** → No — `graph.provider` in `config.yaml` swaps between `neo4j`, `neo4j_aura`, and a Databricks/Cosmos path is mapped out in `local_to_databricks_mapping.md`; the driver is scheme-agnostic (`bolt://` vs `neo4j+s://`).
- **"Can a reviewer make a mistake that corrupts the graph?"** → Every approval/reject/edit is logged (`HistoryLog` in the UI, visible per-item); orphan classes and near-duplicate labels are flagged by guardrails (`guardrails.py`) rather than silently allowed.

## Live-check commands (run the morning of the demo)

```bash
curl -s http://localhost:8000/api/dashboard        # confirm current counts match this script
curl -s http://localhost:8000/api/class-proposals  # confirm "No Trace Marker (NTM)" is still NEW
```
If the numbers or example names have drifted, swap in whatever's currently pending — the mechanics described here don't change, only which specific item is live at demo time.
