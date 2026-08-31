"""
enrich_ontology_with_rdf() must be a no-op when no turtle_modules are
configured (the default `local` provider's exact behavior, unaffected by
Phase 3), and must union in RDF-derived classes and keywords without
dropping any keyword ontology.yaml already defines for an existing entity
type - against the real change_of_address.ttl domain module (which pulls in
core.ttl transitively), not a synthetic fixture, since that's what a
running `local_turtle` pipeline actually loads.
"""

from __future__ import annotations

from config.app_config import AppConfig, OntologyConfig
from ontology.rdf.graph_loader import enrich_ontology_with_rdf


def _config(turtle_modules: list[str]) -> AppConfig:
    return AppConfig(ontology=OntologyConfig(turtle_modules=turtle_modules))


def test_no_turtle_modules_is_a_noop():
    base = {"entity_types": {"System": {"keywords": ["system"]}}}
    config = _config([])

    assert enrich_ontology_with_rdf(config, base) is base


def test_domain_module_keyword_class_merged_in():
    base = {"entity_types": {"System": {"keywords": ["system"]}}}
    config = _config(["ontology/rdf/domains/change_of_address.ttl"])

    enriched = enrich_ontology_with_rdf(config, base)

    assert "ChangeOfAddressProcess" in enriched["entity_types"]
    assert enriched["entity_types"]["System"] == {"keywords": ["system"]}


def test_existing_entity_type_keeps_its_own_keywords():
    base = {"entity_types": {"Process": {"keywords": ["custom-process-word"]}}}
    config = _config(["ontology/rdf/domains/change_of_address.ttl"])

    enriched = enrich_ontology_with_rdf(config, base)

    assert "custom-process-word" in enriched["entity_types"]["Process"]["keywords"]


def test_existing_entity_type_gains_rdf_only_keywords_instead_of_losing_them():
    """core.ttl's core:Process carries skos:altLabel "pipeline"/"process"/
    "workflow" - a class name ontology.yaml also defines. Before the Part 2
    fix, enrich_ontology_with_rdf's setdefault() silently dropped these the
    moment "Process" already existed in base_ontology; the correct
    behavior is the union the docstring always claimed."""
    base = {"entity_types": {"Process": {"keywords": ["custom-process-word"]}}}
    config = _config(["ontology/rdf/domains/change_of_address.ttl"])

    enriched = enrich_ontology_with_rdf(config, base)

    keywords = {k.lower() for k in enriched["entity_types"]["Process"]["keywords"]}
    assert {"pipeline", "process", "workflow"} <= keywords
    # base_ontology's own dict must not be mutated in place.
    assert base["entity_types"]["Process"]["keywords"] == ["custom-process-word"]
