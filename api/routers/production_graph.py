"""GET /api/production-graph - passthrough of storage.read_graph_export(),
same call app/pages/production_graph.py makes. Returns null when nothing
has been published yet (same as the Streamlit page's "not published" case)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api import deps
from providers.storage_provider import StorageProvider

router = APIRouter()


@router.get("/api/production-graph")
def get_production_graph(storage: StorageProvider = Depends(deps.get_storage)) -> dict | None:
    return storage.read_graph_export()
