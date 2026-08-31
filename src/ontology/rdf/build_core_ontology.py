"""
build_core_ontology: converts ontology.yaml's entity_types/relationship_types
into an OWL/Turtle vocabulary (core.ttl) - each entity type becomes an
owl:Class, each relationship type becomes an owl:ObjectProperty, and each of
their keyword/trigger strings becomes a skos:altLabel so the class hierarchy
carries the same vocabulary the rule-based extractor already matches
against.

Run standalone to regenerate core.ttl after editing ontology.yaml:

    python src/ontology/rdf/build_core_ontology.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml
from rdflib import Graph, Literal, OWL, RDF, RDFS, SKOS

_SRC_DIR = Path(__file__).resolve().parents[2]
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from ontology.rdf.namespaces import CORE_NS  # noqa: E402

_ONTOLOGY_YAML_PATH = _SRC_DIR / "ontology" / "ontology.yaml"
_CORE_TTL_PATH = Path(__file__).resolve().parent / "core.ttl"


def build_core_ontology(ontology_yaml_path: Path = _ONTOLOGY_YAML_PATH) -> Graph:
    raw = yaml.safe_load(ontology_yaml_path.read_text(encoding="utf-8")) or {}

    graph = Graph()
    graph.bind("core", CORE_NS)
    graph.bind("skos", SKOS)

    for name, spec in (raw.get("entity_types") or {}).items():
        cls = CORE_NS[name]
        graph.add((cls, RDF.type, OWL.Class))
        graph.add((cls, RDFS.label, Literal(name)))
        for keyword in (spec or {}).get("keywords") or []:
            graph.add((cls, SKOS.altLabel, Literal(keyword)))

    for name, spec in (raw.get("relationship_types") or {}).items():
        prop = CORE_NS[name]
        graph.add((prop, RDF.type, OWL.ObjectProperty))
        graph.add((prop, RDFS.label, Literal(name)))
        for trigger in (spec or {}).get("triggers") or []:
            graph.add((prop, SKOS.altLabel, Literal(trigger)))
        domain = (spec or {}).get("domain")
        for domain_type in [domain] if isinstance(domain, str) else (domain or []):
            graph.add((prop, RDFS.domain, CORE_NS[domain_type]))
        range_ = (spec or {}).get("range")
        for range_type in [range_] if isinstance(range_, str) else (range_ or []):
            graph.add((prop, RDFS.range, CORE_NS[range_type]))

    return graph


def main() -> None:
    graph = build_core_ontology()
    graph.serialize(destination=_CORE_TTL_PATH, format="turtle")
    print(f"Wrote {len(graph)} triples to {_CORE_TTL_PATH}")


if __name__ == "__main__":
    main()
