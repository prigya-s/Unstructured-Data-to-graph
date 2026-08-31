"""
Pure in-memory graph tests for ontology.rdf.guardrails - no dependency on the
real ontology.yaml/core.ttl on disk, same style as test_rdf_hierarchy.py.
"""

from __future__ import annotations

from rdflib import Graph, Literal, OWL, RDF, RDFS, SKOS

from ontology.rdf.guardrails import (
    assert_no_disjoint_violation,
    check_near_duplicate_labels,
    check_orphan_classes,
    check_relationship_type_mismatch,
)
from ontology.rdf.namespaces import CORE_NS, domain_namespace


def _build_graph() -> Graph:
    graph = Graph()

    graph.add((CORE_NS.Process, RDF.type, OWL.Class))
    graph.add((CORE_NS.Process, RDFS.label, Literal("Process")))

    graph.add((CORE_NS.Product, RDF.type, OWL.Class))
    graph.add((CORE_NS.Product, RDFS.label, Literal("Product")))
    graph.add((CORE_NS.Product, SKOS.altLabel, Literal("offering")))

    graph.add((CORE_NS.Team, RDF.type, OWL.Class))
    graph.add((CORE_NS.Team, RDFS.label, Literal("Team")))

    graph.add((CORE_NS.System, RDF.type, OWL.Class))
    graph.add((CORE_NS.System, RDFS.label, Literal("System")))

    graph.add((CORE_NS.OWNS, RDF.type, OWL.ObjectProperty))
    graph.add((CORE_NS.OWNS, RDFS.label, Literal("OWNS")))
    graph.add((CORE_NS.OWNS, RDFS.domain, CORE_NS.Team))
    graph.add((CORE_NS.OWNS, RDFS.range, CORE_NS.System))

    graph.add((CORE_NS.REFERENCES, RDF.type, OWL.ObjectProperty))
    graph.add((CORE_NS.REFERENCES, RDFS.label, Literal("REFERENCES")))

    coa = domain_namespace("change_of_address")
    graph.add((coa.ChangeOfAddressProcess, RDF.type, OWL.Class))
    graph.add((coa.ChangeOfAddressProcess, RDFS.subClassOf, CORE_NS.Process))
    graph.add((coa.ChangeOfAddressProcess, RDFS.label, Literal("ChangeOfAddressProcess")))

    coa_system = domain_namespace("change_of_address")
    graph.add((coa_system.SAMM, RDF.type, OWL.Class))
    graph.add((coa_system.SAMM, RDFS.subClassOf, CORE_NS.System))
    graph.add((coa_system.SAMM, RDFS.label, Literal("SAMM")))

    return graph


def test_check_near_duplicate_labels_matches_local_name_case_and_whitespace_insensitively():
    graph = _build_graph()
    matches = check_near_duplicate_labels(graph, "change of address process")
    assert matches == ["ChangeOfAddressProcess"]


def test_check_near_duplicate_labels_matches_altlabel():
    graph = _build_graph()
    matches = check_near_duplicate_labels(graph, "Offering")
    assert matches == ["Product"]


def test_check_near_duplicate_labels_no_match_returns_empty():
    graph = _build_graph()
    assert check_near_duplicate_labels(graph, "Cryptocurrency Custody Service") == []


def test_check_orphan_classes_excludes_core_classes():
    graph = _build_graph()
    assert check_orphan_classes(graph) == []


def test_check_orphan_classes_flags_domain_class_with_no_subclassof():
    graph = _build_graph()
    coa = domain_namespace("change_of_address")
    graph.add((coa.OrphanThing, RDF.type, OWL.Class))
    graph.add((coa.OrphanThing, RDFS.label, Literal("OrphanThing")))

    assert check_orphan_classes(graph) == ["OrphanThing"]


def test_assert_no_disjoint_violation_is_a_documented_noop():
    graph = _build_graph()
    assert assert_no_disjoint_violation(graph, "NewClass", "Process") is None


def test_check_relationship_type_mismatch_returns_none_when_unconstrained():
    graph = _build_graph()
    assert check_relationship_type_mismatch(graph, "Party", "REFERENCES", "Party") is None


def test_check_relationship_type_mismatch_returns_none_when_satisfied():
    graph = _build_graph()
    assert check_relationship_type_mismatch(graph, "Team", "OWNS", "System") is None


def test_check_relationship_type_mismatch_satisfied_via_domain_subclass():
    graph = _build_graph()
    assert check_relationship_type_mismatch(graph, "Team", "OWNS", "SAMM") is None


def test_check_relationship_type_mismatch_flags_bad_source():
    graph = _build_graph()
    warning = check_relationship_type_mismatch(graph, "Party", "OWNS", "System")
    assert warning is not None
    assert "source" in warning
    assert "Party" in warning


def test_check_relationship_type_mismatch_flags_bad_target():
    graph = _build_graph()
    warning = check_relationship_type_mismatch(graph, "Team", "OWNS", "Party")
    assert warning is not None
    assert "target" in warning
    assert "Party" in warning


def test_check_relationship_type_mismatch_unknown_property_returns_none():
    graph = _build_graph()
    assert check_relationship_type_mismatch(graph, "Team", "NOT_A_PROPERTY", "System") is None
