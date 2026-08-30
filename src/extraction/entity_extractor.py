"""
Phase 4: Ontology-based entity extraction.

Deterministic, offline extraction of ontology entities from chunk text.
Candidate noun phrases (sequences of capitalized words) are classified
against the entity types defined in ontology.yaml: a phrase is typed
by its final word matching a type's keyword list, or by direct lookup
in the technology gazetteer.
"""

from __future__ import annotations

import re

from .id_utils import build_entity_id

_GLUE_WORDS = {"of", "the", "for", "to"}
_GLUE_PATTERN = "|".join(sorted(_GLUE_WORDS))

# A capitalized "word" may contain internal hyphens (e.g. "Account-Managing"),
# and up to 4 more tokens may follow - each either another capitalized word or
# one of the lowercase glue words above (e.g. "Change of Address"). The
# (?<!\.) lookbehind still blocks gluing across a sentence-ending period.
_PHRASE_RE = re.compile(
    r"\b[A-Z][A-Za-z0-9.\-]*"
    rf"(?:(?<!\.)\s+(?:[A-Z][A-Za-z0-9.\-]*|(?:{_GLUE_PATTERN}))){{0,4}}\b"
)

_STRIP_LEADING = {
    "The", "This", "That", "These", "Those", "All", "It", "In", "On", "For",
    "And", "Or", "A", "An",
}

# A matched phrase may legitimately end on a glue word if the capitalized
# word that would have followed it wasn't itself a valid phrase continuation
# (e.g. lowercased in the source, or end of sentence) - trim those trailing
# glue words so "Change of" doesn't outlive "Change of Address" as its own hit.
_STRIP_TRAILING = _GLUE_WORDS


def _build_suffix_map(ontology: dict) -> dict[str, str]:
    suffix_map: dict[str, str] = {}
    for entity_type, cfg in (ontology.get("entity_types") or {}).items():
        for keyword in cfg.get("keywords") or []:
            suffix_map[keyword.lower()] = entity_type
    return suffix_map


def _build_gazetteer(ontology: dict) -> set[str]:
    return {t.lower() for t in ontology.get("technology_gazetteer") or []}


def _build_domain_gazetteer(ontology: dict) -> dict[str, str]:
    """term -> entity_type, e.g. {"IVR": "Channel", "CAT": "Check"}.

    Unlike the flat technology_gazetteer (always "Technology"), each entry
    here is a domain acronym that types to something else entirely. Matched
    by exact case (acronyms), not lowercased, so it can't collide with an
    ordinary capitalized word that happens to share letters."""
    return dict(ontology.get("domain_gazetteer") or {})


def _clean_phrase(phrase: str) -> str:
    tokens = phrase.split()
    while tokens and tokens[0] in _STRIP_LEADING:
        tokens.pop(0)
    while tokens and tokens[-1] in _STRIP_TRAILING:
        tokens.pop()
    return " ".join(tokens)


def _classify(
    phrase: str,
    suffix_map: dict[str, str],
    gazetteer: set[str],
    domain_gazetteer: dict[str, str],
) -> str | None:
    tokens = phrase.split()
    if not tokens:
        return None

    last_token = tokens[-1].lower().rstrip(".,;:")
    is_multi_word = len(tokens) > 1
    is_acronym = tokens[-1].isupper() and 2 <= len(tokens[-1]) <= 6
    is_gazetteer_hit = phrase.lower() in gazetteer or last_token in gazetteer

    if last_token in suffix_map:
        entity_type = suffix_map[last_token]
        if entity_type == "Document":
            return None
        if is_multi_word or is_acronym or is_gazetteer_hit:
            return entity_type
        return None

    domain_type = domain_gazetteer.get(tokens[-1].rstrip(".,;:"))
    if domain_type:
        return domain_type

    if is_gazetteer_hit:
        return "Technology"

    return None


def extract_entities_from_chunk(chunk: dict, ontology: dict) -> list[dict]:
    """Return raw (non-deduplicated) entity mentions found in a single chunk.

    Each item: {"name", "type", "source_chunk"}. Standalone convenience
    wrapper - rebuilds the ontology-derived lookup structures on every call,
    which is fine for a single chunk but wasteful across many (see
    extract_entities, which builds them once and reuses them)."""
    return _extract_from_chunk(
        chunk,
        _build_suffix_map(ontology),
        _build_gazetteer(ontology),
        _build_domain_gazetteer(ontology),
    )


def _extract_from_chunk(
    chunk: dict,
    suffix_map: dict[str, str],
    gazetteer: set[str],
    domain_gazetteer: dict[str, str],
) -> list[dict]:
    found: list[dict] = []
    seen_in_chunk: set[tuple[str, str]] = set()

    def _add(name: str, entity_type: str) -> None:
        key = (name.lower(), entity_type)
        if key in seen_in_chunk:
            return
        seen_in_chunk.add(key)
        found.append({"name": name, "type": entity_type, "source_chunk": chunk["chunk_id"]})

    for match in _PHRASE_RE.finditer(chunk["content"]):
        phrase = _clean_phrase(match.group(0).strip())
        if not phrase:
            continue
        entity_type = _classify(phrase, suffix_map, gazetteer, domain_gazetteer)
        if entity_type is None:
            continue
        _add(phrase, entity_type)

    return found


def extract_entities(chunks: list[dict], ontology: dict) -> tuple[list[dict], list[dict]]:
    """Extract and deduplicate entities across all chunks.

    Returns (entities, mentions):
      entities: [{"id", "name", "type", "source_chunk"}] deduplicated by
                (name.lower(), type), keeping the first chunk seen.
      mentions: [{"chunk_id", "entity_id"}] one row per (chunk, entity)
                pair, including every chunk an entity appears in.
    """
    suffix_map = _build_suffix_map(ontology)
    gazetteer = _build_gazetteer(ontology)
    domain_gazetteer = _build_domain_gazetteer(ontology)

    entities_by_key: dict[tuple[str, str], dict] = {}
    mentions: list[dict] = []
    mention_keys: set[tuple[str, str]] = set()

    for chunk in chunks:
        raw_entities = _extract_from_chunk(chunk, suffix_map, gazetteer, domain_gazetteer)
        for raw in raw_entities:
            key = (raw["name"].lower(), raw["type"])
            if key not in entities_by_key:
                entity_id = build_entity_id(raw["type"], raw["name"])
                entities_by_key[key] = {
                    "id": entity_id,
                    "name": raw["name"],
                    "type": raw["type"],
                    "source_chunk": raw["source_chunk"],
                }

            entity_id = entities_by_key[key]["id"]
            mention_key = (chunk["chunk_id"], entity_id)
            if mention_key not in mention_keys:
                mention_keys.add(mention_key)
                mentions.append({"chunk_id": chunk["chunk_id"], "entity_id": entity_id})

    entities = list(entities_by_key.values())
    return entities, mentions
