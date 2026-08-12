"""
Ask the Knowledge Graph: conversational retrieval over the approved
Production Graph only. Business-friendly language only - never "Node",
"Edge", "Cypher", or "Ontology Class" in UI copy (see app/common.py).
"""

from __future__ import annotations

import asyncio
import time

import streamlit as st

import providers
from common import get_logger
from config import load_config

logger = get_logger()

st.title("Ask the Knowledge Graph")
st.caption(
    "Answers are grounded only in the approved Production Graph - never unapproved candidates."
)


def _build_agent():
    from agents.graphrag_agent import build_agent

    config = load_config()
    embedding_provider = providers.get_embedding_provider(config)
    graph_provider = providers.get_graph_provider(config)
    llm_provider = providers.get_llm_provider(config)
    return build_agent(llm_provider, embedding_provider, graph_provider, config)


if "graphrag_agent" not in st.session_state:
    try:
        st.session_state.graphrag_agent = _build_agent()
        st.session_state.graphrag_thread = st.session_state.graphrag_agent.get_new_thread()
        st.session_state.chat_history = []
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

agent = st.session_state.graphrag_agent

for turn in st.session_state.chat_history:
    with st.chat_message(turn["role"]):
        st.write(turn["content"])
        if turn.get("citations"):
            with st.expander("Sources"):
                st.dataframe(
                    [
                        {"Source Chunk": c["chunk_id"], "Source Document": c["document_id"]}
                        for c in turn["citations"]
                    ],
                    use_container_width=True,
                )
                if turn.get("graph_paths"):
                    st.caption("Graph path used:")
                    for path in turn["graph_paths"]:
                        st.write(f"- {path}")

query = st.chat_input("Ask a question about the approved knowledge graph...")
if query:
    st.session_state.chat_history.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.write(query)

    with st.chat_message("assistant"):
        started_at = time.monotonic()
        try:
            response = asyncio.run(agent.run(query, thread=st.session_state.graphrag_thread))
            answer = str(response)
            st.write(answer)

            result = agent.last_result
            turn = {
                "role": "assistant",
                "content": answer,
                "citations": result.citations,
                "graph_paths": result.graph_paths,
            }
            logger.info(
                "Chat query answered in %.2fs (chunks=%d, entities=%d)",
                time.monotonic() - started_at,
                len(result.chunks),
                len(result.entities),
            )
            if result.citations:
                with st.expander("Sources"):
                    st.dataframe(
                        [
                            {"Source Chunk": c["chunk_id"], "Source Document": c["document_id"]}
                            for c in result.citations
                        ],
                        use_container_width=True,
                    )
                    if result.graph_paths:
                        st.caption("Graph path used:")
                        for path in result.graph_paths:
                            st.write(f"- {path}")
            st.session_state.chat_history.append(turn)
        except asyncio.TimeoutError:
            st.error("That took too long to answer - please try again.")
        except ValueError as exc:
            st.error(str(exc))
        except Exception:  # noqa: BLE001 - keep the UI alive on provider/LLM errors
            logger.exception("Chat turn failed")
            st.error(
                "Could not get an answer from the Knowledge Graph Assistant. Check your Azure "
                "OpenAI and Neo4j configuration, or check the log file for details."
            )
