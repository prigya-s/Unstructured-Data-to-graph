"""
NLP-based entity extraction, using spaCy instead of the hand-rolled regex in
entity_extractor.py. Ports the same ontology-driven classification - the
same 17 entity types, the same domain_gazetteer/technology_gazetteer/
per-type keywords data in ontology.yaml, matched by build_nlp() into a
spaCy EntityRuler - so the governance guarantee is unchanged: a pattern can
only ever exist for a type already declared in ontology.yaml, and there is
no path from this module to a type outside that fixed set.

No pretrained spaCy language model is downloaded or required. build_nlp()
uses spacy.blank("en") + a sentencizer + an EntityRuler seeded entirely from
the ontology dict passed in, so this stays as offline/deterministic as the
regex extractor it can replace - the benefit over the regex is spaCy's
tokenizer/sentence handling (Unicode punctuation, abbreviations, contractions)
across varied unstructured source documents, and a pipeline object that a
later trained NER component (Phase 2) can slot into without touching
callers - see providers/spacy_extraction_provider.py.
"""

from __future__ import annotations

import spacy
from spacy.language import Language
from spacy.tokenizer import Tokenizer
from spacy.util import compile_infix_regex

from .entity_extractor import _GLUE_WORDS, _clean_phrase
from .id_utils import build_entity_id

_CAP_WORD = r"[A-Z][A-Za-z0-9.\-]*"
_LEAD_TOKEN_RE = rf"^{_CAP_WORD}$"
_REST_TOKEN_RE = rf"^({_CAP_WORD}|{'|'.join(sorted(_GLUE_WORDS))})$"


def _keyword_patterns(ontology: dict) -> list[dict]:
    """'Something Keyword' patterns from entity_types.<Type>.keywords - the
    spaCy Matcher equivalent of entity_extractor._classify()'s suffix_map
    branch: a run of one-or-more capitalized/glue-word tokens immediately
    followed by a known keyword, labeled with that keyword's entity type.
    Document is skipped, same as the regex extractor (Document candidates
    come from the pipeline's own chunk/source metadata, never free text)."""
    patterns = []
    for entity_type, cfg in (ontology.get("entity_types") or {}).items():
        if entity_type == "Document":
            continue
        for keyword in cfg.get("keywords") or []:
            pattern = [
                {"TEXT": {"REGEX": _LEAD_TOKEN_RE}},
                {"TEXT": {"REGEX": _REST_TOKEN_RE}, "OP": "*"},
            ] + [{"LOWER": token.lower()} for token in keyword.split()]
            patterns.append({"label": entity_type, "pattern": pattern})
    return patterns


def _domain_gazetteer_patterns(ontology: dict) -> list[dict]:
    """Exact-case acronym matches from domain_gazetteer (e.g. IVR -> Channel) -
    matched by TEXT, not LOWER, so it can't collide with an ordinary
    capitalized word that happens to share letters, same as the regex
    extractor's exact-case dict lookup."""
    patterns = []
    for term, entity_type in (ontology.get("domain_gazetteer") or {}).items():
        pattern = [{"TEXT": token} for token in term.split()]
        patterns.append({"label": entity_type, "pattern": pattern})
    return patterns


def _technology_gazetteer_patterns(ontology: dict) -> list[dict]:
    """Case-insensitive phrase matches from technology_gazetteer, always
    typed Technology. A term also present in domain_gazetteer is skipped
    here so that gazetteer wins deterministically (same precedence as
    entity_extractor._classify, which checks domain_gazetteer before the
    flat technology_gazetteer) rather than depending on spaCy's overlap
    tie-breaking between two equal-length matches."""
    domain_terms_lower = {term.lower() for term in (ontology.get("domain_gazetteer") or {})}
    patterns = []
    for term in ontology.get("technology_gazetteer") or []:
        if term.lower() in domain_terms_lower:
            continue
        pattern = [{"LOWER": token.lower()} for token in term.split()]
        patterns.append({"label": "Technology", "pattern": pattern})
    return patterns


def _keep_hyphenated_words_tokenizer(nlp: Language) -> Tokenizer:
    """spaCy's default English infixes split "Account-Managing" into three
    tokens (Account, -, Managing), which breaks the EntityRuler patterns
    above (they chain on single REST_TOKEN tokens, not a bare "-"). The
    regex extractor's _CAP_WORD treats a hyphen as part of the word, so drop
    the one default infix that splits on a hyphen/dash between two
    alphabetic characters, keeping every other default infix (e.g. still
    splitting "won't" or comma-separated words) unchanged."""
    infixes = [pattern for pattern in nlp.Defaults.infixes if "(?:-|" not in pattern]
    infix_re = compile_infix_regex(infixes)
    return Tokenizer(
        nlp.vocab,
        rules=nlp.Defaults.tokenizer_exceptions,
        prefix_search=nlp.tokenizer.prefix_search,
        suffix_search=nlp.tokenizer.suffix_search,
        infix_finditer=infix_re.finditer,
        token_match=nlp.tokenizer.token_match,
    )


def build_nlp(ontology: dict) -> Language:
    """A fresh spaCy pipeline seeded entirely from the given ontology dict.
    Cheap to build per call (no model to load) - keeps this stateless like
    entity_extractor.extract_entities, which rebuilds its lookup dicts on
    every call too."""
    nlp = spacy.blank("en")
    nlp.tokenizer = _keep_hyphenated_words_tokenizer(nlp)
    nlp.add_pipe("sentencizer")
    ruler = nlp.add_pipe("entity_ruler")
    ruler.add_patterns(
        _keyword_patterns(ontology)
        + _domain_gazetteer_patterns(ontology)
        + _technology_gazetteer_patterns(ontology)
    )
    return nlp


def _extract_from_chunk(doc, chunk_id: str) -> list[dict]:
    found: list[dict] = []
    seen_in_chunk: set[tuple[str, str]] = set()
    for ent in doc.ents:
        name = _clean_phrase(ent.text.strip())
        if not name:
            continue
        key = (name.lower(), ent.label_)
        if key in seen_in_chunk:
            continue
        seen_in_chunk.add(key)
        found.append({"name": name, "type": ent.label_, "source_chunk": chunk_id})
    return found


def extract_entities(chunks: list[dict], ontology: dict) -> tuple[list[dict], list[dict]]:
    """Same contract as entity_extractor.extract_entities: (entities, mentions).

    entities: [{"id", "name", "type", "source_chunk"}] deduplicated by
              (name.lower(), type), keeping the first chunk seen.
    mentions: [{"chunk_id", "entity_id"}] one row per (chunk, entity) pair.
    """
    nlp = build_nlp(ontology)

    entities_by_key: dict[tuple[str, str], dict] = {}
    mentions: list[dict] = []
    mention_keys: set[tuple[str, str]] = set()

    for chunk in chunks:
        doc = nlp(chunk["content"])
        for raw in _extract_from_chunk(doc, chunk["chunk_id"]):
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

    return list(entities_by_key.values()), mentions
