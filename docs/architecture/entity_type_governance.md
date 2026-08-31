# Entity Type Governance: Staying Inside the Ontology

## In plain terms

After the first ingestion, the ontology ended up with a real, working set of
entity types. The natural worry going into every ingestion after that is:
will the next batch of documents just keep adding more types, until the
ontology sprawls into something nobody agreed to?

It won't, because nothing in the pipeline is allowed to invent a type on its
own. Three checks stand between a raw document and the ontology, each one
stricter than the last:

- **First pass — a fixed checklist.** Every document is scanned by simple,
  deterministic matching against the entity types that already exist. This
  pass is physically incapable of producing anything else — it either finds
  a match on the existing list or finds nothing.
- **Second pass — a second opinion, same checklist.** Only for the parts the
  first pass came up empty on, an AI model takes a look. It's given the
  exact same list of allowed types and told plainly: never invent a new
  type. If it can match what it sees to something already on the list, it
  does.
- **The one exception is a suggestion box, not a door.** If the AI genuinely
  can't match something to any existing type, it doesn't add one. It writes
  the idea down — what it saw, what existing type it's closest to — and
  drops it in a review queue. Nothing changes in the ontology until a person
  looks at that suggestion and explicitly approves it.

So the answer to "how do we make sure new data goes into the existing types
first" isn't a setting to turn on — it's already how the pipeline is built.
The one thing worth doing every ingestion is checking that suggestion box
(the **Class Proposals** queue) so genuine gaps get a deliberate yes or no,
instead of sitting there unreviewed.

The rest of this document is a technical reference for engineers — the exact
code paths, the config knobs, and what approving a proposal actually writes.

## Summary

```
Chunk text
  -> Rule-based match against ontology.yaml's existing entity_types
     (OntologyRulesExtractionProvider) - runs on every chunk, cannot
     produce a type outside this list, drops unmatched phrases silently
  -> Found >= extraction.hybrid.min_entities_per_chunk entities? ---- yes -> done
       |
       no
       v
     LLM fallback (OllamaExtractionProvider), given the same allowed-type
     list and told never to invent a new one
  -> Matches an existing type? -------------------------------------- yes -> done
       |
       no (NO_FIT, used sparingly)
       v
     Class Proposal (Silver, status=NEW) - queued at /api/class-proposals,
     ontology and hierarchy unchanged until a reviewer acts
  -> Reviewer rejects --------------------------------------------- discarded, no change
  -> Reviewer approves -> near-duplicate-name guardrail, then a new
     *subclass* (not a new root type) is appended under an existing
     parent into a domain .ttl file
```

`extraction.provider: hybrid` (the default in `config.yaml`) runs the first
two stages; `ontology_rules` alone skips the LLM fallback entirely (see
Configuration below).

## Layer 1: the rule-based pass cannot produce a new type

[`entity_extractor.py`](../../src/extraction/entity_extractor.py) (wrapped by
`OntologyRulesExtractionProvider`) builds its matching tables — the
keyword-suffix map, the flat technology gazetteer, the acronym-to-type
gazetteer — entirely from `entity_types` / `technology_gazetteer` /
`domain_gazetteer` in `ontology.yaml`. `_classify()` either returns one of
those existing type names or `None`; there is no other return path. A
phrase that matches nothing is dropped from that pass, not assigned a
placeholder type.

## Layer 2: the LLM fallback is scoped to the same vocabulary

