"""
Candidate Entity stage.

Converts the raw, deterministic output of entity_extractor/relationship_extractor
(dumb dicts keyed by id, no business framing) into reviewable
CandidateEntity/CandidateRelationship objects, and persists them via an
OntologyRepository. This is the seam between the existing extraction
pipeline and the new human review workflow - nothing upstream of this
module changes.

Re-running this against an existing repository is safe: entities/relationships
already decided (APPROVED, REJECTED, MERGED) are left untouched so a repeat
`ingest` run never overwrites a business user's decision. Only NEW/PENDING_REVIEW
rows are refreshed with the latest extraction output.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from .ambiguity_terms import possible_meanings_for
from .models import (
    CandidateEntity,
    CandidateRelationship,
    ClassProposal,
    HistoryEntry,
    WorkflowStatus,
    make_proposal_id,
    make_relationship_id,
)
from .repository import OntologyRepository

if TYPE_CHECKING:
    from config.app_config import AppConfig

logger = logging.getLogger("kg_local.candidate_builder")

_SNIPPET_LENGTH = 200
_MAX_SNIPPETS = 3

# Tunable: an entity mentioned fewer times than this across the whole corpus
# never becomes a PENDING_REVIEW row at all - a single stray capitalized
# phrase is noise, not a candidate worth a reviewer's attention.
_MIN_MENTIONS_FOR_REVIEW = 2

DEFINITION_TEMPLATES: dict[str, str] = {
    "Document": "{name} is a source document referenced by the reviewed content.",
    "Application": "{name} is a software application used within the organization.",
    "System": "{name} is a system that supports one or more business functions.",
    "Service": "{name} is a service that provides a defined capability to other components.",
    "Database": "{name} is a database or data store used to persist business data.",
    "API": "{name} is an API or integration point used to exchange data between systems.",
    "Process": "{name} is a business or technical process followed by the organization.",
    "Team": "{name} is a team or group responsible for part of the organization's operations.",
    "Technology": "{name} is a technology or platform used in the organization's technical stack.",
    "Policy": "{name} is a policy or standard that governs how work must be carried out.",
    "Check": "{name} is a verification or authentication check performed as part of a process.",
    "Party": "{name} is a person or role involved in a business transaction or request.",
    "Channel": "{name} is a channel through which customers or staff interact with the business.",
}

BUSINESS_MEANING_TEMPLATES: dict[str, str] = {
    "Document": "Provides context and source material for other business concepts.",
    "Application": "Supports business users in carrying out day-to-day activities.",
    "System": "Underpins core business operations and other dependent components.",
    "Service": "Delivers a specific piece of business or technical functionality.",
    "Database": "Stores information that the business relies on for decisions and operations.",
    "API": "Enables other systems and services to exchange information.",
    "Process": "Describes how work is carried out to achieve a business outcome.",
    "Team": "Owns and is accountable for a part of the business or technology estate.",
    "Technology": "Provides technical capability used to build or run other components.",
    "Policy": "Sets rules or expectations that other concepts must comply with.",
    "Check": "Confirms that a customer or request meets the conditions needed to proceed.",
    "Party": "Identifies who is involved in, or affected by, a business transaction or request.",
    "Channel": "Determines how a customer or staff member can carry out an interaction.",
}

_DEFAULT_DEFINITION = "{name} is a concept identified in the reviewed documents."
_DEFAULT_BUSINESS_MEANING = "Its business significance has not yet been described."


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _group_mentions_by_entity(mentions: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for mention in mentions:
        grouped.setdefault(mention["entity_id"], []).append(mention)
    return grouped


def _compute_confidence(mention_count: int) -> float:
    return round(min(1.0, mention_count / 10.0), 2)


def _gather_evidence(entity_mentions: list[dict], chunks_by_id: dict[str, dict]) -> list[str]:
    snippets: list[str] = []
    for mention in entity_mentions:
        chunk = chunks_by_id.get(mention["chunk_id"])
        if not chunk:
            continue
        content = chunk["content"].strip().replace("\n", " ")
        snippet = content[:_SNIPPET_LENGTH]
        if snippet and snippet not in snippets:
            snippets.append(snippet)
        if len(snippets) >= _MAX_SNIPPETS:
            break
    return snippets


def _gather_source_documents(entity_mentions: list[dict], chunks_by_id: dict[str, dict]) -> list[str]:
    docs: list[str] = []
    for mention in entity_mentions:
        chunk = chunks_by_id.get(mention["chunk_id"])
        if chunk and chunk["document"] not in docs:
            docs.append(chunk["document"])
    return docs


def _gather_source_chunks(entity_mentions: list[dict]) -> list[str]:
    return [m["chunk_id"] for m in entity_mentions]


def _make_history_entry(action: str, comment: str) -> HistoryEntry:
    return HistoryEntry(timestamp=_now_iso(), reviewer="pipeline", action=action, comment=comment)


def build_candidates(
    entities: list[dict],
    mentions: list[dict],
    relationships: list[dict],
    chunks: list[dict],
    repository: OntologyRepository,
    config: "AppConfig | None" = None,
) -> tuple[int, int]:
    """entities/mentions/relationships: raw output from entity_extractor and
    relationship_extractor. chunks: all chunks from semantic_chunker (used to
    resolve evidence snippets and source documents). repository: destination
    for the resulting CandidateEntity/CandidateRelationship rows. config: when
    given and ontology.turtle_modules is configured, each relationship
    candidate is checked against the RDF layer's declared rdfs:domain/
    rdfs:range (see ontology.rdf.guardrails.check_relationship_type_mismatch)
    and any mismatch is recorded as a "warning" history entry - advisory
    only, never blocking. Fully inert (no graph loaded, no behavior change)
    when config is None or no turtle_modules are configured.

    Returns (entities_saved, relationships_saved) - the number of rows
    actually written (decided rows that were preserved are not counted).
    """
    chunks_by_id = {c["chunk_id"]: c for c in chunks}
    mentions_by_entity = _group_mentions_by_entity(mentions)
    entity_type_by_id = {raw["id"]: raw["type"] for raw in entities}

    ontology_graph = None
    if config is not None:
        from ontology.rdf.graph_loader import load_ontology_graph

        ontology_graph = load_ontology_graph(config)

    existing_entities = {e.id: e.status for e in repository.get_candidate_entities()}
    entity_confidence: dict[str, float] = {}

    entities_to_save: list[CandidateEntity] = []
    entities_skipped_low_mentions = 0
    for raw in entities:
        entity_id = raw["id"]
        entity_mentions = mentions_by_entity.get(entity_id, [])
        mention_count = len(entity_mentions)
        confidence = _compute_confidence(mention_count)
        entity_confidence[entity_id] = confidence

        current_status = existing_entities.get(entity_id)
        if current_status in (WorkflowStatus.APPROVED, WorkflowStatus.REJECTED, WorkflowStatus.MERGED):
            continue

        if mention_count < _MIN_MENTIONS_FOR_REVIEW:
            entities_skipped_low_mentions += 1
            continue

        entity_type = raw["type"]
        name = raw["name"]
        possible_meanings = possible_meanings_for(name)
        status = WorkflowStatus.PENDING_REVIEW

        candidate = CandidateEntity(
            id=entity_id,
            name=name,
            entity_type=entity_type,
            definition=DEFINITION_TEMPLATES.get(entity_type, _DEFAULT_DEFINITION).format(name=name),
            business_meaning=BUSINESS_MEANING_TEMPLATES.get(entity_type, _DEFAULT_BUSINESS_MEANING),
            confidence_score=confidence,
            status=status,
            evidence=_gather_evidence(entity_mentions, chunks_by_id),
            source_documents=_gather_source_documents(entity_mentions, chunks_by_id),
            source_chunks=_gather_source_chunks(entity_mentions),
            possible_meanings=possible_meanings,
            history=[
                _make_history_entry(
                    "created",
                    f"Auto-created from {mention_count} mention(s)."
                    + (" Flagged for ambiguity." if possible_meanings else ""),
                )
            ],
        )
        entities_to_save.append(candidate)

    repository.save_candidate_entities(entities_to_save)
    entities_saved = len(entities_to_save)
    if entities_skipped_low_mentions:
        logger.info(
            "Skipped %d entity candidate(s) with fewer than %d mention(s)",
            entities_skipped_low_mentions,
            _MIN_MENTIONS_FOR_REVIEW,
        )

    existing_relationships = {r.id: r.status for r in repository.get_candidate_relationships()}

    deduped: dict[tuple[str, str, str], dict] = {}
    for raw in relationships:
        key = (raw["source"], raw["relationship"], raw["target"])
        if key not in deduped:
            deduped[key] = {**raw, "evidence_chunks": [raw["source_chunk"]]}
        else:
            deduped[key]["evidence_chunks"].append(raw["source_chunk"])

    relationships_to_save: list[CandidateRelationship] = []
    for (source, rel_type, target), raw in deduped.items():
        rel_id = make_relationship_id(source, rel_type, target)

        current_status = existing_relationships.get(rel_id)
        if current_status in (WorkflowStatus.APPROVED, WorkflowStatus.REJECTED):
            continue

        source_confidence = entity_confidence.get(source, 0.5)
        target_confidence = entity_confidence.get(target, 0.5)
        confidence = round((source_confidence + target_confidence) / 2.0, 2)

        evidence = []
        for chunk_id in raw["evidence_chunks"]:
            chunk = chunks_by_id.get(chunk_id)
            if chunk:
                snippet = chunk["content"].strip().replace("\n", " ")[:_SNIPPET_LENGTH]
                if snippet and snippet not in evidence:
                    evidence.append(snippet)
            if len(evidence) >= _MAX_SNIPPETS:
                break

        history = [
            _make_history_entry(
                "created", f"Auto-created from {len(raw['evidence_chunks'])} occurrence(s)."
            )
        ]
        if ontology_graph is not None:
            from ontology.rdf.guardrails import check_relationship_type_mismatch

            mismatch = check_relationship_type_mismatch(
                ontology_graph,
                entity_type_by_id.get(source, ""),
                rel_type,
                entity_type_by_id.get(target, ""),
            )
            if mismatch is not None:
                history.append(_make_history_entry("warning", mismatch))

        candidate = CandidateRelationship(
            id=rel_id,
            source_entity=source,
            relationship_type=rel_type,
            target_entity=target,
            confidence_score=confidence,
            status=WorkflowStatus.PENDING_REVIEW,
            evidence=evidence,
            history=history,
        )
        relationships_to_save.append(candidate)

    repository.save_candidate_relationships(relationships_to_save)
    relationships_saved = len(relationships_to_save)

    return entities_saved, relationships_saved


def build_class_proposals(raw_proposals: list[dict], repository: OntologyRepository) -> int:
    """raw_proposals: from ExtractionProvider.get_class_proposals() - one row
    per NO_FIT-flagged entity name the LLM judged doesn't fit any existing
    ontology class. Same idempotency rule as build_candidates(): a proposal
    that already has a terminal status (APPROVED/REJECTED/MERGED) is left
    untouched by a repeat ingest run.

    Returns the number of rows actually written."""
    if not raw_proposals:
        return 0

    existing = {p.id: p.status for p in repository.get_class_proposals()}

    proposals_to_save: list[ClassProposal] = []
    for raw in raw_proposals:
        proposal_id = make_proposal_id(raw["proposed_name"])
        current_status = existing.get(proposal_id)
        if current_status in (WorkflowStatus.APPROVED, WorkflowStatus.REJECTED, WorkflowStatus.MERGED):
            continue

        proposal = ClassProposal(
            id=proposal_id,
            proposed_name=raw["proposed_name"],
            suggested_parent=raw.get("suggested_parent"),
            evidence=raw.get("evidence", ""),
            source_chunks=list(raw.get("source_chunks") or []),
            confidence=float(raw.get("confidence", 0.5)),
            status=WorkflowStatus.NEW,
            history=[_make_history_entry("created", "Auto-created from a NO_FIT extraction flag.")],
        )
        proposals_to_save.append(proposal)

    repository.save_class_proposals(proposals_to_save)
    return len(proposals_to_save)
