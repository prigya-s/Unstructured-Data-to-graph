"""
FutureOntoBricksRepository: OntologyRepository implementation for a
Delta/SQL-Warehouse-backed approval workflow.

Every method below delegates to providers._delta_sql.DeltaSqlTableStore,
driven by contracts.schemas.TABLE_REGISTRY's "candidate_entities"/
"candidate_relationships" entries - the exact same generic helper
UnityCatalogProvider uses. save_*() upserts by id via MERGE INTO, which is
atomic across concurrent writers (a CLI ingest run and a Streamlit server
writing at the same time) - the one cross-process-safety gap
LocalOntologyRepository documents as an accepted local-only limitation.
get_approved_*() is a select_all() + status filter, mirroring
LocalOntologyRepository's own get_approved_entities() implementation
exactly (same filter, different row source).

Connection details (server hostname / HTTP path / access token env var
names, catalog, schema) come from config.yaml's approval.options block -
see config.databricks.example.yaml. Requires the optional
databricks-sql-connector dependency (requirements-databricks.txt); not
exercised by local dev, and not executable without a real SQL Warehouse.
"""

from __future__ import annotations

from contracts.schemas import TABLE_REGISTRY

from providers._delta_sql import build_delta_sql_store
from providers.secrets_provider import SecretsProvider

from .models import CandidateEntity, CandidateRelationship, WorkflowStatus
from .repository import OntologyRepository


class FutureOntoBricksRepository(OntologyRepository):
    def __init__(self, options: dict | None = None, secrets: SecretsProvider | None = None) -> None:
        self._store = build_delta_sql_store(options or {}, secrets=secrets)

    def save_candidate_entity(self, entity: CandidateEntity) -> None:
        self.save_candidate_entities([entity])

    def save_candidate_relationship(self, relationship: CandidateRelationship) -> None:
        self.save_candidate_relationships([relationship])

    def save_candidate_entities(self, entities: list[CandidateEntity]) -> None:
        if not entities:
            return
        record_cls, primary_key = TABLE_REGISTRY["candidate_entities"]
        self._store.merge_rows(
            "candidate_entities", record_cls, primary_key, [e.to_dict() for e in entities]
        )

    def save_candidate_relationships(self, relationships: list[CandidateRelationship]) -> None:
        if not relationships:
            return
        record_cls, primary_key = TABLE_REGISTRY["candidate_relationships"]
        self._store.merge_rows(
            "candidate_relationships", record_cls, primary_key, [r.to_dict() for r in relationships]
        )

    def get_candidate_entities(self) -> list[CandidateEntity]:
        record_cls, _ = TABLE_REGISTRY["candidate_entities"]
        rows = self._store.select_all("candidate_entities", record_cls)
        entities = [CandidateEntity.from_dict(r) for r in rows]
        return sorted(entities, key=lambda e: e.name.lower())

    def get_candidate_relationships(self) -> list[CandidateRelationship]:
        record_cls, _ = TABLE_REGISTRY["candidate_relationships"]
        rows = self._store.select_all("candidate_relationships", record_cls)
        return [CandidateRelationship.from_dict(r) for r in rows]

    def get_approved_entities(self) -> list[CandidateEntity]:
        return [e for e in self.get_candidate_entities() if e.status == WorkflowStatus.APPROVED]

    def get_approved_relationships(self) -> list[CandidateRelationship]:
        return [
            r for r in self.get_candidate_relationships() if r.status == WorkflowStatus.APPROVED
        ]
