"""build_graph() assembles Document/Chunk/Entity nodes plus relationships.
Coverage here: page_hierarchy is derived only for documents carrying a
parent_page_id (the MYDET Confluence-export case), and documents without
the optional MYDET provenance fields (today's existing-source shape) still
build a valid graph - the new fields/relationship must be purely additive."""

from __future__ import annotations

from graph.graph_builder import build_graph


def _document(**overrides):
    base = {
        "document_id": "d1",
        "document_name": "Doc 1",
        "source_path": "d1.json",
        "markdown_path": "d1.md",
    }
    base.update(overrides)
    return base


def test_build_graph_with_minimal_document_fields_is_backward_compatible():
    graph = build_graph([_document()], [], [], [], [])

    doc_node = graph["nodes"]["documents"][0]
    assert doc_node["space_key"] is None
    assert doc_node["parent_page_id"] is None
    assert graph["relationships"]["page_hierarchy"] == []
    assert graph["stats"]["page_hierarchy"] == 0


def test_build_graph_derives_page_hierarchy_from_parent_page_id():
    documents = [
        _document(document_id="parent", parent_page_id=None),
        _document(document_id="child", parent_page_id="parent", space_key="MYDET", version=2, content_hash="h1"),
    ]

    graph = build_graph(documents, [], [], [], [])

    assert graph["relationships"]["page_hierarchy"] == [{"child_id": "child", "parent_id": "parent"}]
    assert graph["stats"]["page_hierarchy"] == 1

    child_node = next(d for d in graph["nodes"]["documents"] if d["id"] == "child")
    assert child_node["space_key"] == "MYDET"
    assert child_node["version"] == 2
    assert child_node["content_hash"] == "h1"


def test_build_graph_omits_hierarchy_entry_for_documents_without_parent():
    documents = [_document(document_id="d1"), _document(document_id="d2")]

    graph = build_graph(documents, [], [], [], [])

    assert graph["relationships"]["page_hierarchy"] == []


def test_build_graph_extracts_page_link_with_answer_label():
    documents = [
        _document(
            document_id="100",
            markdown=(
                "Some intro. smallblueAn adulthttps://confluence.example.com/wiki/"
                "pages/200/MD1.50+-+Q19 more text."
            ),
        ),
        _document(document_id="200"),
    ]

    graph = build_graph(documents, [], [], [], [])

    assert graph["relationships"]["page_links"] == [
        {"source_id": "100", "target_id": "200", "answer_label": "An adult"}
    ]
    assert graph["stats"]["page_links"] == 1
    assert graph["stats"]["page_links_dropped_external"] == 0


def test_build_graph_drops_and_counts_link_to_page_outside_corpus():
    documents = [
        _document(
            document_id="100",
            markdown=(
                "smallblueA childhttps://confluence.example.com/wiki/pages/999/Some+Page"
            ),
        ),
    ]

    graph = build_graph(documents, [], [], [], [])

    assert graph["relationships"]["page_links"] == []
    assert graph["stats"]["page_links"] == 0
    assert graph["stats"]["page_links_dropped_external"] == 1


def test_build_graph_page_with_no_links_produces_no_page_links():
    documents = [_document(document_id="100", markdown="Just plain prose, no links here.")]

    graph = build_graph(documents, [], [], [], [])

    assert graph["relationships"]["page_links"] == []
    assert graph["stats"]["page_links_dropped_external"] == 0
