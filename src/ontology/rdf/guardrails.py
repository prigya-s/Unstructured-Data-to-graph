"""
Cheap pre-write checks for human-gated ontology growth (Phase 3) - run by
the class-proposal approval endpoint before writer.append_class_to_domain(),
not baked into the writer itself. Same in-memory-graph, no-reasoner style as
hierarchy.py.
"""

from __future__ import annotations

import re

from rdflib import Graph, OWL, RDF, RDFS, SKOS

from .hierarchy import _local_name, nearest_core_ancestor
from .namespaces import CORE_NS


def _normalize(text: str) -> str:
    return re.sub(r"[\s\-_]+", "", text.strip().lower())


def check_near_duplicate_labels(graph: Graph, proposed_name: str) -> list[str]:
    """Local names of existing classes whose local name, rdfs:label, or
    skos:altLabel normalizes (case/whitespace/separators collapsed) to the
    same string as proposed_name - candidates the reviewer likely meant to
    reuse instead of creating a duplicate."""
    target = _normalize(proposed_name)
    matches: list[str] = []
    for cls in graph.subjects(RDF.type, OWL.Class):
        name = _local_name(cls)
        candidates = [name]
        candidates.extend(str(lit) for lit in graph.objects(cls, RDFS.label))
        candidates.extend(str(lit) for lit in graph.objects(cls, SKOS.altLabel))
        if any(_normalize(candidate) == target for candidate in candidates):
            matches.append(name)
    return matches


def check_orphan_classes(graph: Graph) -> list[str]:
    """Local names of non-core classes with no rdfs:subClassOf edge - core
    classes are intentionally top-level and excluded. Audit-only signal, not
    a write-blocker: a proposal approved without a suggested_parent still
    gets written, just as one more orphan."""
    orphans: list[str] = []
    for cls in graph.subjects(RDF.type, OWL.Class):
        if str(cls).startswith(str(CORE_NS)):
            continue
        if next(graph.objects(cls, RDFS.subClassOf), None) is None:
            orphans.append(_local_name(cls))
    return orphans


def check_relationship_type_mismatch(
    graph: Graph, source_type: str, rel_type: str, target_type: str
) -> str | None:
    """Advisory (never blocking) check: if rel_type's owl:ObjectProperty
    declares rdfs:domain/rdfs:range, confirm source_type/target_type satisfy
    it - walking nearest_core_ancestor so a domain subclass (e.g.
    coa:IVRChannel) satisfies a core:Channel domain/range declaration.
    Returns a human-readable warning, or None when the property has no
    domain/range declared (unconstrained, not invalid) or both are
    satisfied. A source/target type unknown to the graph fails the check
    it's being tested against, same as a genuine mismatch - it can't be
    verified, so it's surfaced rather than silently passed."""
    prop = next(
        (p for p in graph.subjects(RDF.type, OWL.ObjectProperty) if _local_name(p) == rel_type),
        None,
    )
    if prop is None:
        return None

    domains = [_local_name(o) for o in graph.objects(prop, RDFS.domain)]
    ranges = [_local_name(o) for o in graph.objects(prop, RDFS.range)]

    if domains and not any(nearest_core_ancestor(graph, source_type) == d for d in domains):
        return (
            f"{rel_type} expects a source of type {'/'.join(domains)}, "
            f"but the source entity is typed {source_type}."
        )
    if ranges and not any(nearest_core_ancestor(graph, target_type) == r for r in ranges):
        return (
            f"{rel_type} expects a target of type {'/'.join(ranges)}, "
            f"but the target entity is typed {target_type}."
        )
    return None


def assert_no_disjoint_violation(graph: Graph, class_name: str, parent_name: str) -> None:
    """No owl:disjointWith triples exist anywhere in the ontology yet, so
    this is a documented no-op - the extension point for once disjointness
    is actually declared, not a placeholder standing in for missed work."""
    return None
