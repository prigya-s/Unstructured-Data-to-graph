"""Publish endpoints wrapping the same two PipelineRunner stages
app/pages/publish.py drives (OntologyStage, GraphStage). Both stages are
slow (real storage/graph I/O), so each POST kicks the stage off via
run_in_threadpool and returns a job_id immediately; the client polls
GET /api/publish/jobs/{job_id} for the result - a plain in-memory dict is
enough at this scale, no queue needed. Job state does not survive a
backend restart, same tradeoff as chat.py's thread store."""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

import providers
from api import deps
from api.schemas import PublishJobResponse, PublishJobStatus, PublishSummaryResponse
from config import load_config
from config.app_config import AppConfig
from pipeline.context import PipelineContext
from pipeline.runner import PipelineRunner
from pipeline.stages.graph_stage import GraphStage
from pipeline.stages.ontology_stage import OntologyStage
from review import WorkflowStatus
from review.repository import OntologyRepository

logger = logging.getLogger("kg_local.api.publish")

router = APIRouter()

_RUNNER = PipelineRunner([OntologyStage(), GraphStage()])
_jobs: dict[str, PublishJobStatus] = {}

_PENDING = (WorkflowStatus.NEW, WorkflowStatus.PENDING_REVIEW)

_GRAPH_CONNECTION_ERROR = (
    "Could not publish to the graph database. If you're using a local Neo4j "
    "instance, make sure Neo4j Desktop/Docker is running; if you're using Neo4j "
    "AuraDB, check your internet connection. Either way, check the credentials in "
    "your .env file, or check the log file for details."
)


def _build_context(config: AppConfig) -> PipelineContext:
    return PipelineContext(
        config=config,
        storage=providers.get_storage_provider(config),
        document_source=providers.get_document_source(config),
        embedding_provider=providers.get_embedding_provider(config),
        approval_provider=providers.get_approval_provider(config),
        ontology_provider=providers.get_ontology_provider(config),
        graph_provider=deps.get_graph_provider(),
        extraction_provider=providers.get_extraction_provider(config),
    )


async def _run_job(job_id: str, stage_name: str) -> None:
    try:
        ctx = await run_in_threadpool(_RUNNER.run_stage, stage_name, _build_context(load_config()))
    except ValueError as exc:
        _jobs[job_id] = PublishJobStatus(status="failed", error=str(exc))
        return
    except Exception:  # noqa: BLE001 - surfaced to the client via job status
        logger.exception("Publish job %s (stage=%s) failed", job_id, stage_name)
        error = _GRAPH_CONNECTION_ERROR if stage_name == "graph" else "Ontology generation failed. Check the log file for details."
        _jobs[job_id] = PublishJobStatus(status="failed", error=error)
        return

    result = ctx.ontology_result if stage_name == "ontology" else ctx.publish_stats
    _jobs[job_id] = PublishJobStatus(status="succeeded", result=result)


def _start_job(stage_name: str) -> PublishJobResponse:
    job_id = str(uuid.uuid4())
    _jobs[job_id] = PublishJobStatus(status="running")
    asyncio.create_task(_run_job(job_id, stage_name))
    return PublishJobResponse(job_id=job_id)


@router.get("/api/publish/summary")
def get_publish_summary(repo: OntologyRepository = Depends(deps.get_repository)) -> PublishSummaryResponse:
    entities = repo.get_candidate_entities()
    relationships = repo.get_candidate_relationships()
    return PublishSummaryResponse(
        approved_entities=sum(1 for e in entities if e.status == WorkflowStatus.APPROVED),
        approved_relationships=sum(1 for r in relationships if r.status == WorkflowStatus.APPROVED),
        pending_entities=sum(1 for e in entities if e.status in _PENDING),
        pending_relationships=sum(1 for r in relationships if r.status in _PENDING),
    )


@router.post("/api/publish/ontology")
async def publish_ontology() -> PublishJobResponse:
    return _start_job("ontology")


@router.post("/api/publish/graph")
async def publish_graph() -> PublishJobResponse:
    return _start_job("graph")


@router.get("/api/publish/jobs/{job_id}")
def get_publish_job(job_id: str) -> PublishJobStatus:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return job
