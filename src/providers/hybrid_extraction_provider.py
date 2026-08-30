"""
HybridExtractionProvider: rule-based extraction first (fast, deterministic,
zero LLM cost) on every chunk, then LLM fallback only for chunks where
rule-based extraction found fewer than `min_entities_per_chunk` entities.
Composes the two existing providers behind the ExtractionProvider ABC rather
than reimplementing either extraction path - this is the seam that recovers
the LLM's recall for chunks the regex-based extractor structurally can't
cover, while keeping the LLM's workload to a fraction of the corpus instead
of every chunk.

Entities from both sources are merged by id (build_entity_id is shared
between the rule-based and Ollama providers, so a real-world entity that
both sides name identically collapses to one row; a name/type disagreement
between the two - e.g. abbreviation vs. full phrase - legitimately produces
two distinct candidate entities, the same "needs manual merge review" outcome
as running the two providers on separate ingests, see ontology.yaml).
"""

from __future__ import annotations

from collections import Counter

from config.app_config import AppConfig
from providers.extraction_provider import ExtractionProvider
from providers.ollama_extraction_provider import OllamaExtractionProvider
from providers.ontology_rules_extraction_provider import OntologyRulesExtractionProvider


def _merge_entities(
    entities_a: list[dict], mentions_a: list[dict], entities_b: list[dict], mentions_b: list[dict]
) -> tuple[list[dict], list[dict]]:
    entities_by_id = {e["id"]: e for e in entities_a}
    for entity in entities_b:
        entities_by_id.setdefault(entity["id"], entity)

    mentions = list(mentions_a)
    seen_mention_keys = {(m["chunk_id"], m["entity_id"]) for m in mentions_a}
    for mention in mentions_b:
        key = (mention["chunk_id"], mention["entity_id"])
        if key not in seen_mention_keys:
            seen_mention_keys.add(key)
            mentions.append(mention)

    return list(entities_by_id.values()), mentions


class HybridExtractionProvider(ExtractionProvider):
    def __init__(self, config: AppConfig) -> None:
        options = config.extraction.options.get("hybrid", {})
        self.min_entities_per_chunk = int(options.get("min_entities_per_chunk", 1))
        self._rules = OntologyRulesExtractionProvider()
        self._llm = OllamaExtractionProvider(config)
        self._fallback_chunk_ids: set[str] = set()

    def extract_entities(self, chunks: list[dict], ontology: dict) -> tuple[list[dict], list[dict]]:
        rule_entities, rule_mentions = self._rules.extract_entities(chunks, ontology)

        mention_counts = Counter(mention["chunk_id"] for mention in rule_mentions)
        fallback_chunks = [
            chunk for chunk in chunks if mention_counts[chunk["chunk_id"]] < self.min_entities_per_chunk
        ]
        self._fallback_chunk_ids = {chunk["chunk_id"] for chunk in fallback_chunks}

        if not fallback_chunks:
            return rule_entities, rule_mentions

        llm_entities, llm_mentions = self._llm.extract_entities(fallback_chunks, ontology)
        return _merge_entities(rule_entities, rule_mentions, llm_entities, llm_mentions)

    def extract_relationships(
        self, chunks: list[dict], entities: list[dict], mentions: list[dict], ontology: dict
    ) -> list[dict]:
        rule_chunks = [chunk for chunk in chunks if chunk["chunk_id"] not in self._fallback_chunk_ids]
        llm_chunks = [chunk for chunk in chunks if chunk["chunk_id"] in self._fallback_chunk_ids]

        relationships: list[dict] = []
        seen: set[tuple[str, str, str]] = set()

        def _add_all(rels: list[dict]) -> None:
            for rel in rels:
                key = (rel["source"], rel["relationship"], rel["target"])
                if key not in seen:
                    seen.add(key)
                    relationships.append(rel)

        if rule_chunks:
            _add_all(self._rules.extract_relationships(rule_chunks, entities, mentions, ontology))
        if llm_chunks:
            _add_all(self._llm.extract_relationships(llm_chunks, entities, mentions, ontology))

        return relationships

    def get_class_proposals(self) -> list[dict]:
        """Only the LLM leg can flag NO_FIT; the rule-based leg never
        produces proposals."""
        return self._llm.get_class_proposals()
