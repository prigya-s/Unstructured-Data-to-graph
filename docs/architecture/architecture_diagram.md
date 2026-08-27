# Target Architecture

Each box below is annotated with whether an implementation is real/working
today (●) or is still a documented `NotImplementedError` stub (○). Multiple
● boxes in the same seam (e.g. Ollama and Azure OpenAI for embeddings) are
both real, working alternatives selected by `config.yaml`'s `provider:`
field (or the `ai.mode` shortcut) - not a "real vs. stub" pair. Switching
between them, or from ● to ○, is a `config.yaml` change plus (for ○)
implementing that one stub class - no other box changes.

```mermaid
flowchart TB
    subgraph Sources["Document Sources"]
        LF["● Local Folder\n(LocalFolderSource)"]
        CE["● Confluence Export\n(ConfluenceExportSource - default,\nreads docs/MYDET)"]
        CF["○ Confluence live API\n(ConfluenceSource - stub)"]
        SP["○ SharePoint\n(SharePointSource - stub)"]
    end

    subgraph Ingest["Ingestion / Extraction"]
        ING["IngestionStage"]
        EXT["ExtractionStage\n-> docling_parser (unchanged)"]
    end

    subgraph Bronze["Bronze"]
        BRZ["● Local JSON\n○ Unity Catalog / Volumes\n(StorageProvider)"]
    end

    subgraph Silver["Silver"]
        CHK["ChunkingStage\n-> semantic_chunker (unchanged)"]
        EMB["EmbeddingStage\n● ollama (bge-m3, default local)\n● azure_openai (real, alt)\n○ local_noop (pass-through, opt-in offline)\n○ databricks (stub)"]
        SLV["● Local JSON\n○ Delta Table\n(StorageProvider)"]
    end

    subgraph GoldExtract["Gold: Extraction"]
        EE["EntityExtractionStage\n-> entity_extractor\n(+domain_gazetteer, +heading-to-Topic)"]
        RE["RelationshipExtractionStage\n-> relationship_extractor\n(+REQUIRES/APPLIES_TO)"]
        HYB["hybrid extraction: ontology_rules first,\nollama (qwen3:14b) fallback for\nlow-yield chunks"]
    end

    subgraph Review["Business Review & Approval"]
        APP["ApprovalStage\n-> candidate_builder (unchanged)"]
        UI["● React + FastAPI\n(web/ + api/, bulk-approve)\n○ OntoBricks (FutureOntoBricksRepository - stub)"]
    end

    subgraph CandGraph["Silver: Candidate Graph"]
        CGS["CandidateGraphStage\n-> graph_builder\n(+page-link/LEADS_TO extraction)"]
    end

    subgraph GoldApproved["Gold: Approved"]
        ONT["OntologyStage\n-> ontology_generator/publisher (unchanged)"]
        GR["GraphStage\n-> graph_builder (unchanged)"]
    end

    subgraph GraphDB["Graph Database"]
        NEO["● Neo4j\n(Neo4jGraphProvider -> Neo4jLoader)"]
        AURA["● Neo4j AuraDB\n(Neo4jAuraGraphProvider,\nsubclasses Neo4jGraphProvider)"]
        MOCK["● Mock / in-memory\n(MockGraphProvider - dev/tests)"]
        COS["○ Cosmos DB\n(CosmosGraphProvider - stub)"]
    end

    subgraph Retrieval["GraphRAG Retrieval / Agent Layer"]
        SVC["retrieval/graphrag_service.py\nembed query -> search_chunks ->\nget_mentioned_entities -> get_neighbors ->\nget_linked_documents (next steps)"]
        AGT["agents/graphrag_agent.py\nGraphRAGAgent: calls retrieve_context()\ndirectly, no tool-call turn; streamed\nrun_stream(), QueryCache short-circuit"]
        LLM["● ollama (llama3.2:3b, default local)\n● azure_openai (real, alt)\n(LLMProvider)"]
        CONV["Ask the Knowledge Graph\n(React page / `chat` CLI, both streamed)"]
    end

    LF --> ING
    CE --> ING
    CF --> ING
    SP --> ING
    ING --> EXT --> BRZ
    BRZ --> CHK --> EMB --> SLV
    SLV --> EE --> RE
    HYB -.-> EE
    RE --> APP --> UI
    UI --> CGS
    CGS -->|"Silver JSON"| SLV
    CGS -->|":CandidateEntity /\n:CANDIDATE_RELATIONSHIP labels"| NEO
    UI --> ONT
    UI --> GR
    ONT --> GoldApproved
    GR -->|"unlabeled Gold nodes"| NEO
    GR --> AURA
    GR --> COS
    GR --> MOCK
    NEO --> SVC
    AURA --> SVC
    SVC --> AGT
    LLM --> AGT
    AGT --> CONV
```

## Reading the diagram

- **Solid business-logic boxes** (`docling_parser`, `semantic_chunker`,
  `entity_extractor`, `relationship_extractor`, `candidate_builder`,
  `ontology_generator`/`publisher`, `graph_builder`, `neo4j_loader`) appear
  unchanged/additive inside their stage - they have no inbound edge from
  `config.yaml` or `os.environ`. See [dependency_diagram.md](dependency_diagram.md)
  for the explicit proof of that. `entity_extractor`/`relationship_extractor`
  gained the `domain_gazetteer`, heading-to-`Topic` promotion, and
  `REQUIRES`/`APPLIES_TO` logic as additive business logic, still driven
  entirely by `ontology.yaml` content, not by config/env branches.
  `graph_builder`/`neo4j_loader` gained page-link (`LEADS_TO`) extraction
  and `get_linked_documents()` the same way.
- **Every other box** is a provider interface, selected by `config.yaml`'s
  `provider:` fields (or the `ai.mode: local`/`azure` shortcut for
  embedding/extraction/llm). `EmbeddingStage`, `ExtractionStage`'s hybrid
  path, and the retrieval layer's `LLMProvider` each have two real (●)
  implementations today (Ollama and Azure OpenAI), not one real and one
  stub - `local_noop`/`ontology_rules`-only extraction remain available as
  an explicit opt-in for fully offline runs.
- **Candidate Graph reaches Neo4j too**, but under `:CandidateEntity`/
  `:CANDIDATE_RELATIONSHIP` labels that the retrieval layer and Production
  Graph page never query - see [graph_governance.md](graph_governance.md)
  for exactly how that exclusion is enforced.
- **The retrieval/agent layer** (bottom subgraph) only reads from
  `GraphDB`'s unlabeled Gold nodes; it has no path back to `Review` or
  `CandGraph`.
