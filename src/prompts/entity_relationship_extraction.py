"""
Entity + relationship extraction prompt for OllamaExtractionProvider (see
providers/ollama_extraction_provider.py). Externalized so the prompt wording
can be reviewed/tuned without touching provider logic - see
src/prompts/__init__.py.

The model classifies into the *existing* ontology vocabulary (entity_types/
relationship_types from ontology.yaml) rather than inventing new categories,
so ontology governance is unchanged from the rule-based extractor.

The prompt is always batch-shaped (one or more chunks per call): most of
this corpus's chunks are far smaller than the model's context window, so
batching several into one call cuts round-trips without changing the
per-chunk extraction contract.
"""

from __future__ import annotations

import json

SYSTEM_PROMPT = (
    "You are an information-extraction engine for an enterprise knowledge "
    "graph. You are given one or more document chunks, each labeled with its "
    "chunk_id, and a fixed ontology of allowed entity types and relationship "
    "types. Extract only entities and relationships that use those exact "
    "type names - never invent a new type. Treat each chunk independently: "
    "only extract relationships between entities that appear in the same "
    "chunk. If nothing in a chunk matches an allowed type, return empty "
    "lists for that chunk_id. Respond with a single JSON object and nothing "
    "else - no prose, no markdown code fences."
)

_OUTPUT_SCHEMA = {
    "chunks": [
        {
            "chunk_id": "must match one of the chunk_id values given below, exactly",
            "entities": [
                {"name": "string", "type": "one of the allowed entity types", "confidence_score": "number 0-1"}
            ],
            "relationships": [
                {
                    "source": "an entity name from this chunk's entities list",
                    "relationship": "one of the allowed relationship types",
                    "target": "an entity name from this chunk's entities list",
                    "confidence_score": "number 0-1",
                }
            ],
        }
    ]
}


def build_extraction_prompt(chunks: list[dict], ontology: dict) -> str:
    entity_types = sorted((ontology.get("entity_types") or {}).keys())
    relationship_types = sorted((ontology.get("relationship_types") or {}).keys())

    chunks_block = "\n\n".join(
        f'chunk_id: "{chunk["chunk_id"]}"\n"""\n{chunk["content"]}\n"""' for chunk in chunks
    )

    return (
        f"Allowed entity types: {', '.join(entity_types)}\n"
        f"Allowed relationship types: {', '.join(relationship_types)}\n\n"
        f"Respond using exactly this JSON shape, with one entry in \"chunks\" "
        f"for every chunk_id below (any order):\n{json.dumps(_OUTPUT_SCHEMA, indent=2)}\n\n"
        f"Document chunks:\n{chunks_block}"
    )
