"""
append_class_to_domain(): the human-approved write side of Phase 3's
governed ontology growth. Parses the target domain .ttl (if it already
exists), adds one owl:Class triple plus rdfs:subClassOf/rdfs:label, and
reserializes the whole file via rdflib - never a raw text append - so the
output is always valid Turtle, matching build_core_ontology.py's and
turtle_ontology_provider.py's existing graph.serialize(...) pattern.

Thread-safe within one process only, via a module-level lock - same
accepted single-process limitation as review.local_repository's _LOCK.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path

from rdflib import Graph, Literal, OWL, RDF, RDFS

from .graph_loader import load_full_ttl_graph
from .hierarchy import _local_name
from .namespaces import CORE_NS, domain_namespace

_DOMAINS_DIR = Path(__file__).resolve().parent / "domains"
_LOCK = threading.Lock()


def _slugify_local_name(class_name: str) -> str:
    """PascalCase IRI-safe local name for a (possibly human-readable,
    space-separated) proposed class name - matches the naming convention
    every other domain file already uses (e.g. ChangeOfAddressProcess).
    The original class_name is preserved verbatim as the class's
    rdfs:label, so no information is lost - only the URI-illegal
    characters are."""
    words = re.findall(r"[A-Za-z0-9]+", class_name)
    return "".join(word[:1].upper() + word[1:] for word in words)


def _resolve_parent_iri(domains_dir: Path, parent_local_name: str):
    """Scans core.ttl plus every existing domain file for a class whose
    local name matches parent_local_name, falling back to CORE_NS if none
    is found (e.g. approving a proposal whose suggested_parent is itself a
    core class name that just hasn't been loaded here)."""
    lookup = load_full_ttl_graph(domains_dir)

    for cls in lookup.subjects(RDF.type, OWL.Class):
        if _local_name(cls) == parent_local_name:
            return cls
    return CORE_NS[parent_local_name]


def append_class_to_domain(
    class_name: str,
    parent_local_name: str | None,
    domain_stem: str,
    domains_dir: Path | None = None,
) -> Path:
    """Writes class_name as a new owl:Class under domains_dir/<domain_stem>.ttl,
    subclassing parent_local_name. parent_local_name=None writes an orphan
    class (no rdfs:subClassOf edge) - approving a proposal with no
    suggested_parent is a valid, audit-only outcome (see guardrails.
    check_orphan_classes), not an error. Raises ValueError if class_name
    already exists in that file - treated by the caller as
    idempotent-already-done, not a hard failure."""
    domains_dir = domains_dir or _DOMAINS_DIR
    domains_dir.mkdir(parents=True, exist_ok=True)
    target_path = domains_dir / f"{domain_stem}.ttl"
    local_name = _slugify_local_name(class_name)

    with _LOCK:
        graph = Graph()
        if target_path.exists():
            graph.parse(target_path, format="turtle")

        if any(_local_name(cls) == local_name for cls in graph.subjects(RDF.type, OWL.Class)):
            raise ValueError(f"{class_name!r} already exists in {target_path}")

        ns = domain_namespace(domain_stem)
        subject = ns[local_name]
        graph.add((subject, RDF.type, OWL.Class))
        if parent_local_name:
            parent_iri = _resolve_parent_iri(domains_dir, parent_local_name)
            graph.add((subject, RDFS.subClassOf, parent_iri))
        graph.add((subject, RDFS.label, Literal(class_name)))

        graph.bind(domain_stem, ns)
        graph.bind("core", CORE_NS)
        graph.serialize(destination=target_path, format="turtle")

    return target_path
