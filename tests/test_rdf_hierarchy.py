"""
Pure in-memory graph tests for ontology.rdf.hierarchy - no dependency on the
real ontology.yaml/core.ttl on disk.
"""

from __future__ import annotations

from rdflib import Graph, Literal, OWL, RDF, RDFS, SKOS

from ontology.rdf.hierarchy import allowed_classes, class_labels_and_keywords, nearest_core_ancestor
from ontology.rdf.namespaces import CORE_NS, domain_namespace


def _build_graph() -> Graph:
    graph = Graph()

    graph.add((CORE_NS.Process, RDF.type, OWL.Class))
    graph.add((CORE_NS.Process, RDFS.label, Literal("Process")))
    graph.add((CORE_NS.Process, SKOS.altLabel, Literal("workflow")))

    coa = domain_namespace("change_of_address")
    graph.add((coa.ChangeOfAddressProcess, RDF.type, OWL.Class))
    graph.add((coa.ChangeOfAddressProcess, RDFS.subClassOf, CORE_NS.Process))
    graph.add((coa.ChangeOfAddressProcess, RDFS.label, Literal("ChangeOfAddressProcess")))

    return graph


def test_allowed_classes_includes_core_and_domain():
    graph = _build_graph()
    assert allowed_classes(graph) == {"Process", "ChangeOfAddressProcess"}


def test_class_labels_and_keywords_collects_altlabels():
    graph = _build_graph()
    labels = class_labels_and_keywords(graph)
    assert labels["Process"] == ["workflow"]
    assert labels["ChangeOfAddressProcess"] == []


def test_nearest_core_ancestor_rolls_up_domain_class():
    graph = _build_graph()
    assert nearest_core_ancestor(graph, "ChangeOfAddressProcess") == "Process"


def test_nearest_core_ancestor_of_core_class_is_itself():
    graph = _build_graph()
    assert nearest_core_ancestor(graph, "Process") == "Process"


def test_nearest_core_ancestor_unknown_class_is_none():
    graph = _build_graph()
    assert nearest_core_ancestor(graph, "NoSuchClass") is None
