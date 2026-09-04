"""
Chat endpoints wrapping agents.graphrag_agent.GraphRAGAgent.

Threads live server-side in an in-memory dict keyed by a generated id; the
client only ever holds the id (see NewThreadResponse). This is fine for a
single-process local/demo deployment.

send_message streams the answer back as newline-delimited JSON
(one {"type": "delta"|"done"|"error", ...} object per line) rather than a
single JSON body, since the local CPU-bound LLM can take a while to
generate a full answer - see agents.graphrag_agent.GraphRAGAgent.run_stream.
Validation/thread-lookup errors are raised as ordinary HTTPExceptions
*before* the streaming response starts; anything that fails mid-stream
(timeout, provider error) surfaces as an "error" line instead, since the
200 status and headers have already been sent by then.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from api import deps
from api.schemas import ChatMessageRequest, NewThreadResponse, RetrievalTraceEntry
from agents.graphrag_agent import GraphRAGAgent
from config.app_config import AppConfig

logger = logging.getLogger("kg_local.api.chat")

router = APIRouter()

_threads: dict[str, object] = {}

# One RetrievalTraceEntry per turn, in the order turns were answered -
# api/routers/retrieval_trace.py reads this to regenerate that turn's
# Cypher/connectivity/snapshot on demand. Same in-memory, local-demo-only
# lifecycle as _threads above.
_retrieval_trace_history: dict[str, list[RetrievalTraceEntry]] = {}


@router.post("/api/chat/threads", response_model=NewThreadResponse)
def new_thread(agent: GraphRAGAgent = Depends(deps.get_agent)) -> NewThreadResponse:
    thread_id = str(uuid.uuid4())
    _threads[thread_id] = agent.get_new_thread()
    return NewThreadResponse(thread_id=thread_id)


@router.post("/api/chat/threads/{thread_id}/messages")
async def send_message(
    thread_id: str,
    body: ChatMessageRequest,
    agent: GraphRAGAgent = Depends(deps.get_agent),
    config: AppConfig = Depends(deps.get_config),
) -> StreamingResponse:
    thread = _threads.get(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Unknown thread_id - call POST /api/chat/threads first.")

    try:
        agent.validate_message(body.message)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    async def event_stream():
        try:
            async for chunk in agent.run_stream(body.message, thread=thread):
                yield json.dumps({"type": "delta", "text": chunk}) + "\n"
        except asyncio.TimeoutError:
            yield json.dumps(
                {"type": "error", "detail": "The knowledge graph assistant took too long to respond."}
            ) + "\n"
            return
        except Exception:  # noqa: BLE001 - surface as a stream event, not an unhandled 500
            logger.exception("Chat turn failed")
            yield json.dumps(
                {"type": "error", "detail": "Something went wrong answering that - check the log file."}
            ) + "\n"
            return

        result = agent.last_result
        turn_index = len(_retrieval_trace_history.get(thread_id, []))
        _retrieval_trace_history.setdefault(thread_id, []).append(
            RetrievalTraceEntry(
                question=body.message,
                chunk_ids=[chunk["chunk_id"] for chunk in result.chunks],
                entity_ids=[entity["entity_id"] for entity in result.entities],
                document_ids=list({chunk["document_id"] for chunk in result.chunks}),
                graph_expansion_hops=config.retrieval.graph_expansion_hops,
                page_link_hops=config.retrieval.page_link_hops,
            )
        )
        yield json.dumps(
            {
                "type": "done",
                "turn_index": turn_index,
                "citations": result.citations,
                "entities": result.entities,
                "graph_paths": result.graph_paths,
                "next_steps": result.next_steps,
            }
        ) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
