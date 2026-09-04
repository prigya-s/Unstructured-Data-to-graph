"""
COA demo: vector search alone vs. graph-expanded retrieval.

Runs the same Change-of-Address question through each stage of the real
retrieval pipeline (src/retrieval/graphrag_service.py) one stage at a time,
and prints what each stage adds on top of the last:

  1. Vector search only  - db.index.vector.queryNodes over :Chunk.embedding
  2. + entities mentioned in those chunks (:MENTIONS)
  3. + entities reached only by walking the graph (Entity<->Entity neighbors)
  4. + documents reached only via :LEADS_TO ("what happens next")

Also prints a ready-to-paste Neo4j Browser query, filled in with the real
chunk/entity ids this run found, so the traversal can be shown visually.

Usage:
    python demo_coa_vector_vs_graph.py ["your question here"]
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from dotenv import load_dotenv

load_dotenv(_PROJECT_ROOT / ".env")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import providers
from config import load_config
from retrieval.graphrag_service import embed_query

DEFAULT_QUESTION = "What is the process for a change of address request?"


def _header(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def main() -> None:
    question = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUESTION

    config = load_config()
    embedding_provider = providers.get_embedding_provider(config)
    graph_provider = providers.get_graph_provider(config)

    print(f"Question: {question}")
    print(f"(embedding model: {config.embedding.options.get('ollama', {}).get('model', '?')}, "
          f"top_k_chunks={config.retrieval.top_k_chunks}, "
          f"graph_expansion_hops={config.retrieval.graph_expansion_hops}, "
          f"page_link_hops={config.retrieval.page_link_hops})")

    query_vector = embed_query(embedding_provider, question)

    # ---- Stage 1: vector search only ------------------------------------
    chunks = graph_provider.search_chunks(query_vector, config.retrieval.top_k_chunks)
    vector_only_documents = {c["document_name"] for c in chunks}

    _header("STAGE 1 - VECTOR SEARCH ONLY (plain semantic search baseline)")
    if not chunks:
        print("No chunks found - check that the COA documents were ingested.")
        return
    for i, chunk in enumerate(chunks, 1):
        snippet = " ".join(chunk["content"].split())[:160]
        print(f"{i:2d}. [{chunk['document_name']}]  score={chunk['score']:.3f}")
        print(f"      {snippet}...")
    print(f"\n-> {len(chunks)} chunks from {len(vector_only_documents)} documents.")
    print("-> This is all a vector-only search gives you: raw passages, ranked by")
    print("   similarity to the question. No entities, no relationships, no")
    print("   'what happens next' - and no way to tell what's missing.")

    # ---- Stage 2: entities directly mentioned in those chunks ------------
    chunk_ids = [c["chunk_id"] for c in chunks]
    mentioned = graph_provider.get_mentioned_entities(chunk_ids)
    mentioned_ids = {e["entity_id"] for e in mentioned}

    _header("STAGE 2 - ENTITIES MENTIONED IN THOSE CHUNKS  (Chunk-[:MENTIONS]->Entity)")
    for e in mentioned:
        print(f"  - {e['name']}  ({e['entity_type']})")
    print(f"\n-> {len(mentioned)} entities named in the retrieved text.")

    # ---- Stage 3: graph expansion - entities NOT in the text at all -----
    neighbors = {"entities": [], "paths": []}
    if mentioned_ids:
        neighbors = graph_provider.get_neighbors(
            list(mentioned_ids), config.retrieval.graph_expansion_hops, config.retrieval.max_neighbors
        )
    new_entities = [e for e in neighbors["entities"] if e["entity_id"] not in mentioned_ids]

    _header(
        f"STAGE 3 - {config.retrieval.graph_expansion_hops}-HOP GRAPH EXPANSION "
        "(entities reached only by walking the graph)"
    )
    if new_entities:
        for e in new_entities:
            print(f"  - {e['name']}  ({e['entity_type']})")
        print()
        for p in neighbors["paths"]:
            hops = " -> ".join(p["relationship_types"]) if p["relationship_types"] else "related to"
            print(f"      path: {p['source_name']}  --[{hops}]-->  {p['target_name']}")
    else:
        print("  (none found at this hop count)")
    print(f"\n-> {len(new_entities)} additional entities surfaced ONLY by traversing the graph -")
    print("   none of these names appear anywhere in the top-k chunk text above.")

    # ---- Stage 4: documents reached via LEADS_TO -------------------------
    document_ids = list({c["document_id"] for c in chunks})
    linked = graph_provider.get_linked_documents(
        document_ids, config.retrieval.page_link_hops, config.retrieval.max_neighbors
    )
    new_documents = [d for d in linked["documents"] if d["name"] not in vector_only_documents]

    _header(
        f"STAGE 4 - DOCUMENTS REACHED VIA :LEADS_TO, {config.retrieval.page_link_hops} hops "
        "('what happens next')"
    )
    if new_documents:
        for d in new_documents:
            print(f"  - {d['name']}")
        print()
        for p in linked["paths"]:
            labels = [l for l in (p["answer_labels"] or []) if l]
            condition = (" -> ".join(labels)) if labels else "(no condition recorded)"
            print(f"      {p['source_name']}  --[{condition}]-->  {p['target_name']}")
    else:
        print("  (none found - these documents have no outgoing decision-tree links)")
    print(f"\n-> {len(new_documents)} follow-on documents surfaced ONLY via graph links -")
    print("   none of these were in the vector-only result set, because they may not")
    print("   be semantically similar to the question at all (they're reachable by")
    print("   process/decision-tree structure, not by wording).")

    # ---- Summary -----------------------------------------------------------
    _header("SUMMARY - what vector search alone would have missed")
    print(f"Vector search alone:     {len(chunks)} chunks, {len(vector_only_documents)} documents, 0 entities, 0 relationships, 0 next-steps.")
    print(
        f"With graph traversal:   +{len(mentioned)} mentioned entities, "
        f"+{len(new_entities)} graph-only entities, "
        f"+{len(neighbors['paths'])} entity relationships, "
        f"+{len(new_documents)} follow-on documents."
    )

    # ---- Ready-to-paste Neo4j Browser query for a live visual demo -------
    # Every hop's relationship is bound to its own variable (h, m, r, l) and
    # returned explicitly - Neo4j Browser only draws an edge for a
    # relationship that comes back in the result, so a query that only
    # returns node variables (even when a path clearly connects them)
    # renders as disconnected dots.
    def browser_query(ids: list[str], hops: int, link_hops: int) -> str:
        return (
            "MATCH (c:Chunk) WHERE c.id IN " + repr(ids) + "\n"
            "OPTIONAL MATCH (d:Document)-[h:HAS_CHUNK]->(c)\n"
            "OPTIONAL MATCH (c)-[m:MENTIONS]->(e:Entity)\n"
            "OPTIONAL MATCH (e)-[r*1..%d]-(n:Entity)\n"
            "OPTIONAL MATCH (d)-[l:LEADS_TO*1..%d]->(nd:Document)\n"
            "RETURN c, d, h, e, m, n, r, nd, l" % (hops, link_hops)
        )

    # Find which of the retrieved chunks actually end up wired together
    # (via a shared entity, shared entity-neighbor, or a document-to-document
    # LEADS_TO link) versus which sit in their own isolated pocket of the
    # graph. This is a real property of the data, not a rendering artifact -
    # two chunks whose only entity mentions never connect to anything else
    # WILL look disconnected in Neo4j Browser no matter how the query is
    # written, and that is worth knowing before the demo, not during it.
    hops = config.retrieval.graph_expansion_hops
    probe_rows = graph_provider.query_graph(
        "MATCH (c:Chunk) WHERE c.id IN $chunk_ids\n"
        "OPTIONAL MATCH (d:Document)-[:HAS_CHUNK]->(c)\n"
        "OPTIONAL MATCH (c)-[:MENTIONS]->(e:Entity)\n"
        "OPTIONAL MATCH (e)-[*1..%d]-(n:Entity)\n"
        "OPTIONAL MATCH (d)-[:LEADS_TO*1..%d]->(nd:Document)\n"
        "RETURN c.id AS c, d.name AS d, e.name AS e, n.name AS n, nd.name AS nd"
        % (hops, config.retrieval.page_link_hops),
        {"chunk_ids": chunk_ids},
    )

    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    chunk_to_doc: dict[str, str] = {}
    for row in probe_rows:
        c_node, d_node = "C:" + row["c"], ("D:" + row["d"] if row["d"] else None)
        e_node, n_node = ("E:" + row["e"] if row["e"] else None), ("E:" + row["n"] if row["n"] else None)
        nd_node = "D:" + row["nd"] if row["nd"] else None
        find(c_node)
        if d_node:
            union(c_node, d_node)
            chunk_to_doc[row["c"]] = row["d"]
        if e_node:
            union(c_node, e_node)
        if e_node and n_node:
            union(e_node, n_node)
        if d_node and nd_node:
            union(d_node, nd_node)

    components: dict[str, list[str]] = {}
    for chunk_id in chunk_ids:
        components.setdefault(find("C:" + chunk_id), []).append(chunk_id)

    largest_component = max(components.values(), key=len)

    _header("GRAPH CONNECTIVITY - is this one connected picture, or several?")
    print(f"{len(components)} separate connected cluster(s) among the {len(chunk_ids)} retrieved chunks:")
    for members in sorted(components.values(), key=len, reverse=True):
        docs = sorted({chunk_to_doc.get(cid, "?") for cid in members})
        print(f"  - {len(members)} chunk(s) -> documents: {docs}")
    if len(components) > 1:
        print(
            "\nA cluster of its own does not mean the query is broken - it means that"
            "\nchunk's entities/relationships genuinely don't connect to anything else"
            "\nin this result set. Two options below: the full picture (islands and all,"
            "\nwhich is itself a legitimate 'the graph tells you these are unrelated"
            "\nasides' talking point), or a query restricted to the single largest"
            "\nconnected cluster for a clean one-picture visual."
        )

    _header("NEO4J BROWSER - option A: full picture (may show separate clusters)")
    print(browser_query(chunk_ids, hops, config.retrieval.page_link_hops))

    _header(
        f"NEO4J BROWSER - option B: largest connected cluster only "
        f"({len(largest_component)} of {len(chunk_ids)} chunks - guaranteed one connected graph)"
    )
    print(browser_query(largest_component, hops, config.retrieval.page_link_hops))


if __name__ == "__main__":
    main()
