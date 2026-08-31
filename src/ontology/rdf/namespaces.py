"""
RDF namespaces for kg-local's OWL/Turtle ontology layer.

Defined once here and imported everywhere else that mints or resolves an
IRI - Turtle generation (build_core_ontology.py, turtle_ontology_provider.py),
the graph loader/hierarchy helpers, and (Phase 2) the Neo4j `uri` properties
- so the same entity/document/chunk always resolves to the identical IRI
regardless of which part of the pipeline is building it.
"""

from __future__ import annotations

from rdflib import Namespace

BASE = "https://kg.local/ontology/"

CORE_NS = Namespace(f"{BASE}core#")
ENTITY_NS = Namespace(f"{BASE}entity/")
DOCUMENT_NS = Namespace(f"{BASE}document/")
CHUNK_NS = Namespace(f"{BASE}chunk/")


def domain_namespace(stem: str) -> Namespace:
    """stem is a domain module's file stem, e.g. "change_of_address" for
    src/ontology/rdf/domains/change_of_address.ttl -> that module's classes
    live under .../domain/<stem>#."""
    return Namespace(f"{BASE}domain/{stem}#")
