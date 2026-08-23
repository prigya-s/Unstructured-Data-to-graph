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
from api.schemas import ChatMessageRequest, NewThreadResponse
from agents.graphrag_agent import GraphRAGAgent

logger = logging.getLogger("kg_local.api.chat")

router = APIRouter()

_threads: dict[str, object] = {}


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
        yield json.dumps(
            {
                "type": "done",
                "citations": result.citations,
                "entities": result.entities,
                "graph_paths": result.graph_paths,
                "next_steps": result.next_steps,
            }
        ) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
