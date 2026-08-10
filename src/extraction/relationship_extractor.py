"""
Phase 5: Relationship extraction.

For every chunk, entities mentioned in the same sentence are checked
against the ontology's relationship triggers (e.g. "uses", "depends on").
If a trigger phrase sits between two distinct entity mentions, a
directed relationship is emitted from the nearest preceding entity to
the nearest following entity.
"""

from __future__ import annotations

import re

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(normalized) if s.strip()]


def _build_relationship_triggers(ontology: dict) -> list[tuple[str, str]]:
    """Return (relationship_type, trigger_phrase) pairs, longest triggers
    first so e.g. "depends on" is matched before a shorter overlapping
    trigger would be."""
    pairs: list[tuple[str, str]] = []
    for rel_type, cfg in (ontology.get("relationship_types") or {}).items():
        for trigger in cfg.get("triggers") or []:
            pairs.append((rel_type, trigger.lower()))
    pairs.sort(key=lambda p: len(p[1]), reverse=True)
    return pairs


def extract_relationships_from_chunk(
    chunk: dict,
    entities_in_chunk: list[dict],
    ontology: dict,
) -> list[dict]:
    """entities_in_chunk: entities (with id/name/type) known to be mentioned
    in this chunk. Returns [{"source", "relationship", "target", "source_chunk"}].
    """
    if len(entities_in_chunk) < 2:
        return []

    triggers = _build_relationship_triggers(ontology)
    results: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    for sentence in _split_sentences(chunk["content"]):
        lower_sentence = sentence.lower()

        present = []
        for entity in entities_in_chunk:
            pos = lower_sentence.find(entity["name"].lower())
            if pos != -1:
                present.append((pos, entity))

        if len(present) < 2:
            continue

        matched_trigger_spans: list[tuple[int, int, str]] = []
        for rel_type, trigger in triggers:
            start = 0
            while True:
                idx = lower_sentence.find(trigger, start)
                if idx == -1:
                    break
                matched_trigger_spans.append((idx, idx + len(trigger), rel_type))
                start = idx + len(trigger)

        for trig_start, trig_end, rel_type in matched_trigger_spans:
            before = [(pos, e) for pos, e in present if pos < trig_start]
            after = [(pos, e) for pos, e in present if pos >= trig_end]
            if not before or not after:
                continue

            src_pos, src_entity = max(before, key=lambda pair: pair[0])
            tgt_pos, tgt_entity = min(after, key=lambda pair: pair[0])

            if src_entity["id"] == tgt_entity["id"]:
                continue

            key = (src_entity["id"], rel_type, tgt_entity["id"])
            if key in seen:
                continue
            seen.add(key)

            results.append(
                {
                    "source": src_entity["id"],
                    "relationship": rel_type,
                    "target": tgt_entity["id"],
                    "source_chunk": chunk["chunk_id"],
                }
            )

    return results


def extract_relationships(
    chunks: list[dict],
    entities: list[dict],
    mentions: list[dict],
    ontology: dict,
) -> list[dict]:
    """Extract relationships for all chunks.

    entities: deduplicated entity list [{"id","name","type","source_chunk"}]
    mentions: [{"chunk_id","entity_id"}] mapping chunks to entities they mention
    """
    entity_by_id = {e["id"]: e for e in entities}
    entities_per_chunk: dict[str, list[dict]] = {}
    for mention in mentions:
        entities_per_chunk.setdefault(mention["chunk_id"], []).append(
            entity_by_id[mention["entity_id"]]
        )

    all_relationships: list[dict] = []
    seen_global: set[tuple[str, str, str]] = set()

    for chunk in chunks:
        chunk_entities = entities_per_chunk.get(chunk["chunk_id"], [])
        relationships = extract_relationships_from_chunk(chunk, chunk_entities, ontology)
        for rel in relationships:
            key = (rel["source"], rel["relationship"], rel["target"])
            if key in seen_global:
                continue
            all_relationships.append(rel)
            seen_global.add(key)

    return all_relationships
