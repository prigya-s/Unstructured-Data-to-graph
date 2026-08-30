"""
Data models for the business review/approval workflow.

Pure dataclasses, stdlib only. No I/O here - repositories own persistence,
callers own state-machine transitions (a save() is a plain upsert; nothing
in this module or in the repository layer enforces which status transitions
are legal).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class WorkflowStatus(str, Enum):
    NEW = "NEW"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MERGED = "MERGED"


@dataclass
class HistoryEntry:
    timestamp: str
    reviewer: str
    action: str
    comment: str | None = None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "reviewer": self.reviewer,
            "action": self.action,
            "comment": self.comment,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HistoryEntry":
        return cls(
            timestamp=d["timestamp"],
            reviewer=d["reviewer"],
            action=d["action"],
            comment=d.get("comment"),
        )


@dataclass
class CandidateEntity:
    id: str
    name: str
    entity_type: str
    definition: str
    business_meaning: str
    confidence_score: float
    status: WorkflowStatus
    evidence: list[str] = field(default_factory=list)
    source_documents: list[str] = field(default_factory=list)
    source_chunks: list[str] = field(default_factory=list)
    possible_meanings: list[str] = field(default_factory=list)
    history: list[HistoryEntry] = field(default_factory=list)
    reviewer: str | None = None
    review_timestamp: str | None = None
    merged_into: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "entity_type": self.entity_type,
            "definition": self.definition,
            "business_meaning": self.business_meaning,
            "confidence_score": self.confidence_score,
            "status": self.status.value,
            "evidence": self.evidence,
            "source_documents": self.source_documents,
            "source_chunks": self.source_chunks,
            "possible_meanings": self.possible_meanings,
            "history": [h.to_dict() for h in self.history],
            "reviewer": self.reviewer,
            "review_timestamp": self.review_timestamp,
            "merged_into": self.merged_into,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CandidateEntity":
        return cls(
            id=d["id"],
            name=d["name"],
            entity_type=d["entity_type"],
            definition=d["definition"],
            business_meaning=d["business_meaning"],
            confidence_score=d["confidence_score"],
            status=WorkflowStatus(d["status"]),
            evidence=list(d.get("evidence") or []),
            source_documents=list(d.get("source_documents") or []),
            source_chunks=list(d.get("source_chunks") or []),
            possible_meanings=list(d.get("possible_meanings") or []),
            history=[HistoryEntry.from_dict(h) for h in d.get("history") or []],
            reviewer=d.get("reviewer"),
            review_timestamp=d.get("review_timestamp"),
            merged_into=d.get("merged_into"),
        )


@dataclass
class CandidateRelationship:
    id: str
    source_entity: str
    relationship_type: str
    target_entity: str
    confidence_score: float
    status: WorkflowStatus
    evidence: list[str] = field(default_factory=list)
    history: list[HistoryEntry] = field(default_factory=list)
    reviewer: str | None = None
    review_timestamp: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_entity": self.source_entity,
            "relationship_type": self.relationship_type,
            "target_entity": self.target_entity,
            "confidence_score": self.confidence_score,
            "status": self.status.value,
            "evidence": self.evidence,
            "history": [h.to_dict() for h in self.history],
            "reviewer": self.reviewer,
            "review_timestamp": self.review_timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CandidateRelationship":
        return cls(
            id=d["id"],
            source_entity=d["source_entity"],
            relationship_type=d["relationship_type"],
            target_entity=d["target_entity"],
            confidence_score=d["confidence_score"],
            status=WorkflowStatus(d["status"]),
            evidence=list(d.get("evidence") or []),
            history=[HistoryEntry.from_dict(h) for h in d.get("history") or []],
            reviewer=d.get("reviewer"),
            review_timestamp=d.get("review_timestamp"),
        )


def make_relationship_id(source_entity: str, relationship_type: str, target_entity: str) -> str:
    return f"rel__{source_entity}__{relationship_type}__{target_entity}"


@dataclass
class ClassProposal:
    id: str
    proposed_name: str
    suggested_parent: str | None
    evidence: str
    source_chunks: list[str]
    confidence: float
    status: WorkflowStatus
    target_domain: str | None = None
    reviewer: str | None = None
    review_timestamp: str | None = None
    history: list[HistoryEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "proposed_name": self.proposed_name,
            "suggested_parent": self.suggested_parent,
            "evidence": self.evidence,
            "source_chunks": self.source_chunks,
            "confidence": self.confidence,
            "status": self.status.value,
            "target_domain": self.target_domain,
            "reviewer": self.reviewer,
            "review_timestamp": self.review_timestamp,
            "history": [h.to_dict() for h in self.history],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ClassProposal":
        return cls(
            id=d["id"],
            proposed_name=d["proposed_name"],
            suggested_parent=d.get("suggested_parent"),
            evidence=d.get("evidence", ""),
            source_chunks=list(d.get("source_chunks") or []),
            confidence=float(d.get("confidence", 0.5)),
            status=WorkflowStatus(d["status"]),
            target_domain=d.get("target_domain"),
            reviewer=d.get("reviewer"),
            review_timestamp=d.get("review_timestamp"),
            history=[HistoryEntry.from_dict(h) for h in d.get("history") or []],
        )


def make_proposal_id(proposed_name: str) -> str:
    normalized = proposed_name.strip().lower().replace(" ", "_")
    return f"proposal__{normalized}"
