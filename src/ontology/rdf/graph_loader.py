"""
load_ontology_graph: merges core.ttl with every domain module configured in
AppConfig.ontology.turtle_modules into one in-memory rdflib Graph.

Returns None when no turtle modules are configured - the OWL/Turtle layer
is fully opt-in; the existing YAML/JSON pipeline is unaffected when this
returns None.
"""

from __future__ import annotations

from pathlib import Path

from rdflib import Graph

from config.app_config import AppConfig

from .hierarchy import class_labels_and_keywords

_CORE_TTL_PATH = Path(__file__).resolve().parent / "core.ttl"
_DOMAINS_DIR = Path(__file__).resolve().parent / "domains"


def load_full_ttl_graph(domains_dir: Path | None = None) -> Graph:
    """Parses core.ttl plus every *.ttl file already on disk under
    domains_dir (default: ontology/rdf/domains/) into one Graph - the
    complete class vocabulary as it exists on disk right now, independent of
    AppConfig.ontology.turtle_modules (which governs what the pipeline's
    rule/LLM extraction paths see, not what a guardrail check or the .ttl
    writer's parent-IRI lookup should see). Unlike load_ontology_graph(),
    never returns None - callers that need "no classes" as a signal should
    check config directly instead."""
    domains_dir = domains_dir or _DOMAINS_DIR
    graph = Graph()
    if _CORE_TTL_PATH.exists():
        graph.parse(_CORE_TTL_PATH, format="turtle")
    if domains_dir.exists():
        for path in domains_dir.glob("*.ttl"):
            graph.parse(path, format="turtle")
    return graph


def load_ontology_graph(config: AppConfig) -> Graph | None:
    module_paths = config.turtle_module_paths
    if not module_paths:
        return None

    if not _CORE_TTL_PATH.exists():
        raise FileNotFoundError(
            f"{_CORE_TTL_PATH} not found - run "
            "`python src/ontology/rdf/build_core_ontology.py` to generate it."
        )

    graph = Graph()
    graph.parse(_CORE_TTL_PATH, format="turtle")
    for path in module_paths:
        graph.parse(path, format="turtle")
    return graph


def enrich_ontology_with_rdf(config: AppConfig, base_ontology: dict) -> dict:
    """Unions the RDF-derived class vocabulary (core classes plus every
    configured domain module) into base_ontology["entity_types"], the same
    merge OllamaExtractionProvider._extended_ontology() already does for the
    LLM path - so the rule-based extractor (entity_extractor.py) sees an
    identical vocabulary and can classify a domain-only keyword
    deterministically instead of falling through to the LLM fallback.

    A class name already present in base_ontology keeps its existing
    keywords and gains any RDF-declared keywords it doesn't already have
    (case-insensitive dedup) - a domain .ttl file can extend an existing
    core class's vocabulary via skos:altLabel, not just add net-new
    subclasses. Returns base_ontology unchanged when no turtle_modules are
    configured."""
    graph = load_ontology_graph(config)
    if graph is None:
        return base_ontology

    entity_types = {
        name: {**cfg, "keywords": list(cfg.get("keywords") or [])}
        for name, cfg in (base_ontology.get("entity_types") or {}).items()
    }
    for class_name, keywords in class_labels_and_keywords(graph).items():
        if class_name not in entity_types:
            entity_types[class_name] = {"keywords": keywords}
            continue
        existing = entity_types[class_name]["keywords"]
        seen = {k.lower() for k in existing}
        for keyword in keywords:
            if keyword.lower() not in seen:
                existing.append(keyword)
                seen.add(keyword.lower())
    return {**base_ontology, "entity_types": entity_types}
