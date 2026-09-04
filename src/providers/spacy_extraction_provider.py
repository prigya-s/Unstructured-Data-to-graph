"""
SpacyExtractionProvider: NLP-based ExtractionProvider - delegates entity
extraction to extraction.spacy_entity_extractor (spaCy tokenizer/sentence
pipeline + an EntityRuler seeded from ontology.yaml, same 17 entity types as
the regex-based extractor) and relationship extraction to the existing,
unmodified extraction.relationship_extractor module.

Same governance guarantee as OntologyRulesExtractionProvider: every entity
this emits is one of the fixed ontology types, so get_class_proposals() stays
the ABC's no-op default - it cannot flag NO_FIT. When ambiguous/novel-concept
discovery is needed, pair this with an LLM leg (see hybrid_extraction_provider's
`rules_backend` option) rather than expecting this provider to self-flag it.
"""

from __future__ import annotations

from extraction import relationship_extractor, spacy_entity_extractor
from providers.extraction_provider import ExtractionProvider


class SpacyExtractionProvider(ExtractionProvider):
    def extract_entities(self, chunks: list[dict], ontology: dict) -> tuple[list[dict], list[dict]]:
        return spacy_entity_extractor.extract_entities(chunks, ontology)

    def extract_relationships(
        self, chunks: list[dict], entities: list[dict], mentions: list[dict], ontology: dict
    ) -> list[dict]:
        return relationship_extractor.extract_relationships(chunks, entities, mentions, ontology)
