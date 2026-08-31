"""
append_class_to_domain() writes real Turtle via rdflib (parse + add +
reserialize), never a raw text append - these tests isolate domains_dir to
tmp_path so nothing here touches the real src/ontology/rdf/domains/ files,
while still resolving core parent classes against the real core.ttl (the
same file the running pipeline uses).
"""

from __future__ import annotations

import pytest
from rdflib import Graph, Literal, OWL, RDF, RDFS

from ontology.rdf.namespaces import CORE_NS, domain_namespace
from ontology.rdf.writer import append_class_to_domain


def _load(path):
    graph = Graph()
    graph.parse(path, format="turtle")
    return graph


def test_append_class_to_domain_creates_new_file_with_class(tmp_path):
    path = append_class_to_domain("CryptoCustodyService", "Product", "extensions", tmp_path)

    assert path == tmp_path / "extensions.ttl"
    graph = _load(path)
    ns = domain_namespace("extensions")
    assert (ns.CryptoCustodyService, RDF.type, OWL.Class) in graph
    assert (ns.CryptoCustodyService, RDFS.subClassOf, CORE_NS.Product) in graph


def test_append_class_to_domain_appends_without_losing_prior_class(tmp_path):
    append_class_to_domain("CryptoCustodyService", "Product", "extensions", tmp_path)
    append_class_to_domain("GreenEnergyRetrofitLoan", "Product", "extensions", tmp_path)

    graph = _load(tmp_path / "extensions.ttl")
    ns = domain_namespace("extensions")
    assert (ns.CryptoCustodyService, RDF.type, OWL.Class) in graph
    assert (ns.GreenEnergyRetrofitLoan, RDF.type, OWL.Class) in graph


def test_append_class_to_domain_raises_on_exact_duplicate(tmp_path):
    append_class_to_domain("CryptoCustodyService", "Product", "extensions", tmp_path)

    with pytest.raises(ValueError):
        append_class_to_domain("CryptoCustodyService", "Product", "extensions", tmp_path)


def test_append_class_to_domain_falls_back_to_core_ns_for_unknown_parent(tmp_path):
    path = append_class_to_domain("NewThing", "NoSuchCoreClass", "extensions", tmp_path)

    graph = _load(path)
    ns = domain_namespace("extensions")
    assert (ns.NewThing, RDFS.subClassOf, CORE_NS.NoSuchCoreClass) in graph


def test_append_class_to_domain_with_no_parent_writes_an_orphan_class(tmp_path):
    path = append_class_to_domain("UnclassifiedConcept", None, "extensions", tmp_path)

    graph = _load(path)
    ns = domain_namespace("extensions")
    assert (ns.UnclassifiedConcept, RDF.type, OWL.Class) in graph
    assert next(graph.objects(ns.UnclassifiedConcept, RDFS.subClassOf), None) is None


def test_append_class_to_domain_slugifies_human_readable_names(tmp_path):
    path = append_class_to_domain("Cryptocurrency Custody Service", "Product", "extensions", tmp_path)

    graph = _load(path)
    ns = domain_namespace("extensions")
    assert (ns.CryptocurrencyCustodyService, RDF.type, OWL.Class) in graph
    assert (ns.CryptocurrencyCustodyService, RDFS.subClassOf, CORE_NS.Product) in graph
    assert (ns.CryptocurrencyCustodyService, RDFS.label, Literal("Cryptocurrency Custody Service")) in graph


def test_append_class_to_domain_raises_on_duplicate_after_slugifying(tmp_path):
    append_class_to_domain("Cryptocurrency Custody Service", "Product", "extensions", tmp_path)

    with pytest.raises(ValueError):
        append_class_to_domain("cryptocurrency-custody-service", "Product", "extensions", tmp_path)


def test_append_class_to_domain_resolves_parent_defined_in_another_domain_file(tmp_path):
    (tmp_path / "other_domain.ttl").write_text(
        "\n".join(
            [
                "@prefix other: <https://kg.local/ontology/domain/other_domain#> .",
                "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
                "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
                "",
                "other:CustomBase a owl:Class ;",
                '    rdfs:label "CustomBase" .',
                "",
            ]
        ),
        encoding="utf-8",
    )

    path = append_class_to_domain("NewThing", "CustomBase", "extensions", tmp_path)

    graph = _load(path)
    other_ns = domain_namespace("other_domain")
    ns = domain_namespace("extensions")
    assert (ns.NewThing, RDFS.subClassOf, other_ns.CustomBase) in graph
