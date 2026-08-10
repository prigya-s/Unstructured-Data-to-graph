"""
LocalOntologyRepository: JSON-file backed implementation of OntologyRepository.

Two flat JSON arrays under output/review/ act as the row store:
  - candidate_entities.json
  - candidate_relationships.json

Each row carries its own "status" field, so get_approved_*() is just a
filter over the same file rather than a separate table - there is a single
source of truth per concept type. This mirrors the row shape a future Delta
table would use, so a later migration only has to change how rows are
read/written, not their shape.

The module-level lock only protects against concurrent writes from
multiple threads within this one process (e.g. two Streamlit re-runs). It
does not protect against two separate processes (a CLI run and a Streamlit
server) writing at the same instant - last writer wins for the full row.
That's an acceptable limitation for a local single-user tool.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from .models import CandidateEntity, CandidateRelationship, WorkflowStatus
from .repository import OntologyRepository

_LOCK = threading.Lock()

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class LocalOntologyRepository(OntologyRepository):
    def __init__(self, review_dir: Path | None = None) -> None:
        self.review_dir = review_dir or (_PROJECT_ROOT / "output" / "review")
        self.review_dir.mkdir(parents=True, exist_ok=True)
        self.entities_path = self.review_dir / "candidate_entities.json"
        self.relationships_path = self.review_dir / "candidate_relationships.json"

    # -- raw file I/O -----------------------------------------------------

    def _read_rows(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return []
        return json.loads(text)

    def _write_rows(self, path: Path, rows: list[dict]) -> None:
        path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    # -- OntologyRepository interface --------------------------------------

    def save_candidate_entity(self, entity: CandidateEntity) -> None:
        with _LOCK:
            rows = self._read_rows(self.entities_path)
            row = entity.to_dict()
            for i, existing in enumerate(rows):
                if existing["id"] == row["id"]:
                    rows[i] = row
                    break
            else:
                rows.append(row)
            self._write_rows(self.entities_path, rows)

    def save_candidate_relationship(self, relationship: CandidateRelationship) -> None:
        with _LOCK:
            rows = self._read_rows(self.relationships_path)
            row = relationship.to_dict()
            for i, existing in enumerate(rows):
                if existing["id"] == row["id"]:
                    rows[i] = row
                    break
            else:
                rows.append(row)
            self._write_rows(self.relationships_path, rows)

    def save_candidate_entities(self, entities: list[CandidateEntity]) -> None:
        if not entities:
            return
        with _LOCK:
            rows = self._read_rows(self.entities_path)
            by_id = {row["id"]: i for i, row in enumerate(rows)}
            for entity in entities:
                row = entity.to_dict()
                if row["id"] in by_id:
                    rows[by_id[row["id"]]] = row
                else:
                    by_id[row["id"]] = len(rows)
                    rows.append(row)
            self._write_rows(self.entities_path, rows)

    def save_candidate_relationships(self, relationships: list[CandidateRelationship]) -> None:
        if not relationships:
            return
        with _LOCK:
            rows = self._read_rows(self.relationships_path)
            by_id = {row["id"]: i for i, row in enumerate(rows)}
            for relationship in relationships:
                row = relationship.to_dict()
                if row["id"] in by_id:
                    rows[by_id[row["id"]]] = row
                else:
                    by_id[row["id"]] = len(rows)
                    rows.append(row)
            self._write_rows(self.relationships_path, rows)

    def get_candidate_entities(self) -> list[CandidateEntity]:
        rows = self._read_rows(self.entities_path)
        entities = [CandidateEntity.from_dict(r) for r in rows]
        return sorted(entities, key=lambda e: e.name.lower())

    def get_candidate_relationships(self) -> list[CandidateRelationship]:
        rows = self._read_rows(self.relationships_path)
        return [CandidateRelationship.from_dict(r) for r in rows]

    def get_approved_entities(self) -> list[CandidateEntity]:
        return [e for e in self.get_candidate_entities() if e.status == WorkflowStatus.APPROVED]

    def get_approved_relationships(self) -> list[CandidateRelationship]:
        return [
            r for r in self.get_candidate_relationships() if r.status == WorkflowStatus.APPROVED
        ]