`HybridExtractionProvider` (`src/providers/hybrid_extraction_provider.py`)
runs the rule-based pass on every chunk first, then only hands a chunk to
the LLM (`OllamaExtractionProvider`) if the rule-based pass found fewer than
`extraction.hybrid.min_entities_per_chunk` entities in it (default `1` — a
chunk with zero rule-based hits gets a second look; anything else doesn't).

The prompt the LLM receives
([`entity_relationship_extraction.py`](../../src/prompts/entity_relationship_extraction.py))
lists only the entity/relationship type names already in `ontology.yaml`
and states directly: *"Extract only entities and relationships that use
those exact type names — never invent a new type name."* The one escape
hatch, `NO_FIT`, is described as an exception to use *"sparingly: at most
one or two per chunk, only for concepts you are confident a human reviewer
would agree deserve a new ontology class."*

## Layer 3: NO_FIT produces a proposal, never a type

When the LLM does flag `NO_FIT`, `OllamaExtractionProvider._collect_no_fit()`
records the name, its evidence snippet, and a `suggested_parent` (cleared if
the model suggested something that isn't itself an allowed type). This is
plain data — nothing is written to the ontology yet.

`ApprovalStage` drains those rows through
[`candidate_builder.build_class_proposals()`](../../src/review/candidate_builder.py),
which turns each into a `ClassProposal` (`status: NEW`) and persists it via
`OntologyRepository.save_class_proposals()`. A proposal that already reached
a terminal status (`APPROVED`/`REJECTED`/`MERGED`) on a prior ingest is left
untouched by a repeat run — same idempotency rule as candidate
entities/relationships.

From there it's a normal review queue, `GET /api/class-proposals`
([`class_proposals.py`](../../api/routers/class_proposals.py)):

- **Save** — a reviewer can edit `suggested_parent` and `target_domain`
  before deciding.
- **Reject** — status becomes `REJECTED`; nothing else changes.
- **Approve** — `check_near_duplicate_labels()` first blocks the approval if
  the proposed name looks like a near-duplicate of a class that already
  exists (rename/reject instead of creating a look-alike). If it passes,
  `ontology.rdf.writer.append_class_to_domain()` writes a new `owl:Class`
  that is a **subclass of the suggested (or edited) parent type**, into a
  domain `.ttl` file (`target_domain`, defaulting to `extensions`) — not a
  new root entity type, and not an edit to `ontology.yaml` itself. This is
  the same core→domain extension mechanism documented in
  [owl_turtle_ontology.md](owl_turtle_ontology.md).

## Configuration reference

| Key | Values | Effect |
|---|---|---|
| `extraction.provider` | `ontology_rules` \| `ollama` \| `azure_openai` \| `hybrid` | `ontology_rules`: deterministic only — zero chance of a class proposal, but a chunk with no keyword match yields no entities at all. `hybrid` (default): rules first, LLM only for low-yield chunks, NO_FIT possible but rare and always review-gated. `ollama`/`azure_openai` alone: every chunk goes through the LLM. |
| `extraction.hybrid.min_entities_per_chunk` | integer, default `1` | Raising it sends more chunks to the LLM fallback (more recall, more chances for a NO_FIT proposal); lowering it (or using `ontology_rules`) keeps ingestion fully deterministic. |

## Operational guidance for repeat ingestion

- No configuration change is required to keep new ingestions inside the
  existing entity types — it's the default behavior of `extraction.provider:
  hybrid`.
- After each ingest, check `/api/class-proposals` (or the Class Proposals
  review page) for anything new. This is the only place a genuinely new
  type can enter the ontology, and it only does so with an explicit
  approval — an unreviewed queue is a paused decision, not a safe default.
- If even review-gated proposals are unwanted — e.g. a fully locked-down
  ontology for a given environment — set `extraction.provider:
  ontology_rules`. Unmatched phrases are then simply not extracted, with no
  proposal generated, at the cost of missing entities that a keyword match
  alone can't find.

## Files

- `src/extraction/entity_extractor.py` — deterministic keyword/gazetteer matcher
- `src/providers/ontology_rules_extraction_provider.py` — `ExtractionProvider` wrapper around it
- `src/providers/ollama_extraction_provider.py` — LLM extraction + `NO_FIT` collection
- `src/providers/hybrid_extraction_provider.py` — rules-first, LLM-fallback composition
- `src/prompts/entity_relationship_extraction.py` — the prompt enforcing "never invent a new type"
- `src/review/candidate_builder.py` — `build_class_proposals()`
- `src/review/models.py` — `ClassProposal`
- `api/routers/class_proposals.py` — review endpoints (save/approve/reject)
- `src/ontology/rdf/writer.py` — `append_class_to_domain()`
- `src/ontology/rdf/guardrails.py` — `check_near_duplicate_labels()`
