"""
Pydantic request/response models - a pure serialization boundary. Field
shapes mirror the dataclasses they wrap (RetrievalResult in
src/retrieval/graphrag_service.py, CandidateEntity/CandidateRelationship/
HistoryEntry in src/review/models.py) rather than introducing a new shape.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


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
