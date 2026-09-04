"""
FastAPI entry point for the React-based Entity Review app. Every route
wraps existing src/ code directly (see api/deps.py, api/routers/*.py);
this file only owns process startup and HTTP wiring.

Run with:
    uvicorn api.main:app --reload --port 8000

In local dev, the React app runs separately via `npm run dev` in web/ and
proxies /api/* to this server (see web/vite.config.ts). In a
production-shaped run, `npm run build`'s output (web/dist/) is mounted
below as static files, so one process serves both the API and the UI - the
same single-process shape Databricks Apps expects.
"""

from __future__ import annotations

import sys
from pathlib import Path

_API_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _API_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import deps
from api.routers import (
    ambiguity,
    candidate_graph,
    chat,
    class_proposals,
    dashboard,
    entities,
    graph_diff,
    health,
    ontology,
    production_graph,
    publish,
    relationships,
    retrieval_trace,
)

load_dotenv(_PROJECT_ROOT / ".env")

_WEB_DIST = _PROJECT_ROOT / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    deps.init_providers()
    yield


app = FastAPI(title="Entity Review API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(retrieval_trace.router)
app.include_router(dashboard.router)
app.include_router(entities.router)
app.include_router(relationships.router)
app.include_router(ambiguity.router)
app.include_router(class_proposals.router)
app.include_router(candidate_graph.router)
app.include_router(production_graph.router)
app.include_router(graph_diff.router)
app.include_router(ontology.router)
app.include_router(publish.router)

if _WEB_DIST.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=_WEB_DIST, html=True), name="web")
