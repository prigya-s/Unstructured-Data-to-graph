"""
Pydantic request/response models - a pure serialization boundary. Field
shapes mirror the dataclasses they wrap (RetrievalResult in
src/retrieval/graphrag_service.py, CandidateEntity/CandidateRelationship/
HistoryEntry in src/review/models.py) rather than introducing a new shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel


@dataclass
class RetrievalTraceEntry:
    """One chat turn's retrieval footprint, kept server-side only (never
    serialized as an HTTP response body) so api/routers/retrieval_trace.py
    can regenerate that turn's Cypher/connectivity/snapshot on demand. Lives
    alongside api/routers/chat.py's _threads dict with the same in-memory,
    local-demo-only lifecycle."""

    question: str
    chunk_ids: list[str] = field(default_factory=list)
    entity_ids: list[str] = field(default_factory=list)
    document_ids: list[str] = field(default_factory=list)
    graph_expansion_hops: int = 1
    page_link_hops: int = 2


class NewThreadResponse(BaseModel):
    thread_id: str


class ChatMessageRequest(BaseModel):
    message: str


class ChatMessageResponse(BaseModel):
    answer: str
    citations: list[dict]
    entities: list[dict]
    graph_paths: list[str]
    next_steps: list[str]


class PublishSummaryResponse(BaseModel):
    approved_entities: int
    approved_relationships: int
    pending_entities: int
    pending_relationships: int


class PublishJobResponse(BaseModel):
    job_id: str


class PublishJobStatus(BaseModel):
    status: Literal["running", "succeeded", "failed"]
    result: dict | None = None
    error: str | None = None
