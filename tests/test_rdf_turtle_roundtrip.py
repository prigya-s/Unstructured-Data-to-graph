"""
Round-trip tests against the real ontology.yaml: build_core_ontology()
must produce a graph that serializes to Turtle and re-parses back to the
same triples, and must cover every entity/relationship type currently in
ontology.yaml.
"""

from __future__ import annotations

import yaml
from rdflib import Graph, OWL, RDF

from ontology.rdf.build_core_ontology import _ONTOLOGY_YAML_PATH, build_core_ontology
from ontology.rdf.hierarchy import allowed_classes
from ontology.rdf.namespaces import CORE_NS


def _real_ontology() -> dict:
    return yaml.safe_load(_ONTOLOGY_YAML_PATH.read_text(encoding="utf-8")) or {}


def test_build_core_ontology_covers_every_entity_and_relationship_type():
    raw = _real_ontology()
    graph = build_core_ontology()

    assert allowed_classes(graph) == set((raw.get("entity_types") or {}).keys())

    relationship_props = {
        str(prop).rsplit("#", 1)[-1] for prop in graph.subjects(RDF.type, OWL.ObjectProperty)
    }
    assert relationship_props == set((raw.get("relationship_types") or {}).keys())


def test_core_ontology_survives_serialize_and_reparse(tmp_path):
    graph = build_core_ontology()

    ttl_path = tmp_path / "core.ttl"
    graph.serialize(destination=ttl_path, format="turtle")

    reloaded = Graph()
    reloaded.parse(ttl_path, format="turtle")

    assert len(reloaded) == len(graph)
    assert (CORE_NS.Document, RDF.type, OWL.Class) in reloaded
