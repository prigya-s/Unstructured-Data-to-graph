# Dependency Diagram: Stage → Provider → Business Logic

This diagram exists to make one property visually checkable: **business
logic has zero inbound edges from config or environment.** Every arrow
into a business-logic module comes from a Stage passing it plain dicts/
dataclasses; every arrow into `config.yaml`/`os.environ` terminates at a
provider factory or a provider constructor, never at a business-logic
module directly.

```mermaid
flowchart LR
    CFG["config.yaml / AppConfig"]
    ENV["os.environ (.env)"]

    subgraph Factories["src/providers/__init__.py factories"]
        F1["get_storage_provider"]
        F2["get_document_source"]
        F3["get_embedding_provider"]
        F4["get_approval_provider"]
        F5["get_ontology_provider"]
        F6["get_graph_provider"]
        F7["get_extraction_provider"]
        F8["get_llm_provider"]
        F9["get_secrets_provider"]
        F10["get_auth_provider"]
    end

    CFG --> F1 & F2 & F3 & F4 & F5 & F6 & F7 & F8 & F9 & F10

    subgraph Providers["Provider implementations"]
        P1["LocalStorageProvider / *stub*"]
        P2["LocalFolderSource / ConfluenceExportSource / *stub*"]
        P3["LocalEmbeddingProvider (no-op) / OllamaEmbeddingProvider /\nAzureOpenAIEmbeddingProvider / *stub*"]
        P4["LocalOntologyRepository / FutureOntoBricksRepository"]
        P5["LocalOntologyProvider"]
        P6["Neo4jGraphProvider / Neo4jAuraGraphProvider /\nMockGraphProvider / *stub*"]
        P7["OntologyRulesExtractionProvider / SpacyExtractionProvider /\nOllamaExtractionProvider / AzureOpenAIExtractionProvider /\nHybridExtractionProvider"]
        P8["OllamaLLMProvider / AzureOpenAILLMProvider"]
        P9["EnvSecretsProvider / *stub*"]
        P10["LocalAuthProvider / *stub*"]
    end

    F1 --> P1
    F2 --> P2
    F3 --> P3
    F4 --> P4
    F5 --> P5
    F6 --> P6
    F7 --> P7
    F8 --> P8
    F9 --> P9
    F10 --> P10
    ENV --> P6
    ENV --> P9

    subgraph Stages["src/pipeline/stages/*.py"]
        S1["IngestionStage"]
        S2["ExtractionStage"]
        S3["ChunkingStage"]
        S4["EmbeddingStage"]
        S5["EntityExtractionStage"]
        S6["RelationshipExtractionStage"]
        S7["ApprovalStage"]
        SCG["CandidateGraphStage"]
        S8["OntologyStage"]
        S9["GraphStage"]
    end

    P1 -.reads/writes via.-> S1 & S2 & S3 & S4 & S5 & S6 & S8 & S9 & SCG
    P2 -.reads via.-> S1 & S2
    P3 -.calls.-> S4
    P4 -.reads/writes via.-> S7 & SCG & S8 & S9
    P5 -.calls.-> S8 & S9
    P6 -.calls.-> SCG & S9
    P7 -.calls.-> S5 & S6

    subgraph BusinessLogic["Business logic - zero inbound edges from CFG/ENV"]
        B1["extract/docling_parser.py"]
        B2["chunking/semantic_chunker.py"]
        B3["extraction/entity_extractor.py\n(+domain_gazetteer)"]
        B4["extraction/relationship_extractor.py\n(+REQUIRES/APPLIES_TO)"]
        B5["review/candidate_builder.py"]
        B6["review/ontology_generator.py + publisher.py"]
        B7["graph/graph_builder.py\n(+page-link/LEADS_TO extraction)"]
        B8["graph/neo4j_loader.py\n(+get_linked_documents,\n+CHILD_OF_PAGE/LEADS_TO structural edges)"]
    end

    S2 -->|"convert_to_markdown(path)"| B1
    S3 -->|"chunk_markdown(markdown, doc_id)"| B2
    S5 -->|"extract_entities(chunks, ontology)"| B3
    S6 -->|"extract_relationships(chunks, entities, mentions, ontology)"| B4
    P7 -.falls back to LLM via.-> S5 & S6
    S7 -->|"build_candidates(entities, mentions, rels, chunks, repo)"| B5
    SCG -->|"build_candidate_graph(...)"| B7
    S8 -->|"publish_ontology(repo, output_path)"| B6
    S9 -->|"load_approved_for_graph(repo, mentions)"| B6
    S9 -->|"build_graph(docs, chunks, entities, mentions, rels)"| B7
    P6 -->|"Neo4jLoader(uri, user, password, database)"| B8
```

## What to check when reviewing this diagram

- No arrow goes from `CFG`/`ENV` directly into the `BusinessLogic` subgraph -
  every path into it passes through a Stage, which only ever hands the
  business-logic function plain data (dicts, lists, an `OntologyRepository`
  instance) - never a `Path`, an env var, or a config value. This still
  holds for the MYDET-domain-fit additions: `entity_extractor.py`'s
  `domain_gazetteer` lookups and `relationship_extractor.py`'s
  `REQUIRES`/`APPLIES_TO` trigger matching are driven entirely by
  `ontology.yaml` content passed in as a plain
  dict by the Stage - no new config/env edge was added.
- `HybridExtractionProvider` (`P7`) composes two other providers (a
  rules-first leg, an LLM provider as fallback for low-yield chunks) but is
  itself still just a provider selected by `extraction.provider: hybrid` -
  `S5`/`S6` call it exactly like any other `ExtractionProvider`, with no
  extra inbound config edge. The rules-first leg is itself config-selected
  via `extraction.options.hybrid.rules_backend: ontology_rules |
  spacy_rules` (`_build_rules_provider()`), defaulting to
  `OntologyRulesExtractionProvider` - this is one more config-driven branch
  inside `P7`, not a new inbound edge from `CFG` to a new box.
- `graph_builder.py`'s page-link (`LEADS_TO`) extraction reads only the
  `documents` list already passed into `build_graph()`/
  `build_candidate_graph()` by `S9`/`SCG` - no new inbound edge from
  `CFG`/`ENV` either.
- `Neo4jGraphProvider`/`Neo4jAuraGraphProvider` are the providers that read
  `ENV` directly (they always did, via `Neo4jLoader`) - they also read
  `CFG` for *which* env var names to use, but the values themselves still
  flow through `os.environ`, same as before. `Neo4jAuraGraphProvider`
  subclasses `Neo4jGraphProvider` and reuses the same env-var-name
  indirection.
- `CandidateGraphStage` (`SCG`) is a second consumer of `P6`
  (`get_graph_provider`), alongside `GraphStage` (`S9`) - it loads the
  Candidate Graph into the same graph database under distinct
  `:CandidateEntity`/`:CANDIDATE_RELATIONSHIP` labels. See
  [graph_governance.md](graph_governance.md) for why that doesn't
  compromise retrieval blindness.
