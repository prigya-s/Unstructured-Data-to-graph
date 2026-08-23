"""
GraphRAG agent orchestration: every turn retrieves approved knowledge-graph
context (retrieval.graphrag_service.retrieve_context) in Python and folds it
directly into the prompt sent to the LLM for a single generation pass -
implements the required flow literally:

    User Query -> Vector Search -> Relevant Chunks -> Graph Expansion ->
    Gold Graph Traversal -> Context Assembly -> LLM -> Response

Retrieval is unconditional (context is always assembled and always
prepended to the question), so there's no separate LLM turn spent deciding
whether to look anything up. An earlier version of this module called
retrieve_context through an agent_framework tool and let the model decide
whether to call it - but on CPU-only inference that decision turn is a full
extra generation pass before the one that writes the answer. Calling the
chat client's get_response() directly (no Agent wrapper, no tools) removes
that extra pass entirely, at no change to what the model sees or answers -
though on this hardware the dominant cost remains decoding the grounded
answer itself, not the eliminated decision turn.

Conversation memory is a small bounded list of past (question, answer)
message pairs (see ChatThread) - the retrieved context itself is never
persisted, so a long session's prompt doesn't grow with every turn's
retrieval the way replaying a tool result every turn would.
"""

from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator

from agent_framework import Message

from config.app_config import AppConfig
from prompts.graphrag_answer import INSTRUCTIONS
from retrieval.graphrag_service import RetrievalResult, format_context_for_llm, retrieve_context
from retrieval.query_cache import QueryCache


class ChatThread:
    """Bounded (question, answer) turn history - see module docstring for
    why retrieved context is deliberately excluded from it."""

    def __init__(self, max_turns: int = 10) -> None:
        self._max_messages = max_turns * 2
        self.messages: list[Message] = []

    def extend(self, question: str, answer: str) -> None:
        self.messages.append(Message("user", [question]))
        self.messages.append(Message("assistant", [answer]))
        overflow = len(self.messages) - self._max_messages
        if overflow > 0:
            del self.messages[:overflow]


class GraphRAGAgent:
    """Wraps a chat client plus a mutable holder for the last retrieval
    result, so a caller (CLI/API) can render citations (source chunk,
    source document, graph path used) after each turn."""

    def __init__(
        self,
        chat_client,
        embedding_provider,
        graph_provider,
        config: AppConfig,
        cache: QueryCache | None = None,
        chat_options: dict | None = None,
    ) -> None:
        self._chat_client = chat_client
        self._embedding_provider = embedding_provider
        self._graph_provider = graph_provider
        self.config = config
        self._cache = cache
        self._chat_options = chat_options or {}
        self.last_result: RetrievalResult = RetrievalResult()

    def get_new_thread(self) -> ChatThread:
        return ChatThread()

    def validate_message(self, message: str) -> None:
        max_length = self.config.retrieval.max_query_length
        if not message or not message.strip():
            raise ValueError("Query must not be empty.")
        if len(message) > max_length:
            raise ValueError(f"Query exceeds the maximum allowed length of {max_length} characters.")

    def _build_messages(self, message: str, thread: ChatThread | None) -> list[Message]:
        result = retrieve_context(message, self._embedding_provider, self._graph_provider, self.config)
        self.last_result = result
        context_block = format_context_for_llm(result)
        history = thread.messages if thread is not None else []
        question = Message("user", [f"{context_block}\n\nQuestion: {message}"])
        return [Message("system", [INSTRUCTIONS]), *history, question]

    async def run(self, message: str, thread: ChatThread | None = None):
        self.validate_message(message)

        query_vector = None
        if self._cache is not None:
            hit, query_vector = self._cache.lookup(message)
            if hit is not None:
                self.last_result = hit.result
                return hit.answer

        messages = self._build_messages(message, thread)
        response = await asyncio.wait_for(
            self._chat_client.get_response(messages=messages, stream=False, options=self._chat_options),
            timeout=self.config.retrieval.agent_timeout_seconds,
        )
        answer = response.text

        if thread is not None:
            thread.extend(message, answer)
        if self._cache is not None and not self.last_result.is_empty:
            self._cache.store(message, query_vector, answer, self.last_result)

        return answer

    async def run_stream(self, message: str, thread: ChatThread | None = None) -> AsyncIterator[str]:
        self.validate_message(message)

        query_vector = None
        if self._cache is not None:
            hit, query_vector = self._cache.lookup(message)
            if hit is not None:
                self.last_result = hit.result
                yield hit.answer
                return

        messages = self._build_messages(message, thread)
        stream = self._chat_client.get_response(messages=messages, stream=True, options=self._chat_options)
        aiter = stream.__aiter__()
        deadline = time.monotonic() + self.config.retrieval.agent_timeout_seconds
        chunks: list[str] = []
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise asyncio.TimeoutError()
            try:
                update = await asyncio.wait_for(aiter.__anext__(), timeout=remaining)
            except StopAsyncIteration:
                break
            if update.text:
                chunks.append(update.text)
                yield update.text

        answer = "".join(chunks)
        if thread is not None:
            thread.extend(message, answer)
        if self._cache is not None and not self.last_result.is_empty:
            self._cache.store(message, query_vector, answer, self.last_result)


def build_agent(llm_provider, embedding_provider, graph_provider, config: AppConfig) -> GraphRAGAgent:
    cache = (
        QueryCache(
            embedding_provider,
            similarity_threshold=config.retrieval.query_cache_similarity_threshold,
            max_entries=config.retrieval.query_cache_max_entries,
        )
        if config.retrieval.query_cache_enabled
        else None
    )
    return GraphRAGAgent(
        chat_client=llm_provider.get_chat_client(),
        embedding_provider=embedding_provider,
        graph_provider=graph_provider,
        config=config,
        cache=cache,
        chat_options=llm_provider.get_chat_options(),
    )
