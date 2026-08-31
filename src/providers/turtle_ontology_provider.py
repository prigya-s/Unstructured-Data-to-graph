"""
TurtleOntologyProvider: writes the same JSON artifact as LocalOntologyProvider,
plus an OWL/Turtle serialization of the same approved entities and
relationships - one `kg:<id> a core:<Category>` triple per approved entity,
one `kg:<source> core:<REL> kg:<target>` triple per approved relationship,
and one `owl:sameAs` triple per entity that review resolved as MERGED into
an approved survivor (reusing review.merge_resolution.build_merge_map, the
same validated merge map ontology_generator.py already builds for the JSON
path, so a merge pointing at a non-approved survivor is dropped exactly the
same way there too).

Opt-in via `ontology.provider: local_turtle` - the default `local` provider
is untouched.
"""

from __future__ import annotations

from rdflib import Graph, Literal, OWL, RDF, RDFS

from config.app_config import AppConfig
from ontology.rdf.namespaces import CORE_NS, ENTITY_NS
from review.merge_resolution import build_merge_map
from review.ontology_generator import generate_approved_ontology, load_approved_for_graph

from .approval_provider import ApprovalProvider
from .ontology_provider import OntologyProvider


class TurtleOntologyProvider(OntologyProvider):
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def generate(self, approval_provider: ApprovalProvider) -> dict:
        scratch_path = self.config.storage_root / "gold" / "ontology" / "_generated_ontology.json"
        ontology = generate_approved_ontology(approval_provider, output_path=scratch_path)

        ttl_path = self.config.storage_root / "gold" / "ontology" / "ontology.ttl"
        graph = self._build_graph(ontology, approval_provider)
        ttl_path.parent.mkdir(parents=True, exist_ok=True)
        graph.serialize(destination=ttl_path, format="turtle")

        ontology["ttl_path"] = str(ttl_path)
        return ontology

    def load_for_graph(
        self, approval_provider: ApprovalProvider, all_mentions: list[dict]
    ) -> tuple[list[dict], list[dict], list[dict]]:
        return load_approved_for_graph(approval_provider, all_mentions)

    def _build_graph(self, ontology: dict, approval_provider: ApprovalProvider) -> Graph:
        graph = Graph()
        graph.bind("core", CORE_NS)
        graph.bind("kg", ENTITY_NS)

        for entity in ontology["entities"]:
            subject = ENTITY_NS[entity["id"]]
            graph.add((subject, RDF.type, CORE_NS[entity["category"]]))
            graph.add((subject, RDFS.label, Literal(entity["name"])))

        for rel in ontology["relationships"]:
            graph.add(
                (
                    ENTITY_NS[rel["source_entity"]],
                    CORE_NS[rel["relationship_type"]],
                    ENTITY_NS[rel["target_entity"]],
                )
            )

        merge_map = build_merge_map(approval_provider.get_candidate_entities())
        for merged_id, canonical_id in merge_map.items():
            graph.add((ENTITY_NS[merged_id], OWL.sameAs, ENTITY_NS[canonical_id]))

        return graph
