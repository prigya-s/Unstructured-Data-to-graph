"""
Plain rdfs:subClassOf traversal over an ontology graph - no OWL reasoner
(owlrl/owlready2) needed for category rollup at this scale, just
rdflib's transitive_objects over the asserted subClassOf edges.
"""

from __future__ import annotations

from rdflib import Graph, OWL, RDF, RDFS, SKOS

from .namespaces import CORE_NS


def _local_name(iri) -> str:
    text = str(iri)
    if "#" in text:
        return text.rsplit("#", 1)[-1]
    return text.rsplit("/", 1)[-1]


def allowed_classes(graph: Graph) -> set[str]:
    """Local names of every owl:Class declared in the graph (core classes
    plus every loaded domain module) - the LLM-fallback extraction
    vocabulary's entity-type set."""
    return {_local_name(cls) for cls in graph.subjects(RDF.type, OWL.Class)}


def class_labels_and_keywords(graph: Graph) -> dict[str, list[str]]:
    """{class local name: [skos:altLabel, ...]} for every owl:Class - shaped
    like ontology.yaml's entity_types so callers can merge the two
    dicts directly."""
    result: dict[str, list[str]] = {}
    for cls in graph.subjects(RDF.type, OWL.Class):
        result[_local_name(cls)] = [str(lit) for lit in graph.objects(cls, SKOS.altLabel)]
    return result


def nearest_core_ancestor(graph: Graph, class_name: str) -> str | None:
    """Walks rdfs:subClassOf upward from class_name until it reaches a
    class declared in the shared core# namespace - the "category rollup"
    a new domain class gets for free. Returns class_name itself if it is
    already a core class, or None if class_name isn't a known class."""
    subject = next(
        (cls for cls in graph.subjects(RDF.type, OWL.Class) if _local_name(cls) == class_name),
        None,
    )
    if subject is None:
        return None
    if str(subject).startswith(str(CORE_NS)):
        return class_name

    for ancestor in graph.transitive_objects(subject, RDFS.subClassOf):
        if str(ancestor).startswith(str(CORE_NS)):
            return _local_name(ancestor)
    return None
